import asyncio
import json
import importlib
import inspect
from typing import Dict, Any

async def test_mcp_server():
    """Test the AWS MCP server functionality."""
    # Import the module that contains the server
    aws_mcp = importlib.import_module("aws_mcp")
    
    # Verify the server instance
    server = getattr(aws_mcp, "server", None)
    if not server:
        print("❌ Error: No server instance found in aws_mcp module")
        return False
    
    print(f"✅ Server found: {server.name}")
    
    # List the available tools
    tools = await server.list_tools()
    print(f"✅ Found {len(tools)} tools:")
    
    # Output the tools
    for tool in tools:
        print(f"  - {tool.name}: {tool.description}")
    
    # Simulate a call to list-credentials to test functionality
    try:
        for tool in tools:
            if tool.name == 'list-credentials':
                # Call the tool
                result = await server.call_tool(
                    name='list-credentials',
                    arguments={}
                )
                # Check the result format - it's now a list of content objects
                if len(result) > 0 and hasattr(result[0], "text"):
                    result_text = result[0].text
                    result_json = json.loads(result_text)
                else:
                    print("Unexpected result format")
                    result_json = {}
                
                print(f"✅ Successfully called list_credentials: Found {result_json.get('count', 0)} profiles")
                print(f"Table output: \n{result_json.get('formatted_table', '')}")
                
                break
        else:
            print("❌ Error: list-credentials tool not found")
    except Exception as e:
        print(f"❌ Error calling list_credentials: {str(e)}")
    
    return True

if __name__ == "__main__":
    asyncio.run(test_mcp_server())