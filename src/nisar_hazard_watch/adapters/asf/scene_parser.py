import logging
from datetime import UTC, datetime

from nisar_hazard_watch.constants.sar import (
    FREQUENCY_A_MODE_LENGTH,
    MATURITY_BY_COLLECTION,
    POLARIZATIONS_BY_MODE,
    SCENE_NAME_PATTERN,
    SCENE_TIME_FORMAT,
    Configuration,
    Direction,
    Maturity,
)
from nisar_hazard_watch.models.scene import SceneIdentity

logger = logging.getLogger(__name__)


def parse_scene_identity(scene_name: str, url: str) -> SceneIdentity | None:
    """Read an ASF NISAR GCOV product: the name carries the identity, the URL the maturity."""
    match = SCENE_NAME_PATTERN.match(scene_name)
    if match is None:
        logger.warning("skipping a product with an unrecognised name: %r", scene_name)
        return None
    maturity = _maturity_from_url(url=url)
    configuration = _configuration(code=match["configuration"])
    if maturity is None or configuration is None:
        logger.warning("skipping a product with an unknown collection or configuration: %r", url)
        return None
    mode = match["mode"]
    return SceneIdentity(
        granule_id=scene_name,
        acquired_at=datetime.strptime(match["start"], SCENE_TIME_FORMAT).replace(tzinfo=UTC),
        cycle=int(match["cycle"]),
        track=int(match["track"]),
        direction=Direction(match["direction"]),
        frame=int(match["frame"]),
        mode=mode,
        polarizations=list(POLARIZATIONS_BY_MODE.get(mode[:FREQUENCY_A_MODE_LENGTH], [])),
        maturity=maturity,
        configuration=configuration,
        crid=match["crid"],
        version=int(match["version"]),
        url=url,
    )


def _maturity_from_url(url: str) -> Maturity | None:
    for segment, maturity in MATURITY_BY_COLLECTION.items():
        if f"/{segment}/" in url:
            return maturity
    return None


def _configuration(code: str) -> Configuration | None:
    try:
        return Configuration(code)
    except ValueError:
        return None
