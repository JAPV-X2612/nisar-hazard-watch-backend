import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

DEFAULT_LAB_PATH = "/Users/japv-x2612/Documents/NISAC/Backend/NISAC_Data_Lab"
LAB_FILE_ENV = "NISAC_LAB_FILE"
LAB_PATH_ENV = "NISAC_LAB_PATH"
LAB_MODULE_NAME = "nisac_ts"
READERS = ("pyfive", "h5py")


def load_lab(lab_file: str | Path | None = None) -> ModuleType:
    """Import DSSA's reference reader (`util/nisac_ts.py`) from a file, without copying it."""
    path = Path(lab_file) if lab_file else resolve_lab_file()
    if not path.is_file():
        raise FileNotFoundError(
            f"cannot find the lab reader at {path}; set {LAB_PATH_ENV} to the NISAC_Data_Lab folder"
        )
    spec = importlib.util.spec_from_file_location(LAB_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[LAB_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def resolve_lab_file() -> Path:
    if os.environ.get(LAB_FILE_ENV):
        return Path(os.environ[LAB_FILE_ENV])
    return Path(os.environ.get(LAB_PATH_ENV, DEFAULT_LAB_PATH)) / "util" / "nisac_ts.py"


def apply_reader(lab: Any, reader: str) -> None:
    """Force the HDF5 backend the lab opens scenes with (it prefers h5py when installed)."""
    if reader == "pyfive":
        import pyfive

        def open_with_pyfive(source: Any) -> Any:
            return pyfive.File(source)

        lab.abrir_h5 = open_with_pyfive
    elif reader == "h5py":
        import h5py

        def open_with_h5py(source: Any) -> Any:
            return h5py.File(source, "r")

        lab.abrir_h5 = open_with_h5py
    else:
        raise ValueError(f"unknown reader {reader!r}; expected one of {READERS}")
