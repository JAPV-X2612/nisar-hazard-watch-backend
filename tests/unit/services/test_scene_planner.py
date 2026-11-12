import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from nisar_hazard_watch.adapters.asf.asf_catalog import AsfCatalog
from nisar_hazard_watch.constants.sar import WINDOW_DAYS, PlanStatus
from nisar_hazard_watch.exceptions.catalog_errors import CatalogUnavailableError
from nisar_hazard_watch.models.geometry import Aoi
from nisar_hazard_watch.models.scene import Scene
from nisar_hazard_watch.services.scene_planner import ScenePlanner
from tests.factories import make_scene, make_series, qadirabad_aoi

FIXTURE = Path(__file__).parents[2] / "fixtures" / "asf_qadirabad.json"
NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
MAX_IMAGES = 5


class FakeCatalog:
    def __init__(self, scenes: list[Scene]) -> None:
        self._scenes = scenes
        self.calls: list[tuple[Aoi, datetime, datetime]] = []

    async def search(self, aoi: Aoi, start: datetime, end: datetime) -> list[Scene]:
        self.calls.append((aoi, start, end))
        return self._scenes


class BrokenCatalog:
    async def search(self, aoi: Aoi, start: datetime, end: datetime) -> list[Scene]:
        raise CatalogUnavailableError("down")


def _planner(catalog: object) -> ScenePlanner:
    return ScenePlanner(catalog=catalog, clock=lambda: NOW)  # type: ignore[arg-type]


async def test_qadirabad_is_planned_from_the_real_catalog_into_one_group_of_five_dates() -> None:
    # Arrange
    body = json.loads(FIXTURE.read_text())
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code=200, json=body))

    # Act
    async with httpx.AsyncClient(transport=transport) as client:
        plan = await _planner(catalog=AsfCatalog(client=client)).plan(aoi=qadirabad_aoi())

    # Assert
    dates = [scene.acquired_at for scene in plan.scenes]
    assert plan.status is PlanStatus.READY
    assert plan.group is not None
    assert (plan.group.track, plan.group.frame) == (84, 18)
    assert len(plan.scenes) == MAX_IMAGES
    assert dates == sorted(dates)
    assert dates[-1].date().isoformat() == "2026-11-11"
    assert all(scene.track == 84 and scene.frame == 18 for scene in plan.scenes)
    assert plan.maturity_mixed is True
    assert len({scene.acquired_at for scene in plan.scenes}) == len(plan.scenes)


async def test_the_window_is_the_last_five_months_ending_now() -> None:
    # Arrange
    catalog = FakeCatalog(scenes=make_series(count=12))

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi())

    # Assert
    _, start, end = catalog.calls[0]
    assert end == NOW
    assert start == NOW - timedelta(days=WINDOW_DAYS)
    assert (plan.window_start, plan.window_end) == (start, end)


async def test_a_clean_series_is_ready_and_not_flagged_as_mixed() -> None:
    # Arrange
    catalog = FakeCatalog(scenes=make_series(count=12))

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi())

    # Assert
    assert plan.status is PlanStatus.READY
    assert plan.maturity_mixed is False
    assert plan.notes == []


async def test_fewer_than_four_usable_dates_is_an_insufficient_history_plan_not_an_error() -> None:
    # Arrange
    newest = make_series(count=1)[0].acquired_at
    scenes = [make_scene(acquired_at=newest - timedelta(days=30 * step)) for step in range(3)]
    catalog = FakeCatalog(scenes=scenes)

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi())

    # Assert
    assert plan.status is PlanStatus.INSUFFICIENT_HISTORY
    assert len(plan.scenes) == 3
    assert any("3 usable" in note for note in plan.notes)


async def test_an_empty_catalog_is_a_no_coverage_plan() -> None:
    # Arrange
    catalog = FakeCatalog(scenes=[])

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi())

    # Assert
    assert plan.status is PlanStatus.NO_COVERAGE
    assert plan.scenes == []
    assert plan.group is None


async def test_a_group_that_only_partly_covers_the_aoi_is_planned_with_a_note() -> None:
    # Arrange
    catalog = FakeCatalog(scenes=make_series(count=12, coverage=0.6))

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi())

    # Assert
    assert plan.status is PlanStatus.READY
    assert any("60%" in note for note in plan.notes)


async def test_duplicate_acquisitions_never_reach_the_plan() -> None:
    # Arrange
    series = make_series(count=12)
    duplicates = [make_scene(acquired_at=series[-1].acquired_at, crid="P00001")]
    catalog = FakeCatalog(scenes=[*series, *duplicates])

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi())

    # Assert
    times = [scene.acquired_at for scene in plan.scenes]
    assert len(times) == len(set(times))


async def test_catalog_failures_propagate_as_their_own_error() -> None:
    # Arrange
    planner = _planner(catalog=BrokenCatalog())

    # Act / Assert
    with pytest.raises(expected_exception=CatalogUnavailableError):
        await planner.plan(aoi=qadirabad_aoi())
