"""Resource dependency mapping for AWS MCP Pro."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from aws_mcp.core.session import get_session_manager

logger = structlog.get_logger()


class DependencyType(Enum):
    """Types of resource dependencies."""

    USES = "uses"  # Resource A uses resource B
    TRIGGERS = "triggers"  # Resource A triggers resource B
    STORES_IN = "stores_in"  # Resource A stores data in resource B
    SECURED_BY = "secured_by"  # Resource A is secured by resource B
    DEPLOYED_TO = "deployed_to"  # Resource A is deployed to resource B
    REFERENCES = "references"  # Resource A references resource B


@dataclass
class ResourceDependency:
    """A dependency between two resources."""

    source_arn: str
    target_arn: str
    dependency_type: DependencyType
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source": self.source_arn,
            "target": self.target_arn,
            "type": self.dependency_type.value,
            "description": self.description,
        }


@dataclass
class DependencyGraph:
    """A graph of resource dependencies."""

    root_resource: str
    dependencies: list[ResourceDependency] = field(default_factory=list)
    affected_resources: list[str] = field(default_factory=list)
    depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "root_resource": self.root_resource,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "affected_resources": self.affected_resources,
            "total_dependencies": len(self.dependencies),
            "depth": self.depth,
        }


class DependencyMapper:
    """Maps dependencies between AWS resources."""

    def __init__(self):
        """Initialize the dependency mapper."""
        self._session_mgr = None

    @property
    def session_mgr(self):
        """Get session manager lazily."""
        if self._session_mgr is None:
            self._session_mgr = get_session_manager()
        return self._session_mgr

    async def map_dependencies(
        self,
        resource_arn: str,
        max_depth: int = 2,
        region: str | None = None,
    ) -> DependencyGraph:
        """
        Map dependencies for a resource.

        Args:
            resource_arn: ARN of the resource to analyze
            max_depth: Maximum depth to traverse
            region: Region to search

        Returns:
            DependencyGraph with found dependencies
        """
        logger.info("mapping_dependencies", resource_arn=resource_arn, max_depth=max_depth)

        graph = DependencyGraph(root_resource=resource_arn, depth=max_depth)
        visited: set[str] = set()

        await self._traverse_dependencies(
            resource_arn, graph, visited, current_depth=0, max_depth=max_depth, region=region
        )

        # Collect all affected resources
        graph.affected_resources = list(visited - {resource_arn})

        return graph

    async def _traverse_dependencies(
        self,
        resource_arn: str,
        graph: DependencyGraph,
        visited: set[str],
        current_depth: int,
        max_depth: int,
        region: str | None,
    ) -> None:
        """Recursively traverse and collect dependencies."""
        if current_depth >= max_depth or resource_arn in visited:
            return

        visited.add(resource_arn)

        # Parse the ARN to determine service
        parts = resource_arn.split(":")
        if len(parts) < 6:
            return

        service = parts[2]
        dependencies = await self._get_dependencies_for_service(resource_arn, service, region)

        for dep in dependencies:
            graph.dependencies.append(dep)

            # Recurse if not at max depth
            if current_depth + 1 < max_depth:
                await self._traverse_dependencies(
                    dep.target_arn, graph, visited, current_depth + 1, max_depth, region
                )

    async def _get_dependencies_for_service(
        self,
        resource_arn: str,
        service: str,
        region: str | None,
    ) -> list[ResourceDependency]:
        """Get dependencies for a specific service type."""
        dependencies: list[ResourceDependency] = []

        try:
            if service == "lambda":
                dependencies.extend(await self._get_lambda_dependencies(resource_arn, region))
            elif service == "ec2":
                dependencies.extend(await self._get_ec2_dependencies(resource_arn, region))
            elif service == "rds":
                dependencies.extend(await self._get_rds_dependencies(resource_arn, region))
            elif service == "ecs":
                dependencies.extend(await self._get_ecs_dependencies(resource_arn, region))
            elif service == "elasticloadbalancing":
                dependencies.extend(await self._get_elb_dependencies(resource_arn, region))
        except Exception as e:
            logger.warning("failed_to_get_dependencies", service=service, error=str(e))

        return dependencies

    async def _get_lambda_dependencies(
        self,
        function_arn: str,
        region: str | None,
    ) -> list[ResourceDependency]:
        """Get dependencies for a Lambda function."""
        dependencies: list[ResourceDependency] = []

        try:
            client = self.session_mgr.get_client("lambda", region)

            # Extract function name from ARN
            function_name = function_arn.split(":")[-1]
            if "/" in function_name:
                function_name = function_name.split("/")[-1]

            # Get function configuration
            response = client.get_function(FunctionName=function_name)
            config = response.get("Configuration", {})

            # Check execution role
            role_arn = config.get("Role")
            if role_arn:
                dependencies.append(
                    ResourceDependency(
                        source_arn=function_arn,
                        target_arn=role_arn,
                        dependency_type=DependencyType.SECURED_BY,
                        description="Lambda execution role",
                    )
                )

            # Check VPC configuration
            vpc_config = config.get("VpcConfig", {})
            if vpc_config.get("VpcId"):
                vpc_arn = f"arn:aws:ec2:{region or 'us-east-1'}::vpc/{vpc_config['VpcId']}"
                dependencies.append(
                    ResourceDependency(
                        source_arn=function_arn,
                        target_arn=vpc_arn,
                        dependency_type=DependencyType.DEPLOYED_TO,
                        description="Lambda VPC configuration",
                    )
                )

            # Check environment variables for resource references
            env_vars = config.get("Environment", {}).get("Variables", {})
            for key, value in env_vars.items():
                if value.startswith("arn:aws:"):
                    dependencies.append(
                        ResourceDependency(
                            source_arn=function_arn,
                            target_arn=value,
                            dependency_type=DependencyType.REFERENCES,
                            description=f"Environment variable: {key}",
                        )
                    )

            # Check event source mappings
            mappings = client.list_event_source_mappings(FunctionName=function_name)
            for mapping in mappings.get("EventSourceMappings", []):
                source_arn = mapping.get("EventSourceArn")
                if source_arn:
                    dependencies.append(
                        ResourceDependency(
                            source_arn=source_arn,
                            target_arn=function_arn,
                            dependency_type=DependencyType.TRIGGERS,
                            description="Event source mapping",
                        )
                    )

        except Exception as e:
            logger.warning("failed_to_get_lambda_dependencies", error=str(e))

        return dependencies

    async def _get_ec2_dependencies(
        self,
        instance_arn: str,
        region: str | None,
    ) -> list[ResourceDependency]:
        """Get dependencies for an EC2 instance."""
        dependencies: list[ResourceDependency] = []

        try:
            client = self.session_mgr.get_client("ec2", region)

            # Extract instance ID from ARN
            instance_id = instance_arn.split("/")[-1]

            response = client.describe_instances(InstanceIds=[instance_id])
            for reservation in response.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    # Security groups
                    for sg in instance.get("SecurityGroups", []):
                        sg_arn = f"arn:aws:ec2:{region or 'us-east-1'}::security-group/{sg['GroupId']}"
                        dependencies.append(
                            ResourceDependency(
                                source_arn=instance_arn,
                                target_arn=sg_arn,
                                dependency_type=DependencyType.SECURED_BY,
                                description=f"Security group: {sg.get('GroupName', sg['GroupId'])}",
                            )
                        )

                    # Subnet/VPC
                    subnet_id = instance.get("SubnetId")
                    if subnet_id:
                        subnet_arn = f"arn:aws:ec2:{region or 'us-east-1'}::subnet/{subnet_id}"
                        dependencies.append(
                            ResourceDependency(
                                source_arn=instance_arn,
                                target_arn=subnet_arn,
                                dependency_type=DependencyType.DEPLOYED_TO,
                                description="Instance subnet",
                            )
                        )

                    # IAM instance profile
                    profile = instance.get("IamInstanceProfile", {})
                    if profile.get("Arn"):
                        dependencies.append(
                            ResourceDependency(
                                source_arn=instance_arn,
                                target_arn=profile["Arn"],
                                dependency_type=DependencyType.SECURED_BY,
                                description="IAM instance profile",
                            )
                        )

                    # EBS volumes
                    for mapping in instance.get("BlockDeviceMappings", []):
                        ebs = mapping.get("Ebs", {})
                        volume_id = ebs.get("VolumeId")
                        if volume_id:
                            vol_arn = f"arn:aws:ec2:{region or 'us-east-1'}::volume/{volume_id}"
                            dependencies.append(
                                ResourceDependency(
                                    source_arn=instance_arn,
                                    target_arn=vol_arn,
                                    dependency_type=DependencyType.USES,
                                    description=f"EBS volume: {mapping.get('DeviceName', 'unknown')}",
                                )
                            )

        except Exception as e:
            logger.warning("failed_to_get_ec2_dependencies", error=str(e))

        return dependencies

    async def _get_rds_dependencies(
        self,
        db_arn: str,
        region: str | None,
    ) -> list[ResourceDependency]:
        """Get dependencies for an RDS instance."""
        dependencies: list[ResourceDependency] = []

        try:
            client = self.session_mgr.get_client("rds", region)

            # Extract DB instance identifier from ARN
            db_id = db_arn.split(":")[-1]

            response = client.describe_db_instances(DBInstanceIdentifier=db_id)
            for db in response.get("DBInstances", []):
                # VPC security groups
                for sg in db.get("VpcSecurityGroups", []):
                    sg_id = sg.get("VpcSecurityGroupId")
                    if sg_id:
                        sg_arn = f"arn:aws:ec2:{region or 'us-east-1'}::security-group/{sg_id}"
                        dependencies.append(
                            ResourceDependency(
                                source_arn=db_arn,
                                target_arn=sg_arn,
                                dependency_type=DependencyType.SECURED_BY,
                                description="VPC security group",
                            )
                        )

                # DB subnet group
                subnet_group = db.get("DBSubnetGroup", {})
                if subnet_group.get("DBSubnetGroupArn"):
                    dependencies.append(
                        ResourceDependency(
                            source_arn=db_arn,
                            target_arn=subnet_group["DBSubnetGroupArn"],
                            dependency_type=DependencyType.DEPLOYED_TO,
                            description="DB subnet group",
                        )
                    )

                # KMS key
                kms_key = db.get("KmsKeyId")
                if kms_key:
                    dependencies.append(
                        ResourceDependency(
                            source_arn=db_arn,
                            target_arn=kms_key,
                            dependency_type=DependencyType.SECURED_BY,
                            description="KMS encryption key",
                        )
                    )

        except Exception as e:
            logger.warning("failed_to_get_rds_dependencies", error=str(e))

        return dependencies

    async def _get_ecs_dependencies(
        self,
        service_arn: str,
        region: str | None,
    ) -> list[ResourceDependency]:
        """Get dependencies for an ECS service."""
        dependencies: list[ResourceDependency] = []

        try:
            client = self.session_mgr.get_client("ecs", region)

            # Parse ARN to get cluster and service
            parts = service_arn.split("/")
            if len(parts) >= 2:
                cluster = parts[-2]
                service_name = parts[-1]

                response = client.describe_services(cluster=cluster, services=[service_name])
                for svc in response.get("services", []):
                    # Task definition
                    task_def = svc.get("taskDefinition")
                    if task_def:
                        dependencies.append(
                            ResourceDependency(
                                source_arn=service_arn,
                                target_arn=task_def,
                                dependency_type=DependencyType.USES,
                                description="Task definition",
                            )
                        )

                    # Load balancers
                    for lb in svc.get("loadBalancers", []):
                        target_group = lb.get("targetGroupArn")
                        if target_group:
                            dependencies.append(
                                ResourceDependency(
                                    source_arn=service_arn,
                                    target_arn=target_group,
                                    dependency_type=DependencyType.USES,
                                    description="Target group",
                                )
                            )

                    # IAM role
                    role = svc.get("roleArn")
                    if role:
                        dependencies.append(
                            ResourceDependency(
                                source_arn=service_arn,
                                target_arn=role,
                                dependency_type=DependencyType.SECURED_BY,
                                description="Service role",
                            )
                        )

        except Exception as e:
            logger.warning("failed_to_get_ecs_dependencies", error=str(e))

        return dependencies

    async def _get_elb_dependencies(
        self,
        lb_arn: str,
        region: str | None,
    ) -> list[ResourceDependency]:
        """Get dependencies for a load balancer."""
        dependencies: list[ResourceDependency] = []

        try:
            client = self.session_mgr.get_client("elbv2", region)

            # Get target groups
            response = client.describe_target_groups(LoadBalancerArn=lb_arn)
            for tg in response.get("TargetGroups", []):
                dependencies.append(
                    ResourceDependency(
                        source_arn=lb_arn,
                        target_arn=tg["TargetGroupArn"],
                        dependency_type=DependencyType.USES,
                        description=f"Target group: {tg.get('TargetGroupName', 'unknown')}",
                    )
                )

            # Get listeners
            listeners = client.describe_listeners(LoadBalancerArn=lb_arn)
            for listener in listeners.get("Listeners", []):
                # Check for SSL certificates
                for cert in listener.get("Certificates", []):
                    cert_arn = cert.get("CertificateArn")
                    if cert_arn:
                        dependencies.append(
                            ResourceDependency(
                                source_arn=lb_arn,
                                target_arn=cert_arn,
                                dependency_type=DependencyType.SECURED_BY,
                                description="SSL certificate",
                            )
                        )

        except Exception as e:
            logger.warning("failed_to_get_elb_dependencies", error=str(e))

        return dependencies

    async def impact_analysis(
        self,
        resource_arn: str,
        region: str | None = None,
    ) -> dict[str, Any]:
        """
        Analyze the impact of modifying or deleting a resource.

        Args:
            resource_arn: ARN of the resource to analyze
            region: Region to search

        Returns:
            Impact analysis with affected resources and risk assessment
        """
        logger.info("analyzing_impact", resource_arn=resource_arn)

        graph = await self.map_dependencies(resource_arn, max_depth=3, region=region)

        # Count resources by type
        affected_by_type: dict[str, int] = {}
        for dep in graph.dependencies:
            service = dep.target_arn.split(":")[2] if ":" in dep.target_arn else "unknown"
            affected_by_type[service] = affected_by_type.get(service, 0) + 1

        # Determine risk level
        total_affected = len(graph.affected_resources)
        if total_affected > 20:
            risk_level = "HIGH"
        elif total_affected > 5:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return {
            "resource": resource_arn,
            "risk_level": risk_level,
            "total_affected_resources": total_affected,
            "affected_by_type": affected_by_type,
            "dependencies": graph.to_dict(),
            "recommendation": self._get_recommendation(risk_level, total_affected),
        }

    def _get_recommendation(self, risk_level: str, affected_count: int) -> str:
        """Generate a recommendation based on impact analysis."""
        if risk_level == "HIGH":
            return (
                f"This resource has {affected_count} dependencies. "
                "Strongly recommend creating a backup and testing in staging before any changes. "
                "Consider implementing the change during a maintenance window."
            )
        elif risk_level == "MEDIUM":
            return (
                f"This resource has {affected_count} dependencies. "
                "Review the dependency list and ensure all dependent services can handle the change."
            )
        else:
            return "This resource has minimal dependencies. Changes should have limited impact."


# Global instance
_mapper: DependencyMapper | None = None


def get_dependency_mapper() -> DependencyMapper:
    """Get the global dependency mapper instance."""
    global _mapper
    if _mapper is None:
        _mapper = DependencyMapper()
    return _mapper
