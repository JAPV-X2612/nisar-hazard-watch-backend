import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from nisar_hazard_watch.adapters.asf.asf_catalog import AsfCatalog
from nisar_hazard_watch.constants.sar import CATALOG_MAX_RESULTS, Configuration, Maturity
from nisar_hazard_watch.exceptions.catalog_errors import (
    CatalogTruncatedError,
    CatalogUnavailableError,
)
from tests.factories import qadirabad_aoi

FIXTURE = Path(__file__).parents[3] / "fixtures" / "asf_qadirabad.json"
START = datetime(2026, 6, 12, tzinfo=UTC)
END = datetime(2026, 11, 12, tzinfo=UTC)
SCENE_COUNT = 47
EXPECTED_MATURITIES = {Maturity.PROVISIONAL: 39, Maturity.VALIDATED: 4, Maturity.UNVALIDATED: 4}
EXPECTED_CONFIGURATIONS = {Configuration.PRODUCTION: 43, Configuration.URGENT_RESPONSE: 4}


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def _answering(body: object, status: int = 200) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status_code=status, json=body))


async def _search(transport: httpx.MockTransport) -> list:
    async with httpx.AsyncClient(transport=transport) as client:
        catalog = AsfCatalog(client=client)
        return await catalog.search(aoi=qadirabad_aoi(), start=START, end=END)


async def test_it_parses_every_real_granule_with_its_maturity_and_configuration() -> None:
    # Arrange
    transport = _answering(_fixture())

    # Act
    scenes = await _search(transport=transport)

    # Assert
    assert len(scenes) == SCENE_COUNT
    assert dict(Counter(scene.maturity for scene in scenes)) == EXPECTED_MATURITIES
    assert dict(Counter(scene.configuration for scene in scenes)) == EXPECTED_CONFIGURATIONS


async def test_it_reports_how_much_of_the_aoi_each_footprint_covers() -> None:
    # Arrange
    transport = _answering(_fixture())

    # Act
    scenes = await _search(transport=transport)

    # Assert
    assert all(0.0 <= scene.coverage <= 1.0 for scene in scenes)
    assert max(scene.coverage for scene in scenes) == 1.0


async def test_it_asks_asf_without_maturity_or_configuration_filters() -> None:
    # Arrange
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code=200, json={"type": "FeatureCollection", "features": []})

    # Act
    await _search(transport=httpx.MockTransport(handler))

    # Assert
    params = dict(requests[0].url.params)
    assert params["dataset"] == "NISAR"
    assert params["processingLevel"] == "GCOV"
    assert params["output"] == "geojson"
    assert params["maxResults"] == str(CATALOG_MAX_RESULTS)
    assert params["start"] == "2026-06-12T00:00:00Z"
    assert params["end"] == "2026-11-12T00:00:00Z"
    assert params["intersectsWith"].startswith("POLYGON")
    assert "dataMaturity" not in params
    assert "productionConfiguration" not in params


async def test_a_result_that_may_have_been_cut_off_is_an_error_not_a_silent_gap() -> None:
    # Arrange
    features = _fixture()["features"]
    body = {"type": "FeatureCollection", "features": (features * 11)[:CATALOG_MAX_RESULTS]}

    # Act / Assert
    with pytest.raises(expected_exception=CatalogTruncatedError):
        await _search(transport=_answering(body))


async def test_products_with_unrecognised_names_are_skipped() -> None:
    # Arrange
    body = _fixture()
    body["features"][0]["properties"]["sceneName"] = "something-unexpected"

    # Act
    scenes = await _search(transport=_answering(body))

    # Assert
    assert len(scenes) == SCENE_COUNT - 1


async def test_features_without_a_footprint_are_skipped() -> None:
    # Arrange
    body = _fixture()
    body["features"][0]["geometry"] = None

    # Act
    scenes = await _search(transport=_answering(body))

    # Assert
    assert len(scenes) == SCENE_COUNT - 1


@pytest.mark.parametrize(
    argnames="transport",
    argvalues=[
        _answering({}, status=503),
        _answering({"unexpected": "payload"}),
        httpx.MockTransport(lambda request: httpx.Response(status_code=200, content=b"not json")),
    ],
    ids=["http-error", "missing-features", "invalid-json"],
)
async def test_a_failing_or_malformed_answer_is_reported_as_an_unavailable_catalog(
    transport: httpx.MockTransport,
) -> None:
    # Arrange
    failing_transport = transport

    # Act / Assert
    with pytest.raises(expected_exception=CatalogUnavailableError):
        await _search(transport=failing_transport)


async def test_a_network_failure_is_reported_as_an_unavailable_catalog() -> None:
    # Arrange
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    # Act / Assert
    with pytest.raises(expected_exception=CatalogUnavailableError):
        await _search(transport=httpx.MockTransport(unreachable))


async def test_a_product_with_null_fields_is_skipped_instead_of_failing_the_search() -> None:
    # Arrange
    body = _fixture()
    body["features"][0]["properties"]["sceneName"] = None
    body["features"][1]["properties"]["url"] = None

    # Act
    scenes = await _search(transport=_answering(body))

    # Assert
    assert len(scenes) == SCENE_COUNT - 2


async def test_an_unreadable_footprint_skips_only_that_product() -> None:
    # Arrange
    body = _fixture()
    body["features"][0]["geometry"] = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]}

    # Act
    scenes = await _search(transport=_answering(body))

    # Assert
    assert len(scenes) == SCENE_COUNT - 1


async def test_a_catalog_whose_products_are_all_unrecognised_is_not_reported_as_empty() -> None:
    # Arrange
    body = _fixture()
    for feature in body["features"]:
        feature["properties"]["url"] = "https://example.test/new-collection/product.h5"

    # Act / Assert
    with pytest.raises(expected_exception=CatalogUnavailableError, match="format may have changed"):
        await _search(transport=_answering(body))


async def test_an_empty_answer_is_a_valid_empty_catalog() -> None:
    # Arrange
    body = {"type": "FeatureCollection", "features": []}

    # Act
    scenes = await _search(transport=_answering(body))

    # Assert
    assert scenes == []
