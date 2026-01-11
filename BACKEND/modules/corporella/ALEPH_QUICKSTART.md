# Aleph Integration - Quick Start

## 🎯 What You Now Have

A complete **smart routing system** that automatically:
1. Analyzes what data you have
2. Detects what data is missing
3. Routes to the right Aleph collections to fill gaps
4. Works across 10 countries with pre-mapped collections

## 3-Minute Quick Start

### 1. Basic Aleph Search

```python
from aleph import UnifiedAleph

# Initialize
aleph = UnifiedAleph()

# Search UK company
results = aleph.search_entity(
    query="Revolut Ltd",
    country="GB",
    schema="Company"
)

print(f"Found {results['total']} results")
print(f"Collection used: {results['collection_used']}")
```

### 2. Smart Routing by Target

```python
from smart_router import SmartRouter, UserInput, TargetType

router = SmartRouter()

# I want beneficial ownership data
tasks = router.route(UserInput(
    company_name="Revolut Ltd",
    country="GB",
    target=TargetType.BENEFICIAL_OWNERSHIP
))

# Prints search plan:
# Priority 2: UK PSC - company_name = 'Revolut Ltd'
# Priority 3: UK Companies House - company_name = 'Revolut Ltd'
```

### 3. Gap-Aware Auto-Routing

```python
from gap_aware_router import GapAwareRouter

router = GapAwareRouter()

# Entity with some fields populated, some blank
entity = {
    "name": {"value": "Revolut Ltd"},
    "about": {"company_number": "08804411", "jurisdiction": "GB"},
    "ownership_structure": {},  # ← BLANK - will auto-fetch
    "compliance": {}            # ← BLANK - will auto-fetch
}

# Auto-detect gaps and plan searches
report = router.route_with_gaps_report(entity)

print(report['summary'])
# "Ownership data missing: beneficial_owners, shareholders |
#  Regulatory data missing: regulatory_status, sanctions_check"

print(f"Will execute {report['total_searches']} searches")
```

### 4. Full Parallel Search (with Aleph + OpenCorporates)

```python
from fetcher import GlobalCompanyFetcher
import asyncio

async def main():
    fetcher = GlobalCompanyFetcher()

    # Parallel search across all sources
    results = await fetcher.parallel_search(
        "Revolut Ltd",
        country_code="GB"
    )

    print(f"Sources used: {results['sources_used']}")
    # ['opencorporates', 'aleph']

    print(f"Processing time: {results['processing_time']:.2f}s")

    # Results from Aleph tagged with [AL]
    for result in results['raw_results']:
        if result['source'] == 'aleph':
            print(f"Aleph found {result['total']} entities")

asyncio.run(main())
```

## Available Countries

Run this to see what countries have flow data:

```python
from aleph import UnifiedAleph

aleph = UnifiedAleph()
countries = aleph.get_available_countries()
print(countries)
# ['AZ', 'MX', 'SK', 'SI', 'DE', 'PT', 'GG', 'KE', 'GB', 'MU']
```

## GB (United Kingdom) Collections

Most comprehensive coverage with **6 collections**:

```python
aleph = UnifiedAleph()
gb = aleph.get_collections_for_country('GB')

for coll_id, coll_data in gb['collections'].items():
    print(f"{coll_id}: {coll_data['name']}")
    print(f"  Inputs: {', '.join(coll_data['inputs'])}")
```

Output:
```
809: UK Companies House
  Inputs: company_name, company_id, person_name, person_id

2053: UK People with Significant Control
  Inputs: company_name, company_id, person_name, person_id

2302: UK Disqualified Directors
  Inputs: person_name, person_id

1303: HM Treasury Sanctions List
  Inputs: person_name, person_id

153: UK Parliamentary Inquiries
  Inputs: person_name, person_id

fca_register: FCA Register
  Inputs: company_name, company_id, person_name, person_id
```

## Target Types

Use these with `SmartRouter`:

