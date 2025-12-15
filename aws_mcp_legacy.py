#!/usr/bin/env python3
import os
import json
import asyncio
import sys
from typing import Dict, List, Optional, Union, Any

import boto3
import botocore
from botocore.exceptions import ClientError
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field


class RunAwsCodeInput(BaseModel):
    """Model for the run-aws-code tool input parameters."""
    reasoning: str = Field(..., description="The reasoning behind the code")
    code: str = Field(..., description="Your job is to answer questions about AWS environment by writing Javascript code using AWS SDK V2. The code must be adhering to a few rules:\n- Must be preferring promises over callbacks\n- Think step-by-step before writing the code, approach it logically\n- MUST written in Javascript (NodeJS) using AWS-SDK V2\n- Avoid hardcoded values like ARNs\n- Code written should be as parallel as possible enabling the fastest and the most optimal execution\n- Code should be handling errors gracefully, especially when doing multiple SDK calls\n- DO NOT require or import \"aws-sdk\", it is already available as \"AWS\" variable\n- Access to 3rd party libraries apart from \"aws-sdk\" is not allowed\n- Data returned from AWS-SDK must be returned as JSON containing only the minimal amount of data needed\n- Code MUST \"return\" a value: string, number, boolean or JSON object\n- When listing resources, ensure pagination is handled correctly\n- Format output as a table whenever possible for better readability\n- Return data as concisely as possible with no unnecessary details or explanations\n- Be direct and to the point in all responses\nBe concise, only return relevant data without explanation. Do not give advice or commentary. Only return what was explicitly asked for.")
    profileName: Optional[str] = Field(None, description="Name of the AWS profile to use")
    region: Optional[str] = Field(None, description="Region to use (if not provided, us-east-1 is used)")


class ListCredentialsInput(BaseModel):
    """Model for the list-credentials tool input parameters."""
    pass


class SelectProfileInput(BaseModel):
    """Model for the select-profile tool input parameters."""
    profile: str = Field(..., description="Name of the AWS profile to select")
    region: Optional[str] = Field(None, description="Region to use (if not provided, us-east-1 is used)")


# Create a FastMCP instance
server = FastMCP(name="aws-mcp")

# Initialize state
session = None
aws_region = "us-east-1"
active_profile = None
credentials_cache = {}


@server.tool("run-aws-code", 
            "Run AWS code")
