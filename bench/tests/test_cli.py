import json
from pathlib import Path

import pandas as pd
import pytest

from nisar_bench.cli import main
from tests.test_report import _records

BASELINE_OK = {"catalog_s": 5.0, "probe_s": 5.0, "read_s": 30.0, "prepare_s": 5.0}
BASELINE_TIGHT = {"catalog_s": 5.0, "probe_s": 5.0, "read_s": 1.0, "prepare_s": 5.0}


@pytest.fixture
def csv_path(tmp_path: Path) -> Path:
    path = tmp_path / "records.csv"
    _records().to_csv(path, index=False)
    return path


def test_report_writes_the_markdown_and_the_chart(csv_path: Path, tmp_path: Path) -> None:
    # Arrange
    report, chart = tmp_path / "REPORT.md", tmp_path / "chart.png"

    # Act
    status = main(["report", "--input", str(csv_path), "--out", str(report), "--chart", str(chart)])

    # Assert
    assert status == 0
    assert report.read_text().startswith("# Benchmark report")
    assert chart.exists()


def test_defaults_writes_the_recommendation_with_its_evidence(
    csv_path: Path, tmp_path: Path
) -> None:
    # Arrange
    out = tmp_path / "defaults.json"

    # Act
    status = main(["defaults", "--input", str(csv_path), "--out", str(out)])

    # Assert
    defaults = json.loads(out.read_text())
    assert status == 0
    assert defaults["runtime"] == "modal"
    assert defaults["evidence_run_ids"] == ["modal-1"]


@pytest.mark.parametrize(
    argnames=("baseline", "expected_status"), argvalues=[(BASELINE_OK, 0), (BASELINE_TIGHT, 1)]
)
def test_compare_fails_only_when_a_stage_regresses(
    csv_path: Path, tmp_path: Path, baseline: dict, expected_status: int
) -> None:
    # Arrange
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline))

    # Act
    status = main(["compare", "--baseline", str(baseline_path), "--input", str(csv_path)])

    # Assert
    assert status == expected_status


def test_records_written_by_a_run_can_be_read_back_by_the_report(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "records.csv"
    _records().to_csv(path, index=False)

    # Act
    loaded = pd.read_csv(path)

    # Assert
    assert len(loaded) == 5
    assert loaded["error"].notna().sum() == 1
