from fastapi import FastAPI
from fastapi.testclient import TestClient

from nisar_hazard_watch.api.error_handlers import register_error_handlers
from nisar_hazard_watch.api.request_id_middleware import RequestIdMiddleware
from nisar_hazard_watch.constants.errors import PROBLEM_CONTENT_TYPE, ReasonCode
from nisar_hazard_watch.constants.routes import REQUEST_ID_HEADER
from nisar_hazard_watch.exceptions.app_error import AppError

TEAPOT_DETAIL = "No coffee here."
UNEXPECTED_MESSAGE = "secret internal detail"


class TeapotError(AppError):
    status_code = 418
    reason_code = ReasonCode.INVALID_REQUEST
    title = "I'm a teapot"


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    @app.get("/teapot")
    async def teapot() -> None:
        raise TeapotError(TEAPOT_DETAIL)

    @app.get("/items")
    async def items(limit: int) -> dict[str, int]:
        return {"limit": limit}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError(UNEXPECTED_MESSAGE)

    return TestClient(app, raise_server_exceptions=False)


def test_an_app_error_becomes_a_problem_with_its_own_reason_code() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.get("/teapot")

    # Assert
    body = response.json()
    assert response.status_code == 418
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    assert body["title"] == "I'm a teapot"
    assert body["detail"] == TEAPOT_DETAIL
    assert body["reasonCode"] == ReasonCode.INVALID_REQUEST
    assert body["requestId"] == response.headers[REQUEST_ID_HEADER]


def test_a_validation_error_names_the_offending_parameter() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.get("/items", params={"limit": "abc"})

    # Assert
    body = response.json()
    assert response.status_code == 422
    assert body["reasonCode"] == ReasonCode.INVALID_REQUEST
    assert "query.limit" in body["detail"]


def test_an_unknown_route_is_a_not_found_problem() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.get("/missing")

    # Assert
    assert response.status_code == 404
    assert response.json()["reasonCode"] == ReasonCode.NOT_FOUND


def test_a_wrong_method_is_a_method_not_allowed_problem() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.post("/teapot")

    # Assert
    assert response.status_code == 405
    assert response.json()["reasonCode"] == ReasonCode.METHOD_NOT_ALLOWED


def test_an_unexpected_error_hides_its_details_and_keeps_the_request_id() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.get("/boom")

    # Assert
    body = response.json()
    assert response.status_code == 500
    assert body["reasonCode"] == ReasonCode.INTERNAL_ERROR
    assert UNEXPECTED_MESSAGE not in response.text
    assert body["requestId"]
    assert response.headers[REQUEST_ID_HEADER] == body["requestId"]