async def run_aws_code(reasoning: str, code: str, profileName: Optional[str] = None, region: Optional[str] = None) -> str:
    """Run AWS operations directly using boto3.
    
    This method parses common AWS operations from the provided code and
    executes them using boto3. It's designed to be compatible with the 
    TypeScript version's interface while using Python's boto3 library.
    
    Args:
        reasoning: The reasoning behind the code
        code: The AWS operations to perform (JavaScript syntax is parsed)
        profileName: Optional AWS profile name to use
        region: Optional AWS region to use
        
    Returns:
        JSON string with execution results or error message
    """
    global active_profile, aws_region, session
    
    # First check if we have a profile selected
    if not active_profile and not profileName:
        # Get all profiles
        try:
            profiles = boto3.session.Session().available_profiles
            profiles_str = ", ".join(profiles) if profiles else "none"
            return json.dumps({
                "status": "error",
                "message": f"Please select a profile first using the 'select-profile' tool! Available profiles: {profiles_str}"
            })
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": f"Failed to list profiles: {str(e)}"
            })
            
    # If profileName is provided, update session
    if profileName:
        try:
            # Use the provided region or fall back to the global region
            region_to_use = region or aws_region
            session = boto3.session.Session(
                profile_name=profileName,
                region_name=region_to_use
            )
            active_profile = profileName
            if region:
                aws_region = region  # Update global region
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": f"Failed to use profile {profileName}: {str(e)}"
            })
    
    # Make sure we have a session
    if not session:
        try:
            session = boto3.session.Session(
                profile_name=active_profile,
                region_name=aws_region
            )
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": f"Failed to create session: {str(e)}"
            })
    
    # Parse and execute AWS operations based on the provided code
    try:
        # Format table function for better readability
        def format_as_table(data, headers=None):
            if not data or not isinstance(data, list) or len(data) == 0:
                return "[]"
            
            # Extract headers if not provided
            if not headers and isinstance(data[0], dict):
                headers = list(data[0].keys())
            
            if not headers:
                return json.dumps(data)
            
            # Calculate column widths (max 50 chars)
            col_widths = [len(h) for h in headers]
            for row in data:
                for i, h in enumerate(headers):
                    if isinstance(row, dict) and h in row:
                        val = str(row[h])
                        col_widths[i] = min(50, max(col_widths[i], len(val)))
            
            # Build table
            table = '| ' + ' | '.join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + ' |\n'
            table += '| ' + ' | '.join('-' * w for w in col_widths) + ' |\n'
            
            for row in data:
                if isinstance(row, dict):
                    table += '| ' + ' | '.join(str(row.get(h, '')).ljust(col_widths[i]) for i, h in enumerate(headers)) + ' |\n'
            
            return table
        
        # Convert datetime objects to strings for JSON serialization
        def clean_for_json(obj):
            if isinstance(obj, dict):
                return {k: clean_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_for_json(i) for i in obj]
            elif hasattr(obj, 'isoformat'):
                return obj.isoformat()
            else:
                return obj

        # Function to simplify AWS responses (removing ResponseMetadata, etc.)
        def simplify_aws_response(response):
            if isinstance(response, dict):
                # Remove common metadata keys
                simplified = {k: v for k, v in response.items() 
                             if k not in ['ResponseMetadata']}
                return simplified
            return response
        
        # Dynamic execution of boto3 operations based on the code
        code_lower = code.lower()
        
        # Parse the code to identify AWS service and operation
        # This is a simplified parser - in a production environment, you'd want a more robust approach
        
        # First, try to identify the AWS service
        services = {
            's3': ['s3', 'bucket'],
            'ec2': ['ec2', 'instance'],
            'lambda': ['lambda', 'function'],
            'iam': ['iam', 'role', 'user', 'policy'],
            'dynamodb': ['dynamodb', 'table'],
            'rds': ['rds', 'database'],
            'cloudformation': ['cloudformation', 'stack'],
            'cloudwatch': ['cloudwatch', 'metric', 'log'],
            'sns': ['sns', 'topic'],
            'sqs': ['sqs', 'queue'],
            'kms': ['kms', 'key'],
            'secretsmanager': ['secretsmanager', 'secret'],
            'ssm': ['ssm', 'parameter'],
            'route53': ['route53', 'domain', 'record'],
            'cloudfront': ['cloudfront', 'distribution'],
            'elasticbeanstalk': ['elasticbeanstalk', 'application'],
            'apigateway': ['apigateway', 'api', 'resource'],
            'ecs': ['ecs', 'cluster', 'service', 'task'],
            'sts': ['sts', 'token', 'identity'],
            'cognito': ['cognito', 'user', 'pool', 'identity'],
            'codebuild': ['codebuild', 'project', 'build'],
            'codecommit': ['codecommit', 'repository', 'commit'],
            'codepipeline': ['codepipeline', 'pipeline', 'execution'],
            'organizations': ['organizations', 'organization', 'account'],
            'guardduty': ['guardduty', 'detector', 'finding']
        }
        
        detected_service = None
        for service, keywords in services.items():
            if any(keyword in code_lower for keyword in keywords):
                detected_service = service
                break
        
        # Try to identify the operation (list, describe, get, etc.)
        operations = ['list', 'describe', 'get', 'create', 'update', 'delete', 'put']
        detected_operation = None
        operation_suffix = None
        
        for operation in operations:
            if operation in code_lower:
                detected_operation = operation
                # Try to find what comes after the operation
                idx = code_lower.find(operation)
                remaining = code_lower[idx + len(operation):].strip()
                # Extract the first word after the operation
                import re
                matches = re.findall(r'([a-z]+)', remaining)
                if matches:
                    operation_suffix = matches[0].capitalize()
                break
        
        # If we identified a service and operation, try to execute it
        if detected_service and detected_operation:
            try:
                # Create the proper boto3 client
                client = session.client(detected_service)
                
                # Construct the likely method name
                method_name = f"{detected_operation}_{operation_suffix}" if operation_suffix else None
                
                # If we couldn't determine the method name from the code, look for common patterns
                if not method_name or not hasattr(client, method_name.lower()):
                    # Common method names based on service and operation
                    common_methods = {
                        's3': {
                            'list': 'list_buckets',
                            'get': 'get_object',
                            'put': 'put_object'
                        },
                        'ec2': {
                            'describe': 'describe_instances',
                            'list': 'describe_instances'
                        },
                        'lambda': {
                            'list': 'list_functions',
                            'get': 'get_function'
                        },
                        'iam': {
                            'list': 'list_roles' if 'role' in code_lower else 'list_users'
                        },
                        'dynamodb': {
                            'list': 'list_tables',
                            'describe': 'describe_table'
                        },
                        'rds': {
                            'describe': 'describe_db_instances',
                            'list': 'describe_db_instances'
                        },
                        'cloudformation': {
                            'list': 'list_stacks',
                            'describe': 'describe_stacks'
                        }
                    }
                    
                    if detected_service in common_methods and detected_operation in common_methods[detected_service]:
                        method_name = common_methods[detected_service][detected_operation]
                
                # If we have a method name, try to call it
                if method_name and hasattr(client, method_name.lower()):
                    method = getattr(client, method_name.lower())
                    
                    # Execute the method without parameters
                    # In a production environment, you'd parse parameters from the code
                    result = method()
                    
                    # Clean up the result
                    cleaned_result = clean_for_json(simplify_aws_response(result))
                    
                    # Try to extract a list of items for table formatting
                    table_data = None
                    
                    # Look for common list patterns in AWS responses
                    list_keys = [key for key in cleaned_result.keys() 
                                if isinstance(cleaned_result[key], list) and key != 'ResponseMetadata']
                    
                    if list_keys:
                        # Use the first list we find
                        list_key = list_keys[0]
                        items = cleaned_result[list_key]
                        
                        if items and isinstance(items[0], dict):
                            # We found a list of dictionaries, use it for our table
                            table_data = items
                            # Get headers from the first item
                            headers = list(items[0].keys())
                            # Format as table
                            table = format_as_table(table_data, headers)
                            
                            return json.dumps({
                                "status": "success",
                                "profile": active_profile,
                                "region": aws_region,
                                "operation": method_name,
                                "result": cleaned_result,
                                "formatted_table": table
                            })
                    
                    # If we didn't find a list, just return the raw result
                    return json.dumps({
                        "status": "success",
                        "profile": active_profile,
                        "region": aws_region,
                        "operation": method_name,
                        "result": cleaned_result
                    })
            except Exception as e:
                return json.dumps({
                    "status": "error",
                    "error_type": type(e).__name__,
                    "message": str(e),
                    "attempted_operation": f"{detected_service}.{method_name if method_name else 'unknown'}"
                })
                        
        # If we couldn't determine both service and operation, or execution failed
        # Try some common predefined operations based on keywords
        
        # S3 operations
        if 'listbuckets' in code_lower or '.list_buckets' in code_lower or ('s3' in code_lower and 'bucket' in code_lower and ('list' in code_lower or 'get' in code_lower)):
            s3 = session.client('s3')
            buckets = s3.list_buckets()
            bucket_list = [{'Name': b['Name'], 'CreationDate': b['CreationDate'].strftime('%Y-%m-%d %H:%M:%S')} 
                          for b in buckets.get('Buckets', [])]
            
            table = format_as_table(bucket_list, ['Name', 'CreationDate'])
            
            return json.dumps({
                "status": "success",
                "profile": active_profile,
                "region": aws_region,
                "result": bucket_list,
                "formatted_table": table
            })
        
        # EC2 operations
        elif 'ec2' in code_lower and ('describeinstances' in code_lower or 'list' in code_lower and 'instances' in code_lower):
            ec2 = session.client('ec2')
            instances = ec2.describe_instances()
            
            instance_list = []
            for reservation in instances.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    name = 'Unknown'
                    for tag in instance.get('Tags', []):
                        if tag['Key'] == 'Name':
                            name = tag['Value']
                            break
                    
                    instance_list.append({
                        'InstanceId': instance.get('InstanceId', 'Unknown'),
                        'InstanceType': instance.get('InstanceType', 'Unknown'),
                        'State': instance.get('State', {}).get('Name', 'Unknown'),
                        'Name': name
                    })
            
            table = format_as_table(instance_list, ['InstanceId', 'Name', 'InstanceType', 'State'])
            
            return json.dumps({
                "status": "success",
                "profile": active_profile,
                "region": aws_region,
                "result": instance_list,
                "formatted_table": table
            })
        
        # Dynamic execution as a fallback - try to interpret the code directly
        # This is a very simplified approach - in a real-world system you would use
        # a more sophisticated parser
        
        # Identify a potential boto3 operation directly from the code
        import re
        boto3_operations = re.findall(r'(?:client|resource)\.([a-zA-Z0-9_]+)\(', code)
        if boto3_operations:
            operation = boto3_operations[0]
            
            # Try to extract the service name
            service_match = re.search(r'(?:(?:create_)?client|resource)\([\'"]([a-zA-Z0-9_-]+)[\'"]', code)
            if service_match:
                service_name = service_match.group(1)
                
                try:
                    client = session.client(service_name)
                    if hasattr(client, operation):
                        method = getattr(client, operation)
                        # Execute without arguments - in a production environment, you'd parse arguments
                        result = method()
                        
                        # Clean and return the result
                        cleaned_result = clean_for_json(simplify_aws_response(result))
                        
                        return json.dumps({
                            "status": "success",
                            "profile": active_profile,
                            "region": aws_region,
                            "service": service_name,
                            "operation": operation,
                            "result": cleaned_result
                        })
                except Exception as e:
                    return json.dumps({
                        "status": "error",
                        "error_type": type(e).__name__,
                        "message": str(e),
                        "attempted_operation": f"{service_name}.{operation}"
                    })
        
        # If all parsing attempts failed, return a helper message
        return json.dumps({
            "status": "parse_error",
            "profile": active_profile,
            "region": aws_region,
            "message": "Could not determine the exact AWS operation to perform. Please provide more specific code or try one of these formats:\n\n1. List S3 buckets\n2. List EC2 instances\n3. Describe ECS clusters\n4. Get Lambda functions\n\nFor best results, include both the AWS service name and the specific operation in your request.",
            "code": code  # Return the original code for reference
        })
    
    except Exception as e:
        # Handle AWS-specific errors
        if isinstance(e, botocore.exceptions.ClientError):
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            
            return json.dumps({
                "status": "error",
                "error_type": "AWS Client Error",
                "error_code": error_code,
                "error_message": error_message
            })
        
        # Handle other exceptions
        return json.dumps({
            "status": "error",
            "error_type": type(e).__name__,
            "message": str(e)
        })


