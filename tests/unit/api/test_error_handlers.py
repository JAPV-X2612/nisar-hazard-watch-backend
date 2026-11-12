from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from nisar_hazard_watch.api.error_handlers import register_error_handlers
from nisar_hazard_watch.api.request_id_middleware import RequestIdMiddleware
from nisar_hazard_watch.constants.errors import PROBLEM_CONTENT_TYPE, ReasonCode
from nisar_hazard_watch.constants.headers import REQUEST_ID_HEADER
from nisar_hazard_watch.exceptions.app_error import AppError

TEAPOT_STATUS = 418
TEAPOT_DETAIL = "No coffee here."
INTERNAL_DETAIL = "secret internal detail"
UNEXPECTED_MESSAGE = "secret unexpected detail"
RETRY_AFTER_SECONDS = "30"


class TeapotError(AppError):
    status_code = TEAPOT_STATUS
    reason_code = ReasonCode.INVALID_REQUEST
    title = "I'm a teapot"


class BrokenDependencyError(AppError):
    title = "Dependency failed"


def _client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app=app)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/teapot")
    async def teapot() -> None:
        raise TeapotError(detail=TEAPOT_DETAIL)

    @app.get("/broken")
    async def broken() -> None:
        raise BrokenDependencyError(detail=INTERNAL_DETAIL)

    @app.get("/items")
    async def items(limit: int) -> dict[str, int]:
        return {"limit": limit}

    @app.get("/busy")
    async def busy() -> None:
        raise HTTPException(status_code=503, headers={"Retry-After": RETRY_AFTER_SECONDS})

    @app.get("/conflict")
    async def conflict() -> None:
        raise HTTPException(status_code=409, detail="Already exists")

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError(UNEXPECTED_MESSAGE)

    return TestClient(app, raise_server_exceptions=False)


def test_an_app_error_becomes_a_problem_with_its_own_reason_code() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.get(url="/teapot")

    # Assert
    body = response.json()
    assert response.status_code == TEAPOT_STATUS
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    assert body["title"] == "I'm a teapot"
    assert body["detail"] == TEAPOT_DETAIL
    assert body["reasonCode"] == ReasonCode.INVALID_REQUEST
    assert body["requestId"] == response.headers[REQUEST_ID_HEADER]


def test_a_server_side_app_error_hides_its_detail() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.get(url="/broken")

    # Assert
    assert response.status_code == 500
    assert INTERNAL_DETAIL not in response.text
    assert response.json()["reasonCode"] == ReasonCode.INTERNAL_ERROR


def test_a_validation_error_names_the_offending_parameter() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.get(url="/items", params={"limit": "abc"})

    # Assert
    body = response.json()
    assert response.status_code == 422
    assert body["reasonCode"] == ReasonCode.INVALID_REQUEST
    assert "query.limit" in body["detail"]


def test_an_unknown_route_is_a_not_found_problem() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.get(url="/missing")

    # Assert
    assert response.status_code == 404
    assert response.json()["reasonCode"] == ReasonCode.NOT_FOUND


def test_a_wrong_method_is_a_method_not_allowed_problem_that_keeps_the_allow_header() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.post(url="/teapot")

    # Assert
    assert response.status_code == 405
    assert response.json()["reasonCode"] == ReasonCode.METHOD_NOT_ALLOWED
    assert "GET" in response.headers["allow"]


def test_an_http_exception_keeps_its_headers_and_a_5xx_is_an_internal_error() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.get(url="/busy")

    # Assert
    assert response.status_code == 503
    assert response.headers["retry-after"] == RETRY_AFTER_SECONDS
    assert response.json()["reasonCode"] == ReasonCode.INTERNAL_ERROR


def test_an_other_client_error_is_an_invalid_request() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.get(url="/conflict")

    # Assert
    assert response.status_code == 409
    assert response.json()["reasonCode"] == ReasonCode.INVALID_REQUEST


def test_an_unexpected_error_hides_its_details_and_keeps_the_request_id() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.get(url="/boom")

    # Assert
    body = response.json()
    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    assert body["reasonCode"] == ReasonCode.INTERNAL_ERROR
    assert UNEXPECTED_MESSAGE not in response.text
    assert body["requestId"]
    assert response.headers[REQUEST_ID_HEADER] == body["requestId"]
