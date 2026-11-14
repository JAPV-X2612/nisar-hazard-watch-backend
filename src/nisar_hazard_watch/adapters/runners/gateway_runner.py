import logging
from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from nisar_hazard_watch.constants.explorations import (
    GATEWAY_OPERATION,
    OBSERVED_STATUS,
    GatewayCache,
    GatewayErrorCode,
    GatewayStatus,
    Lens,
    RunnerState,
    ScienceStatus,
    TimingKey,
)
from nisar_hazard_watch.constants.insar import INSAR_OPERATION
from nisar_hazard_watch.constants.sar import Configuration, Maturity
from nisar_hazard_watch.exceptions.exploration_errors import QueueFullError, RunnerUnavailableError
from nisar_hazard_watch.exceptions.pair_errors import InvalidPairError
from nisar_hazard_watch.models.insar_summary import InsarSummary
from nisar_hazard_watch.models.scene import Scene
from nisar_hazard_watch.ports.analysis_runner import (
    RunnerJob,
    RunnerLayer,
    RunnerResult,
    RunnerTicket,
)
from nisar_hazard_watch.utils.gateway_layers import gateway_url, layer_kind, layer_title
from nisar_hazard_watch.utils.geometry import aoi_center, window_pixels
from nisar_hazard_watch.utils.gunw import pair_dates

logger = logging.getLogger(__name__)

JOBS_PATH = "/v2/jobs"
BUSY_STATUSES = (HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE)
UNEXPECTED_ANSWER = "the analysis service answered unexpectedly"
STATE_BY_GATEWAY_STATUS = {
    GatewayStatus.QUEUED.value: RunnerState.QUEUED,
    GatewayStatus.RUNNING.value: RunnerState.RUNNING,
    GatewayStatus.SUCCEEDED.value: RunnerState.SUCCEEDED,
    GatewayStatus.FAILED.value: RunnerState.FAILED,
}
COLLECTION_BY_MATURITY = {
    Maturity.PROVISIONAL: "PROVISIONAL",
    Maturity.VALIDATED: "VALIDATED",
    Maturity.BETA: "BETA",
}
URGENT_RESPONSE_COLLECTION = "UR"