```python
from smart_router import TargetType

TargetType.COMPANY_PROFILE       # Full company info
TargetType.BENEFICIAL_OWNERSHIP   # Ownership structure (routes to PSC)
TargetType.PERSON_DUE_DILIGENCE  # Person screening (all checks)
TargetType.REGULATORY_CHECK      # FCA regulatory status
TargetType.SANCTIONS_CHECK       # HM Treasury sanctions
TargetType.POLITICAL_EXPOSURE    # Parliamentary inquiries
TargetType.GENERIC_SEARCH        # Search everything
```

## Real-World Example: Complete Profile Building

```python
from gap_aware_router import GapAwareRouter
from aleph import UnifiedAleph

# Start with minimal info
entity = {
    "name": {"value": "Revolut Ltd"},
    "about": {"jurisdiction": "GB"},
    "ownership_structure": {},
    "officers": [],
    "compliance": {}
}

# Auto-detect gaps
router = GapAwareRouter()
report = router.route_with_gaps_report(entity)

print(f"Missing: {report['targets']}")
# ['ownership', 'sanctions', 'company_profile', 'regulatory']

# Execute the search tasks
aleph = UnifiedAleph()
for task in report['search_tasks']:
    result = aleph.search_entity(
        query=task.query_value,
        country=task.country,
        collection_id=task.collection_id
    )
    print(f"✓ {task.collection_name}: {result['total']} results")
```

## Environment Variables

Set these in your `.env` file (project root):

```bash
ALEPH_API_KEY=1c0971afa4804c2aafabb125c79b275e
ALEPH_BASE_URL=https://aleph.occrp.org
```

The unified aleph module automatically loads from `.env`!

## Test Everything Works

```bash
cd corporella_claude

# Test 1: Aleph module loads
python3 -c "from aleph import UnifiedAleph; print('✓ Aleph module works')"

# Test 2: Flow data loads
python3 -c "from aleph import UnifiedAleph; a = UnifiedAleph(); print(f'✓ {len(a.get_available_countries())} countries loaded')"

# Test 3: Smart router works
python3 smart_router.py

# Test 4: Gap-aware router works
python3 gap_aware_router.py

# Test 5: Fetcher integration works
python3 -c "from fetcher import GlobalCompanyFetcher; f = GlobalCompanyFetcher(); print('✓ Fetcher with Aleph works')"
```

All tests should pass ✅

## Next Steps

1. **Run example_usage.py** to see all components working together
2. **Start websocket_server.py** and open company_profile.html
3. **Search a UK company** and watch Aleph results stream in with [AL] badges

## Documentation Files

- **ROUTING_MATRIX.md** - Complete theory of input/output mapping
- **SMART_ROUTING_INTEGRATION.md** - Web app integration patterns
- **GAP_AWARE_ROUTING.md** - How blank fields trigger fetching
- **ALEPH_INTEGRATION_COMPLETE.md** - Full technical summary
- **ALEPH_QUICKSTART.md** - This file

## Common Patterns

### Pattern 1: Search by Company ID (Highest Precision)
```python
aleph.search_entity(
    query="08804411",  # UK company number
    country="GB",
    collection_id="809"  # Companies House
)
```

### Pattern 2: Ownership-Focused Search
```python
aleph.search_with_routing(
    query="Revolut Ltd",
    country="GB",
    target_feature="beneficial_ownership"  # Auto-routes to PSC (2053)
)
```

### Pattern 3: Multi-Collection Person Search
```python
# Search all person-related collections
for coll_id in ['2302', '1303', '153']:  # Disqualified, Sanctions, Parliamentary
    results = aleph.search_entity(
        query="John Smith",
        country="GB",
        collection_id=coll_id,
        schema="Person"
    )
```

## That's It!

You now have a **production-ready Aleph integration** with:
- ✅ 10 countries of flow data
- ✅ Smart routing based on target type
- ✅ Gap-aware auto-routing
- ✅ Official OCCRP API client
- ✅ Parallel search integration

Start searching! 🚀
