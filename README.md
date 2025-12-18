# AWS Sage

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/arunsanna/aws-sage/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-yellow.svg)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-145%20passing-brightgreen.svg)](tests/)

A production-grade [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server for AWS. Connect AI assistants to your AWS infrastructure and manage it through natural conversation.

**🚀 Works with any MCP-compatible client** - just install and configure.

### Compatible Clients

| Client | Status | Notes |
|--------|--------|-------|
| [Claude Desktop](https://claude.ai/download) | ✅ Full Support | Recommended |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | ✅ Full Support | CLI & IDE |
| [Cursor](https://cursor.sh) | ✅ Full Support | MCP enabled |
| [Cline](https://github.com/cline/cline) | ✅ Full Support | VS Code extension |
| [Windsurf](https://codeium.com/windsurf) | ✅ Full Support | MCP enabled |
| [Zed](https://zed.dev) | ✅ Full Support | MCP enabled |
| VS Code + Copilot | ⏳ Planned | Via MCP extension |

## Why AWS Sage?

AWS Labs offers [15 separate MCP servers](https://github.com/awslabs/mcp) for different services. AWS Sage takes a different approach:

| Feature | AWS Labs MCP | AWS Sage |
|---------|--------------|----------|
| **Architecture** | 15 separate servers | 1 unified server |
| **Tools** | ~45 tools across servers | **30 intelligent tools** |
| **Cross-Service Queries** | No | Yes - discover resources across all services |
| **Dependency Mapping** | No | Yes - "what depends on this resource?" |
| **Impact Analysis** | No | Yes - "what breaks if I delete this?" |
| **Incident Investigation** | No | Yes - automated troubleshooting workflows |
| **Cost Analysis** | Separate server | **Built-in** - idle resources, rightsizing, projections |
| **LocalStack Support** | No | **Yes** - seamless local development |
| **Multi-Account** | No | **Yes** - cross-account via AssumeRole |
| **Docker Support** | Separate | **Built-in** with docker-compose |
| **Safety System** | Basic | 3-tier with 70+ blocked operations |
| **Natural Language** | Limited | Full NLP with intent classification |

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

#### Cost Analysis
Find savings and optimize spending:
```
"Find idle resources in my account"
"Get rightsizing recommendations for EC2"
"Project costs for 3 t3.large instances"
```

#### LocalStack Integration
Develop locally without touching production:
```
"Switch to LocalStack environment"
"Compare S3 buckets between localstack and production"
```

#### Multi-Account Support
Work across AWS accounts:
```
"Assume role in account 123456789012"
"Switch to production account"
```

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/arunsanna/aws-sage
cd aws-sage
pip install .

# 2. Add to Claude Desktop config (see Configuration below)
# 3. Restart Claude Desktop
# 4. Start chatting: "List my S3 buckets"
```

That's it! Claude Desktop automatically runs AWS Sage when needed.

## Installation

### Prerequisites
- Python 3.11+
- AWS credentials configured (`~/.aws/credentials` or `~/.aws/config`)
- Any MCP-compatible client (see [Compatible Clients](#compatible-clients) above)

### Option 1: From Source

```bash
git clone https://github.com/arunsanna/aws-sage
cd aws-sage
pip install .
```

### Option 2: Direct from GitHub

```bash
pip install git+https://github.com/arunsanna/aws-sage.git
```

## Client Configuration

First, find your Python path:
```bash
which python  # or: which python3
```

### Claude Desktop

**Config file location:**
| OS | Path |
|----|------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

```json
{
  "mcpServers": {
    "aws-sage": {
      "command": "/path/to/python3",
      "args": ["-m", "aws_sage.server"],
      "env": {
        "AWS_PROFILE": "default"
      }
    }
  }
}
```

### Claude Code

**Option 1: CLI command**
```bash
claude mcp add aws-sage -s user -- python -m aws_sage.server
```

**Option 2: Project config** (`.mcp.json` in project root)
```json
{
  "mcpServers": {
    "aws-sage": {
      "command": "python",
      "args": ["-m", "aws_sage.server"],
      "env": {
        "AWS_PROFILE": "default"
      }
    }
  }
}
```

**Option 3: Global config** (`~/.claude.json`)
```json
{
  "mcpServers": {
    "aws-sage": {
      "command": "python",
      "args": ["-m", "aws_sage.server"],
      "env": {
        "AWS_PROFILE": "default"
      }
    }
  }
}
```

### Cursor

**Config file:** `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project)

```json
{
  "mcpServers": {
    "aws-sage": {
      "command": "python",
      "args": ["-m", "aws_sage.server"],
      "env": {
        "AWS_PROFILE": "default"
      }
    }
  }
}
```

### Cline (VS Code Extension)

**Config file:** Access via Cline settings → "Configure MCP Servers" → `cline_mcp_settings.json`

```json
{
  "mcpServers": {
    "aws-sage": {
      "command": "python",
      "args": ["-m", "aws_sage.server"],
      "env": {
        "AWS_PROFILE": "default"
      },
      "disabled": false
    }
  }
}
```

### Windsurf

**Config file:**
| OS | Path |
|----|------|
| macOS | `~/.codeium/windsurf/mcp_config.json` |
| Windows | `%USERPROFILE%\.codeium\windsurf\mcp_config.json` |

```json
{
  "mcpServers": {
    "aws-sage": {
      "command": "python",
      "args": ["-m", "aws_sage.server"],
      "env": {
        "AWS_PROFILE": "default"
      }
    }
  }
}
```

### Zed

**Config file:** Zed Settings (`settings.json`)

```json
{
  "context_servers": {
    "aws-sage": {
      "command": "python",
      "args": ["-m", "aws_sage.server"],
      "env": {
        "AWS_PROFILE": "default"
      }
    }
  }
}
```

### VS Code (Native MCP)

**Config file:** `.vscode/mcp.json` (project)

```json
{
  "servers": {
    "aws-sage": {
      "command": "python",
      "args": ["-m", "aws_sage.server"],
      "env": {
        "AWS_PROFILE": "default"
      }
    }
  }
}
```

### Docker Installation (All Clients)

For enhanced security with container isolation:

```bash
git clone https://github.com/arunsanna/aws-sage
cd aws-sage
docker compose build aws-sage
```

**Docker config (use in any client above):**

macOS/Linux:
```json
{
  "command": "docker",
  "args": [
    "run", "-i", "--rm",
    "-v", "${HOME}/.aws:/home/appuser/.aws:ro",
    "-e", "AWS_PROFILE=default",
    "aws-sage:latest"
  ]
}
```

Windows:
```json
{
  "command": "docker",
  "args": [
    "run", "-i", "--rm",
    "-v", "%USERPROFILE%\\.aws:/home/appuser/.aws:ro",
    "-e", "AWS_PROFILE=default",
    "aws-sage:latest"
  ]
}
```

## Tools Reference (30 Tools)

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

### Cost Analysis

| Tool | Description |
|------|-------------|
| `find_idle_resources` | Find unused EC2/RDS/EBS/EIP resources |
| `get_rightsizing_recommendations` | Get EC2 right-sizing suggestions |
| `get_cost_breakdown` | Spending analysis by service/tag |
| `project_costs` | Estimate costs before deployment |

### Environment Management

| Tool | Description |
|------|-------------|
| `list_environments` | List configured environments (production/localstack) |
| `switch_environment` | Switch between LocalStack and production |
| `get_environment_info` | Current environment details |
| `check_localstack` | Verify LocalStack connectivity |
| `compare_environments` | Diff resources between environments |

### Multi-Account Management

| Tool | Description |
|------|-------------|
| `assume_role` | Assume role in another account via STS |
| `list_accounts` | Show configured accounts |
| `switch_account` | Change active account context |

## Usage Examples

### Basic Queries

```
"List all S3 buckets"
"Show EC2 instances in us-west-2"
"Describe Lambda function payment-processor"
"Get IAM users with console access"
```

### Cost Analysis

```
"Find idle resources in us-east-1"
"Get rightsizing recommendations for EC2"
"Show cost breakdown by service for last 30 days"
"Project costs for 2 t3.large and 100GB gp3 EBS"
```

### LocalStack Development

```
"Switch to localstack"
"Create an S3 bucket in localstack"
"Compare DynamoDB tables between localstack and production"
"Check localstack connectivity"
```

### Multi-Account Operations

```
"Assume role arn:aws:iam::123456789012:role/AdminRole"
"List all configured accounts"
"Switch to production account"
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

## Architecture

```
aws-sage/
├── Dockerfile                  # Container support
├── docker-compose.yml          # LocalStack + MCP server
│
├── src/aws_sage/
│   ├── server.py              # FastMCP server (30 tools)
│   ├── config.py              # Configuration & safety modes
│   │
│   ├── core/
│   │   ├── session.py         # AWS session management
│   │   ├── context.py         # Conversation memory
│   │   ├── environment.py     # Environment configuration
│   │   ├── environment_manager.py  # LocalStack/production switching
│   │   ├── multi_account.py   # Cross-account management
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
│   ├── composition/
│   │   ├── docs_proxy.py      # AWS documentation
│   │   └── knowledge_proxy.py # AWS knowledge base + live query
│   │
│   └── differentiators/
│       ├── discovery.py       # Cross-service discovery
│       ├── dependencies.py    # Dependency mapping
│       ├── workflows.py       # Incident investigation
│       ├── cost.py            # Cost analysis
│       └── compare.py         # Environment comparison
│
└── tests/
    ├── unit/                  # Unit tests (145 tests)
    └── integration/           # Integration tests
```

## Development (For Contributors)

### Setup

```bash
git clone https://github.com/arunsanna/aws-sage
cd aws-sage
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest                          # All tests
pytest --cov=aws_sage           # With coverage
pytest tests/unit/test_cost.py  # Specific module
```

### Local Testing with LocalStack

Test against LocalStack without touching real AWS:

```bash
# Start LocalStack
docker compose up -d localstack

# In Claude Desktop, say:
# "Switch to localstack environment"
# "Create test bucket my-test-bucket"
```

### Debug Server Directly

For development/debugging (not needed for normal use):

```bash
fastmcp dev src/aws_sage/server.py  # Interactive mode
python -m aws_sage.server           # Direct run
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_PROFILE` | AWS profile to use | `default` |
| `AWS_DEFAULT_REGION` | Default AWS region | `us-east-1` |
| `AWS_SAGE_SAFETY_MODE` | Safety mode (read_only/standard/unrestricted) | `read_only` |
| `AWS_SAGE_LOCALSTACK_ENABLED` | Enable LocalStack by default | `false` |
| `AWS_SAGE_LOCALSTACK_HOST` | LocalStack host | `localhost` |
| `AWS_SAGE_LOCALSTACK_PORT` | LocalStack port | `4566` |

## Troubleshooting

### View Logs

```bash
# Claude Desktop logs
tail -f ~/Library/Logs/Claude/mcp-server-aws-sage.log
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

**"LocalStack not reachable"**
- Ensure LocalStack is running: `docker compose up -d localstack`
- Check endpoint: `curl http://localhost:4566/_localstack/health`
- Use `check_localstack` tool to diagnose

## Roadmap

**v1.0.0 (Current)**
- [x] 30 intelligent tools across 10 categories
- [x] Cross-service discovery, dependency mapping, impact analysis
- [x] Cost optimization analyzer
- [x] LocalStack integration
- [x] Multi-account support
- [x] Docker containerization
- [x] 3-tier safety system with 70+ blocked operations

**Future**
- [ ] CloudFormation drift detection
- [ ] Custom workflow definitions
- [ ] Terraform state integration
- [ ] Compliance scanning (CIS benchmarks)

## References

- [Model Context Protocol Specification](https://modelcontextprotocol.io) - Anthropic, 2024
- [MCP Ecosystem](https://github.com/modelcontextprotocol) - 5,800+ servers, 97M monthly SDK downloads (2025)
- [AWS Labs MCP Servers](https://github.com/awslabs/mcp) - Official AWS MCP implementations
- [FastMCP Framework](https://github.com/jlowin/fastmcp) - Python MCP SDK
- [LocalStack](https://localstack.cloud) - Local AWS cloud emulator

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](./LICENSE) for details.

## Contact

- GitHub Issues: [arunsanna/aws-sage](https://github.com/arunsanna/aws-sage/issues)
- Email: arun.sanna@outlook.com
- Website: [arunsanna.com](https://arunsanna.com)
