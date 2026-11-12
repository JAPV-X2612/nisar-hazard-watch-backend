import asyncio
import logging
from datetime import timedelta

from shapely.geometry import Point, shape
from shapely.prepared import prep

from nisar_hazard_watch.constants.fire_context import (
    FIRMS_LOW_CONFIDENCE,
    FIRMS_MAX_WINDOW_DAYS,
    NOTE_DETECTIONS,
    NOTE_NO_ASSESSMENT_WINDOW,
    NOTE_NO_DETECTIONS,
    NOTE_NOT_CONFIGURED,
    NOTE_TRUNCATED_WINDOW,
    NOTE_UNAVAILABLE,
    FireContextStatus,
)
from nisar_hazard_watch.exceptions.fire_data_errors import FireDataUnavailableError
from nisar_hazard_watch.hazards.wildfire.assessment_window import (
    AssessmentWindow,
    assessment_window,
)
from nisar_hazard_watch.models.fire_context import FireContext
from nisar_hazard_watch.models.fire_detection import FireDetection
from nisar_hazard_watch.models.scene import ScenePlan
from nisar_hazard_watch.ports.fire_detection_source import FireDetectionSource

logger = logging.getLogger(__name__)


class FirmsFireContextProvider:
    """Counts the active-fire detections inside the area between the baseline and target passes."""

    def __init__(self, source: FireDetectionSource | None, timeout_seconds: float) -> None:
        self._source = source
        self._timeout_seconds = timeout_seconds

    async def fire_context(self, plan: ScenePlan) -> FireContext:
        window = assessment_window(plan=plan)
        if window is None:
            return FireContext(status=FireContextStatus.UNAVAILABLE, note=NOTE_NO_ASSESSMENT_WINDOW)
        if self._source is None:
            return FireContext(
                status=FireContextStatus.NOT_CONFIGURED,
                window_start=window.start,
                window_end=window.end,
                note=NOTE_NOT_CONFIGURED,
            )
        searched = self._clip(window=window)
        try:
            async with asyncio.timeout(self._timeout_seconds):
                search = await self._source.search(
                    bbox=plan.aoi.bbox, start=searched.start.date(), end=searched.end.date()
                )
        except FireDataUnavailableError as exc:
            logger.warning("fire context unavailable: %s", exc.reason)
            return self._unavailable(window=searched)
        except TimeoutError:
            logger.warning("fire context timed out after %s s", self._timeout_seconds)
            return self._unavailable(window=searched)
        inside = self._inside(detections=search.detections, plan=plan, window=searched)
        confident = [d for d in inside if d.confidence != FIRMS_LOW_CONFIDENCE]
        return self._summary(
            window=searched,
            truncated=searched.start != window.start,
            confident=confident,
            low_confidence_excluded=len(inside) - len(confident),
            products=search.products,
        )

    @staticmethod
    def _clip(window: AssessmentWindow) -> AssessmentWindow:
        earliest = window.end - timedelta(days=FIRMS_MAX_WINDOW_DAYS - 1)
        return AssessmentWindow(start=max(window.start, earliest), end=window.end)

    @staticmethod
    def _inside(
        detections: list[FireDetection], plan: ScenePlan, window: AssessmentWindow
    ) -> list[FireDetection]:
        area = prep(shape(plan.aoi.geometry))
        return [
            detection
            for detection in detections
            if window.start < detection.detected_at <= window.end
            and area.contains(Point(detection.longitude, detection.latitude))
        ]

    @staticmethod
    def _unavailable(window: AssessmentWindow) -> FireContext:
        return FireContext(
            status=FireContextStatus.UNAVAILABLE,
            window_start=window.start,
            window_end=window.end,
            note=NOTE_UNAVAILABLE,
        )

    @staticmethod
    def _summary(
        window: AssessmentWindow,
        truncated: bool,
        confident: list[FireDetection],
        low_confidence_excluded: int,
        products: list[str],
    ) -> FireContext:
        note = NOTE_DETECTIONS if confident else NOTE_NO_DETECTIONS
        if truncated:
            note += NOTE_TRUNCATED_WINDOW.format(days=FIRMS_MAX_WINDOW_DAYS)
        powers = [d.frp_mw for d in confident if d.frp_mw is not None]
        times = sorted(d.detected_at for d in confident)
        return FireContext(
            status=FireContextStatus.AVAILABLE,
            window_start=window.start,
            window_end=window.end,
            detections=len(confident),
            low_confidence_excluded=low_confidence_excluded,
            first_detection=times[0] if times else None,
            last_detection=times[-1] if times else None,
            peak_frp_mw=max(powers) if powers else None,
            satellites=sorted({d.satellite for d in confident}),
            products=products,
            note=note,
        )
