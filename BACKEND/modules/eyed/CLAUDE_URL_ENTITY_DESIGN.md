# URL Entity Extraction - Design Plan

## Feature Overview

Extract entities and relationships from web pages using Firecrawl + Claude, creating a knowledge graph from URL content.

## Technical Design

### 1. User Flow

```
1. User double-clicks URL node
2. Selects "Extract Entities" from menu
3. Loading state shows "Extracting entities..."
4. Entities appear as new nodes
5. Relationships appear as edges
6. SOURCE edge connects URL to entities
```

### 2. Backend Architecture

#### New Endpoint: `/api/url/extract-entities`

```python
@app.route('/api/url/extract-entities', methods=['POST'])
def extract_url_entities():
    """
    Request: { "url": "https://example.com", "nodeId": "node_123" }
    Response: {
        "entities": [...],
        "relationships": [...],
        "metadata": { "title": "...", "wordCount": 1234 }
    }
    """
```

#### Processing Pipeline

1. **Firecrawl Scrape**

   ```python
   payload = {
       'url': url,
       'formats': ['markdown'],
       'onlyMainContent': True,
       'waitFor': 5000,
       'timeout': 30000,
       'blockAds': True
   }
   ```

2. **Claude Analysis**
   - Reuse existing tool structure from image extraction
   - Add web-specific entity types if needed
   - Include URL context in prompt

3. **Response Format**
   ```json
   {
     "success": true,
     "entities": [
       {
         "value": "John Doe",
         "type": "name",
         "confidence": "high",
         "notes": "CEO mentioned in about page"
       }
     ],
     "relationships": [
       {
         "source": "John Doe",
         "target": "Acme Corp",
         "relationship": "CEO of",
         "confidence": "high",
         "notes": "Listed as founder and CEO"
       }
     ],
     "metadata": {
       "title": "Acme Corp - About Us",
       "wordCount": 1234,
       "extractedAt": "2025-07-03T..."
     }
   }
   ```

### 3. Frontend Implementation

#### Menu Integration

```javascript
menuItems.push({
  label: "🧠 Extract Entities",
  action: () => {
    extractEntitiesFromUrl(node);
  },
});
```

#### Entity Extraction Function

```javascript
async function extractEntitiesFromUrl(urlNode) {
  // 1. Set loading state
  // 2. Call API
  // 3. Create entity nodes
  // 4. Create relationship edges
  // 5. Create SOURCE edge from URL
  // 6. Position nodes in circular pattern
  // 7. Save graph state
}
```

#### Node Positioning Strategy

- Place entities in a semi-circle around URL node
- Group by entity type (names together, companies together)
- Stagger creation with animation for visual appeal
- Maintain minimum distance between nodes

### 4. Error Handling

- Timeout after 45 seconds (Firecrawl + Claude processing)
- Handle rate limits gracefully
- Fallback for sites that block scraping
- Clear error messages for users

### 5. Visual Design

- Loading: Pulsing animation on URL node
- Entities: Standard node colors by type
- SOURCE edges: Green arrows from URL
- Relationship edges: Cyan with labels
- Success message: "Extracted X entities with Y relationships"

## Implementation Strategy

### Step 1: Backend API

1. Add Firecrawl scraping logic
2. Integrate Claude entity extraction
3. Test with various URLs

### Step 2: Frontend Menu

1. Add menu option
2. Create loading states
3. Handle API response

### Step 3: Graph Creation

1. Entity node creation
2. Relationship edge creation
3. Positioning algorithm

### Step 4: Polish

1. Error handling
2. Performance optimization
3. User feedback

## Risk Mitigation

- **Large Pages**: Limit to first 10,000 words
- **Rate Limits**: Queue requests, show waiting time
- **Failed Scrapes**: Inform user, suggest manual entry
- **No Entities Found**: Clear message, no error state

## Success Metrics

- Entities extracted accurately
- Relationships properly connected
- No duplicate nodes created
- Smooth user experience
- Clear visual representation
