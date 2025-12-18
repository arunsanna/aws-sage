"""Unique differentiators for AWS MCP Pro."""

from aws_sage.differentiators.compare import (
    ComparisonResult,
    EnvironmentComparer,
    ResourceComparison,
    ResourceDifference,
    get_environment_comparer,
    reset_environment_comparer,
)
from aws_sage.differentiators.cost import (
    CostAnalysisResult,
    CostAnalyzer,
    CostBreakdown,
    CostBreakdownItem,
    CostProjection,
    CostTrend,
    IdleReason,
    IdleResource,
    ResourceProjection,
    RightSizeAction,
    RightSizeRecommendation,
    get_cost_analyzer,
    reset_cost_analyzer,
)
from aws_sage.differentiators.dependencies import (
    DependencyGraph,
    DependencyMapper,
    DependencyType,
    ResourceDependency,
    get_dependency_mapper,
)
from aws_sage.differentiators.discovery import (
    DiscoveredResource,
    DiscoveryResult,
    ResourceDiscovery,
    get_resource_discovery,
)
from aws_sage.differentiators.workflows import (
    IncidentInvestigator,
    IncidentType,
    InvestigationResult,
    InvestigationStep,
    get_incident_investigator,
)

__all__ = [
    # Environment comparison
    "ComparisonResult",
    "EnvironmentComparer",
    "ResourceComparison",
    "ResourceDifference",
    "get_environment_comparer",
    "reset_environment_comparer",
    # Cost analysis
    "CostAnalysisResult",
    "CostAnalyzer",
    "CostBreakdown",
    "CostBreakdownItem",
    "CostProjection",
    "CostTrend",
    "IdleReason",
    "IdleResource",
    "ResourceProjection",
    "RightSizeAction",
    "RightSizeRecommendation",
    "get_cost_analyzer",
    "reset_cost_analyzer",
    # Dependencies
    "DependencyGraph",
    "DependencyMapper",
    "DependencyType",
    "ResourceDependency",
    "get_dependency_mapper",
    # Discovery
    "DiscoveredResource",
    "DiscoveryResult",
    "ResourceDiscovery",
    "get_resource_discovery",
    # Workflows
    "IncidentInvestigator",
    "IncidentType",
    "InvestigationResult",
    "InvestigationStep",
    "get_incident_investigator",
]
