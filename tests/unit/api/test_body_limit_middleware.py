from collections.abc import Iterator

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from nisar_hazard_watch.api.body_limit_middleware import BodyLimitMiddleware
from nisar_hazard_watch.api.request_id_middleware import RequestIdMiddleware
from nisar_hazard_watch.constants.errors import PROBLEM_CONTENT_TYPE, ReasonCode
from nisar_hazard_watch.constants.headers import REQUEST_ID_HEADER

MAX_BYTES = 100


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(BodyLimitMiddleware, max_bytes=MAX_BYTES)
    app.add_middleware(RequestIdMiddleware)

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        return {"bytes": len(await request.body())}

    return TestClient(app)


def _chunks(total: int) -> Iterator[bytes]:
    for _ in range(total // 10):
        yield b"x" * 10


def test_a_body_within_the_limit_passes() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.post(url="/echo", content=b"x" * MAX_BYTES)

    # Assert
    assert response.status_code == 200
    assert response.json() == {"bytes": MAX_BYTES}


def test_a_declared_length_over_the_limit_is_refused_as_a_problem() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.post(url="/echo", content=b"x" * (MAX_BYTES + 1))

    # Assert
    body = response.json()
    assert response.status_code == 413
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    assert body["reasonCode"] == ReasonCode.PAYLOAD_TOO_LARGE
    assert body["requestId"] == response.headers[REQUEST_ID_HEADER]


def test_a_streamed_body_over_the_limit_is_refused_too() -> None:
    # Arrange
    client = _client()

    # Act
    response = client.post(url="/echo", content=_chunks(total=MAX_BYTES * 3))

    # Assert
    assert response.status_code == 413
    assert response.json()["reasonCode"] == ReasonCode.PAYLOAD_TOO_LARGE
