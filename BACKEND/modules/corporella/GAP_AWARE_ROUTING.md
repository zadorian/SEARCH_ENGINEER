# Gap-Aware Routing - Auto-Fill Missing Data

## Core Principle

**DEFAULT BEHAVIOR: If a field is blank in the company JSON, we're looking for it.**

The system automatically analyzes what's missing and routes searches to fill those gaps.

## How It Works

### Step 1: Analyze Current Entity
```python
current_entity = {
    "name": {"value": "Revolut Ltd"},
    "about": {
        "company_number": "08804411",
        "jurisdiction": "GB",
        "registered_address": {"value": "7 Westferry Circus, London E14 4HD"}
        # website: MISSING
        # founded_year: MISSING
    },
    "officers": [
        {"name": "Nikolay Storonsky"}
    ],
    "ownership_structure": {},  # ← COMPLETELY MISSING!
    "compliance": {
        "regulatory": {"summary": "Authorized by FCA"},
        "sanctions": {}  # ← MISSING!
    }
}
```

### Step 2: Gap Analyzer Detects Missing Fields
```python
gaps = {
    'ownership': ['beneficial_owners', 'shareholders'],
    'regulatory': ['sanctions_check'],
    'company_info': ['website', 'founded_year'],
    'financial': ['revenue', 'assets']
}
```

### Step 3: Auto-Route to Fill Gaps
```python
# System knows we have company_id "08804411" + country "GB"
# System knows we're MISSING ownership data
# → Routes to UK PSC collection (Priority 1)

search_tasks = [
    SearchTask(
        collection_id="2053",
        collection_name="UK People with Significant Control",
        input_type="company_id",
        query_value="08804411",
        priority=1  # Ownership gap = high priority
    ),
    SearchTask(
        collection_id="1303",
        collection_name="HM Treasury Sanctions List",
        input_type="person_name",
        query_value="Nikolay Storonsky",
        priority=1  # Sanctions gap = high priority
    )
]
```

### Step 4: Execute & Populate
Backend executes searches and populates ONLY the missing fields.

## Gap Categories

The analyzer groups missing fields into categories:

### 1. Ownership Gaps
**Fields checked:**
- `ownership_structure.beneficial_owners`
- `ownership_structure.shareholders`
- `ownership_structure.ownership_percentage`

**Routes to:**
- UK PSC (collection 2053) - for UK companies
- Companies House (collection 809) - for `company_owner_person`, `company_owner_company`

### 2. Regulatory Gaps
**Fields checked:**
- `compliance.regulatory.summary`
- `compliance.regulatory.actions`

**Routes to:**
- FCA Register (fca_register) - UK regulatory status
- Includes: `fca_permissions`, `fca_disciplinary_history`

### 3. Sanctions Gaps
**Fields checked:**
- `compliance.sanctions.listed`
- `compliance.sanctions.details`

**Routes to:**
- HM Treasury Sanctions List (collection 1303) - UK sanctions
- Searches for company name + all officer names

### 4. Officers Gaps
**Fields checked:**
- `officers[]` (empty or missing)

**Routes to:**
- Companies House (collection 809) - returns directors with:
  - `person_name`, `person_id`, `person_dob`, `person_nationality`

### 5. Company Info Gaps
**Fields checked:**
- `about.company_number`
- `about.jurisdiction`
- `about.registered_address`
- `about.website`
- `about.founded_year` (mapped to `company_incorporation_date`)

**Routes to:**
- Companies House (collection 809) - most complete UK data
- German Registry (collection 1027) - for DE companies

### 6. Financial Gaps
**Fields checked:**
- `financial_results.revenue`
- `financial_results.assets`
- `financial_results.liabilities`

**Routes to:**
- Companies House (collection 809) - basic financial data
- EDGAR/SEC - for US public companies (when implemented)

## Priority System

Gap-aware router assigns priorities based on:

1. **Data completeness** - More gaps = higher priority
2. **Input precision** - company_id > company_name
3. **Target criticality** - Sanctions > Ownership > Company Info

### Example Priority Assignment

**Scenario: Partial UK company profile with company_id**

```python
Missing: ownership, sanctions
Have: company_id "08804411", jurisdiction "GB"

Priority 1: PSC (ownership) via company_id
Priority 1: Sanctions (compliance) via person_name
Priority 3: Companies House (backup) via company_id
```

## Web App Integration

### Automatic Gap Filling

User enters minimal info:
```
Company Name: Revolut Ltd
Country: GB
```

