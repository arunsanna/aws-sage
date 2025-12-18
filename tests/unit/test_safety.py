"""Tests for the safety module."""

import pytest

from aws_sage.config import OperationCategory, SafetyMode
from aws_sage.core.exceptions import OperationBlockedError, SafetyError
from aws_sage.safety.classifier import OperationClassifier
from aws_sage.safety.denylist import (
    DENYLIST,
    get_block_reason,
    is_operation_blocked,
    requires_double_confirmation,
)
from aws_sage.safety.validator import SafetyDecision, SafetyEnforcer


class TestOperationClassifier:
    """Tests for OperationClassifier."""

    def test_classify_read_operations(self) -> None:
        """Test classification of read operations."""
        read_ops = [
            ("s3", "list_buckets"),
            ("ec2", "describe_instances"),
            ("lambda", "get_function"),
            ("iam", "list_roles"),
            ("dynamodb", "scan"),
        ]
        for service, operation in read_ops:
            result = OperationClassifier.classify(service, operation)
            assert result == OperationCategory.READ, f"{service}.{operation} should be READ"

    def test_classify_write_operations(self) -> None:
        """Test classification of write operations."""
        write_ops = [
            ("s3", "create_bucket"),
            ("ec2", "start_instances"),
            ("lambda", "update_function_code"),
            ("iam", "attach_role_policy"),
            ("dynamodb", "put_item"),
        ]
        for service, operation in write_ops:
            result = OperationClassifier.classify(service, operation)
            assert result == OperationCategory.WRITE, f"{service}.{operation} should be WRITE"

    def test_classify_destructive_operations(self) -> None:
        """Test classification of destructive operations."""
        destructive_ops = [
            ("s3", "delete_bucket"),
            ("ec2", "terminate_instances"),
            ("lambda", "delete_function"),
            ("iam", "delete_role"),
            ("dynamodb", "delete_table"),
        ]
        for service, operation in destructive_ops:
            result = OperationClassifier.classify(service, operation)
            assert (
                result == OperationCategory.DESTRUCTIVE
            ), f"{service}.{operation} should be DESTRUCTIVE"

    def test_classify_override_operations(self) -> None:
        """Test that overrides work correctly."""
        # logs.filter_log_events looks like a write but is actually a read
        result = OperationClassifier.classify("logs", "filter_log_events")
        assert result == OperationCategory.READ

    def test_supports_dry_run(self) -> None:
        """Test dry run detection."""
        assert OperationClassifier.supports_dry_run("ec2", "run_instances")
        assert OperationClassifier.supports_dry_run("ec2", "terminate_instances")
        assert not OperationClassifier.supports_dry_run("s3", "delete_bucket")


class TestDenylist:
    """Tests for the denylist."""

    def test_blocked_operations_in_denylist(self) -> None:
        """Test that critical operations are in the denylist."""
        critical_ops = [
            ("cloudtrail", "delete_trail"),
            ("cloudtrail", "stop_logging"),
            ("guardduty", "delete_detector"),
            ("iam", "delete_account_password_policy"),
            ("organizations", "leave_organization"),
            ("kms", "schedule_key_deletion"),
        ]
        for service, operation in critical_ops:
            assert is_operation_blocked(
                service, operation
            ), f"{service}.{operation} should be blocked"

    def test_normal_operations_not_blocked(self) -> None:
        """Test that normal operations are not blocked."""
        normal_ops = [
            ("s3", "list_buckets"),
            ("ec2", "describe_instances"),
            ("lambda", "list_functions"),
        ]
        for service, operation in normal_ops:
            assert not is_operation_blocked(
                service, operation
            ), f"{service}.{operation} should not be blocked"

    def test_double_confirmation_required(self) -> None:
        """Test double confirmation requirements."""
        assert requires_double_confirmation("ec2", "terminate_instances")
        assert requires_double_confirmation("rds", "delete_db_instance")
        assert not requires_double_confirmation("s3", "list_buckets")

    def test_get_block_reason(self) -> None:
        """Test that block reasons are provided."""
        reason = get_block_reason("cloudtrail", "delete_trail")
        assert reason is not None
        assert "security" in reason.lower() or "audit" in reason.lower()


