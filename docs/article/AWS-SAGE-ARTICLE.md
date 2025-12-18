# AWS Sage: Bringing Intelligence to Cloud Infrastructure Automation

**How a unified Model Context Protocol server transforms AI-assisted AWS operations**

*By Arun Sanna | December 2025*

> **Open Source Repository**: [github.com/arunsanna/aws-sage](https://github.com/arunsanna/aws-sage)
>
> **License**: MIT | **Version**: 1.0.0 | **Language**: Python 3.11+

---

## Abstract

As artificial intelligence assistants become integral to software development workflows, their ability to interact with cloud infrastructure becomes critical. This article introduces AWS Sage, an open-source Model Context Protocol (MCP) server that provides unified, intelligent access to Amazon Web Services. Unlike existing solutions that fragment AWS services across multiple servers, AWS Sage offers cross-service intelligence including dependency mapping, impact analysis, and automated incident investigation—capabilities previously unavailable in the MCP ecosystem.

---

## 1. Introduction: The Rise of AI-Assisted Cloud Operations

The Model Context Protocol, introduced by Anthropic in late 2024, has rapidly transformed how AI assistants interact with external tools and data sources. By providing a standardized interface between AI models and software systems, MCP enables assistants like Claude, ChatGPT, and others to perform real-world tasks rather than merely generating text.

![MCP Ecosystem Statistics 2025](../images/mcp-ecosystem-stats.png)
*Figure 1: The MCP ecosystem has grown to over 5,800 servers with 97 million monthly SDK downloads, representing a $1.8 billion market in 2025.*

The numbers tell a compelling story: over 5,800 MCP servers exist today, with 97 million monthly SDK downloads. Major technology companies including Block, Apollo, Replit, Codeium, and Sourcegraph have adopted MCP for their AI integrations. Industry analysts project 90% enterprise adoption by 2026.

Within this ecosystem, AWS integration remains one of the most sought-after capabilities. Amazon Web Services powers approximately 32% of global cloud infrastructure, and engineers working with AWS spend significant time on routine tasks: discovering resources, understanding dependencies, investigating incidents, and optimizing costs. AI assistants capable of performing these tasks intelligently could dramatically improve productivity.

Yet existing AWS MCP solutions present significant limitations.

---

## 2. The Problem: Fragmentation and Limited Intelligence

### 2.1 The Official Approach: 15 Servers for 15 Services

AWS Labs, Amazon's official open-source organization, offers MCP integration through a distributed model: separate servers for S3, EC2, Lambda, RDS, CloudWatch, Cost Analysis, and ten other services. Each server requires individual configuration in the AI assistant's settings.

```json
{
  "mcpServers": {
    "aws-s3": { "command": "uvx", "args": ["awslabs.s3-mcp-server@latest"] },
    "aws-ec2": { "command": "uvx", "args": ["awslabs.ec2-mcp-server@latest"] },
    "aws-lambda": { "command": "uvx", "args": ["awslabs.lambda-mcp-server@latest"] },
    "aws-rds": { "command": "uvx", "args": ["awslabs.rds-mcp-server@latest"] }
  }
}
```

This approach creates several challenges:

1. **Configuration Complexity**: Each service requires separate setup and maintenance
2. **No Cross-Service Queries**: Finding all resources tagged "production" requires querying multiple servers and correlating results manually
3. **No Relationship Awareness**: The EC2 server doesn't know which Lambda functions connect to which instances
4. **Duplicate Effort**: Common patterns like pagination handling must be implemented per server

### 2.2 Community Alternatives

Community-developed solutions attempt to address fragmentation but introduce other limitations:

**alexei-led/aws-mcp-server** wraps AWS CLI commands in Docker containers, providing security isolation but limiting functionality to CLI capabilities and introducing shell execution overhead.

**RafalWilinski/aws-mcp** offers a TypeScript implementation with broader service coverage but relies on the deprecated AWS SDK v2 (end-of-life 2025) and lacks advanced features.

Neither solution provides the intelligence layer that modern cloud operations demand.

---

## 3. AWS Sage: A Unified Intelligence Layer

AWS Sage takes a fundamentally different approach: rather than wrapping individual AWS APIs, it provides an intelligence layer that understands AWS as a connected system.

![Architecture Comparison](../images/architecture-comparison.png)
*Figure 2: AWS Labs distributes functionality across 15 separate servers, while AWS Sage consolidates everything into a single unified server with a cross-service intelligence layer.*

### 3.1 Architecture

The unified architecture centers on a single FastMCP server exposing 30 tools across 10 categories:

![Tool Categories](../images/tool-categories.png)
*Figure 3: AWS Sage's 30 tools organized across 10 functional categories, from credential management to cost analysis.*

| Category | Tools | Purpose |
|----------|-------|---------|
| Credential Management | 3 | Profile and SSO authentication |
| Safety Controls | 1 | Three-tier safety mode switching |
| Query Operations | 2 | Natural language queries with validation |
| Execute Operations | 1 | Confirmed write operations |
| Context & Memory | 3 | Aliases and conversation history |
| Cross-Service Intelligence | 4 | Discovery, dependencies, impact, incidents |
| AWS Knowledge | 4 | Documentation and best practices |
| Cost Analysis | 4 | Idle resources, rightsizing, projections |
| Environment Management | 5 | LocalStack integration |
| Multi-Account | 3 | Cross-account operations |

### 3.2 Natural Language Interface

Rather than requiring precise API call specifications, users interact through natural language:

```
"List all S3 buckets"
"Show EC2 instances tagged Environment=production in us-west-2"
"Describe the payment-processor Lambda function"
"Find resources owned by team-platform"
```

The parser classifies intent, maps to appropriate AWS operations, handles pagination automatically, and formats results appropriately (tables for lists, detailed JSON for single resources).

---

## 4. Cross-Service Intelligence: The Key Differentiator

The most significant innovation in AWS Sage lies in its cross-service intelligence capabilities—features unavailable in any competing solution.

### 4.1 Resource Discovery

Traditional approach:
- Query S3 server for buckets with tag
- Query EC2 server for instances with tag
- Query Lambda server for functions with tag
- Manually correlate results

AWS Sage approach:
```
"Find all resources tagged Environment=production"
```

A single query searches across EC2, RDS, Lambda, S3, DynamoDB, ECS, and more, returning a unified inventory.

### 4.2 Dependency Mapping

Understanding resource relationships is critical for operations:

```
"What does my payment-processor Lambda depend on?"
```

Response includes:
- VPC subnet and security group
- IAM execution role with attached policies
- S3 buckets accessed
- DynamoDB tables queried
- Secrets Manager secrets referenced
- KMS keys used for encryption

This information, previously requiring manual investigation across multiple consoles, arrives in seconds.

### 4.3 Impact Analysis

Before modifying or deleting resources, understanding downstream effects prevents outages:

```
"What breaks if I delete sg-abc123?"
```

AWS Sage traces all resources using the security group:
- 3 EC2 instances (i-xxx, i-yyy, i-zzz)
- 2 Lambda functions in VPC (payment-processor, order-validator)
- 1 RDS instance (production-db)

The response explicitly warns: "Deletion will immediately terminate network connectivity for these resources."

### 4.4 Automated Incident Investigation

When production issues occur, manual investigation follows a predictable pattern: check logs, review metrics, examine configuration, trace dependencies. AWS Sage automates this workflow:

![Incident Investigation Workflow](../images/incident-workflow.png)
*Figure 4: AWS Sage's automated incident investigation workflow consolidates multiple investigation steps into a single query response.*

```
"Investigate why my order-processor Lambda is failing"
```

The server automatically:
1. Retrieves recent CloudWatch Logs for errors
2. Checks invocation success/failure metrics
3. Reviews memory utilization and timeout configuration
4. Examines IAM role permissions
5. Tests VPC connectivity and security group rules
6. Traces downstream service dependencies

Findings arrive consolidated, replacing what previously required 20-30 minutes of manual investigation.

---

## 5. Enterprise Safety Controls

Operating against production AWS accounts requires robust safety mechanisms. AWS Sage implements a three-tier safety system:

![Safety System](../images/safety-system.png)
*Figure 5: AWS Sage's three-tier safety system with 70+ always-blocked critical operations.*

### 5.1 Safety Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `READ_ONLY` | No write operations permitted | Investigation, audits, exploration |
| `STANDARD` | Writes require explicit confirmation | Normal daily operations |
| `UNRESTRICTED` | Full access (except denylist) | CI/CD automation |

### 5.2 Operation Denylist

Regardless of safety mode, 70+ critical operations remain permanently blocked:

- `cloudtrail.delete_trail` / `stop_logging` — Audit trail protection
- `iam.delete_account_password_policy` — Security policy protection
- `organizations.leave_organization` — Organization integrity
- `guardduty.delete_detector` — Threat detection protection
- `kms.schedule_key_deletion` — Encryption key protection
- `rds.delete_db_cluster_snapshot` — Backup protection

This defense-in-depth approach ensures that even with `UNRESTRICTED` mode enabled for automation, catastrophic operations cannot execute.

---

## 6. Development and Testing: LocalStack Integration

Production safety extends beyond access controls. AWS Sage integrates natively with LocalStack, enabling complete local development workflows:

```
"Switch to localstack environment"
"Create test bucket my-test-bucket"
"Verify DynamoDB table schema"
"Compare Lambda functions between localstack and production"
```

The environment comparison feature particularly aids deployment verification:

```
"Compare S3 buckets between localstack and production"
```

Response highlights:
- Buckets only in localstack (test artifacts)
- Buckets only in production (missing from local setup)
- Configuration differences between matching buckets

---

## 7. Multi-Account Support

Enterprise AWS deployments span multiple accounts: development, staging, production, security, logging. AWS Sage manages these natively:

```
"Assume role arn:aws:iam::123456789012:role/AdminRole"
"Switch to production account"
"List EC2 instances in staging"
```

Cross-account operations include:
- Clear visual indicators of active account
- Explicit warnings when switching to production
- Automatic credential refresh for assumed roles
- Audit logging for account transitions

---

## 8. Competitive Analysis

![Feature Comparison](../images/feature-comparison.png)
*Figure 6: Feature comparison across AWS MCP solutions shows AWS Sage's comprehensive coverage.*

| Capability | AWS Labs | alexei-led | RafalWilinski | AWS Sage |
|------------|----------|------------|---------------|-------------|
| Architecture | 15 servers | 1 server | 1 server | 1 server |
| Cross-service discovery | No | No | No | **Yes** |
| Dependency mapping | No | No | No | **Yes** |
| Impact analysis | No | No | No | **Yes** |
| Incident investigation | No | No | No | **Yes** |
| Cost analysis | Separate server | No | No | **Built-in** |
| LocalStack integration | No | No | No | **Yes** |
| Multi-account | No | No | No | **Yes** |
| Safety controls | Basic | Container | Basic | **3-tier + denylist** |
| Natural language | Limited | No | Limited | **Full NLP** |
| Test coverage | Varies | Unknown | Unknown | **145 tests** |

---

## 9. Technical Implementation

### 9.1 Technology Stack

- **Language**: Python 3.11+
- **Framework**: FastMCP (Model Context Protocol SDK)
- **AWS SDK**: boto3/botocore (current, maintained)
- **Transport**: stdio (standard MCP transport)
- **Container**: Docker (optional, recommended)

### 9.2 Quality Metrics

| Metric | Value |
|--------|-------|
| Unit Tests | 145 passing |
| Tools | 30 across 10 categories |
| Module Coverage | 29 modules |
| Code Quality | ruff verified |

### 9.3 Installation

**Docker (Recommended)**:
```json
{
  "mcpServers": {
    "aws-sage": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-v", "~/.aws:/home/appuser/.aws:ro",
        "-e", "AWS_PROFILE=default",
        "aws-sage:latest"
      ]
    }
  }
}
```

**Direct Installation**:
```bash
pip install aws-sage
```

---

## 10. Use Cases and Examples

### 10.1 Daily Operations

```
"List all running EC2 instances"
"Show S3 buckets larger than 100GB"
"Get IAM users without MFA enabled"
```

### 10.2 Cost Optimization

```
"Find idle resources in us-east-1"
"Get rightsizing recommendations for EC2"
"Project monthly cost for 5 t3.large instances"
```

### 10.3 Security Investigation

```
"Show security groups with 0.0.0.0/0 ingress"
"Find Lambda functions with admin IAM policies"
"List resources not encrypted with KMS"
```

### 10.4 Incident Response

```
"Investigate high latency on alb-production"
"Debug Lambda timeout errors for payment-processor"
"Analyze CloudWatch alarms triggered in last hour"
```

---

## 11. Future Directions

The roadmap for AWS Sage includes:

- **CloudFormation Drift Detection**: Compare deployed resources against template definitions
- **Custom Workflow Definitions**: User-defined investigation and automation workflows
- **Terraform State Integration**: Cross-reference with infrastructure-as-code state
- **Cost Anomaly Detection**: Proactive alerts for unexpected spending patterns
- **Compliance Scanning**: Check resources against CIS benchmarks and custom policies

---

## 12. Conclusion

The Model Context Protocol represents a fundamental shift in how AI assistants interact with software systems. For cloud operations—where engineers spend significant time on routine discovery, investigation, and optimization tasks—intelligent MCP servers offer substantial productivity improvements.

AWS Sage demonstrates that MCP servers can be more than API wrappers. By understanding AWS as a connected system rather than isolated services, it provides capabilities impossible with distributed architectures: cross-service discovery, dependency mapping, impact analysis, and automated incident investigation.

For teams managing non-trivial AWS infrastructure, these capabilities transform "show me the instances" queries into "help me understand and operate my infrastructure" conversations.

---

## About the Author

**Arun Sanna** is a software engineer focused on cloud infrastructure automation and AI-assisted development tools. AWS Sage is open source under the MIT license at github.com/arunsanna/aws-sage.

**Contact**: arun.sanna@outlook.com

---

## References

1. Anthropic. "Model Context Protocol Specification." 2024. https://modelcontextprotocol.io
2. AWS Labs. "AWS MCP Servers." 2025. https://github.com/awslabs/mcp
3. FastMCP. "FastMCP Documentation." 2025. https://github.com/jlowin/fastmcp
4. LocalStack. "LocalStack Documentation." 2025. https://localstack.cloud

---

*AWS Sage v1.0.0 | MIT License | December 2025*
