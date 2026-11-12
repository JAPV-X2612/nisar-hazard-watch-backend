from pathlib import Path

import pytest

from nisar_bench.reader import apply_reader, load_lab

MODULE_SOURCE = "MARKER = 'lab'\n\ndef abrir_h5(fuente):\n    return ('original', fuente)\n"


def test_it_loads_the_lab_module_from_a_file(tmp_path: Path) -> None:
    # Arrange
    lab_file = tmp_path / "nisac_ts.py"
    lab_file.write_text(MODULE_SOURCE)

    # Act
    lab = load_lab(lab_file=lab_file)

    # Assert
    assert lab.MARKER == "lab"


def test_it_fails_clearly_when_the_lab_file_is_missing(tmp_path: Path) -> None:
    # Arrange
    missing = tmp_path / "nowhere.py"

    # Act / Assert
    with pytest.raises(expected_exception=FileNotFoundError, match="NISAC_LAB_PATH"):
        load_lab(lab_file=missing)


def test_the_lab_path_comes_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    (tmp_path / "util").mkdir()
    (tmp_path / "util" / "nisac_ts.py").write_text(MODULE_SOURCE)
    monkeypatch.setenv(name="NISAC_LAB_PATH", value=str(tmp_path))
    monkeypatch.delenv(name="NISAC_LAB_FILE", raising=False)

    # Act
    lab = load_lab()

    # Assert
    assert lab.MARKER == "lab"


def test_apply_reader_replaces_the_hdf5_opener(tmp_path: Path) -> None:
    # Arrange
    lab_file = tmp_path / "nisac_ts.py"
    lab_file.write_text(MODULE_SOURCE)
    lab = load_lab(lab_file=lab_file)

    # Act
    apply_reader(lab=lab, reader="pyfive")

    # Assert
    assert lab.abrir_h5 is not None
    assert lab.abrir_h5.__name__ == "open_with_pyfive"


def test_an_unknown_reader_is_rejected(tmp_path: Path) -> None:
    # Arrange
    lab_file = tmp_path / "nisac_ts.py"
    lab_file.write_text(MODULE_SOURCE)
    lab = load_lab(lab_file=lab_file)

    # Act / Assert
    with pytest.raises(expected_exception=ValueError, match="reader"):
        apply_reader(lab=lab, reader="netcdf")
