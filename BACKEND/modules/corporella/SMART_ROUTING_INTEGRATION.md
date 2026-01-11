# Smart Routing Integration for Corporella Web App

## What We Built

**Smart Router** (`smart_router.py`) - An input/output matrix that routes searches to the right data sources based on:
1. **What you're searching for** (company profile, ownership, person DD, regulatory, sanctions)
2. **What data you have** (name, ID, DOB, country)
3. **What's available** (collections per country from flow data)

## How It Works

### User fills out web form with:
```javascript
{
  company_name: "Revolut Ltd",
  company_id: "08804411",      // optional
  person_name: "Nik Storonsky", // optional
  person_dob: "1984-07-21",     // optional
  country: "GB",
  target: "ownership"           // what they want
}
```

### Smart Router returns prioritized search plan:
```python
[
  SearchTask(
    country="GB",
    collection_id="2053",
    collection_name="UK People with Significant Control",
    input_type="company_id",
    query_value="08804411",
    expected_schema="Company",
    priority=1  # Execute first
  ),
  SearchTask(
    country="GB",
    collection_id="809",
    collection_name="UK Companies House",
    input_type="company_id",
    query_value="08804411",
    expected_schema="Company",
    priority=2  # Execute second
  )
]
```

### Backend executes searches in priority order:
1. PSC collection → Gets beneficial owners
2. Companies House → Gets company profile + directors

### Results merged and displayed in structured profile UI

## Target Types Available

| Target | What It Does | Collections Used (GB example) |
|--------|-------------|-------------------------------|
| `company_profile` | Full company information | Companies House (809), PSC (2053), FCA (fca_register) |
| `ownership` | Beneficial ownership structure | PSC (2053) first, then Companies House (809) |
| `person_dd` | Person due diligence check | Sanctions (1303), Disqualified (2302), Parliamentary (153), Companies House (809) |
| `regulatory` | Regulatory status and history | FCA Register (fca_register) |
| `sanctions` | Sanctions screening | HM Treasury Sanctions (1303) |
| `political_exposure` | Political exposure check | Parliamentary Inquiries (153) |
| `generic` | Search everything | All relevant collections |

## Priority Rules

The router assigns priorities based on data quality:

### Highest Priority (1): Direct ID lookups
- Have company_id → Direct Companies House lookup
- Have person_id → Direct person lookup
- **Why**: Most accurate, no ambiguity

### Medium Priority (2): Name searches in specialized collections
- company_name + target="ownership" → PSC first
- person_name + target="sanctions" → Sanctions list first
- **Why**: Targeted search with clear intent

### Lower Priority (3): Broad name searches
- company_name without specific target → All company collections
- person_name without specific target → All person collections
- **Why**: Exploratory, may return multiple matches

## Web App Integration

### Two-Mode UI

#### MODE 1: FINDER (Discovery)
User starts with minimal info, router helps narrow down:

```javascript
// User enters:
{ company_name: "Revolut", country: "GB" }

// Router returns multiple candidates:
[
  { name: "Revolut Ltd", company_id: "08804411", status: "Active" },
  { name: "Revolut Bank UAB", company_id: "...", status: "Active" },
  { name: "Revolut Inc", company_id: "...", status: "Active" }
]

// User clicks one → Switches to MODE 2 with company_id
```

#### MODE 2: FETCHER (Direct Retrieval)
User has specific details, router optimizes fetching:

```javascript
// User provides:
{
  company_id: "08804411",
  country: "GB",
  target: "ownership"
}

// Router knows:
// 1. Use PSC collection (2053) for ownership
// 2. Use company_id input (highest precision)
// 3. Priority 1 execution

// Result: Fastest, most accurate fetch
```

## Filter Exposure

The router exposes ALL available filters per collection:

