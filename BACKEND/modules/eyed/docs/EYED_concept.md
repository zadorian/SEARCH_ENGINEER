# EYE-D CONCEPT: THE OSINT INTELLIGENCE GRAPH

> **Satellite of:** [`docs/CONCEPT.md`](../../../docs/CONCEPT.md) — See master for full system philosophy.

---

> **AI AGENTS: DO NOT MODIFY THIS FILE WITHOUT EXPLICIT USER PERMISSION**
>
> Update `2_TODO.md` and `3_LOGS.md` automatically as you work.
> See `AGENT.md` at project root for documentation protocols.

---

## 1. Role & Philosophy

**Global Alignment:** This module instantiates the "Unknown Unknowns" quadrant—pure discovery through OSINT data aggregation.
**Purpose:** Interactive graph-based exploration of breach data, social profiles, and identity intelligence with automatic relationship mapping.

**Core Insight:** EYE-D treats identity as a graph problem—every email, phone, username, and breach record is a node; every correlation is an edge waiting to be discovered.

## 2. The Graph-First Approach

### Why Graph Visualization?

| Traditional OSINT | EYE-D Approach |
|-------------------|----------------|
| Linear reports | Interactive graph exploration |
| Manual correlation | Automatic relationship detection |
| Single-source queries | Multi-source aggregation |
| Static results | Dynamic expansion (double-click to explore) |

### Node Types & Visual Language

| Node Type | Color | Symbol | Purpose |
|-----------|-------|--------|---------|
| Search Query | Yellow | 🔍 | Entry points |
| Email | Green | ✉ | Email addresses |
| Username | Cyan | 👤 | Account identifiers |
| Password/Hash | Magenta | 🔑 | Credential data |
| IP Address | Orange | 🌐 | Network identifiers |
| Phone | Blue | 📱 | Phone numbers |
| Breach Record | Red | ⚠ | Database entries |
| URL | Coral | 🔗 | Web resources |
| Company | Teal | 🏢 | Organizations |
| Person | Purple | 👨 | Individuals |

### Connection Types

