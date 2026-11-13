from datetime import date

import pytest

from nisar_hazard_watch.exceptions.pair_errors import InvalidPairError
from nisar_hazard_watch.utils.gunw import pair_dates

KUMAMOTO_PAIR = (
    "NISAR_L2_PR_GUNW_026_024_A_018_028_4000_SH_20260721T202900_20260721T202934_"
    "20260814T202858_20260814T202933_P05023_N_F_J_001"
)


def test_the_two_acquisition_days_come_from_the_granule_name() -> None:
    # Arrange
    pair_id = KUMAMOTO_PAIR

    # Act
    reference, secondary = pair_dates(pair_id=pair_id)

    # Assert
    assert (reference, secondary) == (date(2026, 7, 21), date(2026, 8, 14))


@pytest.mark.parametrize(
    argnames="pair_id",
    argvalues=[
        "NISAR_L2_PR_GCOV_001_084_A_018_4005_DHDH_A_20260612T020000_20260612T020030_P05023",
        KUMAMOTO_PAIR.replace("20260721T202900_20260721T202934", "20261321T202900_20261321T202934"),
        KUMAMOTO_PAIR.replace("20260814T202858_20260814T202933", "20260701T202858_20260701T202933"),
    ],
    ids=["not a GUNW name", "impossible date", "secondary before reference"],
)
def test_a_name_that_is_not_a_usable_pair_is_refused(pair_id: str) -> None:
    # Arrange
    name = pair_id

    # Act / Assert
    with pytest.raises(expected_exception=InvalidPairError):
        pair_dates(pair_id=name)
