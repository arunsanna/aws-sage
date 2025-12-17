# Contributing to AWS MCP Pro

Thank you for your interest in contributing! This guide will help you get started.

## Code of Conduct

Be respectful, inclusive, and constructive in all interactions.

## Project Structure

```
aws-mcp/
├── src/aws_mcp/
│   ├── server.py              # Main FastMCP server
│   ├── config.py              # Configuration management
│   │
│   ├── core/                  # Core infrastructure
│   │   ├── session.py         # AWS session & credentials
│   │   ├── context.py         # Conversation memory
│   │   └── exceptions.py      # Custom exceptions
│   │
│   ├── safety/                # Safety layer
│   │   ├── classifier.py      # Operation classification
│   │   ├── validator.py       # Validation pipeline
│   │   └── denylist.py        # Blocked operations
│   │
│   ├── parser/                # NLP & validation
│   │   ├── intent.py          # Intent classification
│   │   └── service_models.py  # Botocore integration
│   │
│   ├── execution/             # Execution engine
│   │   ├── engine.py          # Main orchestrator
│   │   └── pagination.py      # Auto-pagination
│   │
│   ├── composition/           # AWS docs integration
│   │   ├── docs_proxy.py      # Documentation proxy
│   │   └── knowledge_proxy.py # Knowledge base
│   │
│   └── differentiators/       # Unique features
│       ├── discovery.py       # Cross-service discovery
│       ├── dependencies.py    # Dependency mapping
│       └── workflows.py       # Incident investigation
│
├── tests/
│   ├── unit/                  # Unit tests
│   ├── integration/           # Integration tests
│   └── conftest.py            # Pytest fixtures
│
└── pyproject.toml             # Project configuration
```

## Development Setup

### Prerequisites
- Python 3.11+
- AWS credentials for testing

### Installation

```bash
# Clone the repository
git clone https://github.com/arunsanna/aws-sage
cd aws-sage

# Install in development mode with dev dependencies
pip install -e ".[dev]"

# Verify installation
pytest --version
```

### Running the Server

```bash
# Development mode with auto-reload
fastmcp dev src/aws_mcp/server.py

# Or run directly
python -m aws_mcp.server
```

## Making Changes

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-description
```

### 2. Write Code

Follow these standards:

**Style**
- Follow PEP 8
- Use type hints for all function signatures
- Maximum line length: 100 characters
- Use `ruff` for linting

**Documentation**
- Docstrings for all public functions/classes (Google style)
- Update README if adding new features
- Add inline comments for complex logic only

**Example:**
```python
async def discover_resources(
    tags: dict[str, str],
    services: list[str] | None = None,
    region: str | None = None,
) -> DiscoveryResult:
    """Discover AWS resources by tags across multiple services.

    Args:
        tags: Tag key-value pairs to search for.
        services: Services to search. Defaults to all taggable services.
        region: AWS region. Defaults to configured region.

    Returns:
        DiscoveryResult containing found resources.

    Raises:
        AWSMCPError: If discovery fails.
    """
    ...
```

### 3. Write Tests

All new code must have tests:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=aws_mcp --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_safety.py -v

# Run tests matching pattern
pytest -k "test_classifier" -v
```

**Test file naming:**
- `test_<module>.py` for unit tests
- `test_<feature>_integration.py` for integration tests

**Test structure:**
```python
import pytest
from aws_mcp.safety.classifier import OperationClassifier

class TestOperationClassifier:
    """Tests for OperationClassifier."""

    def test_classify_read_operation(self):
        """Should classify list operations as READ."""
        classifier = OperationClassifier()
        result = classifier.classify("s3", "list_buckets")
        assert result == OperationType.READ

    def test_classify_destructive_operation(self):
        """Should classify delete operations as DESTRUCTIVE."""
        classifier = OperationClassifier()
        result = classifier.classify("s3", "delete_bucket")
        assert result == OperationType.DESTRUCTIVE
```

### 4. Run Quality Checks

Before submitting:

```bash
# Lint
ruff check src/

# Type check
mypy src/aws_mcp/

# Format
ruff format src/

# All tests pass
pytest
```

### 5. Commit Changes

Use conventional commits:

```
type(scope): description

[optional body]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `refactor`: Code refactoring
- `test`: Adding tests
- `chore`: Maintenance

**Examples:**
```bash
git commit -m "feat(safety): add rate limiting for API calls"
git commit -m "fix(parser): handle empty response from botocore"
git commit -m "docs: update installation instructions"
```

### 6. Submit Pull Request

1. Push your branch: `git push origin feature/your-feature`
2. Open a PR on GitHub
3. Fill out the PR template
4. Wait for review

## Adding New Features

### Adding a New Tool

1. Add the tool in `server.py`:

```python
@mcp.tool("tool_name", description="What the tool does")
async def tool_name(param: str) -> str:
    """Tool implementation."""
    # Implementation
    return result
```

2. Add tests in `tests/unit/test_server.py`
3. Update README.md with the new tool

### Adding a New Safety Rule

1. Add to `safety/denylist.py` for blocked operations
2. Add to `safety/classifier.py` for classification rules
3. Add tests in `tests/unit/test_safety.py`

### Adding a New Service Plugin

1. Create a new file in `services/plugins/`
2. Inherit from `BaseService` in `services/base.py`
3. Register in `services/registry.py`
4. Add tests

## Testing with AWS

### Using Moto (Recommended)

Most tests use [moto](https://github.com/getmoto/moto) to mock AWS:

```python
import pytest
from moto import mock_aws

@mock_aws
def test_list_buckets():
    # moto mocks boto3 calls
    ...
```

### Using Real AWS (Integration Tests)

For integration tests that need real AWS:

```bash
# Set profile
export AWS_PROFILE=your-test-profile

# Run integration tests only
pytest tests/integration/ -v
```

## Reporting Issues

Include:
- Clear title and description
- Steps to reproduce
- Expected vs actual behavior
- Environment (OS, Python version)
- Relevant logs

## Questions?

- GitHub Issues: [arunsanna/aws-sage/issues](https://github.com/arunsanna/aws-sage/issues)
- Email: arun.sanna@outlook.com

Thank you for contributing!
