# Outlinks Feature Analysis - Phase 1

## Overview

Outlinks are the opposite of backlinks - they are the links that go FROM a page to other pages. We need to extract all the links from a given URL and display them similar to how backlinks are displayed.

## Firecrawl API Analysis

### Scrape Endpoint

- Endpoint: `POST /scrape`
- We can use the `formats` parameter with value `["links"]` to get all links from a page
- This will return an array of URLs found on the page

### Request Format

```json
{
  "url": "https://example.com",
  "formats": ["links"],
  "onlyMainContent": true
}
```

### Expected Response

```json
{
  "success": true,
  "data": {
    "links": [
      "https://example.com/page1",
      "https://example.com/page2",
      "https://external.com/resource"
    ],
    "metadata": {
      "title": "Page Title",
      "sourceURL": "https://example.com"
    }
  }
}
```

## Current Architecture

### Frontend (graph.js)

- URL node menu already has infrastructure for multiple options
- Can add "Get Outlinks" option after backlinks options
- Use similar pattern as `fetchAndDisplayBacklinks` function

### Backend (server.py)

- Need new endpoint `/api/url/outlinks`
- Use Firecrawl API with links format
- Return structured data similar to backlinks

## Implementation Requirements

1. **Menu Option**: Add "Get Outlinks" to URL node menu
2. **Backend Endpoint**: Create endpoint to fetch links using Firecrawl
3. **Node Creation**: Create outlinks_query node type
4. **Display Logic**: Show links in profile similar to backlinks
5. **Edge Creation**: Connect URL node to outlinks node

## Key Differences from Backlinks

1. **Data Source**: Firecrawl instead of Ahrefs
2. **Data Structure**: Simple URL list vs rich backlink metadata
3. **Display**: May want to categorize internal vs external links
4. **Performance**: Should be faster than backlinks API
