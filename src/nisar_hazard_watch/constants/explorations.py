from enum import StrEnum


class Lens(StrEnum):
    FLOOD_WETLAND = "flood_wetland"
    VEGETATION_DISTURBANCE = "vegetation_disturbance"
    WILDFIRE = "wildfire"
    AGRICULTURE = "agriculture"


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
    StageName.READING: 15.0,
    StageName.ANALYSING: 30.0,
    StageName.RENDERING: 8.0,
}
LIMITATIONS = (
    "Diagnostic evidence from measured L-band radar backscatter, not a validated classifier.",
    "Departures are measured against the scene's own observed baseline, which may include change.",
    "No forecast, probability, cause, area in hectares or displacement is reported.",
)
