"""JSON logging suitable for container stdout and CloudWatch Logs."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

STANDARD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in STANDARD_FIELDS and key not in {"message", "asctime"}:
                payload[key] = value
        if record.exc_info:
            payload["error_type"] = record.exc_info[0].__name__
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
