# AWS MCP Pro

A production-grade [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server for AWS that goes beyond basic API wrappers. Built for AI assistants like Claude to intelligently interact with AWS environments through natural language.

## Why AWS MCP Pro?

AWS Labs offers [15 separate MCP servers](https://github.com/awslabs/mcp) for different services. AWS MCP Pro takes a different approach:

| Feature | AWS Labs MCP | AWS MCP Pro |
|---------|--------------|-------------|
| **Architecture** | 15 separate servers | 1 unified server |
| **Tools** | ~45 tools across servers | 18 intelligent tools |
| **Cross-Service Queries** | No | Yes - discover resources across all services |
| **Dependency Mapping** | No | Yes - "what depends on this resource?" |
| **Impact Analysis** | No | Yes - "what breaks if I delete this?" |
| **Incident Investigation** | No | Yes - automated troubleshooting workflows |
| **Safety System** | Basic | 3-tier with 70+ blocked operations |
| **Natural Language** | Limited | Full NLP with intent classification |
| **Validation** | Runtime errors | Pre-execution validation via botocore |

## Features

### Core Capabilities
- **Natural Language Queries**: "Show me EC2 instances tagged production"
- **Multi-Profile Support**: Switch between AWS profiles with SSO support
- **Auto-Pagination**: Never miss resources due to pagination limits
- **Smart Formatting**: Tabular output for lists, detailed JSON for single resources

### Safety System
Three safety modes protect your infrastructure:

| Mode | Description | Operations Allowed |
|------|-------------|-------------------|
| `READ_ONLY` | Default - exploration only | list, describe, get |
| `STANDARD` | Normal operations | read + write (with confirmation) |
| `UNRESTRICTED` | Full access | all except denylist |

**Always Blocked** (70+ operations):
- `cloudtrail.delete_trail` / `stop_logging`
- `iam.delete_account_password_policy`
- `organizations.leave_organization`
- `guardduty.delete_detector`
- `kms.schedule_key_deletion`
- And 65+ more critical operations

### Unique Differentiators

#### Cross-Service Resource Discovery
Find resources across your entire AWS account:
```
"Find all resources tagged Environment=production"
"Discover resources with Name containing api"
```

#### Dependency Mapping
Understand resource relationships:
```
"What resources does my Lambda function depend on?"
"Map dependencies for my ECS service"
```

#### Impact Analysis
Know what breaks before you delete:
```
"What will break if I delete this security group?"
"Show impact of removing this IAM role"
```

#### Incident Investigation
Automated troubleshooting workflows:
```
"Investigate why my Lambda is failing"
"Debug high latency on my ALB"
"Analyze this security alert"
```

## Installation

### Prerequisites
- Python 3.11+
- AWS credentials configured (`~/.aws/`)
- [Claude Desktop](https://claude.ai/download) or Claude Code

### Install from Source

```bash
git clone https://github.com/arunsanna/aws-sage
cd aws-sage
pip install -e .
```

### Configure Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "aws-mcp": {
      "command": "/path/to/python",
      "args": ["-m", "aws_mcp.server"],
      "env": {
        "AWS_PROFILE": "default"
      }
    }
  }
}
```

**Find your Python path:**
```bash
which python3
```

**Config file locations:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

## Tools Reference

### Credential Management

| Tool | Description |
|------|-------------|
| `list_profiles` | List available AWS profiles |
| `select_profile` | Select and authenticate with a profile |
| `get_account_info` | Show current account ID, region, identity |

### Safety Controls

| Tool | Description |
|------|-------------|
| `set_safety_mode` | Switch between READ_ONLY, STANDARD, UNRESTRICTED |

### Query Operations (Read-Only)

| Tool | Description |
|------|-------------|
| `aws_query` | Natural language AWS queries |
| `validate_operation` | Check if an operation is valid without executing |

### Execute Operations (Require Confirmation)

| Tool | Description |
|------|-------------|
| `aws_execute` | Execute validated AWS operations |

### Context & Memory

| Tool | Description |
|------|-------------|
| `get_context` | View conversation context and recent resources |
| `set_alias` | Create shortcuts for resources (e.g., "prod-db") |
| `list_aliases` | View all defined aliases |

### Cross-Service Intelligence

| Tool | Description |
|------|-------------|
| `discover_resources` | Find resources by tags across all services |
| `map_dependencies` | Show what a resource depends on |
| `impact_analysis` | Predict what breaks if you modify/delete something |
| `investigate_incident` | Automated incident investigation workflows |

### AWS Knowledge (Composition)

| Tool | Description |
|------|-------------|
| `search_docs` | Search AWS documentation |
| `get_aws_knowledge` | Query built-in AWS knowledge base |
| `get_best_practices` | Get service-specific best practices |
| `get_service_limits` | Show default service quotas |

## Usage Examples

### Basic Queries

```
"List all S3 buckets"
"Show EC2 instances in us-west-2"
"Describe Lambda function payment-processor"
"Get IAM users with console access"
```

### Cross-Service Discovery

```
"Find all resources tagged with Environment=production"
"Discover resources owned by team-platform"
"Show all resources in the payment-service stack"
```

### Dependency Analysis

```
"What does my api-gateway Lambda depend on?"
"Map all dependencies for the checkout-service ECS task"
"Show resources connected to vpc-abc123"
```

### Impact Analysis

```
"What breaks if I delete sg-abc123?"
"Impact of terminating this RDS instance"
"What depends on this KMS key?"
```

### Incident Investigation

```
"Investigate Lambda failures for order-processor"
"Debug high latency: ALB arn:aws:elasticloadbalancing:..."
"Analyze security alert for instance i-abc123"
```

### Safety Mode Management

```
"Switch to standard mode to make changes"
"Enable unrestricted mode for maintenance"
"Return to read-only mode"
```

## Architecture

```
aws-mcp/
├── src/aws_mcp/
│   ├── server.py              # FastMCP server (18 tools)
│   ├── config.py              # Configuration & safety modes
│   │
│   ├── core/
│   │   ├── session.py         # AWS session management
│   │   ├── context.py         # Conversation memory
│   │   └── exceptions.py      # Custom exceptions
│   │
│   ├── safety/
│   │   ├── classifier.py      # Operation classification
│   │   ├── validator.py       # Pre-execution validation
│   │   └── denylist.py        # Blocked operations (70+)
│   │
│   ├── parser/
│   │   ├── intent.py          # NLP intent classification
│   │   └── service_models.py  # Botocore integration
│   │
│   ├── execution/
│   │   ├── engine.py          # Execution orchestrator
│   │   └── pagination.py      # Auto-pagination
│   │
│   ├── services/
│   │   └── registry.py        # Service plugin system
│   │
│   ├── composition/
│   │   ├── docs_proxy.py      # AWS documentation
│   │   └── knowledge_proxy.py # AWS knowledge base
│   │
│   └── differentiators/
│       ├── discovery.py       # Cross-service discovery
│       ├── dependencies.py    # Dependency mapping
│       └── workflows.py       # Incident investigation
│
└── tests/
    ├── unit/                  # Unit tests (83 tests)
    └── integration/           # Integration tests
