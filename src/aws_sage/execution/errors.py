"""Error handling for AWS operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from botocore.exceptions import ClientError, ParamValidationError

from aws_sage.core.exceptions import ExecutionError

logger = structlog.get_logger()


@dataclass
class ErrorInfo:
    """Information about an error for recovery suggestions."""

    category: str
    suggestion: str
    recoverable: bool
    retry_after: int | None = None


# Common AWS error mappings
AWS_ERROR_MAPPINGS: dict[str, ErrorInfo] = {
    # Authentication / Authorization
    "UnauthorizedAccess": ErrorInfo(
        category="auth",
        suggestion="Check your AWS credentials and IAM permissions",
        recoverable=False,
    ),
    "AccessDenied": ErrorInfo(
        category="auth",
        suggestion="You don't have permission for this operation. Check IAM policies.",
        recoverable=False,
    ),
    "AccessDeniedException": ErrorInfo(
        category="auth",
        suggestion="You don't have permission for this operation. Check IAM policies.",
        recoverable=False,
    ),
    "ExpiredToken": ErrorInfo(
        category="auth",
        suggestion="Your credentials have expired. Run 'aws sso login' or refresh your credentials.",
        recoverable=True,
    ),
    "ExpiredTokenException": ErrorInfo(
        category="auth",
        suggestion="Your credentials have expired. Run 'aws sso login' or refresh your credentials.",
        recoverable=True,
    ),
    "InvalidIdentityToken": ErrorInfo(
        category="auth",
        suggestion="The identity token is invalid. Try refreshing your credentials.",
        recoverable=True,
    ),
    "SignatureDoesNotMatch": ErrorInfo(
        category="auth",
        suggestion="Request signature doesn't match. Check your credentials and clock sync.",
        recoverable=False,
    ),
    # Resource errors
    "ResourceNotFoundException": ErrorInfo(
        category="resource",
        suggestion="The resource doesn't exist. Verify the identifier is correct.",
        recoverable=False,
    ),
    "ResourceNotFoundFault": ErrorInfo(
        category="resource",
        suggestion="The resource doesn't exist. Verify the identifier is correct.",
        recoverable=False,
    ),
    "NoSuchBucket": ErrorInfo(
        category="resource",
        suggestion="The S3 bucket doesn't exist. Check the bucket name.",
        recoverable=False,
    ),
    "NoSuchKey": ErrorInfo(
        category="resource",
        suggestion="The S3 object doesn't exist. Check the key path.",
        recoverable=False,
    ),
    "ResourceAlreadyExistsException": ErrorInfo(
        category="resource",
        suggestion="A resource with this name already exists. Use a different name.",
        recoverable=False,
    ),
    "BucketAlreadyExists": ErrorInfo(
        category="resource",
        suggestion="This bucket name is already taken globally. Try a different name.",
        recoverable=False,
    ),
    "BucketAlreadyOwnedByYou": ErrorInfo(
        category="resource",
        suggestion="You already own this bucket. No action needed.",
        recoverable=False,
    ),
    # Validation errors
    "ValidationException": ErrorInfo(
        category="validation",
        suggestion="Request validation failed. Check parameter types and formats.",
        recoverable=False,
    ),
    "ValidationError": ErrorInfo(
        category="validation",
        suggestion="Request validation failed. Check parameter types and formats.",
        recoverable=False,
    ),
    "InvalidParameterValue": ErrorInfo(
        category="validation",
        suggestion="One or more parameters have invalid values.",
        recoverable=False,
    ),
    "InvalidParameterException": ErrorInfo(
        category="validation",
        suggestion="One or more parameters have invalid values.",
        recoverable=False,
    ),
    "MissingParameter": ErrorInfo(
        category="validation",
        suggestion="A required parameter is missing.",
        recoverable=False,
    ),
    "MalformedQueryString": ErrorInfo(
        category="validation",
        suggestion="The query string is malformed. Check the request format.",
        recoverable=False,
    ),
    # Rate limiting
    "ThrottlingException": ErrorInfo(
        category="rate_limit",
        suggestion="Request was throttled. Wait and retry.",
        recoverable=True,
        retry_after=5,
    ),
    "Throttling": ErrorInfo(
        category="rate_limit",
        suggestion="Request was throttled. Wait and retry.",
        recoverable=True,
        retry_after=5,
    ),
    "RequestLimitExceeded": ErrorInfo(
        category="rate_limit",
        suggestion="Request limit exceeded. Reduce request frequency.",
        recoverable=True,
        retry_after=10,
    ),
    "TooManyRequestsException": ErrorInfo(
        category="rate_limit",
        suggestion="Too many requests. Wait and retry.",
        recoverable=True,
        retry_after=5,
    ),
    "ProvisionedThroughputExceededException": ErrorInfo(
        category="rate_limit",
        suggestion="DynamoDB throughput exceeded. Consider increasing capacity.",
        recoverable=True,
        retry_after=1,
    ),
    # Service availability
    "ServiceUnavailable": ErrorInfo(
        category="service",
        suggestion="AWS service is temporarily unavailable. Retry later.",
        recoverable=True,
        retry_after=30,
    ),
    "ServiceException": ErrorInfo(
        category="service",
        suggestion="AWS service error. Retry later.",
        recoverable=True,
        retry_after=30,
    ),
    "InternalError": ErrorInfo(
        category="service",
        suggestion="AWS internal error. Retry later.",
        recoverable=True,
        retry_after=30,
    ),
    "InternalServerError": ErrorInfo(
        category="service",
        suggestion="AWS internal error. Retry later.",
        recoverable=True,
        retry_after=30,
    ),
    # Limits
    "LimitExceededException": ErrorInfo(
        category="limit",
        suggestion="Service limit exceeded. Request a limit increase or delete unused resources.",
        recoverable=False,
    ),
    "QuotaExceededException": ErrorInfo(
        category="limit",
        suggestion="Service quota exceeded. Request a quota increase.",
        recoverable=False,
    ),
    # Conflicts
    "ConditionalCheckFailedException": ErrorInfo(
        category="conflict",
        suggestion="A condition check failed. The resource may have been modified.",
        recoverable=True,
    ),
    "ResourceInUseException": ErrorInfo(
        category="conflict",
        suggestion="The resource is currently in use. Wait and retry.",
        recoverable=True,
        retry_after=10,
    ),
    "OptimisticLockException": ErrorInfo(
        category="conflict",
        suggestion="Resource was modified by another process. Refresh and retry.",
        recoverable=True,
    ),
}


class ErrorHandler:
    """Handles AWS errors and provides actionable suggestions."""

    @classmethod
    def handle_client_error(
        cls,
        error: ClientError,
        service: str | None = None,
        operation: str | None = None,
    ) -> ExecutionError:
        """
        Handle a boto3 ClientError and convert to ExecutionError.

        Args:
            error: The boto3 ClientError
            service: The AWS service name
            operation: The operation that failed

        Returns:
            ExecutionError with actionable information
        """
        error_code = error.response.get("Error", {}).get("Code", "Unknown")
        error_message = error.response.get("Error", {}).get("Message", str(error))

        # Look up error info
        error_info = AWS_ERROR_MAPPINGS.get(error_code)

        if error_info:
            return ExecutionError(
                message=f"{error_message}. {error_info.suggestion}",
                service=service,
                operation=operation,
                aws_error_code=error_code,
                recoverable=error_info.recoverable,
                retry_after=error_info.retry_after,
            )

        # Unknown error - provide generic handling
        return ExecutionError(
            message=error_message,
            service=service,
            operation=operation,
            aws_error_code=error_code,
            recoverable=False,
        )

    @classmethod
    def handle_param_validation_error(
        cls,
        error: ParamValidationError,
        service: str | None = None,
        operation: str | None = None,
    ) -> ExecutionError:
        """Handle a parameter validation error."""
        return ExecutionError(
            message=f"Parameter validation error: {str(error)}",
            service=service,
            operation=operation,
            recoverable=False,
        )

    @classmethod
    def handle_exception(
        cls,
        error: Exception,
        service: str | None = None,
        operation: str | None = None,
    ) -> ExecutionError:
        """Handle any exception."""
        if isinstance(error, ClientError):
            return cls.handle_client_error(error, service, operation)
        elif isinstance(error, ParamValidationError):
            return cls.handle_param_validation_error(error, service, operation)
        else:
            return ExecutionError(
                message=str(error),
                service=service,
                operation=operation,
                recoverable=False,
            )

    @classmethod
    def format_error_response(
        cls,
        error: ExecutionError,
    ) -> dict[str, Any]:
        """Format an error for JSON response."""
        response: dict[str, Any] = {
            "status": "error",
            "message": error.message,
        }

        if error.details:
            response.update(error.details)

        if error.details.get("recoverable"):
            response["recoverable"] = True
            if "retry_after_seconds" in error.details:
                response["retry_after"] = error.details["retry_after_seconds"]

        return response

    @classmethod
    def should_retry(cls, error_code: str) -> bool:
        """Check if an error should be retried."""
        error_info = AWS_ERROR_MAPPINGS.get(error_code)
        return error_info.recoverable if error_info else False

    @classmethod
    def get_retry_delay(cls, error_code: str) -> int:
        """Get the recommended retry delay for an error."""
        error_info = AWS_ERROR_MAPPINGS.get(error_code)
        return error_info.retry_after if error_info and error_info.retry_after else 5
