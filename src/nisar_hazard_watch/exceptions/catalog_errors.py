from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.exceptions.app_error import AppError


class CatalogUnavailableError(AppError):
    status_code = 502
    reason_code = ReasonCode.UPSTREAM_CATALOG_ERROR
    title = "Scene catalog unavailable"


class CatalogTruncatedError(AppError):
    status_code = 502
    reason_code = ReasonCode.UPSTREAM_CATALOG_ERROR
    title = "Scene catalog result is incomplete"
