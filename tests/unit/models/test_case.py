import json
from pathlib import Path

import pytest

from nisar_hazard_watch.models.case import CaseEvidence
from tests.honesty import forbidden_keys

FIXTURE = Path(__file__).parents[2] / "fixtures" / "ml_gateway_cases.json"
CASES = json.loads(FIXTURE.read_text())
DROPPED = {
    "threshold_cell_area_ha",
    "area_semantics",
    "flood_probability",
    "flood_depth_m",
    "causal_attribution",
    "los_displacement_cm",
}


@pytest.mark.parametrize(argnames="case", argvalues=CASES, ids=[case["id"] for case in CASES])
def test_the_evidence_keeps_none_of_the_unvalidated_top_level_fields(case: dict) -> None:
    # Arrange
    raw = case["evidence"]

    # Act
    dumped = CaseEvidence.model_validate(raw).model_dump(mode="json")

    # Assert
    assert not set(dumped) & {"thresholdCellAreaHa", "floodProbability", "floodDepthM"}
    assert not [key for key in forbidden_keys(dumped) if key.count(".") == 1]
    assert DROPPED & set(raw)  # the raw answer does hold them


def test_the_word_check_flags_hectares_but_not_shape_or_phase() -> None:
    # Arrange
    payload = {"shape": 1, "sha256": 2, "commonPhaseSupport": 3, "areaHa": 4, "x": {"depth_m": 5}}

    # Act
    found = forbidden_keys(payload)

    # Assert
    assert found == [".areaHa", ".x.depth_m"]


def test_the_test_list_flags_nested_unit_and_plural_keys_the_old_list_missed() -> None:
    # Arrange
    payload = {
        "losDisplacementMm": 1,
        "flooded_area_km2": 2,
        "x": {"floodProbabilities": [0.1], "inundatedFraction": 0.2, "causedBy": "rain"},
        "calibratedFloodClassifier": False,
    }

    # Act
    found = forbidden_keys(payload)

    # Assert
    assert found == [
        ".losDisplacementMm",
        ".flooded_area_km2",
        ".x.floodProbabilities",
        ".x.inundatedFraction",
        ".x.causedBy",
    ]
