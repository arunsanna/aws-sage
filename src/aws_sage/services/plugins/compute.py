"""Compute service plugins (EC2, Lambda, ECS)."""

from __future__ import annotations

from typing import Any

import boto3

from aws_sage.config import OperationCategory
from aws_sage.services.base import BaseService, OperationResult, OperationSpec, register_service


@register_service
class EC2Service(BaseService):
    """Amazon EC2 service plugin."""

    @property
    def service_name(self) -> str:
        return "ec2"

    @property
    def display_name(self) -> str:
        return "Amazon EC2"

    def get_operations(self) -> list[OperationSpec]:
        return [
            OperationSpec(
                name="describe_instances",
                description="List EC2 instances",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["InstanceIds", "Filters", "MaxResults"],
                supports_pagination=True,
                result_key="Reservations",
            ),
            OperationSpec(
                name="describe_vpcs",
                description="List VPCs",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["VpcIds", "Filters"],
                supports_pagination=True,
                result_key="Vpcs",
            ),
            OperationSpec(
                name="describe_subnets",
                description="List subnets",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["SubnetIds", "Filters"],
                supports_pagination=True,
                result_key="Subnets",
            ),
            OperationSpec(
                name="describe_security_groups",
                description="List security groups",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["GroupIds", "GroupNames", "Filters"],
                supports_pagination=True,
                result_key="SecurityGroups",
            ),
            OperationSpec(
                name="describe_volumes",
                description="List EBS volumes",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["VolumeIds", "Filters"],
                supports_pagination=True,
                result_key="Volumes",
            ),
            OperationSpec(
                name="describe_images",
                description="List AMIs",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["ImageIds", "Owners", "Filters"],
                supports_pagination=False,
                result_key="Images",
            ),
            OperationSpec(
                name="start_instances",
                description="Start EC2 instances",
                category=OperationCategory.WRITE,
                required_params=["InstanceIds"],
                optional_params=[],
                supports_pagination=False,
                supports_dry_run=True,
            ),
            OperationSpec(
                name="stop_instances",
                description="Stop EC2 instances",
                category=OperationCategory.WRITE,
                required_params=["InstanceIds"],
                optional_params=["Force"],
                supports_pagination=False,
                supports_dry_run=True,
            ),
            OperationSpec(
                name="terminate_instances",
                description="Terminate EC2 instances",
                category=OperationCategory.DESTRUCTIVE,
                required_params=["InstanceIds"],
                optional_params=[],
                supports_pagination=False,
                supports_dry_run=True,
            ),
            OperationSpec(
                name="run_instances",
                description="Launch new EC2 instances",
                category=OperationCategory.WRITE,
                required_params=["ImageId", "MinCount", "MaxCount"],
                optional_params=["InstanceType", "KeyName", "SecurityGroupIds", "SubnetId"],
                supports_pagination=False,
                supports_dry_run=True,
            ),
        ]

    async def execute(
        self,
        operation: str,
        parameters: dict[str, Any] | None = None,
    ) -> OperationResult:
        """Custom execution for EC2 with instance flattening."""
        result = await super().execute(operation, parameters)

        # Flatten instances from reservations for describe_instances
        if result.success and operation == "describe_instances":
            if isinstance(result.data, list):
                instances = []
                for reservation in result.data:
                    if isinstance(reservation, dict) and "Instances" in reservation:
                        instances.extend(reservation["Instances"])
                result.data = instances
                result.count = len(instances)

        return result

    def format_response(self, data: Any, format_type: str = "table") -> str:
        """Custom formatting for EC2 responses."""
        if format_type == "json":
            import json
            return json.dumps(data, indent=2, default=str)

        if isinstance(data, list) and data:
            first = data[0]
            # Format instances
            if "InstanceId" in first:
                return self._format_instances(data)
            # Format VPCs
            elif "VpcId" in first and "CidrBlock" in first:
                return self._format_vpcs(data)
            # Format security groups
            elif "GroupId" in first and "GroupName" in first:
                return self._format_security_groups(data)

        return super().format_response(data, format_type)

    def _format_instances(self, instances: list[dict[str, Any]]) -> str:
        """Format instance list."""
        lines = [
            "| Instance ID | Name | Type | State | Private IP |",
            "| ----------- | ---- | ---- | ----- | ---------- |",
        ]
        for inst in instances[:50]:
            inst_id = inst.get("InstanceId", "")
            name = self._get_tag(inst, "Name") or "-"
            inst_type = inst.get("InstanceType", "")
            state = inst.get("State", {}).get("Name", "")
            private_ip = inst.get("PrivateIpAddress", "-")
            lines.append(f"| {inst_id} | {name[:20]} | {inst_type} | {state} | {private_ip} |")

        if len(instances) > 50:
            lines.append(f"... and {len(instances) - 50} more instances")

        return "\n".join(lines)

    def _format_vpcs(self, vpcs: list[dict[str, Any]]) -> str:
        """Format VPC list."""
        lines = ["| VPC ID | CIDR | Name | Default |", "| ------ | ---- | ---- | ------- |"]
        for vpc in vpcs:
            vpc_id = vpc.get("VpcId", "")
            cidr = vpc.get("CidrBlock", "")
            name = self._get_tag(vpc, "Name") or "-"
            default = "Yes" if vpc.get("IsDefault") else "No"
            lines.append(f"| {vpc_id} | {cidr} | {name[:20]} | {default} |")
        return "\n".join(lines)

    def _format_security_groups(self, groups: list[dict[str, Any]]) -> str:
        """Format security group list."""
        lines = ["| Group ID | Name | VPC | Description |", "| -------- | ---- | --- | ----------- |"]
        for sg in groups[:50]:
            sg_id = sg.get("GroupId", "")
            name = sg.get("GroupName", "")[:20]
            vpc_id = sg.get("VpcId", "-")
            desc = sg.get("Description", "")[:30]
            lines.append(f"| {sg_id} | {name} | {vpc_id} | {desc} |")
        return "\n".join(lines)

    @staticmethod
    def _get_tag(resource: dict[str, Any], key: str) -> str | None:
        """Get a tag value from a resource."""
        for tag in resource.get("Tags", []):
            if tag.get("Key") == key:
                return tag.get("Value")
        return None


