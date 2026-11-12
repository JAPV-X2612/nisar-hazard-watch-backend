import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nisar_hazard_watch.api.request_id_middleware import RequestIdMiddleware
from nisar_hazard_watch.constants.routes import REQUEST_ID_HEADER
from nisar_hazard_watch.utils.request_context import request_id_var

VALID_INCOMING_ID = "client-supplied_id-42"
INVALID_INCOMING_ID = "bad id with spaces and <tags>"
GENERATED_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ping")
    async def ping() -> dict[str, str | None]:
        return {"requestId": request_id_var.get()}

    return TestClient(app)


def test_a_request_id_is_generated_when_the_client_sends_none() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.get("/ping")

    # Assert
    header = response.headers[REQUEST_ID_HEADER]
    assert GENERATED_ID_PATTERN.match(header)
    assert response.json() == {"requestId": header}


def test_a_valid_incoming_request_id_is_kept() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.get("/ping", headers={REQUEST_ID_HEADER: VALID_INCOMING_ID})

    # Assert
    assert response.headers[REQUEST_ID_HEADER] == VALID_INCOMING_ID
    assert response.json() == {"requestId": VALID_INCOMING_ID}


def test_an_unsafe_incoming_request_id_is_replaced() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.get("/ping", headers={REQUEST_ID_HEADER: INVALID_INCOMING_ID})

    # Assert
    assert GENERATED_ID_PATTERN.match(response.headers[REQUEST_ID_HEADER])
