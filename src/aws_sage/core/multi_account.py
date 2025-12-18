"""Multi-account management for AWS MCP Pro.

Supports cross-account access via STS AssumeRole.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, ClassVar

import boto3
import structlog
from botocore.exceptions import ClientError

logger = structlog.get_logger()


@dataclass
class AssumedRoleCredentials:
    """Credentials from an assumed role."""

    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: datetime

    def is_expired(self) -> bool:
        """Check if credentials are expired or about to expire."""
        # Consider expired 5 minutes before actual expiration
        buffer = timedelta(minutes=5)
        return datetime.now(self.expiration.tzinfo) >= (self.expiration - buffer)


@dataclass
class AccountContext:
    """Context for an AWS account."""

    account_id: str
    role_arn: str | None = None
    alias: str | None = None
    is_active: bool = False
    credentials: AssumedRoleCredentials | None = None
    session_name: str | None = None
    external_id: str | None = None
    tags: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "account_id": self.account_id,
            "role_arn": self.role_arn,
            "alias": self.alias,
            "is_active": self.is_active,
            "has_credentials": self.credentials is not None,
            "credentials_expired": (
                self.credentials.is_expired() if self.credentials else None
            ),
            "session_name": self.session_name,
            "tags": self.tags,
        }


@dataclass
class AssumeRoleResult:
    """Result of assuming a role."""

    success: bool
    account: AccountContext | None = None
    message: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "account": self.account.to_dict() if self.account else None,
            "message": self.message,
            "warnings": self.warnings,
        }


class MultiAccountManager:
    """Manages multiple AWS accounts and cross-account access."""

    _instance: ClassVar["MultiAccountManager | None"] = None
    _accounts: dict[str, AccountContext]
    _active_account: str | None

    def __init__(self) -> None:
        """Initialize with default account from current credentials."""
        self._accounts = {}
        self._active_account = None
        self._base_session = boto3.Session()
        self._initialize_default_account()

    @classmethod
    def get_instance(cls) -> "MultiAccountManager":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = MultiAccountManager()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        cls._instance = None

    def _initialize_default_account(self) -> None:
        """Initialize with the default account from current credentials."""
        try:
            sts = self._base_session.client("sts")
            identity = sts.get_caller_identity()
            account_id = identity["Account"]

            self._accounts[account_id] = AccountContext(
                account_id=account_id,
                alias="default",
                is_active=True,
            )
            self._active_account = account_id

            logger.info("initialized_default_account", account_id=account_id)

        except Exception as e:
            logger.warning("failed_to_initialize_default_account", error=str(e))

    def list_accounts(self) -> list[AccountContext]:
        """List all configured accounts."""
        return list(self._accounts.values())

    def get_account(self, account_id_or_alias: str) -> AccountContext | None:
        """Get an account by ID or alias."""
        # Try by account ID first
        if account_id_or_alias in self._accounts:
            return self._accounts[account_id_or_alias]

        # Try by alias
        for account in self._accounts.values():
            if account.alias == account_id_or_alias:
                return account

        return None

    def get_active_account(self) -> AccountContext | None:
        """Get the currently active account."""
        if self._active_account:
            return self._accounts.get(self._active_account)
        return None

    def assume_role(
        self,
        role_arn: str,
        session_name: str | None = None,
        duration_seconds: int = 3600,
        external_id: str | None = None,
        alias: str | None = None,
    ) -> AssumeRoleResult:
        """Assume a role in another account.

        Args:
            role_arn: ARN of the role to assume
            session_name: Session name for the assumed role
            duration_seconds: Duration for the credentials (default 1 hour)
            external_id: External ID for cross-account access (if required)
            alias: Optional alias for the account

        Returns:
            AssumeRoleResult with success status and account context
        """
        warnings: list[str] = []

        # Extract account ID from role ARN
        try:
            # Format: arn:aws:iam::123456789012:role/RoleName
            parts = role_arn.split(":")
            if len(parts) < 5 or parts[2] != "iam":
                return AssumeRoleResult(
                    success=False,
                    message=f"Invalid role ARN format: {role_arn}",
                )
            account_id = parts[4]
        except Exception as e:
            return AssumeRoleResult(
                success=False,
                message=f"Failed to parse role ARN: {e!s}",
            )

        # Generate session name if not provided
        if not session_name:
            session_name = f"aws-sage-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Assume the role
        try:
            sts = self._base_session.client("sts")

            assume_params = {
                "RoleArn": role_arn,
                "RoleSessionName": session_name,
                "DurationSeconds": duration_seconds,
            }
            if external_id:
                assume_params["ExternalId"] = external_id

            response = sts.assume_role(**assume_params)

            credentials = AssumedRoleCredentials(
                access_key_id=response["Credentials"]["AccessKeyId"],
                secret_access_key=response["Credentials"]["SecretAccessKey"],
                session_token=response["Credentials"]["SessionToken"],
                expiration=response["Credentials"]["Expiration"],
            )

            # Create or update account context
            account = AccountContext(
                account_id=account_id,
                role_arn=role_arn,
                alias=alias or f"account-{account_id}",
                is_active=False,
                credentials=credentials,
                session_name=session_name,
                external_id=external_id,
            )
            self._accounts[account_id] = account

            logger.info(
                "assumed_role",
                role_arn=role_arn,
                account_id=account_id,
                expires=credentials.expiration.isoformat(),
            )

            # Warn about cross-account operations
            warnings.append(
                f"Role assumed in account {account_id}. "
                "Use switch_account to make this the active account."
            )

            return AssumeRoleResult(
                success=True,
                account=account,
                message=f"Successfully assumed role in account {account_id}",
                warnings=warnings,
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "AccessDenied":
                return AssumeRoleResult(
                    success=False,
                    message=f"Access denied when assuming role: {error_message}",
                )
            elif error_code == "MalformedPolicyDocument":
                return AssumeRoleResult(
                    success=False,
                    message="The trust policy on the role is malformed",
                )
            else:
                return AssumeRoleResult(
                    success=False,
                    message=f"Failed to assume role: {error_message}",
                )

        except Exception as e:
            return AssumeRoleResult(
                success=False,
                message=f"Unexpected error assuming role: {e!s}",
            )

    def switch_account(self, account_id_or_alias: str) -> AssumeRoleResult:
        """Switch to a different account context.

        Args:
            account_id_or_alias: Account ID or alias to switch to

        Returns:
            AssumeRoleResult with success status
        """
        warnings: list[str] = []

        account = self.get_account(account_id_or_alias)
        if not account:
            available = [
                f"{a.account_id} ({a.alias})" for a in self._accounts.values()
            ]
            return AssumeRoleResult(
                success=False,
                message=(
                    f"Account '{account_id_or_alias}' not found. "
                    f"Available accounts: {', '.join(available)}"
                ),
            )

        # Check if credentials are expired (for assumed roles)
        if account.credentials and account.credentials.is_expired():
            return AssumeRoleResult(
                success=False,
                message=(
                    f"Credentials for account {account.account_id} have expired. "
                    "Use assume_role to refresh credentials."
                ),
            )

        # Deactivate current account
        if self._active_account and self._active_account in self._accounts:
            self._accounts[self._active_account].is_active = False

        # Activate new account
        account.is_active = True
        self._active_account = account.account_id

        # Warn about cross-account operations
        if account.role_arn:
            warnings.append(
                f"WARNING: Now operating in account {account.account_id} "
                f"via role {account.role_arn}. "
                "Operations will affect resources in this account."
            )

        logger.info("switched_account", account_id=account.account_id, alias=account.alias)

        return AssumeRoleResult(
            success=True,
            account=account,
            message=f"Switched to account {account.account_id} ({account.alias})",
            warnings=warnings,
        )

    def get_session(self) -> boto3.Session:
        """Get a boto3 session for the active account.

        Returns:
            boto3.Session configured for the active account
        """
        account = self.get_active_account()

        if account and account.credentials and not account.credentials.is_expired():
            return boto3.Session(
                aws_access_key_id=account.credentials.access_key_id,
                aws_secret_access_key=account.credentials.secret_access_key,
                aws_session_token=account.credentials.session_token,
            )

        return self._base_session

    def get_account_info(self) -> dict[str, Any]:
        """Get information about the current account context.

        Returns:
            Dictionary with account context information
        """
        account = self.get_active_account()
        if not account:
            return {
                "error": "No active account",
                "accounts_configured": len(self._accounts),
            }

        return {
            "account_id": account.account_id,
            "alias": account.alias,
            "is_assumed_role": account.role_arn is not None,
            "role_arn": account.role_arn,
            "session_name": account.session_name,
            "credentials_status": (
                "expired"
                if account.credentials and account.credentials.is_expired()
                else "valid"
                if account.credentials
                else "default"
            ),
            "accounts_configured": len(self._accounts),
        }


# Global singleton accessor
def get_multi_account_manager() -> MultiAccountManager:
    """Get the global MultiAccountManager instance."""
    return MultiAccountManager.get_instance()


def reset_multi_account_manager() -> None:
    """Reset the global MultiAccountManager instance (for testing)."""
    MultiAccountManager.reset_instance()
