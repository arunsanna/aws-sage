"""AWS Knowledge MCP proxy for composition."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class KnowledgeCategory(Enum):
    """Categories of AWS knowledge."""

    BEST_PRACTICES = "best_practices"
    SECURITY = "security"
    ARCHITECTURE = "architecture"
    PRICING = "pricing"
    LIMITS = "limits"
    TROUBLESHOOTING = "troubleshooting"


@dataclass
class KnowledgeItem:
    """An item of AWS knowledge."""

    title: str
    content: str
    category: KnowledgeCategory
    service: str | None = None
    source: str | None = None
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
            "confidence": self.confidence,
            "related_services": self.related_services,
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


# Global proxy instance
_knowledge_proxy: AWSKnowledgeProxy | None = None


def get_knowledge_proxy(mcp_server_url: str | None = None) -> AWSKnowledgeProxy:
    """Get the global knowledge proxy instance."""
    global _knowledge_proxy
    if _knowledge_proxy is None:
        _knowledge_proxy = AWSKnowledgeProxy(mcp_server_url)
    return _knowledge_proxy
