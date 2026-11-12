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
HEAD_REVISION = "0002"

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
    assert version == HEAD_REVISION


async def test_explorations_round_trip_through_the_migrated_schema() -> None:
    # Arrange
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from nisar_hazard_watch.adapters.db.job_repository import SqlJobRepository
    from nisar_hazard_watch.constants.explorations import ExplorationStatus
    from tests.factories import make_job

    get_settings.cache_clear()
    engine = create_async_engine(get_settings().database_url)
    repository = SqlJobRepository(
        session_factory=async_sessionmaker(engine, expire_on_commit=False)
    )
    job_id = f"exp_{datetime.now(UTC):%H%M%S%f}"[:20]
    job = make_job(id=job_id, cache_key="d" * 64)
    done = job.model_copy(
        update={
            "status": ExplorationStatus.SUCCEEDED,
            "finished_at": job.created_at + timedelta(seconds=30),
        }
    )

    # Act
    await repository.add(job=job)
    await repository.update(job=done)
    loaded = await repository.get(job_id=job_id)
    fresh = await repository.find_fresh(cache_key="d" * 64, newer_than=job.created_at)

    # Assert
    assert loaded == done
    assert fresh is not None
    assert fresh.id == job_id
    await engine.dispose()
