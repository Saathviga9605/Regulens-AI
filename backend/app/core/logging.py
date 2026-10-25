"""Structured (JSON-lines) logging configuration."""

import json
import logging
import sys
from datetime import datetime, timezone

_EXTRA_FIELDS = (
    "request_id",
    "path",
    "method",
    "status_code",
    "error_type",
    "ruleset_profile",
    "ruleset_version",
    "rule_set_version",
    "rule_count",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _EXTRA_FIELDS:
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            # Stack traces stay in server logs only; never in API responses.
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
