import math

from nisar_hazard_watch.constants.explorations import (
    ETA_MIN_SAMPLES,
    ETA_PERCENTILE,
    ETA_SAMPLE_LIMIT,
    Lens,
)
from nisar_hazard_watch.ports.job_repository import JobRepository


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


class EtaEstimator:
    """p80 of recent comparable runs; until there are enough, the configured prior is used."""

    def __init__(
        self,
        repository: JobRepository,
        prior_seconds: float,
        min_samples: int = ETA_MIN_SAMPLES,
        fraction: float = ETA_PERCENTILE,
        limit: int = ETA_SAMPLE_LIMIT,
    ) -> None:
        self._repository = repository
        self._prior_seconds = prior_seconds
        self._min_samples = min_samples
        self._fraction = fraction
        self._limit = limit

    async def estimate(self, lens: Lens, scenes_total: int, area_bucket: str) -> float:
        totals = await self._repository.recent_totals(
            lens=lens, scenes_total=scenes_total, area_bucket=area_bucket, limit=self._limit
        )
        if len(totals) < self._min_samples:
            return self._prior_seconds
        return round(percentile(values=totals, fraction=self._fraction), 1)
