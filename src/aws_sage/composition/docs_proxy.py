"""AWS Documentation MCP proxy for composition."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class DocSearchResult:
    """Result from documentation search."""

    title: str
    url: str
    snippet: str
    service: str | None = None
    relevance_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "service": self.service,
            "relevance_score": self.relevance_score,
        }


class AWSDocsProxy:
    """
    Proxy for AWS Documentation MCP server.

    This class provides integration with the official AWS Documentation
    MCP server for searching and retrieving AWS documentation.

    When the official AWS Docs MCP server is available, this proxy will
    forward requests to it. Otherwise, it provides fallback functionality
    using public AWS documentation URLs.
    """

    # AWS Documentation base URLs
    BASE_URLS = {
        "cli": "https://docs.aws.amazon.com/cli/latest/reference",
        "sdk-python": "https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services",
        "general": "https://docs.aws.amazon.com",
    }

    # Service to documentation mapping
    SERVICE_DOCS: dict[str, str] = {
        "s3": "https://docs.aws.amazon.com/AmazonS3/latest/userguide/",
        "ec2": "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/",
        "lambda": "https://docs.aws.amazon.com/lambda/latest/dg/",
        "iam": "https://docs.aws.amazon.com/IAM/latest/UserGuide/",
        "rds": "https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/",
        "dynamodb": "https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/",
        "ecs": "https://docs.aws.amazon.com/AmazonECS/latest/developerguide/",
        "eks": "https://docs.aws.amazon.com/eks/latest/userguide/",
        "cloudformation": "https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/",
        "cloudwatch": "https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/",
        "sns": "https://docs.aws.amazon.com/sns/latest/dg/",
        "sqs": "https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/",
        "kinesis": "https://docs.aws.amazon.com/streams/latest/dev/",
        "secretsmanager": "https://docs.aws.amazon.com/secretsmanager/latest/userguide/",
        "kms": "https://docs.aws.amazon.com/kms/latest/developerguide/",
        "route53": "https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/",
        "apigateway": "https://docs.aws.amazon.com/apigateway/latest/developerguide/",
        "cognito": "https://docs.aws.amazon.com/cognito/latest/developerguide/",
    }

    def __init__(self, mcp_server_url: str | None = None):
        """
        Initialize the AWS Docs proxy.

        Args:
            mcp_server_url: URL of the AWS Docs MCP server (optional)
        """
        self.mcp_server_url = mcp_server_url
        self._connected = False

    async def connect(self) -> bool:
        """Connect to the AWS Docs MCP server."""
        if self.mcp_server_url:
            try:
                # Attempt to connect to MCP server
                # This is a placeholder for actual MCP client connection
                logger.info("connecting_to_docs_mcp", url=self.mcp_server_url)
                self._connected = True
                return True
            except Exception as e:
                logger.warning("failed_to_connect_docs_mcp", error=str(e))
                return False
        return False

    async def search(
        self,
        query: str,
        service: str | None = None,
        max_results: int = 5,
    ) -> list[DocSearchResult]:
        """
        Search AWS documentation.

        Args:
            query: Search query
            service: Optional service to scope the search
            max_results: Maximum number of results

        Returns:
            List of documentation search results
        """
        logger.info("searching_docs", query=query, service=service)

        if self._connected and self.mcp_server_url:
            # Forward to MCP server
            return await self._search_via_mcp(query, service, max_results)

        # Fallback: Generate helpful documentation links
        return self._generate_doc_links(query, service, max_results)

    async def _search_via_mcp(
        self,
        query: str,
        service: str | None,
        max_results: int,
    ) -> list[DocSearchResult]:
        """Search via MCP server (placeholder for actual implementation)."""
        # This would use the MCP client to call the docs server
        # For now, fall back to local generation
        return self._generate_doc_links(query, service, max_results)

    def _generate_doc_links(
        self,
        query: str,
        service: str | None,
        max_results: int,
    ) -> list[DocSearchResult]:
        """Generate helpful documentation links based on query."""
        results: list[DocSearchResult] = []

        # If service is specified, add service-specific docs
        if service and service.lower() in self.SERVICE_DOCS:
            service_lower = service.lower()
            results.append(
                DocSearchResult(
                    title=f"{service.upper()} User Guide",
                    url=self.SERVICE_DOCS[service_lower],
                    snippet=f"Official AWS {service.upper()} documentation and user guide.",
                    service=service_lower,
                    relevance_score=1.0,
                )
            )

            # Add CLI reference
            results.append(
                DocSearchResult(
                    title=f"AWS CLI - {service}",
                    url=f"{self.BASE_URLS['cli']}/{service_lower}/index.html",
                    snippet=f"AWS CLI reference for {service.upper()} commands.",
                    service=service_lower,
                    relevance_score=0.9,
                )
            )

            # Add Boto3 reference
            results.append(
                DocSearchResult(
                    title=f"Boto3 - {service}",
                    url=f"{self.BASE_URLS['sdk-python']}/{service_lower}.html",
                    snippet=f"Boto3 (Python SDK) reference for {service.upper()}.",
                    service=service_lower,
                    relevance_score=0.8,
                )
            )
        else:
            # General AWS docs
            results.append(
                DocSearchResult(
                    title="AWS Documentation Home",
                    url=self.BASE_URLS["general"],
                    snippet="Browse all AWS documentation and user guides.",
                    relevance_score=0.5,
                )
            )

        return results[:max_results]

    def get_service_doc_url(self, service: str) -> str | None:
        """Get the documentation URL for a service."""
        return self.SERVICE_DOCS.get(service.lower())

    def get_cli_reference_url(self, service: str, operation: str | None = None) -> str:
        """Get the AWS CLI reference URL for a service/operation."""
        base = f"{self.BASE_URLS['cli']}/{service.lower()}"
        if operation:
            # Convert snake_case to kebab-case for CLI docs
            op_kebab = operation.replace("_", "-").lower()
            return f"{base}/{op_kebab}.html"
        return f"{base}/index.html"

    def get_boto3_reference_url(self, service: str, operation: str | None = None) -> str:
        """Get the Boto3 reference URL for a service/operation."""
        base = f"{self.BASE_URLS['sdk-python']}/{service.lower()}.html"
        if operation:
            # Boto3 uses PascalCase for operations
            return f"{base}#{service.upper()}.Client.{operation}"
        return base


# Global proxy instance
_docs_proxy: AWSDocsProxy | None = None


def get_docs_proxy(mcp_server_url: str | None = None) -> AWSDocsProxy:
    """Get the global docs proxy instance."""
    global _docs_proxy
    if _docs_proxy is None:
        _docs_proxy = AWSDocsProxy(mcp_server_url)
    return _docs_proxy
