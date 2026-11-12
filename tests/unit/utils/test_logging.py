import json
import logging
import sys

from nisar_hazard_watch.utils.logging import JsonFormatter
from nisar_hazard_watch.utils.request_context import request_id_var

REQUEST_ID = "abc123"


def _record(message: str = "hello", exc_info: tuple | None = None) -> logging.LogRecord:
    return logging.LogRecord(
        name="tests.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=exc_info,
    )


def test_formatter_emits_one_json_object_per_record() -> None:
    # Arrange
    formatter = JsonFormatter()

    # Act
    payload = json.loads(formatter.format(_record()))

    # Assert
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "tests.logger"
    assert "requestId" not in payload


def test_formatter_adds_the_request_id_from_the_context() -> None:
    # Arrange
    formatter = JsonFormatter()
    token = request_id_var.set(REQUEST_ID)

    # Act
    try:
        payload = json.loads(formatter.format(_record()))
    finally:
        request_id_var.reset(token)

    # Assert
    assert payload["requestId"] == REQUEST_ID


def test_formatter_includes_the_exception_traceback() -> None:
    # Arrange
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = _record(exc_info=sys.exc_info())

    # Act
    payload = json.loads(formatter.format(record))

    # Assert
    assert "ValueError: boom" in payload["exception"]
