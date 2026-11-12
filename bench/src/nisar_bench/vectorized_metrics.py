from collections.abc import Sequence

import numpy as np
import xarray as xr

DB_FACTOR = 10


def quantiles_along_time(stack: np.ndarray, quantiles: Sequence[float]) -> np.ndarray:
    """NaN-aware linear quantiles over axis 0, without a per-pixel Python loop."""
    ordered = np.sort(stack, axis=0)
    valid = np.sum(~np.isnan(stack), axis=0)
    results = []
    for quantile in quantiles:
        position = np.clip((valid - 1) * quantile, 0, None)
        lower = np.floor(position).astype(int)
        upper = np.minimum(lower + 1, np.maximum(valid - 1, 0))
        low_values = np.take_along_axis(ordered, lower[None], axis=0)[0]
        high_values = np.take_along_axis(ordered, upper[None], axis=0)[0]
        values = low_values + (high_values - low_values) * (position - lower)
        results.append(np.where(valid > 0, values, np.nan))
    return np.stack(results)


def series_metrics(da: xr.DataArray) -> xr.Dataset:
    """Same seven per-pixel metrics as the lab's `metricas_serie`, computed with one sort."""
    stack = da.transpose("time", ...).values
    p05, p50, p95 = quantiles_along_time(stack=stack, quantiles=(0.05, 0.5, 0.95))
    with np.errstate(all="ignore"):
        mean = np.nanmean(stack, axis=0)
        std = np.nanstd(stack, axis=0)
        positive_p05 = np.where(p05 > 0, p05, np.nan)
        positive_p95 = np.where(p95 > 0, p95, np.nan)
        range_db = DB_FACTOR * np.log10(positive_p95 / positive_p05)
        variation = std / np.where(mean != 0, mean, np.nan)
    spatial_dims = [dim for dim in da.dims if dim != "time"]
    coords = {dim: da.coords[dim] for dim in spatial_dims if dim in da.coords}

    def layer(values: np.ndarray) -> xr.DataArray:
        return xr.DataArray(values, dims=spatial_dims, coords=coords)

    return xr.Dataset(
        {
            "p05": layer(p05),
            "p50": layer(p50),
            "p95": layer(p95),
            "rango_db": layer(range_db),
            "media": layer(mean),
            "std": layer(std),
            "cv": layer(variation),
        }
    )
