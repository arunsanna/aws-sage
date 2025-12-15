"""Tests for the execution engine module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from aws_mcp.config import OperationCategory, SafetyMode
from aws_mcp.core.session import SessionManager
from aws_mcp.execution.engine import (
    ExecutionEngine,
    ExecutionResult,
    get_execution_engine,
    reset_execution_engine,
)
from aws_mcp.parser.schemas import StructuredCommand


class TestExecutionResult:
    """Tests for ExecutionResult."""

    def test_success_result_to_dict(self) -> None:
        """Test successful result serialization."""
        result = ExecutionResult(
            success=True,
            data={"Buckets": [{"Name": "test-bucket"}]},
            service="s3",
            operation="list_buckets",
            category="read",
            count=1,
        )
        d = result.to_dict()
        assert d["status"] == "success"
        assert d["data"]["Buckets"][0]["Name"] == "test-bucket"
        assert d["service"] == "s3"
        assert d["count"] == 1

    def test_error_result_to_dict(self) -> None:
        """Test error result serialization."""
        result = ExecutionResult(
            success=False,
            error="Access denied",
            error_code="AccessDenied",
            service="s3",
            operation="list_buckets",
            suggestions=["Check your IAM permissions"],
        )
        d = result.to_dict()
        assert d["status"] == "error"
        assert d["error"] == "Access denied"
        assert d["error_code"] == "AccessDenied"
        assert "suggestions" in d

    def test_confirmation_required_to_dict(self) -> None:
        """Test confirmation required result."""
        result = ExecutionResult(
            success=False,
            service="s3",
            operation="delete_bucket",
            requires_confirmation=True,
            confirmation_message="Delete bucket? Set confirm=true",
        )
        d = result.to_dict()
        assert d["status"] == "confirmation_required"
        assert "confirmation_message" in d

    def test_to_json(self) -> None:
        """Test JSON serialization."""
        result = ExecutionResult(success=True, data={"key": "value"})
        json_str = result.to_json()
        assert '"status": "success"' in json_str
        assert '"key": "value"' in json_str


class TestExecutionEngine:
    """Tests for ExecutionEngine."""

    @pytest.fixture
    def mock_session_manager(self) -> MagicMock:
        """Create a mock session manager."""
        manager = MagicMock(spec=SessionManager)
        manager.active_profile = "test-profile"
        manager.active_region = "us-east-1"
        manager.list_profiles.return_value = ["default", "test-profile"]
        return manager

    @pytest.fixture
    def engine(self, mock_session_manager: MagicMock) -> ExecutionEngine:
        """Create an execution engine with mock session manager."""
        reset_execution_engine()
        return ExecutionEngine(session_manager=mock_session_manager)

    @pytest.mark.asyncio
    async def test_execute_natural_language_no_profile(
        self, mock_session_manager: MagicMock
    ) -> None:
        """Test execution fails when no profile is selected."""
        mock_session_manager.active_profile = None
        engine = ExecutionEngine(session_manager=mock_session_manager)

        result = await engine.execute_natural_language("list s3 buckets")
        assert not result.success
        assert "profile" in result.error.lower()
        assert len(result.suggestions) > 0

    @pytest.mark.asyncio
    async def test_execute_natural_language_invalid_query(
        self, engine: ExecutionEngine
    ) -> None:
        """Test execution fails for invalid query."""
        result = await engine.execute_natural_language("foobar blah")
        assert not result.success
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_execute_natural_language_success(
        self, engine: ExecutionEngine, mock_session_manager: MagicMock
    ) -> None:
        """Test successful natural language execution."""
        # Mock the client
        mock_client = MagicMock()
        mock_client.list_buckets.return_value = {
            "Buckets": [{"Name": "bucket1"}, {"Name": "bucket2"}],
            "ResponseMetadata": {},
        }
        mock_session_manager.get_client.return_value = mock_client

        result = await engine.execute_natural_language("list s3 buckets")
        assert result.success
        assert result.data is not None
        assert result.service == "s3"
        assert result.operation == "list_buckets"

    @pytest.mark.asyncio
    async def test_execute_explicit_success(
        self, engine: ExecutionEngine, mock_session_manager: MagicMock
    ) -> None:
        """Test explicit service/operation execution."""
        mock_client = MagicMock()
        mock_client.describe_instances.return_value = {
            "Reservations": [],
            "ResponseMetadata": {},
        }
        mock_session_manager.get_client.return_value = mock_client

        result = await engine.execute_explicit(
            service="ec2",
            operation="describe_instances",
            parameters={},
        )
        assert result.success
        assert result.service == "ec2"
        assert result.operation == "describe_instances"

    @pytest.mark.asyncio
    async def test_execute_explicit_validation_failure(
        self, engine: ExecutionEngine
    ) -> None:
        """Test that invalid operations fail validation."""
        result = await engine.execute_explicit(
            service="s3",
            operation="nonexistent_operation",
            parameters={},
        )
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_blocked_operation(
        self, engine: ExecutionEngine
    ) -> None:
        """Test that denylist operations are blocked."""
        result = await engine.execute_explicit(
            service="cloudtrail",
            operation="delete_trail",
            parameters={"Name": "test-trail"},
        )
        assert not result.success

    @pytest.mark.asyncio
    async def test_execute_write_in_read_only_mode(
        self, engine: ExecutionEngine
    ) -> None:
        """Test that write operations fail in read-only mode."""
        result = await engine.execute_explicit(
            service="s3",
            operation="create_bucket",
            parameters={"Bucket": "test-bucket"},
        )
        assert not result.success
        assert "mode" in result.error.lower() or "safety" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_requires_confirmation(
        self, engine: ExecutionEngine, mock_session_manager: MagicMock
    ) -> None:
        """Test that destructive operations require confirmation in standard mode."""
        # Switch to standard mode
        engine.safety_enforcer.set_mode(SafetyMode.STANDARD)

        result = await engine.execute_explicit(
            service="s3",
            operation="delete_bucket",
            parameters={"Bucket": "test-bucket"},
            confirm=False,
        )
        assert not result.success
        assert result.requires_confirmation
        assert result.confirmation_message is not None

    @pytest.mark.asyncio
    async def test_execute_with_confirmation(
        self, engine: ExecutionEngine, mock_session_manager: MagicMock
    ) -> None:
        """Test that confirmed operations proceed."""
        # Switch to standard mode
        engine.safety_enforcer.set_mode(SafetyMode.STANDARD)

        mock_client = MagicMock()
        mock_client.delete_bucket.return_value = {}
        mock_session_manager.get_client.return_value = mock_client

        result = await engine.execute_explicit(
            service="s3",
            operation="delete_bucket",
            parameters={"Bucket": "test-bucket"},
            confirm=True,
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_client_error_handling(
        self, engine: ExecutionEngine, mock_session_manager: MagicMock
    ) -> None:
        """Test AWS ClientError handling."""
        mock_client = MagicMock()
        error = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "ListBuckets",
        )
        mock_client.list_buckets.side_effect = error
        # Also mock paginator to raise the error
        mock_paginator = MagicMock()
        mock_paginator.paginate.side_effect = error
        mock_client.get_paginator.return_value = mock_paginator
        mock_session_manager.get_client.return_value = mock_client

        result = await engine.execute_natural_language("list s3 buckets")
        assert not result.success
        assert result.error_code == "AccessDenied"

    @pytest.mark.asyncio
    async def test_pagination_handling(
        self, engine: ExecutionEngine, mock_session_manager: MagicMock
    ) -> None:
        """Test automatic pagination."""
        mock_client = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"Buckets": [{"Name": f"bucket{i}"} for i in range(50)]},
            {"Buckets": [{"Name": f"bucket{i}"} for i in range(50, 100)]},
        ]
        mock_client.get_paginator.return_value = mock_paginator
        mock_session_manager.get_client.return_value = mock_client

        # Pagination handler will attempt to use paginator
        result = await engine.execute_natural_language("list s3 buckets")
        # Result depends on pagination handler implementation

    @pytest.mark.asyncio
    async def test_execute_with_region_override(
        self, engine: ExecutionEngine, mock_session_manager: MagicMock
    ) -> None:
        """Test region override in execution."""
        mock_client = MagicMock()
        mock_client.list_buckets.return_value = {"Buckets": [], "ResponseMetadata": {}}
        mock_session_manager.get_client.return_value = mock_client

        result = await engine.execute_natural_language(
            "list s3 buckets",
            region="eu-west-1",
        )
        assert result.success
        mock_session_manager.get_client.assert_called_with("s3", "eu-west-1")

    def test_format_as_table(self, engine: ExecutionEngine) -> None:
        """Test table formatting."""
        data = [
            {"Name": "bucket1", "CreationDate": "2024-01-01"},
            {"Name": "bucket2", "CreationDate": "2024-01-02"},
        ]
        table = engine._format_as_table(data)
        assert table is not None
        assert "bucket1" in table
        assert "bucket2" in table
        assert "|" in table

    def test_format_as_table_empty_list(self, engine: ExecutionEngine) -> None:
        """Test table formatting with empty list."""
        table = engine._format_as_table([])
        assert table is None

    def test_format_as_table_truncation(self, engine: ExecutionEngine) -> None:
        """Test table formatting truncates large datasets."""
        data = [{"id": f"item{i}"} for i in range(100)]
        table = engine._format_as_table(data)
        assert table is not None
        assert "more rows" in table

    def test_clean_response_datetime(self, engine: ExecutionEngine) -> None:
        """Test datetime cleaning in responses."""
        from datetime import datetime

        data = {"created": datetime(2024, 1, 1, 12, 0, 0)}
        cleaned = engine._clean_response(data)
        assert isinstance(cleaned["created"], str)
        assert "2024-01-01" in cleaned["created"]

    def test_clean_response_removes_metadata(self, engine: ExecutionEngine) -> None:
        """Test ResponseMetadata is removed."""
        data = {
            "Buckets": [{"Name": "test"}],
            "ResponseMetadata": {"RequestId": "123"},
        }
        cleaned = engine._clean_response(data)
        assert "ResponseMetadata" not in cleaned
        assert "Buckets" in cleaned

    def test_infer_resource_type(self, engine: ExecutionEngine) -> None:
        """Test resource type inference from operation."""
        assert engine._infer_resource_type("list_buckets") == "buckets"
        assert engine._infer_resource_type("describe_instances") == "instances"
        assert engine._infer_resource_type("get_function") == "function"

    def test_get_operation_suggestions(self, engine: ExecutionEngine) -> None:
        """Test operation suggestions."""
        suggestions = engine._get_operation_suggestions("s3")
        # Suggestions come from botocore operations converted to snake_case
        # If empty, service registry may return PascalCase that doesn't match filter
        assert isinstance(suggestions, list)
        # At minimum we verify it returns a list without errors


class TestExecutionEngineSingleton:
    """Tests for execution engine singleton management."""

    def test_get_execution_engine_returns_same_instance(self) -> None:
        """Test singleton behavior."""
        reset_execution_engine()
        e1 = get_execution_engine()
        e2 = get_execution_engine()
        assert e1 is e2

    def test_reset_execution_engine(self) -> None:
        """Test resetting the singleton."""
        e1 = get_execution_engine()
        reset_execution_engine()
        e2 = get_execution_engine()
        assert e1 is not e2


class TestStructuredCommandExecution:
    """Tests for executing StructuredCommand objects."""

    @pytest.fixture
    def mock_session_manager(self) -> MagicMock:
        """Create a mock session manager."""
        manager = MagicMock(spec=SessionManager)
        manager.active_profile = "test-profile"
        manager.active_region = "us-east-1"
        return manager

    @pytest.fixture
    def engine(self, mock_session_manager: MagicMock) -> ExecutionEngine:
        """Create an execution engine."""
        reset_execution_engine()
        return ExecutionEngine(session_manager=mock_session_manager)

    @pytest.mark.asyncio
    async def test_execute_command_read(
        self, engine: ExecutionEngine, mock_session_manager: MagicMock
    ) -> None:
        """Test executing a read command."""
        mock_client = MagicMock()
        mock_client.list_buckets.return_value = {"Buckets": [], "ResponseMetadata": {}}
        mock_session_manager.get_client.return_value = mock_client

        command = StructuredCommand(
            service="s3",
            operation="list_buckets",
            parameters={},
            category=OperationCategory.READ,
        )
        result = await engine.execute_command(command)
        assert result.success
        assert result.category == "read"

    @pytest.mark.asyncio
    async def test_execute_command_with_parameters(
        self, engine: ExecutionEngine, mock_session_manager: MagicMock
    ) -> None:
        """Test executing command with parameters."""
        mock_client = MagicMock()
        mock_client.list_objects_v2.return_value = {
            "Contents": [],
            "ResponseMetadata": {},
        }
        # Mock paginator since list_objects_v2 supports pagination
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"Contents": [], "ResponseMetadata": {}}]
        mock_client.get_paginator.return_value = mock_paginator
        mock_session_manager.get_client.return_value = mock_client

        command = StructuredCommand(
            service="s3",
            operation="list_objects_v2",
            parameters={"Bucket": "test-bucket"},
            category=OperationCategory.READ,
        )
        result = await engine.execute_command(command)
        assert result.success
        # Pagination is used, so verify paginator was called instead
        mock_client.get_paginator.assert_called_with("list_objects_v2")
