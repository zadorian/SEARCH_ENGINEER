# Contradiction Handling in Corporella Claude

## Overview

The hybrid deterministic + Haiku approach now handles three scenarios when merging data from multiple sources:

1. **SAME DATA** → Append source badges
2. **SIMILAR VERSIONS** → Consolidate to best version + append badges
3. **CONTRADICTIONS** → Highlight both values in red + add to `_contradictions` array

---

## 1. SAME DATA → Append Badges

**Scenario**: Multiple sources confirm identical data

**Example**:
```json
// OpenCorporates returns:
{"name": "Apple Inc"}

// Aleph returns:
{"name": "Apple Inc"}

// Result:
{
  "name": {
    "value": "Apple Inc",
    "source": "[OC] [AL]"  // ✅ Both badges appended
  }
}
```

**Implementation**: Deterministic merge function (`_deterministic_merge()`) checks if values match and appends badges:

```python
if not entity["name"].get("value"):
    # First time - set value and source
    entity["name"]["value"] = company["name"]
    entity["name"]["source"] = badge
else:
    # Value already exists - check if same name, append badge
    if company["name"].strip().lower() == entity["name"]["value"].strip().lower():
        if badge not in entity["name"]["source"]:
            entity["name"]["source"] += f" {badge}"
```

**Fields with this logic**:
- ✅ `name.value` (OpenCorporates)
- ✅ `name.value` (Aleph)
- ✅ `about.registered_address.value` (OpenCorporates)
- ✅ `about.registered_address.value` (Aleph)
- ✅ `about.website.value` (Aleph)
- ✅ `about.contact_details.phone.value` (Aleph)
- ✅ `about.contact_details.email.value` (Aleph)

---

## 2. SIMILAR VERSIONS → Consolidate + Append Badges

**Scenario**: Data is similar but one source has more detail

**Example**:
```json
// OpenCorporates returns:
{"registered_address": "123 Main St"}

// Aleph returns:
{"registered_address": "123 Main Street, Suite 100, Floor 5"}

// Haiku consolidates to most complete version:
{
  "about": {
    "registered_address": {
      "value": "123 Main Street, Suite 100, Floor 5",  // ✅ Most detailed version
      "source": "[OC] [AL]"  // ✅ Both badges
    }
  }
}
```

**Implementation**:
1. Deterministic merge: If addresses are similar (after normalization), appends badge
2. Haiku validation: Chooses the most detailed version and consolidates badges

**Haiku instruction**:
```
2. DEDUPLICATE & CONSOLIDATE: Are there duplicate or similar values across sources?
   - SAME DATA: "Apple Inc" from [OC] and "Apple Inc" from [AL] → consolidate to one value with "[OC] [AL]"
   - SIMILAR VERSIONS: "123 Main St" vs "123 Main Street, Suite 100" → choose most complete version, append both badges
   - Keep the most detailed/complete version of the data
```

---

## 3. CONTRADICTIONS → Highlight + Flag

**Scenario**: Sources provide conflicting data that can't be versions of each other

**Example**:
```json
// OpenCorporates returns:
{"jurisdiction": "us_ca"}

// Aleph returns:
{"jurisdiction": "us_de"}

// Result - BOTH values kept, highlighted in red:
{
  "about": {
    "jurisdiction": "us_ca [OC] | us_de [AL]"  // ⚠️ Both kept with pipe separator
  },
  "_contradictions": [  // ✅ Flagged for user review
    {
      "field": "about.jurisdiction",
      "values": [
        {"value": "us_ca", "source": "[OC]"},
        {"value": "us_de", "source": "[AL]"}
      ],
      "highlight": "red"  // 🔴 UI should highlight this field
    }
  ]
}
```

**Implementation**: Haiku detects contradictions and adds to `_contradictions` array

**Haiku instruction**:
```
3. DETECT CONTRADICTIONS: Do multiple sources give DIFFERENT values that can't be versions of each other?
   - Example: jurisdiction="us_ca" [OC] vs jurisdiction="us_de" [AL] ← CONTRADICTION!
   - When you find a contradiction:
     a) Add a "_contradictions" array to the entity if it doesn't exist
     b) Add entry: {"field": "about.jurisdiction", "values": [{"value": "us_ca", "source": "[OC]"}, {"value": "us_de", "source": "[AL]"}], "highlight": "red"}
     c) In the main field, keep BOTH values separated by " | " with their badges: "us_ca [OC] | us_de [AL]"
```

**Schema**:
```python
"_contradictions": {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "field": {"type": "string"},
            "values": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "source": {"type": "string"}
                    }
                }
            },
            "highlight": {"type": "string"}  // "red" for UI highlighting
        }
    }
}
```

---

## UI Display Requirements

### For Normal Fields:
- Display clean value
- Show source badge in top-right corner: `[OC]` or `[OC] [AL]`

### For Contradictions (`_contradictions` array exists):
1. **Highlight field in red** - entire field should have red background
2. **Add arrow indicator** - pointing to the field
3. **Add "contradiction" label** - visible indicator
4. **Show both values** - display as: `value1 [OC] | value2 [AL]`
5. **🔴 RED SOURCE BADGES** - The source badges for contradicting values MUST be RED

