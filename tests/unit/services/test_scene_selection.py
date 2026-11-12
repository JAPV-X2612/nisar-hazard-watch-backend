import itertools
from datetime import timedelta

from nisar_hazard_watch.constants.sar import Configuration, Direction, Maturity
from nisar_hazard_watch.services.scene_selection import (
    choose_group,
    dedupe_scenes,
    select_dates,
)
from tests.factories import SERIES_START, make_scene, make_series

OTHER_GROUP = {"track": 172, "frame": 9}
MAX_IMAGES = 5
SPACING_DAYS = 30
TOLERANCE_DAYS = 6
NEWEST = SERIES_START + timedelta(days=12 * 11)


def test_a_production_and_an_urgent_product_of_one_acquisition_leave_only_the_production_one() -> (
    None
):
    # Arrange
    production = make_scene(configuration=Configuration.PRODUCTION, maturity=Maturity.PROVISIONAL)
    urgent = make_scene(configuration=Configuration.URGENT_RESPONSE, maturity=Maturity.UNVALIDATED)

    # Act
    kept = dedupe_scenes(scenes=[urgent, production])

    # Assert
    assert kept == [production]


def test_the_validated_reprocessing_wins_over_the_provisional_one() -> None:
    # Arrange
    provisional = make_scene(maturity=Maturity.PROVISIONAL, crid="P05036")
    validated = make_scene(maturity=Maturity.VALIDATED, crid="P05000")

    # Act
    kept = dedupe_scenes(scenes=[validated, provisional])

    # Assert
    assert kept == [validated]


def test_the_newest_crid_and_version_win_when_maturity_and_configuration_tie() -> None:
    # Arrange
    old = make_scene(crid="P05023", version=1)
    newer_crid = make_scene(crid="P05036", version=1)
    newer_version = make_scene(crid="P05036", version=2)

    # Act
    kept = dedupe_scenes(scenes=[old, newer_crid, newer_version])

    # Assert
    assert kept == [newer_version]


def test_distinct_acquisitions_are_all_kept_in_time_order() -> None:
    # Arrange
    scenes = list(reversed(make_series(count=4)))

    # Act
    kept = dedupe_scenes(scenes=scenes)

    # Assert
    assert [scene.acquired_at for scene in kept] == sorted(scene.acquired_at for scene in scenes)


def test_the_group_that_fully_covers_the_aoi_beats_a_partial_one_with_more_dates() -> None:
    # Arrange
    full = make_series(count=8)
    partial = make_series(count=12, coverage=0.4, **OTHER_GROUP)

    # Act
    group = choose_group(scenes=[*partial, *full])

    # Assert
    assert group is not None
    assert (group.track, group.frame) == (84, 18)


def test_dual_pol_beats_single_pol_and_then_the_group_with_more_dates_wins() -> None:
    # Arrange
    single_pol = make_series(count=12, mode="SHSH", polarizations=["HH"], **OTHER_GROUP)
    dual_few = make_series(count=6)
    dual_many = make_series(count=9, track=300, frame=40)

    # Act
    group = choose_group(scenes=[*single_pol, *dual_few, *dual_many])

    # Assert
    assert group is not None
    assert group.track == 300


def test_a_tie_is_resolved_by_the_newest_acquisition_then_by_group_numbers() -> None:
    # Arrange
    older = make_series(count=5)
    newer = [
        make_scene(acquired_at=scene.acquired_at + timedelta(days=6), **OTHER_GROUP)
        for scene in make_series(count=5)
    ]

    # Act
    group = choose_group(scenes=[*older, *newer])

    # Assert
    assert group is not None
    assert group.track == OTHER_GROUP["track"]


def test_with_no_full_coverage_the_best_covered_group_is_chosen() -> None:
    # Arrange
    low = make_series(count=10, coverage=0.3)
    better = make_series(count=4, coverage=0.7, **OTHER_GROUP)

    # Act
    group = choose_group(scenes=[*low, *better])

    # Assert
    assert group is not None
    assert group.track == OTHER_GROUP["track"]


def test_no_scenes_means_no_group() -> None:
    # Arrange
    scenes: list = []

    # Act
    group = choose_group(scenes=scenes)

    # Assert
    assert group is None


def test_dates_end_on_the_newest_acquisition_and_walk_back_about_a_month() -> None:
    # Arrange
    scenes = make_series(count=12)

    # Act
    selected = select_dates(
        scenes=scenes,
        max_images=MAX_IMAGES,
        spacing_days=SPACING_DAYS,
        tolerance_days=TOLERANCE_DAYS,
    )

    # Assert
    dates = [scene.acquired_at for scene in selected]
    gaps = [(later - earlier).days for earlier, later in itertools.pairwise(dates)]
    assert len(selected) == MAX_IMAGES
    assert dates[-1] == NEWEST
    assert all(
        SPACING_DAYS - TOLERANCE_DAYS <= gap <= SPACING_DAYS + TOLERANCE_DAYS for gap in gaps
    )


def test_a_gap_in_the_archive_gives_fewer_images_instead_of_a_far_away_substitute() -> None:
    # Arrange
    series = make_series(count=12)
    gap_start = NEWEST - timedelta(days=SPACING_DAYS + 9)
    gap_end = NEWEST - timedelta(days=SPACING_DAYS - 9)
    scenes = [s for s in series if not gap_start <= s.acquired_at <= gap_end]

    # Act
    selected = select_dates(
        scenes=scenes,
        max_images=MAX_IMAGES,
        spacing_days=SPACING_DAYS,
        tolerance_days=TOLERANCE_DAYS,
    )

    # Assert
    assert len(selected) < MAX_IMAGES
    assert all(scene.acquired_at not in (gap_start, gap_end) for scene in selected)


def test_an_empty_series_selects_nothing() -> None:
    # Arrange
    scenes: list = []

    # Act
    selected = select_dates(
        scenes=scenes,
        max_images=MAX_IMAGES,
        spacing_days=SPACING_DAYS,
        tolerance_days=TOLERANCE_DAYS,
    )

    # Assert
    assert selected == []


def test_directions_are_part_of_the_group_identity() -> None:
    # Arrange
    ascending = make_series(count=4)
    descending = make_series(count=6, direction=Direction.DESCENDING)

    # Act
    group = choose_group(scenes=[*ascending, *descending])

    # Assert
    assert group is not None
    assert group.direction is Direction.DESCENDING


def test_bandwidth_codes_and_modes_of_one_frame_are_different_series() -> None:
    # Arrange
    wide_band = make_series(count=4)
    narrow_band = make_series(count=7, code="2005")
    quad_pol = make_series(count=5, mode="QPDH", polarizations=["HH", "HV", "VH", "VV"])

    # Act
    group = choose_group(scenes=[*wide_band, *narrow_band, *quad_pol])

    # Assert
    assert group is not None
    assert group.series_key == "084_A_018_2005_DHDH"


def test_the_series_key_follows_the_ml_service_format() -> None:
    # Arrange
    scenes = make_series(count=4)

    # Act
    group = choose_group(scenes=scenes)

    # Assert
    assert group is not None
    assert group.series_key == "084_A_018_4005_DHDH"


def test_a_tie_between_series_is_resolved_by_the_smallest_key() -> None:
    # Arrange
    first = make_series(count=5, code="2005")
    second = make_series(count=5, code="4005")

    # Act
    group = choose_group(scenes=[*second, *first])

    # Assert
    assert group is not None
    assert group.code == "2005"
