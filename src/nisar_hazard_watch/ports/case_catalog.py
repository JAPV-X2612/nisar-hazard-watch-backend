from typing import Protocol

from nisar_hazard_watch.models.case import CaseView


class CaseCatalog(Protocol):
    async def cases(self) -> list[CaseView]:
        """The known cases in the source's order, layer URLs absolute on the source."""
        ...
