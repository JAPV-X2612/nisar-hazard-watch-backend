from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.exceptions.app_error import AppError


class InvalidQueryError(AppError):
    status_code = 422
    reason_code = ReasonCode.INVALID_QUERY
    title = "Invalid search"


class GeocoderUnavailableError(AppError):
    status_code = 502
    reason_code = ReasonCode.UPSTREAM_GEOCODER_ERROR
    title = "Place search unavailable"
