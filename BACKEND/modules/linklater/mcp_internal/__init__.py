"""
LINKLATER MCP Module

Two MCP servers available:

1. linklater_mcp.py - SYNTAX-DRIVEN (recommended)
   Single tool that accepts query syntax strings.
   Example: linklater_query(query="?bl:!soax.com")

2. server.py - DISCRETE TOOLS (legacy)
   Individual tools like get_backlinks(), extract_entities(), etc.

Usage with Claude Code MCP config:
{
  "mcpServers": {
    "linklater": {
      "command": "python3",
      "args": ["/path/to/LINKLATER/mcp/linklater_mcp.py"]
    }
  }
}
"""

# Re-export main components for programmatic use
try:
    from .linklater_mcp import format_results
except ImportError:
    format_results = None

__all__ = ["format_results"]
