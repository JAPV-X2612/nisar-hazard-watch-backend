import nisar_hazard_watch


def test_version_is_a_non_empty_string() -> None:
    # Arrange
    package = nisar_hazard_watch

    # Act
    version = package.__version__

    # Assert
    assert isinstance(version, str)
    assert version
