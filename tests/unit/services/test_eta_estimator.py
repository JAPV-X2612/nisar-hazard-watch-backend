from typing import cast

import pytest

from nisar_hazard_watch.constants.explorations import Lens
from nisar_hazard_watch.ports.job_repository import JobRepository
from nisar_hazard_watch.services.eta_estimator import EtaEstimator, percentile

PRIOR_SECONDS = 60.0


class FakeRepository:
    def __init__(self, totals: list[float]) -> None:
        self._totals = totals
        self.queries: list[tuple] = []

    async def recent_totals(
        self, lens: Lens, scenes_total: int, area_bucket: str, limit: int
    ) -> list[float]:
        self.queries.append((lens, scenes_total, area_bucket, limit))
        return self._totals


@pytest.mark.parametrize(
    argnames=("values", "fraction", "expected"),
    argvalues=[
        ([10.0], 0.8, 10.0),
        ([20.0, 24.0, 30.0, 38.0, 90.0], 0.8, 38.0),
        ([90.0, 20.0, 38.0, 24.0, 30.0], 0.5, 30.0),
        ([1.0, 2.0], 1.0, 2.0),
    ],
)
def test_the_percentile_is_the_nearest_rank(
    values: list[float], fraction: float, expected: float
) -> None:
    # Arrange
    samples = values

    # Act
    result = percentile(values=samples, fraction=fraction)

    # Assert
    assert result == expected


async def test_with_too_few_runs_the_budget_is_the_prior() -> None:
    # Arrange
    repository = cast(JobRepository, FakeRepository(totals=[20.0, 30.0]))
    estimator = EtaEstimator(repository=repository, prior_seconds=PRIOR_SECONDS)

    # Act
    eta = await estimator.estimate(lens=Lens.FLOOD_WETLAND, scenes_total=5, area_bucket="<=200")

    # Assert
    assert eta == PRIOR_SECONDS


async def test_with_enough_runs_the_p80_of_the_comparable_ones_is_used() -> None:
    # Arrange
    fake = FakeRepository(totals=[20.0, 24.0, 30.0, 38.0, 90.0])
    estimator = EtaEstimator(repository=cast(JobRepository, fake), prior_seconds=PRIOR_SECONDS)

    # Act
    eta = await estimator.estimate(lens=Lens.WILDFIRE, scenes_total=4, area_bucket="<=100")

    # Assert
    assert eta == 38.0
    assert fake.queries == [(Lens.WILDFIRE, 4, "<=100", 50)]
