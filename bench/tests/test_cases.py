from nisar_bench.cases import SITES, CaseSpec, build_matrix

DEFAULT_SPEC = CaseSpec(site="qadirabad")


def test_the_default_case_matches_the_mvp_contract() -> None:
    # Arrange
    spec = DEFAULT_SPEC

    # Act
    side_km = 2 * spec.half_side_km

    # Assert
    assert spec.n_images == 5
    assert side_km == 10.24
    assert spec.reader == "pyfive"


def test_a_case_survives_a_round_trip_through_a_dict() -> None:
    # Arrange
    spec = CaseSpec(site="chokwe", threads=3, block_mb=4.0, multilook=1, reader="h5py")

    # Act
    restored = CaseSpec.from_dict(data=spec.to_dict())

    # Assert
    assert restored == spec


def test_the_matrix_is_the_product_of_the_requested_options() -> None:
    # Arrange
    sites, threads, readers = ["qadirabad", "richmond"], [3, 5], ["pyfive", "h5py"]

    # Act
    matrix = build_matrix(sites=sites, threads=threads, readers=readers, block_mb=1.0, multilook=2)

    # Assert
    assert len(matrix) == 8
    assert {spec.site for spec in matrix} == set(sites)
    assert {spec.reader for spec in matrix} == set(readers)


def test_every_known_site_has_valid_coordinates() -> None:
    # Arrange
    sites = SITES.values()

    # Act
    valid = [-90 <= site.lat <= 90 and -180 <= site.lon <= 180 for site in sites]

    # Assert
    assert all(valid)
