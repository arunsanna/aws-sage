#!/usr/bin/env python3
"""AWS MCP Pro - Production-grade AWS MCP server."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from typing import Any, Optional

import structlog
from fastmcp import FastMCP
from pydantic import BaseModel, Field

from aws_mcp.config import SafetyMode, get_config, set_config, ServerConfig
from aws_mcp.core.context import get_context
from aws_mcp.core.exceptions import (
    AWSMCPError,
    AuthenticationError,
    SafetyError,
)
from aws_mcp.core.session import get_session_manager
from aws_mcp.core.environment_manager import get_environment_manager
from aws_mcp.core.multi_account import get_multi_account_manager
from aws_mcp.execution import get_execution_engine
from aws_mcp.safety.classifier import OperationClassifier
from aws_mcp.safety.validator import get_safety_enforcer
from aws_mcp.composition import get_docs_proxy, get_knowledge_proxy, KnowledgeCategory
from aws_mcp.differentiators import (
    get_cost_analyzer,
    get_dependency_mapper,
    get_environment_comparer,
    get_incident_investigator,
    IncidentType,
)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()

# Create FastMCP server
mcp = FastMCP(
    name="aws-mcp-pro",
    instructions="""AWS MCP Pro - Production-grade AWS operations with safety controls.

Available safety modes:
- READ_ONLY (default): Only list/describe/get operations allowed
- STANDARD: Read + write operations (confirmation required for mutations)
- UNRESTRICTED: All operations (still blocks security-critical operations)

Start by selecting a profile with 'select_profile', then use 'aws_query' for read operations
or 'aws_execute' for write operations.

