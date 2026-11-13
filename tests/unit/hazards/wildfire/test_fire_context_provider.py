import asyncio
from datetime import UTC, date, datetime, timedelta

import pytest

from nisar_hazard_watch.constants.fire_context import (
    NOTE_DETECTIONS,
    NOTE_NO_ASSESSMENT_WINDOW,
    NOTE_NO_DETECTIONS,
    NOTE_NOT_CONFIGURED,
    NOTE_UNAVAILABLE,
    FireContextStatus,
)
from nisar_hazard_watch.exceptions.fire_data_errors import FireDataUnavailableError
from nisar_hazard_watch.hazards.wildfire.fire_context_provider import FirmsFireContextProvider
from nisar_hazard_watch.models.fire_detection import FireDetection
from nisar_hazard_watch.models.fire_search import FireSearch
from tests.factories import QADIRABAD_LAT, QADIRABAD_LON, SERIES_START, make_plan

TIMEOUT_SECONDS = 0.05
FAR_LONGITUDE = 74.5
TARGET = SERIES_START + timedelta(days=48)
BASELINE_END = SERIES_START + timedelta(days=36)
MIDDLE = BASELINE_END + timedelta(days=5)
PRODUCTS = ["VIIRS_NOAA20_SP", "VIIRS_SNPP_SP"]


def _detection(**overrides: object) -> FireDetection:
    values: dict[str, object] = {
        "latitude": QADIRABAD_LAT,
        "longitude": QADIRABAD_LON,
        "detected_at": MIDDLE,
        "satellite": "N20",
        "confidence": "nominal",
        "frp_mw": 3.0,
        **overrides,
    }
    return FireDetection(**values)  # type: ignore[arg-type]


class FakeSource:
    def __init__(
        self,
        detections: list[FireDetection] | None = None,
        failure: Exception | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self.detections = detections or []
        self.failure = failure
        self.delay_seconds = delay_seconds
        self.calls: list[tuple[tuple[float, float, float, float], date, date]] = []

    async def search(
        self, bbox: tuple[float, float, float, float], start: date, end: date
    ) -> FireSearch:
        self.calls.append((bbox, start, end))
        await asyncio.sleep(self.delay_seconds)
        if self.failure is not None:
            raise self.failure
        return FireSearch(detections=self.detections, products=PRODUCTS)


async def test_it_counts_the_confident_detections_inside_the_area_between_the_two_passes() -> None:
    # Arrange
    source = FakeSource(
        detections=[
            _detection(detected_at=MIDDLE, frp_mw=3.0, satellite="N20"),
            _detection(detected_at=MIDDLE + timedelta(days=2), frp_mw=9.5, satellite="N"),
            _detection(detected_at=TARGET, frp_mw=None),
            _detection(confidence="low"),
            _detection(longitude=FAR_LONGITUDE),
            _detection(detected_at=BASELINE_END),
            _detection(detected_at=TARGET + timedelta(hours=1)),
        ]
    )
    provider = FirmsFireContextProvider(source=source, timeout_seconds=TIMEOUT_SECONDS)

    # Act
    context = await provider.fire_context(plan=make_plan(count=5))

    # Assert
    assert context.status is FireContextStatus.AVAILABLE
    assert context.detections == 3
    assert context.low_confidence_excluded == 1
    assert context.first_detection == MIDDLE
    assert context.last_detection == TARGET
    assert context.peak_frp_mw == 9.5
    assert context.satellites == ["N", "N20"]
    assert context.products == PRODUCTS
    assert (context.window_start, context.window_end) == (BASELINE_END, TARGET)
    assert context.note == NOTE_DETECTIONS


async def test_no_detections_is_an_answer_that_does_not_rule_a_fire_out() -> None:
    # Arrange
    provider = FirmsFireContextProvider(source=FakeSource(), timeout_seconds=TIMEOUT_SECONDS)

    # Act
    context = await provider.fire_context(plan=make_plan(count=5))

    # Assert
    assert context.status is FireContextStatus.AVAILABLE
    assert context.detections == 0
    assert context.first_detection is None
    assert context.peak_frp_mw is None
    assert context.note == NOTE_NO_DETECTIONS


async def test_the_source_is_asked_for_the_dates_of_the_window_and_the_box_of_the_area() -> None:
    # Arrange
    source = FakeSource()
    plan = make_plan(count=5)
    provider = FirmsFireContextProvider(source=source, timeout_seconds=TIMEOUT_SECONDS)

    # Act
    await provider.fire_context(plan=plan)

    # Assert
    assert source.calls == [(plan.aoi.bbox, BASELINE_END.date(), TARGET.date())]


async def test_without_a_key_the_verdict_stays_radar_only_and_says_so() -> None:
    # Arrange
    provider = FirmsFireContextProvider(source=None, timeout_seconds=TIMEOUT_SECONDS)

    # Act
    context = await provider.fire_context(plan=make_plan(count=5))

    # Assert
    assert context.status is FireContextStatus.NOT_CONFIGURED
    assert context.detections is None
    assert context.note == NOTE_NOT_CONFIGURED
    assert (context.window_start, context.window_end) == (BASELINE_END, TARGET)


@pytest.mark.parametrize(
    argnames="source",
    argvalues=[
        FakeSource(failure=FireDataUnavailableError(reason="FIRMS answered 503")),
        FakeSource(delay_seconds=1.0),
    ],
    ids=["upstream error", "timeout"],
)
async def test_a_failing_or_slow_source_makes_the_context_unavailable_not_an_error(
    source: FakeSource,
) -> None:
    # Arrange
    provider = FirmsFireContextProvider(source=source, timeout_seconds=TIMEOUT_SECONDS)

    # Act
    context = await provider.fire_context(plan=make_plan(count=5))

    # Assert
    assert context.status is FireContextStatus.UNAVAILABLE
    assert context.detections is None
    assert context.note == NOTE_UNAVAILABLE


async def test_a_plan_with_one_pass_has_no_window_to_search() -> None:
    # Arrange
    source = FakeSource()
    provider = FirmsFireContextProvider(source=source, timeout_seconds=TIMEOUT_SECONDS)

    # Act
    context = await provider.fire_context(plan=make_plan(count=1))

    # Assert
    assert context.status is FireContextStatus.UNAVAILABLE
    assert context.note == NOTE_NO_ASSESSMENT_WINDOW
    assert source.calls == []


async def test_a_long_gap_between_passes_searches_only_the_last_forty_days_and_says_so() -> None:
    # Arrange
    source = FakeSource()
    plan = make_plan(count=2)
    later = plan.scenes[1].model_copy(update={"acquired_at": datetime(2026, 9, 20, 2, tzinfo=UTC)})
    plan = plan.model_copy(update={"scenes": [plan.scenes[0], later]})
    provider = FirmsFireContextProvider(source=source, timeout_seconds=TIMEOUT_SECONDS)

    # Act
    context = await provider.fire_context(plan=plan)

    # Assert
    assert source.calls[0][1:] == (date(2026, 8, 12), date(2026, 9, 20))
    assert context.window_start == datetime(2026, 8, 12, 2, tzinfo=UTC)
    assert context.note.endswith("Only the last 40 days before the target pass were searched.")
