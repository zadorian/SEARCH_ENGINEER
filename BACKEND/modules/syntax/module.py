"""
SYNTAX - Unified Operator Syntax Module

Exposes the unified query parser, operator registry, and execution engine.
"""

from .parser import parse, ParsedQuery, TargetType, OperatorType, GridTarget
from .operators import OPERATORS, OperatorCategory, OperatorDef
from .executor import UnifiedExecutor, execute as execute_query

def parse_query(query: str):
    """
    Parse a unified query string.
    
    Args:
        query: Raw query string (e.g., "bl? p? :!soax.com")
        
    Returns:
        ParsedQuery object or None if invalid
    """
    return parse(query)

def get_operators():
    """Get the full operator registry."""
    return OPERATORS

def get_operator(symbol: str):
    """Get definition for a specific operator."""
    return OPERATORS.get(symbol)

async def execute(query: str, project_id: str = "default"):
    """
    Execute a query using the unified executor.
    
    Args:
        query: Operator syntax query
        project_id: Project context
        
    Returns:
        Execution result dict
    """
    return await execute_query(query, project_id)

