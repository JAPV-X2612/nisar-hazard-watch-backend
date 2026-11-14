import asyncio
import json
from pathlib import Path

import httpx
import pytest

from nisar_hazard_watch.adapters.gateway.gateway_case_catalog import GatewayCaseCatalog
from nisar_hazard_watch.exceptions.case_errors import (
    CaseLayerNotFoundError,
    CaseNotFoundError,
    CasesUnavailableError,
)
from nisar_hazard_watch.models.case import CaseView
from nisar_hazard_watch.services.case_service import CaseService

FIXTURE = Path(__file__).parents[2] / "fixtures" / "ml_gateway_cases.json"
BASE_URL = "https://gateway.example.test"
TTL_SECONDS = 600.0
RETRY_AFTER_SECONDS = 60.0
LAYER_PATH = "/api/v1/cases/qadirabad/layers"


async def _real_cases() -> list[CaseView]:
    body = json.loads(FIXTURE.read_text())
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code=200, json=body))
    async with httpx.AsyncClient(transport=transport) as client:
        return await GatewayCaseCatalog(client=client, base_url=BASE_URL).cases()


class FakeCatalog:
    def __init__(self, cases: list[CaseView]) -> None:
        self.calls = 0
        self.down = False
        self.cases_to_answer = cases
        # Cleared to hold every call open, like a gateway that takes seconds to answer.
        self.gate = asyncio.Event()
        self.gate.set()

    async def cases(self) -> list[CaseView]:
        self.calls += 1
        await self.gate.wait()
        if self.down:
            raise CasesUnavailableError("down")
        return self.cases_to_answer


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
async def catalog() -> FakeCatalog:
    return FakeCatalog(cases=await _real_cases())


def _service(catalog: FakeCatalog, clock: FakeClock) -> CaseService:
    return CaseService(
        catalog=catalog,
        ttl_seconds=TTL_SECONDS,
        retry_after_seconds=RETRY_AFTER_SECONDS,
        clock=clock,
    )


async def _let_the_refresh_run() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_a_second_call_within_ten_minutes_does_not_reach_the_gateway(
    catalog: FakeCatalog,
) -> None:
    # Arrange
    clock = FakeClock()
    service = _service(catalog=catalog, clock=clock)
    await service.cases()

    # Act
    clock.now += TTL_SECONDS - 1
    await service.get(case_id="qadirabad")

    # Assert
    assert catalog.calls == 1


async def test_the_cases_are_read_again_once_the_copy_expires(catalog: FakeCatalog) -> None:
    # Arrange
    clock = FakeClock()
    service = _service(catalog=catalog, clock=clock)
    await service.cases()
    fresh = catalog.cases_to_answer[:1]
    catalog.cases_to_answer = fresh

    # Act
    clock.now += TTL_SECONDS + 1
    await service.cases()
    await _let_the_refresh_run()
    view = await service.cases()

    # Assert
    assert catalog.calls == 2
    assert [case.id for case in view.cases] == [fresh[0].id]


async def test_a_stale_copy_is_served_when_the_gateway_is_down(catalog: FakeCatalog) -> None:
    # Arrange
    clock = FakeClock()
    service = _service(catalog=catalog, clock=clock)
    await service.cases()
    catalog.down = True
    clock.now += TTL_SECONDS + 1

    # Act
    view = await service.cases()
    await _let_the_refresh_run()

    # Assert
    assert len(view.cases) == 6
    assert catalog.calls == 2


async def test_an_outage_is_not_retried_on_every_request(catalog: FakeCatalog) -> None:
    # Arrange
    clock = FakeClock()
    service = _service(catalog=catalog, clock=clock)
    await service.cases()
    catalog.down = True
    clock.now += TTL_SECONDS + 1
    await service.cases()
    await _let_the_refresh_run()

    # Act
    for _ in range(30):
        await service.layer_url(case_id="qadirabad", layer_id="change_db_hh")
    await _let_the_refresh_run()
    calls_while_backing_off = catalog.calls
    clock.now += RETRY_AFTER_SECONDS
    await service.cases()
    await _let_the_refresh_run()

    # Assert
    assert calls_while_backing_off == 2
    assert catalog.calls == 3


