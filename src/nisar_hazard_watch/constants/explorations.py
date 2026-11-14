from enum import StrEnum


class Lens(StrEnum):
    FLOOD_WETLAND = "flood_wetland"
    VEGETATION_DISTURBANCE = "vegetation_disturbance"
    WILDFIRE = "wildfire"
    AGRICULTURE = "agriculture"
    INSAR = "insar"


OPTICAL_LENSES = frozenset({Lens.FLOOD_WETLAND, Lens.VEGETATION_DISTURBANCE, Lens.WILDFIRE})


class SourceBand(StrEnum):
    L_BAND = "L"
    S_BAND = "S"


class ExplorationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    NO_DATA = "noData"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_STATUSES = (ExplorationStatus.QUEUED, ExplorationStatus.RUNNING)


class Stage(StrEnum):
    PLANNING = "planning"
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"


class StageName(StrEnum):
    PLANNING = "planning"
    PROCESSING = "processing"
    READING = "reading"
    ANALYSING = "analysing"
    RENDERING = "rendering"


class StageState(StrEnum):
    DONE = "done"
    RUNNING = "running"
    PENDING = "pending"


class CacheState(StrEnum):
    MISS = "miss"
    HIT = "hit"


class RunnerKind(StrEnum):
    GATEWAY = "gateway"
    IN_PROCESS = "inProcess"


class RunnerState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TimingKey(StrEnum):
    PREFETCH = "prefetch_s"
    MEASURE = "measure_s"
    RENDER = "render_s"
    ELAPSED = "elapsed_s"
    TOTAL = "total_s"


class ScienceStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NO_DATA = "no_data"
    UNAVAILABLE = "unavailable"


class LayerKind(StrEnum):
    CHANGE = "change"
    DIAGNOSTIC = "diagnostic"
    OBSERVED = "observed"
    COHERENCE = "coherence"
    PHASE = "phase"
    GENERIC = "layer"


# Gateway layer-id prefixes and the kind each one is drawn as; the first match wins.
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


class GatewayStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class GatewayCache(StrEnum):
    HIT = "hit"


class GatewayErrorCode(StrEnum):
    JOB_NOT_FOUND = "job_not_found"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    WORKER_FAILED = "worker_failed"


GATEWAY_OPERATION = "explore"
REGIONAL_OPERATION = "analysis"
REGIONAL_ANALYSES = ("physical", "spectral", "stochastic")
REGIONAL_DEADLINE_SECONDS = 480
REGIONAL_MAX_DATES = 6
OBSERVED_STATUS = "observed"
GEOJSON_POINT = "Point"
ETA_TIMING_KEY = "etaSeconds"
QUALITY_MATURITY_MIXED = "maturityMixed"
QUALITY_WINDOW_TRUNCATED = "windowTruncated"
EXPLORATION_ID_PREFIX = "exp_"
BODY_LIMIT_BYTES = 16 * 1024
SCIENTIFIC_STATUS = "diagnostic"
NATIVE_PIXEL_SIDE_MIN = 64
NATIVE_PIXEL_SIDE_MAX = 1024
NATIVE_PIXEL_SIDE_MULTIPLE = 8
AREA_BUCKET_KM2_STEP = 100
ETA_SAMPLE_LIMIT = 50
ETA_PERCENTILE = 0.8
ETA_MIN_SAMPLES = 3
STAGE_BUDGETS_SECONDS = {
    StageName.PLANNING: 2.0,
    StageName.READING: 105.0,
    StageName.ANALYSING: 15.0,
    StageName.RENDERING: 15.0,
}
LIMITATIONS = (
    "Diagnostic evidence from measured L-band radar backscatter, not a validated classifier.",
    "Departures are measured against the scene's own observed baseline, which may include change.",
    "No forecast, probability, cause, area in hectares or displacement is reported.",
)
