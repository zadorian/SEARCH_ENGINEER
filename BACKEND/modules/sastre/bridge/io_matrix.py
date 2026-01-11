"""
SASTRE IO Matrix Bridge

Bridge to IO Matrix system (5,620+ rules).
Routes investigations through the correct modules based on:
- Input type (company name, email, domain, etc.)
- Desired output (officers, shareholders, backlinks, etc.)
- Jurisdiction
"""

# Re-export from bridges.py
from ..bridges import IOBridge

# Alias for spec compliance
IOMatrixBridge = IOBridge

__all__ = ['IOBridge', 'IOMatrixBridge']
