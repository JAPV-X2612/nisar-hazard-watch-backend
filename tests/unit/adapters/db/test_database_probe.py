from sqlalchemy.ext.asyncio import create_async_engine

from nisar_hazard_watch.adapters.db.database_probe import DatabaseProbe
from nisar_hazard_watch.constants.health import DependencyName, DependencyState

WORKING_URL = "sqlite+aiosqlite://"
BROKEN_URL = "sqlite+aiosqlite:////nonexistent-directory/nisar.db"
TIMEOUT_SECONDS = 2.0


async def test_a_reachable_database_is_ok_and_reports_latency() -> None:
    # Arrange
    engine = create_async_engine(WORKING_URL)
    probe = DatabaseProbe(engine=engine, timeout_seconds=TIMEOUT_SECONDS)

    # Act
    report = await probe.check()

    # Assert
    assert probe.name is DependencyName.DATABASE
    assert report.state is DependencyState.OK
    assert report.critical is True
    assert report.latency_ms is not None
    await engine.dispose()


async def test_an_unreachable_database_is_down_without_leaking_its_url() -> None:
    # Arrange
    engine = create_async_engine(BROKEN_URL)
    probe = DatabaseProbe(engine=engine, timeout_seconds=TIMEOUT_SECONDS)

    # Act
    report = await probe.check()

    # Assert
    assert report.state is DependencyState.DOWN
    assert report.detail == "database is unreachable"
    assert "nonexistent-directory" not in (report.detail or "")
    await engine.dispose()
