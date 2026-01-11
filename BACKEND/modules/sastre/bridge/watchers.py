"""
SASTRE Watcher Bridge

Bridge to TypeScript watcher system - ALL 15 procedures.

Watchers are bidirectional:
- Header -> Watcher: Document header triggers investigation query
- Finding -> Section: New findings stream back to document sections

tRPC endpoints from watcherRouter.ts:
1. create - Basic watcher creation
2. createEvent - Event watcher (ET3)
3. createTopic - Topic watcher (ET3)
4. createEntity - Entity watcher
5. addContext - Add context node
6. removeContext - Remove context node
7. updateDirective - Update watcher directive note
8. getContext - Get watcher context nodes
9. list - List all watchers
10. listActive - List active watchers
11. listForDocument - Get watchers for a document
12. get - Get watcher by ID
13. updateStatus - Update watcher status
14. delete - Delete watcher
15. toggle - Toggle watcher active status
"""

# Re-export from bridges.py
from ..bridges import WatcherBridge

__all__ = ['WatcherBridge']
