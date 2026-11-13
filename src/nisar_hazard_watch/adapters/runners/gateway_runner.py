import logging
import re
from http import HTTPStatus
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import httpx

from nisar_hazard_watch.constants.explorations import (
    GATEWAY_OPERATION,
    OBSERVED_STATUS,
    REGIONAL_ANALYSES,
    REGIONAL_OPERATION,
    GatewayCache,
    GatewayErrorCode,
    GatewayStatus,
    LayerKind,
    Lens,
    RunnerState,
    ScienceStatus,
    TimingKey,
)
from nisar_hazard_watch.constants.insar import INSAR_OPERATION, LAYER_TITLES
from nisar_hazard_watch.constants.sar import Configuration, Maturity
from nisar_hazard_watch.exceptions.exploration_errors import QueueFullError, RunnerUnavailableError
from nisar_hazard_watch.exceptions.pair_errors import InvalidPairError
from nisar_hazard_watch.models.insar_summary import InsarSummary
from nisar_hazard_watch.models.scene import Scene
from nisar_hazard_watch.models.science_products import (
    PublishedAsset,
    RadarVisualization,
    RegionalAnalysis,
    SciencePreview,
    ScienceProducts,
)
from nisar_hazard_watch.ports.analysis_runner import (
    RunnerJob,
    RunnerLayer,
    RunnerResult,
    RunnerTicket,
)
from nisar_hazard_watch.utils.geometry import aoi_center, window_pixels
from nisar_hazard_watch.utils.gunw import pair_dates

logger = logging.getLogger(__name__)

JOBS_PATH = "/v2/jobs"
ASSET_NAME = re.compile(r"[A-Za-z0-9._-]{1,180}")
OBSERVATION_LAYER = re.compile(r"display_(\d{4}-\d{2}-\d{2})_(?:[A-Z]+|\d+)")
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
LAYER_KINDS = (
    ("display_baseline_change", LayerKind.CHANGE),
    ("display_change_", LayerKind.CHANGE),
    ("display_flood_signature", LayerKind.DIAGNOSTIC),
    ("display_agriculture", LayerKind.DIAGNOSTIC),
    ("display_cross_pol_pattern", LayerKind.DIAGNOSTIC),
    ("display_cross_pol_decline_count", LayerKind.DIAGNOSTIC),
    ("display_coherence", LayerKind.COHERENCE),
    ("display_wrapped_phase", LayerKind.PHASE),
    ("display_optical", LayerKind.DIAGNOSTIC),
    ("display_", LayerKind.OBSERVED),
)


def _collection(scene: Scene) -> str:
    if scene.configuration is Configuration.URGENT_RESPONSE:
        return URGENT_RESPONSE_COLLECTION
    return COLLECTION_BY_MATURITY[scene.maturity]


def _layer_kind(layer_id: str) -> str:
    for prefix, kind in LAYER_KINDS:
        if layer_id.startswith(prefix):
            return kind.value
    return LayerKind.GENERIC.value


