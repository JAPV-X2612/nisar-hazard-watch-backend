from nisar_hazard_watch.constants.health import DependencyName, DependencyState
from nisar_hazard_watch.models.health import DependencyReport


class ConfiguredProbe:
    critical = False

    def __init__(self, name: DependencyName, configured: bool) -> None:
        self.name = name
        self._configured = configured

    async def check(self) -> DependencyReport:
        state = DependencyState.CONFIGURED if self._configured else DependencyState.NOT_CONFIGURED
        return DependencyReport(state=state, critical=self.critical)
