"""Security denylist for AWS MCP Pro."""

from __future__ import annotations

# Operations that should NEVER be allowed via MCP regardless of safety mode.
# These operations are either:
# 1. Catastrophic (can destroy entire accounts/organizations)
# 2. Security-critical (can disable audit logging, security monitoring)
# 3. Billing-related (can incur unexpected costs)
# 4. Identity-related (can escalate privileges in unexpected ways)

DENYLIST: set[str] = {
    # === IAM - Identity and Access Management ===
    # Account-level operations
    "iam.delete_account_alias",
    "iam.delete_account_password_policy",
    "iam.update_account_password_policy",
    "iam.create_account_alias",
    # Service-linked roles (can break AWS services)
    "iam.delete_service_linked_role",
    # SAML/OIDC providers (can break SSO)
    "iam.delete_saml_provider",
    "iam.delete_open_id_connect_provider",
    # Credential reports (privacy)
    "iam.generate_credential_report",
    # === Organizations ===
    "organizations.leave_organization",
    "organizations.delete_organization",
    "organizations.remove_account_from_organization",
    "organizations.close_account",
    "organizations.delete_organizational_unit",
    # === CloudTrail - Audit Logging ===
    "cloudtrail.delete_trail",
    "cloudtrail.stop_logging",
    "cloudtrail.update_trail",  # Could redirect logs
    "cloudtrail.delete_event_data_store",
    # === GuardDuty - Security Monitoring ===
    "guardduty.delete_detector",
    "guardduty.disable_organization_admin_account",
    "guardduty.disassociate_from_administrator_account",
    "guardduty.disassociate_members",
    "guardduty.delete_members",
    # === Config - Compliance ===
    "config.delete_configuration_recorder",
    "config.stop_configuration_recorder",
    "config.delete_delivery_channel",
    # === SecurityHub ===
    "securityhub.disable_security_hub",
    "securityhub.delete_insight",
    "securityhub.disable_import_findings_for_product",
    # === KMS - Key Management ===
    "kms.schedule_key_deletion",
    "kms.disable_key",
    "kms.delete_alias",
    "kms.delete_imported_key_material",
    # === S3 - Storage (Account-level) ===
    "s3control.delete_public_access_block",
    "s3control.put_public_access_block",  # Could open buckets
    # Dangerous bucket operations
    "s3.delete_bucket_policy",
    "s3.put_bucket_policy",  # Could make bucket public
    "s3.put_bucket_acl",  # Could make bucket public
    "s3.delete_bucket_encryption",
    "s3.put_public_access_block",  # Bucket-level
    "s3.delete_public_access_block",
    # === EC2 - Compute ===
    # VPC Flow Logs (security monitoring)
    "ec2.delete_flow_logs",
    # Default VPC (can break things)
    "ec2.delete_default_vpc",
    "ec2.delete_default_subnet",
    # === RDS - Databases ===
    "rds.delete_db_cluster_snapshot",
    "rds.delete_db_snapshot",
    # Automated backups
    "rds.delete_db_instance_automated_backup",
    "rds.modify_db_cluster",  # Can disable deletion protection
    # === Backup ===
    "backup.delete_backup_vault",
    "backup.delete_backup_plan",
    "backup.delete_recovery_point",
    # === Route 53 ===
    "route53.delete_hosted_zone",
    "route53domains.delete_domain",
    "route53domains.transfer_domain_to_another_aws_account",
    # === ACM - Certificates ===
    "acm.delete_certificate",
    # === Secrets Manager ===
    "secretsmanager.delete_secret",  # Has recovery, but still dangerous
    # === Cost and Billing ===
    "ce.delete_cost_category_definition",
    "budgets.delete_budget",
    "cur.delete_report_definition",
    # === Service Quotas ===
    "service-quotas.delete_service_quota_increase_request_from_template",
    # === SSO / Identity Center ===
    "sso-admin.delete_instance",
    "sso-admin.delete_permission_set",
    "identitystore.delete_user",
    "identitystore.delete_group",
    # === RAM - Resource Access Manager ===
    "ram.delete_resource_share",
    "ram.disassociate_resource_share",
    # === Service Catalog ===
    "servicecatalog.delete_portfolio",
    "servicecatalog.delete_product",
    # === Control Tower ===
    "controltower.disable_control",
    "controltower.delete_landing_zone",
}

# Operations that require explicit double confirmation even in unrestricted mode
DOUBLE_CONFIRM_OPERATIONS: set[str] = {
    "ec2.terminate_instances",
    "rds.delete_db_instance",
    "rds.delete_db_cluster",
    "dynamodb.delete_table",
    "s3.delete_bucket",
    "lambda.delete_function",
    "ecs.delete_cluster",
    "eks.delete_cluster",
    "cloudformation.delete_stack",
    "elasticbeanstalk.terminate_environment",
}

# Operations to warn about (not blocked, but flagged)
WARN_OPERATIONS: set[str] = {
    "iam.attach_role_policy",
    "iam.attach_user_policy",
    "iam.put_role_policy",
    "iam.put_user_policy",
    "iam.create_access_key",
    "ec2.authorize_security_group_ingress",
    "ec2.authorize_security_group_egress",
    "s3.put_bucket_versioning",
    "rds.modify_db_instance",
    "lambda.update_function_configuration",
}


def is_operation_blocked(service: str, operation: str) -> bool:
    """Check if an operation is in the denylist."""
    key = f"{service.lower()}.{operation.lower()}"
    return key in DENYLIST


def requires_double_confirmation(service: str, operation: str) -> bool:
    """Check if an operation requires double confirmation."""
    key = f"{service.lower()}.{operation.lower()}"
    return key in DOUBLE_CONFIRM_OPERATIONS


def should_warn(service: str, operation: str) -> bool:
    """Check if an operation should trigger a warning."""
    key = f"{service.lower()}.{operation.lower()}"
    return key in WARN_OPERATIONS


def get_block_reason(service: str, operation: str) -> str | None:
    """Get the reason why an operation is blocked."""
    key = f"{service.lower()}.{operation.lower()}"
    if key not in DENYLIST:
        return None

    # Categorize the reason
    if "cloudtrail" in key or "guardduty" in key or "config" in key or "securityhub" in key:
        return "This operation could disable security monitoring or audit logging"
    elif "iam" in key and ("account" in key or "saml" in key or "oidc" in key):
        return "This operation could affect account-level identity configuration"
    elif "organizations" in key:
        return "This operation could affect your AWS Organization structure"
    elif "kms" in key:
        return "This operation could permanently destroy encryption keys"
    elif "backup" in key or "snapshot" in key:
        return "This operation could destroy backup data"
    elif "s3" in key and ("policy" in key or "acl" in key or "public" in key):
        return "This operation could change S3 bucket security settings"
    elif "route53" in key or "domain" in key:
        return "This operation could affect DNS configuration"
    else:
        return "This operation is blocked for security reasons"
