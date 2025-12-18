"""Base service plugin interface for AWS MCP Pro."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

import boto3
import structlog

from aws_sage.config import OperationCategory
from aws_sage.safety.classifier import OperationClassifier

logger = structlog.get_logger()


@dataclass
class OperationSpec:
    """Specification for an AWS operation."""

    name: str
    description: str
    category: OperationCategory
    required_params: list[str]
    optional_params: list[str]
    supports_pagination: bool = False
    supports_dry_run: bool = False
    result_key: str | None = None  # Key in response containing the data list


@dataclass
class OperationResult:
    """Result of an operation execution."""

    success: bool
    data: Any = None
    error: str | None = None
    error_code: str | None = None
    count: int | None = None
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"success": self.success}
        if self.success:
            result["data"] = self.data
            if self.count is not None:
                result["count"] = self.count
            if self.truncated:
                result["truncated"] = True
        else:
            result["error"] = self.error
            if self.error_code:
                result["error_code"] = self.error_code
        return result


class BaseService(ABC):
    """Abstract base class for AWS service plugins.

    Each service plugin should implement this interface to provide
    standardized access to AWS service operations.

    Example:
        class S3Service(BaseService):
            @property
            def service_name(self) -> str:
                return "s3"

            @property
            def display_name(self) -> str:
                return "Amazon S3"

            def get_operations(self) -> list[OperationSpec]:
                return [
                    OperationSpec(
                        name="list_buckets",
                        description="List all S3 buckets",
                        category=OperationCategory.READ,
                        required_params=[],
                        optional_params=[],
                        result_key="Buckets",
                    ),
                ]
    """

    def __init__(self, session: boto3.Session):
        """Initialize the service with a boto3 session."""
        self._session = session
        self._client: Any = None

    @property
    @abstractmethod
    def service_name(self) -> str:
        """Return the boto3 service name (e.g., 's3', 'ec2')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Return a human-readable service name."""
        ...

    @property
    def client(self) -> Any:
        """Get or create the boto3 client for this service."""
        if self._client is None:
            self._client = self._session.client(self.service_name)
        return self._client

    @abstractmethod
    def get_operations(self) -> list[OperationSpec]:
        """Return list of supported operations for this service."""
        ...

    def get_operation(self, name: str) -> OperationSpec | None:
        """Get a specific operation by name."""
        for op in self.get_operations():
            if op.name == name:
                return op
        return None

    def supports_operation(self, name: str) -> bool:
        """Check if an operation is supported."""
        return self.get_operation(name) is not None

    async def execute(
        self,
        operation: str,
        parameters: dict[str, Any] | None = None,
    ) -> OperationResult:
        """Execute an operation on this service.

        Args:
            operation: The operation name (e.g., 'list_buckets')
            parameters: Operation parameters

        Returns:
            OperationResult with success status and data or error
        """
        parameters = parameters or {}
        op_spec = self.get_operation(operation)

        if not op_spec:
            return OperationResult(
                success=False,
                error=f"Operation '{operation}' not supported for {self.service_name}",
            )

        # Validate required parameters
        missing = [p for p in op_spec.required_params if p not in parameters]
        if missing:
            return OperationResult(
                success=False,
                error=f"Missing required parameters: {', '.join(missing)}",
            )

        try:
            method = getattr(self.client, operation)

            if op_spec.supports_pagination:
                result = await self._execute_paginated(operation, parameters, op_spec.result_key)
            else:
                result = method(**parameters)
                if op_spec.result_key and op_spec.result_key in result:
                    result = result[op_spec.result_key]

            count = len(result) if isinstance(result, list) else None

            logger.info(
                "operation_executed",
                service=self.service_name,
                operation=operation,
                count=count,
            )

            return OperationResult(success=True, data=result, count=count)

        except Exception as e:
            error_code = None
            if hasattr(e, "response"):
                error_code = e.response.get("Error", {}).get("Code")  # type: ignore

            logger.error(
                "operation_failed",
                service=self.service_name,
                operation=operation,
                error=str(e),
                error_code=error_code,
            )

            return OperationResult(
                success=False,
                error=str(e),
                error_code=error_code,
            )

    async def _execute_paginated(
        self,
        operation: str,
        parameters: dict[str, Any],
        result_key: str | None,
    ) -> list[Any]:
        """Execute an operation with pagination."""
        try:
            paginator = self.client.get_paginator(operation)
            results = []

            for page in paginator.paginate(**parameters):
                if result_key and result_key in page:
                    results.extend(page[result_key])
                else:
                    # Find the first list in the response
                    for key, value in page.items():
                        if key != "ResponseMetadata" and isinstance(value, list):
                            results.extend(value)
                            break

            return results
        except Exception:
            # Fallback to non-paginated
            method = getattr(self.client, operation)
            result = method(**parameters)
            if result_key and result_key in result:
                return result[result_key]
            return result

    def format_response(
        self,
        data: Any,
        format_type: str = "table",
    ) -> str:
        """Format operation response for display.

        Override this in subclasses for service-specific formatting.
        """
        if format_type == "json":
            import json

            return json.dumps(data, indent=2, default=str)

        if isinstance(data, list) and data:
            return self._format_as_table(data)

        return str(data)

    def _format_as_table(self, data: list[dict[str, Any]]) -> str:
        """Format a list of dicts as a markdown table."""
        if not data or not isinstance(data[0], dict):
            return str(data)

        headers = list(data[0].keys())
        col_widths = [min(30, len(h)) for h in headers]

        for row in data:
            for i, h in enumerate(headers):
                if h in row:
                    val = str(row[h])[:30]
                    col_widths[i] = min(30, max(col_widths[i], len(val)))

        lines = []
        lines.append("| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |")
        lines.append("| " + " | ".join("-" * w for w in col_widths) + " |")

        for row in data:
            cells = [str(row.get(h, ""))[:30].ljust(col_widths[i]) for i, h in enumerate(headers)]
            lines.append("| " + " | ".join(cells) + " |")

        return "\n".join(lines)


class ServiceRegistry:
    """Registry for service plugins."""

    _services: dict[str, type[BaseService]] = {}
    _instances: dict[str, BaseService] = {}

    @classmethod
    def register(cls, service_class: type[BaseService]) -> type[BaseService]:
        """Register a service plugin.

        Can be used as a decorator:
            @ServiceRegistry.register
            class S3Service(BaseService):
                ...
        """
        # Create a temporary instance to get the service name
        # We use a dummy session since we just need the name
        temp_session = boto3.Session(region_name="us-east-1")
        try:
            temp_instance = service_class(temp_session)
            name = temp_instance.service_name
            cls._services[name] = service_class
            logger.debug("service_registered", service=name)
        except Exception as e:
            logger.warning("failed_to_register_service", error=str(e))
        return service_class

    @classmethod
    def get_service(cls, name: str, session: boto3.Session) -> BaseService | None:
        """Get a service instance by name."""
        if name not in cls._services:
            return None

        # Cache instances per session
        cache_key = f"{name}:{id(session)}"
        if cache_key not in cls._instances:
            cls._instances[cache_key] = cls._services[name](session)
        return cls._instances[cache_key]

    @classmethod
    def list_services(cls) -> list[str]:
        """List all registered services."""
        return list(cls._services.keys())

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the instance cache."""
        cls._instances.clear()


def register_service(cls: type[BaseService]) -> type[BaseService]:
    """Decorator to register a service plugin."""
    return ServiceRegistry.register(cls)
