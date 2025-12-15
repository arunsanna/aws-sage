"""Custom exceptions for AWS MCP Pro."""

from __future__ import annotations

from typing import Any


class AWSMCPError(Exception):
    """Base exception for AWS MCP Pro."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for JSON serialization."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            **self.details,
        }


class AuthenticationError(AWSMCPError):
    """Raised when AWS authentication fails."""

    def __init__(self, message: str, profile: str | None = None, suggestion: str | None = None):
        details = {}
        if profile:
            details["profile"] = profile
        if suggestion:
            details["suggestion"] = suggestion
        super().__init__(message, details)


class SafetyError(AWSMCPError):
    """Raised when an operation is blocked by safety controls."""

    def __init__(
        self,
        message: str,
        operation: str | None = None,
        category: str | None = None,
        current_mode: str | None = None,
        suggested_mode: str | None = None,
    ):
        details = {}
        if operation:
            details["operation"] = operation
        if category:
            details["category"] = category
        if current_mode:
            details["current_mode"] = current_mode
        if suggested_mode:
            details["suggested_mode"] = suggested_mode
        super().__init__(message, details)


class OperationBlockedError(SafetyError):
    """Raised when an operation is in the denylist."""

    def __init__(self, operation: str, reason: str = "Operation is in the security denylist"):
        super().__init__(
            message=f"Operation '{operation}' is blocked: {reason}",
            operation=operation,
            category="blocked",
        )


class ValidationError(AWSMCPError):
    """Raised when command validation fails."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        expected: str | None = None,
        received: str | None = None,
        suggestions: list[str] | None = None,
    ):
        details = {}
        if field:
            details["field"] = field
        if expected:
            details["expected"] = expected
        if received:
            details["received"] = received
        if suggestions:
            details["suggestions"] = suggestions
        super().__init__(message, details)


class ParseError(AWSMCPError):
    """Raised when command parsing fails."""

    def __init__(
        self,
        message: str,
        input_text: str | None = None,
        suggestions: list[str] | None = None,
    ):
        details = {}
        if input_text:
            details["input"] = input_text
        if suggestions:
            details["suggestions"] = suggestions
        super().__init__(message, details)


class ExecutionError(AWSMCPError):
    """Raised when AWS operation execution fails."""

    def __init__(
        self,
        message: str,
        service: str | None = None,
        operation: str | None = None,
        aws_error_code: str | None = None,
        recoverable: bool = False,
        retry_after: int | None = None,
    ):
        details = {
            "recoverable": recoverable,
        }
        if service:
            details["service"] = service
        if operation:
            details["operation"] = operation
        if aws_error_code:
            details["aws_error_code"] = aws_error_code
        if retry_after:
            details["retry_after_seconds"] = retry_after
        super().__init__(message, details)
