from datetime import UTC, datetime, timedelta
from typing import Any

from nisar_hazard_watch.constants.sar import Configuration, Direction, Maturity
from nisar_hazard_watch.models.geometry import Aoi
from nisar_hazard_watch.models.scene import Scene
from nisar_hazard_watch.utils.geometry import aoi_from_point

QADIRABAD_LON, QADIRABAD_LAT = 73.713, 32.329
REVISIT_DAYS = 12
SERIES_START = datetime(2026, 6, 12, 2, 0, tzinfo=UTC)
DEFAULT_GROUP = (84, Direction.ASCENDING, 18)


def qadirabad_aoi() -> Aoi:
    return aoi_from_point(lon=QADIRABAD_LON, lat=QADIRABAD_LAT)


def make_scene(**overrides: Any) -> Scene:
    track, direction, frame = DEFAULT_GROUP
    acquired_at = overrides.pop("acquired_at", SERIES_START)
    values: dict[str, Any] = {
        "granule_id": f"scene-{track}-{frame}-{acquired_at:%Y%m%dT%H%M%S}",
        "acquired_at": acquired_at,
        "cycle": 33,
        "track": track,
        "direction": direction,
        "frame": frame,
        "code": "4005",
        "mode": "DHDH",
        "polarizations": ["HH", "HV"],
        "maturity": Maturity.PROVISIONAL,
        "configuration": Configuration.PRODUCTION,
        "crid": "P05023",
        "version": 1,
        "url": "https://example.test/scene.h5",
        "coverage": 1.0,
        **overrides,
    }
    return Scene(**values)


def make_series(count: int, **overrides: Any) -> list[Scene]:
    return [
        make_scene(acquired_at=SERIES_START + timedelta(days=REVISIT_DAYS * index), **overrides)
        for index in range(count)
    ]
