"""Service plugins for AWS MCP Pro."""

from aws_mcp.services.base import (
    BaseService,
    OperationResult,
    OperationSpec,
    ServiceRegistry,
    register_service,
)

# Import plugins to trigger registration
from aws_mcp.services.plugins import compute, security, storage

__all__ = [
    "BaseService",
    "OperationResult",
    "OperationSpec",
    "ServiceRegistry",
    "register_service",
]
