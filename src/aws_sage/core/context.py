"""Conversation context management for AWS MCP Pro."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from aws_sage.config import get_config

logger = structlog.get_logger()


@dataclass
class ResourceReference:
    """Reference to an AWS resource."""

    arn: str
    service: str
    resource_type: str
    name: str | None = None
    region: str | None = None
    accessed_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arn": self.arn,
            "service": self.service,
            "resource_type": self.resource_type,
            "name": self.name,
            "region": self.region,
            "accessed_at": self.accessed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResourceReference":
        return cls(
            arn=data["arn"],
            service=data["service"],
            resource_type=data["resource_type"],
            name=data.get("name"),
            region=data.get("region"),
            accessed_at=datetime.fromisoformat(data["accessed_at"]),
        )


@dataclass
class QueryRecord:
    """Record of a previous query."""

    query: str
    service: str | None
    operation: str | None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    success: bool = True
    result_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "service": self.service,
            "operation": self.operation,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "result_count": self.result_count,
        }


@dataclass
class ConversationContext:
    """Maintains conversation context across tool calls."""

    # Recent resources (FIFO queue)
    recent_resources: deque[ResourceReference] = field(
        default_factory=lambda: deque(maxlen=get_config().max_recent_resources)
    )

    # User-defined aliases
    aliases: dict[str, str] = field(default_factory=dict)

    # Query history
    query_history: deque[QueryRecord] = field(default_factory=lambda: deque(maxlen=50))

    # Current investigation context
    current_investigation: dict[str, Any] | None = None

    # Session metadata
    session_start: datetime = field(default_factory=datetime.utcnow)

    def add_resource(self, resource: ResourceReference) -> None:
        """Add a resource to recent resources."""
        # Remove if already exists (to move to front)
        self.recent_resources = deque(
            [r for r in self.recent_resources if r.arn != resource.arn],
            maxlen=self.recent_resources.maxlen,
        )
        self.recent_resources.appendleft(resource)
        logger.debug("resource_added_to_context", arn=resource.arn)

    def add_resources_from_response(
        self, service: str, resource_type: str, items: list[dict[str, Any]]
    ) -> None:
        """Extract and add resources from an AWS API response."""
        for item in items[:10]:  # Limit to first 10
            arn = self._extract_arn(item, service, resource_type)
            if arn:
                name = self._extract_name(item)
                self.add_resource(
                    ResourceReference(
                        arn=arn,
                        service=service,
                        resource_type=resource_type,
                        name=name,
                    )
                )

    def _extract_arn(
        self, item: dict[str, Any], service: str, resource_type: str
    ) -> str | None:
        """Extract ARN from a resource item."""
        # Common ARN field names
        arn_keys = ["Arn", "ARN", "arn", "FunctionArn", "RoleArn", "BucketArn", "TopicArn"]
        for key in arn_keys:
            if key in item:
                return item[key]

        # For S3 buckets, construct ARN
        if service == "s3" and "Name" in item:
            return f"arn:aws:s3:::{item['Name']}"

        # For EC2 instances
        if service == "ec2" and "InstanceId" in item:
            return f"arn:aws:ec2:::instance/{item['InstanceId']}"

        return None

    def _extract_name(self, item: dict[str, Any]) -> str | None:
        """Extract a human-readable name from a resource item."""
        name_keys = ["Name", "name", "FunctionName", "RoleName", "BucketName", "TopicName"]
        for key in name_keys:
            if key in item:
                return item[key]

        # Check tags for Name
        tags = item.get("Tags", item.get("tags", []))
        if isinstance(tags, list):
            for tag in tags:
                if tag.get("Key") == "Name":
                    return tag.get("Value")

        return None

    def record_query(
        self,
        query: str,
        service: str | None = None,
        operation: str | None = None,
        success: bool = True,
        result_count: int | None = None,
    ) -> None:
        """Record a query in history."""
        self.query_history.appendleft(
            QueryRecord(
                query=query,
                service=service,
                operation=operation,
                success=success,
                result_count=result_count,
            )
        )

    def set_alias(self, name: str, value: str) -> None:
        """Set a user-defined alias."""
        self.aliases[name.lower()] = value
        logger.info("alias_set", name=name, value=value)

    def remove_alias(self, name: str) -> bool:
        """Remove an alias."""
        if name.lower() in self.aliases:
            del self.aliases[name.lower()]
            return True
        return False

    def resolve_alias(self, text: str) -> str:
        """Resolve any aliases in the text."""
        result = text
        for name, value in self.aliases.items():
            # Replace whole word matches only
            import re

            result = re.sub(rf"\b{re.escape(name)}\b", value, result, flags=re.IGNORECASE)
        return result

    def get_recent_resource(self, index: int = 0) -> ResourceReference | None:
        """Get a recent resource by index (0 = most recent)."""
        if 0 <= index < len(self.recent_resources):
            return self.recent_resources[index]
        return None

    def get_recent_resource_by_type(
        self, service: str, resource_type: str | None = None
    ) -> ResourceReference | None:
        """Get the most recent resource of a specific type."""
        for resource in self.recent_resources:
            if resource.service == service:
                if resource_type is None or resource.resource_type == resource_type:
                    return resource
        return None

    def start_investigation(self, incident_type: str, context: dict[str, Any]) -> None:
        """Start an investigation context."""
        self.current_investigation = {
            "type": incident_type,
            "started_at": datetime.utcnow().isoformat(),
            "context": context,
            "findings": [],
        }

    def add_investigation_finding(self, finding: dict[str, Any]) -> None:
        """Add a finding to the current investigation."""
        if self.current_investigation:
            self.current_investigation["findings"].append(
                {**finding, "timestamp": datetime.utcnow().isoformat()}
            )

    def end_investigation(self) -> dict[str, Any] | None:
        """End the current investigation and return summary."""
        result = self.current_investigation
        self.current_investigation = None
        return result

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary for serialization."""
        return {
            "recent_resources": [r.to_dict() for r in self.recent_resources],
            "aliases": self.aliases,
            "query_history": [q.to_dict() for q in list(self.query_history)[:10]],
            "current_investigation": self.current_investigation,
            "session_start": self.session_start.isoformat(),
        }

    def save(self, path: str | Path | None = None) -> None:
        """Save context to file."""
        config = get_config()
        if not config.persist_context:
            return

        save_path = Path(path or config.context_file_path).expanduser()
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info("context_saved", path=str(save_path))

    @classmethod
    def load(cls, path: str | Path | None = None) -> "ConversationContext":
        """Load context from file."""
        config = get_config()
        load_path = Path(path or config.context_file_path).expanduser()

        if not load_path.exists():
            return cls()

        try:
            with open(load_path) as f:
                data = json.load(f)

            context = cls()
            context.aliases = data.get("aliases", {})
            context.current_investigation = data.get("current_investigation")

            for r_data in data.get("recent_resources", []):
                context.recent_resources.append(ResourceReference.from_dict(r_data))

            logger.info("context_loaded", path=str(load_path))
            return context
        except Exception as e:
            logger.warning("failed_to_load_context", error=str(e))
            return cls()

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of current context for AI consumption."""
        return {
            "recent_resources_count": len(self.recent_resources),
            "recent_resources": [
                {"name": r.name or r.arn.split("/")[-1], "service": r.service}
                for r in list(self.recent_resources)[:5]
            ],
            "aliases_count": len(self.aliases),
            "aliases": list(self.aliases.keys())[:10],
            "has_active_investigation": self.current_investigation is not None,
            "investigation_type": (
                self.current_investigation["type"] if self.current_investigation else None
            ),
        }


# Global context instance
_context: ConversationContext | None = None


def get_context() -> ConversationContext:
    """Get the global context instance."""
    global _context
    if _context is None:
        config = get_config()
        if config.persist_context:
            _context = ConversationContext.load()
        else:
            _context = ConversationContext()
    return _context


def reset_context() -> None:
    """Reset the global context (for testing)."""
    global _context
    _context = None
