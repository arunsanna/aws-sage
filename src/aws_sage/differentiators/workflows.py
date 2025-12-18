"""Incident investigation workflows for AWS MCP Pro."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import structlog

from aws_sage.core.session import get_session_manager

logger = structlog.get_logger()


class IncidentType(Enum):
    """Types of incidents to investigate."""

    LAMBDA_FAILURE = "lambda_failure"
    HIGH_LATENCY = "high_latency"
    SECURITY_ALERT = "security_alert"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    CONNECTIVITY = "connectivity"


@dataclass
class InvestigationStep:
    """A step in an investigation workflow."""

    name: str
    description: str
    service: str
    operation: str
    parameters: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    status: str = "pending"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "service": self.service,
            "operation": self.operation,
            "status": self.status,
            "result_summary": self._summarize_result(),
            "error": self.error,
        }

    def _summarize_result(self) -> str | None:
        """Summarize the result for display."""
        if self.result is None:
            return None
        if isinstance(self.result, list):
            return f"{len(self.result)} items found"
        if isinstance(self.result, dict):
            return f"{len(self.result)} fields"
        return str(self.result)[:100]


@dataclass
class InvestigationResult:
    """Result of an incident investigation."""

    incident_type: IncidentType
    resource: str
    steps: list[InvestigationStep] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    severity: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "incident_type": self.incident_type.value,
            "resource": self.resource,
            "severity": self.severity,
            "steps": [s.to_dict() for s in self.steps],
            "findings": self.findings,
            "recommendations": self.recommendations,
            "steps_completed": sum(1 for s in self.steps if s.status == "completed"),
            "steps_total": len(self.steps),
        }


class IncidentInvestigator:
    """Automated incident investigation workflows."""

    def __init__(self):
        """Initialize the incident investigator."""
        self._session_mgr = None

    @property
    def session_mgr(self):
        """Get session manager lazily."""
        if self._session_mgr is None:
            self._session_mgr = get_session_manager()
        return self._session_mgr

    async def investigate(
        self,
        incident_type: IncidentType,
        resource: str,
        region: str | None = None,
        time_range_hours: int = 1,
    ) -> InvestigationResult:
        """
        Run an automated investigation workflow.

        Args:
            incident_type: Type of incident to investigate
            resource: Resource ARN or identifier
            region: AWS region
            time_range_hours: Hours of data to analyze

        Returns:
            InvestigationResult with findings and recommendations
        """
        logger.info(
            "starting_investigation",
            incident_type=incident_type.value,
            resource=resource,
        )

        if incident_type == IncidentType.LAMBDA_FAILURE:
            return await self._investigate_lambda_failure(resource, region, time_range_hours)
        elif incident_type == IncidentType.HIGH_LATENCY:
            return await self._investigate_high_latency(resource, region, time_range_hours)
        elif incident_type == IncidentType.SECURITY_ALERT:
            return await self._investigate_security_alert(resource, region, time_range_hours)
        elif incident_type == IncidentType.RESOURCE_EXHAUSTION:
            return await self._investigate_resource_exhaustion(resource, region, time_range_hours)
        else:
            return InvestigationResult(
                incident_type=incident_type,
                resource=resource,
                findings=["Investigation type not yet implemented"],
                severity="unknown",
            )

    async def _investigate_lambda_failure(
        self,
        function_name: str,
        region: str | None,
        time_range_hours: int,
    ) -> InvestigationResult:
        """Investigate Lambda function failures."""
        result = InvestigationResult(
            incident_type=IncidentType.LAMBDA_FAILURE,
            resource=function_name,
        )

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=time_range_hours)

        # Step 1: Get function configuration
        step1 = InvestigationStep(
            name="Get Function Configuration",
            description="Retrieve Lambda function settings and status",
            service="lambda",
            operation="get_function",
        )
        result.steps.append(step1)

        try:
            lambda_client = self.session_mgr.get_client("lambda", region)
            func_response = lambda_client.get_function(FunctionName=function_name)
            step1.result = func_response.get("Configuration", {})
            step1.status = "completed"

            # Check for issues
            config = step1.result
            if config.get("State") != "Active":
                result.findings.append(f"Function state is '{config.get('State')}', not Active")
            if config.get("LastUpdateStatus") == "Failed":
                result.findings.append(f"Last update failed: {config.get('LastUpdateStatusReason')}")

        except Exception as e:
            step1.status = "failed"
            step1.error = str(e)
            result.findings.append(f"Could not retrieve function configuration: {e}")

        # Step 2: Get recent invocations from CloudWatch Logs
        step2 = InvestigationStep(
            name="Check CloudWatch Logs",
            description="Look for recent errors in function logs",
            service="logs",
            operation="filter_log_events",
        )
        result.steps.append(step2)

        try:
            logs_client = self.session_mgr.get_client("logs", region)
            log_group = f"/aws/lambda/{function_name}"

            log_response = logs_client.filter_log_events(
                logGroupName=log_group,
                startTime=int(start_time.timestamp() * 1000),
                endTime=int(end_time.timestamp() * 1000),
                filterPattern="ERROR",
                limit=50,
            )
            step2.result = log_response.get("events", [])
            step2.status = "completed"

            error_count = len(step2.result)
            if error_count > 0:
                result.findings.append(f"Found {error_count} ERROR logs in the past {time_range_hours} hour(s)")
                # Extract unique error messages
                error_messages = set()
                for event in step2.result[:10]:
                    msg = event.get("message", "")[:200]
                    error_messages.add(msg)
                for msg in list(error_messages)[:3]:
                    result.findings.append(f"Error sample: {msg}")

        except Exception as e:
            step2.status = "failed"
            step2.error = str(e)

        # Step 3: Get CloudWatch metrics
        step3 = InvestigationStep(
            name="Check CloudWatch Metrics",
            description="Analyze invocation and error metrics",
            service="cloudwatch",
            operation="get_metric_statistics",
        )
        result.steps.append(step3)

        try:
            cw_client = self.session_mgr.get_client("cloudwatch", region)

            # Get error count
            error_metrics = cw_client.get_metric_statistics(
                Namespace="AWS/Lambda",
                MetricName="Errors",
                Dimensions=[{"Name": "FunctionName", "Value": function_name}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=["Sum"],
            )

            # Get invocation count
            invocation_metrics = cw_client.get_metric_statistics(
                Namespace="AWS/Lambda",
                MetricName="Invocations",
                Dimensions=[{"Name": "FunctionName", "Value": function_name}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=["Sum"],
            )

            total_errors = sum(dp["Sum"] for dp in error_metrics.get("Datapoints", []))
            total_invocations = sum(dp["Sum"] for dp in invocation_metrics.get("Datapoints", []))

            step3.result = {
                "total_errors": total_errors,
                "total_invocations": total_invocations,
                "error_rate": (total_errors / total_invocations * 100) if total_invocations > 0 else 0,
            }
            step3.status = "completed"

            if total_errors > 0:
                error_rate = step3.result["error_rate"]
                result.findings.append(
                    f"Error rate: {error_rate:.1f}% ({int(total_errors)} errors / {int(total_invocations)} invocations)"
                )

        except Exception as e:
            step3.status = "failed"
            step3.error = str(e)

        # Step 4: Check recent deployments
        step4 = InvestigationStep(
            name="Check Recent Changes",
            description="Look for recent function updates",
            service="lambda",
            operation="list_versions_by_function",
        )
        result.steps.append(step4)

        try:
            versions = lambda_client.list_versions_by_function(FunctionName=function_name)
            step4.result = versions.get("Versions", [])
            step4.status = "completed"

            # Check if there was a recent deployment
            for version in step4.result[-3:]:
                last_modified = version.get("LastModified", "")
                result.findings.append(f"Version {version.get('Version')}: Last modified {last_modified}")

        except Exception as e:
            step4.status = "failed"
            step4.error = str(e)

        # Generate recommendations
        self._generate_lambda_recommendations(result)

        # Determine severity
        result.severity = self._determine_severity(result)

        return result

    async def _investigate_high_latency(
        self,
        resource: str,
        region: str | None,
        time_range_hours: int,
    ) -> InvestigationResult:
        """Investigate high latency issues."""
        result = InvestigationResult(
            incident_type=IncidentType.HIGH_LATENCY,
            resource=resource,
        )

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=time_range_hours)

        # Step 1: Check CloudWatch latency metrics
        step1 = InvestigationStep(
            name="Check Latency Metrics",
            description="Analyze latency metrics from CloudWatch",
            service="cloudwatch",
            operation="get_metric_statistics",
        )
        result.steps.append(step1)

        try:
            cw_client = self.session_mgr.get_client("cloudwatch", region)

            # Determine metric based on resource type
            if "lambda" in resource.lower():
                namespace = "AWS/Lambda"
                metric_name = "Duration"
                dimension_name = "FunctionName"
                dimension_value = resource.split(":")[-1] if ":" in resource else resource
            elif "elb" in resource.lower() or "loadbalancer" in resource.lower():
                namespace = "AWS/ApplicationELB"
                metric_name = "TargetResponseTime"
                dimension_name = "LoadBalancer"
                dimension_value = resource
            else:
                # Default to API Gateway
                namespace = "AWS/ApiGateway"
                metric_name = "Latency"
                dimension_name = "ApiName"
                dimension_value = resource

            metrics = cw_client.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=[{"Name": dimension_name, "Value": dimension_value}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=["Average", "Maximum", "p99"],
            )

            step1.result = metrics.get("Datapoints", [])
            step1.status = "completed"

            if step1.result:
                avg_latency = sum(dp.get("Average", 0) for dp in step1.result) / len(step1.result)
                max_latency = max(dp.get("Maximum", 0) for dp in step1.result)
                result.findings.append(f"Average latency: {avg_latency:.0f}ms")
                result.findings.append(f"Maximum latency: {max_latency:.0f}ms")

        except Exception as e:
            step1.status = "failed"
            step1.error = str(e)

        # Step 2: Check for throttling
        step2 = InvestigationStep(
            name="Check Throttling",
            description="Look for throttling events",
            service="cloudwatch",
            operation="get_metric_statistics",
        )
        result.steps.append(step2)

        try:
            cw_client = self.session_mgr.get_client("cloudwatch", region)

            # Check for Lambda throttles
            throttle_metrics = cw_client.get_metric_statistics(
                Namespace="AWS/Lambda",
                MetricName="Throttles",
                Dimensions=[{"Name": "FunctionName", "Value": resource}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=["Sum"],
            )

            total_throttles = sum(dp["Sum"] for dp in throttle_metrics.get("Datapoints", []))
            step2.result = {"total_throttles": total_throttles}
            step2.status = "completed"

            if total_throttles > 0:
                result.findings.append(f"Detected {int(total_throttles)} throttle events")

        except Exception as e:
            step2.status = "failed"
            step2.error = str(e)

        # Generate recommendations
        result.recommendations = [
            "Review CloudWatch dashboards for latency trends",
            "Check for increased traffic or load",
            "Consider increasing provisioned capacity",
            "Review cold start frequency for Lambda functions",
            "Check database connection pool settings",
        ]

        result.severity = self._determine_severity(result)
        return result

    async def _investigate_security_alert(
        self,
        resource: str,
        region: str | None,
        time_range_hours: int,
    ) -> InvestigationResult:
        """Investigate security alerts."""
        result = InvestigationResult(
            incident_type=IncidentType.SECURITY_ALERT,
            resource=resource,
        )

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=time_range_hours)

        # Step 1: Check GuardDuty findings
        step1 = InvestigationStep(
            name="Check GuardDuty Findings",
            description="Look for related GuardDuty findings",
            service="guardduty",
            operation="list_findings",
        )
        result.steps.append(step1)

        try:
            gd_client = self.session_mgr.get_client("guardduty", region)

            # Get detector ID
            detectors = gd_client.list_detectors()
            if detectors.get("DetectorIds"):
                detector_id = detectors["DetectorIds"][0]

                findings = gd_client.list_findings(
                    DetectorId=detector_id,
                    FindingCriteria={
                        "Criterion": {
                            "updatedAt": {
                                "GreaterThanOrEqual": int(start_time.timestamp() * 1000),
                            }
                        }
                    },
                    MaxResults=50,
                )

                step1.result = findings.get("FindingIds", [])
                step1.status = "completed"

                if step1.result:
                    result.findings.append(f"Found {len(step1.result)} GuardDuty findings")

        except Exception as e:
            step1.status = "failed"
            step1.error = str(e)

        # Step 2: Check CloudTrail for suspicious activity
        step2 = InvestigationStep(
            name="Check CloudTrail Events",
            description="Look for suspicious API activity",
            service="cloudtrail",
            operation="lookup_events",
        )
        result.steps.append(step2)

        try:
            ct_client = self.session_mgr.get_client("cloudtrail", region)

            events = ct_client.lookup_events(
                StartTime=start_time,
                EndTime=end_time,
                MaxResults=50,
            )

            step2.result = events.get("Events", [])
            step2.status = "completed"

            # Look for suspicious events
            suspicious_events = ["DeleteTrail", "StopLogging", "DeleteBucket", "CreateUser", "AttachUserPolicy"]
            found_suspicious = [e for e in step2.result if e.get("EventName") in suspicious_events]
            if found_suspicious:
                result.findings.append(f"Found {len(found_suspicious)} potentially suspicious API calls")
                for event in found_suspicious[:3]:
                    result.findings.append(f"  - {event.get('EventName')} by {event.get('Username', 'unknown')}")

        except Exception as e:
            step2.status = "failed"
            step2.error = str(e)

        # Generate recommendations
        result.recommendations = [
            "Review IAM policies for overly permissive access",
            "Enable MFA for all privileged users",
            "Review VPC security group rules",
            "Check for unauthorized access patterns in CloudTrail",
            "Consider enabling AWS Config rules for compliance",
        ]

        result.severity = "HIGH"  # Security alerts are always high severity
        return result

    async def _investigate_resource_exhaustion(
        self,
        resource: str,
        region: str | None,
        time_range_hours: int,
    ) -> InvestigationResult:
        """Investigate resource exhaustion issues."""
        result = InvestigationResult(
            incident_type=IncidentType.RESOURCE_EXHAUSTION,
            resource=resource,
        )

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=time_range_hours)

        # Step 1: Check service quotas
        step1 = InvestigationStep(
            name="Check Service Quotas",
            description="Review current service quota usage",
            service="service-quotas",
            operation="list_service_quotas",
        )
        result.steps.append(step1)

        try:
            sq_client = self.session_mgr.get_client("service-quotas", region)

            # Parse service from resource
            service_code = resource.split(":")[2] if ":" in resource else resource

            quotas = sq_client.list_service_quotas(ServiceCode=service_code)
            step1.result = quotas.get("Quotas", [])
            step1.status = "completed"

            # Check for quotas near limit
            for quota in step1.result:
                if quota.get("Value") and quota.get("UsageMetric"):
                    usage = quota.get("UsageMetric", {}).get("MetricStatisticRecommendation")
                    if usage:
                        result.findings.append(f"{quota.get('QuotaName')}: {usage}")

        except Exception as e:
            step1.status = "failed"
            step1.error = str(e)

        # Step 2: Check CloudWatch for resource metrics
        step2 = InvestigationStep(
            name="Check Resource Metrics",
            description="Analyze CPU, memory, and connection metrics",
            service="cloudwatch",
            operation="get_metric_statistics",
        )
        result.steps.append(step2)

        try:
            cw_client = self.session_mgr.get_client("cloudwatch", region)

            # Check EC2 CPU utilization as an example
            cpu_metrics = cw_client.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=["Average", "Maximum"],
            )

            step2.result = cpu_metrics.get("Datapoints", [])
            step2.status = "completed"

            if step2.result:
                avg_cpu = sum(dp.get("Average", 0) for dp in step2.result) / len(step2.result)
                max_cpu = max(dp.get("Maximum", 0) for dp in step2.result)
                result.findings.append(f"Average CPU utilization: {avg_cpu:.1f}%")
                result.findings.append(f"Maximum CPU utilization: {max_cpu:.1f}%")

                if max_cpu > 90:
                    result.findings.append("WARNING: CPU utilization exceeded 90%")

        except Exception as e:
            step2.status = "failed"
            step2.error = str(e)

        # Generate recommendations
        result.recommendations = [
            "Request quota increase through Service Quotas console",
            "Review resource scaling policies",
            "Consider implementing auto-scaling",
            "Optimize resource usage to reduce demand",
            "Review for unused or idle resources",
        ]

        result.severity = self._determine_severity(result)
        return result

    def _generate_lambda_recommendations(self, result: InvestigationResult) -> None:
        """Generate recommendations for Lambda failures."""
        findings_text = " ".join(result.findings).lower()

        if "timeout" in findings_text:
            result.recommendations.append("Consider increasing function timeout")
            result.recommendations.append("Check for slow external API calls or database queries")

        if "memory" in findings_text:
            result.recommendations.append("Consider increasing function memory")
            result.recommendations.append("Profile memory usage to identify leaks")

        if "permission" in findings_text or "access denied" in findings_text:
            result.recommendations.append("Review IAM execution role permissions")
            result.recommendations.append("Check resource-based policies on accessed resources")

        if "cold start" in findings_text:
            result.recommendations.append("Consider using provisioned concurrency")
            result.recommendations.append("Reduce deployment package size")

        # Default recommendations
        if not result.recommendations:
            result.recommendations = [
                "Review CloudWatch Logs for detailed error messages",
                "Check function timeout and memory settings",
                "Verify IAM role has necessary permissions",
                "Test function with different input payloads",
                "Consider enabling X-Ray tracing for detailed analysis",
            ]

    def _determine_severity(self, result: InvestigationResult) -> str:
        """Determine incident severity based on findings."""
        findings_text = " ".join(result.findings).lower()

        # High severity indicators
        if any(
            indicator in findings_text
            for indicator in ["security", "unauthorized", "suspicious", "error rate: 100", "critical"]
        ):
            return "HIGH"

        # Medium severity indicators
        if any(
            indicator in findings_text
            for indicator in ["error rate", "throttl", "timeout", "warning", "failed"]
        ):
            return "MEDIUM"

        return "LOW"


# Global instance
_investigator: IncidentInvestigator | None = None


def get_incident_investigator() -> IncidentInvestigator:
    """Get the global incident investigator instance."""
    global _investigator
    if _investigator is None:
        _investigator = IncidentInvestigator()
    return _investigator
