from pathlib import Path
from typing import Any

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

STAGES = ["catalog_s", "probe_s", "read_s", "prepare_s"]
CONFIG_COLUMNS = ["runtime", "threads", "block_mb", "multilook", "n_images", "reader"]
SUMMARY_COLUMNS = [*STAGES, "total_s", "requests", "mb_downloaded"]
AOI_AREA_KM2 = 10.24**2
MAX_IMAGES = 5


def _clean(records: pd.DataFrame) -> pd.DataFrame:
    return records[records["error"].isna() & records["total_s"].notna()]


def _markdown_table(frame: pd.DataFrame) -> str:
    header = "| " + " | ".join(str(column) for column in frame.columns) + " |"
    divider = "|" + "|".join("---" for _ in frame.columns) + "|"
    rows = [
        "| " + " | ".join("" if pd.isna(value) else str(value) for value in row) + " |"
        for row in frame.itertuples(index=False)
    ]
    return "\n".join([header, divider, *rows])


def build_report(records: pd.DataFrame, budget_s: float) -> str:
    clean = _clean(records)
    failed = records[records["error"].notna()]
    lines = [
        "# Benchmark report",
        "",
        f"{len(records)} runs ({len(clean)} clean, {len(failed)} failed) across "
        f"{records['runtime'].nunique()} runtime(s); run ids: "
        f"{', '.join(sorted(records['run_id'].astype(str).unique()))}.",
        "",
        "## Median by configuration (seconds, MB)",
        "",
    ]
    if clean.empty:
        lines.append("No clean runs.")
    else:
        summary = clean.groupby(CONFIG_COLUMNS)[SUMMARY_COLUMNS].median().round(2).reset_index()
        counts = clean.groupby(CONFIG_COLUMNS).size().rename("runs").reset_index()
        lines.append(_markdown_table(summary.merge(counts, on=CONFIG_COLUMNS)))
        lines += ["", *_budget_section(clean=clean, budget_s=budget_s)]
        lines += ["", *_prepare_section(clean=clean)]
    if not failed.empty:
        lines += ["", "## Failures", ""]
        lines.append(_markdown_table(failed[["run_id", "runtime", "site", "error"]]))
    return "\n".join(lines) + "\n"


def _budget_section(clean: pd.DataFrame, budget_s: float) -> list[str]:
    per_runtime = clean.groupby("runtime")[[*STAGES, "total_s"]].median()
    lines = [f"## Budget ({budget_s:g} s for catalog + auth + fetch + prepare)", ""]
    for runtime, row in per_runtime.iterrows():
        dominant = str(row[STAGES].idxmax())
        verdict = "fits" if row["total_s"] <= budget_s else "does not fit"
        lines.append(
            f"- **{runtime}**: median total {row['total_s']:.1f} s {verdict} the "
            f"{budget_s:g} s budget; dominant stage `{dominant}` ({row[dominant]:.1f} s)."
        )
    fastest = per_runtime["total_s"].idxmin()
    lines += [
        "",
        f"Fastest runtime: **{fastest}** (median total {per_runtime['total_s'].min():.1f} s).",
    ]
    return lines


def _prepare_section(clean: pd.DataFrame) -> list[str]:
    vectorized = clean["prepare_s"].median()
    original = clean["prepare_original_s"].median()
    ratio = original / vectorized if vectorized else float("inf")
    return [
        "## Prepare stage",
        "",
        f"Vectorized metrics take a median {vectorized:.2f} s against {original:.2f} s for the "
        f"original `metricas_serie` ({ratio:.1f}x).",
    ]


def recommend_defaults(records: pd.DataFrame) -> dict[str, object]:
    clean = _clean(records)
    if clean.empty:
        raise ValueError("no successful runs to recommend defaults from")
    grouped = clean.groupby(CONFIG_COLUMNS)["total_s"].median()
    best = grouped.idxmin()
    if not isinstance(best, tuple):
        raise TypeError(f"expected a tuple of configuration values, got {type(best)}")
    config: dict[str, Any] = dict(zip(CONFIG_COLUMNS, best, strict=True))
    mask = pd.Series(True, index=clean.index)
    for column, value in config.items():
        mask &= clean[column] == value
    return {
        "runtime": config["runtime"],
        "threads": int(config["threads"]),
        "block_mb": float(config["block_mb"]),
        "multilook": int(config["multilook"]),
        "max_images": MAX_IMAGES,
        "reader": config["reader"],
        "measured_area_km2": round(AOI_AREA_KM2, 2),
        "median_total_s": round(float(grouped.min()), 2),
        "evidence_run_ids": sorted(clean.loc[mask, "run_id"].astype(str).unique()),
    }


def compare_to_baseline(
    records: pd.DataFrame, baseline: dict[str, float], tolerance: float
) -> list[str]:
    clean = _clean(records)
    return [
        stage
        for stage in STAGES
        if stage in baseline and clean[stage].median() > baseline[stage] * (1 + tolerance)
    ]


def write_stage_chart(records: pd.DataFrame, path: Path) -> None:
    clean = _clean(records)
    labels = (
        clean[[*CONFIG_COLUMNS[:3], "reader"]]
        .astype(str)
        .agg(" · ".join, axis=1)
        .rename("configuration")
    )
    medians = clean[STAGES].groupby(labels).median()
    figure, axes = plt.subplots(figsize=(10, max(3.0, 0.6 * len(medians) + 1)))
    medians.plot(kind="barh", stacked=True, ax=axes)
    axes.set_xlabel("seconds (median)")
    axes.set_ylabel("")
    axes.set_title("Fetch and prepare time by stage")
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)
