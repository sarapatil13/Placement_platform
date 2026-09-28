"""Domain exceptions mapped to HTTP responses in one place."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for expected, user-facing failures."""

    status_code: int = 400
    code: str = "app_error"

    def __init__(
        self,
        detail: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.extra = extra or {}

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"detail": self.detail, "code": self.code}
        body.update(self.extra)
        return body


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class PayloadTooLargeError(AppError):
    """413. Rejected using only request metadata, before the body is buffered."""

    status_code = 413
    code = "payload_too_large"


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_failed"


class PermissionError_(AppError):
    """403. Named with a trailing underscore to avoid shadowing the builtin."""

    status_code = 403
    code = "permission_denied"


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"


class NotEligibleError(AppError):
    """Raised when a student attempts to register for a drive they cannot join."""

    status_code = 403
    code = "not_eligible"


class ExternalServiceError(AppError):
    """An AI or third-party call failed. Degraded, never fatal."""

    status_code = 502
    code = "external_service_error"
