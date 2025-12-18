"""Intent classification for natural language AWS queries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import structlog

from aws_sage.config import OperationCategory
from aws_sage.parser.schemas import (
    ParsedIntent,
    ParsedOperation,
    ParsedParameter,
    ParsedService,
    ParseResult,
    StructuredCommand,
)

logger = structlog.get_logger()


@dataclass
class IntentPattern:
    """Pattern for matching user intent."""

    intent_type: str
    patterns: list[str]
    category: OperationCategory
    operation_prefix: str


class IntentClassifier:
    """Classifies natural language queries into AWS operations."""

    # Intent patterns with regex
    INTENT_PATTERNS: list[IntentPattern] = [
        IntentPattern(
            intent_type="list",
            patterns=[
                r"^list\s+(?:all\s+)?(.+)",
                r"^show\s+(?:me\s+)?(?:all\s+)?(.+)",
                r"^get\s+(?:all\s+)?(.+)",
                r"^what\s+(.+)\s+(?:do\s+)?(?:i\s+)?have",
                r"^display\s+(.+)",
                r"^find\s+(?:all\s+)?(.+)",
            ],
            category=OperationCategory.READ,
            operation_prefix="list",
        ),
        IntentPattern(
            intent_type="describe",
            patterns=[
                r"^describe\s+(.+)",
                r"^tell\s+me\s+about\s+(.+)",
                r"^details\s+(?:of|for|about)\s+(.+)",
                r"^info\s+(?:on|about|for)\s+(.+)",
                r"^what\s+is\s+(.+)",
            ],
            category=OperationCategory.READ,
            operation_prefix="describe",
        ),
        IntentPattern(
            intent_type="get",
            patterns=[
                r"^get\s+(.+?)(?:\s+details|\s+info)?$",
                r"^fetch\s+(.+)",
                r"^retrieve\s+(.+)",
            ],
            category=OperationCategory.READ,
            operation_prefix="get",
        ),
        IntentPattern(
            intent_type="create",
            patterns=[
                r"^create\s+(?:a\s+)?(?:new\s+)?(.+)",
                r"^make\s+(?:a\s+)?(?:new\s+)?(.+)",
                r"^add\s+(?:a\s+)?(?:new\s+)?(.+)",
                r"^launch\s+(?:a\s+)?(?:new\s+)?(.+)",
                r"^start\s+(?:a\s+)?(?:new\s+)?(.+)",
            ],
            category=OperationCategory.WRITE,
            operation_prefix="create",
        ),
        IntentPattern(
            intent_type="delete",
            patterns=[
                r"^delete\s+(.+)",
                r"^remove\s+(.+)",
                r"^destroy\s+(.+)",
                r"^terminate\s+(.+)",
                r"^drop\s+(.+)",
            ],
            category=OperationCategory.DESTRUCTIVE,
            operation_prefix="delete",
        ),
        IntentPattern(
            intent_type="update",
            patterns=[
                r"^update\s+(.+)",
                r"^modify\s+(.+)",
                r"^change\s+(.+)",
                r"^edit\s+(.+)",
            ],
            category=OperationCategory.WRITE,
            operation_prefix="update",
        ),
        IntentPattern(
            intent_type="stop",
            patterns=[
                r"^stop\s+(.+)",
                r"^halt\s+(.+)",
                r"^pause\s+(.+)",
            ],
            category=OperationCategory.WRITE,
            operation_prefix="stop",
        ),
        IntentPattern(
            intent_type="start",
            patterns=[
                r"^start\s+(.+)",
                r"^resume\s+(.+)",
                r"^run\s+(.+)",
            ],
            category=OperationCategory.WRITE,
            operation_prefix="start",
        ),
    ]

    # Service keyword mapping
    SERVICE_KEYWORDS: dict[str, dict[str, Any]] = {
        "s3": {
            "keywords": ["s3", "bucket", "buckets", "object", "objects", "storage"],
            "display_name": "Amazon S3",
            "resource_types": {
                "bucket": "list_buckets",
                "object": "list_objects_v2",
            },
        },
        "ec2": {
            "keywords": ["ec2", "instance", "instances", "ami", "amis", "ebs", "volume", "volumes", "vpc", "vpcs", "subnet", "subnets", "security group", "security groups"],
            "display_name": "Amazon EC2",
            "resource_types": {
                "instance": "describe_instances",
                "volume": "describe_volumes",
                "vpc": "describe_vpcs",
                "subnet": "describe_subnets",
                "security group": "describe_security_groups",
                "ami": "describe_images",
            },
        },
        "lambda": {
            "keywords": ["lambda", "function", "functions", "serverless"],
            "display_name": "AWS Lambda",
            "resource_types": {
                "function": "list_functions",
            },
        },
        "iam": {
            "keywords": ["iam", "role", "roles", "user", "users", "policy", "policies", "permission", "permissions", "group", "groups"],
            "display_name": "AWS IAM",
            "resource_types": {
                "role": "list_roles",
                "user": "list_users",
                "policy": "list_policies",
                "group": "list_groups",
            },
        },
        "rds": {
            "keywords": ["rds", "database", "databases", "db", "mysql", "postgres", "postgresql", "aurora", "mariadb"],
            "display_name": "Amazon RDS",
            "resource_types": {
                "instance": "describe_db_instances",
                "cluster": "describe_db_clusters",
                "snapshot": "describe_db_snapshots",
            },
        },
        "dynamodb": {
            "keywords": ["dynamodb", "dynamo", "table", "tables", "nosql"],
            "display_name": "Amazon DynamoDB",
            "resource_types": {
                "table": "list_tables",
            },
        },
        "ecs": {
            "keywords": ["ecs", "container", "containers", "cluster", "clusters", "task", "tasks", "service", "services"],
            "display_name": "Amazon ECS",
            "resource_types": {
                "cluster": "list_clusters",
                "service": "list_services",
                "task": "list_tasks",
            },
        },
        "eks": {
            "keywords": ["eks", "kubernetes", "k8s"],
            "display_name": "Amazon EKS",
            "resource_types": {
                "cluster": "list_clusters",
            },
        },
        "cloudformation": {
            "keywords": ["cloudformation", "cfn", "stack", "stacks", "template", "templates"],
            "display_name": "AWS CloudFormation",
            "resource_types": {
                "stack": "list_stacks",
            },
        },
        "cloudwatch": {
            "keywords": ["cloudwatch", "logs", "log", "metric", "metrics", "alarm", "alarms", "dashboard", "dashboards"],
            "display_name": "Amazon CloudWatch",
            "resource_types": {
                "alarm": "describe_alarms",
                "metric": "list_metrics",
                "log group": "describe_log_groups",
            },
        },
        "sns": {
            "keywords": ["sns", "notification", "notifications", "topic", "topics"],
            "display_name": "Amazon SNS",
            "resource_types": {
                "topic": "list_topics",
            },
        },
        "sqs": {
            "keywords": ["sqs", "queue", "queues", "message", "messages"],
            "display_name": "Amazon SQS",
            "resource_types": {
                "queue": "list_queues",
            },
        },
        "secretsmanager": {
            "keywords": ["secret", "secrets", "secretsmanager", "secrets manager"],
            "display_name": "AWS Secrets Manager",
            "resource_types": {
                "secret": "list_secrets",
            },
        },
        "ssm": {
            "keywords": ["ssm", "parameter", "parameters", "systems manager"],
            "display_name": "AWS Systems Manager",
            "resource_types": {
                "parameter": "describe_parameters",
            },
        },
        "route53": {
            "keywords": ["route53", "dns", "domain", "domains", "hosted zone", "hosted zones", "record", "records"],
            "display_name": "Amazon Route 53",
            "resource_types": {
                "hosted zone": "list_hosted_zones",
            },
        },
        "cloudfront": {
            "keywords": ["cloudfront", "cdn", "distribution", "distributions"],
            "display_name": "Amazon CloudFront",
            "resource_types": {
                "distribution": "list_distributions",
            },
        },
        "apigateway": {
            "keywords": ["apigateway", "api gateway", "api", "apis", "rest api"],
            "display_name": "Amazon API Gateway",
            "resource_types": {
                "api": "get_rest_apis",
            },
        },
        "elasticache": {
            "keywords": ["elasticache", "redis", "memcached", "cache"],
            "display_name": "Amazon ElastiCache",
            "resource_types": {
                "cluster": "describe_cache_clusters",
            },
        },
        "kinesis": {
            "keywords": ["kinesis", "stream", "streams"],
            "display_name": "Amazon Kinesis",
            "resource_types": {
                "stream": "list_streams",
            },
        },
        "sagemaker": {
            "keywords": ["sagemaker", "ml", "machine learning", "model", "notebook"],
            "display_name": "Amazon SageMaker",
            "resource_types": {
                "notebook": "list_notebook_instances",
                "model": "list_models",
            },
        },
    }

    # Default operations for common intents
    DEFAULT_OPERATIONS: dict[str, dict[str, str]] = {
        "s3": {"list": "list_buckets", "describe": "list_buckets", "get": "list_buckets"},
        "ec2": {"list": "describe_instances", "describe": "describe_instances", "get": "describe_instances"},
        "lambda": {"list": "list_functions", "describe": "list_functions", "get": "get_function"},
        "iam": {"list": "list_roles", "describe": "list_roles", "get": "get_role"},
        "rds": {"list": "describe_db_instances", "describe": "describe_db_instances"},
        "dynamodb": {"list": "list_tables", "describe": "list_tables"},
        "ecs": {"list": "list_clusters", "describe": "describe_clusters"},
        "cloudformation": {"list": "list_stacks", "describe": "describe_stacks"},
        "secretsmanager": {"list": "list_secrets", "describe": "list_secrets"},
    }

    def __init__(self) -> None:
        """Initialize the intent classifier."""
        self._compiled_patterns: dict[str, list[re.Pattern[str]]] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for performance."""
        for intent_pattern in self.INTENT_PATTERNS:
            self._compiled_patterns[intent_pattern.intent_type] = [
                re.compile(p, re.IGNORECASE) for p in intent_pattern.patterns
            ]

    def classify(self, query: str) -> ParseResult:
        """
        Classify a natural language query into a structured AWS command.

        Args:
            query: Natural language query (e.g., "list all S3 buckets")

        Returns:
            ParseResult with parsed command or error
        """
        query = query.strip()
        if not query:
            return ParseResult.error_result("Empty query provided")

        logger.debug("classifying_query", query=query)

        # Step 1: Classify intent
        intent = self._classify_intent(query)
        if not intent:
            return ParseResult.error_result(
                "Could not understand the intent. Try phrases like 'list buckets' or 'describe instances'.",
                suggestions=["list S3 buckets", "show EC2 instances", "get Lambda functions"],
            )

        # Step 2: Identify service
        service = self._identify_service(query)
        if not service:
            return ParseResult.error_result(
                "Could not identify the AWS service. Please specify a service like S3, EC2, or Lambda.",
                suggestions=["list S3 buckets", "describe EC2 instances", "get IAM roles"],
            )

        # Step 3: Determine operation
        operation = self._determine_operation(intent, service, query)

        # Step 4: Extract parameters
        parameters = self._extract_parameters(query, service.service_name, operation.operation_name)

        # Step 5: Build structured command
        command = StructuredCommand(
            service=service.service_name,
            operation=operation.operation_name,
            parameters={p.name: p.value for p in parameters},
            category=operation.category,
            raw_input=query,
            confidence=min(intent.confidence, service.confidence, operation.confidence),
        )

        logger.info(
            "query_classified",
            service=command.service,
            operation=command.operation,
            confidence=command.confidence,
        )

        return ParseResult.success_result(
            command=command,
            intent=intent,
            service=service,
            operation=operation,
            parameters=parameters,
        )

    def _classify_intent(self, query: str) -> ParsedIntent | None:
        """Classify the user's intent from the query."""
        query_lower = query.lower()

        for intent_pattern in self.INTENT_PATTERNS:
            for pattern in self._compiled_patterns[intent_pattern.intent_type]:
                if pattern.search(query_lower):
                    return ParsedIntent(
                        intent_type=intent_pattern.intent_type,
                        confidence=0.9,
                        raw_input=query,
                    )

        # Fallback: check for simple keyword presence
        if any(word in query_lower for word in ["list", "show", "get", "all"]):
            return ParsedIntent(intent_type="list", confidence=0.6, raw_input=query)

        return None

    def _identify_service(self, query: str) -> ParsedService | None:
        """Identify the AWS service from the query."""
        query_lower = query.lower()
        best_match: ParsedService | None = None
        best_score = 0.0

        for service_name, service_info in self.SERVICE_KEYWORDS.items():
            matched_keywords = []
            for keyword in service_info["keywords"]:
                if keyword in query_lower:
                    matched_keywords.append(keyword)

            if matched_keywords:
                # Score based on keyword matches and specificity
                score = len(matched_keywords) / len(service_info["keywords"])
                # Bonus for exact service name match
                if service_name in query_lower:
                    score += 0.3

                if score > best_score:
                    best_score = score
                    best_match = ParsedService(
                        service_name=service_name,
                        display_name=service_info["display_name"],
                        confidence=min(1.0, score),
                        matched_keywords=matched_keywords,
                    )

        return best_match

    def _determine_operation(
        self,
        intent: ParsedIntent,
        service: ParsedService,
        query: str,
    ) -> ParsedOperation:
        """Determine the specific AWS operation to call."""
        from aws_sage.safety.classifier import OperationClassifier

        query_lower = query.lower()
        service_info = self.SERVICE_KEYWORDS.get(service.service_name, {})
        resource_types = service_info.get("resource_types", {})

        # Check for specific resource type mentions
        for resource_type, operation in resource_types.items():
            if resource_type in query_lower:
                category = OperationClassifier.classify(service.service_name, operation)
                return ParsedOperation(
                    operation_name=operation,
                    category=category,
                    confidence=0.9,
                )

        # Fall back to default operation for intent
        default_ops = self.DEFAULT_OPERATIONS.get(service.service_name, {})
        if intent.intent_type in default_ops:
            operation = default_ops[intent.intent_type]
            category = OperationClassifier.classify(service.service_name, operation)
            return ParsedOperation(
                operation_name=operation,
                category=category,
                confidence=0.7,
            )

        # Last resort: construct operation name from intent prefix
        # This won't always work but provides a reasonable guess
        first_resource = list(resource_types.values())[0] if resource_types else f"{intent.intent_type}_resources"
        category = OperationClassifier.classify(service.service_name, first_resource)
        return ParsedOperation(
            operation_name=first_resource,
            category=category,
            confidence=0.5,
            suggested_alternatives=list(resource_types.values())[:3],
        )

    def _extract_parameters(
        self,
        query: str,
        service: str,
        operation: str,
    ) -> list[ParsedParameter]:
        """Extract parameters from the query."""
        parameters: list[ParsedParameter] = []
        query_lower = query.lower()

        # Extract common patterns

        # Region pattern
        region_match = re.search(r"(?:in|region)\s+(us-\w+-\d+|eu-\w+-\d+|ap-\w+-\d+)", query_lower)
        if region_match:
            parameters.append(ParsedParameter(
                name="region",
                value=region_match.group(1),
                source="explicit",
            ))

        # Instance ID pattern
        instance_match = re.search(r"(i-[a-f0-9]{8,17})", query_lower)
        if instance_match:
            parameters.append(ParsedParameter(
                name="InstanceIds",
                value=[instance_match.group(1)],
                source="explicit",
            ))

        # Bucket name pattern
        if service == "s3":
            bucket_match = re.search(r"bucket\s+['\"]?([a-z0-9][a-z0-9.-]{1,61}[a-z0-9])['\"]?", query_lower)
            if bucket_match:
                parameters.append(ParsedParameter(
                    name="Bucket",
                    value=bucket_match.group(1),
                    source="explicit",
                ))

        # Function name pattern
        if service == "lambda":
            func_match = re.search(r"function\s+['\"]?([a-zA-Z0-9_-]+)['\"]?", query_lower)
            if func_match:
                parameters.append(ParsedParameter(
                    name="FunctionName",
                    value=func_match.group(1),
                    source="explicit",
                ))

        # Tag filters
        tag_match = re.search(r"tagged?\s+(?:with\s+)?['\"]?(\w+)['\"]?\s*[=:]\s*['\"]?(\w+)['\"]?", query_lower)
        if tag_match:
            parameters.append(ParsedParameter(
                name="Filters",
                value=[{"Name": f"tag:{tag_match.group(1)}", "Values": [tag_match.group(2)]}],
                source="explicit",
            ))

        # Max results / limit
        limit_match = re.search(r"(?:top|first|limit)\s+(\d+)", query_lower)
        if limit_match:
            parameters.append(ParsedParameter(
                name="MaxResults",
                value=int(limit_match.group(1)),
                source="explicit",
            ))

        return parameters


def fuzzy_match(query: str, options: list[str], threshold: float = 0.6) -> list[tuple[str, float]]:
    """Find fuzzy matches for a query in a list of options."""
    matches = []
    query_lower = query.lower()

    for option in options:
        ratio = SequenceMatcher(None, query_lower, option.lower()).ratio()
        if ratio >= threshold:
            matches.append((option, ratio))

    return sorted(matches, key=lambda x: x[1], reverse=True)


# Global classifier instance
_classifier: IntentClassifier | None = None


def get_intent_classifier() -> IntentClassifier:
    """Get the global intent classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier
