import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nisar_hazard_watch.adapters.db.database_probe import DatabaseProbe
from nisar_hazard_watch.adapters.db.job_repository import SqlJobRepository
from nisar_hazard_watch.adapters.db.models import ExplorationRecord
from nisar_hazard_watch.config.settings import get_settings
from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.constants.explorations import EXPLORATION_ID_PREFIX, ExplorationStatus
from nisar_hazard_watch.constants.health import DependencyState
from nisar_hazard_watch.models.exploration import ProblemInfo
from tests.factories import make_job

DATABASE_URL = os.environ.get("DATABASE_URL")
PROBE_TIMEOUT_SECONDS = 5.0
HEAD_REVISION = "0002"
SECONDS_TO_FINISH = 30

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
    get_settings.cache_clear()
    engine = create_async_engine(get_settings().database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = SqlJobRepository(session_factory=session_factory)
    unique = uuid4().hex
    job_id = f"{EXPLORATION_ID_PREFIX}{unique[:16]}"
    cache_key = unique * 2
    job = make_job(id=job_id, cache_key=cache_key)
    done = job.model_copy(
        update={
            "status": ExplorationStatus.SUCCEEDED,
            "finished_at": job.created_at + timedelta(seconds=SECONDS_TO_FINISH),
        }
    )

    # Act
    try:
        await repository.add(job=job)
        saved = await repository.transition(job=done)
        loaded = await repository.get(job_id=job_id)
        fresh = await repository.find_fresh(cache_key=cache_key, newer_than=job.created_at)
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(delete(ExplorationRecord).where(ExplorationRecord.id == job_id))
        await engine.dispose()

    # Assert
    assert saved is True
    assert loaded == done
    assert fresh is not None
    assert fresh.id == job_id


async def test_an_overdue_job_is_expired_and_stops_counting_as_active_on_postgres() -> None:
    # Arrange
    get_settings.cache_clear()
    engine = create_async_engine(get_settings().database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = SqlJobRepository(session_factory=session_factory)
    job_id = f"{EXPLORATION_ID_PREFIX}{uuid4().hex[:16]}"
    job = make_job(id=job_id, cache_key=uuid4().hex * 2)
    now = job.deadline_at + timedelta(seconds=1)
    timeout = ProblemInfo(reason_code=ReasonCode.TIMEOUT_PARTIAL, detail="late")

    # Act
    try:
        await repository.add(job=job)
        active_before = await repository.count_active(now=job.deadline_at - timedelta(seconds=1))
        active_after_deadline = await repository.count_active(now=now)
        expired = await repository.expire_overdue(now=now, error=timeout)
        loaded = await repository.get(job_id=job_id)
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(delete(ExplorationRecord).where(ExplorationRecord.id == job_id))
        await engine.dispose()

    # Assert
    assert active_before > active_after_deadline
    assert expired >= 1
    assert loaded is not None
    assert loaded.status is ExplorationStatus.PARTIAL
    assert loaded.error == timeout
