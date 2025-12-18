"""Security service plugins (IAM, KMS, Secrets Manager)."""

from __future__ import annotations

from typing import Any

import boto3

from aws_sage.config import OperationCategory
from aws_sage.services.base import BaseService, OperationSpec, register_service


@register_service
class IAMService(BaseService):
    """AWS IAM service plugin."""

    @property
    def service_name(self) -> str:
        return "iam"

    @property
    def display_name(self) -> str:
        return "AWS IAM"

    def get_operations(self) -> list[OperationSpec]:
        return [
            OperationSpec(
                name="list_users",
                description="List IAM users",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["PathPrefix", "MaxItems"],
                supports_pagination=True,
                result_key="Users",
            ),
            OperationSpec(
                name="list_roles",
                description="List IAM roles",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["PathPrefix", "MaxItems"],
                supports_pagination=True,
                result_key="Roles",
            ),
            OperationSpec(
                name="list_policies",
                description="List IAM policies",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["Scope", "PathPrefix", "MaxItems", "OnlyAttached"],
                supports_pagination=True,
                result_key="Policies",
            ),
            OperationSpec(
                name="list_groups",
                description="List IAM groups",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["PathPrefix", "MaxItems"],
                supports_pagination=True,
                result_key="Groups",
            ),
            OperationSpec(
                name="get_user",
                description="Get details about an IAM user",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["UserName"],
                supports_pagination=False,
                result_key="User",
            ),
            OperationSpec(
                name="get_role",
                description="Get details about an IAM role",
                category=OperationCategory.READ,
                required_params=["RoleName"],
                optional_params=[],
                supports_pagination=False,
                result_key="Role",
            ),
            OperationSpec(
                name="list_attached_role_policies",
                description="List policies attached to a role",
                category=OperationCategory.READ,
                required_params=["RoleName"],
                optional_params=["PathPrefix", "MaxItems"],
                supports_pagination=True,
                result_key="AttachedPolicies",
            ),
            OperationSpec(
                name="list_attached_user_policies",
                description="List policies attached to a user",
                category=OperationCategory.READ,
                required_params=["UserName"],
                optional_params=["PathPrefix", "MaxItems"],
                supports_pagination=True,
                result_key="AttachedPolicies",
            ),
            OperationSpec(
                name="create_role",
                description="Create an IAM role",
                category=OperationCategory.WRITE,
                required_params=["RoleName", "AssumeRolePolicyDocument"],
                optional_params=["Path", "Description", "Tags"],
                supports_pagination=False,
            ),
            OperationSpec(
                name="attach_role_policy",
                description="Attach a policy to a role",
                category=OperationCategory.WRITE,
                required_params=["RoleName", "PolicyArn"],
                optional_params=[],
                supports_pagination=False,
            ),
            OperationSpec(
                name="delete_role",
                description="Delete an IAM role",
                category=OperationCategory.DESTRUCTIVE,
                required_params=["RoleName"],
                optional_params=[],
                supports_pagination=False,
            ),
        ]

    def format_response(self, data: Any, format_type: str = "table") -> str:
        """Custom formatting for IAM responses."""
        if format_type == "json":
            import json
            return json.dumps(data, indent=2, default=str)

        if isinstance(data, list) and data:
            first = data[0]
            if "UserName" in first:
                return self._format_users(data)
            elif "RoleName" in first:
                return self._format_roles(data)
            elif "PolicyName" in first:
                return self._format_policies(data)

        return super().format_response(data, format_type)

    def _format_users(self, users: list[dict[str, Any]]) -> str:
        """Format user list."""
        lines = ["| User Name | User ID | Created | Password Last Used |", "| --------- | ------- | ------- | ------------------ |"]
        for user in users[:50]:
            name = user.get("UserName", "")
            user_id = user.get("UserId", "")[:15]
            created = user.get("CreateDate", "")
            if hasattr(created, "strftime"):
                created = created.strftime("%Y-%m-%d")
            pwd_used = user.get("PasswordLastUsed", "-")
            if hasattr(pwd_used, "strftime"):
                pwd_used = pwd_used.strftime("%Y-%m-%d")
            lines.append(f"| {name} | {user_id} | {created} | {pwd_used} |")
        return "\n".join(lines)

    def _format_roles(self, roles: list[dict[str, Any]]) -> str:
        """Format role list."""
        lines = ["| Role Name | Role ID | Created |", "| --------- | ------- | ------- |"]
        for role in roles[:50]:
            name = role.get("RoleName", "")[:30]
            role_id = role.get("RoleId", "")[:15]
            created = role.get("CreateDate", "")
            if hasattr(created, "strftime"):
                created = created.strftime("%Y-%m-%d")
            lines.append(f"| {name} | {role_id} | {created} |")
        return "\n".join(lines)

    def _format_policies(self, policies: list[dict[str, Any]]) -> str:
        """Format policy list."""
        lines = ["| Policy Name | ARN | Attached |", "| ----------- | --- | -------- |"]
        for policy in policies[:50]:
            name = policy.get("PolicyName", "")[:25]
            arn = policy.get("Arn", "")[-40:]
            attached = policy.get("AttachmentCount", 0)
            lines.append(f"| {name} | ...{arn} | {attached} |")
        return "\n".join(lines)


