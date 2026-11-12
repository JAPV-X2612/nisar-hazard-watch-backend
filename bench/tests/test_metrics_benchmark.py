import numpy as np
import xarray as xr

from nisar_bench.metrics_benchmark import benchmark_metrics

SHAPES = [(3, 20, 20), (4, 30, 30)]


class ReferenceLab:
    def metricas_serie(self, da):
        quantiles = da.quantile([0.05, 0.5, 0.95], dim="time")
        mean = da.mean("time")
        std = da.std("time")
        p05, p95 = quantiles.sel(quantile=0.05, drop=True), quantiles.sel(quantile=0.95, drop=True)
        return xr.Dataset(
            {
                "p05": p05,
                "p50": quantiles.sel(quantile=0.5, drop=True),
                "p95": p95,
                "rango_db": 10 * np.log10(p95.where(p95 > 0) / p05.where(p05 > 0)),
                "media": mean,
                "std": std,
                "cv": std / mean.where(mean != 0),
            }
        )


def test_it_times_both_implementations_per_shape_and_checks_they_agree() -> None:
    # Arrange
    lab = ReferenceLab()

    # Act
    results = benchmark_metrics(lab=lab, shapes=SHAPES)

    # Assert
    assert [result["shape"] for result in results] == ["3x20x20", "4x30x30"]
    for result in results:
        assert result["original_s"] >= 0
        assert result["vectorized_s"] >= 0
        assert result["max_abs_diff"] < 1e-4
