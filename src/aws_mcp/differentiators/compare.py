"""Environment comparison for AWS MCP Pro.

Compare resources between LocalStack and production environments.
"""

from dataclasses import dataclass, field
from enum import Enum

import boto3
import structlog

from aws_mcp.core.environment import EnvironmentConfig, EnvironmentType

logger = structlog.get_logger()


class ResourceDifference(Enum):
    """Type of difference between environments."""

    ONLY_IN_SOURCE = "only_in_source"
    ONLY_IN_TARGET = "only_in_target"
    DIFFERENT = "different"
    IDENTICAL = "identical"


@dataclass
class ResourceComparison:
    """Comparison result for a single resource."""

    resource_type: str
    identifier: str
    difference: ResourceDifference
    source_value: dict | None = None
    target_value: dict | None = None
    differences: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "resource_type": self.resource_type,
            "identifier": self.identifier,
            "difference": self.difference.value,
            "source_value": self.source_value,
            "target_value": self.target_value,
            "differences": self.differences,
        }


@dataclass
class ComparisonResult:
    """Result of comparing two environments."""

    service: str
    source_environment: str
    target_environment: str
    resource_type: str
    only_in_source: list[ResourceComparison] = field(default_factory=list)
    only_in_target: list[ResourceComparison] = field(default_factory=list)
    different: list[ResourceComparison] = field(default_factory=list)
    identical: list[ResourceComparison] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "service": self.service,
            "source_environment": self.source_environment,
            "target_environment": self.target_environment,
            "resource_type": self.resource_type,
            "summary": {
                "only_in_source": len(self.only_in_source),
                "only_in_target": len(self.only_in_target),
                "different": len(self.different),
                "identical": len(self.identical),
            },
            "only_in_source": [r.to_dict() for r in self.only_in_source],
            "only_in_target": [r.to_dict() for r in self.only_in_target],
            "different": [r.to_dict() for r in self.different],
            "identical_count": len(self.identical),
            "errors": self.errors,
        }


