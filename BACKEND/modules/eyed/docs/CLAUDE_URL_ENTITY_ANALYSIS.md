# URL Entity Extraction - Architecture Analysis

## Current State: Image Entity Extraction

### How Picture Extraction Works

1. **Frontend Flow** (graph.js:9544-9696)
   - `autoExtractEntitiesFromImage()` is called when image is added
   - Sends image data to `/api/vision` endpoint
   - Receives structured entities and relationships
   - Creates nodes for each entity
   - Creates edges for relationships between entities
   - Creates SOURCE edges from image to extracted entities

2. **Backend Processing** (server.py:559-723)
   - Uses Claude with structured tool calling
   - Tool: `extract_entities_and_relationships`
   - Extracts entities with: value, type, confidence, notes
   - Extracts relationships with: source, target, relationship, confidence, notes
   - Returns structured JSON response

3. **Entity Types Supported**
   - name (people only)
   - company (organizations)
   - email, phone, address
   - ip_address, domain, url
   - username, account
   - license_plate, other

4. **Connection Creation Pattern**

   ```javascript
   // SOURCE connections (purple) from image to entities
   edges.add({
     from: imageNodeId,
     to: entityNodeId,
     ...getConnectionStyle("SOURCE"),
     label: "SOURCE",
   });

   // Relationship connections (cyan) between entities
   edges.add({
     from: sourceEntityId,
     to: targetEntityId,
     label: relationshipType,
     color: { color: "#00CED1" },
     arrows: { to: { enabled: true } },
   });
   ```

## Proposed: URL Entity Extraction

### Architecture Overview

```
URL Node → Firecrawl Scrape → Claude Analysis → Entity Creation → Connection Creation
     ↓           ↓                  ↓                 ↓                ↓
  Node ID    Markdown Content   Entities List    Node Creation    Edge Creation
                                & Relationships
```

### Integration Points

1. **Entry Point**: Add to URL options menu (like backlinks)
2. **Backend Flow**:
   - New endpoint `/api/url/extract-entities`
   - Use Firecrawl to get markdown content
   - Pass to Claude for entity extraction
   - Return entities and relationships
3. **Frontend Flow**:
   - Display loading state
   - Create entity nodes
   - Create relationship edges
   - Create SOURCE edge from URL node

### Key Differences from Image Extraction

1. **Content Source**: Firecrawl markdown vs image data
2. **Context**: Full webpage content vs visual elements
3. **Entity Types**: May include additional web-specific types
4. **Volume**: Potentially more entities from text-heavy pages

### Firecrawl Integration Requirements

- Use `/scrape` endpoint with `formats: ["markdown"]`
- Set `onlyMainContent: true` to focus on main content
- Use `waitFor: 5000` for dynamic content
- Handle timeouts and errors gracefully
