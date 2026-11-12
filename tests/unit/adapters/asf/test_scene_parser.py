from datetime import UTC, datetime

import pytest

from nisar_hazard_watch.adapters.asf.scene_parser import parse_scene_identity
from nisar_hazard_watch.constants.sar import Configuration, Direction, Maturity

PROVISIONAL_NAME = (
    "NISAR_L2_PR_GCOV_033_063_A_070_2005_DHDH_A_20261010T020000_20261010T020035_P05023_N_F_J_001"
)
PROVISIONAL_URL = (
    "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/"
    f"{PROVISIONAL_NAME}/{PROVISIONAL_NAME}.h5"
)
VALIDATED_NAME = (
    "NISAR_L2_PR_GCOV_034_135_D_072_2005_DHDH_M_20261102T134701_20261102T134735_P05036_N_F_J_001"
)
VALIDATED_URL = (
    "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_V1/"
    f"{VALIDATED_NAME}/{VALIDATED_NAME}.h5"
)
URGENT_NAME = (
    "NISAR_L2_UR_GCOV_035_084_A_018_4005_QPDH_A_20261111T002203_20261111T002238_P05036_F_F_J_001"
)
URGENT_URL = (
    "https://nisar.asf.earthdatacloud.nasa.gov/NISAR-UR/UR_L2_L_GCOV/"
    f"{URGENT_NAME}/{URGENT_NAME}.h5"
)


def test_a_provisional_product_is_parsed_from_its_name_and_url() -> None:
    # Arrange
    name, url = PROVISIONAL_NAME, PROVISIONAL_URL

    # Act
    scene = parse_scene_identity(scene_name=name, url=url)

    # Assert
    assert scene is not None
    assert scene.granule_id == name
    assert scene.acquired_at == datetime(2026, 10, 10, 2, 0, 0, tzinfo=UTC)
    assert (scene.cycle, scene.track, scene.frame) == (33, 63, 70)
    assert scene.direction is Direction.ASCENDING
    assert (scene.code, scene.mode) == ("2005", "DHDH")
    assert scene.polarizations == ["HH", "HV"]
    assert scene.configuration is Configuration.PRODUCTION
    assert scene.maturity is Maturity.PROVISIONAL
    assert (scene.crid, scene.version) == ("P05023", 1)


def test_the_validated_collection_is_recognised_from_the_url() -> None:
    # Arrange
    name, url = VALIDATED_NAME, VALIDATED_URL

    # Act
    scene = parse_scene_identity(scene_name=name, url=url)

    # Assert
    assert scene is not None
    assert scene.maturity is Maturity.VALIDATED
    assert scene.direction is Direction.DESCENDING


def test_an_urgent_response_product_is_unvalidated_and_quad_pol_is_expanded() -> None:
    # Arrange
    name, url = URGENT_NAME, URGENT_URL

    # Act
    scene = parse_scene_identity(scene_name=name, url=url)

    # Assert
    assert scene is not None
    assert scene.configuration is Configuration.URGENT_RESPONSE
    assert scene.maturity is Maturity.UNVALIDATED
    assert scene.polarizations == ["HH", "HV", "VH", "VV"]


@pytest.mark.parametrize(
    argnames="name",
    argvalues=["", "not-a-nisar-name", "NISAR_L1_PR_RSLC_033_063_A_070_2005_DHDH_A_x"],
)
def test_names_that_are_not_gcov_products_are_skipped(name: str) -> None:
    # Arrange
    url = PROVISIONAL_URL

    # Act
    scene = parse_scene_identity(scene_name=name, url=url)

    # Assert
    assert scene is None


def test_an_unknown_collection_segment_is_skipped_instead_of_guessed() -> None:
    # Arrange
    url = "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/SOMETHING_NEW/x/y.h5"

    # Act
    scene = parse_scene_identity(scene_name=PROVISIONAL_NAME, url=url)

    # Assert
    assert scene is None


def test_crids_other_than_p_and_x_are_accepted() -> None:
    # Arrange
    name = PROVISIONAL_NAME.replace("P05023", "Q12345")

    # Act
    scene = parse_scene_identity(scene_name=name, url=PROVISIONAL_URL)

    # Assert
    assert scene is not None
    assert scene.crid == "Q12345"
