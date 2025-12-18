"""Core modules for AWS MCP Pro."""

from aws_sage.core.environment import (
    DEFAULT_LOCALSTACK_CONFIG,
    DEFAULT_PRODUCTION_CONFIG,
    LOCALSTACK_COMMUNITY_SERVICES,
    LOCALSTACK_PRO_SERVICES,
    EnvironmentConfig,
    EnvironmentType,
)
from aws_sage.core.environment_manager import (
    EnvironmentManager,
    EnvironmentSwitchResult,
    get_environment_manager,
    reset_environment_manager,
)
from aws_sage.core.exceptions import (
    AWSMCPError,
    AuthenticationError,
    OperationBlockedError,
    ParseError,
    SafetyError,
    ValidationError,
)
from aws_sage.core.multi_account import (
    AccountContext,
    AssumedRoleCredentials,
    AssumeRoleResult,
    MultiAccountManager,
    get_multi_account_manager,
    reset_multi_account_manager,
)
from aws_sage.core.session import SessionManager, get_session_manager

__all__ = [
    # Environment
    "DEFAULT_LOCALSTACK_CONFIG",
    "DEFAULT_PRODUCTION_CONFIG",
    "EnvironmentConfig",
    "EnvironmentManager",
    "EnvironmentSwitchResult",
    "EnvironmentType",
    "LOCALSTACK_COMMUNITY_SERVICES",
    "LOCALSTACK_PRO_SERVICES",
    "get_environment_manager",
    "reset_environment_manager",
    # Exceptions
    "AWSMCPError",
    "AuthenticationError",
    "OperationBlockedError",
    "ParseError",
    "SafetyError",
    "ValidationError",
    # Multi-Account
    "AccountContext",
    "AssumedRoleCredentials",
    "AssumeRoleResult",
    "MultiAccountManager",
    "get_multi_account_manager",
    "reset_multi_account_manager",
    # Session
    "SessionManager",
    "get_session_manager",
]
