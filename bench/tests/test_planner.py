import itertools

import pandas as pd
import pytest

from nisar_bench.planner import plan_scenes

GROUP = (84, "A", 18)
PARTIAL_GROUP = (172, "A", 9)
SERIES_START = pd.Timestamp("2026-06-12")
REVISIT = pd.Timedelta(days=12)
NEWEST_DATE = pd.Timestamp("2026-10-22")
MIN_GAP_DAYS = 24
MAX_GAP_DAYS = 48
SCENE_COLUMNS = ["fecha", "pista", "direccion", "frame", "pol"]


def _scene(group: tuple[int, str, int], date: pd.Timestamp, mode: str, coverage: float) -> dict:
    track, direction, frame = group
    return {
        "fecha": date,
        "pista": track,
        "direccion": direction,
        "frame": frame,
        "pol": mode,
        "cobertura_aoi": coverage,
        "url": f"https://example.test/{track}_{frame}_{date:%Y%m%d}.h5",
    }


def _series(
    group: tuple[int, str, int], count: int, mode: str = "DHDH", coverage: float = 1.0
) -> list[dict]:
    return [
        _scene(group, pd.Timestamp(SERIES_START + i * REVISIT), mode, coverage)
        for i in range(count)
    ]


def test_it_picks_the_group_that_covers_the_aoi_fully_and_has_the_most_dates() -> None:
    # Arrange
    catalog = pd.DataFrame(
        _series(GROUP, 12) + _series(PARTIAL_GROUP, 14, coverage=0.45),
    )

    # Act
    group, scenes = plan_scenes(catalog=catalog)

    # Assert
    assert group == GROUP
    assert set(scenes["pista"]) == {GROUP[0]}


def test_it_falls_back_to_the_best_partial_group_when_none_covers_the_aoi() -> None:
    # Arrange
    catalog = pd.DataFrame(
        _series(GROUP, 6, coverage=0.4) + _series(PARTIAL_GROUP, 6, coverage=0.7),
    )

    # Act
    group, _ = plan_scenes(catalog=catalog)

    # Assert
    assert group == PARTIAL_GROUP


def test_it_ends_on_the_newest_acquisition_and_spaces_the_others_about_a_month() -> None:
    # Arrange
    catalog = pd.DataFrame(_series(GROUP, 12))

    # Act
    _, scenes = plan_scenes(catalog=catalog, n_images=5, spacing_days=30)

    # Assert
    dates = list(pd.to_datetime(scenes["fecha"]))
    gaps = [(later - earlier).days for earlier, later in itertools.pairwise(dates)]
    assert len(dates) == 5
    assert dates[-1] == NEWEST_DATE
    assert all(MIN_GAP_DAYS <= gap <= MAX_GAP_DAYS for gap in gaps)


def test_it_prefers_dual_polarization_scenes_when_there_are_enough() -> None:
    # Arrange
    rows = _series(GROUP, 12)
    for index in (1, 3, 5):
        rows[index]["pol"] = "SHSH"
    catalog = pd.DataFrame(rows)

    # Act
    _, scenes = plan_scenes(catalog=catalog)

    # Assert
    assert all("DH" in mode for mode in scenes["pol"])


def test_it_returns_what_exists_when_fewer_than_the_requested_images_are_available() -> None:
    # Arrange
    catalog = pd.DataFrame(_series(GROUP, 3))

    # Act
    _, scenes = plan_scenes(catalog=catalog, n_images=5)

    # Assert
    assert len(scenes) == 3


def test_it_drops_duplicate_acquisitions_of_the_same_group_and_day() -> None:
    # Arrange
    rows = _series(GROUP, 6)
    rows.append({**rows[-1], "url": "https://example.test/duplicate.h5"})
    catalog = pd.DataFrame(rows)

    # Act
    _, scenes = plan_scenes(catalog=catalog, n_images=6)

    # Assert
    assert scenes["fecha"].is_unique


def test_an_empty_catalog_is_rejected() -> None:
    # Arrange
    catalog = pd.DataFrame(columns=SCENE_COLUMNS)

    # Act / Assert
    with pytest.raises(expected_exception=ValueError, match="no scenes"):
        plan_scenes(catalog=catalog)
