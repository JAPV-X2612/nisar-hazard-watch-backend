import json
from pathlib import Path

import httpx
import pytest

from nisar_hazard_watch.adapters.geocoding.nominatim_geocoder import NominatimGeocoder
from nisar_hazard_watch.exceptions.place_errors import GeocoderUnavailableError

FIXTURE = Path(__file__).parents[3] / "fixtures" / "nominatim_qadirabad.json"
BASE_URL = "https://geocoder.example.test/search"
FIRST_PLACE_ID = "n4295615569"
FIRST_PLACE_POINT = (73.5025289, 32.297263)
FIRST_PLACE_BBOX = (73.4625289, 32.257263, 73.5425289, 32.337263)
PLACE_COUNT = 3


def _fixture() -> list[dict]:
    return json.loads(FIXTURE.read_text())


def _answering(body: object, status: int = 200) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status_code=status, json=body))


async def _search(transport: httpx.MockTransport, query: str = "Qadirabad", limit: int = 6) -> list:
    async with httpx.AsyncClient(transport=transport) as client:
        return await NominatimGeocoder(client=client, base_url=BASE_URL).search(
            query=query, limit=limit
        )


async def test_it_maps_the_real_answer_to_places_with_a_box_in_west_south_east_north_order() -> (
    None
):
    # Arrange
    transport = _answering(_fixture())

    # Act
    places = await _search(transport=transport)

    # Assert
    assert len(places) == PLACE_COUNT
    first = places[0]
    assert first.id == FIRST_PLACE_ID
    assert first.name == "Qadirabad"
    assert first.display_name.endswith("Punjab, Pakistan")
    assert first.kind == "town"
    assert first.point == FIRST_PLACE_POINT
    assert first.bbox == FIRST_PLACE_BBOX
    assert first.importance == pytest.approx(0.16004, abs=1e-4)


async def test_the_request_names_the_text_the_language_and_the_limit() -> None:
    # Arrange
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(status_code=200, json=[])

    # Act
    await _search(transport=httpx.MockTransport(handler), query="Río Cauca", limit=4)

    # Assert
    params = sent[0].url.params
    assert str(sent[0].url).startswith(BASE_URL)
    assert params["q"] == "Río Cauca"
    assert params["limit"] == "4"
    assert params["format"] == "jsonv2"
    assert params["accept-language"] == "en"


async def test_a_place_without_a_name_uses_the_first_part_of_its_display_name() -> None:
    # Arrange
    item = {**_fixture()[0], "name": ""}

    # Act
    places = await _search(transport=_answering([item]))

    # Assert
    assert places[0].name == "Qadirabad"


async def test_a_place_without_a_box_still_has_its_point() -> None:
    # Arrange
    item = {key: value for key, value in _fixture()[0].items() if key != "boundingbox"}

    # Act
    places = await _search(transport=_answering([item]))

    # Assert
    assert places[0].bbox is None
    assert places[0].point == FIRST_PLACE_POINT


async def test_no_results_is_an_empty_list_not_an_error() -> None:
    # Arrange
    transport = _answering([])

    # Act
    places = await _search(transport=transport)

    # Assert
    assert places == []


async def test_an_unreadable_place_is_skipped_while_the_others_stay() -> None:
    # Arrange
    body = [{"osm_type": "node"}, _fixture()[0]]

    # Act
    places = await _search(transport=_answering(body))

    # Assert
    assert [place.id for place in places] == [FIRST_PLACE_ID]


@pytest.mark.parametrize(
    argnames="transport",
    argvalues=[
        httpx.MockTransport(lambda request: httpx.Response(status_code=503, json=[])),
        httpx.MockTransport(lambda request: httpx.Response(status_code=200, content=b"not json")),
        httpx.MockTransport(lambda request: httpx.Response(status_code=200, json={"a": 1})),
        httpx.MockTransport(lambda request: httpx.Response(status_code=200, json=[{"x": 1}])),
    ],
    ids=["provider-error", "invalid-json", "not-a-list", "nothing-readable"],
)
async def test_a_failing_or_unreadable_provider_is_an_unavailable_search(
    transport: httpx.MockTransport,
) -> None:
    # Arrange
    failing_transport = transport

    # Act / Assert
    with pytest.raises(expected_exception=GeocoderUnavailableError):
        await _search(transport=failing_transport)


async def test_a_network_failure_is_an_unavailable_search() -> None:
    # Arrange
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    # Act / Assert
    with pytest.raises(expected_exception=GeocoderUnavailableError):
        await _search(transport=httpx.MockTransport(unreachable))
