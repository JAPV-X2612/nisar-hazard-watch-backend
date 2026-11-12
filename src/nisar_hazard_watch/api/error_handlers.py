import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from nisar_hazard_watch.api.unexpected_error_middleware import UnexpectedErrorMiddleware
from nisar_hazard_watch.constants.errors import PROBLEM_CONTENT_TYPE, ReasonCode
from nisar_hazard_watch.exceptions.app_error import AppError
from nisar_hazard_watch.models.problem_details import ProblemDetails

logger = logging.getLogger(__name__)

HTTP_STATUS_REASONS: dict[int, ReasonCode] = {
    HTTPStatus.NOT_FOUND: ReasonCode.NOT_FOUND,
    HTTPStatus.METHOD_NOT_ALLOWED: ReasonCode.METHOD_NOT_ALLOWED,
}
UNEXPECTED_ERROR_DETAIL = "An unexpected error occurred."


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _is_server_error(status_code: int) -> bool:
    return status_code >= HTTPStatus.INTERNAL_SERVER_ERROR


def problem_response(
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
        request_id=_request_id(request=request),
    )
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(mode="json", exclude_none=True),
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    detail = exc.detail
    if _is_server_error(status_code=exc.status_code):
        logger.error(
            "application error", exc_info=exc, extra={"request_id": _request_id(request=request)}
        )
        detail = UNEXPECTED_ERROR_DETAIL
    return problem_response(
        request=request,
        status_code=exc.status_code,
        reason_code=exc.reason_code,
        title=exc.title,
        detail=detail,
    )


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()
    )
    return problem_response(
        request=request,
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        reason_code=ReasonCode.INVALID_REQUEST,
        title="Invalid request",
        detail=detail,
    )


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if _is_server_error(status_code=exc.status_code):
        logger.error("http error", exc_info=exc, extra={"request_id": _request_id(request=request)})
        reason_code = ReasonCode.INTERNAL_ERROR
    else:
        reason_code = HTTP_STATUS_REASONS.get(exc.status_code, ReasonCode.INVALID_REQUEST)
    return problem_response(
        request=request,
        status_code=exc.status_code,
        reason_code=reason_code,
        title=str(exc.detail),
        detail=str(exc.detail),
        headers=dict(exc.headers) if exc.headers else None,
    )


def unexpected_error_response(request: Request, exc: Exception) -> JSONResponse:
    # Read the id from request.state: the context variable is reset by the time this runs.
    logger.error(
        "unhandled error", exc_info=exc, extra={"request_id": _request_id(request=request)}
    )
    return problem_response(
        request=request,
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        reason_code=ReasonCode.INTERNAL_ERROR,
        title="Internal Server Error",
        detail=UNEXPECTED_ERROR_DETAIL,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Add this first: the middleware must sit inside CORS so 500 responses get CORS headers."""
    app.add_middleware(UnexpectedErrorMiddleware, responder=unexpected_error_response)
    app.exception_handler(AppError)(handle_app_error)
    app.exception_handler(RequestValidationError)(handle_validation_error)
    app.exception_handler(StarletteHTTPException)(handle_http_exception)