def _collection(scene: Scene) -> str:
    if scene.configuration is Configuration.URGENT_RESPONSE:
        return URGENT_RESPONSE_COLLECTION
    return COLLECTION_BY_MATURITY[scene.maturity]


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
        response = await self._request("GET", f"{JOBS_PATH}/{quote(run_id, safe='')}")
        if response.status_code == HTTPStatus.NOT_FOUND:
            return RunnerTicket(
                run_id=run_id,
                state=RunnerState.FAILED,
                error_code=GatewayErrorCode.JOB_NOT_FOUND.value,
            )
        return self._ticket(payload=self._payload(response=response))

    def _body(self, job: RunnerJob) -> dict[str, Any]:
        aoi = job.plan.aoi
        longitude, latitude = aoi_center(aoi=aoi)
        if job.lens is Lens.INSAR and job.pair is not None:
            return {
                "operation": INSAR_OPERATION,
                "longitude": round(longitude, 5),
                "latitude": round(latitude, 5),
                "start_date": job.plan.window_start.date().isoformat(),
                "end_date": job.plan.window_end.date().isoformat(),
                "pair_id": job.pair.pair_id,
                "coherence_threshold": job.pair.coherence_threshold,
            }
        pixels, _ = window_pixels(aoi=aoi)
        body: dict[str, Any] = {
            "operation": GATEWAY_OPERATION,
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
        except ValueError as exc:
            raise GatewayRunner._unexpected(response=response) from exc
        if response.status_code >= HTTPStatus.BAD_REQUEST or not isinstance(payload, dict):
            raise GatewayRunner._unexpected(response=response)
        return payload

    @staticmethod
    def _unexpected(response: httpx.Response) -> RunnerUnavailableError:
        logger.warning("ML gateway answered %s: %s", response.status_code, response.text[:300])
        return RunnerUnavailableError(UNEXPECTED_ANSWER)

    def _ticket(self, payload: dict[str, Any]) -> RunnerTicket:
        try:
            return self._build_ticket(payload=payload)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("ML gateway answer could not be read", exc_info=True)
            raise RunnerUnavailableError(UNEXPECTED_ANSWER) from exc

    def _build_ticket(self, payload: dict[str, Any]) -> RunnerTicket:
        state = STATE_BY_GATEWAY_STATUS[payload["status"]]
        error = payload.get("error") or {}
        result = None
        if state is RunnerState.SUCCEEDED and payload.get("result"):
            result = self._result(payload["result"])
        return RunnerTicket(
            run_id=str(payload.get("job_id", "")),
            state=state,
            cached=payload.get("cache") == GatewayCache.HIT.value,
            result=result,
            error_code=error.get("code") if state is RunnerState.FAILED else None,
        )

    def _result(self, result: dict[str, Any]) -> RunnerResult:
        if result.get("operation") == INSAR_OPERATION:
            return self._insar_result(result)
        science = result.get("science") or {}
        timings = {key: float(value) for key, value in (science.get("timings") or {}).items()}
        timings[TimingKey.ELAPSED.value] = float(result.get("elapsed_seconds", 0.0))
        timings[TimingKey.RENDER.value] = float(result.get("visualization_seconds", 0.0))
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

    def _insar_result(self, result: dict[str, Any]) -> RunnerResult:
        science = result.get("science") or {}
        timings = {
            TimingKey.ELAPSED.value: float(result.get("elapsed_seconds", 0.0)),
            TimingKey.RENDER.value: float(result.get("visualization_seconds", 0.0)),
        }
        timings[TimingKey.MEASURE.value] = max(
            0.0, timings[TimingKey.ELAPSED.value] - timings[TimingKey.RENDER.value]
        )
        grid = science.get("grid") or {}
        spacing = grid.get("pixel_spacing_m") or [None]
        valid = science.get("valid_pixels") or {}
        point = science.get("point") or {}
        status = str(result.get("science_status") or science.get("status") or "unknown")
        measured = status in (ScienceStatus.COMPLETE.value, ScienceStatus.PARTIAL.value)
        return RunnerResult(
            science_status=status,
            lens=None,
            observations=self._pair_observations(science=science) if measured else [],
            aoi_summary=None,
            layers=[self._layer(layer) for layer in result.get("layers") or []],
            quality={
                "revision": result.get("revision"),
                "gridWidth": grid.get("width"),
                "gridHeight": grid.get("height"),
                "postingMeters": spacing[0],
            },
            timings=timings,
            insar=InsarSummary(
                pair_id=str(science.get("pair_id", "")),
                status=status,
                reason=science.get("reason"),
                polarization=science.get("polarization"),
                median_coherence=science.get("median_coherence"),
                coherence_threshold=float(science.get("coherence_threshold", 0.0)),
                coherent_cells=valid.get("coherence"),
                phase_cells=valid.get("wrapped_phase_rad"),
                window_cells=(grid["width"] * grid["height"]) if measured and grid else None,
                point_coherence=point.get("coherence"),
                point_wrapped_phase_rad=point.get("wrapped_phase_rad"),
                phase_reference=science.get("phase_reference"),
                corrections_applied=list(science.get("corrections_applied") or []),
            ),
        )

    @staticmethod
    def _pair_observations(science: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            days = pair_dates(pair_id=str(science["pair_id"]))
        except (KeyError, InvalidPairError):
            return []
        return [{"date": day.isoformat(), "status": OBSERVED_STATUS} for day in days]

    @staticmethod
    def _observation(row: dict[str, Any]) -> dict[str, Any]:
        keys = ("date", "status", "reason", "granule_id")
        return {key: row[key] for key in keys if key in row}

    def _layer(self, layer: dict[str, Any]) -> RunnerLayer:
        identifier = str(layer["id"])
        value_range = layer.get("range")
        return RunnerLayer(
            id=identifier,
            title=layer_title(identifier),
            kind=layer_kind(identifier),
            units=str(layer.get("units", "")),
            colormap=str(layer.get("colormap", "")),
            bounds=tuple(layer["bounds"]),
            url=gateway_url(base_url=self._base_url, path=str(layer["png_url"])),
            legend=layer.get("legend"),
            value_range=tuple(value_range) if value_range else None,
        )
