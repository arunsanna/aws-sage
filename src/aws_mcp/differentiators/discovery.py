"""Cross-service resource discovery for AWS MCP Pro."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from aws_mcp.core.session import get_session_manager

logger = structlog.get_logger()


@dataclass
class DiscoveredResource:
    """A discovered AWS resource."""

    arn: str
    service: str
    resource_type: str
    name: str | None = None
    region: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "arn": self.arn,
            "service": self.service,
            "resource_type": self.resource_type,
            "name": self.name,
            "region": self.region,
            "tags": self.tags,
            "metadata": self.metadata,
        }


@dataclass
class DiscoveryResult:
    """Result of a resource discovery operation."""

    resources: list[DiscoveredResource]
    total_count: int
    services_searched: list[str]
    truncated: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resources": [r.to_dict() for r in self.resources],
            "total_count": self.total_count,
            "services_searched": self.services_searched,
            "truncated": self.truncated,
            "errors": self.errors if self.errors else None,
        }


class ResourceDiscovery:
    """Cross-service resource discovery using Resource Groups Tagging API."""

    # Services that support tagging
    TAGGABLE_SERVICES = [
        "ec2",
        "s3",
        "lambda",
        "rds",
        "dynamodb",
        "ecs",
        "eks",
        "elasticache",
        "elasticsearch",
        "sns",
        "sqs",
        "secretsmanager",
        "kms",
        "cloudformation",
        "apigateway",
        "cloudfront",
        "route53",
        "iam",
    ]

    def __init__(self, max_results: int = 100):
        """Initialize the resource discovery."""
        self.max_results = max_results

    async def discover_by_tags(
        self,
        tags: dict[str, str],
        services: list[str] | None = None,
        region: str | None = None,
    ) -> DiscoveryResult:
        """
        Discover resources across services by tags.

        Args:
            tags: Tags to search for (e.g., {"Environment": "production"})
            services: Services to search (default: all taggable services)
            region: Region to search

        Returns:
            DiscoveryResult with found resources
        """
        logger.info("discovering_resources", tags=tags, services=services)

        session_mgr = get_session_manager()
        client = session_mgr.get_client("resourcegroupstaggingapi", region)

        # Build tag filters
        tag_filters = [{"Key": k, "Values": [v]} for k, v in tags.items()]

        # Build resource type filters
        resource_type_filters = []
        services_to_search = services or self.TAGGABLE_SERVICES
        for svc in services_to_search:
            resource_type_filters.append(f"{svc}:")

        resources: list[DiscoveredResource] = []
        errors: list[str] = []

        try:
            paginator = client.get_paginator("get_resources")
            params: dict[str, Any] = {"TagFilters": tag_filters}
            if resource_type_filters:
                params["ResourceTypeFilters"] = resource_type_filters

            for page in paginator.paginate(**params, PaginationConfig={"MaxItems": self.max_results}):
                for mapping in page.get("ResourceTagMappingList", []):
                    resource = self._parse_resource_mapping(mapping)
                    if resource:
                        resources.append(resource)

                    if len(resources) >= self.max_results:
                        break

                if len(resources) >= self.max_results:
                    break

        except Exception as e:
            logger.error("discovery_failed", error=str(e))
            errors.append(str(e))

        return DiscoveryResult(
            resources=resources,
            total_count=len(resources),
            services_searched=services_to_search,
            truncated=len(resources) >= self.max_results,
            errors=errors,
        )

    async def discover_by_name_pattern(
        self,
        pattern: str,
        services: list[str] | None = None,
        region: str | None = None,
    ) -> DiscoveryResult:
        """
        Discover resources by name pattern.

        This searches for resources with names matching the pattern.
        Note: This is less efficient than tag-based discovery.

        Args:
            pattern: Name pattern to search for (supports * wildcard)
            services: Services to search
            region: Region to search

        Returns:
            DiscoveryResult with found resources
        """
        logger.info("discovering_by_name", pattern=pattern, services=services)

        # Use tag:Name for pattern matching
        # This won't catch all resources but covers common cases
        return await self.discover_by_tags(
            tags={"Name": pattern.replace("*", "")},
            services=services,
            region=region,
        )

    def _parse_resource_mapping(self, mapping: dict[str, Any]) -> DiscoveredResource | None:
        """Parse a resource tag mapping into a DiscoveredResource."""
        arn = mapping.get("ResourceARN", "")
        if not arn:
            return None

        # Parse ARN: arn:partition:service:region:account:resource
        parts = arn.split(":")
        if len(parts) < 6:
            return None

        service = parts[2]
        region = parts[3] if parts[3] else None

        # Extract resource type and name from the resource part
        resource_part = ":".join(parts[5:])
        if "/" in resource_part:
            resource_type, name = resource_part.split("/", 1)
        else:
            resource_type = resource_part
            name = None

        # Extract tags
        tags = {t["Key"]: t["Value"] for t in mapping.get("Tags", [])}

        # Try to get name from tags if not in ARN
        if not name and "Name" in tags:
            name = tags["Name"]

        return DiscoveredResource(
            arn=arn,
            service=service,
            resource_type=resource_type,
            name=name,
            region=region,
            tags=tags,
        )


# Global instance
_discovery: ResourceDiscovery | None = None


def get_resource_discovery() -> ResourceDiscovery:
    """Get the global resource discovery instance."""
    global _discovery
    if _discovery is None:
        _discovery = ResourceDiscovery()
    return _discovery