class TestSafetyEnforcer:
    """Tests for SafetyEnforcer."""

    def test_read_only_mode_allows_reads(self, safety_enforcer: SafetyEnforcer) -> None:
        """Test that read-only mode allows read operations."""
        decision = safety_enforcer.evaluate("s3", "list_buckets")
        assert decision.allowed
        assert decision.category == OperationCategory.READ
        assert not decision.requires_confirmation

    def test_read_only_mode_blocks_writes(self, safety_enforcer: SafetyEnforcer) -> None:
        """Test that read-only mode blocks write operations."""
        decision = safety_enforcer.evaluate("s3", "create_bucket")
        assert not decision.allowed
        assert decision.category == OperationCategory.WRITE
        assert decision.suggested_mode == SafetyMode.STANDARD

    def test_read_only_mode_blocks_destructive(self, safety_enforcer: SafetyEnforcer) -> None:
        """Test that read-only mode blocks destructive operations."""
        decision = safety_enforcer.evaluate("s3", "delete_bucket")
        assert not decision.allowed
        assert decision.category == OperationCategory.DESTRUCTIVE

    def test_standard_mode_allows_writes(self, safety_enforcer_standard: SafetyEnforcer) -> None:
        """Test that standard mode allows write operations with confirmation."""
        decision = safety_enforcer_standard.evaluate("s3", "create_bucket")
        assert decision.allowed
        assert decision.requires_confirmation

    def test_standard_mode_allows_destructive_with_confirmation(
        self, safety_enforcer_standard: SafetyEnforcer
    ) -> None:
        """Test that standard mode allows destructive ops with confirmation."""
        decision = safety_enforcer_standard.evaluate("s3", "delete_bucket")
        assert decision.allowed
        assert decision.requires_confirmation

    def test_denylist_blocked_in_all_modes(
        self, safety_enforcer_unrestricted: SafetyEnforcer
    ) -> None:
        """Test that denylist operations are blocked even in unrestricted mode."""
        decision = safety_enforcer_unrestricted.evaluate("cloudtrail", "delete_trail")
        assert not decision.allowed
        assert decision.category == OperationCategory.BLOCKED

    def test_resource_count_limit(self, safety_enforcer_standard: SafetyEnforcer) -> None:
        """Test that bulk operations are limited."""
        # Create parameters with many instances
        params = {"InstanceIds": [f"i-{i:08d}" for i in range(100)]}
        decision = safety_enforcer_standard.evaluate("ec2", "terminate_instances", params)
        assert not decision.allowed
        assert "resources" in decision.reason.lower()

    def test_enforce_raises_on_blocked(self, safety_enforcer: SafetyEnforcer) -> None:
        """Test that enforce() raises exceptions for blocked operations."""
        with pytest.raises(SafetyError):
            safety_enforcer.enforce("s3", "create_bucket")

    def test_enforce_raises_operation_blocked_for_denylist(
        self, safety_enforcer_unrestricted: SafetyEnforcer
    ) -> None:
        """Test that denylist operations raise OperationBlockedError."""
        with pytest.raises(OperationBlockedError):
            safety_enforcer_unrestricted.enforce("cloudtrail", "delete_trail")

    def test_set_mode(self, safety_enforcer: SafetyEnforcer) -> None:
        """Test changing safety mode."""
        assert safety_enforcer.get_mode() == SafetyMode.READ_ONLY
        safety_enforcer.set_mode(SafetyMode.STANDARD)
        assert safety_enforcer.get_mode() == SafetyMode.STANDARD


class TestSafetyDecision:
    """Tests for SafetyDecision."""

    def test_to_dict_allowed(self) -> None:
        """Test to_dict for allowed operations."""
        decision = SafetyDecision(
            allowed=True,
            category=OperationCategory.READ,
            requires_confirmation=False,
        )
        result = decision.to_dict()
        assert result["allowed"] is True
        assert result["category"] == "read"
        assert "reason" not in result

    def test_to_dict_blocked(self) -> None:
        """Test to_dict for blocked operations."""
        decision = SafetyDecision(
            allowed=False,
            category=OperationCategory.WRITE,
            reason="Operation not allowed in read_only mode",
            suggested_mode=SafetyMode.STANDARD,
        )
        result = decision.to_dict()
        assert result["allowed"] is False
        assert result["reason"] == "Operation not allowed in read_only mode"
        assert result["suggested_mode"] == "standard"
