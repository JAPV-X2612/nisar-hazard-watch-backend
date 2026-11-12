from collections import defaultdict
from datetime import timedelta
from statistics import mean

from nisar_hazard_watch.constants.sar import (
    CONFIGURATION_RANK,
    FREQUENCY_A_MODE_LENGTH,
    FULL_COVERAGE,
    MATURITY_RANK,
    Direction,
)
from nisar_hazard_watch.models.scene import Scene, SceneGroup

GroupKey = tuple[int, str, int]


def _group_key(scene: Scene) -> GroupKey:
    return scene.track, scene.direction.value, scene.frame


def dedupe_scenes(scenes: list[Scene]) -> list[Scene]:
    """One scene per acquisition: best maturity, then configuration, then CRID and version."""
    best: dict[tuple, Scene] = {}
    for scene in scenes:
        key = (scene.cycle, *_group_key(scene=scene), scene.acquired_at)
        current = best.get(key)
        if current is None or _rank(scene=scene) > _rank(scene=current):
            best[key] = scene
    return sorted(best.values(), key=lambda scene: (scene.acquired_at, _group_key(scene=scene)))


def _rank(scene: Scene) -> tuple:
    return (
        MATURITY_RANK[scene.maturity],
        CONFIGURATION_RANK[scene.configuration],
        scene.crid,
        scene.version,
    )


def choose_group(scenes: list[Scene]) -> SceneGroup | None:
    """Group by (track, direction, frame): full coverage, then dual-pol, dates, newest, numbers."""
    groups: dict[GroupKey, list[Scene]] = defaultdict(list)
    for scene in scenes:
        groups[_group_key(scene=scene)].append(scene)
    if not groups:
        return None
    best_key = max(groups, key=lambda key: _group_score(key=key, members=groups[key]))
    track, direction, frame = best_key
    return SceneGroup(track=track, direction=Direction(direction), frame=frame)


def _group_score(key: GroupKey, members: list[Scene]) -> tuple:
    track, direction, frame = key
    coverage = mean(scene.coverage for scene in members)
    full = coverage >= FULL_COVERAGE
    newest = max(members, key=lambda scene: scene.acquired_at)
    family = newest.mode[:FREQUENCY_A_MODE_LENGTH]
    return (
        full,
        0.0 if full else coverage,
        any(len(scene.polarizations) >= 2 for scene in members),
        len({s.acquired_at for s in members if s.mode[:FREQUENCY_A_MODE_LENGTH] == family}),
        max(scene.acquired_at for scene in members),
        -track,
        -ord(direction),
        -frame,
    )


def select_dates(
    scenes: list[Scene], max_images: int, spacing_days: int, tolerance_days: int
) -> list[Scene]:
    """The newest scene plus those nearest to target minus spacing times k, within a tolerance."""
    if not scenes:
        return []
    ordered = sorted(scenes, key=lambda scene: scene.acquired_at)
    target = ordered[-1]
    family = target.mode[:FREQUENCY_A_MODE_LENGTH]
    pool = [scene for scene in ordered[:-1] if scene.mode[:FREQUENCY_A_MODE_LENGTH] == family]
    tolerance = timedelta(days=tolerance_days)
    selected = [target]
    for step in range(1, max_images):
        wanted = target.acquired_at - timedelta(days=spacing_days * step)
        candidates = [
            scene
            for scene in pool
            if scene not in selected and abs(scene.acquired_at - wanted) <= tolerance
        ]
        if candidates:
            selected.append(
                min(
                    candidates,
                    key=lambda scene: (abs(scene.acquired_at - wanted), scene.acquired_at),
                )
            )
    return sorted(selected, key=lambda scene: scene.acquired_at)
