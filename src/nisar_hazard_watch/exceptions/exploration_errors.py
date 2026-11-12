from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.exceptions.app_error import AppError


class SourceNotAvailableError(AppError):
    status_code = 422
    reason_code = ReasonCode.SOURCE_NOT_AVAILABLE
    title = "Source not available"


class ExplorationNotFoundError(AppError):
    status_code = 404
    reason_code = ReasonCode.NOT_FOUND
    title = "Exploration not found"


class QueueFullError(AppError):
    status_code = 503
    reason_code = ReasonCode.QUEUE_FULL
    title = "Analysis capacity is full"


class RateLimitedError(AppError):
    status_code = 429
    reason_code = ReasonCode.RATE_LIMITED
    title = "Too many requests"


class PayloadTooLargeError(AppError):
    status_code = 413
    reason_code = ReasonCode.PAYLOAD_TOO_LARGE
    title = "Request body too large"


class RunnerUnavailableError(AppError):
    status_code = 502
    reason_code = ReasonCode.UPSTREAM_ML_ERROR
    title = "Analysis service unavailable"
