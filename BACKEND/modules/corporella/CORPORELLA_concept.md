# CORPORELLA CONCEPT: THE CORPORATE INTELLIGENCE ENGINE

> **Satellite of:** [`docs/CONCEPT.md`](../../../docs/CONCEPT.md) — See master for full system philosophy.

---

> **AI AGENTS: DO NOT MODIFY THIS FILE WITHOUT EXPLICIT USER PERMISSION**
>
> Update `2_TODO.md` and `3_LOGS.md` automatically as you work.
> See `AGENT.md` at project root for documentation protocols.

---

## 1. Role & Philosophy

**Global Alignment:** This module instantiates "Subject-Centric" and "Location-Centric" enrichment as described in the Master Concept.
**Purpose:** Corporate entity profiling with a fundamental distinction between **Global Search** and **Jurisdictional Search**.

## 2. The Two Search Paradigms

### Global Search (Discovery Mode)
**"I have a name. Find it anywhere."**

- Multi-source aggregation across ALL jurisdictions
- OpenCorporates, OpenSanctions, web search
- Returns candidates from multiple countries
- Use when: You don't know WHERE the company is registered

| Component | File | Purpose |
|-----------|------|---------|
| **OpenCorporates** | `opencorporates_brute.py` | Global registry aggregator |
| **OpenSanctions** | `opensanctions.py` | Global PEP/Sanctions |
| **Company Search** | `company_search_v3.py` | Multi-source global lookup |

### Jurisdictional Search (Precision Mode)
**"I know the jurisdiction. Query the authoritative source."**

When jurisdiction is set, the system activates:

1. **Country Engines** (`BACKEND/modules/country_engines/`)
   - Per-country search implementations (rudimentary but growing)

2. **Matrix Directory Knowledge** (`input_output/matrix/`)
   - Wikis, public records links, research tips for EVERY jurisdiction
   - Presented as **dynamic buttons** when jurisdiction is selected
   - The "Location-Centric" UI surfaces these automatically

3. **Programmatic APIs** (where available)
   - **UK:** Mostly complete (Companies House API, etc.)
   - Others: In progress

```
┌─────────────────────────────────────────────────────────────┐
│              JURISDICTION SELECTED: "UK"                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  DYNAMIC BUTTONS APPEAR (from Matrix directory):            │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ Companies    │ │ Land         │ │ Court        │        │
│  │ House API ✓  │ │ Registry     │ │ Records      │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ Charity      │ │ FCA          │ │ Gazette      │        │
│  │ Commission   │ │ Register     │ │ Search       │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
│                                                             │
│  ✓ = Fully automated API    ○ = Link/manual lookup          │
└─────────────────────────────────────────────────────────────┘
```

## 3. The Fundamental Distinction

| Aspect | Global Search | Jurisdictional Search |
|--------|---------------|----------------------|
| **Input** | Company name only | Company name + Jurisdiction |
| **Sources** | OpenCorporates, OpenSanctions | Matrix directory, country_engines, APIs |
| **UI** | Standard search | Dynamic buttons based on jurisdiction |
| **Output** | Candidates from many countries | Official records from ONE country |
| **Automation** | Full | Partial (depends on API availability) |

## 4. Jurisdictional Data Sources

The Matrix holds a wealth of knowledge per jurisdiction:
- **Registry links** (direct URLs to search)
- **Public records** (court, land, charity, etc.)
- **Research tips** (what's available, access methods)
- **Wikis** (jurisdiction-specific guidance)

When a jurisdiction is set, this knowledge becomes **actionable buttons**.

## 5. API Status by Jurisdiction

| Jurisdiction | Status | Components |
|--------------|--------|------------|
| **UK** | ✅ Mostly complete | Companies House, Land Registry, FCA |
| **US** | 🟡 Partial | SEC EDGAR, state varies |
| **EU** | 🟡 Partial | Some national registries |
| **Others** | ⚪ Matrix links | Manual lookup with guidance |

## 6. Connection Points

- **Input:** Company name (13) + optional jurisdiction (14)
- **Output:** Structured profiles to Elasticsearch
- **Location-Centric UI:** `MatrixDirectory.tsx` presents jurisdictional options
- **country_engines:** `BACKEND/modules/country_engines/` for programmatic searches
- **MACROS:** `c?` extracts companies → CORPORELLA enriches

## 7. Key Files

| File | Purpose |
|------|---------|
| `opencorporates_brute.py` | Global OpenCorporates search |
| `opensanctions.py` | PEP/Sanctions screening |
| `company_search_v3.py` | Multi-source company lookup |
| `uk/` | UK-specific APIs (Companies House, etc.) |

## 8. Matrix Integration

**Sources per Jurisdiction:** `input_output/matrix/sources.json`
**Registries:** `input_output/matrix/registries.json`
**Jurisdiction Intel:** `input_output/matrix/jurisdiction_intel.json`

Coverage: **137 jurisdictions** with varying levels of automation

## 9. Frontend Integration

### Entity Profiles (Enrichment Mode)

**See:** [`CLIENT/docs/PROFILES.concept.md`](../../../CLIENT/docs/PROFILES.concept.md)

Company profiles integrate CORPORELLA for:
- Global company search (OpenCorporates, OpenSanctions)
- Jurisdictional registry queries
- Officer lookup with recursive expansion
- UBO chain tracing

| Profile Component | CORPORELLA Method |
|-------------------|-------------------|
| Company search | `opencorporates_brute.search()` |
| Sanctions check | `opensanctions.screen()` |
| Officer lookup | `company_search_v3.getOfficers()` |
| UK Companies House | `uk/companies_house.py` |

### Directory (Location-Centric)

**See:** [`CLIENT/docs/DIRECTORY.concept.md`](../../../CLIENT/docs/DIRECTORY.concept.md)

The Directory interface surfaces CORPORELLA's jurisdictional knowledge:
- Dynamic buttons from Matrix registries
- Country-specific search panels
- Research tips per jurisdiction

**Key Frontend Files:**
- `CompanyProfilePage.tsx` — Company enrichment interface
- `SmartEnrichmentActions.tsx` — Jurisdiction-aware buttons
- `MatrixDirectoryPage.tsx` — Location-centric interface
