# Dynamic Flow Integration Complete ✅

## Date: 2025-11-02
## Status: **BIDIRECTIONAL FLOW SYSTEM OPERATIONAL**

---

## SUMMARY

Corporella Claude now has a **bidirectional dynamic flow system** that:
- **Forward Flow**: When we find an ID/input → Shows buttons to fetch what that ID can retrieve
- **Reverse Flow**: When we have empty slots → Shows what inputs would fill those slots
- **ID Decoder**: Automatically decodes 55+ national ID formats with detailed info
- **Dynamic Actions**: Actions appear dynamically based on detected inputs and missing data

---

## KEY ACHIEVEMENTS

### 1. ID Decoder Integration (`utils/id_decoder.py`)
- ✅ Supports 55+ national ID formats
- ✅ Auto-detects and validates IDs
- ✅ Extracts metadata (DOB, gender, location codes)
- ✅ Examples:
  - Indonesian NIK: Extracts birth date, gender, district
  - Brazilian CNPJ/CPF: Validates and formats
  - Swedish Personnummer: Extracts DOB, gender, checksum
  - China National ID: Province, DOB, gender

### 2. Dynamic Flow Router (`utils/dynamic_flow_router.py`)
- ✅ Maps inputs to outputs (what we HAVE → what we can GET)
- ✅ Maps slots to inputs (what we NEED → what would FILL them)
- ✅ Analyzes entire entities for opportunities
- ✅ Supports multiple jurisdictions and ID types

### 3. Jurisdiction Actions Enhanced (`jurisdiction_actions.py`)
- ✅ Integrated with flow router
- ✅ Generates dynamic actions based on entity data
- ✅ Shows both fetch actions and slot-fill suggestions
- ✅ Priority-based action ordering

### 4. WebSocket Integration (`websocket_server.py`)
- ✅ Passes entity data to action generator
- ✅ Includes flow actions in search results
- ✅ Works with both cached and fresh searches

---

## HOW IT WORKS

### Forward Flow: ID → Actions
When we detect an ID (CNPJ, CIK, NIK, etc.):
```python
# Detected: Brazilian CNPJ "11.222.333/0001-81"
Actions generated:
→ Fetch Brazilian company from Receita Federal
→ Shows decoded info (valid, formatted)
```

### Reverse Flow: Empty Slot → Requirements
When we find empty slots:
```python
# Empty slot: "officers"
Suggestions:
← Need: company_number (example: 12345678)
← Need: company_name (example: Apple Inc)
```

---

## SUPPORTED FLOW MAPPINGS

| Input Type | Jurisdiction | Fills Slots | Fetcher |
|------------|--------------|-------------|---------|
| company_number | GB | officers, address, filings | UK Companies House |
| CNPJ | BR | name, address, status | Brazil Receita Federal |
| NIK | ID | officers, beneficial_owners | Indonesia Person Lookup |
| CIK | US | filings, revenue, officers | SEC EDGAR |
| VAT Number | EU | name, address, tax status | EU VIES |
| LEI | Global | parent, ultimate_parent | GLEIF |
| Domain | Global | website, emails, phones | Domain Intel |

---

## ACTION TYPES

### 1. Standard Actions (Priority 1-5)
- Registry links
- DDG bangs
- API fetches
- OpenCorporates
- OCCRP Aleph

### 2. Flow Actions (Priority 6)
- `flow_fetch`: Fetch data using detected ID
- Shows decoded information
- Example: "Fetch Brazilian company (CNPJ validated)"

### 3. Slot Fill Suggestions (Priority 7)
- `slot_fill`: Shows what input is needed
- Provides examples
- Example: "Need: company_number to fill officers"

---

## TESTING RESULTS

Running `test_dynamic_flow_actions.py`:

```
✅ Brazilian CNPJ decoded and actions generated
✅ Empty slots trigger fill suggestions
✅ Indonesian NIK decoded (DOB: 1981-04-16, Male)
✅ US CIK triggers EDGAR actions
✅ Empty entity shows all missing data requirements
```

---

## USAGE IN FRONTEND

### 1. Detected IDs Show Fetch Buttons
```javascript
// When CNPJ detected in entity
[🔄 Fetch Brazilian company data for CNPJ 11.222.333/0001-81]
```

### 2. Empty Slots Show Requirements
```javascript
// Click in empty "officers" field
[🔍 Need: company_number (example: 12345678)]
[🔍 Need: company_name (example: Apple Inc)]
```

### 3. Dynamic Actions in Response
```javascript
{
  "jurisdiction_actions": [
    // Standard actions
    {"type": "link", "label": "🌐 UK Official Registry"},
    {"type": "search", "label": "🔍 Search UK Companies House"},

    // Flow actions (from detected IDs)
    {"type": "flow_fetch", "label": "🔄 Fetch from UK Companies House"},

    // Slot fill suggestions (for empty fields)
    {"type": "slot_fill", "label": "🔍 Need: company_number"}
  ]
}
```

---

## FILES MODIFIED/CREATED

1. **utils/id_decoder.py** - ID decoding system (copied from corporella_codex)
2. **utils/dynamic_flow_router.py** - Bidirectional flow mapping (new)
3. **jurisdiction_actions.py** - Enhanced with flow analysis
4. **websocket_server.py** - Passes entity data for analysis
5. **test_dynamic_flow_actions.py** - Comprehensive test suite

---

## NEXT STEPS FOR FRONTEND

1. **Handle flow_fetch actions**:
   - Send to WebSocket with action type and input value
   - Server executes appropriate fetcher

2. **Handle slot_fill actions**:
   - Show input field with example placeholder
   - When user provides input, trigger search

3. **Visual indicators**:
   - 🔄 for flow actions (detected inputs)
   - 🔍 for slot fills (missing data)

---

## BENEFITS

1. **Smart Actions**: Only shows relevant actions based on available data
2. **Data Discovery**: Automatically identifies what can be fetched
3. **Gap Identification**: Shows exactly what's missing and how to get it
4. **ID Intelligence**: Decodes and validates national IDs automatically
5. **Bidirectional**: Works both ways - from data we have AND data we need

---

**Status**: ✅ Complete and Working
**Test Script**: `test_dynamic_flow_actions.py`
**Integration**: Native to Corporella, ready for frontend implementation