```

## Development

### Setup

```bash
git clone https://github.com/arunsanna/aws-sage
cd aws-sage
pip install -e ".[dev]"
```

### Run Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=aws_mcp

# Specific module
pytest tests/unit/test_safety.py -v
```

### Run Server Locally

```bash
# Using FastMCP dev mode
fastmcp dev src/aws_mcp/server.py

# Or directly
python -m aws_mcp.server
```

## Troubleshooting

### View Logs

```bash
# Claude Desktop logs
tail -f ~/Library/Logs/Claude/mcp-server-aws-mcp.log
tail -f ~/Library/Logs/Claude/mcp.log
```

### Common Issues

**"Profile not found"**
- Ensure AWS credentials are configured in `~/.aws/credentials` or `~/.aws/config`
- For SSO profiles, run `aws sso login --profile <name>` first

**"Operation blocked"**
- Check current safety mode with `get_account_info`
- Use `set_safety_mode` to change if needed
- Some operations are always blocked (see denylist)

**"Validation failed"**
- The parser validates operations against botocore models
- Check spelling of service/operation names
- Use `validate_operation` to test before executing

## Roadmap

- [ ] LocalStack integration for local development
- [ ] Cost optimization analyzer
- [ ] CloudFormation drift detection
- [ ] Multi-account support
- [ ] Custom workflow definitions

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](./LICENSE) for details.

## Contact

- GitHub Issues: [arunsanna/aws-sage](https://github.com/arunsanna/aws-sage/issues)
- Email: arun.sanna@outlook.com
