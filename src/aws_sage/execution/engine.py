"""Main execution engine for AWS operations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog
from botocore.exceptions import ClientError, ParamValidationError

from aws_sage.config import OperationCategory, get_config
from aws_sage.core.context import get_context
from aws_sage.core.exceptions import AWSMCPError, SafetyError
from aws_sage.core.session import SessionManager, get_session_manager
from aws_sage.execution.errors import ErrorHandler
from aws_sage.execution.pagination import PaginationHandler
from aws_sage.parser.intent import get_intent_classifier
from aws_sage.parser.schemas import ParseResult, StructuredCommand
from aws_sage.parser.service_models import get_service_registry
from aws_sage.safety.classifier import OperationClassifier
from aws_sage.safety.validator import SafetyDecision, get_safety_enforcer

logger = structlog.get_logger()


@dataclass
class ExecutionResult:
    """Result of executing an AWS operation."""

    success: bool
    data: Any = None
    error: str | None = None
    error_code: str | None = None

    # Metadata
    service: str | None = None
    operation: str | None = None
    category: str | None = None
    region: str | None = None

    # Formatting
    formatted_table: str | None = None
    count: int | None = None
    truncated: bool = False

    # Safety
    requires_confirmation: bool = False
    confirmation_message: str | None = None

    # Suggestions
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {"status": "success" if self.success else "error"}

        if self.success:
            if self.data is not None:
                result["data"] = self.data
            if self.formatted_table:
                result["formatted_table"] = self.formatted_table
            if self.count is not None:
                result["count"] = self.count
            if self.truncated:
                result["truncated"] = True
        else:
            result["error"] = self.error
            if self.error_code:
                result["error_code"] = self.error_code
            if self.suggestions:
                result["suggestions"] = self.suggestions

        if self.service:
            result["service"] = self.service
        if self.operation:
            result["operation"] = self.operation
        if self.category:
            result["category"] = self.category

        if self.requires_confirmation:
            result["status"] = "confirmation_required"
            result["confirmation_message"] = self.confirmation_message

        return result

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)


class ExecutionEngine:
    """Main execution engine orchestrating all components."""

    def __init__(
        self,
        session_manager: SessionManager | None = None,
    ) -> None:
        """Initialize the execution engine."""
        self.session_manager = session_manager or get_session_manager()
        self.intent_classifier = get_intent_classifier()
        self.service_registry = get_service_registry()
        self.safety_enforcer = get_safety_enforcer()
        self.pagination_handler = PaginationHandler()
        self.error_handler = ErrorHandler()

    async def execute_natural_language(
        self,
        query: str,
        region: str | None = None,
        confirm: bool = False,
    ) -> ExecutionResult:
        """
        Execute a natural language query.

        This is the main entry point for processing user queries.

        Args:
            query: Natural language query
            region: Target region (optional)
            confirm: Whether user has confirmed the operation

        Returns:
            ExecutionResult with data or error
        """
        logger.info("executing_query", query=query, region=region)

        # Check session
        if not self.session_manager.active_profile:
            profiles = self.session_manager.list_profiles()
            return ExecutionResult(
                success=False,
                error="No AWS profile selected. Please select a profile first.",
                suggestions=[f"select_profile {p}" for p in profiles[:3]],
            )

        # Resolve aliases in query
        context = get_context()
        resolved_query = context.resolve_alias(query)

        # Parse the query
        parse_result = self.intent_classifier.classify(resolved_query)
        if not parse_result.success:
            return ExecutionResult(
                success=False,
                error=parse_result.error,
                suggestions=parse_result.suggestions,
            )

        command = parse_result.command
        assert command is not None

        # Override region if specified
        if region:
            command.region = region

        # Execute the command
        return await self.execute_command(command, confirm=confirm)

    async def execute_command(
        self,
        command: StructuredCommand,
        confirm: bool = False,
    ) -> ExecutionResult:
        """
        Execute a structured command.

        Args:
            command: Parsed and validated command
            confirm: Whether user has confirmed the operation

        Returns:
            ExecutionResult with data or error
        """
        logger.info(
            "executing_command",
            service=command.service,
            operation=command.operation,
            category=command.category.value,
        )

        # Validate the command
        validation = self.service_registry.validate_operation(
            command.service,
            command.operation,
            command.parameters,
        )

        if not validation.valid:
            return ExecutionResult(
                success=False,
                error="; ".join(validation.errors),
                service=command.service,
                operation=command.operation,
                suggestions=self._get_operation_suggestions(command.service),
            )

        # Safety check
        safety_decision = self.safety_enforcer.evaluate(
            command.service,
            command.operation,
            command.parameters,
        )

        if not safety_decision.allowed:
            return ExecutionResult(
                success=False,
                error=safety_decision.reason,
                service=command.service,
                operation=command.operation,
                category=safety_decision.category.value,
                suggestions=[
                    f"set_safety_mode {safety_decision.suggested_mode.value}"
                ] if safety_decision.suggested_mode else [],
            )

        # Check confirmation requirement
        if safety_decision.requires_confirmation and not confirm:
            return ExecutionResult(
                success=False,
                service=command.service,
                operation=command.operation,
                category=safety_decision.category.value,
                requires_confirmation=True,
                confirmation_message=self._build_confirmation_message(command, safety_decision),
            )

        # Execute the operation
        try:
            client = self.session_manager.get_client(
                command.service,
                command.region,
            )

            # Check for pagination support
            supports_pagination = self.service_registry.supports_pagination(
                command.service,
                command.operation,
            )
            result_key = self.service_registry.get_result_key(
                command.service,
                command.operation,
            )

            if supports_pagination:
                data, truncated = self.pagination_handler.execute_paginated(
                    client,
                    command.operation,
                    command.parameters,
                    result_key,
                )
            else:
                method = getattr(client, command.operation)
                response = method(**command.parameters)
                data = self._extract_data(response, result_key)
                truncated = False

            # Clean the data
            data = self._clean_response(data)

            # Format as table if list
            formatted_table = None
            count = None
            if isinstance(data, list):
                count = len(data)
                formatted_table = self._format_as_table(data)

                # Record resources in context
                context = get_context()
                context.add_resources_from_response(
                    command.service,
                    self._infer_resource_type(command.operation),
                    data,
                )

            # Record query in context
            context = get_context()
            context.record_query(
                query=command.raw_input or f"{command.service}.{command.operation}",
                service=command.service,
                operation=command.operation,
                success=True,
                result_count=count,
            )

            logger.info(
                "execution_success",
                service=command.service,
                operation=command.operation,
                count=count,
            )

            return ExecutionResult(
                success=True,
                data=data,
                service=command.service,
                operation=command.operation,
                category=command.category.value,
                region=command.region or self.session_manager.active_region,
                formatted_table=formatted_table,
                count=count,
                truncated=truncated,
            )

        except ClientError as e:
            exec_error = self.error_handler.handle_client_error(
                e, command.service, command.operation
            )
            logger.warning(
                "execution_failed",
                service=command.service,
                operation=command.operation,
                error_code=exec_error.details.get("aws_error_code"),
            )
            return ExecutionResult(
                success=False,
                error=exec_error.message,
                error_code=exec_error.details.get("aws_error_code"),
                service=command.service,
                operation=command.operation,
            )

        except ParamValidationError as e:
            exec_error = self.error_handler.handle_param_validation_error(
                e, command.service, command.operation
            )
            return ExecutionResult(
                success=False,
                error=exec_error.message,
                service=command.service,
                operation=command.operation,
            )

        except Exception as e:
            logger.error(
                "execution_error",
                service=command.service,
                operation=command.operation,
                error=str(e),
            )
            return ExecutionResult(
                success=False,
                error=str(e),
                service=command.service,
                operation=command.operation,
            )

    async def execute_explicit(
        self,
        service: str,
        operation: str,
        parameters: dict[str, Any] | None = None,
        region: str | None = None,
        confirm: bool = False,
    ) -> ExecutionResult:
        """
        Execute an explicit service/operation call.

        Args:
            service: AWS service name
            operation: Operation name
            parameters: Operation parameters
            region: Target region
            confirm: Whether user has confirmed

        Returns:
            ExecutionResult with data or error
        """
        category = OperationClassifier.classify(service, operation)

        command = StructuredCommand(
            service=service,
            operation=operation,
            parameters=parameters or {},
            category=category,
            region=region,
        )

        return await self.execute_command(command, confirm=confirm)

    def _extract_data(
        self,
        response: dict[str, Any],
        result_key: str | None,
    ) -> Any:
        """Extract data from API response."""
        # Remove metadata
        cleaned = {k: v for k, v in response.items() if k != "ResponseMetadata"}

        if result_key and result_key in cleaned:
            return cleaned[result_key]

        # Find first list
        for key, value in cleaned.items():
            if isinstance(value, list):
                return value

        return cleaned

    def _clean_response(self, data: Any) -> Any:
        """Clean response data for serialization."""
        if isinstance(data, dict):
            return {
                k: self._clean_response(v)
                for k, v in data.items()
                if k != "ResponseMetadata"
            }
        elif isinstance(data, list):
            return [self._clean_response(item) for item in data]
        elif isinstance(data, datetime):
            return data.isoformat()
        elif hasattr(data, "isoformat"):
            return data.isoformat()
        return data

    def _format_as_table(self, data: list[dict[str, Any]]) -> str | None:
        """Format data as markdown table."""
        if not data or not isinstance(data[0], dict):
            return None

        # Get headers (limit to first 6 columns)
        all_headers = list(data[0].keys())
        headers = all_headers[:6]

        # Calculate column widths
        col_widths = [min(30, len(h)) for h in headers]
        for row in data[:20]:  # Sample first 20 rows
            for i, h in enumerate(headers):
                if h in row:
                    val = str(row[h])[:30]
                    col_widths[i] = min(30, max(col_widths[i], len(val)))

        # Build table
        lines = []
        lines.append("| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |")
        lines.append("| " + " | ".join("-" * w for w in col_widths) + " |")

        for row in data[:50]:  # Limit to 50 rows
            cells = [
                str(row.get(h, ""))[:30].ljust(col_widths[i])
                for i, h in enumerate(headers)
            ]
            lines.append("| " + " | ".join(cells) + " |")

        if len(data) > 50:
            lines.append(f"... and {len(data) - 50} more rows")

        return "\n".join(lines)

    def _build_confirmation_message(
        self,
        command: StructuredCommand,
        decision: SafetyDecision,
    ) -> str:
        """Build a confirmation message for the user."""
        msg = f"Operation '{command.operation}' on {command.service}"

        if decision.category == OperationCategory.DESTRUCTIVE:
            msg += " is DESTRUCTIVE"
        else:
            msg += " will modify resources"

        if decision.affected_resources > 1:
            msg += f" ({decision.affected_resources} resources affected)"

        if decision.warning:
            msg += f". Warning: {decision.warning}"

        msg += ". Set confirm=true to proceed."
        return msg

    def _get_operation_suggestions(self, service: str) -> list[str]:
        """Get operation suggestions for a service."""
        operations = self.service_registry.get_operations(service)
        # Return first 5 read operations
        suggestions = []
        for op_name in list(operations.keys())[:10]:
            snake_case = self.service_registry._to_snake_case(op_name)
            if snake_case.startswith(("list_", "describe_", "get_")):
                suggestions.append(snake_case)
                if len(suggestions) >= 5:
                    break
        return suggestions

    def _infer_resource_type(self, operation: str) -> str:
        """Infer resource type from operation name."""
        # Remove common prefixes
        for prefix in ["list_", "describe_", "get_"]:
            if operation.startswith(prefix):
                return operation[len(prefix):]
        return operation


# Global engine instance
_engine: ExecutionEngine | None = None


def get_execution_engine() -> ExecutionEngine:
    """Get the global execution engine."""
    global _engine
    if _engine is None:
        _engine = ExecutionEngine()
    return _engine


def reset_execution_engine() -> None:
    """Reset the global execution engine (for testing)."""
    global _engine
    _engine = None
