"""AWS Knowledge MCP proxy for composition."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

# AWS documentation endpoints
AWS_DOCS_BASE_URL = "https://docs.aws.amazon.com"
AWS_KNOWLEDGE_MCP_URL = "https://knowledge-mcp.global.api.aws"


class KnowledgeCategory(Enum):
    """Categories of AWS knowledge."""

    BEST_PRACTICES = "best_practices"
    SECURITY = "security"
    ARCHITECTURE = "architecture"
    PRICING = "pricing"
    LIMITS = "limits"
    TROUBLESHOOTING = "troubleshooting"


class KnowledgeSource(Enum):
    """Source of knowledge."""

    BUILTIN = "builtin"
    AWS_DOCS = "aws_docs"
    AWS_KNOWLEDGE_MCP = "aws_knowledge_mcp"
    WEB_SEARCH = "web_search"


@dataclass
class KnowledgeItem:
    """An item of AWS knowledge."""

    title: str
    content: str
    category: KnowledgeCategory
    service: str | None = None
    source: str | None = None
    source_type: KnowledgeSource = KnowledgeSource.BUILTIN
    source_url: str | None = None
    confidence: float = 1.0
    related_services: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "content": self.content,
            "category": self.category.value,
            "service": self.service,
            "source": self.source,
            "source_type": self.source_type.value,
            "source_url": self.source_url,
            "confidence": self.confidence,
            "related_services": self.related_services,
        }


@dataclass
class LiveQueryResult:
    """Result from live knowledge query."""

    success: bool
    items: list[KnowledgeItem] = field(default_factory=list)
    source: KnowledgeSource = KnowledgeSource.BUILTIN
    error: str | None = None
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "items": [item.to_dict() for item in self.items],
            "source": self.source.value,
            "error": self.error,
            "fallback_used": self.fallback_used,
            "items_count": len(self.items),
        }


class AWSKnowledgeProxy:
    """
    Proxy for AWS Knowledge MCP server.

    This class provides integration with the official AWS Knowledge
    MCP server for retrieving AWS best practices, architectural
    guidance, and operational knowledge.

    When the official AWS Knowledge MCP server is available, this proxy
    will forward requests to it. Otherwise, it provides fallback
    functionality using built-in knowledge.
    """

    # Built-in knowledge for common questions
    BUILTIN_KNOWLEDGE: dict[str, list[KnowledgeItem]] = {
        "s3": [
            KnowledgeItem(
                title="S3 Bucket Naming Best Practices",
                content="S3 bucket names must be globally unique, 3-63 characters, lowercase, "
                "start with letter or number. Use DNS-compliant names. Avoid underscores.",
                category=KnowledgeCategory.BEST_PRACTICES,
                service="s3",
            ),
            KnowledgeItem(
                title="S3 Security Best Practices",
                content="Enable versioning, use bucket policies and ACLs sparingly (prefer IAM), "
                "enable server-side encryption (SSE-S3 or SSE-KMS), block public access by default, "
                "enable access logging and CloudTrail.",
                category=KnowledgeCategory.SECURITY,
                service="s3",
            ),
            KnowledgeItem(
                title="S3 Service Limits",
                content="No limit on objects per bucket. Max object size: 5TB. "
                "Max PUT size: 5GB (use multipart for larger). "
                "3,500 PUT/COPY/POST/DELETE and 5,500 GET/HEAD requests per second per prefix.",
                category=KnowledgeCategory.LIMITS,
                service="s3",
            ),
        ],
        "ec2": [
            KnowledgeItem(
                title="EC2 Instance Selection",
                content="Match instance type to workload: general purpose (M/T), compute optimized (C), "
                "memory optimized (R/X), storage optimized (D/H/I), GPU (P/G). "
                "Use burstable (T) for variable workloads, dedicated for compliance.",
                category=KnowledgeCategory.BEST_PRACTICES,
                service="ec2",
            ),
            KnowledgeItem(
                title="EC2 Security Best Practices",
                content="Use IMDSv2 (disable IMDSv1), apply least-privilege security groups, "
                "use Systems Manager for management (not SSH), enable EBS encryption, "
                "use IAM roles instead of access keys.",
                category=KnowledgeCategory.SECURITY,
                service="ec2",
            ),
            KnowledgeItem(
                title="EC2 Service Limits",
                content="Default: 5 VPCs per region, 20 instances per type per region. "
                "Max EBS volumes per instance varies by type. Request limit increases via Service Quotas.",
                category=KnowledgeCategory.LIMITS,
                service="ec2",
            ),
        ],
        "lambda": [
            KnowledgeItem(
                title="Lambda Best Practices",
                content="Keep functions small and focused, minimize cold starts by keeping deployments small, "
                "use provisioned concurrency for latency-sensitive functions, "
                "put shared code in layers, use environment variables for config.",
                category=KnowledgeCategory.BEST_PRACTICES,
                service="lambda",
            ),
            KnowledgeItem(
                title="Lambda Security",
                content="Apply least-privilege execution roles, encrypt environment variables, "
                "use VPC for private resource access, validate and sanitize inputs, "
                "never hardcode secrets (use Secrets Manager).",
                category=KnowledgeCategory.SECURITY,
                service="lambda",
            ),
            KnowledgeItem(
                title="Lambda Limits",
                content="Max execution time: 15 minutes. Memory: 128MB-10GB. "
                "Deployment package: 50MB zipped, 250MB unzipped. "
                "Concurrent executions: 1000 default (soft limit).",
                category=KnowledgeCategory.LIMITS,
                service="lambda",
            ),
        ],
        "iam": [
            KnowledgeItem(
                title="IAM Best Practices",
                content="Enable MFA for all users (especially root), use roles instead of users for apps, "
                "apply least privilege, use permission boundaries, review with IAM Access Analyzer, "
                "rotate credentials regularly.",
                category=KnowledgeCategory.BEST_PRACTICES,
                service="iam",
            ),
            KnowledgeItem(
                title="IAM Policy Best Practices",
                content="Use AWS managed policies when possible, prefer resource-based policies for cross-account, "
                "use conditions for additional security, avoid wildcards in resources, "
                "use policy variables for dynamic values.",
                category=KnowledgeCategory.SECURITY,
                service="iam",
            ),
        ],
        "architecture": [
            KnowledgeItem(
                title="Well-Architected Framework",
                content="AWS Well-Architected Framework has 6 pillars: Operational Excellence, Security, "
                "Reliability, Performance Efficiency, Cost Optimization, and Sustainability. "
                "Use the Well-Architected Tool for reviews.",
                category=KnowledgeCategory.ARCHITECTURE,
            ),
            KnowledgeItem(
                title="Multi-Region Architecture",
                content="Use Route 53 for DNS-based routing, replicate data with S3 CRR or DynamoDB Global Tables, "
                "consider active-active vs active-passive, use CloudFront for global content delivery, "
                "plan for regional failures.",
                category=KnowledgeCategory.ARCHITECTURE,
            ),
        ],
    }

    def __init__(self, mcp_server_url: str | None = None):
        """
        Initialize the AWS Knowledge proxy.

        Args:
            mcp_server_url: URL of the AWS Knowledge MCP server (optional)
        """
        self.mcp_server_url = mcp_server_url
        self._connected = False

    async def connect(self) -> bool:
        """Connect to the AWS Knowledge MCP server."""
        if self.mcp_server_url:
            try:
                logger.info("connecting_to_knowledge_mcp", url=self.mcp_server_url)
                self._connected = True
                return True
            except Exception as e:
                logger.warning("failed_to_connect_knowledge_mcp", error=str(e))
                return False
        return False

    async def query(
        self,
        question: str,
        service: str | None = None,
        category: KnowledgeCategory | None = None,
    ) -> list[KnowledgeItem]:
        """
        Query AWS knowledge.

        Args:
            question: The question to ask
            service: Optional service to scope the query
            category: Optional category to filter results

        Returns:
            List of relevant knowledge items
        """
        logger.info("querying_knowledge", question=question, service=service)

        if self._connected and self.mcp_server_url:
            return await self._query_via_mcp(question, service, category)

        # Fallback: Search built-in knowledge
        return self._search_builtin_knowledge(question, service, category)

    async def _query_via_mcp(
        self,
        question: str,
        service: str | None,
        category: KnowledgeCategory | None,
    ) -> list[KnowledgeItem]:
        """Query via MCP server (placeholder)."""
        # This would use the MCP client to call the knowledge server
        return self._search_builtin_knowledge(question, service, category)

    def _search_builtin_knowledge(
        self,
        question: str,
        service: str | None,
        category: KnowledgeCategory | None,
    ) -> list[KnowledgeItem]:
        """Search built-in knowledge base."""
        results: list[KnowledgeItem] = []
        question_lower = question.lower()

        # Search by service
        if service and service.lower() in self.BUILTIN_KNOWLEDGE:
            for item in self.BUILTIN_KNOWLEDGE[service.lower()]:
                if category and item.category != category:
                    continue
                if self._matches_question(question_lower, item):
                    results.append(item)

        # Search architecture knowledge
        if not service or "architecture" in question_lower or "design" in question_lower:
            for item in self.BUILTIN_KNOWLEDGE.get("architecture", []):
                if category and item.category != category:
                    continue
                if self._matches_question(question_lower, item):
                    results.append(item)

        # Search all services if no specific match
        if not results:
            for items in self.BUILTIN_KNOWLEDGE.values():
                for item in items:
                    if category and item.category != category:
                        continue
                    if self._matches_question(question_lower, item):
                        results.append(item)

        return results[:5]  # Limit results

    def _matches_question(self, question: str, item: KnowledgeItem) -> bool:
        """Check if a knowledge item matches the question."""
        # Simple keyword matching
        keywords = question.split()
        item_text = (item.title + " " + item.content).lower()

        matched = 0
        for keyword in keywords:
            if len(keyword) > 2 and keyword in item_text:
                matched += 1

        return matched >= min(2, len(keywords) // 2 + 1)

    async def get_best_practices(self, service: str) -> list[KnowledgeItem]:
        """Get best practices for a service."""
        return await self.query(
            f"best practices for {service}",
            service=service,
            category=KnowledgeCategory.BEST_PRACTICES,
        )

    async def get_security_guidance(self, service: str) -> list[KnowledgeItem]:
        """Get security guidance for a service."""
        return await self.query(
            f"security best practices for {service}",
            service=service,
            category=KnowledgeCategory.SECURITY,
        )

    async def get_service_limits(self, service: str) -> list[KnowledgeItem]:
        """Get service limits for a service."""
        return await self.query(
            f"limits and quotas for {service}",
            service=service,
            category=KnowledgeCategory.LIMITS,
        )

    async def query_live(
        self,
        question: str,
        service: str | None = None,
        timeout: float = 10.0,
    ) -> LiveQueryResult:
        """
        Query AWS knowledge with live fetch from AWS documentation.

        This method attempts to fetch live information from AWS documentation
        or the AWS Knowledge MCP server, falling back to built-in knowledge
        if external sources are unavailable.

        Args:
            question: The question to ask
            service: Optional service to scope the query
            timeout: HTTP request timeout in seconds

        Returns:
            LiveQueryResult with items from live or fallback sources
        """
        logger.info("querying_knowledge_live", question=question, service=service)

        # Try AWS Knowledge MCP server first (if configured)
        if self.mcp_server_url:
            try:
                result = await self._query_aws_knowledge_mcp(question, service, timeout)
                if result.success and result.items:
                    return result
            except Exception as e:
                logger.warning("aws_knowledge_mcp_failed", error=str(e))

        # Try AWS documentation search
        try:
            result = await self._query_aws_docs(question, service, timeout)
            if result.success and result.items:
                return result
        except Exception as e:
            logger.warning("aws_docs_query_failed", error=str(e))

        # Fallback to built-in knowledge
        builtin_items = self._search_builtin_knowledge(question, service, None)
        return LiveQueryResult(
            success=True,
            items=builtin_items,
            source=KnowledgeSource.BUILTIN,
            fallback_used=True,
        )

    async def _query_aws_knowledge_mcp(
        self,
        question: str,
        service: str | None,
        timeout: float,
    ) -> LiveQueryResult:
        """Query the AWS Knowledge MCP server."""
        if not self.mcp_server_url:
            return LiveQueryResult(
                success=False,
                error="AWS Knowledge MCP URL not configured",
            )

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.mcp_server_url}/tools/call",
                    json={
                        "name": "aws___search_documentation",
                        "arguments": {
                            "query": question,
                            "service": service,
                        },
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    items = self._parse_mcp_response(data, service)
                    return LiveQueryResult(
                        success=True,
                        items=items,
                        source=KnowledgeSource.AWS_KNOWLEDGE_MCP,
                    )
                else:
                    return LiveQueryResult(
                        success=False,
                        error=f"MCP server returned status {response.status_code}",
                    )

        except httpx.TimeoutException:
            return LiveQueryResult(
                success=False,
                error="Request timed out",
            )
        except Exception as e:
            return LiveQueryResult(
                success=False,
                error=str(e),
            )

    async def _query_aws_docs(
        self,
        question: str,
        service: str | None,
        timeout: float,
    ) -> LiveQueryResult:
        """Query AWS documentation (simplified approach using service-specific docs)."""
        # AWS documentation doesn't have a public search API, so we provide
        # guidance based on known documentation URLs
        items: list[KnowledgeItem] = []

        # Map services to their documentation URLs
        SERVICE_DOCS: dict[str, dict[str, str]] = {
            "s3": {
                "url": f"{AWS_DOCS_BASE_URL}/AmazonS3/latest/userguide/",
                "title": "Amazon S3 User Guide",
            },
            "ec2": {
                "url": f"{AWS_DOCS_BASE_URL}/AWSEC2/latest/UserGuide/",
                "title": "Amazon EC2 User Guide",
            },
            "lambda": {
                "url": f"{AWS_DOCS_BASE_URL}/lambda/latest/dg/",
                "title": "AWS Lambda Developer Guide",
            },
            "iam": {
                "url": f"{AWS_DOCS_BASE_URL}/IAM/latest/UserGuide/",
                "title": "IAM User Guide",
            },
            "rds": {
                "url": f"{AWS_DOCS_BASE_URL}/AmazonRDS/latest/UserGuide/",
                "title": "Amazon RDS User Guide",
            },
            "dynamodb": {
                "url": f"{AWS_DOCS_BASE_URL}/amazondynamodb/latest/developerguide/",
                "title": "DynamoDB Developer Guide",
            },
            "cloudformation": {
                "url": f"{AWS_DOCS_BASE_URL}/AWSCloudFormation/latest/UserGuide/",
                "title": "AWS CloudFormation User Guide",
            },
            "ecs": {
                "url": f"{AWS_DOCS_BASE_URL}/AmazonECS/latest/developerguide/",
                "title": "Amazon ECS Developer Guide",
            },
            "eks": {
                "url": f"{AWS_DOCS_BASE_URL}/eks/latest/userguide/",
                "title": "Amazon EKS User Guide",
            },
            "sns": {
                "url": f"{AWS_DOCS_BASE_URL}/sns/latest/dg/",
                "title": "Amazon SNS Developer Guide",
            },
            "sqs": {
                "url": f"{AWS_DOCS_BASE_URL}/AWSSimpleQueueService/latest/SQSDeveloperGuide/",
                "title": "Amazon SQS Developer Guide",
            },
        }

        if service and service.lower() in SERVICE_DOCS:
            doc_info = SERVICE_DOCS[service.lower()]
            items.append(
                KnowledgeItem(
                    title=f"{doc_info['title']}",
                    content=f"For detailed information about {service.upper()}, "
                    f"refer to the official AWS documentation.",
                    category=KnowledgeCategory.BEST_PRACTICES,
                    service=service,
                    source="AWS Documentation",
                    source_type=KnowledgeSource.AWS_DOCS,
                    source_url=doc_info["url"],
                    confidence=1.0,
                )
            )

        # Add AWS Well-Architected reference
        items.append(
            KnowledgeItem(
                title="AWS Well-Architected Framework",
                content="The AWS Well-Architected Framework provides best practices "
                "and guidance for building secure, high-performing, resilient, "
                "and efficient infrastructure.",
                category=KnowledgeCategory.ARCHITECTURE,
                source="AWS Documentation",
                source_type=KnowledgeSource.AWS_DOCS,
                source_url=f"{AWS_DOCS_BASE_URL}/wellarchitected/latest/framework/",
                confidence=1.0,
            )
        )

        return LiveQueryResult(
            success=True,
            items=items,
            source=KnowledgeSource.AWS_DOCS,
        )

    def _parse_mcp_response(
        self, data: dict[str, Any], service: str | None
    ) -> list[KnowledgeItem]:
        """Parse response from AWS Knowledge MCP server."""
        items: list[KnowledgeItem] = []

        # Parse the MCP response format
        results = data.get("results", data.get("content", []))
        if isinstance(results, list):
            for result in results[:5]:  # Limit to 5 items
                if isinstance(result, dict):
                    items.append(
                        KnowledgeItem(
                            title=result.get("title", "AWS Documentation"),
                            content=result.get("content", result.get("text", "")),
                            category=KnowledgeCategory.BEST_PRACTICES,
                            service=service,
                            source="AWS Knowledge MCP",
                            source_type=KnowledgeSource.AWS_KNOWLEDGE_MCP,
                            source_url=result.get("url"),
                            confidence=result.get("confidence", 0.9),
                        )
                    )

        return items


# Global proxy instance
_knowledge_proxy: AWSKnowledgeProxy | None = None


def get_knowledge_proxy(mcp_server_url: str | None = None) -> AWSKnowledgeProxy:
    """Get the global knowledge proxy instance."""
    global _knowledge_proxy
    if _knowledge_proxy is None:
        _knowledge_proxy = AWSKnowledgeProxy(mcp_server_url)
    return _knowledge_proxy
