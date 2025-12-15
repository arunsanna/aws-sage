"""Safety validation for AWS MCP Pro."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from aws_mcp.config import OperationCategory, SafetyConfig, SafetyMode, get_config
from aws_mcp.core.exceptions import OperationBlockedError, SafetyError
from aws_mcp.safety.classifier import OperationClassifier
from aws_mcp.safety.denylist import (
    get_block_reason,
    is_operation_blocked,
    requires_double_confirmation,
    should_warn,
)

logger = structlog.get_logger()


@dataclass
class SafetyDecision:
    """Result of a safety evaluation."""

    allowed: bool
    category: OperationCategory
    reason: str = ""
    requires_confirmation: bool = False
    requires_double_confirmation: bool = False
    can_dry_run: bool = False
    warning: str | None = None
    suggested_mode: SafetyMode | None = None
    affected_resources: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "allowed": self.allowed,
            "category": self.category.value,
            "requires_confirmation": self.requires_confirmation,
        }
        if not self.allowed:
            result["reason"] = self.reason
        if self.suggested_mode:
            result["suggested_mode"] = self.suggested_mode.value
        if self.warning:
            result["warning"] = self.warning
        if self.can_dry_run:
            result["can_dry_run"] = True
        if self.requires_double_confirmation:
            result["requires_double_confirmation"] = True
        return result


class SafetyEnforcer:
    """Enforces safety policies for AWS operations."""

    def __init__(self, config: SafetyConfig | None = None):
        self.config = config or get_config().safety
        self.classifier = OperationClassifier

    def evaluate(
        self,
        service: str,
        operation: str,
        parameters: dict[str, Any] | None = None,
    ) -> SafetyDecision:
        """
        Evaluate an operation against safety policies.

        Args:
            service: AWS service name
            operation: Operation name
            parameters: Operation parameters (used for resource counting)

        Returns:
            SafetyDecision indicating whether to proceed
        """
        parameters = parameters or {}

        # Step 1: Check if operation is in denylist (always blocked)
        if is_operation_blocked(service, operation):
            reason = get_block_reason(service, operation)
            logger.warning(
                "operation_blocked",
                service=service,
                operation=operation,
                reason=reason,
            )
            return SafetyDecision(
                allowed=False,
                category=OperationCategory.BLOCKED,
                reason=reason or f"Operation '{service}.{operation}' is blocked for security reasons",
            )

        # Step 2: Classify the operation
        category = self.classifier.classify(service, operation)

        # Step 3: Check safety mode restrictions
        allowed_categories = self._get_allowed_categories()
        if category not in allowed_categories:
            logger.info(
                "operation_blocked_by_mode",
                service=service,
                operation=operation,
                category=category.value,
                mode=self.config.mode.value,
            )
            return SafetyDecision(
                allowed=False,
                category=category,
                reason=f"Operation '{operation}' ({category.value}) is not allowed in {self.config.mode.value} mode",
                suggested_mode=self._suggest_mode_for_category(category),
            )

        # Step 4: Determine confirmation requirements
        requires_confirmation = category in self.config.require_confirmation_for
        double_confirm = requires_double_confirmation(service, operation)

        # Step 5: Check for dry-run support
        can_dry_run = (
            self.config.dry_run_when_available
            and self.classifier.supports_dry_run(service, operation)
        )

        # Step 6: Check for warnings
        warning = None
        if should_warn(service, operation):
            warning = f"Operation '{operation}' can have significant security implications"

        # Step 7: Count affected resources (for bulk operations)
        affected_count = self._count_affected_resources(parameters)
        if affected_count > self.config.max_resources_per_operation:
            return SafetyDecision(
                allowed=False,
                category=category,
                reason=f"Operation would affect {affected_count} resources, exceeding limit of {self.config.max_resources_per_operation}",
                affected_resources=affected_count,
            )

        logger.debug(
            "operation_allowed",
            service=service,
            operation=operation,
            category=category.value,
            requires_confirmation=requires_confirmation,
        )

        return SafetyDecision(
            allowed=True,
            category=category,
            requires_confirmation=requires_confirmation,
            requires_double_confirmation=double_confirm,
            can_dry_run=can_dry_run,
            warning=warning,
            affected_resources=affected_count,
        )

    def _get_allowed_categories(self) -> set[OperationCategory]:
        """Get categories allowed by current safety mode."""
        if self.config.mode == SafetyMode.READ_ONLY:
            return {OperationCategory.READ}
        elif self.config.mode == SafetyMode.STANDARD:
            return {OperationCategory.READ, OperationCategory.WRITE, OperationCategory.DESTRUCTIVE}
        elif self.config.mode == SafetyMode.UNRESTRICTED:
            return {OperationCategory.READ, OperationCategory.WRITE, OperationCategory.DESTRUCTIVE}
        return {OperationCategory.READ}

    def _suggest_mode_for_category(self, category: OperationCategory) -> SafetyMode:
        """Suggest the appropriate mode for a category."""
        if category in {OperationCategory.WRITE, OperationCategory.DESTRUCTIVE}:
            return SafetyMode.STANDARD
        return SafetyMode.READ_ONLY

    def _count_affected_resources(self, parameters: dict[str, Any]) -> int:
        """Count the number of resources that would be affected."""
        # Check common parameter patterns for bulk operations
        count = 1

        # Instance IDs (EC2)
        if "InstanceIds" in parameters:
            count = max(count, len(parameters["InstanceIds"]))

        # Resource IDs generic
        if "ResourceIds" in parameters:
            count = max(count, len(parameters["ResourceIds"]))

        # ARNs
        if "ResourceArns" in parameters:
            count = max(count, len(parameters["ResourceArns"]))

        # S3 objects
        if "Delete" in parameters and "Objects" in parameters.get("Delete", {}):
            count = max(count, len(parameters["Delete"]["Objects"]))

        # Function names (Lambda)
        if "FunctionNames" in parameters:
            count = max(count, len(parameters["FunctionNames"]))

        return count

    def set_mode(self, mode: SafetyMode) -> None:
        """Change the safety mode."""
        old_mode = self.config.mode
        self.config.mode = mode
        logger.info("safety_mode_changed", old_mode=old_mode.value, new_mode=mode.value)

    def get_mode(self) -> SafetyMode:
        """Get the current safety mode."""
        return self.config.mode

    def enforce(
        self,
        service: str,
        operation: str,
        parameters: dict[str, Any] | None = None,
    ) -> SafetyDecision:
        """
        Evaluate and raise exception if not allowed.

        This is a stricter version of evaluate() that raises exceptions
        instead of returning decisions for blocked operations.
        """
        decision = self.evaluate(service, operation, parameters)

        if not decision.allowed:
            if decision.category == OperationCategory.BLOCKED:
                raise OperationBlockedError(
                    f"{service}.{operation}",
                    reason=decision.reason,
                )
            else:
                raise SafetyError(
                    message=decision.reason,
                    operation=f"{service}.{operation}",
                    category=decision.category.value,
                    current_mode=self.config.mode.value,
                    suggested_mode=decision.suggested_mode.value if decision.suggested_mode else None,
                )

        return decision


# Global safety enforcer
_enforcer: SafetyEnforcer | None = None


def get_safety_enforcer() -> SafetyEnforcer:
    """Get the global safety enforcer instance."""
    global _enforcer
    if _enforcer is None:
        _enforcer = SafetyEnforcer()
    return _enforcer


def reset_safety_enforcer() -> None:
    """Reset the global safety enforcer (for testing)."""
    global _enforcer
    _enforcer = None
