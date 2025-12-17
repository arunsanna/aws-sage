"""Environment configuration for AWS MCP Pro.

Supports multiple environments including production AWS and LocalStack for local development.
"""

from dataclasses import dataclass, field
from enum import Enum


class EnvironmentType(Enum):
    """Type of AWS environment."""

    PRODUCTION = "production"
    LOCALSTACK = "localstack"


# Services available in LocalStack Community Edition
LOCALSTACK_COMMUNITY_SERVICES: set[str] = {
    # Core services
    "acm",
    "apigateway",
    "cloudformation",
    "cloudwatch",
    "config",
    "dynamodb",
    "dynamodbstreams",
    "ec2",
    "ecr",
    "ecs",
    "elasticbeanstalk",
    "events",
    "firehose",
    "iam",
    "kinesis",
    "kms",
    "lambda",
    "logs",
    "opensearch",
    "redshift",
    "resourcegroupstaggingapi",
    "route53",
    "route53resolver",
    "s3",
    "s3control",
    "secretsmanager",
    "ses",
    "sns",
    "sqs",
    "ssm",
    "stepfunctions",
    "sts",
    "transcribe",
}

# Services that require LocalStack Pro
LOCALSTACK_PRO_SERVICES: set[str] = {
    "amplify",
    "appsync",
    "athena",
    "backup",
    "batch",
    "ce",  # Cost Explorer - Pro only
    "cloudfront",
    "codeartifact",
    "codecommit",
    "cognito-identity",
    "cognito-idp",
    "docdb",
    "elasticache",
    "elasticloadbalancing",
    "elasticloadbalancingv2",
    "emr",
    "glue",
    "iot",
    "lakeformation",
    "mediastore",
    "mq",
    "mwaa",
    "neptune",
    "organizations",
    "pricing",  # Pricing API - Pro only
    "qldb",
    "rds",
    "redshift-data",
    "sagemaker",
    "servicediscovery",
    "shield",
    "timestream",
    "transfer",
    "waf",
    "wafv2",
    "xray",
}


@dataclass
class EnvironmentConfig:
    """Configuration for an AWS environment."""

    name: str
    type: EnvironmentType
    endpoint_url: str | None = None
    region: str = "us-east-1"
    access_key_id: str | None = None
    secret_access_key: str | None = None
    is_active: bool = False
    description: str = ""
    available_services: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Set available services based on environment type."""
        if self.type == EnvironmentType.LOCALSTACK and not self.available_services:
            self.available_services = LOCALSTACK_COMMUNITY_SERVICES.copy()

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "type": self.type.value,
            "endpoint_url": self.endpoint_url,
            "region": self.region,
            "is_active": self.is_active,
            "description": self.description,
            "available_services_count": len(self.available_services),
        }

    def is_service_available(self, service: str) -> bool:
        """Check if a service is available in this environment."""
        if self.type == EnvironmentType.PRODUCTION:
            return True  # All services available in production
        return service.lower() in self.available_services

    def get_client_kwargs(self, service: str) -> dict:
        """Get boto3 client kwargs for this environment."""
        kwargs: dict = {}

        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url

        if self.region:
            kwargs["region_name"] = self.region

        if self.access_key_id and self.secret_access_key:
            kwargs["aws_access_key_id"] = self.access_key_id
            kwargs["aws_secret_access_key"] = self.secret_access_key

        return kwargs


# Default environment configurations
DEFAULT_PRODUCTION_CONFIG = EnvironmentConfig(
    name="production",
    type=EnvironmentType.PRODUCTION,
    description="Production AWS environment using configured credentials",
)

DEFAULT_LOCALSTACK_CONFIG = EnvironmentConfig(
    name="localstack",
    type=EnvironmentType.LOCALSTACK,
    endpoint_url="http://localhost:4566",
    region="us-east-1",
    access_key_id="test",
    secret_access_key="test",
    description="LocalStack local development environment",
)
