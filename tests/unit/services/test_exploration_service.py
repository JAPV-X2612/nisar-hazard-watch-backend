from collections.abc import Callable
from datetime import timedelta

import pytest

from nisar_hazard_watch.adapters.cases.static_precomputed_cases import StaticPrecomputedCases
from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.constants.explorations import (
    CacheState,
    ExplorationStatus,
    Lens,
    RunnerState,
    SourceBand,
    Stage,
    StageName,
)
from nisar_hazard_watch.constants.sar import PlanStatus
from nisar_hazard_watch.exceptions.catalog_errors import CatalogUnavailableError
from nisar_hazard_watch.exceptions.exploration_errors import (
    ExplorationNotFoundError,
    QueueFullError,
    RunnerUnavailableError,
    SourceNotAvailableError,
)
from nisar_hazard_watch.exceptions.geometry_errors import InvalidGeometryError
from nisar_hazard_watch.models.exploration import ExplorationRequest
from nisar_hazard_watch.ports.analysis_runner import RunnerLayer, RunnerTicket
from nisar_hazard_watch.ports.precomputed_cases import PrecomputedCase
from nisar_hazard_watch.services.exploration_service import ExplorationService
from tests.factories import QADIRABAD_LAT, QADIRABAD_LON, make_job, make_plan
from tests.unit.services.conftest import (
    DEADLINE_SECONDS,
    FakePlanner,
    ManualClock,
    ScriptedRunner,
    runner_result,
)

POINT = {"type": "Point", "coordinates": [QADIRABAD_LON, QADIRABAD_LAT]}
SMALL_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [[73.70, 32.30], [73.75, 32.30], [73.75, 32.34], [73.70, 32.34], [73.70, 32.30]]
    ],
}
Factory = Callable[..., ExplorationService]


def _request(**overrides: object) -> ExplorationRequest:
    values: dict[str, object] = {"lens": Lens.FLOOD_WETLAND, "geometry": POINT, **overrides}
    return ExplorationRequest(**values)  # type: ignore[arg-type]


def _succeeded(runner: ScriptedRunner, **overrides: object) -> None:
    runner.poll_ticket = RunnerTicket(
        run_id="run-1", state=RunnerState.SUCCEEDED, result=runner_result(**overrides)
    )


async def test_a_new_exploration_starts_with_a_plan_an_eta_and_nothing_final(
    make_service: Factory, runner: ScriptedRunner
) -> None:
    # Arrange
    service = make_service()

    # Act
    view, final = await service.create(request=_request())

    # Assert
    assert final is False
    assert view.id.startswith("exp_")
    assert view.status is ExplorationStatus.RUNNING
    assert view.stage is Stage.PROCESSING
    assert view.cache is CacheState.MISS
    assert view.eta_seconds == 60.0
    assert view.eta_remaining_seconds == 60.0
    assert view.plan is not None
    assert view.plan.status is PlanStatus.READY
    assert view.plan.series_key == "084_A_018_4005_DHDH"
    assert len(view.plan.dates) == 5
    assert [stage.name for stage in view.stages] == [StageName.PLANNING, StageName.PROCESSING]
    assert view.progress is not None
    assert (view.progress.scenes_read, view.progress.scenes_total) == (None, 5)
    assert len(runner.submissions) == 1


async def test_the_remaining_time_counts_down_with_the_clock(
    make_service: Factory, clock: ManualClock
) -> None:
    # Arrange
    service = make_service()
    view, _ = await service.create(request=_request())

    # Act
    clock.advance(20)
    later = await service.get(exploration_id=view.id)

    # Assert
    assert later.elapsed_seconds == 20.0
    assert later.eta_remaining_seconds == 40.0


