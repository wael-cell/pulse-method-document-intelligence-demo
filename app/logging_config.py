"""
Structured logging configuration.

Emits single-line JSON logs so the demo behaves like a service that can be
shipped to a log aggregator (CloudWatch, Loki, Datadog, etc.). Structured fields
are passed through a single namespaced ``context`` key, which guarantees they can
never collide with reserved ``LogRecord`` attributes (``message``, ``filename``,
``module``, ...) — a subtle footgun that otherwise crashes ``logging`` at runtime.

Usage:
    logger.info("job.created", extra=log_context(job_id=jid, source_filename=name))
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


def log_context(**fields: Any) -> dict[str, dict[str, Any]]:
    """Wrap structured fields so they attach safely to a log record."""
    return {"context": fields}


class JsonLogFormatter(logging.Formatter):
    """Render log records as compact JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        context = getattr(record, "context", None)
        if isinstance(context, dict):
            for key, value in context.items():
                if key not in payload:
                    payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger once, idempotently."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Avoid duplicate handlers if called more than once (e.g. under reload).
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root.addHandler(handler)

    # Quiet noisy third-party access logs; we emit our own structured events.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger for a module."""
    return logging.getLogger(name)
