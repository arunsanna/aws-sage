"""Operation classification for AWS MCP Pro."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from aws_sage.config import OperationCategory


class OperationClassifier:
    """Classifies AWS operations by their impact level."""

    # Prefix-based classification
    READ_PREFIXES = (
        "list",
        "describe",
        "get",
        "batch_get",
        "scan",
        "query",
        "head",
        "check",
        "lookup",
        "search",
        "filter",
        "poll",
    )

    WRITE_PREFIXES = (
        "create",
        "put",
        "update",
        "modify",
        "set",
        "tag",
        "untag",
        "enable",
        "disable",
        "start",
        "stop",
        "attach",
        "detach",
        "associate",
        "disassociate",
        "register",
        "add",
        "import",
        "copy",
        "restore",
        "reboot",
        "reset",
        "renew",
    )

    DESTRUCTIVE_PREFIXES = (
        "delete",
        "terminate",
        "destroy",
        "remove",
        "deregister",
        "revoke",
        "cancel",
        "purge",
        "release",
        "deprecate",
    )

    # Service-specific overrides (some operations don't follow naming conventions)
    OPERATION_OVERRIDES: dict[tuple[str, str], OperationCategory] = {
        # Operations that look like reads but are actually writes
        ("logs", "put_log_events"): OperationCategory.WRITE,
        ("kinesis", "put_record"): OperationCategory.WRITE,
        ("kinesis", "put_records"): OperationCategory.WRITE,
        ("firehose", "put_record"): OperationCategory.WRITE,
        ("firehose", "put_record_batch"): OperationCategory.WRITE,
        # Operations that look like writes but are reads
        ("logs", "filter_log_events"): OperationCategory.READ,
        ("logs", "get_log_events"): OperationCategory.READ,
        ("cloudwatch", "get_metric_data"): OperationCategory.READ,
        ("cloudwatch", "get_metric_statistics"): OperationCategory.READ,
        # Explicitly destructive operations that don't follow prefix convention
        ("ec2", "terminate_instances"): OperationCategory.DESTRUCTIVE,
        ("autoscaling", "terminate_instance_in_auto_scaling_group"): OperationCategory.DESTRUCTIVE,
        ("ecs", "deregister_container_instance"): OperationCategory.DESTRUCTIVE,
        ("ecs", "deregister_task_definition"): OperationCategory.DESTRUCTIVE,
        ("lambda", "delete_function"): OperationCategory.DESTRUCTIVE,
        ("s3", "delete_object"): OperationCategory.DESTRUCTIVE,
        ("s3", "delete_objects"): OperationCategory.DESTRUCTIVE,
        ("s3", "delete_bucket"): OperationCategory.DESTRUCTIVE,
        ("dynamodb", "delete_table"): OperationCategory.DESTRUCTIVE,
        ("dynamodb", "delete_item"): OperationCategory.DESTRUCTIVE,
        ("rds", "delete_db_instance"): OperationCategory.DESTRUCTIVE,
        ("rds", "delete_db_cluster"): OperationCategory.DESTRUCTIVE,
    }

    # Operations that support DryRun parameter for safe testing
    DRY_RUN_SUPPORTED: dict[str, set[str]] = {
        "ec2": {
            "run_instances",
            "start_instances",
            "stop_instances",
            "terminate_instances",
            "create_security_group",
            "delete_security_group",
            "authorize_security_group_ingress",
            "authorize_security_group_egress",
            "revoke_security_group_ingress",
            "revoke_security_group_egress",
            "create_vpc",
            "delete_vpc",
            "create_subnet",
            "delete_subnet",
            "create_internet_gateway",
            "delete_internet_gateway",
            "attach_internet_gateway",
            "detach_internet_gateway",
            "create_nat_gateway",
            "delete_nat_gateway",
            "create_route_table",
            "delete_route_table",
            "create_route",
            "delete_route",
            "create_volume",
            "delete_volume",
            "attach_volume",
            "detach_volume",
            "create_snapshot",
            "delete_snapshot",
            "create_image",
            "deregister_image",
            "create_key_pair",
            "delete_key_pair",
            "import_key_pair",
            "create_launch_template",
            "delete_launch_template",
            "modify_instance_attribute",
            "modify_volume",
        },
    }

    @classmethod
    @lru_cache(maxsize=1000)
    def classify(cls, service: str, operation: str) -> OperationCategory:
        """
        Classify an AWS operation by its impact level.

        Args:
            service: AWS service name (e.g., 'ec2', 's3')
            operation: Operation name (e.g., 'describe_instances', 'delete_bucket')

        Returns:
            OperationCategory indicating the impact level
        """
        # Normalize inputs
        service_lower = service.lower()
        operation_lower = operation.lower()

        # Check overrides first
        key = (service_lower, operation_lower)
        if key in cls.OPERATION_OVERRIDES:
            return cls.OPERATION_OVERRIDES[key]

        # Check prefixes in priority order (destructive > write > read)
        for prefix in cls.DESTRUCTIVE_PREFIXES:
            if operation_lower.startswith(prefix):
                return OperationCategory.DESTRUCTIVE

        for prefix in cls.WRITE_PREFIXES:
            if operation_lower.startswith(prefix):
                return OperationCategory.WRITE

        for prefix in cls.READ_PREFIXES:
            if operation_lower.startswith(prefix):
                return OperationCategory.READ

        # Default to WRITE for unknown operations (conservative)
        return OperationCategory.WRITE

    @classmethod
    def supports_dry_run(cls, service: str, operation: str) -> bool:
        """Check if an operation supports the DryRun parameter."""
        service_lower = service.lower()
        operation_lower = operation.lower()
        return operation_lower in cls.DRY_RUN_SUPPORTED.get(service_lower, set())

    @classmethod
    def get_category_description(cls, category: OperationCategory) -> str:
        """Get a human-readable description of a category."""
        descriptions = {
            OperationCategory.READ: "Read-only operation that doesn't modify resources",
            OperationCategory.WRITE: "Write operation that creates or modifies resources",
            OperationCategory.DESTRUCTIVE: "Destructive operation that deletes or terminates resources",
            OperationCategory.BLOCKED: "Operation that is blocked for security reasons",
        }
        return descriptions.get(category, "Unknown operation category")

    @classmethod
    def get_allowed_categories_for_mode(cls, mode: str) -> set[OperationCategory]:
        """Get allowed operation categories for a safety mode."""
        from aws_sage.config import SafetyMode

        mode_enum = SafetyMode(mode) if isinstance(mode, str) else mode

        if mode_enum == SafetyMode.READ_ONLY:
            return {OperationCategory.READ}
        elif mode_enum == SafetyMode.STANDARD:
            return {OperationCategory.READ, OperationCategory.WRITE, OperationCategory.DESTRUCTIVE}
        elif mode_enum == SafetyMode.UNRESTRICTED:
            return {OperationCategory.READ, OperationCategory.WRITE, OperationCategory.DESTRUCTIVE}
        else:
            return {OperationCategory.READ}


def classify_operation(service: str, operation: str) -> OperationCategory:
    """Convenience function to classify an operation."""
    return OperationClassifier.classify(service, operation)
