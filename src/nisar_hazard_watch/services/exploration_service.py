import hashlib
import json
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.constants.explorations import (
    ACTIVE_STATUSES,
    AREA_BUCKET_KM2_STEP,
    ETA_TIMING_KEY,
    EXPLORATION_ID_PREFIX,
    GEOJSON_POINT,
    LIMITATIONS,
    OBSERVED_STATUS,
    QUALITY_MATURITY_MIXED,
    QUALITY_WINDOW_TRUNCATED,
    SCIENTIFIC_STATUS,
    STAGE_BUDGETS_SECONDS,
    CacheState,
    ExplorationStatus,
    GatewayErrorCode,
    Lens,
    RunnerState,
    ScienceStatus,
    SourceBand,
    Stage,
    StageName,
    StageState,
    TimingKey,
)
from nisar_hazard_watch.constants.fire_context import WILDFIRE_LIMITATION, FireContextStatus
from nisar_hazard_watch.constants.insar import (
    INSAR_FAILURE_DETAILS,
    INSAR_LIMITATIONS,
    INSAR_NO_DATA_DETAIL,
    INSAR_SCENES,
    INSAR_WINDOW_KM,
    INSAR_WINDOW_LIMITATION,
)
from nisar_hazard_watch.constants.routes import API_PREFIX, EXPLORATIONS_PREFIX
from nisar_hazard_watch.constants.sar import PlanStatus
from nisar_hazard_watch.exceptions.catalog_errors import CatalogUnavailableError
from nisar_hazard_watch.exceptions.exploration_errors import (
    ExplorationNotFoundError,
    QueueFullError,
    RunnerUnavailableError,
    SourceNotAvailableError,
)
from nisar_hazard_watch.exceptions.geometry_errors import InvalidGeometryError
from nisar_hazard_watch.models.exploration import (
    CoverageView,
    ExplorationRequest,
    ExplorationResult,
    ExplorationScene,
    ExplorationView,
    Layer,
    PlanSummary,
    ProblemInfo,
    Progress,
    StageTiming,
)
from nisar_hazard_watch.models.geometry import Aoi
from nisar_hazard_watch.models.scene import ScenePlan
from nisar_hazard_watch.ports.analysis_runner import (
    AnalysisRunner,
    InsarSelection,
    RunnerJob,
    RunnerResult,
    RunnerTicket,
)
from nisar_hazard_watch.ports.fire_context_provider import FireContextProvider
from nisar_hazard_watch.ports.job_repository import ExplorationJob, JobRepository
from nisar_hazard_watch.ports.precomputed_cases import PrecomputedCases
from nisar_hazard_watch.services.eta_estimator import EtaEstimator
from nisar_hazard_watch.services.scene_planner import ScenePlanner
from nisar_hazard_watch.utils.geometry import (
    aoi_center,
    aoi_from_geojson,
    aoi_from_point,
    window_pixels,
)
from nisar_hazard_watch.utils.gunw import pair_dates

logger = logging.getLogger(__name__)