@server.tool("list-credentials", 
            "List all AWS credentials/configs/profiles that are configured/usable on this machine")
async def list_credentials() -> str:
    """List available AWS credentials.
    
    Retrieves all AWS profiles configured on the system from
    ~/.aws/config and ~/.aws/credentials files.
    
    Returns:
        JSON string with the list of available profiles
    """
    try:
        # Get all profiles from ~/.aws/config and ~/.aws/credentials
        profiles = boto3.session.Session().available_profiles
        
        # Format as a table like in the TypeScript implementation
        if profiles:
            table = "| AWS Profile |\n| ----------- |\n"
            for profile in profiles:
                table += f"| {profile} |\n"
            
            return json.dumps({
                "status": "success",
                "formatted_table": table,
                "profiles": profiles,
                "count": len(profiles)
            })
        else:
            return json.dumps({
                "status": "warning",
                "message": "No AWS profiles found. You may need to configure AWS credentials.",
                "profiles": []
            })
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e)
        })


@server.tool("select-profile", 
            "Selects AWS profile to use for subsequent interactions. If needed, does SSO authentication")
async def select_profile(profile: str, region: Optional[str] = None) -> str:
    """Select an AWS profile to use.
    
    Creates a new boto3 session using the specified profile
    and validates the credentials by making a test API call.
    
    Args:
        profile: Name of the AWS profile to select
        region: Optional AWS region to use
        
    Returns:
        JSON string with the result of profile selection
    """
    global active_profile, aws_region, session
    
    try:
        # Check if the profile exists
        available_profiles = boto3.session.Session().available_profiles
        if profile not in available_profiles:
            profiles_str = ", ".join(available_profiles) if available_profiles else "none"
            return json.dumps({
                "status": "error",
                "message": f"Profile '{profile}' not found. Available profiles: {profiles_str}"
            })
            
        # Create a new session with the selected profile
        session = boto3.session.Session(
            profile_name=profile, 
            region_name=region or aws_region
        )
        
        # Save the active profile
        active_profile = profile
        
        # Update the region if provided
        if region:
            aws_region = region
        
        # Test the credentials by making a simple API call
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        
        return json.dumps({
            "status": "success", 
            "profile": profile, 
            "region": aws_region,
            "account_id": identity["Account"],
            "user_id": identity["UserId"]
        })
    except ClientError as e:
        # Handle AWS-specific errors (like expired credentials)
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))
        
        # Check if this is an SSO profile that might need authentication
        if error_code in ['ExpiredToken', 'AccessDenied']:
            # While we can't implement full SSO here, we can provide guidance
            return json.dumps({
                "status": "error", 
                "error_type": "AWS Client Error",
                "error_code": error_code,
                "error_message": f"{error_message}. If this is an SSO profile, please run 'aws sso login --profile {profile}' in your terminal and try again."
            })
        
        return json.dumps({
            "status": "error", 
            "error_type": "AWS Client Error",
            "error_code": error_code,
            "error_message": error_message
        })
    except Exception as e:
        # Handle other exceptions
        return json.dumps({
            "status": "error",
            "error_type": type(e).__name__,
            "message": str(e)
        })


