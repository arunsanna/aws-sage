"""AWS Session management for AWS MCP Pro."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import boto3
import structlog
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound

from aws_mcp.config import get_config
from aws_mcp.core.exceptions import AuthenticationError

logger = structlog.get_logger()


@dataclass
class AccountInfo:
    """Information about the current AWS account."""

    account_id: str
    user_id: str
    arn: str
    profile: str | None = None
    region: str | None = None


@dataclass
class SessionManager:
    """Manages AWS sessions and credentials."""

    active_profile: str | None = None
    active_region: str = field(default_factory=lambda: get_config().default_region)
    _session: boto3.Session | None = field(default=None, repr=False)
    _account_info: AccountInfo | None = field(default=None, repr=False)

    def list_profiles(self) -> list[str]:
        """List all available AWS profiles."""
        try:
            session = boto3.Session()
            profiles = session.available_profiles
            logger.info("listed_profiles", count=len(profiles))
            return sorted(profiles)
        except Exception as e:
            logger.error("failed_to_list_profiles", error=str(e))
            return []

    def get_profile_details(self) -> list[dict[str, Any]]:
        """Get detailed information about all profiles."""
        profiles = self.list_profiles()
        details = []

        config_path = Path.home() / ".aws" / "config"
        credentials_path = Path.home() / ".aws" / "credentials"

        for profile in profiles:
            info: dict[str, Any] = {"name": profile, "type": "unknown"}

            # Check if it's an SSO profile
            if config_path.exists():
                try:
                    content = config_path.read_text()
                    profile_section = f"[profile {profile}]" if profile != "default" else "[default]"
                    if profile_section in content:
                        section_start = content.find(profile_section)
                        section_end = content.find("\n[", section_start + 1)
                        section = (
                            content[section_start:section_end]
                            if section_end > 0
                            else content[section_start:]
                        )
                        if "sso_start_url" in section:
                            info["type"] = "sso"
                        elif "role_arn" in section:
                            info["type"] = "assume_role"
                        elif "source_profile" in section:
                            info["type"] = "chained"
                except Exception:
                    pass

            # Check if credentials exist
            if credentials_path.exists() and info["type"] == "unknown":
                try:
                    content = credentials_path.read_text()
                    if f"[{profile}]" in content:
                        info["type"] = "static"
                except Exception:
                    pass

            details.append(info)

        return details

    def select_profile(self, profile: str, region: str | None = None) -> AccountInfo:
        """Select an AWS profile and validate credentials."""
        # Check if profile exists
        available = self.list_profiles()
        if profile not in available:
            raise AuthenticationError(
                f"Profile '{profile}' not found",
                profile=profile,
                suggestion=f"Available profiles: {', '.join(available[:5])}{'...' if len(available) > 5 else ''}",
            )

        # Create new session
        region_to_use = region or self.active_region
        try:
            self._session = boto3.Session(profile_name=profile, region_name=region_to_use)
        except ProfileNotFound:
            raise AuthenticationError(f"Profile '{profile}' not found in AWS config", profile=profile)

        # Validate credentials
        try:
            sts = self._session.client("sts")
            identity = sts.get_caller_identity()

            self.active_profile = profile
            self.active_region = region_to_use
            self._account_info = AccountInfo(
                account_id=identity["Account"],
                user_id=identity["UserId"],
                arn=identity["Arn"],
                profile=profile,
                region=region_to_use,
            )

            logger.info(
                "profile_selected",
                profile=profile,
                region=region_to_use,
                account_id=identity["Account"],
            )

            return self._account_info

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if error_code in ["ExpiredToken", "ExpiredTokenException"]:
                raise AuthenticationError(
                    f"Credentials expired for profile '{profile}'",
                    profile=profile,
                    suggestion=f"Run 'aws sso login --profile {profile}' to refresh credentials",
                )
            elif error_code == "AccessDenied":
                raise AuthenticationError(
                    f"Access denied for profile '{profile}'",
                    profile=profile,
                    suggestion="Check IAM permissions or refresh SSO credentials",
                )
            else:
                raise AuthenticationError(f"Authentication failed: {error_message}", profile=profile)

        except NoCredentialsError:
            raise AuthenticationError(
                f"No credentials found for profile '{profile}'",
                profile=profile,
                suggestion="Run 'aws configure' or 'aws sso login' to set up credentials",
            )

    def get_session(self) -> boto3.Session:
        """Get the current boto3 session."""
        if self._session is None:
            if self.active_profile:
                self._session = boto3.Session(
                    profile_name=self.active_profile,
                    region_name=self.active_region,
                )
            else:
                self._session = boto3.Session(region_name=self.active_region)
        return self._session

    def get_client(self, service: str, region: str | None = None) -> Any:
        """Get a boto3 client for a service."""
        session = self.get_session()
        return session.client(service, region_name=region or self.active_region)

    def get_resource(self, service: str, region: str | None = None) -> Any:
        """Get a boto3 resource for a service."""
        session = self.get_session()
        return session.resource(service, region_name=region or self.active_region)

    def get_account_info(self) -> AccountInfo | None:
        """Get information about the current AWS account."""
        if self._account_info:
            return self._account_info

        if self._session or self.active_profile:
            try:
                sts = self.get_client("sts")
                identity = sts.get_caller_identity()
                self._account_info = AccountInfo(
                    account_id=identity["Account"],
                    user_id=identity["UserId"],
                    arn=identity["Arn"],
                    profile=self.active_profile,
                    region=self.active_region,
                )
                return self._account_info
            except Exception:
                return None
        return None

    def set_region(self, region: str) -> None:
        """Set the active region."""
        self.active_region = region
        # Reset session to use new region
        if self._session:
            self._session = boto3.Session(
                profile_name=self.active_profile,
                region_name=region,
            )
        logger.info("region_changed", region=region)

    def to_dict(self) -> dict[str, Any]:
        """Convert session state to dictionary."""
        return {
            "active_profile": self.active_profile,
            "active_region": self.active_region,
            "account_info": (
                {
                    "account_id": self._account_info.account_id,
                    "user_id": self._account_info.user_id,
                    "arn": self._account_info.arn,
                }
                if self._account_info
                else None
            ),
        }


# Global session manager instance
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Get the global session manager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


def reset_session_manager() -> None:
    """Reset the global session manager (for testing)."""
    global _session_manager
    _session_manager = None