Use 'discover_resources' for cross-service queries by tags.
Use 'get_context' to see recent resources and aliases.
""",
)


# === Input Models ===


class SelectProfileInput(BaseModel):
    """Input for selecting an AWS profile."""

    profile: str = Field(..., description="Name of the AWS profile to select")
    region: Optional[str] = Field(None, description="AWS region to use (defaults to us-east-1)")


class SetSafetyModeInput(BaseModel):
    """Input for changing safety mode."""

    mode: str = Field(
        ...,
        description="Safety mode: 'read_only', 'standard', or 'unrestricted'",
    )


class AWSQueryInput(BaseModel):
    """Input for natural language AWS queries."""

    query: str = Field(..., description="Natural language query (e.g., 'list all S3 buckets')")
    service: Optional[str] = Field(None, description="AWS service to query (e.g., 's3', 'ec2')")
    region: Optional[str] = Field(None, description="AWS region to query")


class AWSExecuteInput(BaseModel):
    """Input for executing AWS operations."""

    service: str = Field(..., description="AWS service (e.g., 's3', 'ec2')")
    operation: str = Field(..., description="Operation name (e.g., 'create_bucket')")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Operation parameters")
    confirm: bool = Field(False, description="Set to true to confirm destructive operations")


class SetAliasInput(BaseModel):
    """Input for setting a resource alias."""

    name: str = Field(..., description="Alias name (e.g., 'prod-db')")
    value: str = Field(..., description="Value to alias (e.g., ARN or resource ID)")


class DiscoverResourcesInput(BaseModel):
    """Input for cross-service resource discovery."""

    tags: dict[str, str] = Field(
        ...,
        description="Tags to search for (e.g., {'Environment': 'production'})",
    )
    services: Optional[list[str]] = Field(
        None,
        description="Services to search (default: all supported services)",
    )
    region: Optional[str] = Field(None, description="Region to search")


# === Helper Functions ===


def format_as_table(data: list[dict[str, Any]], headers: list[str] | None = None) -> str:
    """Format data as a markdown table."""
    if not data:
        return "No results found."

    if not headers and isinstance(data[0], dict):
        headers = list(data[0].keys())

    if not headers:
        return json.dumps(data, indent=2, default=str)

    # Calculate column widths (max 40 chars)
    col_widths = [min(40, len(h)) for h in headers]
    for row in data:
        for i, h in enumerate(headers):
            if isinstance(row, dict) and h in row:
                val = str(row[h])[:40]
                col_widths[i] = min(40, max(col_widths[i], len(val)))

    # Build table
    lines = []
    lines.append("| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |")
    lines.append("| " + " | ".join("-" * w for w in col_widths) + " |")

    for row in data:
        if isinstance(row, dict):
            cells = [str(row.get(h, ""))[:40].ljust(col_widths[i]) for i, h in enumerate(headers)]
            lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def clean_response(obj: Any) -> Any:
    """Clean AWS response for JSON serialization."""
    if isinstance(obj, dict):
        # Remove ResponseMetadata
        cleaned = {k: clean_response(v) for k, v in obj.items() if k != "ResponseMetadata"}
        return cleaned
    elif isinstance(obj, list):
        return [clean_response(i) for i in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


def make_response(
    status: str,
    data: Any = None,
    message: str | None = None,
    **kwargs: Any,
) -> str:
    """Create a standardized JSON response."""
    response: dict[str, Any] = {"status": status}
    if message:
        response["message"] = message
    if data is not None:
        response["data"] = clean_response(data)
    response.update(kwargs)
    return json.dumps(response, indent=2, default=str)


# === Core Tools ===


@mcp.tool("list_profiles", description="List all available AWS profiles")
async def list_profiles() -> str:
    """List all AWS profiles configured on the system."""
    try:
        session_mgr = get_session_manager()
        profiles = session_mgr.get_profile_details()

        if not profiles:
            return make_response(
                "warning",
                message="No AWS profiles found. Run 'aws configure' to set up credentials.",
            )

        table = format_as_table(profiles, ["name", "type"])
        return make_response(
            "success",
            data=profiles,
            formatted_table=table,
            count=len(profiles),
        )
    except Exception as e:
        logger.error("list_profiles_failed", error=str(e))
        return make_response("error", message=str(e))


@mcp.tool("select_profile", description="Select an AWS profile to use for operations")
async def select_profile(profile: str, region: str | None = None) -> str:
    """Select an AWS profile and validate credentials."""
    try:
        session_mgr = get_session_manager()
        account_info = session_mgr.select_profile(profile, region)

        return make_response(
            "success",
            data={
                "profile": account_info.profile,
                "region": account_info.region,
                "account_id": account_info.account_id,
                "user_id": account_info.user_id,
            },
            message=f"Successfully selected profile '{profile}'",
        )
    except AuthenticationError as e:
        return make_response("error", message=e.message, **e.details)
    except Exception as e:
        logger.error("select_profile_failed", error=str(e), profile=profile)
        return make_response("error", message=str(e))


@mcp.tool("get_account_info", description="Get current AWS account and session information")
async def get_account_info() -> str:
    """Get information about the current AWS session."""
    try:
        session_mgr = get_session_manager()
        account_info = session_mgr.get_account_info()
        safety = get_safety_enforcer()

        data = {
            "active_profile": session_mgr.active_profile,
            "active_region": session_mgr.active_region,
            "safety_mode": safety.get_mode().value,
        }

        if account_info:
            data.update(
                {
                    "account_id": account_info.account_id,
                    "user_id": account_info.user_id,
                    "arn": account_info.arn,
                }
            )
        else:
            data["message"] = "No profile selected. Use 'select_profile' first."

        return make_response("success", data=data)
    except Exception as e:
        logger.error("get_account_info_failed", error=str(e))
        return make_response("error", message=str(e))


@mcp.tool("set_safety_mode", description="Change the safety mode for operations")
async def set_safety_mode(mode: str) -> str:
    """Change the safety mode.

    Modes:
    - read_only: Only allow read operations (default)
    - standard: Allow read and write operations (requires confirmation)
    - unrestricted: Allow all operations (still blocks dangerous operations)
    """
    try:
        mode_enum = SafetyMode(mode.lower())
        safety = get_safety_enforcer()
        old_mode = safety.get_mode()
        safety.set_mode(mode_enum)

        return make_response(
            "success",
            data={
                "old_mode": old_mode.value,
                "new_mode": mode_enum.value,
            },
            message=f"Safety mode changed from '{old_mode.value}' to '{mode_enum.value}'",
        )
    except ValueError:
        return make_response(
            "error",
            message=f"Invalid mode '{mode}'. Valid modes: read_only, standard, unrestricted",
        )


# === Query Tools ===


@mcp.tool("aws_query", description="Execute read-only AWS queries (natural language supported)")
async def aws_query(
    query: str,
    service: str | None = None,
    region: str | None = None,
) -> str:
    """Execute a read-only AWS query.

    Supports natural language queries like:
    - "list all S3 buckets"
    - "show EC2 instances"
    - "get Lambda functions"
    """
    try:
        # Use the execution engine for natural language queries
        engine = get_execution_engine()
        result = await engine.execute_natural_language(query, region=region)
        return result.to_json()

    except AWSMCPError as e:
        return make_response("error", message=e.message, **e.details)
    except Exception as e:
        logger.error("aws_query_failed", error=str(e), query=query)
        return make_response("error", message=str(e), query=query)


@mcp.tool("aws_execute", description="Execute AWS operations (requires appropriate safety mode)")
async def aws_execute(
    service: str,
    operation: str,
    parameters: dict[str, Any] | None = None,
    confirm: bool = False,
) -> str:
    """Execute an AWS operation with safety controls.

    For write/destructive operations, you must:
    1. Be in 'standard' or 'unrestricted' mode
    2. Set confirm=true for destructive operations
    """
    try:
        # Use the execution engine for explicit operations
        engine = get_execution_engine()
        result = await engine.execute_explicit(
            service=service,
            operation=operation,
            parameters=parameters,
            confirm=confirm,
        )
        return result.to_json()

    except SafetyError as e:
        return make_response("blocked", message=e.message, **e.details)
    except AWSMCPError as e:
        return make_response("error", message=e.message, **e.details)
    except Exception as e:
        logger.error("aws_execute_failed", error=str(e), service=service, operation=operation)
        return make_response("error", message=str(e))


@mcp.tool("validate_operation", description="Check if an operation is valid and allowed without executing")
async def validate_operation(
    service: str,
    operation: str,
    parameters: dict[str, Any] | None = None,
) -> str:
    """Validate an operation without executing it."""
    parameters = parameters or {}

    try:
        safety = get_safety_enforcer()
        decision = safety.evaluate(service, operation, parameters)

        category = OperationClassifier.classify(service, operation)
        supports_dry_run = OperationClassifier.supports_dry_run(service, operation)

        return make_response(
            "success" if decision.allowed else "blocked",
            data={
                "allowed": decision.allowed,
                "category": category.value,
                "requires_confirmation": decision.requires_confirmation,
                "requires_double_confirmation": decision.requires_double_confirmation,
                "supports_dry_run": supports_dry_run,
                "warning": decision.warning,
            },
            reason=decision.reason if not decision.allowed else None,
            suggested_mode=decision.suggested_mode.value if decision.suggested_mode else None,
        )
    except Exception as e:
        return make_response("error", message=str(e))


# === Context Tools ===


@mcp.tool("get_context", description="Get current conversation context (recent resources, aliases)")
async def get_context_tool() -> str:
    """Get the current conversation context."""
    context = get_context()
    return make_response("success", data=context.get_summary())


@mcp.tool("set_alias", description="Create a shortcut alias for a resource")
async def set_alias(name: str, value: str) -> str:
    """Set an alias for quick reference.

    Example: set_alias("prod-db", "arn:aws:rds:us-east-1:123456789:db/production")
    """
    context = get_context()
    context.set_alias(name, value)
    return make_response(
        "success",
        message=f"Alias '{name}' set to '{value}'",
        data={"name": name, "value": value},
    )


@mcp.tool("list_aliases", description="List all defined aliases")
async def list_aliases() -> str:
    """List all defined aliases."""
    context = get_context()
    aliases = context.aliases

    if not aliases:
        return make_response("success", data=[], message="No aliases defined.")

    alias_list = [{"name": k, "value": v} for k, v in aliases.items()]
    table = format_as_table(alias_list, ["name", "value"])
    return make_response(
        "success",
        data=alias_list,
        formatted_table=table,
        count=len(aliases),
    )


# === Discovery Tools ===


@mcp.tool("discover_resources", description="Find resources across services by tags")
async def discover_resources(
    tags: dict[str, str],
    services: list[str] | None = None,
    region: str | None = None,
) -> str:
    """Discover resources across multiple AWS services by tags.

    This is a unique feature that official AWS MCP servers don't provide.
    """
    try:
        session_mgr = get_session_manager()

        if not session_mgr.active_profile:
            return make_response(
                "error",
                message="No profile selected. Please select a profile first.",
            )

        # Use Resource Groups Tagging API
        client = session_mgr.get_client("resourcegroupstaggingapi", region)

        tag_filters = [{"Key": k, "Values": [v]} for k, v in tags.items()]

        # Build resource type filter if services specified
        resource_type_filters = []
        if services:
            for svc in services:
                resource_type_filters.append(f"{svc}:")

        paginator = client.get_paginator("get_resources")
        resources = []

        pagination_config = {"MaxItems": 100}
        params = {"TagFilters": tag_filters}
        if resource_type_filters:
            params["ResourceTypeFilters"] = resource_type_filters

        for page in paginator.paginate(**params, PaginationConfig=pagination_config):
            for mapping in page.get("ResourceTagMappingList", []):
                arn = mapping["ResourceARN"]
                # Parse ARN to extract service and resource type
                parts = arn.split(":")
                service_name = parts[2] if len(parts) > 2 else "unknown"
                resource_type = parts[5].split("/")[0] if len(parts) > 5 else "resource"

                resources.append(
                    {
                        "arn": arn,
                        "service": service_name,
                        "type": resource_type,
                        "tags": {t["Key"]: t["Value"] for t in mapping.get("Tags", [])},
                    }
                )

        if not resources:
            return make_response(
                "success",
                data=[],
                message=f"No resources found with tags: {tags}",
            )

        # Format as table
        table_data = [
            {"service": r["service"], "type": r["type"], "arn": r["arn"][:60] + "..."}
            for r in resources
        ]
        table = format_as_table(table_data, ["service", "type", "arn"])

        return make_response(
            "success",
            data=resources,
            formatted_table=table,
            count=len(resources),
            tags_searched=tags,
        )

    except Exception as e:
        logger.error("discover_resources_failed", error=str(e), tags=tags)
        return make_response("error", message=str(e))


# === Documentation & Knowledge Tools ===


@mcp.tool("search_docs", description="Search AWS documentation for a service or topic")
async def search_docs(
    query: str,
    service: str | None = None,
    max_results: int = 5,
) -> str:
    """Search AWS documentation.

    This tool integrates with AWS Documentation MCP server when available,
    otherwise provides helpful documentation links.

    Examples:
    - search_docs("S3 encryption")
    - search_docs("creating a bucket", service="s3")
    """
    try:
        docs_proxy = get_docs_proxy()
        results = await docs_proxy.search(query, service, max_results)

        if not results:
            return make_response(
                "success",
                data=[],
                message=f"No documentation found for '{query}'",
            )

        data = [r.to_dict() for r in results]
        return make_response(
            "success",
            data=data,
            count=len(results),
        )
    except Exception as e:
        logger.error("search_docs_failed", error=str(e), query=query)
        return make_response("error", message=str(e))


@mcp.tool("get_aws_knowledge", description="Get AWS best practices and operational knowledge")
async def get_aws_knowledge(
    question: str,
    service: str | None = None,
    category: str | None = None,
) -> str:
    """Get AWS knowledge for best practices, security, limits, and architecture.

    Categories: best_practices, security, architecture, pricing, limits, troubleshooting

    Examples:
    - get_aws_knowledge("best practices for S3 security")
    - get_aws_knowledge("Lambda limits", service="lambda", category="limits")
    """
    try:
        knowledge_proxy = get_knowledge_proxy()

        # Parse category if provided
        category_enum = None
        if category:
            try:
                category_enum = KnowledgeCategory(category.lower())
            except ValueError:
                pass

        results = await knowledge_proxy.query(question, service, category_enum)

        if not results:
            return make_response(
                "success",
                data=[],
                message=f"No knowledge found for '{question}'",
                suggestion="Try asking about specific services like S3, EC2, Lambda, or IAM",
            )

        data = [r.to_dict() for r in results]
        return make_response(
            "success",
            data=data,
            count=len(results),
        )
    except Exception as e:
        logger.error("get_aws_knowledge_failed", error=str(e), question=question)
        return make_response("error", message=str(e))


@mcp.tool("get_best_practices", description="Get best practices for an AWS service")
async def get_best_practices(service: str) -> str:
    """Get best practices for a specific AWS service.

    Examples:
    - get_best_practices("s3")
    - get_best_practices("lambda")
    """
    try:
        knowledge_proxy = get_knowledge_proxy()
        results = await knowledge_proxy.get_best_practices(service)

        if not results:
            return make_response(
                "success",
                data=[],
                message=f"No best practices found for '{service}'",
            )

        data = [r.to_dict() for r in results]
        return make_response(
            "success",
            data=data,
            service=service,
            count=len(results),
        )
    except Exception as e:
        logger.error("get_best_practices_failed", error=str(e), service=service)
        return make_response("error", message=str(e))


@mcp.tool("get_service_limits", description="Get service quotas and limits for an AWS service")
async def get_service_limits(service: str) -> str:
    """Get service limits and quotas for a specific AWS service.

    Examples:
    - get_service_limits("lambda")
    - get_service_limits("s3")
    """
    try:
        knowledge_proxy = get_knowledge_proxy()
        results = await knowledge_proxy.get_service_limits(service)

        if not results:
            return make_response(
                "success",
                data=[],
                message=f"No limits information found for '{service}'",
            )

        data = [r.to_dict() for r in results]
        return make_response(
            "success",
            data=data,
            service=service,
            count=len(results),
        )
    except Exception as e:
        logger.error("get_service_limits_failed", error=str(e), service=service)
        return make_response("error", message=str(e))


# === Differentiator Tools ===


@mcp.tool("map_dependencies", description="Map resource dependencies and relationships")
async def map_dependencies(
    resource_arn: str,
    max_depth: int = 2,
    region: str | None = None,
) -> str:
    """Map dependencies for an AWS resource.

    This is a unique feature that shows what other resources depend on or are
    used by the specified resource. Useful for understanding blast radius
    before making changes.

    Examples:
    - map_dependencies("arn:aws:lambda:us-east-1:123456789:function:my-function")
    - map_dependencies("arn:aws:ec2:us-east-1:123456789:instance/i-1234567890abcdef0", max_depth=3)
    """
    try:
        mapper = get_dependency_mapper()
        graph = await mapper.map_dependencies(resource_arn, max_depth, region)

        return make_response(
            "success",
            data=graph.to_dict(),
            total_dependencies=len(graph.dependencies),
            affected_resources=len(graph.affected_resources),
        )
    except Exception as e:
        logger.error("map_dependencies_failed", error=str(e), resource_arn=resource_arn)
        return make_response("error", message=str(e))


@mcp.tool("impact_analysis", description="Analyze the impact of modifying or deleting a resource")
async def impact_analysis(
    resource_arn: str,
    region: str | None = None,
) -> str:
    """Analyze what would be affected if a resource is modified or deleted.

    This helps answer "what breaks if I delete this?" by tracing all
    dependencies and providing a risk assessment.

    Examples:
    - impact_analysis("arn:aws:rds:us-east-1:123456789:db:production-db")
    - impact_analysis("arn:aws:iam::123456789:role/critical-role")
    """
    try:
        mapper = get_dependency_mapper()
        analysis = await mapper.impact_analysis(resource_arn, region)

        return make_response(
            "success",
            data=analysis,
            risk_level=analysis.get("risk_level"),
            total_affected=analysis.get("total_affected_resources"),
        )
    except Exception as e:
        logger.error("impact_analysis_failed", error=str(e), resource_arn=resource_arn)
        return make_response("error", message=str(e))


@mcp.tool("investigate_incident", description="Run automated incident investigation workflow")
async def investigate_incident(
    incident_type: str,
    resource: str,
    region: str | None = None,
    time_range_hours: int = 1,
) -> str:
    """Run an automated incident investigation workflow.

    This is a unique feature that automatically gathers relevant data from
    multiple AWS services to help diagnose issues.

    Incident types:
    - lambda_failure: Investigate Lambda function errors
    - high_latency: Investigate latency issues
    - security_alert: Investigate security-related alerts
    - resource_exhaustion: Investigate resource limit issues

    Examples:
    - investigate_incident("lambda_failure", "my-function-name")
    - investigate_incident("high_latency", "my-api", time_range_hours=4)
    - investigate_incident("security_alert", "suspicious-activity")
    """
    try:
        # Parse incident type
        try:
            incident_type_enum = IncidentType(incident_type.lower())
        except ValueError:
            valid_types = [t.value for t in IncidentType]
            return make_response(
                "error",
                message=f"Invalid incident type '{incident_type}'. Valid types: {', '.join(valid_types)}",
            )

        investigator = get_incident_investigator()
        result = await investigator.investigate(
            incident_type_enum,
            resource,
            region,
            time_range_hours,
        )

        return make_response(
            "success",
            data=result.to_dict(),
            severity=result.severity,
            findings_count=len(result.findings),
            recommendations_count=len(result.recommendations),
        )
    except Exception as e:
        logger.error(
            "investigate_incident_failed",
            error=str(e),
            incident_type=incident_type,
            resource=resource,
        )
        return make_response("error", message=str(e))


# === Cost Analysis Tools ===


@mcp.tool("find_idle_resources", description="Find potentially idle or underutilized AWS resources")
async def find_idle_resources(
    services: list[str] | None = None,
    region: str | None = None,
    lookback_days: int = 14,
) -> str:
    """Find idle resources that may be candidates for termination.

    Checks for:
    - EC2 instances with low CPU utilization (<5% avg)
    - Stopped EC2 instances
    - RDS instances with zero connections
    - Unattached EBS volumes
    - Unused Elastic IPs

    Examples:
    - find_idle_resources()
    - find_idle_resources(services=["ec2", "ebs"])
    - find_idle_resources(lookback_days=30)
    """
    try:
        analyzer = get_cost_analyzer()
        result = await analyzer.find_idle_resources(services, region, lookback_days)

        return make_response(
            "success",
            data=result.to_dict(),
            idle_count=len(result.idle_resources),
            potential_savings=f"${result.total_potential_savings:.2f}/month",
        )
    except Exception as e:
        logger.error("find_idle_resources_failed", error=str(e))
        return make_response("error", message=str(e))


@mcp.tool("get_rightsizing_recommendations", description="Get recommendations for right-sizing EC2 and RDS instances")
async def get_rightsizing_recommendations(
    services: list[str] | None = None,
    region: str | None = None,
    lookback_days: int = 14,
) -> str:
    """Get right-sizing recommendations based on utilization metrics.

    Analyzes CloudWatch metrics to recommend:
    - Downsizing over-provisioned instances
    - Upsizing under-provisioned instances
    - Modernizing to newer instance families

    Examples:
    - get_rightsizing_recommendations()
    - get_rightsizing_recommendations(services=["ec2"], lookback_days=30)
    """
    try:
        analyzer = get_cost_analyzer()
        result = await analyzer.get_rightsizing_recommendations(services, region, lookback_days)

        return make_response(
            "success",
            data=result.to_dict(),
            recommendation_count=len(result.recommendations),
            potential_savings=f"${result.total_potential_savings:.2f}/month",
        )
    except Exception as e:
        logger.error("get_rightsizing_recommendations_failed", error=str(e))
        return make_response("error", message=str(e))


@mcp.tool("get_cost_breakdown", description="Get cost breakdown by service or tag")
async def get_cost_breakdown(
    group_by: str = "SERVICE",
    tag_key: str | None = None,
    days: int = 30,
) -> str:
    """Get AWS cost breakdown grouped by service or tag.

    Requires Cost Explorer to be enabled in the AWS account.

    Args:
        group_by: How to group costs - SERVICE, TAG, or USAGE_TYPE
        tag_key: Tag key to group by (required if group_by=TAG)
        days: Number of days to analyze (default: 30)

    Examples:
    - get_cost_breakdown()
    - get_cost_breakdown(group_by="TAG", tag_key="Environment")
    - get_cost_breakdown(days=90)
    """
    try:
        analyzer = get_cost_analyzer()
        result = await analyzer.get_cost_breakdown(
            granularity="MONTHLY",
            group_by=group_by,
            tag_key=tag_key,
            days=days,
        )

        if result.breakdown:
            return make_response(
                "success",
                data=result.to_dict(),
                total_cost=f"${result.breakdown.total_cost:.2f}",
                period=f"{result.breakdown.period_start.date()} to {result.breakdown.period_end.date()}",
            )
        else:
            return make_response(
                "error",
                message="Failed to retrieve cost breakdown",
                errors=result.errors,
            )
    except Exception as e:
        logger.error("get_cost_breakdown_failed", error=str(e))
        return make_response("error", message=str(e))


@mcp.tool("project_costs", description="Estimate costs for proposed AWS resources")
async def project_costs(
    resources: list[dict[str, Any]],
    region: str | None = None,
) -> str:
    """Estimate monthly costs for proposed resources before deployment.

    Supports EC2, RDS, EBS, and Lambda pricing estimates.

    Args:
        resources: List of resource configurations
        region: AWS region for pricing

    Resource config examples:
    - {"type": "ec2", "instance_type": "t3.large", "count": 2}
    - {"type": "rds", "instance_class": "db.t3.medium", "engine": "mysql"}
    - {"type": "ebs", "size_gb": 100, "volume_type": "gp3"}
    - {"type": "lambda", "memory_mb": 256, "monthly_invocations": 1000000, "avg_duration_ms": 200}

    Examples:
    - project_costs(resources=[{"type": "ec2", "instance_type": "m5.large"}])
    - project_costs(resources=[
        {"type": "ec2", "instance_type": "t3.medium", "count": 3},
        {"type": "rds", "instance_class": "db.m5.large"},
        {"type": "ebs", "size_gb": 500, "volume_type": "gp3"}
      ])
    """
    try:
        analyzer = get_cost_analyzer()
        result = await analyzer.project_costs(resources, region)

        if result.projection:
            return make_response(
                "success",
                data=result.to_dict(),
                total_monthly=f"${result.projection.total_monthly:.2f}",
                total_yearly=f"${result.projection.total_yearly:.2f}",
            )
        else:
            return make_response(
                "error",
                message="Failed to project costs",
                errors=result.errors,
            )
    except Exception as e:
        logger.error("project_costs_failed", error=str(e))
        return make_response("error", message=str(e))


# === Environment Management Tools ===


@mcp.tool(
    "list_environments",
    description="List all configured AWS environments (production, localstack)",
)
async def list_environments() -> str:
    """List all available AWS environments.

    Returns configured environments including production AWS and LocalStack.
    Shows which environment is currently active.

    Examples:
    - list_environments()
    """
    try:
        env_manager = get_environment_manager()
        environments = env_manager.list_environments()

        return make_response(
            "success",
            environments=[env.to_dict() for env in environments],
            active=env_manager.get_active_environment().name,
        )
    except Exception as e:
        logger.error("list_environments_failed", error=str(e))
        return make_response("error", message=str(e))


@mcp.tool(
    "switch_environment",
    description="Switch between AWS environments (production or localstack)",
)
async def switch_environment(
    environment: str,
    validate: bool = True,
) -> str:
    """Switch to a different AWS environment.

    Args:
        environment: Environment name ('production' or 'localstack')
        validate: Whether to validate connectivity before switching

    Examples:
    - switch_environment(environment="localstack")
    - switch_environment(environment="production")
    - switch_environment(environment="localstack", validate=False)

    IMPORTANT: Switching to production will affect real AWS resources!
    """
    try:
        env_manager = get_environment_manager()
        result = env_manager.switch_environment(environment, validate=validate)

        if result.success:
            return make_response(
                "success",
                message=result.message,
                environment=result.environment.to_dict() if result.environment else None,
                warnings=result.warnings,
            )
        else:
            return make_response(
                "error",
                message=result.message,
                warnings=result.warnings,
            )
    except Exception as e:
        logger.error("switch_environment_failed", error=str(e))
        return make_response("error", message=str(e))


@mcp.tool(
    "get_environment_info",
    description="Get detailed information about the current AWS environment",
)
async def get_environment_info() -> str:
    """Get information about the currently active environment.

    Returns details including environment type, region, connectivity status,
    and available services (for LocalStack).

    Examples:
    - get_environment_info()
    """
    try:
        env_manager = get_environment_manager()
        info = env_manager.get_environment_info()

        return make_response(
            "success",
            **info,
        )
    except Exception as e:
        logger.error("get_environment_info_failed", error=str(e))
        return make_response("error", message=str(e))


@mcp.tool(
    "check_localstack",
    description="Check LocalStack connectivity and available services",
)
async def check_localstack() -> str:
    """Check if LocalStack is running and accessible.

    Returns LocalStack status, endpoint URL, and lists of community
    and pro services.

    Examples:
    - check_localstack()
    """
    try:
        env_manager = get_environment_manager()
        status = env_manager.check_localstack()

        return make_response(
            "success" if status["available"] else "info",
            **status,
        )
    except Exception as e:
        logger.error("check_localstack_failed", error=str(e))
        return make_response("error", message=str(e))


@mcp.tool(
    "compare_environments",
    description="Compare resources between two AWS environments (e.g., localstack vs production)",
)
async def compare_environments(
    service: str,
    source: str = "localstack",
    target: str = "production",
) -> str:
    """Compare resources between two environments.

    Useful for validating that LocalStack has the same resources as production,
    or for identifying drift between environments.

    Args:
        service: AWS service to compare (s3, dynamodb, lambda, sqs, sns)
        source: Source environment name (default: localstack)
        target: Target environment name (default: production)

    Examples:
    - compare_environments(service="s3")
    - compare_environments(service="dynamodb", source="localstack", target="production")
    - compare_environments(service="lambda")
    """
    try:
        env_manager = get_environment_manager()
        comparer = get_environment_comparer()

        source_env = env_manager.get_environment(source)
        target_env = env_manager.get_environment(target)

        if not source_env:
            return make_response(
                "error",
                message=f"Source environment '{source}' not found",
            )
        if not target_env:
            return make_response(
                "error",
                message=f"Target environment '{target}' not found",
            )

        result = await comparer.compare_environments(service, source_env, target_env)

        if result.errors:
            return make_response(
                "warning",
                data=result.to_dict(),
                message="Comparison completed with errors",
            )

        return make_response(
            "success",
            data=result.to_dict(),
            summary={
                "only_in_source": len(result.only_in_source),
                "only_in_target": len(result.only_in_target),
                "different": len(result.different),
                "identical": len(result.identical),
            },
        )
    except Exception as e:
        logger.error("compare_environments_failed", error=str(e))
        return make_response("error", message=str(e))


# === Multi-Account Management Tools ===


@mcp.tool(
    "assume_role",
    description="Assume an IAM role in another AWS account for cross-account access",
)
async def assume_role(
    role_arn: str,
    session_name: str | None = None,
    duration_seconds: int = 3600,
    external_id: str | None = None,
    alias: str | None = None,
) -> str:
    """Assume an IAM role in another AWS account.

    Enables cross-account access by assuming a role. The role must have a trust
    policy allowing the current account/role to assume it.

    Args:
        role_arn: ARN of the role to assume (e.g., arn:aws:iam::123456789012:role/MyRole)
        session_name: Optional session name (auto-generated if not provided)
        duration_seconds: Credential validity duration (default: 3600 = 1 hour)
        external_id: External ID for cross-account access (if required by trust policy)
        alias: Optional friendly name for this account

    Examples:
    - assume_role(role_arn="arn:aws:iam::123456789012:role/CrossAccountRole")
    - assume_role(role_arn="arn:aws:iam::123456789012:role/Role", alias="production")
    - assume_role(
        role_arn="arn:aws:iam::123456789012:role/Role",
        external_id="my-external-id",
        duration_seconds=7200
      )
    """
    try:
        manager = get_multi_account_manager()
        result = manager.assume_role(
            role_arn=role_arn,
            session_name=session_name,
            duration_seconds=duration_seconds,
            external_id=external_id,
            alias=alias,
        )

        if result.success:
            return make_response(
                "success",
                message=result.message,
                account=result.account.to_dict() if result.account else None,
                warnings=result.warnings,
            )
        else:
            return make_response(
                "error",
                message=result.message,
                warnings=result.warnings,
            )
    except Exception as e:
        logger.error("assume_role_failed", error=str(e))
        return make_response("error", message=str(e))


@mcp.tool(
    "list_accounts",
    description="List all configured AWS accounts (including assumed roles)",
)
async def list_accounts() -> str:
    """List all configured AWS accounts.

    Shows all accounts that have been added via assume_role or detected
    from the current credentials. Indicates which account is currently active.

    Examples:
    - list_accounts()
    """
    try:
        manager = get_multi_account_manager()
        accounts = manager.list_accounts()

        active = manager.get_active_account()
        active_id = active.account_id if active else None

        return make_response(
            "success",
            accounts=[acc.to_dict() for acc in accounts],
            active_account=active_id,
            total_accounts=len(accounts),
        )
    except Exception as e:
        logger.error("list_accounts_failed", error=str(e))
        return make_response("error", message=str(e))


@mcp.tool(
    "switch_account",
    description="Switch the active AWS account context",
)
async def switch_account(
    account: str,
) -> str:
    """Switch to a different AWS account context.

    Changes the active account for subsequent operations. Use the account ID
    or the alias assigned during assume_role.

    Args:
        account: Account ID or alias to switch to

    Examples:
    - switch_account(account="123456789012")
    - switch_account(account="production")
    - switch_account(account="default")

    IMPORTANT: Operations after switching will affect resources in the new account!
    """
    try:
        manager = get_multi_account_manager()
        result = manager.switch_account(account)

        if result.success:
            return make_response(
                "success",
                message=result.message,
                account=result.account.to_dict() if result.account else None,
                warnings=result.warnings,
            )
        else:
            return make_response(
                "error",
                message=result.message,
            )
    except Exception as e:
        logger.error("switch_account_failed", error=str(e))
        return make_response("error", message=str(e))


# === Helper Functions ===


def _parse_query(query: str, service_hint: str | None = None) -> dict[str, Any]:
    """Parse a natural language query into service/operation/parameters."""
    query_lower = query.lower()

    # Service detection
    SERVICE_KEYWORDS = {
        "s3": ["s3", "bucket", "object", "storage"],
        "ec2": ["ec2", "instance", "ami", "ebs", "volume"],
        "lambda": ["lambda", "function", "serverless"],
        "iam": ["iam", "role", "user", "policy", "permission"],
        "rds": ["rds", "database", "mysql", "postgres", "aurora"],
        "dynamodb": ["dynamodb", "dynamo", "table", "nosql"],
        "ecs": ["ecs", "container", "cluster", "task"],
        "eks": ["eks", "kubernetes", "k8s"],
        "cloudformation": ["cloudformation", "cfn", "stack"],
        "cloudwatch": ["cloudwatch", "logs", "metrics", "alarm"],
        "sns": ["sns", "notification", "topic"],
        "sqs": ["sqs", "queue", "message"],
        "secretsmanager": ["secret", "secrets"],
        "ssm": ["ssm", "parameter"],
        "route53": ["route53", "dns", "domain"],
    }

    detected_service = service_hint
    if not detected_service:
        for svc, keywords in SERVICE_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                detected_service = svc
                break

    # Operation detection
    OPERATION_MAPPING = {
        "s3": {
            "list": "list_buckets",
            "show": "list_buckets",
            "get": "list_buckets",
            "describe": "list_buckets",
        },
        "ec2": {
            "list": "describe_instances",
            "show": "describe_instances",
            "get": "describe_instances",
            "describe": "describe_instances",
        },
        "lambda": {
            "list": "list_functions",
            "show": "list_functions",
            "get": "list_functions",
        },
        "iam": {
            "list": "list_roles",
            "show": "list_roles",
            "role": "list_roles",
            "user": "list_users",
            "policy": "list_policies",
        },
        "rds": {
            "list": "describe_db_instances",
            "show": "describe_db_instances",
            "describe": "describe_db_instances",
        },
        "dynamodb": {
            "list": "list_tables",
            "show": "list_tables",
            "table": "list_tables",
        },
        "ecs": {
            "list": "list_clusters",
            "cluster": "list_clusters",
            "service": "list_services",
        },
        "cloudformation": {
            "list": "list_stacks",
            "stack": "list_stacks",
            "describe": "describe_stacks",
        },
        "secretsmanager": {
            "list": "list_secrets",
            "secret": "list_secrets",
        },
    }

    detected_operation = None
    resource_type = None

    if detected_service and detected_service in OPERATION_MAPPING:
        mapping = OPERATION_MAPPING[detected_service]
        for keyword, operation in mapping.items():
            if keyword in query_lower:
                detected_operation = operation
                resource_type = keyword
                break

        # Default to first operation if service detected but no specific operation
        if not detected_operation:
            detected_operation = list(mapping.values())[0]

    return {
        "service": detected_service,
        "operation": detected_operation,
        "parameters": {},
        "resource_type": resource_type,
    }


async def _execute_with_pagination(
    client: Any,
    operation: str,
    parameters: dict[str, Any],
) -> list[Any] | Any:
    """Execute an operation with automatic pagination."""
    config = get_config()

    # Check if operation supports pagination
    try:
        paginator = client.get_paginator(operation)
        results = []
        item_count = 0

        for page_num, page in enumerate(paginator.paginate(**parameters)):
            if page_num >= config.pagination_max_pages:
                break

            # Find the main data list in the response
            for key, value in page.items():
                if key != "ResponseMetadata" and isinstance(value, list):
                    results.extend(value)
                    item_count += len(value)

            if item_count >= config.pagination_max_items:
                break

        return results

    except Exception:
        # Operation doesn't support pagination, execute directly
        method = getattr(client, operation)
        response = method(**parameters)

        # Extract the main data from response
        for key, value in response.items():
            if key != "ResponseMetadata" and isinstance(value, list):
                return value

        return response


def main() -> None:
    """Main entry point for the server."""
    import argparse

    parser = argparse.ArgumentParser(description="AWS MCP Pro Server")
    parser.add_argument(
        "--safety-mode",
        choices=["read_only", "standard", "unrestricted"],
        default="read_only",
        help="Initial safety mode",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="Default AWS region",
    )

    args = parser.parse_args()

    # Configure server
    config = ServerConfig.from_env()
    config.safety.mode = SafetyMode(args.safety_mode)
    config.default_region = args.region
    set_config(config)

    logger.info(
        "starting_server",
        safety_mode=args.safety_mode,
        region=args.region,
    )

    # Run the server
    mcp.run()


if __name__ == "__main__":
    main()
