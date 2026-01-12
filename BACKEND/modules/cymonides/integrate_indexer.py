#!/usr/bin/env python3
"""
Script to integrate indexer tools into mcp_server.py
"""

import re

# Read current file
with open('/data/CYMONIDES/mcp_server.py', 'r') as f:
    content = f.read()

# 1. Add import for indexer at the imports section
import_addition = '''
# Import Indexer toolkit
try:
    from indexer.mcp_tools import get_indexer_tools, create_indexer_handler, INDEXER_TOOLS
    INDEXER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Indexer toolkit not available: {e}")
    INDEXER_AVAILABLE = False
'''

# Find where to insert (after the CymonidesUnifiedSearch import)
insert_point = content.find('UNIFIED_AVAILABLE = False')
if insert_point > 0:
    insert_point = content.find('\n', insert_point) + 1
    content = content[:insert_point] + import_addition + content[insert_point:]

# 2. Add indexer handler initialization in __init__
init_addition = '''
        # Initialize indexer handler
        self.indexer_handler = create_indexer_handler(self.es) if INDEXER_AVAILABLE else None
'''

# Find __init__ end point (after self._register_handlers())
init_point = content.find('self._register_handlers()')
if init_point > 0:
    # Find the previous line
    init_point = content.rfind('\n', 0, init_point)
    content = content[:init_point] + init_addition + content[init_point:]

# 3. Add indexer tools to list_tools - add before 'return tools'
tools_addition = '''
                # === INDEXER TOOLKIT ===
                # Added dynamically from indexer module
            ]
            
            # Add indexer tools if available
            if INDEXER_AVAILABLE:
                for tool_def in INDEXER_TOOLS:
                    tools.append(Tool(
                        name=tool_def["name"],
                        description=tool_def["description"],
                        inputSchema=tool_def["inputSchema"]
                    ))
'''

# Find the return tools statement and the closing bracket before it
return_tools_pattern = r'(\s+)(\]\s*return tools)'
match = re.search(return_tools_pattern, content)
if match:
    # Replace the closing ] with our addition
    content = content[:match.start()] + '''
                # === INDEXER TOOLKIT ===
                # (Tools added dynamically below)
            ]
            
            # Add indexer tools if available
            if INDEXER_AVAILABLE:
                for tool_def in INDEXER_TOOLS:
                    tools.append(Tool(
                        name=tool_def["name"],
                        description=tool_def["description"],
                        inputSchema=tool_def["inputSchema"]
                    ))
            
            return tools
''' + content[match.end():]

# 4. Add indexer tool handling in _handle_tool
handler_addition = '''
        # === INDEXER TOOLKIT ===
        if name.startswith("indexer_") and INDEXER_AVAILABLE and self.indexer_handler:
            return await self.indexer_handler.handle(name, args)

'''

# Find the _handle_tool method and add at the start of the routing
handle_point = content.find('async def _handle_tool(self, name: str, args: Dict)')
if handle_point > 0:
    # Find the first if statement after the docstring
    first_if = content.find('# === ', handle_point)
    if first_if > 0:
        content = content[:first_if] + handler_addition + content[first_if:]

# Write updated file
with open('/data/CYMONIDES/mcp_server.py', 'w') as f:
    f.write(content)

print("Integration complete!")
