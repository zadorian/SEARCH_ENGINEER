# URL Node Screenshot Architecture Analysis

## Current State Analysis

### URL Node Creation Flow

1. **Paste Handler** (graph.js:10491-10565)
   - User pastes URL on canvas
   - URL detected via regex pattern
   - Node created with `addNode(nodeData, 'url')`
   - Node positioned at view center

2. **URL Node Structure**

   ```javascript
   {
     type: 'url',
     value: 'example.com',      // Normalized URL
     label: 'example.com',
     fullUrl: 'https://example.com',  // Original URL
     source: 'Pasted URL',
     data: {
       // Additional metadata
     }
   }
   ```

3. **Node Display** (graph.js:2615-2830)
   - Profile shows URL fields
   - Manual URL management
   - Auto-save functionality

### Current Architecture

```
User Action → Paste Event → URL Detection → Node Creation → Display
                                                   ↓
                                            Graph State Save
```

### Integration Points for Screenshots

1. **Entry Points**:
   - URL paste detection (graph.js:10551)
   - Manual URL field save (graph.js:10730)
   - URL node creation via API

2. **Backend Requirements**:
   - New endpoint `/api/screenshot/capture`
   - Firecrawl API integration
   - Image storage handling

3. **Frontend Display**:
   - Add screenshot section to URL node profiles
   - Handle loading states
   - Display full-page screenshots

### Technical Considerations

1. **Asynchronous Flow**:
   - Screenshot capture takes time (5-30 seconds)
   - Need loading indicator
   - Background processing

2. **Storage**:
   - Screenshots as base64 data URLs
   - Store in node.data.screenshot
   - Consider size implications

3. **Error Handling**:
   - Site may be unreachable
   - Firecrawl API limits
   - Timeout scenarios

### Dependencies

- Firecrawl API (provided key: fc-00fe2a9f75b8431b99f92c34b4e9927c)
- Python requests library (backend)
- Base64 image handling (frontend)

## Pain Points to Address

1. No visual preview of URLs
2. Manual verification needed
3. No automatic content capture
