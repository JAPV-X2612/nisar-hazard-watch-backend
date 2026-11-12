import pytest
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import Message, Receive, Scope, Send

from nisar_hazard_watch.api.unexpected_error_middleware import UnexpectedErrorMiddleware

HTTP_SCOPE: Scope = {
    "type": "http",
    "method": "GET",
    "path": "/",
    "headers": [],
    "query_string": b"",
}
LIFESPAN_SCOPE: Scope = {"type": "lifespan"}
FAILURE_MESSAGE = "late failure"


async def _receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


class RecordingSend:
    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def __call__(self, message: Message) -> None:
        self.messages.append(message)


def _responder(request: Request, exc: Exception) -> Response:
    return PlainTextResponse(content=f"handled {exc}", status_code=500)


async def _fails_before_responding(scope: Scope, receive: Receive, send: Send) -> None:
    raise RuntimeError("early failure")


async def _fails_after_responding(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    raise RuntimeError(FAILURE_MESSAGE)


async def _succeeds(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def test_an_exception_before_the_response_becomes_the_responders_response() -> None:
    # Arrange
    middleware = UnexpectedErrorMiddleware(app=_fails_before_responding, responder=_responder)
    send = RecordingSend()

    # Act
    await middleware(HTTP_SCOPE, _receive, send)

    # Assert
    start = send.messages[0]
    assert start["type"] == "http.response.start"
    assert start["status"] == 500


async def test_an_exception_after_the_response_started_is_not_hidden() -> None:
    # Arrange
    middleware = UnexpectedErrorMiddleware(app=_fails_after_responding, responder=_responder)
    send = RecordingSend()

    # Act / Assert
    with pytest.raises(expected_exception=RuntimeError, match=FAILURE_MESSAGE):
        await middleware(HTTP_SCOPE, _receive, send)


async def test_successful_requests_and_other_scopes_pass_straight_through() -> None:
    # Arrange
    middleware = UnexpectedErrorMiddleware(app=_succeeds, responder=_responder)
    http_send = RecordingSend()
    lifespan_send = RecordingSend()

    # Act
    await middleware(HTTP_SCOPE, _receive, http_send)
    await middleware(LIFESPAN_SCOPE, _receive, lifespan_send)

    # Assert
    assert http_send.messages[0]["status"] == 204
    assert lifespan_send.messages[0]["status"] == 204
