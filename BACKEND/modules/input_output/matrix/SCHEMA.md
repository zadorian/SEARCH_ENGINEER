# IO Matrix - Single Source of Truth Schema

## THE LAW: One Place for Everything

When adding something new, there is **ONE obvious place** to add it.
No duplication. No ambiguity.

---

## THE FILES

### 1. `sources.json` - PRIMARY SOURCES

**What goes here:** Every external data source (registries, APIs, breach datasets, collections)

**ID scheme:**
- Web sources → normalized domain (`companieshouse.gov.uk`)
- Breach datasets → collection name (`linkedin-2021-breach`)
- Named collections → collection name (`panama-papers`)

```json
{
  "companieshouse.gov.uk": {
    "name": "Companies House",
    "type": "registry",
    "jurisdiction": "GB",
    "url": "https://find-and-update.company-information.service.gov.uk",
    "search_url": "https://find-and-update.company-information.service.gov.uk/search",
    "inputs": [13, 14],
    "outputs": [42, 43, 47, 49, 50, 59],
    "friction": "open",
    "handled_by": "corporella"
  },
  "linkedin-2021-breach": {
    "name": "LinkedIn 2021 Data Breach",
    "type": "breach",
    "jurisdiction": "GLOBAL",
    "inputs": [1, 3],
    "outputs": [187, 188],
    "friction": "paywalled",
    "handled_by": "eye-d",
    "aggregator": "dehashed.com"
  }
}
```

**Adding a new source?** Add it here. Done.

---

### 2. `modules.json` - OUR CODE (hidden from user)

**What goes here:** Our modules that execute lookups

**ID scheme:** module name (`eye-d`, `corporella`, `torpedo`)

```json
{
  "eye-d": {
    "name": "EYE-D OSINT Platform",
    "path": "BACKEND/modules/EYE-D/",
    "inputs": [1, 2, 3, 6, 7],
    "outputs": [187, 188, 189, 190, 191],
    "aggregators": ["dehashed.com", "rocketreach.co", "osint.industries"]
  },
  "corporella": {
    "name": "Corporella Company Intelligence",
    "path": "BACKEND/modules/corporella/",
    "inputs": [13, 14, 15, 16],
    "outputs": [42, 43, 44, 45, 46, 47, 48, 49, 50, 59],
    "aggregators": ["opencorporates.com"]
  },
  "torpedo": {
    "name": "Torpedo Profile Scraper",
    "path": "BACKEND/modules/JESTER/",
    "inputs": [13, 14],
    "outputs": [42, 43, 47, 49, 50],
    "learning": true,
    "note": "Scrapes, Haiku extracts, improves country JSON"
  }
}
```

**Adding a new module?** Add it here. Done.

---

### 3. `codes.json` - THE LEGEND

**What goes here:** What each numeric code means

**ID scheme:** numeric code

```json
{
  "1": {"name": "email", "type": "identity", "creates": "node"},
  "2": {"name": "phone", "type": "identity", "creates": "node"},
  "7": {"name": "person_name", "type": "entity", "creates": "node"},
  "13": {"name": "company_name", "type": "entity", "creates": "node"},
  "14": {"name": "company_reg_id", "type": "identifier", "creates": "metadata"},
  "42": {"name": "company_name_output", "type": "entity", "creates": "node"},
  "49": {"name": "company_status", "type": "metadata", "attaches_to": "company"},
  "59": {"name": "officer_name", "type": "entity", "creates": "node", "edge": "officer_of"},
  "187": {"name": "breach_record", "type": "dataset", "creates": "edge"}
}
```

**Adding a new field code?** Add it here. Done.

---

### 4. `jurisdictions.json` - COUNTRY METADATA ONLY

**What goes here:** Jurisdiction-level intelligence (NOT source data)

**ID scheme:** ISO country code (`GB`, `DE`, `HR`)

```json
{
  "GB": {
    "name": "United Kingdom",
    "legal_notes": "PSC register public since 2016",
    "entity_types": ["LTD", "PLC", "LLP"],
    "id_formats": ["Company Number: 8 digits"],
    "source_domains": ["companieshouse.gov.uk", "fca.org.uk"]
  }
}
```

**`source_domains`** = REFERENCES to sources.json, NOT embedded source data

**Adding jurisdiction intel?** Add it here. Done.

---

### 5. `methodologies.json` - RESEARCH PATTERNS

**What goes here:** How to investigate things

```json
{
  "COMPANY_DEEP_DIVE": {
    "name": "Full Company Investigation",
    "steps": ["registry_lookup", "officer_search", "ubo_check", "litigation"],
    "source_domains": ["companieshouse.gov.uk", "courtlistener.com"],
    "input_codes": [13],
    "output_codes": [42, 59, 60]
  }
}
```

---

## THE THREE LEVELS

```
┌─────────────────────────────────────────────────────────────┐
│ LEVEL 1: MODULES (ours - HIDDEN)                            │
│ modules.json                                                 │
│ eye-d, corporella, torpedo                                   │
│ → What io_cli EXECUTES                                       │
└─────────────────────────────────────────────────────────────┘
                          ↓ uses
┌─────────────────────────────────────────────────────────────┐
│ LEVEL 2: AGGREGATORS (third-party APIs)                     │
│ Listed in modules.json under "aggregators"                  │
│ dehashed.com, opencorporates.com, rocketreach.co            │
│ → APIs that aggregate from primary sources                   │
└─────────────────────────────────────────────────────────────┘
                          ↓ sources from
┌─────────────────────────────────────────────────────────────┐
│ LEVEL 3: PRIMARY SOURCES (what user sees)                   │
│ sources.json                                                 │
│ companieshouse.gov.uk, linkedin-2021-breach                 │
│ → What appears in FOOTNOTES                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## io_cli BEHAVIOR

### LOOKUP mode (no value)
```
Query: cuk:
→ Return sources.json entries where jurisdiction="GB" AND type="registry"
→ Show: name, url, friction, what codes it returns
→ User sees: "Companies House - companieshouse.gov.uk"
```

### EXECUTE mode (with value)
```
Query: cuk: Acme Ltd
→ Find source: companieshouse.gov.uk
→ Find handler: modules.json["corporella"]
→ Execute: corporella.search(name="Acme Ltd", jurisdiction="GB")
→ Return: IOResult with source_domain="companieshouse.gov.uk" (for footnotes)
→ User sees: "Acme Ltd - Companies House" with footnote URL
```

---

## SANCTITY OF SOURCE

The **module** that executed is NEVER shown to user.
Only the **primary source** appears in output/footnotes.

```
INTERNAL: corporella → opencorporates → companieshouse.gov.uk
USER SEES: "Source: Companies House"
```