| Type | Color | Style | Meaning |
|------|-------|-------|---------|
| Default | Gray (#666666) | Dotted | General relationship |
| Anchored | White (#FFFFFF) | Thick solid | Confirmed connection |
| Hypothetical | Blue (#0066FF) | Solid | Suspected relationship |
| Source | Green (#00FF00) | Arrow | Origin → derived |
| Query | Red (#FF0000) | Solid | Search → results |

## 3. Data Sources (Resources)

### Primary OSINT Resources

| Resource | Input Types | Output Codes | Purpose |
|----------|-------------|--------------|---------|
| **DeHashed** | email, phone, domain, person | 187 | Breach credential search |
| **OSINT Industries** | email, phone, person | 188, 190 | Social profiles, linked identities |
| **RocketReach** | email, phone, domain, person | 189, 190 | Contact enrichment |
| **ContactOut** | email, phone, domain, person | 188, 189 | LinkedIn-driven discovery |
| **Kaspr** | person | 188 | Deep LinkedIn enrichment |
| **WhoisXML API** | email, phone, domain | 193, 195 | WHOIS history, DNS |
| **Archive.org** | domain | 192 | Wayback snapshots |
| **OpenCorporates** | company, person | - | Corporate registry |
| **OCCRP Aleph** | company, person | - | Investigative database |

### Matrix Integration Codes

#### Input Codes

| Code | Field | Type | Use |
|------|-------|------|-----|
| 1 | `email` | input | Email enrichment |
| 2 | `phone` | input | Phone normalization |
| 6 | `domain_url` | input | Domain/URL analysis |
| 7 | `person_name` | input | Person context |

#### Output Codes (187-198)

| Code | Output | Description |
|------|--------|-------------|
| 187 | `BreachData` | DeHashed/OSINT breach results |
| 188 | `SocialProfile` | LinkedIn profiles, social data |
| 189 | `PhoneRecord` | Reverse phone, carrier data |
| 190 | `PersonIdentityGraph` | Linked identifiers |
| 191 | `DomainBacklinks` | Backlink sets |
| 192 | `DomainWaybackSnapshots` | Archive.org captures |
| 193 | `DomainDNSRecords` | DNS answers |
| 195 | `WhoisHistoryEntry` | WHOIS timeline |
| 196 | `SSLCertificate` | SSL cert inventory |
| 197 | `DomainTimeline` | URL liveness over time |
| 198 | `DomainKeywordResults` | Historic keyword hits |

## 4. Key Features

### Double-Click Expansion

When a user double-clicks a node, EYE-D presents a search provider selection:

**API Services Tab:**
- DeHashed → Shows AI-generated variations
- OSINT Industries → Direct search
- WhoisXML API → Domain special handling
- OpenCorporates → Company/Officer based on node type
- OCCRP Aleph → Direct search

**Search Categories Tab:**
- Accounts & Credentials → DeHashed + OSINT Industries
- Corporate Intelligence → OpenCorporates + Aleph
- Domain Intelligence → WhoisXML + email search
- Personal Information → All applicable services

### URL Node Intelligence

URL nodes support:
- **Screenshot capture** via Firecrawl (auto-triggered on paste)
- **Backlink discovery** via Ahrefs/Majestic APIs
- **Outlink extraction** from page content
- **Entity extraction** via Claude (persons, companies, emails, phones)

### Exhaustive Search (ExactPhraseRecallRunner)

Google search maximizes recall through:
- Q1-Q4 query permutations
- 138 TLDs chunked into 5 site groups
- Parallel ThreadPoolExecutor execution
- Automatic deduplication
- Progressive node updates showing (1/7), (2/7)...

### Automatic Connection Detection

EYE-D automatically creates connections when:
- Search results share URLs
- Nodes share manual URLs
- Backlinks overlap between nodes
- Similar entities detected (80-95% match → blue hypothetical)

## 5. Architecture

```
BACKEND/modules/EYE-D/
├── __init__.py
├── classifier.py           # Entity type detection
├── claude_utils.py         # Claude integration
├── legend/
│   ├── __init__.py
│   ├── module.py           # Legend-aligned wrapper
│   ├── STRUCTURE.md        # This documentation
│   ├── OUTPUT.md           # Output format specs
│   ├── MATRIX_INTEGRATION.md
│   ├── input/              # Input handlers by code
│   │   ├── email.py        # Code 1
│   │   ├── phone.py        # Code 2
│   │   ├── domain_url.py   # Code 6
│   │   └── person_name.py  # Code 7
│   ├── models/
│   │   └── output_models.py  # Codes 187-198
│   └── resources/
│       ├── base.py
│       ├── dehashed.py
│       ├── osint_industries.py
│       ├── rocketreach.py
│       ├── contactout.py
│       ├── kaspr.py
│       ├── whoisxml.py
│       └── archive_org.py
└── web/
    ├── server.py           # Flask backend
    ├── graph.js            # Vis.js frontend
    └── graph-sql-integration.js  # Drill Search bridge
```

## 6. Drill Search Integration

### TypeScript Bridge

`server/routers/eyedRouter.ts` exposes:
- `/api/eyed/whois` - WHOIS lookup
- `/api/eyed/backlinks` - Backlink queries
- `/api/eyed/outlinks` - Outlink extraction
- `/api/eyed/osint` - OSINT Industries
- `/api/eyed/opencorporates` - Corporate search
- `/api/eyed/aleph` - OCCRP database

### SQL Graph Persistence

When `?projectId=XXX` is passed:
- Nodes sync to PostgreSQL
- Positions persist across sessions
- Graph state recoverable
- Cross-project entity sharing

### Graph → Cymonides Flow

1. EYE-D discovers entities (emails, persons, companies)
2. Entities stored as nodes with type classification
3. SQL sync pushes to Drill Search database
4. Cymonides can index and correlate across projects

## 7. Connection Points

- **Input:** Any node value (paste text, URL, search term)
- **Output:** Graph nodes synced to Drill Search
- **CYMONIDES:** Entities discovered here feed global indices
- **LINKLATER:** URL nodes can expand via CC graph queries
- **CORPORELLA:** Company nodes trigger corporate enrichment
- **MACROS:** `osint!` operator routes through EYE-D

## 8. Key Files Reference

| File | Purpose |
|------|---------|
| `web/server.py` | Flask API backend |
| `web/graph.js` | Vis.js graph frontend |
| `legend/module.py` | Matrix-aligned wrapper |
| `legend/resources/*.py` | Individual OSINT sources |
| `CLAUDE.md` | Development history & feature log |

## 9. Security & Compliance

- **API Keys:** Backend-only storage (never in frontend)
- **Breach Data:** Handle responsibly, defensive research only
- **Rate Limits:** Respectful API usage with exponential backoff
- **Data Retention:** User-controlled, no cloud sync without consent

## 10. Frontend Integration

### Graph Visualization

**See:** [`CLIENT/docs/GRAPH.concept.md`](../../../CLIENT/docs/GRAPH.concept.md)

The Graph interface is EYE-D's visual frontend:
- Vis.js network rendering
- Double-click expansion
- Node color/shape by type
- Edge styles by relationship type

### Entity Profiles (Enrichment Mode)

**See:** [`CLIENT/docs/PROFILES.concept.md`](../../../CLIENT/docs/PROFILES.concept.md)

EYE-D resources appear as Smart Enrichment Actions:

| Profile Type | EYE-D Resources |
|--------------|-----------------|
| **Person** | DeHashed, OSINT Industries, RocketReach, Kaspr |
| **Email** | DeHashed, OSINT Industries, breach lookup |
| **Phone** | Reverse lookup, OSINT Industries |
| **Domain** | WhoisXML, Archive.org, backlinks |

**Key Frontend Files:**
- `GraphVisualization.tsx` — Vis.js network component
- `SmartEnrichmentActions.tsx` — Matrix-driven OSINT buttons
- `PersonProfile.tsx`, `EmailProfile.tsx` — Profile pages using EYE-D

## 11. The EYE-D Philosophy

> "Every identifier is a thread. Pull it, and you unravel a network."

EYE-D embodies the investigative mindset: start with a single data point (an email, a phone number, a domain), expand it through multiple OSINT sources, and let the graph reveal connections that would be invisible in linear reports.

The double-click metaphor is central: *curiosity drives discovery*. When something looks interesting, you explore it—and EYE-D makes that exploration visual, immediate, and persistent.