@register_service
class SecretsManagerService(BaseService):
    """AWS Secrets Manager service plugin."""

    @property
    def service_name(self) -> str:
        return "secretsmanager"

    @property
    def display_name(self) -> str:
        return "AWS Secrets Manager"

    def get_operations(self) -> list[OperationSpec]:
        return [
            OperationSpec(
                name="list_secrets",
                description="List secrets in Secrets Manager",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["MaxResults", "Filters", "SortOrder"],
                supports_pagination=True,
                result_key="SecretList",
            ),
            OperationSpec(
                name="describe_secret",
                description="Get metadata about a secret",
                category=OperationCategory.READ,
                required_params=["SecretId"],
                optional_params=[],
                supports_pagination=False,
            ),
            OperationSpec(
                name="get_secret_value",
                description="Get the value of a secret",
                category=OperationCategory.READ,
                required_params=["SecretId"],
                optional_params=["VersionId", "VersionStage"],
                supports_pagination=False,
            ),
            OperationSpec(
                name="create_secret",
                description="Create a new secret",
                category=OperationCategory.WRITE,
                required_params=["Name"],
                optional_params=["SecretString", "SecretBinary", "Description", "Tags"],
                supports_pagination=False,
            ),
            OperationSpec(
                name="update_secret",
                description="Update a secret value",
                category=OperationCategory.WRITE,
                required_params=["SecretId"],
                optional_params=["SecretString", "SecretBinary", "Description"],
                supports_pagination=False,
            ),
        ]


@register_service
class KMSService(BaseService):
    """AWS KMS service plugin."""

    @property
    def service_name(self) -> str:
        return "kms"

    @property
    def display_name(self) -> str:
        return "AWS KMS"

    def get_operations(self) -> list[OperationSpec]:
        return [
            OperationSpec(
                name="list_keys",
                description="List KMS keys",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["Limit"],
                supports_pagination=True,
                result_key="Keys",
            ),
            OperationSpec(
                name="describe_key",
                description="Get details about a KMS key",
                category=OperationCategory.READ,
                required_params=["KeyId"],
                optional_params=[],
                supports_pagination=False,
                result_key="KeyMetadata",
            ),
            OperationSpec(
                name="list_aliases",
                description="List KMS key aliases",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["KeyId", "Limit"],
                supports_pagination=True,
                result_key="Aliases",
            ),
            OperationSpec(
                name="create_key",
                description="Create a new KMS key",
                category=OperationCategory.WRITE,
                required_params=[],
                optional_params=["Description", "KeySpec", "KeyUsage", "Tags"],
                supports_pagination=False,
            ),
        ]