@register_service
class LambdaService(BaseService):
    """AWS Lambda service plugin."""

    @property
    def service_name(self) -> str:
        return "lambda"

    @property
    def display_name(self) -> str:
        return "AWS Lambda"

    def get_operations(self) -> list[OperationSpec]:
        return [
            OperationSpec(
                name="list_functions",
                description="List Lambda functions",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["MasterRegion", "FunctionVersion", "MaxItems"],
                supports_pagination=True,
                result_key="Functions",
            ),
            OperationSpec(
                name="get_function",
                description="Get details about a Lambda function",
                category=OperationCategory.READ,
                required_params=["FunctionName"],
                optional_params=["Qualifier"],
                supports_pagination=False,
            ),
            OperationSpec(
                name="get_function_configuration",
                description="Get configuration of a Lambda function",
                category=OperationCategory.READ,
                required_params=["FunctionName"],
                optional_params=["Qualifier"],
                supports_pagination=False,
            ),
            OperationSpec(
                name="list_versions_by_function",
                description="List versions of a Lambda function",
                category=OperationCategory.READ,
                required_params=["FunctionName"],
                optional_params=["MaxItems"],
                supports_pagination=True,
                result_key="Versions",
            ),
            OperationSpec(
                name="invoke",
                description="Invoke a Lambda function",
                category=OperationCategory.WRITE,
                required_params=["FunctionName"],
                optional_params=["InvocationType", "Payload", "Qualifier"],
                supports_pagination=False,
            ),
            OperationSpec(
                name="update_function_code",
                description="Update Lambda function code",
                category=OperationCategory.WRITE,
                required_params=["FunctionName"],
                optional_params=["ZipFile", "S3Bucket", "S3Key", "ImageUri"],
                supports_pagination=False,
            ),
            OperationSpec(
                name="delete_function",
                description="Delete a Lambda function",
                category=OperationCategory.DESTRUCTIVE,
                required_params=["FunctionName"],
                optional_params=["Qualifier"],
                supports_pagination=False,
            ),
        ]

    def format_response(self, data: Any, format_type: str = "table") -> str:
        """Custom formatting for Lambda responses."""
        if format_type == "json":
            import json
            return json.dumps(data, indent=2, default=str)

        if isinstance(data, list) and data and "FunctionName" in data[0]:
            return self._format_functions(data)

        return super().format_response(data, format_type)

    def _format_functions(self, functions: list[dict[str, Any]]) -> str:
        """Format function list."""
        lines = [
            "| Function Name | Runtime | Memory | Timeout | Last Modified |",
            "| ------------- | ------- | ------ | ------- | ------------- |",
        ]
        for fn in functions[:50]:
            name = fn.get("FunctionName", "")[:25]
            runtime = fn.get("Runtime", "-")
            memory = f"{fn.get('MemorySize', 0)} MB"
            timeout = f"{fn.get('Timeout', 0)}s"
            modified = fn.get("LastModified", "")[:19]
            lines.append(f"| {name} | {runtime} | {memory} | {timeout} | {modified} |")

        if len(functions) > 50:
            lines.append(f"... and {len(functions) - 50} more functions")

        return "\n".join(lines)


@register_service
class ECSService(BaseService):
    """Amazon ECS service plugin."""

    @property
    def service_name(self) -> str:
        return "ecs"

    @property
    def display_name(self) -> str:
        return "Amazon ECS"

    def get_operations(self) -> list[OperationSpec]:
        return [
            OperationSpec(
                name="list_clusters",
                description="List ECS clusters",
                category=OperationCategory.READ,
                required_params=[],
                optional_params=["maxResults"],
                supports_pagination=True,
                result_key="clusterArns",
            ),
            OperationSpec(
                name="describe_clusters",
                description="Describe ECS clusters",
                category=OperationCategory.READ,
                required_params=["clusters"],
                optional_params=["include"],
                supports_pagination=False,
                result_key="clusters",
            ),
            OperationSpec(
                name="list_services",
                description="List services in a cluster",
                category=OperationCategory.READ,
                required_params=["cluster"],
                optional_params=["maxResults", "launchType"],
                supports_pagination=True,
                result_key="serviceArns",
            ),
            OperationSpec(
                name="list_tasks",
                description="List tasks in a cluster",
                category=OperationCategory.READ,
                required_params=["cluster"],
                optional_params=["serviceName", "maxResults", "desiredStatus"],
                supports_pagination=True,
                result_key="taskArns",
            ),
            OperationSpec(
                name="describe_tasks",
                description="Describe ECS tasks",
                category=OperationCategory.READ,
                required_params=["cluster", "tasks"],
                optional_params=["include"],
                supports_pagination=False,
                result_key="tasks",
            ),
        ]
