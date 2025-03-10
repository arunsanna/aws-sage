from setuptools import setup, find_packages

setup(
    name="aws-mcp",
    version="0.1.0",
    description="AWS Model Context Protocol (MCP) server for Claude Desktop and CLI",
    author="Claude User",
    py_modules=["aws_mcp"],
    install_requires=[
        "boto3>=1.28.0",
        "botocore>=1.31.0",
        "mcp>=0.8.0",
        "pydantic>=2.0.0",
    ],
    entry_points={
        "mcp.servers": ["aws-mcp = aws_mcp:server"],
        "console_scripts": ["aws-mcp = run_aws_mcp:main"],
    },
    scripts=["run_aws_mcp.py"],
)