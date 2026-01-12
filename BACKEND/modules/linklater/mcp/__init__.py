"""
LINKLATER MCP Servers

This package provides MCP (Model Context Protocol) interfaces for LINKLATER.

Available servers:
- syntax_server: UNIFIED syntax-driven interface (PREFERRED)
  - Single tool: linklater_query(query: str)
  - Same syntax as CLI and API

- server: Original multi-tool interface (legacy)
  - Individual tools for backlinks, scraping, etc.

Usage:
    # Syntax-driven (preferred)
    python -m linklater.mcp.syntax_server

    # Or for direct query:
    python -m linklater.mcp.syntax_server "?bl !soax.com"
"""

from .syntax_server import query, query_sync, execute_linklater_query

__all__ = ["query", "query_sync", "execute_linklater_query"]
