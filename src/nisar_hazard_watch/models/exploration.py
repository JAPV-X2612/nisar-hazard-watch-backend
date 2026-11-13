from datetime import date, datetime
from typing import Any, Self

from pydantic import ConfigDict, Field, model_validator

from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.constants.explorations import (
    CacheState,
    ExplorationStatus,
    Lens,
    SourceBand,
    Stage,
    StageName,
    StageState,
)
from nisar_hazard_watch.constants.insar import (
    DEFAULT_COHERENCE_THRESHOLD,
    GUNW_NAME_PATTERN,
    MAX_COHERENCE_THRESHOLD,
    MIN_COHERENCE_THRESHOLD,
)
from nisar_hazard_watch.constants.sar import Configuration, Direction, Maturity, PlanStatus
from nisar_hazard_watch.models.base_model import CamelModel
from nisar_hazard_watch.models.fire_context import FireContext
from nisar_hazard_watch.models.insar_summary import InsarSummary


class ExplorationRequest(CamelModel):
    model_config = ConfigDict(extra="forbid")

    lens: Lens
    geometry: dict[str, Any]
    source: SourceBand = SourceBand.L_BAND
    optical_evidence: bool = False
    pair_id: str | None = Field(default=None, pattern=GUNW_NAME_PATTERN)
    coherence_threshold: float | None = Field(
        default=None, ge=MIN_COHERENCE_THRESHOLD, le=MAX_COHERENCE_THRESHOLD, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def _pair_belongs_to_the_insar_lens(self) -> Self:
        if self.lens is Lens.INSAR:
            if self.pair_id is None:
                raise ValueError("the insar lens needs a pairId from GET /api/v1/insar/pairs")
            if self.coherence_threshold is None:
                self.coherence_threshold = DEFAULT_COHERENCE_THRESHOLD
        elif self.pair_id is not None or self.coherence_threshold is not None:
            raise ValueError("pairId and coherenceThreshold apply to the insar lens only")
        return self


class StageTiming(CamelModel):
    name: StageName
    state: StageState
    seconds: float | None = None
    budget_seconds: float | None = None


class Progress(CamelModel):
    scenes_read: int | None = None
    scenes_total: int


class ProblemInfo(CamelModel):
    reason_code: ReasonCode
    detail: str


class ExplorationScene(CamelModel):
    granule_id: str
    acquired_at: datetime
    track: int
    direction: Direction
    frame: int
    mode: str
    maturity: Maturity
    configuration: Configuration
    crid: str
    version: int
    coverage: float


class Layer(CamelModel):
    id: str
    title: str
    kind: str
    units: str
    colormap: str
    bounds: tuple[float, float, float, float]
    url: str
    legend: dict[str, str] | None = None
    value_range: tuple[float, float] | None = None


class PlanSummary(CamelModel):
    status: PlanStatus
    series_key: str | None = None
    dates: list[date] = Field(default_factory=list)
    maturity_mixed: bool = False
    notes: list[str] = Field(default_factory=list)


class ExplorationResult(CamelModel):
    geometry: dict[str, Any]
    area_km2: float
    window_start: date
    window_end: date
    scenes: list[ExplorationScene]
    observations: list[dict[str, Any]]
    lens: dict[str, Any] | None
    aoi_summary: dict[str, Any] | None
    layers: list[Layer]
    quality: dict[str, Any]
    limitations: list[str]
    scientific_status: str
    timings: dict[str, float]
    is_demo: bool = False
    insar: InsarSummary | None = None
    fire_context: FireContext | None = None


class ExplorationView(CamelModel):
    id: str
    status: ExplorationStatus
    stage: Stage
    lens: Lens
    source: SourceBand
    cache: CacheState
    eta_seconds: float | None = None
    eta_remaining_seconds: float | None = None
    elapsed_seconds: float
    stages: list[StageTiming] = Field(default_factory=list)
    progress: Progress | None = None
    plan: PlanSummary | None = None
    result: ExplorationResult | None = None
    error: ProblemInfo | None = None


class CoverageView(CamelModel):
    plan: PlanSummary
    area_km2: float
    warnings: list[str] = Field(default_factory=list)
    precomputed_case: str | None = None


class LensInfo(CamelModel):
    id: Lens
    title: str
    description: str
    optical_evidence: bool
    minimum_dates: int
