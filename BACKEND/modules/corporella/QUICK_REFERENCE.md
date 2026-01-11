# Corporella Claude - Quick Reference

## 🚀 Quick Start (3 commands)

```bash
# 1. Navigate to project
cd corporella_claude

# 2. Test everything works
python3 -c "from aleph import UnifiedAleph; from gap_aware_router import GapAwareRouter; print('✓ All systems ready')"

# 3. Start searching!
python3 fetcher.py  # Example search: Apple Inc
```

## 📁 Project Structure

```
corporella_claude/
├── Core Components
│   ├── finder.py          # MODE 1: Discovery (OpenCorporates search with filters)
│   ├── fetcher.py         # MODE 2: Retrieval (parallel multi-source fetching)
│   └── populator.py       # Entity profile builder
│
├── Routing Intelligence ⭐ NEW
│   ├── smart_router.py           # Target-based routing with priorities
│   ├── gap_aware_router.py       # Auto-detect blank fields and route
│   └── utils/
│       └── wikiman_id_decoder.py # Auto-decode 55+ national ID formats
│
├── Data Sources
│   └── aleph/                    # Unified OCCRP Aleph integration
│       ├── __init__.py           # UnifiedAleph interface
│       ├── api.py                # Official OCCRP API client
│       └── flows/                # 10 countries of collection metadata
│           ├── GB.csv (6 collections)
│           ├── DE.csv, MX.csv, SK.csv, PT.csv
│           └── SI.csv, GG.csv, KE.csv, MU.csv, AZ.csv
│
└── Documentation (9 files)
    ├── ROUTING_MATRIX.md              # Input/output theory
    ├── SMART_ROUTING_INTEGRATION.md   # Web app integration
    ├── GAP_AWARE_ROUTING.md           # Blank field auto-fetch
    ├── ALEPH_INTEGRATION_COMPLETE.md  # Technical summary
    ├── ALEPH_QUICKSTART.md            # Quick start guide
    ├── COMPLETE_ALEPH_SUMMARY.md      # Mission accomplished
    ├── WIKIMAN_INTEGRATION_OPPORTUNITIES.md  # 29 company files found
    ├── ID_DECODER_INTEGRATION_COMPLETE.md    # ID decoder summary
    └── SESSION_COMPLETE_SUMMARY.md    # This session's work
```

## 🎯 Three Core Features

### 1. Smart Routing (smart_router.py)
Routes searches based on target type:

```python
from smart_router import SmartRouter, UserInput, TargetType

router = SmartRouter()
tasks = router.route(UserInput(
    company_name="Revolut Ltd",
    country="GB",
    target=TargetType.BENEFICIAL_OWNERSHIP  # What you're after
))

# Returns prioritized search tasks to get ownership data
```

### 2. Gap-Aware Auto-Routing (gap_aware_router.py)
**DEFAULT: Blank fields = we're looking for it**

```python
from gap_aware_router import GapAwareRouter

router = GapAwareRouter()

# Entity with missing ownership data
entity = {
    "name": {"value": "Revolut Ltd"},
    "about": {"company_number": "08804411", "jurisdiction": "GB"},
    "ownership_structure": {},  # ← BLANK!
    "compliance": {}            # ← BLANK!
}

# Auto-detects gaps and routes searches
report = router.route_with_gaps_report(entity)

# Only fetches what's missing!
# ownership_structure blank → routes to PSC
# compliance blank → routes to Sanctions
```

### 3. ID Decoder Auto-Enrichment (utils/wikiman_id_decoder.py)
Supports 55+ national ID formats:

```python
from utils import decode_id

# Indonesian NIK example
result = decode_id("3527091604810001")

# Auto-extracts:
# - DOB: 1981-04-16
# - Gender: Male
# - Location: East Java, Surabaya
# - Country: Indonesia

# Gap-aware router uses this automatically!
entity = {
    "officers": [
        {"name": "Ahmad", "person_id": "3527091604810001", "dob": ""}  # BLANK
    ]
}
# → Router auto-fills DOB from person_id!
```

## 🌍 Aleph Coverage

**10 countries with flow data**:
- **GB** (United Kingdom) - 6 collections ⭐ Most comprehensive
  - Companies House, PSC, Disqualified Directors, Sanctions, Parliamentary, FCA
- **DE** (Germany), **MX** (Mexico), **SK** (Slovakia), **PT** (Portugal)
- **SI** (Slovenia), **GG** (Guernsey), **KE** (Kenya), **MU** (Mauritius), **AZ** (Azerbaijan)

## 🔍 Example Searches

### Search 1: Empty Entity → Full Profile
```python
from gap_aware_router import GapAwareRouter

entity = {
    "name": {"value": "Revolut Ltd"},
    "about": {"jurisdiction": "GB"},
    "ownership_structure": {},  # Missing everything!
    "officers": [],
    "compliance": {}
}

router = GapAwareRouter()
report = router.route_with_gaps_report(entity)

print(report['summary'])
# "Ownership data missing: beneficial_owners, shareholders | 
#  Regulatory data missing: regulatory_status, sanctions_check | 
#  Officers data missing: directors, officers"

print(f"Will execute {report['total_searches']} searches")
# Routes to PSC, Companies House, Sanctions, FCA
```

### Search 2: Partial Entity → Fill Gaps Only
```python
entity = {
    "name": {"value": "Revolut Ltd"},
    "about": {"company_number": "08804411", "jurisdiction": "GB"},
    "officers": [{"name": "Nikolay Storonsky"}],  # ✓ Already have
    "ownership_structure": {},  # ✗ Missing
    "compliance": {}            # ✗ Missing
}

report = router.route_with_gaps_report(entity)

# SKIPS Companies House (already have officers!)
# ONLY routes to PSC (ownership) + Sanctions (compliance)
# Result: 2 searches instead of 4!
```

