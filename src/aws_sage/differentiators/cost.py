"""Cost analysis and optimization for AWS MCP Pro."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import structlog

from aws_sage.core.session import get_session_manager

logger = structlog.get_logger()


# === Enums ===


class IdleReason(Enum):
    """Reasons a resource may be considered idle."""

    LOW_CPU = "low_cpu_utilization"
    NO_CONNECTIONS = "no_connections"
    NO_REQUESTS = "no_requests"
    UNATTACHED = "unattached"
    STOPPED = "stopped_long_term"
    UNUSED_IP = "unused_elastic_ip"
    LOW_IOPS = "low_iops"


class RightSizeAction(Enum):
    """Recommended actions for right-sizing."""

    DOWNSIZE = "downsize"
    UPSIZE = "upsize"
    TERMINATE = "terminate"
    MODERNIZE = "modernize"
    NO_CHANGE = "no_change"


class CostTrend(Enum):
    """Cost trend direction."""

    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"


# === Data Classes ===


@dataclass
class IdleResource:
    """A resource identified as potentially idle or underutilized."""

    arn: str
    service: str
    resource_type: str
    name: str | None
    region: str
    reason: IdleReason
    idle_since: datetime | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    estimated_monthly_cost: float = 0.0
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "arn": self.arn,
            "service": self.service,
            "resource_type": self.resource_type,
            "name": self.name,
            "region": self.region,
            "reason": self.reason.value,
            "idle_since": self.idle_since.isoformat() if self.idle_since else None,
            "metrics": self.metrics,
            "estimated_monthly_cost": round(self.estimated_monthly_cost, 2),
            "confidence": round(self.confidence, 2),
        }


@dataclass
class RightSizeRecommendation:
    """A recommendation for right-sizing a resource."""

    arn: str
    service: str
    resource_type: str
    name: str | None
    region: str
    current_config: dict[str, Any]
    recommended_config: dict[str, Any]
    action: RightSizeAction
    current_monthly_cost: float
    projected_monthly_cost: float
    savings_percentage: float
    utilization_metrics: dict[str, float]
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "arn": self.arn,
            "service": self.service,
            "resource_type": self.resource_type,
            "name": self.name,
            "region": self.region,
            "current_config": self.current_config,
            "recommended_config": self.recommended_config,
            "action": self.action.value,
            "current_monthly_cost": round(self.current_monthly_cost, 2),
            "projected_monthly_cost": round(self.projected_monthly_cost, 2),
            "savings_percentage": round(self.savings_percentage, 1),
            "savings_monthly": round(self.current_monthly_cost - self.projected_monthly_cost, 2),
            "utilization_metrics": self.utilization_metrics,
            "reasoning": self.reasoning,
        }


@dataclass
class CostBreakdownItem:
    """Cost breakdown for a service or tag group."""

    name: str
    cost: float
    percentage: float
    change_from_previous: float | None = None
    trend: CostTrend = CostTrend.STABLE
    resource_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "cost": round(self.cost, 2),
            "percentage": round(self.percentage, 1),
            "change_from_previous": round(self.change_from_previous, 1) if self.change_from_previous else None,
            "trend": self.trend.value,
            "resource_count": self.resource_count,
        }


@dataclass
class CostBreakdown:
    """Complete cost breakdown result."""

    total_cost: float
    period_start: datetime
    period_end: datetime
    by_service: list[CostBreakdownItem] = field(default_factory=list)
    by_tag: dict[str, list[CostBreakdownItem]] = field(default_factory=dict)
    top_resources: list[dict[str, Any]] = field(default_factory=list)
    currency: str = "USD"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_cost": round(self.total_cost, 2),
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "currency": self.currency,
            "by_service": [item.to_dict() for item in self.by_service],
            "by_tag": {tag: [item.to_dict() for item in items] for tag, items in self.by_tag.items()},
            "top_resources": self.top_resources,
        }


@dataclass
class ResourceProjection:
    """Cost projection for a single resource."""

    resource_type: str
    config: dict[str, Any]
    hourly_cost: float
    monthly_cost: float
    pricing_source: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resource_type": self.resource_type,
            "config": self.config,
            "hourly_cost": round(self.hourly_cost, 4),
            "monthly_cost": round(self.monthly_cost, 2),
            "pricing_source": self.pricing_source,
        }


@dataclass
class CostProjection:
    """Cost projection result for proposed resources."""

    resources: list[ResourceProjection]
    total_hourly: float
    total_monthly: float
    total_yearly: float
    assumptions: list[str]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resources": [r.to_dict() for r in self.resources],
            "total_hourly": round(self.total_hourly, 4),
            "total_monthly": round(self.total_monthly, 2),
            "total_yearly": round(self.total_yearly, 2),
            "assumptions": self.assumptions,
            "warnings": self.warnings,
        }


@dataclass
class CostAnalysisResult:
    """Combined result from a cost analysis operation."""

    analysis_type: str
    idle_resources: list[IdleResource] = field(default_factory=list)
    recommendations: list[RightSizeRecommendation] = field(default_factory=list)
    breakdown: CostBreakdown | None = None
    projection: CostProjection | None = None
    total_potential_savings: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result: dict[str, Any] = {
            "analysis_type": self.analysis_type,
            "total_potential_savings": round(self.total_potential_savings, 2),
        }

        if self.idle_resources:
            result["idle_resources"] = [r.to_dict() for r in self.idle_resources]
            result["idle_resources_count"] = len(self.idle_resources)
            result["idle_resources_cost"] = round(sum(r.estimated_monthly_cost for r in self.idle_resources), 2)

        if self.recommendations:
            result["recommendations"] = [r.to_dict() for r in self.recommendations]
            result["recommendations_count"] = len(self.recommendations)

        if self.breakdown:
            result["breakdown"] = self.breakdown.to_dict()

        if self.projection:
            result["projection"] = self.projection.to_dict()

        if self.errors:
            result["errors"] = self.errors

        return result


# === Cost Analyzer Class ===


class CostAnalyzer:
    """Comprehensive AWS cost analysis and optimization recommendations."""

    # Thresholds for idle detection
    EC2_CPU_IDLE_THRESHOLD = 5.0  # % average CPU
    EC2_NETWORK_IDLE_THRESHOLD = 1000  # bytes/5min
    RDS_CONNECTIONS_IDLE_THRESHOLD = 0
    EBS_IOPS_IDLE_THRESHOLD = 1.0
    STOPPED_INSTANCE_DAYS = 7

    # Instance size ordering for right-sizing
    EC2_SIZE_ORDER = [
        "nano",
        "micro",
        "small",
        "medium",
        "large",
        "xlarge",
        "2xlarge",
        "4xlarge",
        "8xlarge",
        "12xlarge",
        "16xlarge",
        "24xlarge",
    ]

    def __init__(self) -> None:
        """Initialize the cost analyzer."""
        self._session_mgr = None
        self._pricing_cache: dict[str, float] = {}

    @property
    def session_mgr(self):
        """Get session manager lazily."""
        if self._session_mgr is None:
            self._session_mgr = get_session_manager()
        return self._session_mgr

    # === Idle Resource Detection ===

    async def find_idle_resources(
        self,
        services: list[str] | None = None,
        region: str | None = None,
        lookback_days: int = 14,
    ) -> CostAnalysisResult:
        """Find potentially idle or underutilized resources."""
        logger.info("finding_idle_resources", services=services, lookback_days=lookback_days)

        services_to_check = services or ["ec2", "rds", "ebs", "eip"]
        idle_resources: list[IdleResource] = []
        errors: list[str] = []

        for service in services_to_check:
            try:
                if service == "ec2":
                    idle_resources.extend(await self._find_idle_ec2_instances(region, lookback_days))
                elif service == "rds":
                    idle_resources.extend(await self._find_idle_rds_instances(region, lookback_days))
                elif service == "ebs":
                    idle_resources.extend(await self._find_idle_ebs_volumes(region))
                elif service == "eip":
                    idle_resources.extend(await self._find_unused_elastic_ips(region))
            except Exception as e:
                logger.warning("idle_detection_failed", service=service, error=str(e))
                errors.append(f"{service}: {str(e)}")

        total_savings = sum(r.estimated_monthly_cost for r in idle_resources)

        return CostAnalysisResult(
            analysis_type="idle_resources",
            idle_resources=idle_resources,
            total_potential_savings=total_savings,
            errors=errors,
        )

    async def _find_idle_ec2_instances(self, region: str | None, lookback_days: int) -> list[IdleResource]:
        """Find idle EC2 instances based on CPU and state."""
        idle: list[IdleResource] = []
        ec2 = self.session_mgr.get_client("ec2", region)
        cw = self.session_mgr.get_client("cloudwatch", region)
        account_info = self.session_mgr.get_account_info()
        effective_region = region or self.session_mgr.active_region

        paginator = ec2.get_paginator("describe_instances")
        filters = [{"Name": "instance-state-name", "Values": ["running", "stopped"]}]

        for page in paginator.paginate(Filters=filters):
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    instance_id = instance["InstanceId"]
                    state = instance["State"]["Name"]
                    instance_type = instance["InstanceType"]

                    name = None
                    for tag in instance.get("Tags", []):
                        if tag["Key"] == "Name":
                            name = tag["Value"]
                            break

                    arn = f"arn:aws:ec2:{effective_region}:{account_info.account_id}:instance/{instance_id}"

                    # Check stopped instances
                    if state == "stopped":
                        idle.append(
                            IdleResource(
                                arn=arn,
                                service="ec2",
                                resource_type="instance",
                                name=name,
                                region=effective_region,
                                reason=IdleReason.STOPPED,
                                metrics={"state": "stopped"},
                                estimated_monthly_cost=await self._estimate_ec2_cost(instance_type, region),
                                confidence=0.9,
                            )
                        )
                        continue

                    # Check CPU utilization for running instances
                    end_time = datetime.utcnow()
                    start_time = end_time - timedelta(days=lookback_days)

                    try:
                        cpu_metrics = cw.get_metric_statistics(
                            Namespace="AWS/EC2",
                            MetricName="CPUUtilization",
                            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                            StartTime=start_time,
                            EndTime=end_time,
                            Period=3600,
                            Statistics=["Average"],
                        )

                        datapoints = cpu_metrics.get("Datapoints", [])
                        if datapoints:
                            avg_cpu = sum(dp["Average"] for dp in datapoints) / len(datapoints)

                            if avg_cpu < self.EC2_CPU_IDLE_THRESHOLD:
                                idle.append(
                                    IdleResource(
                                        arn=arn,
                                        service="ec2",
                                        resource_type="instance",
                                        name=name,
                                        region=effective_region,
                                        reason=IdleReason.LOW_CPU,
                                        metrics={
                                            "avg_cpu_percent": round(avg_cpu, 2),
                                            "threshold": self.EC2_CPU_IDLE_THRESHOLD,
                                        },
                                        estimated_monthly_cost=await self._estimate_ec2_cost(instance_type, region),
                                        confidence=0.8 if avg_cpu < 2 else 0.6,
                                    )
                                )
                    except Exception as e:
                        logger.debug("cpu_metrics_failed", instance_id=instance_id, error=str(e))

        return idle

    async def _find_idle_rds_instances(self, region: str | None, lookback_days: int) -> list[IdleResource]:
        """Find idle RDS instances based on connection count."""
        idle: list[IdleResource] = []
        rds = self.session_mgr.get_client("rds", region)
        cw = self.session_mgr.get_client("cloudwatch", region)
        effective_region = region or self.session_mgr.active_region

        response = rds.describe_db_instances()

        for db in response.get("DBInstances", []):
            db_id = db["DBInstanceIdentifier"]
            instance_class = db["DBInstanceClass"]
            arn = db["DBInstanceArn"]

            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=lookback_days)

            try:
                conn_metrics = cw.get_metric_statistics(
                    Namespace="AWS/RDS",
                    MetricName="DatabaseConnections",
                    Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_id}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,
                    Statistics=["Average", "Maximum"],
                )

                datapoints = conn_metrics.get("Datapoints", [])
                if datapoints:
                    max_connections = max(dp["Maximum"] for dp in datapoints)
                    avg_connections = sum(dp["Average"] for dp in datapoints) / len(datapoints)

                    if max_connections <= self.RDS_CONNECTIONS_IDLE_THRESHOLD:
                        idle.append(
                            IdleResource(
                                arn=arn,
                                service="rds",
                                resource_type="db_instance",
                                name=db_id,
                                region=effective_region,
                                reason=IdleReason.NO_CONNECTIONS,
                                metrics={
                                    "max_connections": max_connections,
                                    "avg_connections": round(avg_connections, 2),
                                },
                                estimated_monthly_cost=await self._estimate_rds_cost(instance_class, region),
                                confidence=0.9,
                            )
                        )
            except Exception as e:
                logger.debug("rds_metrics_failed", db_id=db_id, error=str(e))

        return idle

    async def _find_idle_ebs_volumes(self, region: str | None) -> list[IdleResource]:
        """Find unattached EBS volumes."""
        idle: list[IdleResource] = []
        ec2 = self.session_mgr.get_client("ec2", region)
        account_info = self.session_mgr.get_account_info()
        effective_region = region or self.session_mgr.active_region

        paginator = ec2.get_paginator("describe_volumes")
        filters = [{"Name": "status", "Values": ["available"]}]

        for page in paginator.paginate(Filters=filters):
            for volume in page.get("Volumes", []):
                volume_id = volume["VolumeId"]
                size_gb = volume["Size"]
                volume_type = volume["VolumeType"]

                name = None
                for tag in volume.get("Tags", []):
                    if tag["Key"] == "Name":
                        name = tag["Value"]
                        break

                arn = f"arn:aws:ec2:{effective_region}:{account_info.account_id}:volume/{volume_id}"

                idle.append(
                    IdleResource(
                        arn=arn,
                        service="ec2",
                        resource_type="ebs_volume",
                        name=name,
                        region=effective_region,
                        reason=IdleReason.UNATTACHED,
                        metrics={"size_gb": size_gb, "volume_type": volume_type},
                        estimated_monthly_cost=self._estimate_ebs_cost(size_gb, volume_type),
                        confidence=1.0,
                    )
                )

        return idle

    async def _find_unused_elastic_ips(self, region: str | None) -> list[IdleResource]:
        """Find unassociated Elastic IPs."""
        idle: list[IdleResource] = []
        ec2 = self.session_mgr.get_client("ec2", region)
        account_info = self.session_mgr.get_account_info()
        effective_region = region or self.session_mgr.active_region

        response = ec2.describe_addresses()

        for address in response.get("Addresses", []):
            if not address.get("InstanceId") and not address.get("AssociationId"):
                public_ip = address["PublicIp"]
                allocation_id = address.get("AllocationId", "")

                arn = f"arn:aws:ec2:{effective_region}:{account_info.account_id}:elastic-ip/{allocation_id}"

                idle.append(
                    IdleResource(
                        arn=arn,
                        service="ec2",
                        resource_type="elastic_ip",
                        name=public_ip,
                        region=effective_region,
                        reason=IdleReason.UNUSED_IP,
                        metrics={"public_ip": public_ip},
                        estimated_monthly_cost=3.65,  # $0.005/hr when unattached
                        confidence=1.0,
                    )
                )

        return idle

    # === Right-Sizing Recommendations ===

    async def get_rightsizing_recommendations(
        self,
        services: list[str] | None = None,
        region: str | None = None,
        lookback_days: int = 14,
    ) -> CostAnalysisResult:
        """Get right-sizing recommendations based on utilization metrics."""
        logger.info("getting_rightsizing_recommendations", services=services)

        services_to_check = services or ["ec2", "rds"]
        recommendations: list[RightSizeRecommendation] = []
        errors: list[str] = []

        for service in services_to_check:
            try:
                if service == "ec2":
                    recommendations.extend(await self._rightsize_ec2_instances(region, lookback_days))
            except Exception as e:
                logger.warning("rightsizing_failed", service=service, error=str(e))
                errors.append(f"{service}: {str(e)}")

        total_savings = sum(
            r.current_monthly_cost - r.projected_monthly_cost
            for r in recommendations
            if r.action in [RightSizeAction.DOWNSIZE, RightSizeAction.TERMINATE]
        )

        return CostAnalysisResult(
            analysis_type="rightsizing",
            recommendations=recommendations,
            total_potential_savings=max(0, total_savings),
            errors=errors,
        )

    async def _rightsize_ec2_instances(self, region: str | None, lookback_days: int) -> list[RightSizeRecommendation]:
        """Generate right-sizing recommendations for EC2 instances."""
        recommendations: list[RightSizeRecommendation] = []
        ec2 = self.session_mgr.get_client("ec2", region)
        cw = self.session_mgr.get_client("cloudwatch", region)
        account_info = self.session_mgr.get_account_info()
        effective_region = region or self.session_mgr.active_region

        paginator = ec2.get_paginator("describe_instances")
        filters = [{"Name": "instance-state-name", "Values": ["running"]}]

        for page in paginator.paginate(Filters=filters):
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    instance_id = instance["InstanceId"]
                    instance_type = instance["InstanceType"]

                    name = None
                    for tag in instance.get("Tags", []):
                        if tag["Key"] == "Name":
                            name = tag["Value"]
                            break

                    arn = f"arn:aws:ec2:{effective_region}:{account_info.account_id}:instance/{instance_id}"

                    end_time = datetime.utcnow()
                    start_time = end_time - timedelta(days=lookback_days)

                    try:
                        cpu_metrics = cw.get_metric_statistics(
                            Namespace="AWS/EC2",
                            MetricName="CPUUtilization",
                            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                            StartTime=start_time,
                            EndTime=end_time,
                            Period=3600,
                            Statistics=["Average", "Maximum"],
                        )

                        datapoints = cpu_metrics.get("Datapoints", [])
                        if not datapoints:
                            continue

                        avg_cpu = sum(dp["Average"] for dp in datapoints) / len(datapoints)
                        max_cpu = max(dp["Maximum"] for dp in datapoints)

                        current_cost = await self._estimate_ec2_cost(instance_type, region)

                        # Recommend downsizing if underutilized
                        if max_cpu < 30 and avg_cpu < 15:
                            smaller_type = self._get_smaller_instance_type(instance_type)
                            if smaller_type:
                                projected_cost = await self._estimate_ec2_cost(smaller_type, region)
                                savings = ((current_cost - projected_cost) / current_cost) * 100 if current_cost > 0 else 0

                                recommendations.append(
                                    RightSizeRecommendation(
                                        arn=arn,
                                        service="ec2",
                                        resource_type="instance",
                                        name=name,
                                        region=effective_region,
                                        current_config={"instance_type": instance_type},
                                        recommended_config={"instance_type": smaller_type},
                                        action=RightSizeAction.DOWNSIZE,
                                        current_monthly_cost=current_cost,
                                        projected_monthly_cost=projected_cost,
                                        savings_percentage=savings,
                                        utilization_metrics={
                                            "avg_cpu": round(avg_cpu, 1),
                                            "max_cpu": round(max_cpu, 1),
                                        },
                                        reasoning=f"CPU utilization (avg: {avg_cpu:.1f}%, max: {max_cpu:.1f}%) suggests over-provisioning.",
                                    )
                                )

                        # Recommend upsizing if overutilized
                        elif avg_cpu > 80 or max_cpu > 95:
                            larger_type = self._get_larger_instance_type(instance_type)
                            if larger_type:
                                projected_cost = await self._estimate_ec2_cost(larger_type, region)

                                recommendations.append(
                                    RightSizeRecommendation(
                                        arn=arn,
                                        service="ec2",
                                        resource_type="instance",
                                        name=name,
                                        region=effective_region,
                                        current_config={"instance_type": instance_type},
                                        recommended_config={"instance_type": larger_type},
                                        action=RightSizeAction.UPSIZE,
                                        current_monthly_cost=current_cost,
                                        projected_monthly_cost=projected_cost,
                                        savings_percentage=0,
                                        utilization_metrics={
                                            "avg_cpu": round(avg_cpu, 1),
                                            "max_cpu": round(max_cpu, 1),
                                        },
                                        reasoning=f"High CPU utilization (avg: {avg_cpu:.1f}%, max: {max_cpu:.1f}%) may cause performance issues.",
                                    )
                                )
                    except Exception as e:
                        logger.debug("rightsizing_analysis_failed", instance_id=instance_id, error=str(e))

        return recommendations

    # === Cost Breakdown ===

    async def get_cost_breakdown(
        self,
        granularity: str = "MONTHLY",
        group_by: str = "SERVICE",
        tag_key: str | None = None,
        days: int = 30,
    ) -> CostAnalysisResult:
        """Get cost breakdown by service or tag."""
        logger.info("getting_cost_breakdown", group_by=group_by, days=days)

        # Cost Explorer is only available in us-east-1
        ce = self.session_mgr.get_client("ce", "us-east-1")

        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days)

        group_by_param = []
        if group_by == "SERVICE":
            group_by_param = [{"Type": "DIMENSION", "Key": "SERVICE"}]
        elif group_by == "TAG" and tag_key:
            group_by_param = [{"Type": "TAG", "Key": tag_key}]
        elif group_by == "USAGE_TYPE":
            group_by_param = [{"Type": "DIMENSION", "Key": "USAGE_TYPE"}]

        try:
            response = ce.get_cost_and_usage(
                TimePeriod={
                    "Start": start_date.isoformat(),
                    "End": end_date.isoformat(),
                },
                Granularity=granularity,
                Metrics=["UnblendedCost", "UsageQuantity"],
                GroupBy=group_by_param,
            )

            items: list[CostBreakdownItem] = []
            total_cost = 0.0

            for result in response.get("ResultsByTime", []):
                for group in result.get("Groups", []):
                    name = group["Keys"][0]
                    cost = float(group["Metrics"]["UnblendedCost"]["Amount"])
                    total_cost += cost

                    existing = next((i for i in items if i.name == name), None)
                    if existing:
                        existing.cost += cost
                    else:
                        items.append(CostBreakdownItem(name=name, cost=cost, percentage=0))

            for item in items:
                item.percentage = (item.cost / total_cost * 100) if total_cost > 0 else 0

            items.sort(key=lambda x: x.cost, reverse=True)

            breakdown = CostBreakdown(
                total_cost=total_cost,
                period_start=datetime.combine(start_date, datetime.min.time()),
                period_end=datetime.combine(end_date, datetime.min.time()),
                by_service=items if group_by == "SERVICE" else [],
                by_tag={tag_key: items} if group_by == "TAG" and tag_key else {},
            )

            return CostAnalysisResult(analysis_type="cost_breakdown", breakdown=breakdown)

        except Exception as e:
            error_msg = str(e)
            if "DataUnavailableException" in error_msg:
                error_msg = "Cost Explorer is not enabled. Enable it in the AWS Console and wait 24 hours."
            elif "AccessDeniedException" in error_msg:
                error_msg = "Access denied to Cost Explorer. Ensure IAM policy includes ce:GetCostAndUsage."
            logger.error("cost_breakdown_failed", error=error_msg)
            return CostAnalysisResult(analysis_type="cost_breakdown", errors=[error_msg])

    # === Cost Projection ===

    async def project_costs(
        self,
        resources: list[dict[str, Any]],
        region: str | None = None,
    ) -> CostAnalysisResult:
        """Estimate costs for proposed resources."""
        logger.info("projecting_costs", resource_count=len(resources))

        projections: list[ResourceProjection] = []
        warnings: list[str] = []
        assumptions = [
            "Prices are on-demand rates (no reservations or savings plans)",
            "Estimates do not include data transfer costs",
            "Storage costs are based on provisioned capacity, not actual usage",
        ]

        for resource in resources:
            resource_type = resource.get("type", "").lower()
            count = resource.get("count", 1)

            try:
                if resource_type == "ec2":
                    instance_type = resource.get("instance_type", "t3.medium")
                    hourly = await self._get_ec2_price(instance_type, region) * count
                    projections.append(
                        ResourceProjection(
                            resource_type=f"EC2 {instance_type}",
                            config=resource,
                            hourly_cost=hourly,
                            monthly_cost=hourly * 730,
                            pricing_source="estimate",
                        )
                    )

                elif resource_type == "rds":
                    instance_class = resource.get("instance_class", "db.t3.medium")
                    hourly = await self._get_rds_price(instance_class, region) * count
                    projections.append(
                        ResourceProjection(
                            resource_type=f"RDS {instance_class}",
                            config=resource,
                            hourly_cost=hourly,
                            monthly_cost=hourly * 730,
                            pricing_source="estimate",
                        )
                    )

                elif resource_type == "ebs":
                    size_gb = resource.get("size_gb", 100)
                    volume_type = resource.get("volume_type", "gp3")
                    monthly = self._estimate_ebs_cost(size_gb, volume_type) * count
                    projections.append(
                        ResourceProjection(
                            resource_type=f"EBS {volume_type}",
                            config=resource,
                            hourly_cost=monthly / 730,
                            monthly_cost=monthly,
                            pricing_source="estimate",
                        )
                    )

                elif resource_type == "lambda":
                    memory_mb = resource.get("memory_mb", 128)
                    invocations = resource.get("monthly_invocations", 1000000)
                    duration_ms = resource.get("avg_duration_ms", 100)
                    monthly = self._estimate_lambda_cost(memory_mb, invocations, duration_ms)
                    projections.append(
                        ResourceProjection(
                            resource_type="Lambda",
                            config=resource,
                            hourly_cost=monthly / 730,
                            monthly_cost=monthly,
                            pricing_source="estimate",
                        )
                    )

                else:
                    warnings.append(f"Unknown resource type: {resource_type}")

            except Exception as e:
                warnings.append(f"Failed to price {resource_type}: {str(e)}")

        total_hourly = sum(p.hourly_cost for p in projections)
        total_monthly = sum(p.monthly_cost for p in projections)

        projection = CostProjection(
            resources=projections,
            total_hourly=total_hourly,
            total_monthly=total_monthly,
            total_yearly=total_monthly * 12,
            assumptions=assumptions,
            warnings=warnings,
        )

        return CostAnalysisResult(analysis_type="projection", projection=projection)

    # === Helper Methods ===

    async def _estimate_ec2_cost(self, instance_type: str, region: str | None) -> float:
        """Estimate monthly cost for an EC2 instance type."""
        hourly = await self._get_ec2_price(instance_type, region)
        return hourly * 730

    async def _get_ec2_price(self, instance_type: str, region: str | None) -> float:
        """Get EC2 hourly price with fallback estimates."""
        cache_key = f"ec2:{instance_type}:{region}"
        if cache_key in self._pricing_cache:
            return self._pricing_cache[cache_key]

        # Fallback pricing estimates (USD/hour)
        fallback_prices = {
            "t3.nano": 0.0052,
            "t3.micro": 0.0104,
            "t3.small": 0.0208,
            "t3.medium": 0.0416,
            "t3.large": 0.0832,
            "t3.xlarge": 0.1664,
            "t3.2xlarge": 0.3328,
            "m5.large": 0.096,
            "m5.xlarge": 0.192,
            "m5.2xlarge": 0.384,
            "m5.4xlarge": 0.768,
            "c5.large": 0.085,
            "c5.xlarge": 0.17,
            "r5.large": 0.126,
            "r5.xlarge": 0.252,
        }

        price = fallback_prices.get(instance_type, 0.10)
        self._pricing_cache[cache_key] = price
        return price

    async def _estimate_rds_cost(self, instance_class: str, region: str | None) -> float:
        """Estimate monthly cost for an RDS instance."""
        hourly = await self._get_rds_price(instance_class, region)
        return hourly * 730

    async def _get_rds_price(self, instance_class: str, region: str | None) -> float:
        """Get RDS hourly price with fallback estimates."""
        fallback_prices = {
            "db.t3.micro": 0.017,
            "db.t3.small": 0.034,
            "db.t3.medium": 0.068,
            "db.t3.large": 0.136,
            "db.m5.large": 0.171,
            "db.m5.xlarge": 0.342,
            "db.r5.large": 0.24,
            "db.r5.xlarge": 0.48,
        }
        return fallback_prices.get(instance_class, 0.10)

    def _estimate_ebs_cost(self, size_gb: int, volume_type: str) -> float:
        """Estimate monthly cost for EBS volume."""
        prices = {
            "gp2": 0.10,
            "gp3": 0.08,
            "io1": 0.125,
            "io2": 0.125,
            "st1": 0.045,
            "sc1": 0.025,
            "standard": 0.05,
        }
        return size_gb * prices.get(volume_type, 0.10)

    def _estimate_lambda_cost(self, memory_mb: int, invocations: int, duration_ms: int) -> float:
        """Estimate monthly Lambda cost."""
        gb_seconds = (memory_mb / 1024) * (duration_ms / 1000) * invocations
        request_cost = max(0, invocations - 1000000) * 0.0000002
        compute_cost = max(0, gb_seconds - 400000) * 0.0000166667
        return request_cost + compute_cost

    def _get_smaller_instance_type(self, instance_type: str) -> str | None:
        """Get the next smaller instance size."""
        parts = instance_type.split(".")
        if len(parts) != 2:
            return None

        family, size = parts

        try:
            current_idx = self.EC2_SIZE_ORDER.index(size)
            if current_idx > 0:
                return f"{family}.{self.EC2_SIZE_ORDER[current_idx - 1]}"
        except ValueError:
            pass

        return None

    def _get_larger_instance_type(self, instance_type: str) -> str | None:
        """Get the next larger instance size."""
        parts = instance_type.split(".")
        if len(parts) != 2:
            return None

        family, size = parts

        try:
            current_idx = self.EC2_SIZE_ORDER.index(size)
            if current_idx < len(self.EC2_SIZE_ORDER) - 1:
                return f"{family}.{self.EC2_SIZE_ORDER[current_idx + 1]}"
        except ValueError:
            pass

        return None


# === Global Instance ===

_analyzer: CostAnalyzer | None = None


def get_cost_analyzer() -> CostAnalyzer:
    """Get the global cost analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = CostAnalyzer()
    return _analyzer


def reset_cost_analyzer() -> None:
    """Reset the global cost analyzer (for testing)."""
    global _analyzer
    _analyzer = None