SCIENCE_STATUS_TO_STATUS = {
    ScienceStatus.COMPLETE.value: ExplorationStatus.SUCCEEDED,
    ScienceStatus.PARTIAL.value: ExplorationStatus.PARTIAL,
    ScienceStatus.NO_DATA.value: ExplorationStatus.NO_DATA,
}
FAILURE_DETAILS = {
    GatewayErrorCode.DEADLINE_EXCEEDED.value: "the analysis service ran out of time",
    GatewayErrorCode.JOB_NOT_FOUND.value: "the analysis service lost the job",
}
UNKNOWN_FAILURE_DETAIL = "the analysis could not produce a result"
EMPTY_RESULT_DETAIL = "the analysis service reported success without a result"
WINDOW_LIMITATION = (
    "The analysed window is limited to about 10 km around the centre of the area; cells beyond "
    "it are not measured."
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ExplorationService:
    def __init__(
        self,
        planner: ScenePlanner,
        runner: AnalysisRunner,
        repository: JobRepository,
        eta: EtaEstimator,
        cases: PrecomputedCases,
        max_active: int,
        deadline_seconds: float,
        cache_ttl_seconds: float,
        fire_context: FireContextProvider | None = None,
        clock: Callable[[], datetime] = _utc_now,
        timer: Callable[[], float] = time.monotonic,
    ) -> None:
        self._planner = planner
        self._runner = runner
        self._repository = repository
        self._eta = eta
        self._cases = cases
        self._max_active = max_active
        self._deadline_seconds = deadline_seconds
        self._cache_ttl_seconds = cache_ttl_seconds
        self._fire_context = fire_context
        self._clock = clock
        self._timer = timer

    async def create(self, request: ExplorationRequest) -> tuple[ExplorationView, bool]:
        """Return the exploration and whether it is already final (cache hit or nothing to run)."""
        if request.source is SourceBand.S_BAND:
            raise SourceNotAvailableError(
                "S-band is coming as a precomputed layer for a short list of areas; "
                "this release serves L-band only"
            )
        aoi = self._aoi(geometry=request.geometry)
        started = self._timer()
        plan = (
            self._insar_plan(aoi=aoi, request=request)
            if request.lens is Lens.INSAR
            else await self._plan(aoi=aoi, request=request)
        )
        plan_seconds = round(self._timer() - started, 2)
        now = self._clock()
        scenes_total = INSAR_SCENES if request.lens is Lens.INSAR else len(plan.scenes)
        bucket = self._area_bucket(aoi=aoi)
        if plan.status is not PlanStatus.READY:
            job = self._unrunnable_job(
                request=request, plan=plan, bucket=bucket, plan_seconds=plan_seconds, now=now
            )
            await self._repository.add(job=job)
            return await self._view(job=job), True

        cache_key = self._cache_key(request=request, plan=plan)
        fresh = await self._repository.find_fresh(
            cache_key=cache_key, newer_than=now - timedelta(seconds=self._cache_ttl_seconds)
        )
        if fresh is not None:
            fresh = await self._with_fire_context(job=fresh)
            return await self._view(job=fresh, cache=CacheState.HIT), True
        await self._repository.expire_overdue(now=now, error=self._timeout_error())
        await self._require_capacity(
            request=request, scenes_total=scenes_total, bucket=bucket, now=now
        )

        ticket = await self._runner.submit(
            job=RunnerJob(
                lens=request.lens,
                plan=plan,
                optical_evidence=request.optical_evidence,
                pair=self._pair(request=request),
            )
        )
        eta = await self._eta.estimate(
            lens=request.lens, scenes_total=scenes_total, area_bucket=bucket
        )
        job = ExplorationJob(
            id=EXPLORATION_ID_PREFIX + uuid.uuid4().hex[:16],
            status=ExplorationStatus.QUEUED,
            stage=Stage.QUEUED,
            lens=request.lens,
            source=request.source,
            optical_evidence=request.optical_evidence,
            cache_key=cache_key,
            area_bucket=bucket,
            scenes_total=scenes_total,
            plan_seconds=plan_seconds,
            plan=plan,
            timings={ETA_TIMING_KEY: eta},
            created_at=now,
            deadline_at=now + timedelta(seconds=self._deadline_seconds),
        )
        job = await self._with_fire_context(job=self._apply(job=job, ticket=ticket, now=now))
        await self._repository.add(job=job)
        return await self._view(job=job), job.status not in ACTIVE_STATUSES

    async def get(self, exploration_id: str) -> ExplorationView:
        job = await self._load(exploration_id=exploration_id)
        now = self._clock()
        if job.status in ACTIVE_STATUSES and job.runner_id:
            job = await self._refresh(job=job, now=now)
        return await self._view(job=job)

    async def cancel(self, exploration_id: str) -> ExplorationView:
        job = await self._load(exploration_id=exploration_id)
        if job.status in ACTIVE_STATUSES:
            cancelled = job.model_copy(
                update={
                    "status": ExplorationStatus.CANCELLED,
                    "stage": Stage.DONE,
                    "finished_at": self._clock(),
                    "error": ProblemInfo(
                        reason_code=ReasonCode.CANCELLED, detail="the exploration was cancelled"
                    ),
                }
            )
            saved = await self._repository.transition(job=cancelled)
            job = cancelled if saved else await self._load(exploration_id=exploration_id)
        return await self._view(job=job)

    async def layer_url(self, exploration_id: str, layer_id: str) -> str:
        job = await self._load(exploration_id=exploration_id)
        url = job.layer_urls.get(layer_id)
        if url is None:
            raise ExplorationNotFoundError(f"the exploration has no layer {layer_id!r}")
        return url

    async def coverage(self, geometry: dict[str, Any]) -> CoverageView:
        aoi = self._aoi(geometry=geometry)
        plan = await self._planner.plan(aoi=aoi)
        longitude, latitude = aoi_center(aoi=aoi)
        case = next(
            (
                found.id
                for lens in Lens
                if (found := self._cases.find(longitude=longitude, latitude=latitude, lens=lens))
            ),
            None,
        )
        return CoverageView(
            plan=self._plan_summary(plan=plan),
            area_km2=aoi.area_km2,
            warnings=aoi.warnings,
            precomputed_case=case,
        )

    @staticmethod
    def _aoi(geometry: dict[str, Any]) -> Aoi:
        if isinstance(geometry, dict) and geometry.get("type") == GEOJSON_POINT:
            coordinates = geometry.get("coordinates")
            if not isinstance(coordinates, list) or len(coordinates) != 2:
                raise InvalidGeometryError("a Point needs [longitude, latitude]")
            try:
                longitude, latitude = (float(value) for value in coordinates)
            except (TypeError, ValueError):
                raise InvalidGeometryError("point coordinates must be numbers") from None
            return aoi_from_point(lon=longitude, lat=latitude)
        return aoi_from_geojson(geometry=geometry)

    @staticmethod
    def _insar_plan(aoi: Aoi, request: ExplorationRequest) -> ScenePlan:
        """An InSAR pair needs no GCOV plan: the pair's own two days are the window."""
        assert request.pair_id is not None
        reference, secondary = pair_dates(pair_id=request.pair_id)
        return ScenePlan(
            status=PlanStatus.READY,
            aoi=aoi,
            window_start=datetime.combine(reference, datetime.min.time(), tzinfo=UTC),
            window_end=datetime.combine(secondary, datetime.min.time(), tzinfo=UTC),
        )

    @staticmethod
    def _pair(request: ExplorationRequest) -> InsarSelection | None:
        if request.pair_id is None or request.coherence_threshold is None:
            return None
        return InsarSelection(
            pair_id=request.pair_id, coherence_threshold=request.coherence_threshold
        )

    async def _plan(self, aoi: Aoi, request: ExplorationRequest) -> ScenePlan:
        try:
            return await self._planner.plan(aoi=aoi)
        except CatalogUnavailableError as exc:
            longitude, latitude = aoi_center(aoi=aoi)
            case = self._cases.find(longitude=longitude, latitude=latitude, lens=request.lens)
            if case is None:
                raise
            raise CatalogUnavailableError(
                f"{exc.detail}; the precomputed case {case.id!r} ({case.title}) is available"
            ) from exc

    async def _require_capacity(
        self, request: ExplorationRequest, scenes_total: int, bucket: str, now: datetime
    ) -> None:
        active = await self._repository.count_active(now=now)
        if active >= self._max_active:
            eta = await self._eta.estimate(
                lens=request.lens, scenes_total=scenes_total, area_bucket=bucket
            )
            raise QueueFullError(
                f"{active} explorations are running (queue depth {active}); "
                f"retry in about {eta:.0f} seconds"
            )

    def _unrunnable_job(
        self,
        request: ExplorationRequest,
        plan: ScenePlan,
        bucket: str,
        plan_seconds: float,
        now: datetime,
    ) -> ExplorationJob:
        reason = (
            ReasonCode.NO_COVERAGE
            if plan.status is PlanStatus.NO_COVERAGE
            else ReasonCode.INSUFFICIENT_HISTORY
        )
        return ExplorationJob(
            id=EXPLORATION_ID_PREFIX + uuid.uuid4().hex[:16],
            status=ExplorationStatus.NO_DATA,
            stage=Stage.DONE,
            lens=request.lens,
            source=request.source,
            optical_evidence=request.optical_evidence,
            cache_key=self._cache_key(request=request, plan=plan),
            area_bucket=bucket,
            scenes_total=len(plan.scenes),
            plan_seconds=plan_seconds,
            plan=plan,
            error=ProblemInfo(reason_code=reason, detail="; ".join(plan.notes)),
            created_at=now,
            finished_at=now,
            deadline_at=now,
        )

    async def _load(self, exploration_id: str) -> ExplorationJob:
        job = await self._repository.get(job_id=exploration_id)
        if job is None:
            raise ExplorationNotFoundError(f"unknown exploration {exploration_id!r}")
        return job

    async def _refresh(self, job: ExplorationJob, now: datetime) -> ExplorationJob:
        assert job.runner_id is not None
        try:
            ticket = await self._runner.poll(run_id=job.runner_id)
        except (RunnerUnavailableError, QueueFullError):
            logger.warning("polling %s failed; keeping its last state", job.id, exc_info=True)
            ticket = None
        updated = self._apply(job=job, ticket=ticket, now=now) if ticket else job
        updated = await self._with_fire_context(job=updated)
        if updated.status in ACTIVE_STATUSES and now > updated.deadline_at:
            updated = updated.model_copy(
                update={
                    "status": ExplorationStatus.PARTIAL,
                    "stage": Stage.DONE,
                    "finished_at": now,
                    "error": self._timeout_error(),
                }
            )
        if updated == job:
            return job
        if await self._repository.transition(job=updated):
            return updated
        return await self._load(exploration_id=job.id)

    async def _with_fire_context(self, job: ExplorationJob) -> ExplorationJob:
        """Wildfire answers carry independent fire evidence next to the radar, never inside it."""
        result = job.result
        if self._fire_context is None or job.lens is not Lens.WILDFIRE or result is None:
            return job
        if job.plan is None:
            return job
        known = result.fire_context
        if known is not None and known.status is FireContextStatus.AVAILABLE:
            return job
        context = await self._fire_context.fire_context(plan=job.plan)
        return job.model_copy(
            update={"result": result.model_copy(update={"fire_context": context})}
        )

    def _timeout_error(self) -> ProblemInfo:
        return ProblemInfo(
            reason_code=ReasonCode.TIMEOUT_PARTIAL,
            detail=(
                f"the analysis did not finish within {self._deadline_seconds:.0f} s; "
                "the planned scenes are listed"
            ),
        )

    def _apply(self, job: ExplorationJob, ticket: RunnerTicket, now: datetime) -> ExplorationJob:
        update: dict[str, Any] = {"runner_id": ticket.run_id}
        if ticket.state is RunnerState.QUEUED:
            update.update(status=ExplorationStatus.QUEUED, stage=Stage.QUEUED)
        elif ticket.state is RunnerState.RUNNING:
            update.update(status=ExplorationStatus.RUNNING, stage=Stage.PROCESSING)
        elif ticket.state is RunnerState.FAILED:
            code = ticket.error_code or GatewayErrorCode.WORKER_FAILED.value
            update.update(
                self._failed(detail=FAILURE_DETAILS.get(code, UNKNOWN_FAILURE_DETAIL), now=now)
            )
        elif ticket.result is not None:
            update.update(self._succeeded(job=job, result=ticket.result, now=now))
        else:
            update.update(self._failed(detail=EMPTY_RESULT_DETAIL, now=now))
        return job.model_copy(update=update)

    @staticmethod
    def _failed(detail: str, now: datetime) -> dict[str, Any]:
        return {
            "status": ExplorationStatus.FAILED,
            "stage": Stage.DONE,
            "finished_at": now,
            "error": ProblemInfo(reason_code=ReasonCode.ANALYSIS_FAILED, detail=detail),
        }

    def _succeeded(
        self, job: ExplorationJob, result: RunnerResult, now: datetime
    ) -> dict[str, Any]:
        assert job.plan is not None
        if result.science_status == ScienceStatus.UNAVAILABLE.value:
            reason = result.insar.reason if result.insar else None
            return self._failed(
                detail=INSAR_FAILURE_DETAILS.get(reason or "", UNKNOWN_FAILURE_DETAIL), now=now
            )
        status = SCIENCE_STATUS_TO_STATUS.get(result.science_status)
        if status is None:
            return self._failed(
                detail=f"the analysis service returned an unknown status {result.science_status!r}",
                now=now,
            )
        insar = job.lens is Lens.INSAR
        truncated = self._truncated(aoi=job.plan.aoi, insar=insar)
        layers = [
            Layer(
                **layer.model_dump(exclude={"url"}),
                url=f"{API_PREFIX}{EXPLORATIONS_PREFIX}/{job.id}/layers/{layer.id}",
            )
            for layer in result.layers
        ]
        built = ExplorationResult(
            geometry=job.plan.aoi.geometry,
            area_km2=job.plan.aoi.area_km2,
            window_start=job.plan.window_start.date(),
            window_end=job.plan.window_end.date(),
            scenes=[
                ExplorationScene.model_validate(
                    scene.model_dump(exclude={"url", "code", "polarizations", "cycle"})
                )
                for scene in job.plan.scenes
            ],
            observations=result.observations,
            lens=result.lens,
            aoi_summary=result.aoi_summary,
            layers=layers,
            quality={
                **result.quality,
                QUALITY_MATURITY_MIXED: job.plan.maturity_mixed,
                QUALITY_WINDOW_TRUNCATED: truncated,
            },
            limitations=[
                *(INSAR_LIMITATIONS if insar else LIMITATIONS),
                *([WILDFIRE_LIMITATION] if job.lens is Lens.WILDFIRE else []),
                *([INSAR_WINDOW_LIMITATION if insar else WINDOW_LIMITATION] if truncated else []),
            ],
            scientific_status=SCIENTIFIC_STATUS,
            timings=result.timings,
            is_demo=result.is_demo,
            insar=result.insar,
        )
        update: dict[str, Any] = {
            "status": status,
            "stage": Stage.DONE,
            "finished_at": now,
            "result": built,
            "layer_urls": {layer.id: layer.url for layer in result.layers},
            "timings": {**job.timings, **result.timings},
        }
        if status is ExplorationStatus.NO_DATA:
            update["error"] = ProblemInfo(
                reason_code=ReasonCode.NO_COVERAGE,
                detail=(
                    INSAR_NO_DATA_DETAIL
                    if insar
                    else "the planned scenes held no usable measurements"
                ),
            )
        return update

    async def _view(
        self, job: ExplorationJob, cache: CacheState = CacheState.MISS
    ) -> ExplorationView:
        now = self._clock()
        end = job.finished_at or now
        elapsed = max(0.0, (end - job.created_at).total_seconds())
        active = job.status in ACTIVE_STATUSES
        eta = job.timings.get(ETA_TIMING_KEY)
        return ExplorationView(
            id=job.id,
            status=job.status,
            stage=job.stage,
            lens=job.lens,
            source=job.source,
            cache=cache,
            eta_seconds=eta,
            eta_remaining_seconds=max(0.0, round(eta - elapsed, 1)) if active and eta else None,
            elapsed_seconds=round(elapsed, 1),
            stages=self._stages(job=job),
            progress=self._progress(job=job),
            plan=self._plan_summary(plan=job.plan) if job.plan else None,
            result=job.result,
            error=job.error,
        )

    def _stages(self, job: ExplorationJob) -> list[StageTiming]:
        stages = [
            StageTiming(
                name=StageName.PLANNING,
                state=StageState.DONE,
                seconds=job.plan_seconds,
                budget_seconds=STAGE_BUDGETS_SECONDS[StageName.PLANNING],
            )
        ]
        if job.status in ACTIVE_STATUSES:
            stages.append(StageTiming(name=StageName.PROCESSING, state=StageState.RUNNING))
        elif job.result is not None:
            timings = job.result.timings
            reading = timings.get(TimingKey.PREFETCH.value)
            analysing = timings.get(TimingKey.MEASURE.value)
            rendering = timings.get(TimingKey.RENDER.value)
            for name, seconds in (
                (StageName.READING, reading),
                (StageName.ANALYSING, analysing),
                (StageName.RENDERING, rendering),
            ):
                stages.append(
                    StageTiming(
                        name=name,
                        state=StageState.DONE,
                        seconds=seconds,
                        budget_seconds=STAGE_BUDGETS_SECONDS[name],
                    )
                )
        return stages

    @staticmethod
    def _progress(job: ExplorationJob) -> Progress:
        read = None
        if job.result is not None:
            read = sum(1 for row in job.result.observations if row.get("status") == OBSERVED_STATUS)
        return Progress(scenes_read=read, scenes_total=job.scenes_total)

    @staticmethod
    def _plan_summary(plan: ScenePlan) -> PlanSummary:
        return PlanSummary(
            status=plan.status,
            series_key=plan.group.series_key if plan.group else None,
            dates=[scene.acquired_at.date() for scene in plan.scenes],
            maturity_mixed=plan.maturity_mixed,
            notes=plan.notes,
        )

    @staticmethod
    def _truncated(aoi: Aoi, insar: bool) -> bool:
        if insar:
            return aoi.area_km2 > INSAR_WINDOW_KM**2
        return window_pixels(aoi=aoi)[1]

    @staticmethod
    def _area_bucket(aoi: Aoi) -> str:
        top = (int(aoi.area_km2 // AREA_BUCKET_KM2_STEP) + 1) * AREA_BUCKET_KM2_STEP
        return f"<={top}"

    @staticmethod
    def _cache_key(request: ExplorationRequest, plan: ScenePlan) -> str:
        identity = {
            "version": 1,
            "lens": request.lens.value,
            "optical": request.optical_evidence,
            "area": plan.aoi.wkt,
            "windowEnd": plan.window_end.date().isoformat(),
            "granules": sorted(scene.granule_id for scene in plan.scenes),
        }
        if request.lens is Lens.INSAR:
            identity |= {"pair": request.pair_id, "coherence": request.coherence_threshold}
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()