async def test_an_outage_with_no_copy_is_not_retried_on_every_request(
    catalog: FakeCatalog,
) -> None:
    # Arrange
    clock = FakeClock()
    catalog.down = True
    service = _service(catalog=catalog, clock=clock)
    with pytest.raises(CasesUnavailableError):
        await service.cases()

    # Act
    with pytest.raises(CasesUnavailableError):
        await service.get(case_id="qadirabad")
    calls_while_backing_off = catalog.calls
    catalog.down = False
    clock.now += RETRY_AFTER_SECONDS
    view = await service.cases()

    # Assert
    assert calls_while_backing_off == 1
    assert catalog.calls == 2
    assert len(view.cases) == 6


async def test_concurrent_misses_make_one_gateway_call(catalog: FakeCatalog) -> None:
    # Arrange
    service = _service(catalog=catalog, clock=FakeClock())
    catalog.gate.clear()
    waiting = [asyncio.create_task(service.cases()) for _ in range(5)]
    await _let_the_refresh_run()

    # Act
    catalog.gate.set()
    views = await asyncio.gather(*waiting)

    # Assert
    assert catalog.calls == 1
    assert {len(view.cases) for view in views} == {6}


async def test_the_stale_copy_is_served_at_once_while_one_refresh_runs(
    catalog: FakeCatalog,
) -> None:
    # Arrange
    clock = FakeClock()
    service = _service(catalog=catalog, clock=clock)
    await service.cases()
    catalog.gate.clear()
    clock.now += TTL_SECONDS + 1

    # Act
    views = [await service.cases() for _ in range(3)]
    await _let_the_refresh_run()
    calls_during_refresh = catalog.calls
    catalog.gate.set()
    await _let_the_refresh_run()

    # Assert
    assert {len(view.cases) for view in views} == {6}
    assert calls_during_refresh == 2
    assert catalog.calls == 2


async def test_an_outage_with_no_copy_is_raised(catalog: FakeCatalog) -> None:
    # Arrange
    catalog.down = True
    service = _service(catalog=catalog, clock=FakeClock())

    # Act / Assert
    with pytest.raises(CasesUnavailableError):
        await service.cases()


async def test_the_list_holds_summaries_in_the_gateway_order(catalog: FakeCatalog) -> None:
    # Arrange
    service = _service(catalog=catalog, clock=FakeClock())

    # Act
    view = await service.cases()

    # Assert
    assert [case.id for case in view.cases] == [
        "chokwe",
        "qadirabad",
        "richmond",
        "kumamoto",
        "choco",
        "san-marcos",
    ]
    assert set(view.model_dump(by_alias=True)["cases"][0]) == {
        "id",
        "title",
        "point",
        "status",
        "baselineDates",
        "assessmentDates",
    }


async def test_a_case_points_its_layers_at_the_api_and_redirects_to_the_gateway(
    catalog: FakeCatalog,
) -> None:
    # Arrange
    service = _service(catalog=catalog, clock=FakeClock())

    # Act
    case = await service.get(case_id="qadirabad")
    target = await service.layer_url(case_id="qadirabad", layer_id="change_db_hh")
    view_target = await service.layer_url(
        case_id="qadirabad", layer_id="view_polarization_rgb_hh_hv"
    )

    # Assert
    assert case.layers[0].url == f"{LAYER_PATH}/change_db_hh"
    assert case.visualizations[0].url == f"{LAYER_PATH}/view_polarization_rgb_hh_hv"
    assert target == f"{BASE_URL}/v2/cases/qadirabad/layers/change_db_hh.png"
    assert view_target.endswith("/view_polarization_rgb_hh_hv.png")


async def test_an_unknown_case_or_layer_is_not_found(catalog: FakeCatalog) -> None:
    # Arrange
    service = _service(catalog=catalog, clock=FakeClock())

    # Act / Assert
    with pytest.raises(CaseNotFoundError):
        await service.get(case_id="nope")
    with pytest.raises(CaseLayerNotFoundError):
        await service.layer_url(case_id="qadirabad", layer_id="nope")
