import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from nisar_hazard_watch.adapters.db.database_probe import DatabaseProbe
from nisar_hazard_watch.constants.health import DependencyName, DependencyState
from tests.constants import SQLITE_MEMORY_URL

BROKEN_URL = "sqlite+aiosqlite:////nonexistent-directory/nisar.db"
TIMEOUT_SECONDS = 2.0
SHORT_TIMEOUT_SECONDS = 0.05
HANG_SECONDS = 10


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    working_engine = create_async_engine(SQLITE_MEMORY_URL)
    yield working_engine
    await working_engine.dispose()


@pytest.fixture
async def broken_engine() -> AsyncIterator[AsyncEngine]:
    unreachable_engine = create_async_engine(BROKEN_URL)
    yield unreachable_engine
    await unreachable_engine.dispose()


async def test_a_reachable_database_is_ok_and_reports_latency(engine: AsyncEngine) -> None:
    # Arrange
    probe = DatabaseProbe(engine=engine, timeout_seconds=TIMEOUT_SECONDS)

    # Act
    report = await probe.check()

    # Assert
    assert probe.name is DependencyName.DATABASE
    assert report.state is DependencyState.OK
    assert report.critical is True
    assert report.latency_ms is not None


async def test_an_unreachable_database_is_down_without_leaking_its_url(
    broken_engine: AsyncEngine,
) -> None:
    # Arrange
    probe = DatabaseProbe(engine=broken_engine, timeout_seconds=TIMEOUT_SECONDS)

    # Act
    report = await probe.check()

    # Assert
    assert report.state is DependencyState.DOWN
    assert report.detail == "database is unreachable"


async def test_a_database_that_hangs_is_reported_as_timed_out(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    class HangingConnection:
        async def __aenter__(self) -> None:
            await asyncio.sleep(HANG_SECONDS)

        async def __aexit__(self, *exc_info: object) -> None:
            return None

    monkeypatch.setattr(target=AsyncEngine, name="connect", value=lambda self: HangingConnection())
    probe = DatabaseProbe(engine=engine, timeout_seconds=SHORT_TIMEOUT_SECONDS)

    # Act
    report = await probe.check()

    # Assert
    assert report.state is DependencyState.DOWN
    assert report.detail == "database did not answer within 0.05s"


async def test_a_programming_error_is_not_mistaken_for_an_outage(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    def broken_connect(self: AsyncEngine) -> None:
        raise TypeError("connect() got an unexpected keyword argument 'sslmode'")

    monkeypatch.setattr(target=AsyncEngine, name="connect", value=broken_connect)
    probe = DatabaseProbe(engine=engine, timeout_seconds=TIMEOUT_SECONDS)

    # Act / Assert
    with pytest.raises(expected_exception=TypeError, match="sslmode"):
        await probe.check()
