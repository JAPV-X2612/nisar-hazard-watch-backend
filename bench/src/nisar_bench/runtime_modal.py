import sys
from typing import Any

import modal

from nisar_bench.cases import CaseSpec
from nisar_bench.reader import apply_reader, load_lab, resolve_lab_file
from nisar_bench.run_case import run_case

APP_NAME = "nisar-hazard-watch-bench"
SECRET_NAME = "nisar-hazard-watch-earthdata"
REMOTE_LAB_FILE = "/root/lab/nisac_ts.py"
DEFAULT_RUNTIME = "modal"
US_WEST_RUNTIME = "modal-us-west"
PACKAGES = (
    "asf-search",
    "requests",
    "fsspec",
    "aiohttp",
    "h5py",
    "pyfive",
    "numpy",
    "pandas",
    "xarray",
    "pyproj",
    "shapely",
)

image = (
    modal.Image.debian_slim(python_version="3.13")
    .uv_pip_install(*PACKAGES)
    .env({"NISAC_LAB_FILE": REMOTE_LAB_FILE})
    .add_local_file(str(resolve_lab_file()), REMOTE_LAB_FILE)
    .add_local_python_source("nisar_bench")
)
app = modal.App(APP_NAME, image=image)
secrets = [modal.Secret.from_name(SECRET_NAME)]


def _execute(spec: dict[str, Any], run_id: str, runtime: str) -> dict[str, Any]:
    import os

    case = CaseSpec.from_dict(data=spec)
    lab = load_lab()
    apply_reader(lab=lab, reader=case.reader)
    return run_case(
        spec=case, token=os.environ["EARTHDATA_TOKEN"], lab=lab, runtime=runtime, run_id=run_id
    )


@app.function(secrets=secrets, cpu=2, memory=4096, timeout=900)
def run_in_default_region(spec: dict[str, Any], run_id: str) -> dict[str, Any]:
    return _execute(spec=spec, run_id=run_id, runtime=DEFAULT_RUNTIME)


@app.function(secrets=secrets, cpu=2, memory=4096, timeout=900, region="us-west")
def run_in_us_west(spec: dict[str, Any], run_id: str) -> dict[str, Any]:
    return _execute(spec=spec, run_id=run_id, runtime=US_WEST_RUNTIME)


def run_modal(specs: list[CaseSpec], run_id: str, region: str | None) -> list[dict[str, Any]]:
    function = run_in_us_west if region == "us-west" else run_in_default_region
    records = []
    with modal.enable_output(), app.run():
        for position, spec in enumerate(specs, start=1):
            print(f"[modal {position}/{len(specs)}] {spec}", file=sys.stderr, flush=True)
            records.append(function.remote(spec=spec.to_dict(), run_id=run_id))
    return records
