from typing import Protocol

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class ErrorResponder(Protocol):
    def __call__(self, request: Request, exc: Exception) -> Response: ...


class UnexpectedErrorMiddleware:
    """Turns an unhandled exception into a response that still passes through the outer layers."""

    def __init__(self, app: ASGIApp, responder: ErrorResponder) -> None:
        self.app = app
        self._responder = responder

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def track_response_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, track_response_start)
        except Exception as exc:
            if response_started:
                raise
            response = self._responder(request=Request(scope), exc=exc)
            await response(scope, receive, send)
