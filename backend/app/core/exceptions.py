"""Domain exceptions mapped to HTTP responses in `app.main`."""

from __future__ import annotations


class AppError(Exception):
    status_code = 400
    code = "app_error"

    def __init__(self, message: str = "", *, details: dict | None = None):
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__
        self.details = details or {}


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "forbidden"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class InsufficientCreditsError(AppError):
    status_code = 402
    code = "insufficient_credits"


class ProviderError(AppError):
    status_code = 502
    code = "provider_error"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
