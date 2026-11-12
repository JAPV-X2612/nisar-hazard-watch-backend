import nisar_hazard_watch


def test_version_is_a_non_empty_string() -> None:
    # Arrange / Act
    version = nisar_hazard_watch.__version__

    # Assert
    assert isinstance(version, str)
    assert version
