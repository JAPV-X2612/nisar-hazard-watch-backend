from datetime import date

import pytest

from nisar_hazard_watch.constants.sar import Direction
from nisar_hazard_watch.exceptions.pair_errors import InvalidPairWindowError
from nisar_hazard_watch.hazards.earthquake.insar_pairs_service import InsarPairsService
from nisar_hazard_watch.models.insar_pair import InsarPair

TODAY = date(2026, 11, 12)
LONGITUDE, LATITUDE = 130.65, 32.65
PAIR = InsarPair(
    pair_id="NISAR_L2_PR_GUNW_x",
    series_key="024_A_018_4000_SH",
    track=24,
    direction=Direction.ASCENDING,
    frame=18,
    reference_date=date(2026, 7, 21),
    secondary_date=date(2026, 8, 14),
    temporal_baseline_days=24,
)


class FakeCatalog:
    def __init__(self) -> None:
        self.calls: list[tuple[float, float, date, date]] = []

    async def pairs(
        self, longitude: float, latitude: float, start: date, end: date
    ) -> list[InsarPair]:
        self.calls.append((longitude, latitude, start, end))
        return [PAIR]


async def test_without_dates_it_searches_the_last_half_year() -> None:
    # Arrange
    catalog = FakeCatalog()
    service = InsarPairsService(catalog=catalog, today=lambda: TODAY)

    # Act
    view = await service.pairs(longitude=LONGITUDE, latitude=LATITUDE, start=None, end=None)

    # Assert
    assert (view.window_start, view.window_end) == (date(2026, 5, 16), TODAY)
    assert view.pairs == [PAIR]
    assert catalog.calls == [(LONGITUDE, LATITUDE, date(2026, 5, 16), TODAY)]


async def test_explicit_dates_are_used_as_given() -> None:
    # Arrange
    catalog = FakeCatalog()
    service = InsarPairsService(catalog=catalog, today=lambda: TODAY)

    # Act
    view = await service.pairs(
        longitude=LONGITUDE, latitude=LATITUDE, start=date(2026, 7, 1), end=date(2026, 8, 31)
    )

    # Assert
    assert (view.window_start, view.window_end) == (date(2026, 7, 1), date(2026, 8, 31))


@pytest.mark.parametrize(
    argnames=("start", "end"),
    argvalues=[
        (date(2026, 8, 31), date(2026, 7, 1)),
        (date(2026, 7, 1), date(2026, 7, 1)),
        (date(2025, 1, 1), date(2026, 11, 12)),
    ],
    ids=["decreasing", "empty", "too long"],
)
async def test_a_window_that_is_empty_decreasing_or_too_long_is_refused(
    start: date, end: date
) -> None:
    # Arrange
    catalog = FakeCatalog()
    service = InsarPairsService(catalog=catalog, today=lambda: TODAY)

    # Act / Assert
    with pytest.raises(expected_exception=InvalidPairWindowError):
        await service.pairs(longitude=LONGITUDE, latitude=LATITUDE, start=start, end=end)
    assert catalog.calls == []
