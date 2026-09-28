"""Structured logging with request correlation and secret redaction."""

from __future__ import annotations

import logging
import sys
import uuid
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

from app.core.config import settings

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

# Never let these reach a log sink verbatim.
_REDACT_KEYS = {
    "password",
    "password_hash",
    "new_password",
    "current_password",
    "confirm_password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "api_key",
    "secret_key",
    "field_encryption_key",
    "cookie",
    "set-cookie",
    "ssn",
    "aadhaar",
    "phone",
    "email",
}


def _redact_processor(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if key.lower() in _REDACT_KEYS:
            event_dict[key] = "***redacted***"
    return event_dict


def configure_logging(level: str | None = None) -> None:
    resolved = (level or ("DEBUG" if settings.debug else "INFO")).upper()
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=resolved)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, resolved, logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "app") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def new_request_id() -> str:
    rid = uuid.uuid4().hex[:12]
    request_id_ctx.set(rid)
    return rid