def _layer_title(layer_id: str) -> str:
    return LAYER_TITLES.get(layer_id) or layer_id.removeprefix("display_").replace("_", " ")


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
        if job.regional_analysis:
            assert job.plan.group is not None
            return {
                "operation": REGIONAL_OPERATION,
                "longitude": round(longitude, 5),
                "latitude": round(latitude, 5),
                "start_date": job.plan.window_start.date().isoformat(),
                "end_date": job.plan.window_end.date().isoformat(),
                "series_key": job.plan.group.series_key,
                "analyses": list(REGIONAL_ANALYSES),
            }
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
        run_id = str(payload.get("job_id", ""))
        if state is RunnerState.SUCCEEDED and payload.get("result"):
            result = self._result(payload["result"], run_id=run_id)
        return RunnerTicket(
            run_id=run_id,
            state=state,
            cached=payload.get("cache") == GatewayCache.HIT.value,
            result=result,
            error_code=error.get("code") if state is RunnerState.FAILED else None,
        )

    def _result(self, result: dict[str, Any], run_id: str) -> RunnerResult:
        products = self._products(result=result, run_id=run_id)
        if result.get("operation") == INSAR_OPERATION:
            return self._insar_result(result=result, products=products)
        science = result.get("science") or {}
        timings = {key: float(value) for key, value in (science.get("timings") or {}).items()}
        timings[TimingKey.ELAPSED.value] = float(result.get("elapsed_seconds", 0.0))
        timings[TimingKey.RENDER.value] = float(result.get("visualization_seconds", 0.0))
        lens = science.get("lens") or {}
        window = (lens.get("radar") or {}).get("grid") or {}
        comparison = science.get("comparison") or {}
        regional = products.analysis if products else None
        observations = [] if regional else science.get("observations") or []
        grids = {row["date"]: row.get("grid") for row in observations}
        layers = []
        for layer in result.get("layers") or []:
            identifier = layer["id"]
            date_match = OBSERVATION_LAYER.fullmatch(identifier)
            if date_match:
                day = date_match[1]
                layers.append(self._layer(layer, grid=grids.get(day), dates=[day]))
            elif identifier.startswith("display_change_"):
                layers.append(
                    self._layer(layer, grid=comparison.get("grid"), dates=comparison.get("dates"))
                )
            elif identifier.startswith("display_optical"):
                evidence = lens.get("evidence") or {}
                epochs = evidence.get("epochs") or {}
                dates = (
                    [
                        epoch["date"]
                        for epoch in epochs.values()
                        if isinstance(epoch, dict) and "date" in epoch
                    ]
                    if isinstance(epochs, dict)
                    else []
                )
                layers.append(self._layer(layer, grid=evidence.get("grid"), dates=dates))
            elif _layer_kind(identifier) in {LayerKind.CHANGE, LayerKind.DIAGNOSTIC} and not (
                identifier.startswith("display_optical") or regional
            ):
                dates = lens.get("assessment_dates")
                if identifier.startswith("display_baseline_change") and lens.get("target_date"):
                    dates = [lens["target_date"]]
                layers.append(self._layer(layer, grid=window or None, dates=dates))
            else:
                layers.append(self._layer(layer))
        return RunnerResult(
            science_status=str(result.get("science_status") or science.get("status") or "unknown"),
            lens=lens or None,
            observations=[self._observation(row) for row in observations],
            aoi_summary=science.get("aoi_summary"),
            layers=layers,
            quality={
                "revision": result.get("revision"),
                "gridWidth": window.get("width"),
                "gridHeight": window.get("height"),
                "postingMeters": window.get("pixel_spacing_m"),
                "measuredPoint": result.get("point"),
                "seriesKey": science.get("series_key"),
                "comparison": self._comparison(science.get("comparison")),
            },
            timings=timings,
            products=products,
        )

    def _insar_result(
        self, result: dict[str, Any], products: ScienceProducts | None
    ) -> RunnerResult:
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
        observations = self._pair_observations(science=science) if measured else []
        return RunnerResult(
            science_status=status,
            lens=None,
            observations=observations,
            aoi_summary=None,
            layers=[
                self._layer(layer, grid=grid or None, dates=[row["date"] for row in observations])
                for layer in result.get("layers") or []
            ],
            quality={
                "revision": result.get("revision"),
                "gridWidth": grid.get("width"),
                "gridHeight": grid.get("height"),
                "postingMeters": spacing[0],
                "measuredPoint": result.get("point"),
            },
            timings=timings,
            products=products,
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

    def _layer_url(self, path: str) -> str:
        url = urljoin(self._base_url + "/", path)
        if urlsplit(url)[:2] != urlsplit(self._base_url)[:2]:
            raise ValueError(f"layer URL {url!r} is not served by the analysis service")
        return url

    @staticmethod
    def _observation(row: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "date",
            "status",
            "reason",
            "granule_id",
            "granule_title",
            "sensing_start_utc",
            "grid",
            "point_db",
            "valid_pixel_count_by_pol",
        )
        return {key: row[key] for key in keys if key in row}

    @staticmethod
    def _comparison(comparison: dict[str, Any] | None) -> dict[str, Any] | None:
        if comparison is None:
            return None
        return {key: comparison[key] for key in ("status", "dates", "reason") if key in comparison}

    def _products(self, result: dict[str, Any], run_id: str) -> ScienceProducts | None:
        if not any(key in result for key in ("visualizations", "artifacts", "previews")) and (
            result.get("operation") != REGIONAL_OPERATION
        ):
            return None
        assets: dict[str, PublishedAsset] = {}
        for asset in result.get("artifacts") or []:
            name, href = asset["name"], asset["href"]
            if name in {".", ".."} or not ASSET_NAME.fullmatch(name):
                continue
            path = f"{JOBS_PATH}/{quote(run_id, safe='')}/layers/{name}"
            url = self._layer_url(path=href)
            if urlsplit(url).path != path or urlsplit(url).query or urlsplit(url).fragment:
                continue
            assets[href] = PublishedAsset(
                name=name,
                url=url,
                media_type=asset["media_type"],
                bytes=asset["bytes"],
                sha256=asset["sha256"],
            )
        visualizations = [
            RadarVisualization.model_validate(
                {
                    **view,
                    "png": assets[view["png_url"]].name,
                    "cog": assets[view["cog_url"]].name if view.get("cog_url") in assets else None,
                }
            )
            for view in result.get("visualizations") or []
            if view["png_url"] in assets
        ]
        previews = [
            SciencePreview.model_validate({**preview, "name": assets[preview["href"]].name})
            for preview in result.get("previews") or []
            if preview["href"] in assets
        ]
        regional = None
        if result.get("operation") == REGIONAL_OPERATION:
            science = result.get("science") or {}
            regional = RegionalAnalysis(
                point=result.get("point"),
                observations=science.get("observations") or {},
                capabilities=science.get("capabilities") or {},
                series=(science.get("dashboard") or {}).get("series") or {},
                limitations=science.get("limitations") or [],
            )
        return ScienceProducts(
            assets=list(assets.values()),
            visualizations=visualizations,
            previews=previews,
            analysis=regional,
        )

    def _layer(
        self,
        layer: dict[str, Any],
        grid: dict[str, Any] | None = None,
        dates: list[str] | None = None,
    ) -> RunnerLayer:
        identifier = str(layer["id"])
        value_range = layer.get("range")
        return RunnerLayer(
            id=identifier,
            title=_layer_title(identifier),
            kind=_layer_kind(identifier),
            units=str(layer.get("units", "")),
            colormap=str(layer.get("colormap", "")),
            bounds=tuple(layer["bounds"]),
            url=self._layer_url(path=str(layer["png_url"])),
            legend=layer.get("legend"),
            value_range=tuple(value_range) if value_range else None,
            crs=layer.get("crs"),
            grid=grid,
            dates=dates,
        )
