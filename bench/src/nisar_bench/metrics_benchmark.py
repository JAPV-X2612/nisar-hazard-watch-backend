import time
from typing import Any

import numpy as np
import xarray as xr

from nisar_bench.vectorized_metrics import series_metrics

SEED = 0
GAMMA_SHAPE = 4.0
GAMMA_SCALE = 0.05
NAN_FRACTION = 0.05


def benchmark_metrics(lab: Any, shapes: list[tuple[int, int, int]]) -> list[dict[str, Any]]:
    """Time the lab's per-pixel metrics against the vectorized ones on synthetic stacks."""
    rng = np.random.default_rng(SEED)
    results = []
    for shape in shapes:
        data = rng.gamma(shape=GAMMA_SHAPE, scale=GAMMA_SCALE, size=shape).astype("float32")
        data[rng.random(shape) < NAN_FRACTION] = np.nan
        da = xr.DataArray(data, dims=("time", "y", "x"))

        started = time.perf_counter()
        original = lab.metricas_serie(da=da)
        original_s = time.perf_counter() - started

        started = time.perf_counter()
        vectorized = series_metrics(da=da)
        vectorized_s = time.perf_counter() - started

        results.append(
            {
                "shape": "x".join(str(size) for size in shape),
                "original_s": round(original_s, 3),
                "vectorized_s": round(vectorized_s, 3),
                "speedup": round(original_s / vectorized_s, 1) if vectorized_s else None,
                "max_abs_diff": _max_abs_diff(original=original, vectorized=vectorized),
            }
        )
    return results


def _max_abs_diff(original: xr.Dataset, vectorized: xr.Dataset) -> float:
    differences = []
    for name in vectorized.data_vars:
        difference = np.abs(original[name].values - vectorized[name].values)
        if np.isfinite(difference).any():
            differences.append(float(np.nanmax(difference)))
    return max(differences, default=0.0)
