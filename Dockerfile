FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Create non-root user for security
RUN useradd -m -s /bin/bash -u 1000 appuser

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY README.md .
COPY src/ src/

# Install the package (non-editable for container)
RUN pip install --no-cache-dir .

# Switch to non-root user
USER appuser

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV AWS_SAGE_LOG_LEVEL=INFO

# Entry point for MCP server (stdio transport)
ENTRYPOINT ["python", "-m", "aws_sage.server"]
