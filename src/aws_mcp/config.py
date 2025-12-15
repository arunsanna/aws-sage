"""Configuration management for AWS MCP Pro."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Set


class SafetyMode(Enum):
    """Safety modes controlling operation permissions."""

    READ_ONLY = "read_only"  # Default - only list/describe/get operations
    STANDARD = "standard"  # Read + write (confirmation required for mutations)
    UNRESTRICTED = "unrestricted"  # All operations (still blocks denylist)


class OperationCategory(Enum):
    """Categories of AWS operations by their impact."""

    READ = "read"  # list, describe, get, head, scan
    WRITE = "write"  # create, put, update, modify, tag, start, stop
    DESTRUCTIVE = "destructive"  # delete, terminate, destroy, remove, revoke
    BLOCKED = "blocked"  # operations that are never allowed


@dataclass
class SafetyConfig:
    """Configuration for safety controls."""

    mode: SafetyMode = SafetyMode.READ_ONLY
    require_confirmation_for: Set[OperationCategory] = field(
        default_factory=lambda: {OperationCategory.WRITE, OperationCategory.DESTRUCTIVE}
    )
    dry_run_when_available: bool = True
    max_resources_per_operation: int = 50
    audit_logging: bool = True


@dataclass
class ServerConfig:
    """Main server configuration."""

    # AWS defaults
    default_region: str = "us-east-1"

    # Safety
    safety: SafetyConfig = field(default_factory=SafetyConfig)

    # Performance
    pagination_max_pages: int = 100
    pagination_max_items: int = 1000
    cache_ttl_seconds: int = 300

    # Context
    max_recent_resources: int = 10
    persist_context: bool = False
    context_file_path: str = "~/.aws-mcp/context.json"

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Load configuration from environment variables."""
        safety_mode_str = os.environ.get("AWS_MCP_SAFETY_MODE", "read_only")
        try:
            safety_mode = SafetyMode(safety_mode_str)
        except ValueError:
            safety_mode = SafetyMode.READ_ONLY

        return cls(
            default_region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            safety=SafetyConfig(
                mode=safety_mode,
                dry_run_when_available=os.environ.get("AWS_MCP_DRY_RUN", "true").lower() == "true",
                audit_logging=os.environ.get("AWS_MCP_AUDIT_LOG", "true").lower() == "true",
            ),
        )


# Global configuration instance
_config: ServerConfig | None = None


def get_config() -> ServerConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = ServerConfig.from_env()
    return _config


def set_config(config: ServerConfig) -> None:
    """Set the global configuration instance."""
    global _config
    _config = config


def reset_config() -> None:
    """Reset the global configuration (for testing)."""
    global _config
    _config = None
