from datetime import UTC, datetime
from pathlib import Path

from nisar_hazard_watch.adapters.firms.detection_parser import is_detection_csv, parse_detections

FIXTURE = Path(__file__).parents[3] / "fixtures" / "firms_viirs_noaa20_area.csv"
HEADER = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,"
    "version,bright_ti5,frp,daynight"
)
ROW_COUNT = 13
FIRST_DETECTED_AT = datetime(2026, 11, 11, 0, 0, tzinfo=UTC)
FIRST_FRP_MW = 1.88
STRONGEST_FRP_MW = 520.64
REFUSAL = "Invalid MAP_KEY."


def test_every_real_row_becomes_a_detection_with_a_utc_time_and_lowercase_confidence() -> None:
    # Arrange
    text = FIXTURE.read_text()

    # Act
    detections = parse_detections(text=text)

    # Assert
    assert len(detections) == ROW_COUNT
    assert detections[0].detected_at == FIRST_DETECTED_AT
    assert detections[0].satellite == "N20"
    assert detections[0].confidence == "nominal"
    assert detections[0].frp_mw == FIRST_FRP_MW
    assert max(d.frp_mw or 0.0 for d in detections) == STRONGEST_FRP_MW


def test_a_header_line_tells_data_from_a_plain_sentence_refusal() -> None:
    # Arrange
    data = FIXTURE.read_text()

    # Act
    results = (is_detection_csv(text=data), is_detection_csv(text=REFUSAL))

    # Assert
    assert results == (True, False)


def test_a_header_without_rows_is_valid_data_with_no_detections() -> None:
    # Arrange
    text = HEADER + "\n"

    # Act
    detections = parse_detections(text=text)

    # Assert
    assert is_detection_csv(text=text) is True
    assert detections == []


def test_a_row_that_cannot_be_read_is_skipped_without_hiding_the_others() -> None:
    # Arrange
    broken = "x,11.6,298.4,0.5,0.6,2026-11-11,0000,N20,nominal,2.0NRT,277.8,1.9,N"
    good = "0.3,11.6,298.4,0.5,0.6,2026-11-11,0000,N20,nominal,2.0NRT,277.8,1.9,N"
    text = "\n".join([HEADER, broken, good]) + "\n"

    # Act
    detections = parse_detections(text=text)

    # Assert
    assert len(detections) == 1
    assert detections[0].latitude == 0.3


def test_a_missing_power_reading_stays_unknown_instead_of_zero() -> None:
    # Arrange
    row = "0.3,11.6,298.4,0.5,0.6,2026-11-11,0000,N20,nominal,2.0NRT,277.8,,N"
    text = "\n".join([HEADER, row]) + "\n"

    # Act
    detections = parse_detections(text=text)

    # Assert
    assert detections[0].frp_mw is None
