import numpy as np
import pytest
import xarray as xr

from nisar_bench.vectorized_metrics import quantiles_along_time, series_metrics

QUANTILES = (0.05, 0.5, 0.95)
SHAPE = (5, 40, 40)
NAN_FRACTION = 0.1


def _stack(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    data = rng.gamma(shape=4.0, scale=0.05, size=SHAPE).astype("float32")
    data[rng.random(SHAPE) < NAN_FRACTION] = np.nan
    return data


def _reference_metrics(da: xr.DataArray) -> xr.Dataset:
    quantiles = da.quantile(list(QUANTILES), dim="time")
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


def test_it_matches_numpy_nanquantile_on_data_with_gaps() -> None:
    # Arrange
    stack = _stack()
    with np.errstate(all="ignore"):
        expected = np.nanquantile(stack, QUANTILES, axis=0)

    # Act
    result = quantiles_along_time(stack=stack, quantiles=QUANTILES)

    # Assert
    np.testing.assert_allclose(result, expected, rtol=1e-5, atol=1e-7, equal_nan=True)


def test_pixels_with_no_valid_sample_are_nan() -> None:
    # Arrange
    stack = _stack()
    stack[:, 0, 0] = np.nan

    # Act
    result = quantiles_along_time(stack=stack, quantiles=QUANTILES)

    # Assert
    assert np.isnan(result[:, 0, 0]).all()


@pytest.mark.parametrize(argnames="valid_count", argvalues=[1, 2, 3])
def test_it_handles_pixels_with_very_few_valid_samples(valid_count: int) -> None:
    # Arrange
    stack = _stack()
    stack[valid_count:, 1, 1] = np.nan
    with np.errstate(all="ignore"):
        expected = np.nanquantile(stack[:, 1, 1], QUANTILES)

    # Act
    result = quantiles_along_time(stack=stack, quantiles=QUANTILES)[:, 1, 1]

    # Assert
    np.testing.assert_allclose(result, expected, rtol=1e-5, atol=1e-7)


def test_series_metrics_equal_the_xarray_reference_implementation() -> None:
    # Arrange
    da = xr.DataArray(_stack(seed=3), dims=("time", "y", "x"))
    with np.errstate(all="ignore"):
        expected = _reference_metrics(da)

    # Act
    result = series_metrics(da=da)

    # Assert
    assert set(result.data_vars) == set(expected.data_vars)
    for name in expected.data_vars:
        np.testing.assert_allclose(
            result[name].values, expected[name].values, rtol=1e-4, atol=1e-6, equal_nan=True
        )
