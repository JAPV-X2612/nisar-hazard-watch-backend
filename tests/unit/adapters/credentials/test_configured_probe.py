import pytest

from nisar_hazard_watch.adapters.credentials.configured_probe import ConfiguredProbe
from nisar_hazard_watch.constants.health import DependencyName, DependencyState


@pytest.mark.parametrize(
    ("configured", "expected"),
    [(True, DependencyState.CONFIGURED), (False, DependencyState.NOT_CONFIGURED)],
)
async def test_the_state_follows_whether_a_value_is_configured(
    configured: bool, expected: DependencyState
) -> None:
    # Arrange
    probe = ConfiguredProbe(name=DependencyName.MODAL, configured=configured)

    # Act
    report = await probe.check()

    # Assert
    assert probe.name is DependencyName.MODAL
    assert report.state is expected
    assert report.critical is False
