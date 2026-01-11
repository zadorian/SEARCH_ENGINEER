# Corporella Claude - Architecture Documentation

## System Overview

Corporella Claude is a 4-component system for global company intelligence with **hybrid processing**:

- **Fast Path**: Deterministic field mapping → instant user display
- **Smart Path**: Claude Haiku AI → deduplication, contradictions, unexpected data handling

Both paths run in parallel, giving users immediate feedback while the system builds a comprehensive, deduplicated profile.

## Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      USER INTERFACE                          │
│              (client.html + websocket_server.py)            │
└───────────────────────┬─────────────────────────────────────┘
                        │
         ┌──────────────┴──────────────┐
         │                             │
    ┌────▼─────┐                 ┌────▼─────┐
    │  FINDER  │                 │ ANALYZER │
    │finder.py │                 │analyzer.py│
    └────┬─────┘                 └────┬─────┘
         │                             │
         └──────────────┬──────────────┘
                        │
                   ┌────▼─────┐
                   │ FETCHER  │
                   │fetcher.py│
                   └────┬─────┘
                        │
              ┌─────────┴─────────┐
              │    POPULATOR      │
              │   populator.py    │
              │ (Claude Haiku AI) │
              └───────────────────┘
```

## Component 1: Finder (Criteria-based Search)

**File**: `finder.py`
**Purpose**: Search for companies based on various criteria

### Functions

```python
def search_by_name(name: str, jurisdiction: str = None) -> List[Dict]
    """Search OpenCorporates by company name"""

def search_by_officer(officer_name: str) -> List[Dict]
    """Find companies where person is officer/director"""

def search_by_lei(lei: str) -> Dict
    """Search by Legal Entity Identifier"""
```

### Data Sources
- OpenCorporates API (130+ jurisdictions)
- GLEIF LEI database

### Output Format
```json
{
    "companies": [
        {
            "name": "Apple Inc",
            "company_number": "C0806592",
            "jurisdiction": "us_ca",
            "source": "opencorporates"
        }
    ]
}
```

## Component 2: Fetcher (Comprehensive Data Retrieval)

**File**: `fetcher.py`
**Purpose**: Parallel multi-source company data fetching

### Architecture

```python
class GlobalCompanyFetcher:
    async def parallel_search(company_name: str, country_code: str = None):
        """
        Executes 5 parallel searches:
        1. OpenCorporates - Official registry data
        2. OCCRP Aleph - Investigative data, leaks
        3. SEC EDGAR - US public company filings
        4. OpenOwnership - Beneficial ownership
        5. LinkedIn - Company profiles (HuggingFace dataset)

        Returns raw results + calls Populator for AI merging
        """
