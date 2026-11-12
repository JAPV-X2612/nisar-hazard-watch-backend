import subprocess
from typing import Any

import pytest

from nisar_bench.cases import CaseSpec
from nisar_bench.runtime_local import KeychainError, read_keychain_token, run_local
from tests.fakes import TOKEN, FakeLab, catalog_frame

RUN_ID = "local-test"
SPECS = [CaseSpec(site="qadirabad", reader="pyfive"), CaseSpec(site="richmond", reader="h5py")]


def _search(lab, aoi_wkt, months=5):
    return catalog_frame()


def test_it_runs_every_case_with_its_reader_and_the_local_runtime() -> None:
    # Arrange
    applied: list[str] = []
    lab = FakeLab()

    # Act
    records = run_local(
        specs=SPECS,
        run_id=RUN_ID,
        token_provider=lambda: TOKEN,
        lab_loader=lambda: lab,
        reader_applier=lambda lab, reader: applied.append(reader),
        catalog_search=_search,
    )

    # Assert
    assert [record["site"] for record in records] == ["qadirabad", "richmond"]
    assert {record["runtime"] for record in records} == {"local"}
    assert applied == ["pyfive", "h5py"]


def test_the_keychain_token_is_read_with_the_security_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        calls.append(command)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout=f"{TOKEN}\n")

    monkeypatch.setattr(target=subprocess, name="run", value=fake_run)

    # Act
    token = read_keychain_token()

    # Assert
    assert token == TOKEN
    assert calls[0][:2] == ["security", "find-generic-password"]
    assert "nisac-earthdata-token" in calls[0]


def test_a_missing_keychain_item_fails_without_printing_anything_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        raise subprocess.CalledProcessError(returncode=44, cmd=command)

    monkeypatch.setattr(target=subprocess, name="run", value=fake_run)

    # Act / Assert
    with pytest.raises(expected_exception=KeychainError, match="nisac-earthdata-token"):
        read_keychain_token()
