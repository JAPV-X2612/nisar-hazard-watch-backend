from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.exceptions.app_error import AppError


class CaseNotFoundError(AppError):
    status_code = 404
    reason_code = ReasonCode.CASE_NOT_FOUND
    title = "Case not found"


class CaseLayerNotFoundError(AppError):
    status_code = 404
    reason_code = ReasonCode.NOT_FOUND
    title = "Case layer not found"


class CasesUnavailableError(AppError):
    status_code = 502
    reason_code = ReasonCode.CASES_UNAVAILABLE
    title = "Known cases unavailable"
