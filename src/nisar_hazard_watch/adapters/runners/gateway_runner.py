import logging
from typing import Any
from urllib.parse import urljoin

import httpx

from nisar_hazard_watch.constants.explorations import RunnerState
from nisar_hazard_watch.constants.sar import Configuration, Maturity
from nisar_hazard_watch.exceptions.exploration_errors import QueueFullError, RunnerUnavailableError
from nisar_hazard_watch.models.scene import Scene
from nisar_hazard_watch.ports.analysis_runner import (
    RunnerJob,
    RunnerLayer,
    RunnerResult,
    RunnerTicket,
)
from nisar_hazard_watch.utils.geometry import aoi_center, window_pixels

logger = logging.getLogger(__name__)

JOBS_PATH = "/v2/jobs"
BUSY_STATUSES = (429, 503)
STATE_BY_GATEWAY_STATUS = {
    "queued": RunnerState.QUEUED,
    "running": RunnerState.RUNNING,
    "succeeded": RunnerState.SUCCEEDED,
    "failed": RunnerState.FAILED,
}
COLLECTION_BY_MATURITY = {
    Maturity.PROVISIONAL: "PROVISIONAL",
    Maturity.VALIDATED: "VALIDATED",
    Maturity.BETA: "BETA",
}
URGENT_RESPONSE_COLLECTION = "UR"
LAYER_KINDS = (
    ("display_baseline_change", "change"),
    ("display_flood_signature", "diagnostic"),
    ("display_agriculture", "diagnostic"),
    ("display_cross_pol_pattern", "diagnostic"),
    ("display_optical", "diagnostic"),
    ("display_", "observed"),
)


def _collection(scene: Scene) -> str:
    if scene.configuration is Configuration.URGENT_RESPONSE:
        return URGENT_RESPONSE_COLLECTION
    return COLLECTION_BY_MATURITY[scene.maturity]


def _layer_kind(layer_id: str) -> str:
    for prefix, kind in LAYER_KINDS:
        if layer_id.startswith(prefix):
            return kind
    return "layer"


def _layer_title(layer_id: str) -> str:
    return layer_id.removeprefix("display_").replace("_", " ")


class GatewayRunner:
    """Runs explorations on the ML service gateway (Modal) with the backend's scene plan."""

    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def submit(self, job: RunnerJob) -> RunnerTicket:
        body = self._body(job=job)
        response = await self._request("POST", JOBS_PATH, json=body)
        return self._ticket(payload=self._payload(response=response))

    async def poll(self, run_id: str) -> RunnerTicket:
        response = await self._request("GET", f"{JOBS_PATH}/{run_id}")
        return self._ticket(payload=self._payload(response=response))

    def _body(self, job: RunnerJob) -> dict[str, Any]:
        aoi = job.plan.aoi
        longitude, latitude = aoi_center(aoi=aoi)
        pixels, _ = window_pixels(aoi=aoi)
        body: dict[str, Any] = {
            "operation": "explore",
            "longitude": round(longitude, 5),
            "latitude": round(latitude, 5),
            "start_date": job.plan.window_start.date().isoformat(),
            "end_date": job.plan.window_end.date().isoformat(),
            "lens": job.lens.value,
            "scenes": [
                {"granule_id": scene.granule_id, "collection": _collection(scene)}
                for scene in job.plan.scenes
            ],
            "window_pixels": pixels,
            "aoi": aoi.geometry,
        }
        if job.optical_evidence:
            body["optical_evidence"] = True
        return body

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.request(method, self._base_url + path, **kwargs)
        except httpx.HTTPError as exc:
            logger.warning("ML gateway request failed", exc_info=True)
            raise RunnerUnavailableError("the analysis service did not answer") from exc
        if response.status_code in BUSY_STATUSES:
            raise QueueFullError("the analysis service is at capacity; retry shortly")
        return response

    @staticmethod
    def _payload(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
            if response.status_code == 404:
                return {"job_id": "", "status": "failed", "error": {"code": "job_not_found"}}
            if response.status_code >= 400 or "status" not in payload:
                raise ValueError(f"unexpected answer {response.status_code}")
        except ValueError as exc:
            logger.warning("ML gateway answered %s: %s", response.status_code, response.text[:300])
            raise RunnerUnavailableError("the analysis service answered unexpectedly") from exc
        return payload

    def _ticket(self, payload: dict[str, Any]) -> RunnerTicket:
        state = STATE_BY_GATEWAY_STATUS.get(payload["status"], RunnerState.FAILED)
        error = payload.get("error") or {}
        result = None
        if state is RunnerState.SUCCEEDED and payload.get("result"):
            result = self._result(payload["result"])
        return RunnerTicket(
            run_id=payload.get("job_id", ""),
            state=state,
            cached=payload.get("cache") == "hit",
            result=result,
            error_code=error.get("code") if state is RunnerState.FAILED else None,
        )

    def _result(self, result: dict[str, Any]) -> RunnerResult:
        science = result.get("science") or {}
        timings = {key: float(value) for key, value in (science.get("timings") or {}).items()}
        timings["elapsed_s"] = float(result.get("elapsed_seconds", 0.0))
        timings["render_s"] = float(result.get("visualization_seconds", 0.0))
        lens = science.get("lens")
        window = ((lens or {}).get("radar") or {}).get("grid") or {}
        return RunnerResult(
            science_status=str(result.get("science_status") or science.get("status") or "unknown"),
            lens=lens,
            observations=[self._observation(row) for row in science.get("observations") or []],
            aoi_summary=science.get("aoi_summary"),
            layers=[self._layer(layer) for layer in result.get("layers") or []],
            quality={
                "revision": result.get("revision"),
                "gridWidth": window.get("width"),
                "gridHeight": window.get("height"),
                "postingMeters": window.get("pixel_spacing_m"),
            },
            timings=timings,
        )

    @staticmethod
    def _observation(row: dict[str, Any]) -> dict[str, Any]:
        keys = ("date", "status", "reason", "granule_id")
        return {key: row[key] for key in keys if key in row}

    def _layer(self, layer: dict[str, Any]) -> RunnerLayer:
        identifier = str(layer["id"])
        value_range = layer.get("range")
        return RunnerLayer(
            id=identifier,
            title=_layer_title(identifier),
            kind=_layer_kind(identifier),
            units=str(layer.get("units", "")),
            colormap=str(layer.get("colormap", "")),
            bounds=tuple(layer["bounds"]),
            url=urljoin(self._base_url + "/", str(layer["png_url"]).lstrip("/")),
            legend=layer.get("legend"),
            value_range=tuple(value_range) if value_range else None,
        )
