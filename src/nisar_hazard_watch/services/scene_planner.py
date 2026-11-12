from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from statistics import mean

from nisar_hazard_watch.constants.sar import (
    FULL_COVERAGE,
    MAX_IMAGES,
    MIN_IMAGES,
    SPACING_DAYS,
    SPACING_TOLERANCE_DAYS,
    WINDOW_DAYS,
    PlanStatus,
)
from nisar_hazard_watch.models.geometry import Aoi
from nisar_hazard_watch.models.scene import Scene, ScenePlan
from nisar_hazard_watch.ports.sar_catalog import SarCatalog
from nisar_hazard_watch.services.scene_selection import choose_group, dedupe_scenes, select_dates


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ScenePlanner:
    """From an area and "now" to the exact scenes to read: one group, up to five dates."""

    def __init__(
        self,
        catalog: SarCatalog,
        clock: Callable[[], datetime] = _utc_now,
        window_days: int = WINDOW_DAYS,
        max_images: int = MAX_IMAGES,
        min_images: int = MIN_IMAGES,
        spacing_days: int = SPACING_DAYS,
        tolerance_days: int = SPACING_TOLERANCE_DAYS,
    ) -> None:
        self._catalog = catalog
        self._clock = clock
        self._window_days = window_days
        self._max_images = max_images
        self._min_images = min_images
        self._spacing_days = spacing_days
        self._tolerance_days = tolerance_days

    async def plan(self, aoi: Aoi) -> ScenePlan:
        end = self._clock()
        start = end - timedelta(days=self._window_days)
        scenes = dedupe_scenes(scenes=await self._catalog.search(aoi=aoi, start=start, end=end))
        group = choose_group(scenes=scenes)
        if group is None:
            return ScenePlan(
                status=PlanStatus.NO_COVERAGE,
                aoi=aoi,
                window_start=start,
                window_end=end,
                notes=["no NISAR L-band GCOV scene covers this area in the last five months"],
            )
        members = [
            scene
            for scene in scenes
            if (scene.track, scene.direction, scene.frame)
            == (group.track, group.direction, group.frame)
        ]
        selected = select_dates(
            scenes=members,
            max_images=self._max_images,
            spacing_days=self._spacing_days,
            tolerance_days=self._tolerance_days,
        )
        return ScenePlan(
            status=self._status(selected=selected),
            aoi=aoi,
            window_start=start,
            window_end=end,
            group=group,
            scenes=selected,
            maturity_mixed=len({scene.maturity for scene in selected}) > 1,
            notes=self._notes(selected=selected),
        )

    def _status(self, selected: list[Scene]) -> PlanStatus:
        if len(selected) >= self._min_images:
            return PlanStatus.READY
        return PlanStatus.INSUFFICIENT_HISTORY

    def _notes(self, selected: list[Scene]) -> list[str]:
        notes: list[str] = []
        if len(selected) < self._min_images:
            dates = ", ".join(f"{scene.acquired_at:%Y-%m-%d}" for scene in selected)
            notes.append(
                f"only {len(selected)} usable dates found ({dates}); "
                f"at least {self._min_images} are needed"
            )
        coverage = mean(scene.coverage for scene in selected)
        if coverage < FULL_COVERAGE:
            notes.append(f"the scenes cover about {coverage:.0%} of the area")
        return notes