```

### Threading Model
- `ThreadPoolExecutor` with `max_workers=5`
- Each source runs independently
- Results stream to Populator as they arrive

### Data Sources Detail

**OpenCorporates** (`_search_opencorporates()`)
- Official company registry data
- 130+ jurisdictions worldwide
- Company numbers, addresses, officers, filing history

**OCCRP Aleph** (`_search_aleph()`)
- Investigative datasets
- Leaked documents (Panama Papers, Paradise Papers, etc.)
- Sanctions lists, criminal databases

**SEC EDGAR** (`_search_edgar()`)
- US public company filings (10-K, 10-Q, 8-K, DEF 14A)
- Historical filings (default: 3 years)
- Financial data, officer compensation

**OpenOwnership** (`_search_openownership()`)
- Beneficial ownership structures
- Ultimate beneficial owners (UBOs)
- Ownership chains

**LinkedIn** (`_search_linkedin()`)
- Company profiles from HuggingFace dataset
- Employee counts, industry classifications
- Website URLs, descriptions

### Output Format
```json
{
    "raw_results": [...],  // Instant display (deterministic)
    "merged_entity": {...}, // AI-processed (Haiku)
    "sources_used": ["opencorporates", "aleph", "edgar", "openownership", "linkedin"],
    "processing_time": 4.2
}
```

## Component 2.5: Populator (AI-Powered Entity Merging)

**File**: `populator.py`
**Purpose**: Hybrid deterministic + Claude Haiku processing

### Hybrid Processing Model

```
Raw Result Arrives from Fetcher
│
├─ FAST PATH (Deterministic)
│  ├─ Extract source badge [OC], [AL], [ED]
│  ├─ Map known fields (name, company_number, jurisdiction)
│  └─ Stream to user immediately
│
└─ SMART PATH (Claude Haiku AI - parallel)
   ├─ Deduplication check (is this officer already listed?)
   ├─ Contradiction detection (different addresses from different sources?)
   ├─ Unexpected data handling (fields that don't fit template)
   └─ Intelligent merging (combine all sources into coherent profile)
```

### Claude Haiku Implementation

```python
class CorporateEntityPopulator:
    def __init__(self):
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

        self.source_badges = {
            "opencorporates": "[OC]",
            "aleph": "[AL]",
            "edgar": "[ED]",
            "openownership": "[OO]",
            "linkedin": "[LI]"
        }

    async def process_streaming_result(self, result: Dict) -> Dict:
        """
        1. Add to accumulated results
        2. Call Haiku to intelligently merge
        3. Return updated entity
        """
        # Deterministic: Extract company ID and source badge
        company_id = self._extract_company_id(result)
        badge = self._get_source_badge(result)

        # AI: Call Claude Haiku for smart merging
        updated_entity = await self._haiku_merge_result(
            current_entity=self.merged_entities[company_id],
            new_result=result,
            all_results=self.accumulated_results[company_id]
        )

        return updated_entity

    async def _haiku_merge_result(self, current_entity, new_result, all_results):
        """Use Claude Haiku 4.5 for intelligent merging"""

        prompt = f"""You are a corporate data integration specialist.

CURRENT ENTITY:
{json.dumps(current_entity, indent=2)}

NEW RESULT TO MERGE:
Source: {new_result['source']} {badge}
{json.dumps(new_result, indent=2)}

ALL RESULTS SO FAR:
{json.dumps(all_results, indent=2)}

INSTRUCTIONS:
1. DEDUPLICATE: Check if this data already exists
2. MERGE: Add new information to appropriate fields
3. SOURCE BADGES: Tag all values with {badge}
4. CONTRADICTIONS: If values conflict, show both: "value1 {badge} | value2 [OTHER]"
5. UNEXPECTED DATA: Add unmapped fields to raw_data section
6. PRESERVE EVERYTHING: Don't lose any information

Return the updated entity as valid JSON."""

        response = self.client.messages.create(
            model="claude-3-5-haiku-20241022",  # Haiku 4.5
            max_tokens=4000,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse JSON response
        json_text = response.content[0].text
        if "```json" in json_text:
            json_text = json_text.split("```json")[1].split("```")[0]

        return json.loads(json_text)
```

### Deduplication Logic

**Deterministic Checks** (Fast Path):
- Exact company number match
- LEI code match
- Normalized name + jurisdiction match

**AI Checks** (Smart Path - Haiku):
- Fuzzy officer name matching ("John Smith" vs "J. Smith")
- Address similarity (different formats, same location)
- Cross-source reconciliation (which source is most authoritative?)

### Contradiction Handling

When sources disagree:
```json
{
    "registered_address": "123 Main St [OC] | 123 Main Street, Suite 100 [ED]",
    "_contradictions": [
        {
            "field": "registered_address",
            "values": [
                {"value": "123 Main St", "source": "opencorporates"},
                {"value": "123 Main Street, Suite 100", "source": "edgar"}
            ]
        }
    ]
}
```

### Fallback Strategy

If Claude Haiku API fails:
```python
def _simple_merge(self, entity: Dict, result: Dict, badge: str) -> Dict:
    """Deterministic fallback - basic field mapping without AI"""
    # Map known fields
    # Append to lists (officers, addresses)
    # No deduplication, no contradiction detection
```

## Component 3: Analyzer (Network & Connections)

**File**: `analyzer.py`
**Purpose**: Analyze company networks through shared officers, addresses, ownership

### Functions

```python
def find_connected_companies(company_number: str, depth: int = 1) -> List[Dict]:
    """Find companies connected through shared officers"""

def analyze_ownership_network(company_number: str) -> Dict:
    """Build ownership hierarchy from OpenOwnership data"""

def find_companies_at_address(address: str) -> List[Dict]:
    """Find all companies registered at same address"""
```

### Network Analysis Algorithm

```python
# Depth-based graph traversal
visited = set()
to_visit = {root_company}

for level in range(depth):
    next_level = set()
    for company in to_visit:
        if company not in visited:
            visited.add(company)
            # Find connections via:
            # - Shared officers
            # - Shared addresses
            # - Ownership relationships
            connections = get_connections(company)
            next_level.update(connections)
    to_visit = next_level - visited
```

### Output Format

```json
{
    "root_company": "Apple Inc",
    "connections": [
        {
            "company": "Apple Operations Europe",
            "connection_type": "shared_officer",
            "shared_entity": "Tim Cook",
            "depth": 1
        },
        {
            "company": "Apple Services LATAM LLC",
            "connection_type": "ownership",
            "ownership_percentage": 100,
            "depth": 1
        }
    ],
    "graph": {
        "nodes": [...],
        "edges": [...]
    }
}
```

## Component 4: Frontend (Real-time UI)

**Files**: `websocket_server.py`, `client.html`
**Purpose**: Real-time streaming UI with progressive enhancement

### WebSocket Server Architecture

```python
class CorporateWebSocketServer:
    async def handle_search_request(self, websocket, message):
        """
        1. Parse search query
        2. Start parallel searches
        3. Stream raw results immediately (Fast Path)
        4. Stream AI-merged entity progressively (Smart Path)
        """

        query = message.get("query")

        # Initialize populator
        populator = CorporateEntityPopulator()

        # Start parallel searches
        fetcher = GlobalCompanyFetcher()

        async for result in fetcher.stream_search(query):
            # Send raw result immediately
            await websocket.send(json.dumps({
                "type": "raw_result",
                "result": result
            }))

            # Process with Haiku in parallel
            merged_entity = await populator.process_streaming_result(result)

            # Send updated merged entity
            await websocket.send(json.dumps({
                "type": "entity_update",
                "entity": merged_entity
            }))
```

### Frontend UI Layout

```html
<div class="container">
    <!-- Left: Raw streaming results (Fast Path) -->
    <div class="raw-results">
        <h3>Raw Results Stream</h3>
        <div id="rawResults">
            <!-- Results appear here as they arrive -->
        </div>
    </div>

    <!-- Right: AI-merged profile (Smart Path) -->
    <div class="merged-entity">
        <h3>Company Profile (Haiku Merged)</h3>
        <div id="companyProfile">
            <!-- Profile gets progressively smarter -->
        </div>
    </div>
</div>
```

### User Experience Flow

```
User submits search
│
├─ 0.2s: First raw results appear (OpenCorporates fastest)
├─ 0.5s: More raw results (EDGAR, Aleph)
├─ 1.0s: Initial merged profile appears (basic fields mapped)
├─ 2.0s: Profile gets smarter (Haiku deduplicated officers)
├─ 3.0s: Contradictions highlighted (addresses differ between sources)
└─ 4.0s: Final comprehensive profile with all sources reconciled
```

## Data Flow Diagram

```
User Query
    │
    ▼
┌───────────────┐
│    Finder     │ ──► Search by criteria
└───────┬───────┘
        │
        ▼
┌───────────────┐
│   Fetcher     │ ──► Parallel search (5 sources)
└───────┬───────┘
        │
        ├─────────────────────────┐
        │                         │
        ▼                         ▼
  [Fast Path]              [Smart Path]
Deterministic             Claude Haiku
    │                         │
    ├─► Instant display       │
    │                         │
    └─────────┬───────────────┘
              │
              ▼
        ┌─────────────┐
        │  Populator  │ ──► Merged entity
        └──────┬──────┘
               │
               ▼
        ┌─────────────┐
        │  Analyzer   │ ──► Network connections
        └──────┬──────┘
               │
               ▼
        ┌─────────────┐
        │   Frontend  │ ──► Real-time UI updates
        └─────────────┘
```

## Entity Template Structure

**File**: `entity_template.json`

```json
{
    "name": "",
    "variations": [],
    "alias": "",
    "node_class": "entity",
    "type": "company",
    "about": {
        "company_number": "",
        "lei": "",
        "founded_year": "",
        "jurisdiction": "",
        "registered_address": "",
        "website": "",
        "industry": "",
        "employee_count": ""
    },
    "officers": [
        {
            "name": "",
            "position": "",
            "appointed_date": "",
            "source": ""
        }
    ],
    "ownership_structure": {
        "shareholders": [],
        "beneficial_owners": []
    },
    "filings": {
        "recent_filings": [],
        "filing_history_url": ""
    },
    "financial_results": {
        "revenue": "",
        "assets": "",
        "fiscal_year": ""
    },
    "activity": "",
    "notes": "",
    "raw_data": {},
    "_sources": [],
    "_contradictions": []
}
```

## Utilities

### Deduplicator (`utils/deduplicator.py`)

```python
class CompanyDeduplicator:
    @staticmethod
    def normalize_company_name(name: str) -> str:
        """
        - Convert to uppercase
        - Remove punctuation
        - Standardize suffixes (LTD → LIMITED, INC → INCORPORATED)
        """

    @staticmethod
    def are_duplicates(result1: Dict, result2: Dict) -> bool:
        """
        Check:
        1. LEI match
        2. Company number match
        3. Fuzzy name + jurisdiction similarity > 85%
        """

    @staticmethod
    def deduplicate(results: List[Dict]) -> List[Dict]:
        """Remove duplicates, keep highest quality result"""
```

### Parallel Executor (`utils/parallel_executor.py`)

```python
class ParallelExecutor:
    def __init__(self, max_workers: int = 5):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    async def execute_parallel(self, tasks: List[Callable]) -> List[Any]:
        """Execute multiple tasks in parallel, return results as they complete"""
```

## Design Principles

1. **Standalone**: No dependencies on main Search Engineer structure
2. **Compact**: Single-purpose, minimal code
3. **Hybrid Processing**: Fast deterministic + smart AI in parallel
4. **Source Attribution**: Every data point tagged with origin
5. **Progressive Enhancement**: Users see results immediately, profile gets smarter over time
6. **Graceful Degradation**: Fallback to deterministic if AI fails

## Future Enhancements (Not Included)

- National registry modules (UK, Germany, etc.)
- Pre-indexed local search (requires bulk data)
- Risk scoring functionality
- Custom data source plugins
- Export to various formats (PDF, Excel, JSON)

## Performance Characteristics

- **First result**: < 0.5s (OpenCorporates is fastest)
- **Full parallel search**: 3-5s (depends on API latencies)
- **Haiku processing**: +1-2s per source (runs in parallel)
- **Total time to comprehensive profile**: ~4-6s

## API Keys Required

- `ANTHROPIC_API_KEY` (required for Haiku merging)
- `OPENCORPORATES_API_KEY` (optional, increases rate limits)
- `ALEPH_API_KEY` (optional, for private datasets)

## Error Handling

- API timeouts: 30s per source, continues with partial results
- Rate limits: Exponential backoff with 3 retries
- API failures: Graceful degradation to deterministic mode
- Malformed data: Logs warning, continues processing
