from datetime import UTC, datetime, timedelta

from nisar_hazard_watch.hazards.wildfire.assessment_window import assessment_window
from tests.factories import SERIES_START, make_plan, make_scene


def test_the_window_runs_from_the_last_baseline_pass_to_the_target_pass() -> None:
    # Arrange
    plan = make_plan(count=5)

    # Act
    window = assessment_window(plan=plan)

    # Assert
    assert window is not None
    assert window.start == SERIES_START + timedelta(days=36)
    assert window.end == SERIES_START + timedelta(days=48)


def test_scenes_of_the_same_pass_count_once() -> None:
    # Arrange
    twin = make_scene(
        acquired_at=SERIES_START + timedelta(days=12), granule_id="twin-of-the-second-pass"
    )
    plan = make_plan(count=2)
    plan = plan.model_copy(update={"scenes": [*plan.scenes, twin]})

    # Act
    window = assessment_window(plan=plan)

    # Assert
    assert window is not None
    assert window.start == SERIES_START
    assert window.end == datetime(2026, 6, 24, 2, 0, tzinfo=UTC)


def test_one_pass_alone_has_no_window() -> None:
    # Arrange
    plan = make_plan(count=1)

    # Act
    window = assessment_window(plan=plan)

    # Assert
    assert window is None
