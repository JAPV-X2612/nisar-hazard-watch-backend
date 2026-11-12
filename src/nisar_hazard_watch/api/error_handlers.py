import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from nisar_hazard_watch.constants.errors import PROBLEM_CONTENT_TYPE, ReasonCode
from nisar_hazard_watch.constants.routes import REQUEST_ID_HEADER
from nisar_hazard_watch.exceptions.app_error import AppError
from nisar_hazard_watch.models.problem_details import ProblemDetails

logger = logging.getLogger(__name__)

HTTP_STATUS_REASONS = {
    404: ReasonCode.NOT_FOUND,
    405: ReasonCode.METHOD_NOT_ALLOWED,
}
UNEXPECTED_ERROR_DETAIL = "An unexpected error occurred."


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _problem(
    request: Request,
    status_code: int,
    reason_code: ReasonCode,
    title: str,
    detail: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    problem = ProblemDetails(
        title=title,
        status=status_code,
        detail=detail,
        reason_code=reason_code,
        request_id=_request_id(request),
    )
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(mode="json", exclude_none=True),
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return _problem(request, exc.status_code, exc.reason_code, exc.title, exc.detail)


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    detail = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()
    )
    return _problem(request, 422, ReasonCode.INVALID_REQUEST, "Invalid request", detail)


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    reason_code = HTTP_STATUS_REASONS.get(exc.status_code, ReasonCode.INVALID_REQUEST)
    return _problem(request, exc.status_code, reason_code, str(exc.detail), str(exc.detail))


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.error("unhandled error", exc_info=exc, extra={"request_id": request_id})
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return _problem(
        request,
        500,
        ReasonCode.INTERNAL_ERROR,
        "Internal Server Error",
        UNEXPECTED_ERROR_DETAIL,
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)
