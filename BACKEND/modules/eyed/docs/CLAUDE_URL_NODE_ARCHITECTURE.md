# URL Node Double-Click Architecture Analysis

**Date**: 2025-07-02 22:15
**Component**: Node Interaction System

## Current Architecture

### Event Handling Flow

```
User Action → vis.js Network Event → Event Handler → Action Function
     ↓              ↓                      ↓              ↓
Double-Click   network.on()         Params Check    expandNode()
Right-Click    "doubleClick"        Node Type       showContextMenu()
               "oncontext"          Selection       [Custom Actions]
```

### Component Inventory

1. **Event Handlers** (graph.js)
   - `network.on("doubleClick")` - Line 811
   - `network.on("oncontext")` - Line 837
   - Current double-click: Expands nodes or hides query nodes
   - Right-click: Shows dynamic context menu

2. **Context Menu System**
   - `showContextMenu()` - Line 4642
   - `hideContextMenu()` - Line 4637
   - Dynamic menu generation based on node type
   - Special handling for image nodes, company/name nodes

3. **Node Types**
   - URL nodes: color `#00FFFF` (cyan)
   - Currently treated as standard nodes
   - No URL-specific interactions

4. **API Integration Points**
   - Backend server: `/api/*` endpoints
   - Existing search integrations:
     - DeHashed search
     - WhoisXML search
     - Google search (exhaustive)
     - OpenCorporates/Aleph search

### Data Flow for Search Operations

```
Frontend Action → API Request → Backend Processing → Response → UI Update
       ↓              ↓                ↓                ↓          ↓
  expandNode()   fetch('/api/...')  server.py      JSON data   addNode()
                 POST request        Process         results    updateUI()
```

### Current Pain Points

1. URL nodes have no specialized functionality
2. No direct link opening capability
3. No backlinks analysis integration
4. API keys hardcoded in frontend (security risk)

### Technology Stack

- Frontend: vanilla JavaScript + vis.js
- Backend: Python Flask (server.py)
- Network visualization: vis.js library
- HTTP client: Fetch API
- Current external APIs: Google, WhoisXML, DeHashed, OpenCorporates

## Integration Requirements for Ahrefs

1. Secure API key management (backend only)
2. New backend endpoint for Ahrefs requests
3. Frontend handler for URL node double-click
4. Result display mechanism for backlinks
5. Error handling for API failures/limits