### Company Filters (from flow data)
- `company_name` - Name search
- `company_id` - Official registration number
- `company_country` - Country code
- `company_jurisdiction` - Specific jurisdiction
- `company_status` - Active/Dissolved/etc
- `company_incorporation_date` - Date range
- `company_dissolution_date` - Date range

### Person Filters
- `person_name` - Name search
- `person_id` - Official ID
- `person_dob` - Date of birth (when available)
- `person_nationality` - Nationality
- `person_country` - Country of residence

### Special Filters
- `fca_permissions` - FCA regulated permissions
- `fca_disciplinary_history` - Regulatory violations
- `collection_id` - Specific collection to search

## Example: Complete Flow

User wants to research "Revolut Ltd" ownership structure:

### Step 1: User Input (Web Form)
```
Company Name: Revolut Ltd
Country: GB
I want to find: [Beneficial Ownership ▼]
```

### Step 2: Smart Router Decides
```python
router = SmartRouter()
tasks = router.route(UserInput(
    company_name="Revolut Ltd",
    country="GB",
    target=TargetType.BENEFICIAL_OWNERSHIP
))

# Returns:
# Priority 2: UK PSC - search by company_name
# Priority 3: UK Companies House - search by company_name
# Priority 3: FCA Register - search by company_name
```

### Step 3: Backend Executes
```python
async def execute_search(tasks):
    results = {}

    # Execute priority 2 first (PSC)
    psc_results = await aleph.search(
        collection_id="2053",
        query="Revolut Ltd",
        filters={"schema": "Company"}
    )
    results['beneficial_ownership'] = psc_results

    # Execute priority 3 tasks in parallel
    ch_results, fca_results = await asyncio.gather(
        aleph.search(collection_id="809", query="Revolut Ltd"),
        aleph.search(collection_id="fca_register", query="Revolut Ltd")
    )
    results['company_profile'] = ch_results
    results['regulatory'] = fca_results

    return results
```

### Step 4: Results Displayed
```
✅ UK People with Significant Control [ALEPH:2053]
   Beneficial Owners:
   • Nikolay Storonsky (58.4%) - Russian
   • Vlad Yatsenko (20.1%) - Ukrainian

✅ UK Companies House [ALEPH:809]
   Company: Revolut Ltd
   Number: 08804411
   Status: Active
   Incorporated: 2015-07-03
   Directors: Nikolay Storonsky, Vlad Yatsenko, ...

✅ FCA Register [FCA]
   Status: Authorized
   Permissions: Electronic Money Institution
   No disciplinary history
```

## Country Coverage

From flow data, we have routing rules for:
- **GB** (6 collections) - Most comprehensive
- **DE** (1 collection) - German registry
- **MX** (1 collection) - Personas de Interes
- **SK, PT, SI, GG, KE, MU, AZ** - To be loaded

When user searches without country specified, router searches ALL available countries and returns results grouped by jurisdiction.

## Next Steps

1. ✅ **DONE**: Created routing matrix documentation (ROUTING_MATRIX.md)
2. ✅ **DONE**: Built smart router (smart_router.py) with priority system
3. ⏳ **TODO**: Copy flow data to corporella_claude/aleph/flows/
4. ⏳ **TODO**: Copy official Aleph API client to corporella_claude/aleph/
5. ⏳ **TODO**: Create aleph/__init__.py that uses SmartRouter
6. ⏳ **TODO**: Update websocket_server.py to use SmartRouter
7. ⏳ **TODO**: Update company_profile.html UI with target selector and country checkboxes
8. ⏳ **TODO**: Wire up MODE 1 (Finder) vs MODE 2 (Fetcher) UI toggle

## Key Benefits

1. **User doesn't need to know which collection to search** - Router decides
2. **Optimal performance** - Only searches relevant collections
3. **Country-aware** - Leverages country-specific data sources
4. **Input-aware** - Uses best available input type (ID > name)
5. **Target-aware** - Prioritizes collections based on what user wants
6. **Extensible** - Easy to add new countries/collections from flow data