async def test_a_finished_run_returns_the_result_with_honest_labels_and_our_layer_urls(
    make_service: Factory, runner: ScriptedRunner, clock: ManualClock
) -> None:
    # Arrange
    service = make_service()
    view, _ = await service.create(request=_request())
    layer = RunnerLayer(
        id="display_x",
        title="x",
        kind="observed",
        units="dB",
        colormap="gray",
        bounds=(1.0, 2.0, 3.0, 4.0),
        url="https://gateway.example/layer.png",
    )
    _succeeded(runner, layers=[layer])
    clock.advance(30)

    # Act
    done = await service.get(exploration_id=view.id)

    # Assert
    assert done.status is ExplorationStatus.SUCCEEDED
    assert done.stage is Stage.DONE
    assert done.elapsed_seconds == 30.0
    result = done.result
    assert result is not None
    assert result.is_demo is False
    assert result.scientific_status == "diagnostic"
    assert any("not a validated classifier" in text for text in result.limitations)
    assert len(result.scenes) == 5
    assert not hasattr(result.scenes[0], "url")
    assert result.layers[0].url == f"/api/v1/explorations/{view.id}/layers/display_x"
    assert result.quality["maturityMixed"] is False
    assert result.quality["windowTruncated"] is False
    assert [stage.name for stage in done.stages] == [
        StageName.PLANNING,
        StageName.READING,
        StageName.ANALYSING,
        StageName.RENDERING,
    ]
    assert done.progress is not None
    assert done.progress.scenes_read == 5


async def test_the_layer_redirect_target_is_the_runners_url(
    make_service: Factory, runner: ScriptedRunner
) -> None:
    # Arrange
    service = make_service()
    view, _ = await service.create(request=_request())
    layer = RunnerLayer(
        id="display_x",
        title="x",
        kind="observed",
        units="dB",
        colormap="gray",
        bounds=(1.0, 2.0, 3.0, 4.0),
        url="https://gateway.example/layer.png",
    )
    _succeeded(runner, layers=[layer])
    await service.get(exploration_id=view.id)

    # Act
    url = await service.layer_url(exploration_id=view.id, layer_id="display_x")

    # Assert
    assert url == "https://gateway.example/layer.png"
    with pytest.raises(expected_exception=ExplorationNotFoundError):
        await service.layer_url(exploration_id=view.id, layer_id="unknown")


async def test_the_same_request_is_answered_from_the_cache_without_running_again(
    make_service: Factory, runner: ScriptedRunner, clock: ManualClock
) -> None:
    # Arrange
    service = make_service()
    first, _ = await service.create(request=_request())
    _succeeded(runner)
    clock.advance(30)
    await service.get(exploration_id=first.id)

    # Act
    second, final = await service.create(request=_request())

    # Assert
    assert final is True
    assert second.cache is CacheState.HIT
    assert second.id == first.id
    assert second.status is ExplorationStatus.SUCCEEDED
    assert len(runner.submissions) == 1


async def test_a_stale_cache_entry_runs_again(
    make_service: Factory, runner: ScriptedRunner, clock: ManualClock
) -> None:
    # Arrange
    service = make_service()
    first, _ = await service.create(request=_request())
    _succeeded(runner)
    await service.get(exploration_id=first.id)
    clock.advance(86400 + 60)

    # Act
    second, final = await service.create(request=_request())

    # Assert
    assert second.id != first.id
    assert final is False
    assert len(runner.submissions) == 2


async def test_other_lenses_and_areas_never_share_a_cache_entry(
    make_service: Factory, runner: ScriptedRunner
) -> None:
    # Arrange
    service = make_service()
    first, _ = await service.create(request=_request())
    _succeeded(runner)
    await service.get(exploration_id=first.id)

    # Act
    other_lens, _ = await service.create(request=_request(lens=Lens.WILDFIRE))
    other_area, _ = await service.create(request=_request(geometry=SMALL_POLYGON))

    # Assert
    assert len({first.id, other_lens.id, other_area.id}) == 3


async def test_a_full_queue_is_refused_with_its_depth_and_stores_nothing(
    make_service: Factory, runner: ScriptedRunner
) -> None:
    # Arrange
    service = make_service(max_active=1)
    await service.create(request=_request())

    # Act / Assert
    with pytest.raises(expected_exception=QueueFullError, match="queue depth 1"):
        await service.create(request=_request(lens=Lens.AGRICULTURE))
    assert len(runner.submissions) == 1


async def test_the_s_band_is_refused_before_anything_is_planned(
    make_service: Factory, planner: FakePlanner
) -> None:
    # Arrange
    service = make_service()

    # Act / Assert
    with pytest.raises(expected_exception=SourceNotAvailableError, match="precomputed"):
        await service.create(request=_request(source=SourceBand.S_BAND))
    assert planner.calls == 0


