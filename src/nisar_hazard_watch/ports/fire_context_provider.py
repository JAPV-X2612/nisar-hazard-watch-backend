from typing import Protocol

from nisar_hazard_watch.models.fire_context import FireContext
from nisar_hazard_watch.models.scene import ScenePlan


class FireContextProvider(Protocol):
    async def fire_context(self, plan: ScenePlan) -> FireContext:
        """Independent fire evidence for the plan's area; never raises."""
        ...
