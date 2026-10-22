"""Structured logging.

Logs are JSON by default so a collector can index request id, method, path, status
and duration without parsing prose. Development can opt into a readable form with
``SIH_LOG_JSON=false``.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from .context import current_request_id

_STANDARD_ATTRS = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = current_request_id()
        if request_id:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


class ReadableFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        request_id = current_request_id()
        prefix = f"[{request_id}] " if request_id else ""
        return f"{record.levelname:<7} {prefix}{record.getMessage()}"


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Install one stdout handler for the application and uvicorn loggers."""
    formatter: logging.Formatter = (
        JsonFormatter() if json_output else ReadableFormatter()
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # uvicorn installs its own handlers before importing the app. Reuse ours so
    # access and error logs share the same format and request context.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(level.upper())