@pytest.mark.parametrize(
    argnames=("status", "reason"),
    argvalues=[
        (PlanStatus.NO_COVERAGE, ReasonCode.NO_COVERAGE),
        (PlanStatus.INSUFFICIENT_HISTORY, ReasonCode.INSUFFICIENT_HISTORY),
    ],
)
async def test_an_unrunnable_plan_is_a_final_no_data_answer_with_its_reason(
    make_service: Factory,
    planner: FakePlanner,
    runner: ScriptedRunner,
    status: PlanStatus,
    reason: ReasonCode,
) -> None:
    # Arrange
    planner.plan_result = make_plan(count=2, status=status, notes=["explained here"])
    service = make_service()

    # Act
    view, final = await service.create(request=_request())

    # Assert
    assert final is True
    assert view.status is ExplorationStatus.NO_DATA
    assert view.stage is Stage.DONE
    assert view.error is not None
    assert view.error.reason_code is reason
    assert "explained here" in view.error.detail
    assert runner.submissions == []


async def test_a_catalog_failure_propagates_and_offers_a_precomputed_case_when_one_matches(
    make_service: Factory, planner: FakePlanner
) -> None:
    # Arrange
    planner.plan_result = CatalogUnavailableError("the ASF scene catalog did not answer")
    case = PrecomputedCase(
        id="qadirabad",
        title="Qadirabad floods",
        lens=Lens.FLOOD_WETLAND,
        longitude=QADIRABAD_LON,
        latitude=QADIRABAD_LAT,
        radius_km=5,
    )
    with_case = make_service(cases=StaticPrecomputedCases(cases=[case]))
    without_case = make_service()

    # Act / Assert
    with pytest.raises(expected_exception=CatalogUnavailableError, match="'qadirabad'"):
        await with_case.create(request=_request())
    with pytest.raises(expected_exception=CatalogUnavailableError) as error:
        await without_case.create(request=_request())
    assert "precomputed" not in error.value.detail


async def test_a_run_that_outlives_the_deadline_is_partial_with_its_reason(
    make_service: Factory, clock: ManualClock
) -> None:
    # Arrange
    service = make_service()
    view, _ = await service.create(request=_request())
    clock.advance(DEADLINE_SECONDS + 1)

    # Act
    late = await service.get(exploration_id=view.id)
    again = await service.get(exploration_id=view.id)

    # Assert
    assert late.status is ExplorationStatus.PARTIAL
    assert late.error is not None
    assert late.error.reason_code is ReasonCode.TIMEOUT_PARTIAL
    assert late.plan is not None
    assert len(late.plan.dates) == 5
    assert again.status is ExplorationStatus.PARTIAL


async def test_a_failed_run_reports_why_without_leaking_service_details(
    make_service: Factory, runner: ScriptedRunner
) -> None:
    # Arrange
    service = make_service()
    view, _ = await service.create(request=_request())
    runner.poll_ticket = RunnerTicket(
        run_id="run-1", state=RunnerState.FAILED, error_code="deadline_exceeded"
    )

    # Act
    failed = await service.get(exploration_id=view.id)

    # Assert
    assert failed.status is ExplorationStatus.FAILED
    assert failed.error is not None
    assert failed.error.reason_code is ReasonCode.ANALYSIS_FAILED
    assert failed.error.detail == "the analysis service ran out of time"


async def test_a_science_result_without_data_is_reported_as_no_data(
    make_service: Factory, runner: ScriptedRunner
) -> None:
    # Arrange
    service = make_service()
    view, _ = await service.create(request=_request())
    _succeeded(runner, science_status="no_data")

    # Act
    done = await service.get(exploration_id=view.id)

    # Assert
    assert done.status is ExplorationStatus.NO_DATA
    assert done.error is not None
    assert done.error.reason_code is ReasonCode.NO_COVERAGE


async def test_a_partial_science_result_stays_available(
    make_service: Factory, runner: ScriptedRunner
) -> None:
    # Arrange
    service = make_service()
    view, _ = await service.create(request=_request())
    _succeeded(runner, science_status="partial")

    # Act
    done = await service.get(exploration_id=view.id)

    # Assert
    assert done.status is ExplorationStatus.PARTIAL
    assert done.result is not None


