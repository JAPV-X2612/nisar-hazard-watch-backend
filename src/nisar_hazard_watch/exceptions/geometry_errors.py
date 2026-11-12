from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.exceptions.app_error import AppError


class InvalidGeometryError(AppError):
    status_code = 422
    reason_code = ReasonCode.INVALID_GEOMETRY
    title = "Invalid geometry"


class AreaTooLargeError(AppError):
    status_code = 422
    reason_code = ReasonCode.AREA_TOO_LARGE
    title = "Area too large"
