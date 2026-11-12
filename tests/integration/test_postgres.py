import asyncio
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from nisar_hazard_watch.adapters.db.database_probe import DatabaseProbe
from nisar_hazard_watch.config.settings import get_settings
from nisar_hazard_watch.constants.health import DependencyState

DATABASE_URL = os.environ.get("DATABASE_URL")
PROBE_TIMEOUT_SECONDS = 5.0
BASELINE_REVISION = "0001"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(DATABASE_URL is None, reason="DATABASE_URL is not set"),
]


async def test_the_probe_reaches_a_real_postgres() -> None:
    # Arrange
    get_settings.cache_clear()
    engine = create_async_engine(get_settings().database_url)
    probe = DatabaseProbe(engine=engine, timeout_seconds=PROBE_TIMEOUT_SECONDS)

    # Act
    report = await probe.check()

    # Assert
    assert report.state is DependencyState.OK
    await engine.dispose()


def test_alembic_upgrades_a_real_postgres_to_head() -> None:
    # Arrange
    get_settings.cache_clear()
    config = Config("alembic.ini")

    async def read_version() -> str:
        engine = create_async_engine(get_settings().database_url)
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            version = result.scalar_one()
        await engine.dispose()
        return version

    # Act
    command.upgrade(config=config, revision="head")
    version = asyncio.run(read_version())

    # Assert
    assert version == BASELINE_REVISION
