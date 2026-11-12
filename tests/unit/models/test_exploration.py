import pytest
from pydantic import ValidationError

from nisar_hazard_watch.constants.explorations import Lens
from nisar_hazard_watch.models.exploration import ExplorationRequest

POINT = {"type": "Point", "coordinates": [130.65, 32.65]}
PAIR = (
    "NISAR_L2_PR_GUNW_026_024_A_018_028_4000_SH_20260721T202900_20260721T202934_"
    "20260814T202858_20260814T202933_P05023_N_F_J_001"
)
DEFAULT_THRESHOLD = 0.35


def test_an_insar_request_defaults_the_coherence_threshold() -> None:
    # Arrange
    body = {"lens": "insar", "geometry": POINT, "pairId": PAIR}

    # Act
    request = ExplorationRequest.model_validate(body)

    # Assert
    assert request.lens is Lens.INSAR
    assert request.pair_id == PAIR
    assert request.coherence_threshold == DEFAULT_THRESHOLD


def test_an_insar_request_keeps_the_threshold_it_was_given() -> None:
    # Arrange
    body = {"lens": "insar", "geometry": POINT, "pairId": PAIR, "coherenceThreshold": 0.6}

    # Act
    request = ExplorationRequest.model_validate(body)

    # Assert
    assert request.coherence_threshold == 0.6


@pytest.mark.parametrize(
    argnames="body",
    argvalues=[
        {"lens": "insar", "geometry": POINT},
        {"lens": "insar", "geometry": POINT, "pairId": "not-a-gunw-name"},
        {"lens": "insar", "geometry": POINT, "pairId": PAIR, "coherenceThreshold": 0.05},
        {"lens": "insar", "geometry": POINT, "pairId": PAIR, "coherenceThreshold": 0.95},
        {"lens": "wildfire", "geometry": POINT, "pairId": PAIR},
        {"lens": "flood_wetland", "geometry": POINT, "coherenceThreshold": 0.4},
    ],
    ids=[
        "no pair",
        "not a GUNW name",
        "threshold too low",
        "threshold too high",
        "pair on another lens",
        "threshold on another lens",
    ],
)
def test_a_pair_belongs_to_the_insar_lens_and_stays_inside_its_limits(body: dict) -> None:
    # Arrange
    payload = body

    # Act / Assert
    with pytest.raises(expected_exception=ValidationError):
        ExplorationRequest.model_validate(payload)


def test_other_lenses_need_no_pair() -> None:
    # Arrange
    body = {"lens": "wildfire", "geometry": POINT}

    # Act
    request = ExplorationRequest.model_validate(body)

    # Assert
    assert request.pair_id is None
    assert request.coherence_threshold is None
