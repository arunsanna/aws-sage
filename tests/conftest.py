"""Pytest configuration and fixtures for AWS MCP Pro tests."""

import os
from typing import Generator

import boto3
import pytest
from moto import mock_aws

from aws_sage.config import SafetyConfig, SafetyMode, ServerConfig, reset_config, set_config
from aws_sage.core.context import ConversationContext, reset_context
from aws_sage.core.session import SessionManager, reset_session_manager
from aws_sage.execution.engine import reset_execution_engine
from aws_sage.safety.validator import SafetyEnforcer, reset_safety_enforcer


@pytest.fixture(autouse=True)
def reset_globals() -> Generator[None, None, None]:
    """Reset global state before each test."""
    yield
    reset_session_manager()
    reset_context()
    reset_safety_enforcer()
    reset_execution_engine()
    reset_config()


@pytest.fixture
def aws_credentials() -> Generator[None, None, None]:
    """Mock AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    yield
    # Cleanup
    for key in [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SECURITY_TOKEN",
        "AWS_SESSION_TOKEN",
    ]:
        os.environ.pop(key, None)


@pytest.fixture
def mock_aws_services(aws_credentials: None) -> Generator[None, None, None]:
    """Mock all AWS services with moto."""
    with mock_aws():
        yield


@pytest.fixture
def session_manager() -> SessionManager:
    """Create a fresh session manager."""
    return SessionManager()


@pytest.fixture
def context() -> ConversationContext:
    """Create a fresh conversation context."""
    return ConversationContext()


@pytest.fixture
def safety_enforcer() -> SafetyEnforcer:
    """Create a safety enforcer with default config."""
    return SafetyEnforcer()


@pytest.fixture
def safety_enforcer_standard() -> SafetyEnforcer:
    """Create a safety enforcer in standard mode."""
    config = SafetyConfig(mode=SafetyMode.STANDARD)
    return SafetyEnforcer(config)


@pytest.fixture
def safety_enforcer_unrestricted() -> SafetyEnforcer:
    """Create a safety enforcer in unrestricted mode."""
    config = SafetyConfig(mode=SafetyMode.UNRESTRICTED)
    return SafetyEnforcer(config)


@pytest.fixture
def server_config() -> ServerConfig:
    """Create a test server config."""
    return ServerConfig(
        default_region="us-east-1",
        safety=SafetyConfig(mode=SafetyMode.READ_ONLY),
    )


@pytest.fixture
def configured_server(server_config: ServerConfig) -> Generator[ServerConfig, None, None]:
    """Set up server with test config."""
    set_config(server_config)
    yield server_config


@pytest.fixture
def s3_client(mock_aws_services: None) -> boto3.client:
    """Create a mocked S3 client."""
    return boto3.client("s3", region_name="us-east-1")


@pytest.fixture
def ec2_client(mock_aws_services: None) -> boto3.client:
    """Create a mocked EC2 client."""
    return boto3.client("ec2", region_name="us-east-1")


@pytest.fixture
def iam_client(mock_aws_services: None) -> boto3.client:
    """Create a mocked IAM client."""
    return boto3.client("iam", region_name="us-east-1")


@pytest.fixture
def lambda_client(mock_aws_services: None) -> boto3.client:
    """Create a mocked Lambda client."""
    return boto3.client("lambda", region_name="us-east-1")
