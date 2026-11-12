import asyncio
import logging
import time

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from nisar_hazard_watch.constants.health import DependencyName, DependencyState
from nisar_hazard_watch.models.health import DependencyReport
from nisar_hazard_watch.utils.timing import elapsed_ms

logger = logging.getLogger(__name__)


class DatabaseProbe:
    name = DependencyName.DATABASE
    critical = True

    def __init__(self, engine: AsyncEngine, timeout_seconds: float) -> None:
        self._engine = engine
        self._timeout_seconds = timeout_seconds

    async def check(self) -> DependencyReport:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds), self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except TimeoutError:
            logger.warning("database health check timed out", exc_info=True)
            return self._down(detail=f"database did not answer within {self._timeout_seconds:g}s")
        except (OSError, SQLAlchemyError):
            logger.warning("database health check failed", exc_info=True)
            return self._down(detail="database is unreachable")
        return DependencyReport(
            state=DependencyState.OK,
            critical=self.critical,
            latency_ms=elapsed_ms(started=started),
        )

    def _down(self, detail: str) -> DependencyReport:
        return DependencyReport(state=DependencyState.DOWN, critical=self.critical, detail=detail)
