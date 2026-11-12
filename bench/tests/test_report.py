from pathlib import Path

import pandas as pd
import pytest

from nisar_bench.report import (
    build_report,
    compare_to_baseline,
    recommend_defaults,
    write_stage_chart,
)

BUDGET_S = 22.0


def _row(
    runtime: str,
    site: str,
    read_s: float,
    run_id: str = "run-1",
    threads: int = 5,
    reader: str = "pyfive",
    error: str | None = None,
    catalog_s: float = 2.0,
    probe_s: float = 1.0,
    prepare_s: float = 3.0,
) -> dict:
    ok = error is None
    return {
        "run_id": run_id,
        "runtime": runtime,
        "site": site,
        "threads": threads,
        "block_mb": 1.0,
        "multilook": 2,
        "n_images": 5,
        "use_mask": True,
        "reader": reader,
        "catalog_s": catalog_s,
        "probe_s": probe_s,
        "read_s": read_s,
        "prepare_s": prepare_s,
        "prepare_original_s": 4.5,
        "total_s": catalog_s + probe_s + read_s + prepare_s if ok else None,
        "requests": 250,
        "mb_downloaded": 70.0,
        "valid_pct": 99.0,
        "error": error,
    }


def _records() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _row(runtime="local", site="qadirabad", read_s=60.0, run_id="local-1"),
            _row(runtime="local", site="richmond", read_s=30.0, run_id="local-1"),
            _row(runtime="modal", site="qadirabad", read_s=12.0, run_id="modal-1"),
            _row(runtime="modal", site="richmond", read_s=10.0, run_id="modal-1"),
            _row(
                runtime="modal", site="chokwe", read_s=0.0, run_id="modal-1", error="Boom: failed"
            ),
        ]
    )


def test_the_report_summarises_each_runtime_and_flags_failures() -> None:
    # Arrange
    records = _records()

    # Act
    report = build_report(records=records, budget_s=BUDGET_S)

    # Assert
    assert "# Benchmark report" in report
    assert "| local |" in report
    assert "| modal |" in report
    assert "Boom: failed" in report
    assert "read_s" in report


def test_the_report_says_which_runtime_is_fastest_and_whether_it_fits_the_budget() -> None:
    # Arrange
    records = _records()

    # Act
    report = build_report(records=records, budget_s=BUDGET_S)

    # Assert
    assert "Fastest runtime: **modal**" in report
    assert "fits the 22 s budget" in report
    assert "does not fit the 22 s budget" in report


def test_recommended_defaults_come_from_the_fastest_clean_configuration() -> None:
    # Arrange
    records = _records()

    # Act
    defaults = recommend_defaults(records=records)

    # Assert
    assert defaults["runtime"] == "modal"
    assert defaults["threads"] == 5
    assert defaults["reader"] == "pyfive"
    assert defaults["evidence_run_ids"] == ["modal-1"]
    assert defaults["median_total_s"] == pytest.approx(17.0)


def test_recommending_defaults_without_a_clean_run_is_rejected() -> None:
    # Arrange
    records = pd.DataFrame([_row(runtime="local", site="qadirabad", read_s=0.0, error="Boom")])

    # Act / Assert
    with pytest.raises(expected_exception=ValueError, match="no successful"):
        recommend_defaults(records=records)


def test_a_stage_slower_than_the_baseline_by_more_than_the_tolerance_is_reported() -> None:
    # Arrange
    records = pd.DataFrame([_row(runtime="modal", site="qadirabad", read_s=20.0)])
    baseline = {"catalog_s": 2.0, "probe_s": 1.0, "read_s": 12.0, "prepare_s": 3.0}

    # Act
    regressions = compare_to_baseline(records=records, baseline=baseline, tolerance=0.2)

    # Assert
    assert regressions == ["read_s"]


def test_stages_within_the_tolerance_are_not_regressions() -> None:
    # Arrange
    records = pd.DataFrame([_row(runtime="modal", site="qadirabad", read_s=13.0)])
    baseline = {"catalog_s": 2.0, "probe_s": 1.0, "read_s": 12.0, "prepare_s": 3.0}

    # Act
    regressions = compare_to_baseline(records=records, baseline=baseline, tolerance=0.2)

    # Assert
    assert regressions == []


def test_the_stage_chart_is_written_as_a_png(tmp_path: Path) -> None:
    # Arrange
    chart = tmp_path / "stages.png"

    # Act
    write_stage_chart(records=_records(), path=chart)

    # Assert
    assert chart.read_bytes().startswith(b"\x89PNG")
