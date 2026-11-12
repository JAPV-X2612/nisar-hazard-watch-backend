import pytest

from nisar_bench.cases import CaseSpec
from nisar_bench.run_case import run_case
from tests.fakes import TOKEN, FakeLab, catalog_frame

RUN_ID = "test-run"
RUNTIME = "local"
STAGE_COLUMNS = ["catalog_s", "probe_s", "read_s", "prepare_s"]
SPEC = CaseSpec(site="qadirabad", threads=3, block_mb=2.0, multilook=2)


def _search(lab, aoi_wkt, months=5):
    return catalog_frame()


def _run(lab: FakeLab) -> dict:
    return run_case(
        spec=SPEC,
        token=TOKEN,
        lab=lab,
        runtime=RUNTIME,
        run_id=RUN_ID,
        catalog_search=_search,
    )


def test_a_successful_case_records_every_stage_and_the_totals() -> None:
    # Arrange
    lab = FakeLab()

    # Act
    record = _run(lab=lab)

    # Assert
    assert record["error"] is None
    assert record["run_id"] == RUN_ID
    assert record["runtime"] == RUNTIME
    assert record["group"] == "84/A/18"
    assert record["scenes"] == 5
    assert record["requests"] == 250
    assert record["mb_downloaded"] == 75.0
    assert record["valid_pct"] == 99.0
    stage_sum = sum(record[column] for column in STAGE_COLUMNS)
    assert record["total_s"] == pytest.approx(stage_sum)


def test_the_case_parameters_reach_the_lab() -> None:
    # Arrange
    lab = FakeLab()

    # Act
    _run(lab=lab)

    # Assert
    assert lab.calls["aoi"]["radio_km"] == 5.12
    assert lab.calls["fs"]["block_size"] == 2 * 2**20
    assert lab.calls["stack"] == {"hilos": 3, "multilook": 2, "usar_mask": True}
    assert lab.calls["probe"]["url"].endswith("20261022.h5")


def test_the_prepared_layers_are_timed_with_both_implementations() -> None:
    # Arrange
    lab = FakeLab()

    # Act
    record = _run(lab=lab)

    # Assert
    assert record["prepare_s"] >= 0
    assert record["prepare_original_s"] >= 0


@pytest.mark.parametrize(argnames="stage", argvalues=["probe", "read"])
def test_a_failing_stage_is_captured_without_leaking_the_token(stage: str) -> None:
    # Arrange
    lab = FakeLab(fail_in=stage)

    # Act
    record = _run(lab=lab)

    # Assert
    assert record["error"]
    assert TOKEN not in record["error"]
    assert record["total_s"] is None
    assert record["catalog_s"] is not None
