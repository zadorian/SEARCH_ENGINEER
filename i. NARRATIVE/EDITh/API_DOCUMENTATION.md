# EDITh API Documentation

## Base URL
```
http://localhost:3000/api
```

## Authentication
Currently no authentication is required. This will be added in future versions.

## Endpoints

### Document Management

#### List Documents
```http
GET /api/documents?refresh=true
```

Returns a list of all markdown documents in the configured directory.

**Query Parameters:**
- `refresh` (optional): Set to `true` to bypass cache

**Response:**
```json
[
  {
    "name": "document.md",
    "modified": "2024-01-08T10:30:00.000Z",
    "size": 1234
  }
]
```

#### Load Document by Filename
```http
GET /api/load-by-filename/:filename
```

Loads a document by its filename.

**Parameters:**
- `filename`: The markdown file name (e.g., `document.md`)

**Response:**
```json
{
  "title": "Document Title",
  "content": "Document content...",
  "fileId": "optional-file-id",
  "filename": "document.md"
}
```

#### Load Document by ID
```http
GET /api/load/:fileId
```

Loads a document by its file ID.

**Parameters:**
- `fileId`: The unique file identifier

**Response:**
```json
{
  "title": "Document Title",
  "content": "Document content...",
  "fileId": "file-id",
  "filename": "document.md"
}
```

#### Save Document
```http
POST /api/save
```

Creates or updates a document.

**Request Body:**
```json
{
  "title": "Document Title",
  "content": "Document content...",
  "fileId": "optional-for-updates"
}
```

**Response:**
```json
{
  "success": true,
  "fileId": "generated-or-existing-id",
  "filename": "document_title.md"
}
```

#### Delete Document
```http
DELETE /api/delete/:filename
```

Deletes a document by filename.

**Parameters:**
- `filename`: The markdown file name

**Response:**
```json
{
  "success": true
}
```

### AI Features

#### Extract Entities
```http
POST /api/extract-entities
```

Extracts entities from text content.

**Request Body:**
```json
{
  "content": "Text to analyze for entities..."
}
```

**Validation:**
- `content` is required
- Must be a string
- Maximum 100,000 characters

**Response:**
```json
{
  "entities": [
    {
      "name": "Entity Name",
      "type": "PERSON|ORGANIZATION|LOCATION",
      "confidence": 0.95
    }
  ]
}
```

#### Extract Arguments
```http
POST /api/ai/extract-arguments
```

Extracts arguments from text using Claude.

**Request Body:**
```json
{
  "text": "Text containing arguments...",
  "passType": "optional-pass-type"
}
```

**Validation:**
- `text` is required
- Must be a string
- Maximum 50,000 characters

**Response:**
```json
{
  "arguments": [
    {
      "claim": "Main claim",
      "evidence": "Supporting evidence",
      "confidence": 0.85
    }
  ]
}
```

#### Gap Filling
```http
POST /api/ai/gap-fill
```

Fills gaps marked with `[?]` in text.

**Request Body:**
```json
{
  "text": "Text with [?] gaps to fill",
  "sentenceOnly": false
}
```

**Response:**
```json
{
  "filledText": "Text with gaps filled",
  "hasChanges": true,
  "citations": []
}
```

### Utility Endpoints

#### File Map
```http
GET /api/file-map
```

Returns a comprehensive map of all project files.

**Response:**
```json
{
  "projectName": "EDITh",
  "files": {
    "path/to/file.js": {
      "size": 1234,
      "modified": "2024-01-08T10:30:00.000Z"
    }
  }
}
```

#### Cache Statistics
```http
GET /api/cache/stats
```

Returns cache performance statistics.

**Response:**
```json
{
  "size": 5,
  "keys": ["documents-list"],
  "memoryUsage": 123456
}
```

#### WebSocket Status
```http
GET /api/websocket/status
```

Returns WebSocket connection statistics.

**Response:**
```json
{
  "activeConnections": 2,
  "totalConnections": 10
}
```

## Error Responses

All endpoints may return error responses in the following format:

```json
{
  "error": "Error message",
  "status": "error",
  "statusCode": 400
}
```

Common HTTP status codes:
- `400` - Bad Request (invalid parameters)
- `404` - Not Found
- `500` - Internal Server Error

## Rate Limiting
Currently no rate limiting is implemented.

## CORS
CORS is enabled for all origins in development mode.