class EnvironmentComparer:
    """Compare resources between AWS environments."""

    def __init__(self) -> None:
        """Initialize the comparer."""
        self._supported_services = {
            "s3": self._compare_s3_buckets,
            "dynamodb": self._compare_dynamodb_tables,
            "lambda": self._compare_lambda_functions,
            "sqs": self._compare_sqs_queues,
            "sns": self._compare_sns_topics,
        }

    @property
    def supported_services(self) -> list[str]:
        """Get list of supported services for comparison."""
        return list(self._supported_services.keys())

    def _get_client(self, service: str, env_config: EnvironmentConfig) -> boto3.client:
        """Get boto3 client for an environment."""
        kwargs = env_config.get_client_kwargs(service)

        # Create session with appropriate credentials
        if env_config.type == EnvironmentType.LOCALSTACK:
            session = boto3.Session(
                aws_access_key_id=env_config.access_key_id or "test",
                aws_secret_access_key=env_config.secret_access_key or "test",
                region_name=env_config.region,
            )
        else:
            session = boto3.Session(region_name=env_config.region)

        return session.client(service, **kwargs)

    async def compare_environments(
        self,
        service: str,
        source_env: EnvironmentConfig,
        target_env: EnvironmentConfig,
    ) -> ComparisonResult:
        """Compare resources between two environments.

        Args:
            service: AWS service to compare (s3, dynamodb, lambda, sqs, sns)
            source_env: Source environment configuration
            target_env: Target environment configuration

        Returns:
            ComparisonResult with differences
        """
        if service.lower() not in self._supported_services:
            return ComparisonResult(
                service=service,
                source_environment=source_env.name,
                target_environment=target_env.name,
                resource_type="unknown",
                errors=[
                    f"Service '{service}' is not supported for comparison. "
                    f"Supported: {', '.join(self.supported_services)}"
                ],
            )

        compare_func = self._supported_services[service.lower()]
        return await compare_func(source_env, target_env)

    async def _compare_s3_buckets(
        self, source_env: EnvironmentConfig, target_env: EnvironmentConfig
    ) -> ComparisonResult:
        """Compare S3 buckets between environments."""
        result = ComparisonResult(
            service="s3",
            source_environment=source_env.name,
            target_environment=target_env.name,
            resource_type="bucket",
        )

        try:
            source_client = self._get_client("s3", source_env)
            target_client = self._get_client("s3", target_env)

            # Get buckets from both environments
            source_response = source_client.list_buckets()
            target_response = target_client.list_buckets()

            source_buckets = {b["Name"]: b for b in source_response.get("Buckets", [])}
            target_buckets = {b["Name"]: b for b in target_response.get("Buckets", [])}

            # Find differences
            for name, bucket in source_buckets.items():
                if name not in target_buckets:
                    result.only_in_source.append(
                        ResourceComparison(
                            resource_type="bucket",
                            identifier=name,
                            difference=ResourceDifference.ONLY_IN_SOURCE,
                            source_value={"name": name},
                        )
                    )
                else:
                    result.identical.append(
                        ResourceComparison(
                            resource_type="bucket",
                            identifier=name,
                            difference=ResourceDifference.IDENTICAL,
                        )
                    )

            for name in target_buckets:
                if name not in source_buckets:
                    result.only_in_target.append(
                        ResourceComparison(
                            resource_type="bucket",
                            identifier=name,
                            difference=ResourceDifference.ONLY_IN_TARGET,
                            target_value={"name": name},
                        )
                    )

        except Exception as e:
            result.errors.append(f"Error comparing S3 buckets: {e!s}")
            logger.error("s3_comparison_error", error=str(e))

        return result

    async def _compare_dynamodb_tables(
        self, source_env: EnvironmentConfig, target_env: EnvironmentConfig
    ) -> ComparisonResult:
        """Compare DynamoDB tables between environments."""
        result = ComparisonResult(
            service="dynamodb",
            source_environment=source_env.name,
            target_environment=target_env.name,
            resource_type="table",
        )

        try:
            source_client = self._get_client("dynamodb", source_env)
            target_client = self._get_client("dynamodb", target_env)

            # Get tables from both environments
            source_tables = set(source_client.list_tables().get("TableNames", []))
            target_tables = set(target_client.list_tables().get("TableNames", []))

            # Find differences
            for table in source_tables:
                if table not in target_tables:
                    result.only_in_source.append(
                        ResourceComparison(
                            resource_type="table",
                            identifier=table,
                            difference=ResourceDifference.ONLY_IN_SOURCE,
                            source_value={"table_name": table},
                        )
                    )
                else:
                    # Compare table schemas
                    source_desc = source_client.describe_table(TableName=table)["Table"]
                    target_desc = target_client.describe_table(TableName=table)["Table"]

                    differences = self._compare_table_schemas(source_desc, target_desc)
                    if differences:
                        result.different.append(
                            ResourceComparison(
                                resource_type="table",
                                identifier=table,
                                difference=ResourceDifference.DIFFERENT,
                                differences=differences,
                            )
                        )
                    else:
                        result.identical.append(
                            ResourceComparison(
                                resource_type="table",
                                identifier=table,
                                difference=ResourceDifference.IDENTICAL,
                            )
                        )

            for table in target_tables:
                if table not in source_tables:
                    result.only_in_target.append(
                        ResourceComparison(
                            resource_type="table",
                            identifier=table,
                            difference=ResourceDifference.ONLY_IN_TARGET,
                            target_value={"table_name": table},
                        )
                    )

        except Exception as e:
            result.errors.append(f"Error comparing DynamoDB tables: {e!s}")
            logger.error("dynamodb_comparison_error", error=str(e))

        return result

    def _compare_table_schemas(self, source: dict, target: dict) -> list[str]:
        """Compare DynamoDB table schemas."""
        differences = []

        # Compare key schema
        source_keys = {k["AttributeName"]: k["KeyType"] for k in source.get("KeySchema", [])}
        target_keys = {k["AttributeName"]: k["KeyType"] for k in target.get("KeySchema", [])}
        if source_keys != target_keys:
            differences.append(f"Key schema differs: {source_keys} vs {target_keys}")

        # Compare attribute definitions
        source_attrs = {
            a["AttributeName"]: a["AttributeType"]
            for a in source.get("AttributeDefinitions", [])
        }
        target_attrs = {
            a["AttributeName"]: a["AttributeType"]
            for a in target.get("AttributeDefinitions", [])
        }
        if source_attrs != target_attrs:
            differences.append(f"Attribute definitions differ: {source_attrs} vs {target_attrs}")

        # Compare GSI count
        source_gsi = len(source.get("GlobalSecondaryIndexes", []))
        target_gsi = len(target.get("GlobalSecondaryIndexes", []))
        if source_gsi != target_gsi:
            differences.append(f"GSI count differs: {source_gsi} vs {target_gsi}")

        return differences

    async def _compare_lambda_functions(
        self, source_env: EnvironmentConfig, target_env: EnvironmentConfig
    ) -> ComparisonResult:
        """Compare Lambda functions between environments."""
        result = ComparisonResult(
            service="lambda",
            source_environment=source_env.name,
            target_environment=target_env.name,
            resource_type="function",
        )

        try:
            source_client = self._get_client("lambda", source_env)
            target_client = self._get_client("lambda", target_env)

            # Get functions from both environments
            source_funcs = {
                f["FunctionName"]: f
                for f in source_client.list_functions().get("Functions", [])
            }
            target_funcs = {
                f["FunctionName"]: f
                for f in target_client.list_functions().get("Functions", [])
            }

            # Find differences
            for name, func in source_funcs.items():
                if name not in target_funcs:
                    result.only_in_source.append(
                        ResourceComparison(
                            resource_type="function",
                            identifier=name,
                            difference=ResourceDifference.ONLY_IN_SOURCE,
                            source_value={
                                "function_name": name,
                                "runtime": func.get("Runtime"),
                                "memory": func.get("MemorySize"),
                            },
                        )
                    )
                else:
                    # Compare function configs
                    target_func = target_funcs[name]
                    differences = self._compare_lambda_configs(func, target_func)
                    if differences:
                        result.different.append(
                            ResourceComparison(
                                resource_type="function",
                                identifier=name,
                                difference=ResourceDifference.DIFFERENT,
                                differences=differences,
                            )
                        )
                    else:
                        result.identical.append(
                            ResourceComparison(
                                resource_type="function",
                                identifier=name,
                                difference=ResourceDifference.IDENTICAL,
                            )
                        )

            for name in target_funcs:
                if name not in source_funcs:
                    result.only_in_target.append(
                        ResourceComparison(
                            resource_type="function",
                            identifier=name,
                            difference=ResourceDifference.ONLY_IN_TARGET,
                            target_value={"function_name": name},
                        )
                    )

        except Exception as e:
            result.errors.append(f"Error comparing Lambda functions: {e!s}")
            logger.error("lambda_comparison_error", error=str(e))

        return result

    def _compare_lambda_configs(self, source: dict, target: dict) -> list[str]:
        """Compare Lambda function configurations."""
        differences = []

        if source.get("Runtime") != target.get("Runtime"):
            differences.append(
                f"Runtime differs: {source.get('Runtime')} vs {target.get('Runtime')}"
            )

        if source.get("MemorySize") != target.get("MemorySize"):
            differences.append(
                f"Memory differs: {source.get('MemorySize')} vs {target.get('MemorySize')}"
            )

        if source.get("Timeout") != target.get("Timeout"):
            differences.append(
                f"Timeout differs: {source.get('Timeout')} vs {target.get('Timeout')}"
            )

        if source.get("Handler") != target.get("Handler"):
            differences.append(
                f"Handler differs: {source.get('Handler')} vs {target.get('Handler')}"
            )

        return differences

    async def _compare_sqs_queues(
        self, source_env: EnvironmentConfig, target_env: EnvironmentConfig
    ) -> ComparisonResult:
        """Compare SQS queues between environments."""
        result = ComparisonResult(
            service="sqs",
            source_environment=source_env.name,
            target_environment=target_env.name,
            resource_type="queue",
        )

        try:
            source_client = self._get_client("sqs", source_env)
            target_client = self._get_client("sqs", target_env)

            # Get queues from both environments
            source_queues = set(source_client.list_queues().get("QueueUrls", []))
            target_queues = set(target_client.list_queues().get("QueueUrls", []))

            # Extract queue names from URLs
            def get_queue_name(url: str) -> str:
                return url.split("/")[-1]

            source_names = {get_queue_name(q): q for q in source_queues}
            target_names = {get_queue_name(q): q for q in target_queues}

            # Find differences
            for name in source_names:
                if name not in target_names:
                    result.only_in_source.append(
                        ResourceComparison(
                            resource_type="queue",
                            identifier=name,
                            difference=ResourceDifference.ONLY_IN_SOURCE,
                            source_value={"queue_name": name},
                        )
                    )
                else:
                    result.identical.append(
                        ResourceComparison(
                            resource_type="queue",
                            identifier=name,
                            difference=ResourceDifference.IDENTICAL,
                        )
                    )

            for name in target_names:
                if name not in source_names:
                    result.only_in_target.append(
                        ResourceComparison(
                            resource_type="queue",
                            identifier=name,
                            difference=ResourceDifference.ONLY_IN_TARGET,
                            target_value={"queue_name": name},
                        )
                    )

        except Exception as e:
            result.errors.append(f"Error comparing SQS queues: {e!s}")
            logger.error("sqs_comparison_error", error=str(e))

        return result

    async def _compare_sns_topics(
        self, source_env: EnvironmentConfig, target_env: EnvironmentConfig
    ) -> ComparisonResult:
        """Compare SNS topics between environments."""
        result = ComparisonResult(
            service="sns",
            source_environment=source_env.name,
            target_environment=target_env.name,
            resource_type="topic",
        )

        try:
            source_client = self._get_client("sns", source_env)
            target_client = self._get_client("sns", target_env)

            # Get topics from both environments
            source_topics = {
                t["TopicArn"].split(":")[-1]: t["TopicArn"]
                for t in source_client.list_topics().get("Topics", [])
            }
            target_topics = {
                t["TopicArn"].split(":")[-1]: t["TopicArn"]
                for t in target_client.list_topics().get("Topics", [])
            }

            # Find differences
            for name in source_topics:
                if name not in target_topics:
                    result.only_in_source.append(
                        ResourceComparison(
                            resource_type="topic",
                            identifier=name,
                            difference=ResourceDifference.ONLY_IN_SOURCE,
                            source_value={"topic_name": name},
                        )
                    )
                else:
                    result.identical.append(
                        ResourceComparison(
                            resource_type="topic",
                            identifier=name,
                            difference=ResourceDifference.IDENTICAL,
                        )
                    )

            for name in target_topics:
                if name not in source_topics:
                    result.only_in_target.append(
                        ResourceComparison(
                            resource_type="topic",
                            identifier=name,
                            difference=ResourceDifference.ONLY_IN_TARGET,
                            target_value={"topic_name": name},
                        )
                    )

        except Exception as e:
            result.errors.append(f"Error comparing SNS topics: {e!s}")
            logger.error("sns_comparison_error", error=str(e))

        return result


# Global instance
_comparer: EnvironmentComparer | None = None


def get_environment_comparer() -> EnvironmentComparer:
    """Get the global EnvironmentComparer instance."""
    global _comparer
    if _comparer is None:
        _comparer = EnvironmentComparer()
    return _comparer


def reset_environment_comparer() -> None:
    """Reset the global EnvironmentComparer instance (for testing)."""
    global _comparer
    _comparer = None