# Add CLI command handling
def run_cli():
    """Run the AWS MCP as a CLI application"""
    import argparse
    
    parser = argparse.ArgumentParser(description="AWS MCP CLI - AWS operations from your command line")
    # Add format flag to main parser
    parser.add_argument("--format", choices=["json", "pretty"], default="json",
                       help="Output format (json or pretty-printed)")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # List credentials command
    list_creds_parser = subparsers.add_parser("list-credentials", help="List available AWS profiles")
    list_creds_parser.description = "List all AWS credentials/profiles configured on this machine"
    
    # Select profile command
    select_profile_parser = subparsers.add_parser("select-profile", help="Select an AWS profile to use")
    select_profile_parser.description = "Select an AWS profile to use for subsequent operations"
    select_profile_parser.add_argument("profile", help="Name of the AWS profile to select")
    select_profile_parser.add_argument("--region", help="AWS region to use (defaults to us-east-1)")
    
    # Run AWS code command
    run_code_parser = subparsers.add_parser("run-aws-code", help="Run AWS operations")
    run_code_parser.description = """
    Run AWS operations using natural language or code-like syntax.
    
    Examples:
      python -m aws_mcp run-aws-code "list all S3 buckets"
      python -m aws_mcp run-aws-code "describe EC2 instances" --profile myprofile
      python -m aws_mcp run-aws-code "get Lambda functions" --region us-west-2
    """
    run_code_parser.add_argument("--reasoning", default="CLI execution", help="Reasoning for the operation")
    run_code_parser.add_argument("code", help="AWS operation to perform (in natural language or code-like syntax)")
    run_code_parser.add_argument("--profile", help="AWS profile to use")
    run_code_parser.add_argument("--region", help="AWS region to use (defaults to us-east-1)")
    
    # Parse arguments
    args = parser.parse_args()
    
    # If no command specified, show help
    if not args.command:
        parser.print_help()
        return
    
    # Get format argument
    output_format = "pretty" if args.format == "pretty" else "json"
    
    if args.command == "list-credentials":
        result = asyncio.run(list_credentials())
        if args.format == "pretty":
            result_obj = json.loads(result)
            print(json.dumps(result_obj, indent=2))
        else:
            print(result)
    elif args.command == "select-profile":
        region = args.region if hasattr(args, "region") else None
        result = asyncio.run(select_profile(args.profile, region))
        if args.format == "pretty":
            result_obj = json.loads(result)
            print(json.dumps(result_obj, indent=2))
        else:
            print(result)
    elif args.command == "run-aws-code":
        profile = args.profile if hasattr(args, "profile") else None
        region = args.region if hasattr(args, "region") else None
        result = asyncio.run(run_aws_code(args.reasoning, args.code, profile, region))
        if args.format == "pretty":
            result_obj = json.loads(result)
            print(json.dumps(result_obj, indent=2))
        else:
            print(result)

# When running directly as a script, run as CLI or start the server in stdio mode
if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_cli()
    else:
        # Default to running the server in stdio mode if no arguments provided
        asyncio.run(server.run_stdio_async())