from datetime import timedelta

import pandas as pd

GROUP_COLUMNS = ["pista", "direccion", "frame"]
FULL_COVERAGE = 0.95
DUAL_POL_MARK = "DH"
REVISION_COLUMNS = ["crid", "version"]


def plan_scenes(
    catalog: pd.DataFrame, n_images: int = 5, spacing_days: int = 30
) -> tuple[tuple[int, str, int], pd.DataFrame]:
    """Pick one track/direction/frame group and up to n_images dates ending on the newest one."""
    if catalog.empty:
        raise ValueError("no scenes in the catalog")
    ordering = [*GROUP_COLUMNS, "fecha", *(c for c in REVISION_COLUMNS if c in catalog.columns)]
    scenes = (
        catalog.assign(fecha=pd.to_datetime(catalog["fecha"]))
        .sort_values(ordering)
        .drop_duplicates(subset=[*GROUP_COLUMNS, "fecha"], keep="last")
    )
    group = _best_group(scenes=scenes)
    track, direction, frame = group
    in_group = scenes[
        (scenes["pista"] == track) & (scenes["direccion"] == direction) & (scenes["frame"] == frame)
    ]
    return group, _pick_dates(group_scenes=in_group, n_images=n_images, spacing_days=spacing_days)


def _best_group(scenes: pd.DataFrame) -> tuple[int, str, int]:
    summary = (
        scenes.groupby(GROUP_COLUMNS)
        .agg(
            coverage=("cobertura_aoi", "mean"), dates=("fecha", "nunique"), newest=("fecha", "max")
        )
        .reset_index()
    )
    full = summary[summary["coverage"] >= FULL_COVERAGE]
    if full.empty:
        best = summary.sort_values(["coverage", "dates", "newest"], ascending=False).iloc[0]
    else:
        best = full.sort_values(["dates", "newest"], ascending=False).iloc[0]
    return int(best["pista"]), str(best["direccion"]), int(best["frame"])


def _pick_dates(group_scenes: pd.DataFrame, n_images: int, spacing_days: int) -> pd.DataFrame:
    dual = group_scenes[group_scenes["pol"].str.contains(DUAL_POL_MARK)]
    pool = dual if len(dual) >= n_images else group_scenes
    target = pool["fecha"].max()
    chosen = [pool[pool["fecha"] == target].index[0]]
    for step in range(1, n_images):
        remaining = pool[~pool.index.isin(chosen)]
        if remaining.empty:
            break
        wanted = target - timedelta(days=spacing_days * step)
        chosen.append((remaining["fecha"] - wanted).abs().idxmin())
    return pool.loc[chosen].sort_values("fecha")