async def test_a_polling_hiccup_keeps_the_last_known_state(
    make_service: Factory, runner: ScriptedRunner
) -> None:
    # Arrange
    service = make_service()
    view, _ = await service.create(request=_request())
    runner.poll_ticket = RunnerUnavailableError("down")

    # Act
    still = await service.get(exploration_id=view.id)

    # Assert
    assert still.status is ExplorationStatus.RUNNING


async def test_an_active_exploration_can_be_cancelled_and_a_finished_one_cannot(
    make_service: Factory, runner: ScriptedRunner
) -> None:
    # Arrange
    service = make_service()
    cancelled_view, _ = await service.create(request=_request())
    done_view, _ = await service.create(request=_request(lens=Lens.WILDFIRE))
    _succeeded(runner)
    await service.get(exploration_id=done_view.id)

    # Act
    cancelled = await service.cancel(exploration_id=cancelled_view.id)
    untouched = await service.cancel(exploration_id=done_view.id)

    # Assert
    assert cancelled.status is ExplorationStatus.CANCELLED
    assert cancelled.error is not None
    assert cancelled.error.reason_code is ReasonCode.CANCELLED
    assert untouched.status is ExplorationStatus.SUCCEEDED


async def test_unknown_explorations_are_not_found(make_service: Factory) -> None:
    # Arrange
    service = make_service()

    # Act / Assert
    for action in (service.get, service.cancel):
        with pytest.raises(expected_exception=ExplorationNotFoundError):
            await action(exploration_id="exp_0000000000000000")


@pytest.mark.parametrize(
    argnames="geometry",
    argvalues=[
        {"type": "Point", "coordinates": [1]},
        {"type": "Point", "coordinates": ["a", "b"]},
        {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
    ],
)
async def test_invalid_geometries_are_rejected_before_planning(
    make_service: Factory, planner: FakePlanner, geometry: dict
) -> None:
    # Arrange
    service = make_service()

    # Act / Assert
    with pytest.raises(expected_exception=InvalidGeometryError):
        await service.create(request=_request(geometry=geometry))
    assert planner.calls == 0


async def test_an_area_wider_than_the_window_carries_a_limitation(
    make_service: Factory, runner: ScriptedRunner
) -> None:
    # Arrange
    wide = {
        "type": "Polygon",
        "coordinates": [[[73.0, 32.0], [73.17, 32.0], [73.17, 32.17], [73.0, 32.17], [73.0, 32.0]]],
    }
    service = make_service()
    view, _ = await service.create(request=_request(geometry=wide))
    _succeeded(runner)

    # Act
    done = await service.get(exploration_id=view.id)

    # Assert
    assert done.result is not None
    assert done.result.quality["windowTruncated"] is True
    assert any("limited to about 10 km" in text for text in done.result.limitations)


async def test_the_eta_uses_the_p80_of_comparable_past_runs(
    make_service: Factory, repository, clock: ManualClock
) -> None:
    # Arrange
    created = clock() - timedelta(hours=1)
    for index, seconds in enumerate([20, 24, 30, 38, 90]):
        await repository.add(
            job=make_job(
                id=f"exp_{index:016d}",
                status=ExplorationStatus.SUCCEEDED,
                cache_key=f"{index:064d}",
                created_at=created,
                finished_at=created + timedelta(seconds=seconds),
            )
        )
    service = make_service()

    # Act
    view, _ = await service.create(request=_request())

    # Assert
    assert view.eta_seconds == 38.0


async def test_coverage_describes_the_plan_without_running_anything(
    make_service: Factory, runner: ScriptedRunner
) -> None:
    # Arrange
    service = make_service()

    # Act
    coverage = await service.coverage(geometry=POINT)

    # Assert
    assert coverage.plan.status is PlanStatus.READY
    assert coverage.plan.series_key == "084_A_018_4005_DHDH"
    assert coverage.area_km2 == pytest.approx(104.86, abs=0.5)
    assert coverage.precomputed_case is None
    assert runner.submissions == []
