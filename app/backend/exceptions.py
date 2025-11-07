"""
Custom exceptions for ArenaLab services.

This module provides a unified exception hierarchy for all service-level errors.
"""
from typing import Dict, Any, Optional


class ServiceError(Exception):
    """
    Base exception for all service-level errors.

    This is the base class for all custom exceptions raised by service classes.
    It provides consistent error handling and optional status codes for HTTP responses.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        detail: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize a service error.

        Args:
            message: Human-readable error message
            status_code: HTTP status code (default: 400 Bad Request)
            detail: Optional dictionary with additional error details
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail or {"message": message}

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "status_code": self.status_code,
            "detail": self.detail
        }


class ExperimentError(ServiceError):
    """Exception for experiment-related errors."""
    pass


class RunError(ServiceError):
    """Exception for run-related errors."""
    pass


class RevisionError(ServiceError):
    """Exception for revision-related errors."""
    pass


class EnvironmentError(ServiceError):
    """Exception for environment-related errors."""
    pass


class RunnerError(ServiceError):
    """Exception for runner/process management errors."""
    pass


class ValidationError(ServiceError):
    """Exception for validation errors."""

    def __init__(self, message: str, detail: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=422, detail=detail)


class ProcessError(ServiceError):
    """Exception for process-related errors."""

    def __init__(self, message: str, detail: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=500, detail=detail)


class NotFoundError(ServiceError):
    """Exception for resource not found errors."""

    def __init__(self, message: str, detail: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=404, detail=detail)


class ConflictError(ServiceError):
    """Exception for resource conflict errors."""

    def __init__(self, message: str, detail: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=409, detail=detail)
