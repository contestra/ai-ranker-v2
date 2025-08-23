"""
API error handling utilities for AI Ranker V2
Provides consistent error responses with structured details
"""

from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class APIError(HTTPException):
    """Base API error with structured detail"""
    
    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        extra: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status_code,
            detail={
                "code": code,
                "detail": detail,
                "extra": extra or {}
            }
        )


def conflict(code: str, detail: str, extra: Optional[Dict[str, Any]] = None):
    """
    409 Conflict error
    Used for: idempotency conflicts, version mismatches, resource conflicts
    """
    raise APIError(
        status_code=status.HTTP_409_CONFLICT,
        code=code,
        detail=detail,
        extra=extra
    )


def bad_request(code: str, detail: str, extra: Optional[Dict[str, Any]] = None):
    """
    400 Bad Request error
    Used for: invalid input, malformed requests
    """
    raise APIError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code=code,
        detail=detail,
        extra=extra
    )


def unprocessable(code: str, detail: str, extra: Optional[Dict[str, Any]] = None):
    """
    422 Unprocessable Entity error
    Used for: validation failures, business logic violations
    """
    raise APIError(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code=code,
        detail=detail,
        extra=extra
    )


def not_found(code: str, detail: str, extra: Optional[Dict[str, Any]] = None):
    """
    404 Not Found error
    Used for: missing resources
    """
    raise APIError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=code,
        detail=detail,
        extra=extra
    )


def unauthorized(code: str, detail: str, extra: Optional[Dict[str, Any]] = None):
    """
    401 Unauthorized error
    Used for: authentication failures
    """
    raise APIError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code=code,
        detail=detail,
        extra=extra
    )


def forbidden(code: str, detail: str, extra: Optional[Dict[str, Any]] = None):
    """
    403 Forbidden error
    Used for: authorization failures
    """
    raise APIError(
        status_code=status.HTTP_403_FORBIDDEN,
        code=code,
        detail=detail,
        extra=extra
    )


def internal_error(code: str, detail: str, extra: Optional[Dict[str, Any]] = None):
    """
    500 Internal Server Error
    Used for: unexpected server errors
    """
    raise APIError(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code=code,
        detail=detail,
        extra=extra
    )


def service_unavailable(code: str, detail: str, extra: Optional[Dict[str, Any]] = None):
    """
    503 Service Unavailable error
    Used for: temporary service issues, rate limiting
    """
    raise APIError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code=code,
        detail=detail,
        extra=extra
    )