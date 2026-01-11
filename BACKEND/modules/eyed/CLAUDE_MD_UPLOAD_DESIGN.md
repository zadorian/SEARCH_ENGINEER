# EYE-D MD File Upload Design Document

## Phase 2: Design MD File Upload Integration

### Overview

Add functionality to upload .md files and extract entities using the same Claude-based entity extraction pipeline currently used for URLs and images.

### Current Architecture Summary

#### Backend Flow (URL Entity Extraction)

1. **Endpoint**: `/api/url/extract-entities` (server.py:2417-2596)
2. **Process**:
   - Receives URL from frontend
   - Uses Firecrawl to scrape webpage → markdown content
   - Sends markdown to Claude with structured tool calling
   - Claude extracts entities and relationships
   - Returns JSON with entities and relationships

#### Frontend Flow (URL Entity Extraction)

1. **Trigger**: "Extract Entities" option in URL node context menu (graph.js:5038-5041)
2. **Function**: `extractEntitiesFromUrl()` (graph.js:10863)
3. **Process**:
   - Calls `/api/url/extract-entities` endpoint
   - Creates entity nodes in semi-circle pattern
   - Creates green SOURCE edges from URL to entities
   - Creates cyan relationship edges between entities

#### Claude Tool Structure

```python
tools = [{
    "name": "extract_entities_and_relationships",
    "input_schema": {
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "properties": {
                        "value": str,
                        "type": enum["name", "company", "email", ...],
                        "confidence": enum["high", "medium", "low"],
                        "notes": str
                    }
                }
            },
            "relationships": {
                "type": "array",
                "items": {
                    "properties": {
                        "source": str,
                        "target": str,
                        "relationship": str,
                        "confidence": str,
                        "notes": str
                    }
                }
            }
        }
    }
}]
```

### Design Approach

#### 1. Backend Design

**New Endpoint**: `/api/file/extract-entities`

- **Method**: POST (multipart/form-data)
- **Input**:
  - `file`: The uploaded .md file
  - `nodeId`: Optional node ID if attaching to existing node
- **Process**:
  1. Receive uploaded file
  2. Read markdown content directly (skip Firecrawl)
  3. Use same Claude tool structure as URL extraction
  4. Return same JSON format as URL extraction
- **Reuse**: Most of the Claude extraction logic from lines 2473-2586

**Code Location**: Add after the URL entity extraction endpoint (~line 2597)

#### 2. Frontend Design

**Option A: Context Menu on Existing Node**

- Add "Upload MD File" option to general canvas context menu
- Creates a file node first, then extracts entities

**Option B: Direct Upload Button (RECOMMENDED)**

- Add upload button in the main UI
- Upload triggers both node creation and entity extraction
- More discoverable for users

**Implementation Location**:

- Add file upload UI elements (similar to image upload)
- Create new function `extractEntitiesFromMdFile()`
- Reuse entity node creation logic from `extractEntitiesFromUrl()`

#### 3. UI/UX Design

**Upload Interface**:

```html
<!-- Add to the main toolbar or a prominent location -->
<button id="upload-md-btn" class="tool-button">📄 Upload MD File</button>
<input type="file" id="md-file-input" accept=".md" style="display: none;" />
```

**Process Flow**:

1. User clicks "Upload MD File" button
2. File picker opens (accept only .md files)
3. File uploads to backend
4. Loading indicator shows during extraction
5. Creates a document node for the MD file
6. Extracts and displays entities in semi-circle
7. Shows success message with entity count

### Implementation Plan

#### Backend Steps:

1. Create `/api/file/extract-entities` endpoint
2. Add file upload handling with size limits
3. Extract markdown content from uploaded file
4. Call Claude with same tool structure
5. Return entities and relationships

#### Frontend Steps:

1. Add upload button to UI
2. Add file input handler
3. Create `uploadMdFile()` function
4. Create document node for uploaded file
5. Call extraction endpoint
6. Reuse entity creation logic from URL extraction
7. Position entities around document node

### Code Reuse Strategy

#### From URL Entity Extraction:

- Claude tool structure (lines 2473-2523)
- Claude API call pattern (lines 2529-2561)
- Response parsing (lines 2563-2574)

#### From Frontend:

- Entity node creation (lines 10924-10987)
- Relationship edge creation (lines 10989-11026)
- Node positioning logic (semi-circle pattern)
- Animation and styling

### Risk Mitigation

1. **File Size**: Limit to 10MB to avoid token limits
2. **Security**: Validate file type, sanitize content
3. **Error Handling**: Clear user feedback for failures
4. **Performance**: Show progress during extraction

### Success Criteria

1. Users can upload .md files via button click
2. Uploaded files create document nodes
3. Entities are extracted using same Claude pipeline
4. Entities appear in semi-circle around document
5. Relationships show between entities
6. Clear visual feedback throughout process

### Phase 3 Preview

Implementation will follow this order:

1. Backend endpoint creation
2. Frontend upload UI
3. Integration and testing
4. Error handling and polish

---

**Note**: This design maintains consistency with existing patterns while adding the requested MD file upload functionality. The implementation will carefully reuse existing code to ensure reliability and maintainability.
