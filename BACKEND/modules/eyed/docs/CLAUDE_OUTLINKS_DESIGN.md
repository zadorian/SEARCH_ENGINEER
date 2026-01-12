# Outlinks Feature Design - Phase 2

## Feature Design

### 1. User Flow

```
1. User double-clicks URL node
2. Selects "🔗 Get Outlinks" from menu
3. System fetches all links from the page using Firecrawl
4. Creates outlinks_query node with results
5. Displays links in node profile (categorized as internal/external)
```

### 2. Menu Integration

Add new option to URL node menu after backlinks options:

```javascript
{
    label: '🔗 Get Outlinks',
    action: () => {
        fetchAndDisplayOutlinks(node);
    }
}
```

### 3. Backend Endpoint Design

#### Endpoint: `/api/url/outlinks`

```python
@app.route('/api/url/outlinks', methods=['POST'])
def get_url_outlinks():
    """
    Request: { "url": "https://example.com" }
    Response: {
        "success": true,
        "url": "https://example.com",
        "outlinks": [
            {
                "url": "https://example.com/page1",
                "type": "internal",
                "text": "Link text if available"
            },
            {
                "url": "https://external.com/resource",
                "type": "external",
                "text": "External link"
            }
        ],
        "total": 25,
        "internal_count": 15,
        "external_count": 10
    }
    """
```

### 4. Frontend Implementation

#### New Function: `fetchAndDisplayOutlinks`

Similar to `fetchAndDisplayBacklinks` but:

- Calls `/api/url/outlinks` endpoint
- Creates `outlinks_query` node type
- Categorizes links as internal/external
- Different color scheme (purple/magenta)

### 5. Node Display Design

#### Outlinks Query Node Properties

```javascript
{
    type: 'outlinks_query',
    value: 'Outlinks for example.com',
    label: '🔗 Outlinks: example.com (25 URLs)',
    searchTerm: 'https://example.com',
    urls: [...],
    outlinksData: [...],
    internalCount: 15,
    externalCount: 10,
    source: 'Firecrawl Outlinks'
}
```

### 6. Profile Display

- Similar to backlinks display but with categories
- Internal links grouped first
- External links grouped second
- Each link shows URL and link text (if available)

### 7. Visual Design

- Node color: #FF00FF (magenta) for outlinks
- Edge color: #FF00FF to match
- Edge label: 'outlinks'

## Implementation Steps

1. **Backend**: Create `/api/url/outlinks` endpoint
2. **Frontend Menu**: Add "Get Outlinks" option
3. **Frontend Function**: Create `fetchAndDisplayOutlinks`
4. **Display Logic**: Update `showNodeDetails` for outlinks_query nodes
5. **Testing**: Verify link extraction and categorization
