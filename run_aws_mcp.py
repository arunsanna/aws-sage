#!/usr/bin/env python3
"""
AWS MCP Runner Script - Can run as server or CLI
"""
import asyncio
import sys
import aws_mcp

async def run_server():
    """Start the AWS MCP server"""
    print("Starting AWS MCP Server...")
    try:
        await aws_mcp.server.run_stdio_async()
    except Exception as e:
        print(f"Error running AWS MCP server: {e}")
        raise

def main():
    """
    Main entry point for the application
    Can be used both as a CLI and a server
    """
    if len(sys.argv) > 1:
        # Run as CLI if arguments provided
        aws_mcp.run_cli()
    else:
        # Run as server if no arguments
        asyncio.run(run_server())

if __name__ == "__main__":
    main()