**Example HTML**:
```html
<div class="field-group contradiction">
  <label>Jurisdiction ⚠️ CONTRADICTION</label>
  <div class="value-with-contradiction">
    <span>us_ca <span class="badge badge-contradiction">[OC]</span></span>
    <span class="separator">|</span>
    <span>us_de <span class="badge badge-contradiction">[AL]</span></span>
  </div>
  <div class="contradiction-notice">
    ⬆️ Multiple sources provide different values - verify manually
  </div>
</div>
```

**CSS**:
```css
.contradiction {
  background-color: #fee;
  border-left: 4px solid #d00;
  padding: 10px;
}

.contradiction-notice {
  color: #d00;
  font-weight: bold;
  margin-top: 5px;
}

.value-with-contradiction .separator {
  color: #d00;
  font-weight: bold;
  margin: 0 10px;
}

/* 🔴 RED BADGES FOR CONTRADICTIONS */
.badge-contradiction {
  background-color: #d00 !important;
  color: white !important;
  border: 2px solid #a00 !important;
  font-weight: bold;
}
```

---

## Visual Comparison: Normal vs Contradiction

### Normal Field (Same Data from Multiple Sources)
```
┌────────────────────────────────────────┐
│ Company Name                           │
│ Apple Inc              [OC] [AL]       │  ← Green badges (normal)
│                                        │
└────────────────────────────────────────┘
```

### Contradiction Field (Different Data from Sources)
```
┌────────────────────────────────────────┐
│ Jurisdiction ⚠️ CONTRADICTION          │
│                                        │
│ us_ca [OC] | us_de [AL]               │  ← 🔴 RED badges!
│       ^^^^       ^^^^                  │
│       RED        RED                   │
│                                        │
│ ⬆️ Multiple sources provide different  │
│    values - verify manually            │
│                                        │
└────────────────────────────────────────┘
    ↑
    Red background, red border
```

**Key differences**:
1. **Normal**: Green/blue badges, clean display
2. **Contradiction**: 🔴 RED badges, red background, warning arrow, explanation text

---

## Processing Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: DETERMINISTIC MERGE (Fast, Free)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  For each new result:                                           │
│    1. Check if field is empty → set value + badge              │
│    2. Check if field has value:                                 │
│       a) Same value? → append badge "[OC] [AL]"                │
│       b) Different value? → leave for Haiku                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: HAIKU VALIDATION (Smart, Catches Everything)           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Haiku analyzes all fields:                                     │
│    1. Check completeness (missed fields?)                       │
│    2. Deduplicate & consolidate similar values                  │
│    3. Detect contradictions:                                    │
│       • Can't be versions of each other?                        │
│       • Add to _contradictions array                            │
│       • Keep both values with " | " separator                   │
│    4. Deduplicate officers                                      │
│    5. Validate source badges on all fields                      │
│    6. Extract hidden data                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ RESULT                                                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  • Clean values with source badges                              │
│  • Multiple sources appended: "[OC] [AL]"                       │
│  • Contradictions highlighted + flagged                         │
│  • Nothing lost (all raw data preserved)                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Example Entity with Contradictions

```json
{
  "id": "C0806592",
  "name": {
    "value": "Apple Inc",
    "source": "[OC] [AL]"
  },
  "about": {
    "company_number": "C0806592",
    "incorporation_date": "1977-01-03",
    "jurisdiction": "us_ca [OC] | us_de [AL]",  // ⚠️ CONTRADICTION
    "registered_address": {
      "value": "One Apple Park Way, Cupertino, CA 95014",
      "source": "[OC] [AL]"
    }
  },
  "officers": [
    {
      "type": "executive",
      "name": "Tim Cook",
      "details": "Position: CEO, Appointed: 2011-08-24",
      "source": "[OC] [AL]"
    }
  ],
  "_contradictions": [
    {
      "field": "about.jurisdiction",
      "values": [
        {"value": "us_ca", "source": "[OC]"},
        {"value": "us_de", "source": "[AL]"}
      ],
      "highlight": "red"
    }
  ],
  "_sources": ["[OC]", "[AL]"],
  "raw_data": {
    "opencorporates_raw": [...],
    "aleph_raw": [...]
  }
}
```

---

## Testing

To test contradiction handling:

1. Search for a company in multiple jurisdictions (e.g., multinational with subsidiaries)
2. Check if same company registered in different states/countries
3. Verify:
   - Deterministic merge appends badges for matching data
   - Haiku consolidates similar versions
   - Haiku flags contradictions in `_contradictions` array
   - UI highlights contradictions in red

---

## Summary

✅ **Same data** → Append badges deterministically (fast, free)
✅ **Similar versions** → Haiku consolidates to best version
✅ **Contradictions** → Haiku flags + highlights in red + adds to `_contradictions` array
✅ **Nothing lost** → All raw data preserved for manual review
✅ **User friendly** → Clear visual indicators for contradictions in UI
