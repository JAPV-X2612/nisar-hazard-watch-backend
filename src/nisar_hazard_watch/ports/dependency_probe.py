from typing import Protocol

from nisar_hazard_watch.constants.health import DependencyName
from nisar_hazard_watch.models.health import DependencyReport


class DependencyProbe(Protocol):
    @property
    def name(self) -> DependencyName: ...

    @property
    def critical(self) -> bool: ...

    async def check(self) -> DependencyReport: ...
