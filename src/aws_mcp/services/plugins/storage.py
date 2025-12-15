"""Storage service plugins (S3, DynamoDB, etc.)."""

from __future__ import annotations

from typing import Any

import boto3

from aws_mcp.config import OperationCategory
from aws_mcp.services.base import BaseService, OperationResult, OperationSpec, register_service


@register_service
class S3Service(BaseService):
    """Amazon S3 service plugin."""

    @property
    def service_name(self) -> str:
        return "s3"

    @property
    def display_name(self) -> str:
        return "Amazon S3"

    def get_operations(self) -> list[OperationSpec]:
        return [
            OperationSpec(
                name="list_buckets",
                description="List all S3 buckets in the account",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=[],
                supports_pagination=False,
                result_key="Buckets",
            ),
            OperationSpec(
                name="list_objects_v2",
                description="List objects in an S3 bucket",
                category=OperationCategory.READ,
                required_params=["Bucket"],
                optional_params=["Prefix", "MaxKeys", "Delimiter", "StartAfter"],
                supports_pagination=True,
                result_key="Contents",
            ),
            OperationSpec(
                name="head_bucket",
                description="Check if a bucket exists and is accessible",
                category=OperationCategory.READ,
                required_params=["Bucket"],
                optional_params=[],
                supports_pagination=False,
            ),
            OperationSpec(
                name="get_bucket_location",
                description="Get the region of a bucket",
                category=OperationCategory.READ,
                required_params=["Bucket"],
                optional_params=[],
                supports_pagination=False,
            ),
            OperationSpec(
                name="get_bucket_versioning",
                description="Get bucket versioning configuration",
                category=OperationCategory.READ,
                required_params=["Bucket"],
                optional_params=[],
                supports_pagination=False,
            ),
            OperationSpec(
                name="get_bucket_encryption",
                description="Get bucket encryption configuration",
                category=OperationCategory.READ,
                required_params=["Bucket"],
                optional_params=[],
                supports_pagination=False,
            ),
            OperationSpec(
                name="create_bucket",
                description="Create a new S3 bucket",
                category=OperationCategory.WRITE,
                required_params=["Bucket"],
                optional_params=["CreateBucketConfiguration"],
                supports_pagination=False,
            ),
            OperationSpec(
                name="delete_bucket",
                description="Delete an S3 bucket (must be empty)",
                category=OperationCategory.DESTRUCTIVE,
                required_params=["Bucket"],
                optional_params=[],
                supports_pagination=False,
            ),
            OperationSpec(
                name="delete_object",
                description="Delete an object from S3",
                category=OperationCategory.DESTRUCTIVE,
                required_params=["Bucket", "Key"],
                optional_params=["VersionId"],
                supports_pagination=False,
            ),
        ]

    def format_response(self, data: Any, format_type: str = "table") -> str:
        """Custom formatting for S3 responses."""
        if format_type == "json":
            import json
            return json.dumps(data, indent=2, default=str)

        if isinstance(data, list) and data:
            # Format buckets
            if "Name" in data[0] and "CreationDate" in data[0]:
                return self._format_buckets(data)
            # Format objects
            elif "Key" in data[0]:
                return self._format_objects(data)

        return super().format_response(data, format_type)

    def _format_buckets(self, buckets: list[dict[str, Any]]) -> str:
        """Format bucket list."""
        lines = ["| Bucket Name | Created |", "| ----------- | ------- |"]
        for bucket in buckets:
            name = bucket.get("Name", "")
            created = bucket.get("CreationDate", "")
            if hasattr(created, "strftime"):
                created = created.strftime("%Y-%m-%d %H:%M")
            lines.append(f"| {name} | {created} |")
        return "\n".join(lines)

    def _format_objects(self, objects: list[dict[str, Any]]) -> str:
        """Format object list."""
        lines = ["| Key | Size | Last Modified |", "| --- | ---- | ------------- |"]
        for obj in objects[:50]:  # Limit to 50
            key = obj.get("Key", "")[:40]
            size = self._format_size(obj.get("Size", 0))
            modified = obj.get("LastModified", "")
            if hasattr(modified, "strftime"):
                modified = modified.strftime("%Y-%m-%d %H:%M")
            lines.append(f"| {key} | {size} | {modified} |")

        if len(objects) > 50:
            lines.append(f"... and {len(objects) - 50} more objects")

        return "\n".join(lines)

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format byte size to human readable."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"


@register_service
class DynamoDBService(BaseService):
    """Amazon DynamoDB service plugin."""

    @property
    def service_name(self) -> str:
        return "dynamodb"

    @property
    def display_name(self) -> str:
        return "Amazon DynamoDB"

    def get_operations(self) -> list[OperationSpec]:
        return [
            OperationSpec(
                name="list_tables",
                description="List all DynamoDB tables",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["Limit"],
                supports_pagination=True,
                result_key="TableNames",
            ),
            OperationSpec(
                name="describe_table",
                description="Get details about a DynamoDB table",
                category=OperationCategory.READ,
                required_params=["TableName"],
                optional_params=[],
                supports_pagination=False,
                result_key="Table",
            ),
            OperationSpec(
                name="scan",
                description="Scan a DynamoDB table",
                category=OperationCategory.READ,
                required_params=["TableName"],
                optional_params=["FilterExpression", "Limit", "ProjectionExpression"],
                supports_pagination=True,
                result_key="Items",
            ),
            OperationSpec(
                name="query",
                description="Query a DynamoDB table",
                category=OperationCategory.READ,
                required_params=["TableName", "KeyConditionExpression"],
                optional_params=["FilterExpression", "Limit", "ProjectionExpression"],
                supports_pagination=True,
                result_key="Items",
            ),
            OperationSpec(
                name="create_table",
                description="Create a new DynamoDB table",
                category=OperationCategory.WRITE,
                required_params=["TableName", "KeySchema", "AttributeDefinitions"],
                optional_params=["BillingMode", "ProvisionedThroughput"],
                supports_pagination=False,
            ),
            OperationSpec(
                name="delete_table",
                description="Delete a DynamoDB table",
                category=OperationCategory.DESTRUCTIVE,
                required_params=["TableName"],
                optional_params=[],
                supports_pagination=False,
            ),
        ]
