from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nisar_hazard_watch.adapters.db.models import ExplorationRecord
from nisar_hazard_watch.constants.explorations import ACTIVE_STATUSES, ExplorationStatus, Lens
from nisar_hazard_watch.ports.job_repository import ExplorationJob

DATETIME_FIELDS = ("created_at", "finished_at", "deadline_at")


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _to_record(job: ExplorationJob) -> ExplorationRecord:
    values: dict[str, Any] = job.model_dump(mode="json", by_alias=False)
    for field in DATETIME_FIELDS:
        values[field] = getattr(job, field)
    return ExplorationRecord(**values)


def _to_job(record: ExplorationRecord) -> ExplorationJob:
    values = {column.name: getattr(record, column.name) for column in record.__table__.columns}
    for field in DATETIME_FIELDS:
        values[field] = _aware(values[field])
    return ExplorationJob.model_validate(values)


class SqlJobRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, job: ExplorationJob) -> None:
        async with self._session_factory() as session, session.begin():
            session.add(_to_record(job))

    async def get(self, job_id: str) -> ExplorationJob | None:
        async with self._session_factory() as session:
            record = await session.get(ExplorationRecord, job_id)
            return _to_job(record) if record else None

    async def update(self, job: ExplorationJob) -> None:
        async with self._session_factory() as session, session.begin():
            await session.merge(_to_record(job))

    async def count_active(self) -> int:
        active = [status.value for status in ACTIVE_STATUSES]
        statement = select(func.count()).where(ExplorationRecord.status.in_(active))
        async with self._session_factory() as session:
            return int((await session.execute(statement)).scalar_one())

    async def find_fresh(self, cache_key: str, newer_than: datetime) -> ExplorationJob | None:
        statement = (
            select(ExplorationRecord)
            .where(
                ExplorationRecord.cache_key == cache_key,
                ExplorationRecord.status == ExplorationStatus.SUCCEEDED.value,
                ExplorationRecord.finished_at >= newer_than,
            )
            .order_by(ExplorationRecord.finished_at.desc())
            .limit(1)
        )
        async with self._session_factory() as session:
            record = (await session.execute(statement)).scalar_one_or_none()
            return _to_job(record) if record else None

    async def recent_totals(
        self, lens: Lens, scenes_total: int, area_bucket: str, limit: int
    ) -> list[float]:
        statement = (
            select(ExplorationRecord.created_at, ExplorationRecord.finished_at)
            .where(
                ExplorationRecord.lens == lens.value,
                ExplorationRecord.scenes_total == scenes_total,
                ExplorationRecord.area_bucket == area_bucket,
                ExplorationRecord.status == ExplorationStatus.SUCCEEDED.value,
                ExplorationRecord.finished_at.is_not(None),
            )
            .order_by(ExplorationRecord.finished_at.desc())
            .limit(limit)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        totals = []
        for created, finished in rows:
            created, finished = _aware(created), _aware(finished)
            if created is not None and finished is not None:
                totals.append((finished - created).total_seconds())
        return totals
