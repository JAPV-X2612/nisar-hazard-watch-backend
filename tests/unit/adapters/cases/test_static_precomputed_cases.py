import json
from pathlib import Path

from nisar_hazard_watch.adapters.cases.static_precomputed_cases import StaticPrecomputedCases
from nisar_hazard_watch.constants.explorations import Lens
from nisar_hazard_watch.ports.precomputed_cases import PrecomputedCase

QADIRABAD = PrecomputedCase(
    id="qadirabad",
    title="Qadirabad floods",
    lens=Lens.FLOOD_WETLAND,
    longitude=73.713,
    latitude=32.329,
    radius_km=10.0,
)


def test_a_point_within_the_radius_finds_the_case() -> None:
    # Arrange
    cases = StaticPrecomputedCases(cases=[QADIRABAD])

    # Act
    found = cases.find(longitude=73.72, latitude=32.33, lens=Lens.FLOOD_WETLAND)

    # Assert
    assert found == QADIRABAD


def test_a_far_point_or_another_lens_finds_nothing() -> None:
    # Arrange
    cases = StaticPrecomputedCases(cases=[QADIRABAD])

    # Act
    far = cases.find(longitude=74.5, latitude=32.33, lens=Lens.FLOOD_WETLAND)
    other_lens = cases.find(longitude=73.72, latitude=32.33, lens=Lens.WILDFIRE)

    # Assert
    assert far is None
    assert other_lens is None


def test_the_nearest_case_wins() -> None:
    # Arrange
    nearer = QADIRABAD.model_copy(update={"id": "near", "longitude": 73.714})
    farther = QADIRABAD.model_copy(update={"id": "far", "longitude": 73.75})
    cases = StaticPrecomputedCases(cases=[farther, nearer])

    # Act
    found = cases.find(longitude=73.713, latitude=32.329, lens=Lens.FLOOD_WETLAND)

    # Assert
    assert found is not None
    assert found.id == "near"


def test_cases_load_from_a_json_file_and_a_missing_path_means_none(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([QADIRABAD.model_dump(mode="json")]))

    # Act
    loaded = StaticPrecomputedCases.from_file(path=str(path))
    empty = StaticPrecomputedCases.from_file(path=None)

    # Assert
    assert loaded.find(longitude=73.713, latitude=32.329, lens=Lens.FLOOD_WETLAND) is not None
    assert empty.find(longitude=73.713, latitude=32.329, lens=Lens.FLOOD_WETLAND) is None
