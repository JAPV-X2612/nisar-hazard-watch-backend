import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from nisar_hazard_watch.adapters.gateway.gateway_case_catalog import GatewayCaseCatalog
from nisar_hazard_watch.exceptions.case_errors import CasesUnavailableError
from nisar_hazard_watch.models.case import CaseView
from tests.honesty import forbidden_keys

FIXTURE = Path(__file__).parents[3] / "fixtures" / "ml_gateway_cases.json"
BASE_URL = "https://gateway.example.test"
CASE_IDS = ["chokwe", "qadirabad", "richmond", "kumamoto", "choco"]
QADIRABAD_LAYER_URL = f"{BASE_URL}/v2/cases/qadirabad/layers/change_db_hh.png"


def _real_cases() -> list[dict[str, Any]]:
    return json.loads(FIXTURE.read_text())


class Recorder:
    def __init__(self, answer: httpx.Response | Exception) -> None:
        self.requests: list[httpx.Request] = []
        self._answer = answer

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer


async def _cases(handler: Recorder) -> list[CaseView]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await GatewayCaseCatalog(client=client, base_url=BASE_URL + "/").cases()


async def test_it_reads_every_real_case_in_the_gateway_order() -> None:
    # Arrange
    handler = Recorder(answer=httpx.Response(status_code=200, json=_real_cases()))

    # Act
    cases = await _cases(handler=handler)

    # Assert
    assert [case.id for case in cases] == CASE_IDS
    assert str(handler.requests[0].url) == f"{BASE_URL}/v2/cases"
    qadirabad = cases[1]
    assert (len(qadirabad.layers), len(qadirabad.visualizations)) == (8, 8)
    assert qadirabad.layers[0].url == QADIRABAD_LAYER_URL
    assert qadirabad.layers[0].value_range == (-8.0, 8.0)
    assert qadirabad.evidence.threshold_cells == 1911
    assert qadirabad.evidence.radar_support_cells == 16384
    assert len(qadirabad.limitations) == 7
    assert qadirabad.is_demo is False


@pytest.mark.parametrize(argnames="index", argvalues=range(len(CASE_IDS)), ids=CASE_IDS)
async def test_no_relayed_key_names_an_unvalidated_value(index: int) -> None:
    # Arrange
    handler = Recorder(answer=httpx.Response(status_code=200, json=_real_cases()))

    # Act
    case = (await _cases(handler=handler))[index]

    # Assert
    dumped = case.model_dump(mode="json")
    assert forbidden_keys(dumped) == []
    assert "provenance" not in (dumped["evidence"]["independentReference"] or {})


async def test_a_nested_unvalidated_key_is_dropped_too() -> None:
    # Arrange
    raw = _real_cases()
    raw[1]["evidence"]["comparison"]["affected_area_ha"] = 12.5
    handler = Recorder(answer=httpx.Response(status_code=200, json=raw))

    # Act
    cases = await _cases(handler=handler)

    # Assert
    comparison = cases[1].evidence.comparison or {}
    assert "affected_area_ha" not in comparison
    assert "scored_pixels" in comparison


async def test_a_case_whose_layer_lives_on_another_host_is_skipped() -> None:
    # Arrange
    raw = _real_cases()
    raw[0]["layers"][0]["png_url"] = "https://elsewhere.example.test/x.png"
    handler = Recorder(answer=httpx.Response(status_code=200, json=raw))

    # Act
    cases = await _cases(handler=handler)

    # Assert
    assert [case.id for case in cases] == CASE_IDS[1:]


@pytest.mark.parametrize(
    argnames="answer",
    argvalues=[
        httpx.Response(status_code=503, json={"detail": "down"}),
        httpx.Response(status_code=200, content=b"<html>"),
        httpx.Response(status_code=200, json={"cases": []}),
        httpx.Response(status_code=200, json=[{"id": "broken"}]),
        httpx.ConnectError("refused"),
    ],
    ids=["outage", "not-json", "not-a-list", "nothing-valid", "unreachable"],
)
async def test_an_unusable_answer_means_the_cases_are_unavailable(
    answer: httpx.Response | Exception,
) -> None:
    # Arrange
    handler = Recorder(answer=answer)

    # Act / Assert
    with pytest.raises(CasesUnavailableError):
        await _cases(handler=handler)