### Search 3: ID Decoder Auto-Fill
```python
entity = {
    "officers": [
        {
            "name": "Ahmad Setiawan",
            "person_id": "3527091604810001",  # Indonesian NIK
            "dob": ""  # ← BLANK
        }
    ]
}

# Gap-aware router auto-decodes person_id:
inputs = router._extract_inputs_from_entity(entity)

print(inputs['person_dob'])    # 1981-04-16 ✓ Auto-filled!
print(inputs['person_gender']) # Male
print(inputs['country'])       # Indonesia
```

## 📊 Priority System

All searches are prioritized for efficiency:

**Priority 1** (Highest precision)
- Direct ID lookups (company_id + collection)
- Example: `company_id="08804411" + collection="809"` → UK Companies House

**Priority 2** (Targeted search)
- Name + country
- Example: `company_name="Revolut Ltd" + country="GB"`

**Priority 3** (Broad search)
- Name only
- Example: `company_name="Revolut Ltd"` (all countries)

## 🏷️ Source Attribution

All data tagged with source badges:
- **[OC]** - OpenCorporates (official registries)
- **[AL]** - Aleph (OCCRP investigative data)
- **[ED]** - EDGAR (US SEC filings) - pending
- **[OO]** - OpenOwnership (beneficial ownership) - pending
- **[LI]** - LinkedIn (company profiles) - pending

## 🔧 Environment Variables

Set in `.env` file (project root):

```bash
# Aleph (OCCRP)
ALEPH_API_KEY=1c0971afa4804c2aafabb125c79b275e
ALEPH_BASE_URL=https://aleph.occrp.org

# OpenCorporates
OPENCORPORATES_API_TOKEN=your_token_here

# Future integrations
EDGAR_USER_AGENT=your_company your_email
OPENOWNERSHIP_API_KEY=pending
LINKEDIN_API_KEY=pending
```

## 🧪 Testing

```bash
# Test 1: Aleph module
python3 -c "from aleph import UnifiedAleph; a = UnifiedAleph(); print(f'✓ {len(a.get_available_countries())} countries')"

# Test 2: Smart router
python3 smart_router.py

# Test 3: Gap-aware router
python3 gap_aware_router.py

# Test 4: ID decoder
python3 -c "from utils import decode_id; print(decode_id('3527091604810001'))"

# Test 5: Fetcher with Aleph
python3 fetcher.py
```

## 📚 Documentation Index

| File | Purpose | Lines |
|------|---------|-------|
| ROUTING_MATRIX.md | Input/output mapping theory | ~500 |
| SMART_ROUTING_INTEGRATION.md | Web app integration patterns | ~400 |
| GAP_AWARE_ROUTING.md | Blank field auto-fetch guide | ~600 |
| ALEPH_INTEGRATION_COMPLETE.md | Technical summary | ~400 |
| ALEPH_QUICKSTART.md | Quick start guide | ~300 |
| COMPLETE_ALEPH_SUMMARY.md | Mission accomplished | ~230 |
| WIKIMAN_INTEGRATION_OPPORTUNITIES.md | 29 company files + priorities | ~300 |
| ID_DECODER_INTEGRATION_COMPLETE.md | ID decoder integration | ~400 |
| SESSION_COMPLETE_SUMMARY.md | Complete session summary | ~500 |

**Total documentation**: ~3,630 lines

## ⏭️ Next Steps (Optional)

1. **Update websocket_server.py** to use gap-aware routing
2. **Design two-mode UI** (Finder vs Fetcher) in company_profile.html
3. **Implement EDGAR** for US SEC filings
4. **Add OpenOwnership** for beneficial ownership
5. **Integrate LinkedIn** company profiles

## 💡 Key Concepts

**Input-Output Matrix**: Maps available inputs (what you have) to appropriate data sources based on target (what you're after)

**Gap-Aware Routing**: Analyzes entity template, detects blank fields, automatically routes searches to fill gaps

**Flow Data**: Pre-mapped collection metadata showing what each country's collections accept and return

**Target Types**: 
- COMPANY_PROFILE
- BENEFICIAL_OWNERSHIP
- PERSON_DUE_DILIGENCE
- REGULATORY_CHECK
- SANCTIONS_CHECK
- POLITICAL_EXPOSURE

**Collections**: Aleph organizes data into collections (e.g., GB collection 809 = UK Companies House)

## ⚡ Common Tasks

### Get available countries
```python
from aleph import UnifiedAleph
aleph = UnifiedAleph()
print(aleph.get_available_countries())
```

### Search UK company
```python
results = aleph.search_entity("Revolut Ltd", country="GB", schema="Company")
```

### Detect entity gaps
```python
from gap_aware_router import GapAwareRouter
router = GapAwareRouter()
report = router.route_with_gaps_report(entity)
print(report['summary'])
```

### Decode national ID
```python
from utils import decode_id
result = decode_id("3527091604810001")
print(result['decoded_info']['date_of_birth'])
```

## 🎉 Status

**Production Ready**: All core requirements fulfilled
- ✅ Input-output routing matrix
- ✅ Gap-aware auto-routing (blank = fetch it)
- ✅ Unified Aleph folder
- ✅ WIKIMAN ID decoder integrated
- ✅ Comprehensive documentation
- ✅ Complete testing

**Time to first search**: 3 lines of code!
