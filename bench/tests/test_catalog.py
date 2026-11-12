from datetime import UTC, datetime

import pandas as pd

from nisar_bench.catalog import search_catalog

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
AOI_WKT = "POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))"
MONTHS = 5
EXPECTED_WINDOW_DAYS = 152


class FakeLab:
    def __init__(self) -> None:
        self.options = None
        self.aoi = None

    def catalogo_online(self, search_options, aoi_wkt, data_dir=None):
        self.options = search_options
        self.aoi = aoi_wkt
        return pd.DataFrame({"fecha": [NOW]})


def test_it_asks_asf_for_nisar_gcov_without_maturity_or_configuration_filters() -> None:
    # Arrange
    lab = FakeLab()

    # Act
    search_catalog(lab=lab, aoi_wkt=AOI_WKT, months=MONTHS, now=NOW)

    # Assert
    options = lab.options
    assert options is not None
    assert list(options.dataset) == ["NISAR"]
    assert list(options.processingLevel) == ["GCOV"]
    assert not getattr(options, "productionConfiguration", None)
    assert not getattr(options, "dataMaturity", None)
    assert lab.aoi == AOI_WKT


def test_it_searches_the_last_five_months_ending_now() -> None:
    # Arrange
    lab = FakeLab()

    # Act
    search_catalog(lab=lab, aoi_wkt=AOI_WKT, months=MONTHS, now=NOW)

    # Assert
    assert lab.options is not None
    start, end = pd.Timestamp(lab.options.start), pd.Timestamp(lab.options.end)
    assert end == pd.Timestamp(NOW)
    assert (end - start).days == EXPECTED_WINDOW_DAYS