System:
1. Creates empty entity template
2. Detects ALL fields are missing
3. Routes to fetch everything:
   - Companies House → Basic info + directors
   - PSC → Beneficial ownership
   - FCA → Regulatory status
   - Sanctions → Compliance check

### Progressive Enhancement

User already has partial data:
```json
{
  "name": "Revolut Ltd",
  "about": {
    "company_number": "08804411",
    "jurisdiction": "GB"
  }
}
```

System:
1. Detects ownership + compliance missing
2. Routes ONLY to PSC + Sanctions
3. Skips Companies House (already have basic info)

### Refresh Stale Data

User clicks "Refresh Ownership":
```javascript
// Clear ownership fields
entity.ownership_structure = {};

// Gap analyzer detects ownership missing
// Routes to PSC to re-fetch
```

## API Response Format

```json
{
  "gap_analysis": {
    "missing_fields": {
      "ownership": ["beneficial_owners", "shareholders"],
      "regulatory": ["sanctions_check"],
      "company_info": ["website"]
    },
    "targets": ["ownership", "sanctions"],
    "summary": "Ownership data missing: beneficial_owners, shareholders | Regulatory data missing: sanctions_check"
  },
  "search_plan": [
    {
      "priority": 1,
      "collection": "UK People with Significant Control",
      "input": "company_id: 08804411",
      "will_populate": ["beneficial_owners", "shareholders"]
    },
    {
      "priority": 1,
      "collection": "HM Treasury Sanctions List",
      "input": "person_name: Nikolay Storonsky",
      "will_populate": ["sanctions.details"]
    }
  ],
  "estimated_searches": 2
}
```

## Benefits

### 1. Efficiency
Only fetch what's actually missing - no redundant API calls.

### 2. Smart Defaults
User doesn't specify what they want - system figures it out.

### 3. Progressive Loading
Can show partial results immediately, then fill gaps as data arrives.

### 4. Bandwidth Optimization
Especially important for multi-source searches across many countries.

### 5. User Experience
```
Loading... (25% complete)
✓ Basic company info fetched
✓ Officers list populated
⏳ Fetching ownership structure...
⏳ Running sanctions check...

Loading... (100% complete)
✓ Ownership structure populated
✓ Sanctions check complete
```

## Example Flows

### Flow 1: Empty Entity
```
User provides: "Revolut Ltd, GB"
System detects: EVERYTHING missing
Routes to: 4 collections (Companies House, PSC, FCA, Sanctions)
Populates: Complete profile
```

### Flow 2: Have Company Number
```
User provides: "08804411, GB"
System detects: Everything except company_number missing
Routes to: Same 4 collections but uses company_id (faster)
Populates: Complete profile with higher precision
```

### Flow 3: Partial Profile
```
Current entity: Has basic info + officers
System detects: ONLY ownership + compliance missing
Routes to: 2 collections (PSC, Sanctions)
Populates: Just the gaps
```

### Flow 4: Complete Profile
```
Current entity: All fields populated
System detects: No gaps (or only minor fields like website)
Routes to: MINIMAL or NO searches
Result: Fast response, no unnecessary API calls
```

## Implementation

### In websocket_server.py
```python
from gap_aware_router import GapAwareRouter

router = GapAwareRouter()

# User sends entity (partial or empty)
current_entity = message.get('entity', empty_template)

# Auto-detect gaps and route
report = router.route_with_gaps_report(current_entity)

# Send gap analysis to frontend
await websocket.send(json.dumps({
    'type': 'gap_analysis',
    'missing': report['missing_fields'],
    'summary': report['summary'],
    'searches_planned': report['total_searches']
}))

# Execute searches
for task in report['search_tasks']:
    results = await execute_search(task)
    # Populate entity as results arrive
    entity = populate_entity(entity, results, task.collection_name)

    # Stream updated entity to frontend
    await websocket.send(json.dumps({
        'type': 'entity_update',
        'entity': entity,
        'populated_field': task.collection_name
    }))
```

### In company_profile.html
```javascript
// User enters company name
startSearch("Revolut Ltd", "GB");

// Backend sends gap analysis
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === 'gap_analysis') {
        showProgressBar(data.searches_planned);
        showMissingFields(data.missing);
    }

    if (data.type === 'entity_update') {
        updateProfile(data.entity);
        incrementProgress();
        highlightNewData(data.populated_field);
    }
};
```

## Next Steps

This gap-aware routing is the foundation for:
1. ✅ Automatic target detection
2. ✅ Smart source selection
3. ⏳ Progressive profile building
4. ⏳ Efficient API usage
5. ⏳ Real-time gap visualization in UI
