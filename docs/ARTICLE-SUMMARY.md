# AWS Sage: Bringing Intelligence to AWS Automation

*A unified Model Context Protocol server that transforms how AI assistants interact with AWS*

---

## The Problem with Current Solutions

The Model Context Protocol (MCP) ecosystem has exploded in 2025, with over 5,800 servers and 97 million monthly SDK downloads. AWS integration is among the most requested capabilities—yet existing solutions force developers to choose between fragmentation and limited functionality.

**AWS Labs' approach**: 15 separate MCP servers, each requiring individual configuration. Want to find all resources tagged "production"? You'll need to query multiple servers and correlate results manually.

**Community alternatives**: Single-purpose servers that wrap AWS CLI commands or provide basic API access, but lack the intelligence to understand your infrastructure holistically.

---

## A Different Approach

AWS Sage takes a fundamentally different stance: **one unified server with 30 intelligent tools** that understand AWS as a connected system, not isolated services.

Instead of asking "which S3 buckets exist?" across one server and "which Lambda functions exist?" across another, you simply ask:

```
"Find all resources tagged Environment=production"
```

The server queries EC2, RDS, Lambda, S3, DynamoDB, and more—returning a unified view of your infrastructure.

---

## What Makes It Intelligent

### Cross-Service Understanding

Traditional MCP servers answer: "Here are your EC2 instances."

AWS Sage answers: "Here are your EC2 instances, and here's what each one connects to—the security groups, IAM roles, and dependent services."

**Dependency Mapping**:
```
"What does my payment-processor Lambda depend on?"
```
Response: VPC subnet, security group, IAM role with S3/DynamoDB access, Secrets Manager secret, KMS key.

**Impact Analysis**:
```
"What breaks if I delete sg-abc123?"
```
Response: 3 EC2 instances, 2 Lambda functions, and 1 RDS instance currently use this security group. Deletion will cause immediate failures.

### Automated Incident Investigation

When something breaks at 2 AM, you don't want to manually check CloudWatch logs, then metrics, then configuration. AWS Sage's investigation workflows do this automatically:

```
"Investigate why my order-processor Lambda is failing"
```

The server checks invocation errors, examines recent logs, reviews memory/timeout settings, traces downstream dependencies, and presents findings—all in one response.

### Built-In Cost Intelligence

No separate cost analysis server needed. Ask directly:

```
"Find idle resources in us-east-1"
"Get rightsizing recommendations for EC2"
"Project costs for 3 t3.large instances running 24/7"
```

---

## Enterprise-Ready Safety

Three safety modes protect your infrastructure:

| Mode | Purpose |
|------|---------|
| **READ_ONLY** | Investigation and exploration—no changes possible |
| **STANDARD** | Normal operations with confirmation required |
| **UNRESTRICTED** | Full access for automation pipelines |

Beyond modes, 70+ critical operations are **always blocked**, regardless of mode:
- `cloudtrail.delete_trail` / `stop_logging`
- `organizations.leave_organization`
- `guardduty.delete_detector`
- `kms.schedule_key_deletion`

---

## Local Development with LocalStack

Develop and test locally without touching production. AWS Sage integrates natively with LocalStack:

```
"Switch to localstack environment"
"Create test S3 bucket in localstack"
"Compare DynamoDB tables between localstack and production"
```

---

## Multi-Account Support

Enterprise environments span multiple AWS accounts. AWS Sage handles this natively:

```
"Assume role arn:aws:iam::123456789012:role/AdminRole"
"Switch to production account"
"List resources in staging account"
```

Cross-account operations include clear warnings and audit logging.

---

## How It Compares

| Capability | AWS Labs (15 servers) | AWS Sage (1 server) |
|------------|----------------------|------------------------|
| Cross-service discovery | ❌ | ✅ |
| Dependency mapping | ❌ | ✅ |
| Impact analysis | ❌ | ✅ |
| Incident investigation | ❌ | ✅ |
| Cost analysis | Separate server | ✅ Built-in |
| LocalStack integration | ❌ | ✅ |
| Multi-account | ❌ | ✅ |
| Safety controls | Basic | 3-tier + denylist |
| Configuration complexity | High (15 configs) | Low (1 config) |

---

## Technical Foundation

Built on FastMCP with Python 3.11+, AWS Sage provides:

- **30 tools** across 10 categories
- **145 unit tests** with comprehensive coverage
- **Docker support** for container isolation
- **Natural language parsing** for intuitive queries
- **Auto-pagination** so you never miss resources
- **Smart formatting** (tables for lists, JSON for details)

---

## Getting Started

### Docker (Recommended)
```json
{
  "mcpServers": {
    "aws-mcp": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-v", "~/.aws:/home/appuser/.aws:ro", "aws-sage:latest"]
    }
  }
}
```

### Direct Installation
```bash
pip install aws-sage
```

---

## The Bigger Picture

As AI assistants become standard development tools, the quality of their integrations matters. A fragmented approach—15 servers for 15 services—creates cognitive overhead and limits what's possible.

AWS Sage demonstrates that MCP servers can be more than API wrappers. They can embody domain knowledge, understand relationships, predict impacts, and guide operations safely.

For teams managing non-trivial AWS infrastructure, this intelligence isn't a nice-to-have—it's what separates "show me the instances" from "help me understand my infrastructure."

---

## Project Information

- **Repository**: github.com/arunsanna/aws-sage
- **License**: MIT
- **Version**: 0.4.0
- **Contact**: arun.sanna@outlook.com

---

*AWS Sage is open source and welcomes contributions. Whether you're adding service support, improving safety controls, or enhancing investigation workflows—the goal is building the most intelligent AWS MCP server available.*
