"""Botocore service model integration for validation."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import structlog
from botocore.loaders import Loader
from botocore.exceptions import UnknownServiceError

from aws_mcp.parser.schemas import ValidationResult

logger = structlog.get_logger()


class ServiceModelRegistry:
    """Registry for AWS service models using botocore."""

    def __init__(self) -> None:
        """Initialize the service model registry."""
        self._loader = Loader()
        self._available_services: set[str] | None = None

    @property
    def available_services(self) -> set[str]:
        """Get all available AWS services."""
        if self._available_services is None:
            self._available_services = set(self._loader.list_available_services("service-2"))
        return self._available_services

    def service_exists(self, service: str) -> bool:
        """Check if a service exists."""
        return service.lower() in self.available_services

    @lru_cache(maxsize=50)
    def get_service_model(self, service: str) -> dict[str, Any] | None:
        """Load a service model from botocore."""
        try:
            return self._loader.load_service_model(service.lower(), "service-2")
        except UnknownServiceError:
            logger.warning("unknown_service", service=service)
            return None
        except Exception as e:
            logger.error("failed_to_load_service_model", service=service, error=str(e))
            return None

    def get_operations(self, service: str) -> dict[str, Any]:
        """Get all operations for a service."""
        model = self.get_service_model(service)
        if model:
            return model.get("operations", {})
        return {}

    def operation_exists(self, service: str, operation: str) -> bool:
        """Check if an operation exists for a service."""
        operations = self.get_operations(service)
        # Convert snake_case to PascalCase for matching
        pascal_case = "".join(word.capitalize() for word in operation.split("_"))
        return operation in operations or pascal_case in operations

    def get_operation_model(self, service: str, operation: str) -> dict[str, Any] | None:
        """Get the model for a specific operation."""
        operations = self.get_operations(service)

        # Try exact match first
        if operation in operations:
            return operations[operation]

        # Try PascalCase
        pascal_case = "".join(word.capitalize() for word in operation.split("_"))
        if pascal_case in operations:
            return operations[pascal_case]

        return None

    def get_input_shape(self, service: str, operation: str) -> dict[str, Any] | None:
        """Get the input shape for an operation."""
        op_model = self.get_operation_model(service, operation)
        if not op_model:
            return None

        input_info = op_model.get("input", {})
        shape_name = input_info.get("shape")
        if not shape_name:
            return None

        model = self.get_service_model(service)
        if model:
            shapes = model.get("shapes", {})
            return shapes.get(shape_name)

        return None

    def get_required_parameters(self, service: str, operation: str) -> list[str]:
        """Get required parameters for an operation."""
        shape = self.get_input_shape(service, operation)
        if shape:
            return shape.get("required", [])
        return []

    def get_optional_parameters(self, service: str, operation: str) -> list[str]:
        """Get optional parameters for an operation."""
        shape = self.get_input_shape(service, operation)
        if not shape:
            return []

        required = set(shape.get("required", []))
        members = shape.get("members", {})
        return [name for name in members.keys() if name not in required]

    def get_parameter_type(self, service: str, operation: str, parameter: str) -> str | None:
        """Get the type of a parameter."""
        shape = self.get_input_shape(service, operation)
        if not shape:
            return None

        members = shape.get("members", {})
        param_info = members.get(parameter, {})
        return param_info.get("type")

    def validate_operation(
        self,
        service: str,
        operation: str,
        parameters: dict[str, Any],
    ) -> ValidationResult:
        """Validate an operation and its parameters."""
        errors: list[str] = []
        warnings: list[str] = []

        # Check service exists
        if not self.service_exists(service):
            similar = self._find_similar_services(service)
            suggestion = f" Did you mean: {', '.join(similar[:3])}?" if similar else ""
            return ValidationResult.invalid_result(
                [f"Unknown service '{service}'.{suggestion}"]
            )

        # Check operation exists
        if not self.operation_exists(service, operation):
            similar = self._find_similar_operations(service, operation)
            suggestion = f" Similar operations: {', '.join(similar[:3])}" if similar else ""
            return ValidationResult.invalid_result(
                [f"Operation '{operation}' not found for service '{service}'.{suggestion}"]
            )

        # Check required parameters
        required = self.get_required_parameters(service, operation)
        missing = [p for p in required if p not in parameters]
        if missing:
            errors.append(f"Missing required parameters: {', '.join(missing)}")

        # Check for unknown parameters
        shape = self.get_input_shape(service, operation)
        if shape:
            known_params = set(shape.get("members", {}).keys())
            unknown = [p for p in parameters.keys() if p not in known_params]
            if unknown:
                warnings.append(f"Unknown parameters (may be ignored): {', '.join(unknown)}")

        # Type validation
        for param_name, param_value in parameters.items():
            expected_type = self.get_parameter_type(service, operation, param_name)
            if expected_type and not self._type_matches(param_value, expected_type):
                errors.append(
                    f"Parameter '{param_name}' should be {expected_type}, got {type(param_value).__name__}"
                )

        if errors:
            return ValidationResult(
                valid=False,
                errors=errors,
                warnings=warnings,
                missing_required=missing,
            )

        return ValidationResult(valid=True, warnings=warnings)

    def _type_matches(self, value: Any, expected_type: str) -> bool:
        """Check if a value matches the expected botocore type."""
        type_map = {
            "string": str,
            "integer": int,
            "long": int,
            "boolean": bool,
            "list": list,
            "map": dict,
            "structure": dict,
            "blob": (bytes, str),
            "timestamp": (str, int, float),
            "float": (int, float),
            "double": (int, float),
        }

        expected = type_map.get(expected_type.lower())
        if expected is None:
            return True  # Unknown type, allow it

        return isinstance(value, expected)

    def _find_similar_services(self, service: str, threshold: int = 3) -> list[str]:
        """Find services with similar names."""
        from difflib import get_close_matches
        return get_close_matches(service.lower(), list(self.available_services), n=3, cutoff=0.6)

    def _find_similar_operations(self, service: str, operation: str, threshold: int = 3) -> list[str]:
        """Find operations with similar names."""
        from difflib import get_close_matches
        operations = list(self.get_operations(service).keys())
        # Convert to snake_case for matching
        snake_case_ops = [self._to_snake_case(op) for op in operations]
        matches = get_close_matches(operation.lower(), snake_case_ops, n=3, cutoff=0.6)
        return matches

    @staticmethod
    def _to_snake_case(name: str) -> str:
        """Convert PascalCase to snake_case."""
        import re
        s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    def supports_pagination(self, service: str, operation: str) -> bool:
        """Check if an operation supports pagination."""
        try:
            # Check if paginator exists for this operation
            paginator_model = self._loader.load_service_model(
                service, "paginators-1", api_version=None
            )
            paginators = paginator_model.get("pagination", {})
            # Convert operation to PascalCase
            pascal_case = "".join(word.capitalize() for word in operation.split("_"))
            return pascal_case in paginators or operation in paginators
        except Exception:
            return False

    def get_result_key(self, service: str, operation: str) -> str | None:
        """Get the key in the response that contains the result list."""
        try:
            paginator_model = self._loader.load_service_model(
                service, "paginators-1", api_version=None
            )
            paginators = paginator_model.get("pagination", {})
            pascal_case = "".join(word.capitalize() for word in operation.split("_"))

            paginator_config = paginators.get(pascal_case) or paginators.get(operation)
            if paginator_config:
                result_keys = paginator_config.get("result_key")
                if isinstance(result_keys, list) and result_keys:
                    return result_keys[0]
                return result_keys
        except Exception:
            pass

        return None


# Global registry instance
_registry: ServiceModelRegistry | None = None


def get_service_registry() -> ServiceModelRegistry:
    """Get the global service model registry."""
    global _registry
    if _registry is None:
        _registry = ServiceModelRegistry()
    return _registry
