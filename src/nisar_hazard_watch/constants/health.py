from enum import StrEnum


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class DependencyName(StrEnum):
    DATABASE = "database"
    CMR = "cmr"
    MODAL = "modal"
    EARTHDATA_TOKEN = "earthdataToken"


class DependencyState(StrEnum):
    OK = "ok"
    DOWN = "down"
    CONFIGURED = "configured"
    NOT_CONFIGURED = "notConfigured"
