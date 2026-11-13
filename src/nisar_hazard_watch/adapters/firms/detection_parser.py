import csv
import io
from datetime import UTC, datetime

from nisar_hazard_watch.constants.fire_context import (
    COLUMN_CONFIDENCE,
    COLUMN_DATE,
    COLUMN_FRP,
    COLUMN_LATITUDE,
    COLUMN_LONGITUDE,
    COLUMN_SATELLITE,
    COLUMN_TIME,
    FIRMS_CSV_FIRST_COLUMN,
    FIRMS_DATETIME_FORMAT,
)
from nisar_hazard_watch.models.fire_detection import FireDetection


def is_detection_csv(text: str) -> bool:
    """FIRMS answers an error with a plain sentence, so a header line tells data from a refusal."""
    return text.lstrip().startswith(FIRMS_CSV_FIRST_COLUMN)


def parse_detections(text: str) -> list[FireDetection]:
    """Rows that cannot be read are skipped: one bad row must not hide the others."""
    detections: list[FireDetection] = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            detections.append(_detection(row=row))
        except (KeyError, TypeError, ValueError):
            continue
    return detections


def _detection(row: dict[str, str]) -> FireDetection:
    detected_at = datetime.strptime(
        f"{row[COLUMN_DATE]} {row[COLUMN_TIME]}", FIRMS_DATETIME_FORMAT
    ).replace(tzinfo=UTC)
    frp = row.get(COLUMN_FRP)
    return FireDetection(
        latitude=float(row[COLUMN_LATITUDE]),
        longitude=float(row[COLUMN_LONGITUDE]),
        detected_at=detected_at,
        satellite=row[COLUMN_SATELLITE],
        confidence=row[COLUMN_CONFIDENCE].strip().lower(),
        frp_mw=float(frp) if frp else None,
    )
