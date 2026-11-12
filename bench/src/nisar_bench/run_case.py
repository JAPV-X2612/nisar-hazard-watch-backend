import os
import platform
import re
import time
from collections.abc import Callable
from typing import Any

import pandas as pd

from nisar_bench.cases import CaseSpec
from nisar_bench.catalog import search_catalog
from nisar_bench.planner import plan_scenes
from nisar_bench.vectorized_metrics import series_metrics

POLARIZATIONS = ("HHHH", "HVHV")
PRIMARY_POLARIZATION = POLARIZATIONS[0]
MIN_VALID_FRACTION = 0.3
SPACING_DAYS = 30
STAGES = ("catalog_s", "probe_s", "read_s", "prepare_s")
BEARER_PATTERN = re.compile(r"Bearer\s+\S+")
MIB = 2**20

CatalogSearch = Callable[..., pd.DataFrame]


def run_case(
    spec: CaseSpec,
    token: str,
    lab: Any,
    runtime: str,
    run_id: str,
    catalog_search: CatalogSearch = search_catalog,
) -> dict[str, Any]:
    """Run one benchmark case end to end and return a flat record; failures are captured."""
    record = _empty_record(spec=spec, runtime=runtime, run_id=run_id)
    try:
        _measure(record=record, spec=spec, token=token, lab=lab, catalog_search=catalog_search)
    except Exception as exc:
        record["error"] = _scrub(text=f"{type(exc).__name__}: {exc}", token=token)
    record["total_s"] = None if record["error"] else _total(record=record)
    return record


def _empty_record(spec: CaseSpec, runtime: str, run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "runtime": runtime,
        **spec.to_dict(),
        "group": None,
        "dates": None,
        "scenes": None,
        "probe_ok": None,
        **dict.fromkeys(STAGES),
        "prepare_original_s": None,
        "total_s": None,
        "requests": None,
        "mb_downloaded": None,
        "mb_hdf5": None,
        "valid_pct": None,
        "shape": None,
        "python": platform.python_version(),
        "host": f"{platform.system()} {platform.machine()}",
        "cpu_count": os.cpu_count(),
        "error": None,
    }


def _measure(
    record: dict[str, Any], spec: CaseSpec, token: str, lab: Any, catalog_search: CatalogSearch
) -> None:
    location = spec.location
    aoi = lab.aoi_desde_punto(lat=location.lat, lon=location.lon, radio_km=spec.half_side_km)

    started = time.perf_counter()
    catalog = catalog_search(lab=lab, aoi_wkt=aoi)
    group, scenes = plan_scenes(catalog=catalog, n_images=spec.n_images, spacing_days=SPACING_DAYS)
    record["catalog_s"] = _elapsed(started=started)
    record["group"] = "/".join(str(part) for part in group)
    record["dates"] = ",".join(f"{date:%Y-%m-%d}" for date in pd.to_datetime(scenes["fecha"]))

    started = time.perf_counter()
    probe_ok, _ = lab.servicio_en_linea(token=token, url_prueba=scenes["url"].iloc[-1])
    record["probe_s"] = _elapsed(started=started)
    record["probe_ok"] = bool(probe_ok)

    fs = lab.crear_fs_http(token=token, block_size=int(spec.block_mb * MIB))
    started = time.perf_counter()
    stack, log = lab.construir_pila(
        escenas=scenes,
        aoi_wkt=aoi,
        modo="online",
        fs=fs,
        frecuencia="A",
        pols=POLARIZATIONS,
        multilook=spec.multilook,
        min_validos=MIN_VALID_FRACTION,
        hilos=spec.threads,
        usar_mask=spec.use_mask,
        perfilar=True,
    )
    record["read_s"] = _elapsed(started=started)
    _record_read_details(record=record, stack=stack, log=log)

    _record_prepare(record=record, stack=stack, lab=lab)


def _record_read_details(record: dict[str, Any], stack: Any, log: pd.DataFrame) -> None:
    good = log[log["estado"] == "ok"] if "estado" in log else log
    record["scenes"] = len(good)
    record["valid_pct"] = round(float(good["validos"].mean()) * 100, 1) if len(good) else 0.0
    record["requests"] = int(log["peticiones_http"].sum()) if "peticiones_http" in log else None
    if "MB_descargados" in log:
        record["mb_downloaded"] = round(float(log["MB_descargados"].sum()), 1)
    if "MB_leidos_h5" in log:
        record["mb_hdf5"] = round(float(log["MB_leidos_h5"].sum()), 1)
    record["shape"] = f"{stack.sizes['y']}x{stack.sizes['x']}"


def _record_prepare(record: dict[str, Any], stack: Any, lab: Any) -> None:
    layer = stack[PRIMARY_POLARIZATION]
    first, last = stack["time"].values[0], stack["time"].values[-1]

    started = time.perf_counter()
    lab.log_ratio(pila=stack, pol=PRIMARY_POLARIZATION, fecha0=first, fecha1=last)
    series_metrics(da=layer)
    record["prepare_s"] = _elapsed(started=started)

    started = time.perf_counter()
    lab.log_ratio(pila=stack, pol=PRIMARY_POLARIZATION, fecha0=first, fecha1=last)
    lab.metricas_serie(da=layer)
    record["prepare_original_s"] = _elapsed(started=started)


def _total(record: dict[str, Any]) -> float | None:
    values = [record[stage] for stage in STAGES]
    return None if any(value is None for value in values) else round(sum(values), 2)


def _elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 2)


def _scrub(text: str, token: str) -> str:
    scrubbed = BEARER_PATTERN.sub("Bearer ***", text)
    return scrubbed.replace(token, "***") if token else scrubbed
