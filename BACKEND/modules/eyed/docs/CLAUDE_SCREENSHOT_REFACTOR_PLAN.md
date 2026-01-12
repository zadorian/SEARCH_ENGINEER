# URL Node Screenshot Feature - Refactor Plan

## Proposed Architecture

```
URL Node Creation → Trigger Screenshot → Firecrawl API → Store Result → Update Display
      ↓                    ↓                   ↓              ↓              ↓
   Node ID            Loading State        Full Page      Base64 Data    Show in Profile
                                          Screenshot
```

## Design Details

### 1. Backend Architecture

#### New Endpoint: `/api/screenshot/capture`

```python
@app.route('/api/screenshot/capture', methods=['POST'])
def capture_screenshot():
    """
    Request body: { "url": "https://example.com", "nodeId": "node_123" }
    Returns: { "success": true, "screenshot": "base64_data" }
    """
```

#### Firecrawl Integration

- Use scrape endpoint with `formats: ["screenshot@fullPage"]`
- Store API key in .env file
- Implement retry logic for failures
- 30-second timeout

### 2. Frontend Flow

#### Trigger Points

1. **After URL Paste** (graph.js:10551)

   ```javascript
   const result = addNode(nodeData, "url");
   if (result && result.nodeId) {
     triggerScreenshotCapture(result.nodeId, trimmedText);
   }
   ```

2. **After Manual URL Save** (optional - user controlled)
   - Add "Capture Screenshot" button in profile
   - Allow manual trigger for existing URLs

#### Loading State Management

```javascript
// Add to node data
node.data.screenshotStatus = "loading" | "success" | "error" | null;
node.data.screenshotError = "error message if failed";
```

#### Display Integration

- Add screenshot section to URL node profiles
- Show loading spinner during capture
- Display full-page screenshot when ready
- Click to enlarge functionality

### 3. Implementation Strategy

#### Step 1: Backend Setup

1. Add Firecrawl API key to .env
2. Create `/api/screenshot/capture` endpoint
3. Test with sample URLs

#### Step 2: Frontend Trigger

1. Add `triggerScreenshotCapture` function
2. Integrate with URL node creation
3. Add loading state to nodes

#### Step 3: Display Enhancement

1. Modify node profile to show screenshots
2. Add loading/error states
3. Implement click-to-enlarge

#### Step 4: Error Handling

1. Handle timeouts gracefully
2. Retry failed captures
3. User feedback for errors

### 4. Risk Assessment

| Risk              | Impact | Mitigation               |
| ----------------- | ------ | ------------------------ |
| API Rate Limits   | High   | Implement queuing system |
| Large Image Sizes | Medium | Compress/resize images   |
| Slow Page Load    | Medium | Background processing    |
| Failed Captures   | Low    | Manual retry option      |

### 5. Rollback Plan

1. Feature flag: `ENABLE_AUTO_SCREENSHOTS`
2. Keep original URL node creation intact
3. Screenshots stored separately from core data
4. Can disable without affecting existing nodes

### 6. Migration Strategy

- New URL nodes: Auto-capture screenshots
- Existing URL nodes: Manual capture option
- No breaking changes to current functionality

## Success Criteria

✓ Screenshots capture within 30 seconds
✓ Full-page screenshots stored with nodes
✓ Loading states clearly communicated
✓ Errors handled gracefully
✓ No disruption to current workflow
