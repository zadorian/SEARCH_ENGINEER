# SASTRE Complete Syntax Specification

**Version:** 4.0
**Date:** 2026-01-01
**Status:** Consolidated Reference

---

## Table of Contents

1. [The Four CLASSES](#the-four-classes)
2. [The Three Operator Types](#the-three-operator-types)
3. [Two Engines: DISCOVER and ENRICH](#two-engines-discover-and-enrich)
4. [NEXUS: Edges as First-Class Nodes](#nexus-edges-as-first-class-nodes)
5. [Grid Syntax](#grid-syntax)
6. [Cell References](#cell-references)
7. [Search Syntax](#search-syntax)
8. [Actions and Chaining](#actions-and-chaining)
9. [Conditional Logic](#conditional-logic)
10. [Tags as Placeholders](#tags-as-placeholders)
11. [Complete Reference Tables](#complete-reference-tables)

---

## The Four CLASSES

The graph is viewed through four orthogonal lenses. There are exactly four CLASSES—no more can be added.

| CLASS | Short | Nature | Description |
|-------|-------|--------|-------------|
| `@SUBJECT` | `@S` | **DYNAMIC / AGENCY / FUZZY** | Entities and Concepts |
| `@LOCATION` | `@L` | **STATIC / DEFINED** | Places, Time, Language, Virtual |
| `@NEXUS` | `@X` | **CONNECTING** | Edges, Tissue, Relationships |
| `@NARRATIVE` | `@N` | **DIRECTING** | The Brain, Questions, Answers |

### @SUBJECT (DYNAMIC / AGENCY)

Subjects have fuzzy borders, change over time, and exhibit agency.

**types:**
- `@person` / `@p` — Individual people
- `@company` / `@c` — Organizations, legal entities
- `@email` / `@e` — Email addresses (as subject identifiers)
- `@phone` / `@t` — Phone numbers (as subject identifiers)
- `@username` / `@u` — Online identities
- `@theme` — Thematic categories (e.g., sanctions, compliance)
- `@phenomenon` — Observable patterns (e.g., layering, structuring)

### @LOCATION (STATIC / DEFINED)

Locations have fixed, defined borders. They don't change on their own.

**Sub-categories:**
- **Geo** — `@jurisdiction`, `@address`, `@region`, `@municipality`
- **Virtual** — `@domain`, `@url`, `@filetype`, `@format`
- **Temporal** — `@year`, `@daterange`, `@period`
- **Language** — `@language`

### @NEXUS (CONNECTING)

Nexus nodes are the relationships themselves—reified edges with properties.

**types:**
- `@query` / `@q` — Search query nodes
- `@source` / `@src` — Provenance (extracted_from, found_at)
- `#officer_of`, `#director_of`, `#secretary_of`
- `#shareholder_of`, `#beneficial_owner_of`, `#owns`
- `#registered_in`, `#regulated_by`, `#has_address`
- `#party_to`, `#transaction`, `#co_occurrence`

### @NARRATIVE (DIRECTING)

Narrative is the commanding officer—questions, answers, orchestration.

**types (hierarchical first):**
- `@project` — Hierarchical container
- `@note` — Hierarchical annotation
- `@watcher` — Hierarchical search trigger
- `@template` — Pre-made structure with slots
- `@tag` — Classification marker
- `@event` — **Emergent** (auto-created from convergence of dimensions)
- `@timeline` — User-curated sequence

**Event vs Timeline:**
- Timeline = user-created, intentional curation
- Event = emergent, auto-created when dimensions converge (who, what, where, when)

---

## The Three Operator Types

Every operator falls into one of three categories:

| Suffix | Type | Meaning | Examples |
|--------|------|---------|----------|
| `?` | **QUERY** | Search FOR / Extract | `sanctions?`, `@p?`, `bl?`, `whois?` |
| `!` | **FILTER** | FROM source/location | `pdf!`, `uk!`, `cuk!`, `reguk!` |
| `/` | **COMMAND** | DO this action | `/enrich`, `/scrape`, `/brute`, `/gridS` |

### Query Operators `?`

```
EXTRACTION (with @type):
  @P?   @PERSON?    - Extract persons from source
  @C?   @COMPANY?   - Extract companies
  @E?   @EMAIL?     - Extract emails
  @T?   @PHONE?     - Extract phones
  @A?   @ADDRESS?   - Extract addresses
  @ENT? @ENTITY?    - Extract all entities

LINK ANALYSIS:
  bl?   - Find backlinks (page-level)
  ?bl   - Find backlinks (domain-level)
  ol?   - Find outlinks (page-level)
  ?ol   - Find outlinks (domain-level)

LOOKUPS:
  sanctions?  - Search sanctions databases
  registry?   - Search corporate registries
  whois?      - Query domain registration
  pep?        - Politically exposed persons check

COMPARE:
  =?    - Find similar / compare entities
```

### Filter Operators `!`

```
FILETYPE:
  pdf! doc! word! xls! ppt! file!

TLD/JURISDICTION:
  uk! de! fr! us! ru! cy! com! gov! news!

COUNTRY ENGINES (compound):
  cuk: puk: reguk: lituk: propuk:   # UK
  cde: pde: regde: litde:           # Germany
  cfr: pfr: regfr: litfr:           # France
  chr: phr: reghr:                  # Croatia
  chu: phu: reghu:                  # Hungary
```

### Command Operators `/`

```
ACTIONS:
  /enrich   - Augment entity with additional data
  /scrape   - Fetch and scrape content from URL
  /brute    - Run brute search across 40+ engines
  /clink    - N×N pairwise comparison (🤝 🍺 aliases)
  /verify   - Verify/validate entity data

TRANSLATION:
  /tr{XX}   - Translate to language code
  /trde     - Translate to German
  /trfr     - Translate to French
  /trru     - Translate to Russian
  /trhu     - Translate to Hungarian

GRID COMMANDS:
  /gridS    - Switch to SUBJECT view
  /gridX    - Switch to NEXUS view
  /gridN    - Switch to NARRATIVE view
  /gridL    - Switch to LOCATION view
```

---

## Two Engines: DISCOVER and ENRICH

All investigation operations reduce to two atomic intents:

```
DISCOVER: [?] → [KK]           # Bring into existence
ENRICH:   [KK] → [KK+slots]    # Learn more about it
Chain:    Slots contain [?]s   # Loop
```

### The Triad (General, Not Fixed)

Every relationship forms a triad: `[A] - [R] - [B]`

- **A** and **B** can be **any node type** (Subject, Location, Nexus, Narrative)
- **R** is the relationship (NEXUS node)

**Examples:**
- Subject × Subject: Person ↔ Person (family, colleague)
- Location × Location: Jurisdiction ↔ Jurisdiction (treaty, border)
- Subject × Location: Company ↔ Jurisdiction (registered_in)
- Narrative × Subject: Watcher ↔ Entity (monitors)

### DISCOVER Sub-types

| Sub-type | Anchor | Venue | Description |
|----------|--------|-------|-------------|
| **TRACE** | Known | Unknown | "Find where John appears" |
| **EXTRACT** | Unknown | Known | "Find who appears in this registry" |
| **NET** | Unknown | Unknown | "Cast wide, see what emerges" |

### Fractal K-U Levels

| Level | Question | Intent |
|-------|----------|--------|
| **L1 (MACRO)** | Does entity exist? | DISCOVER |
| **L2 (MICRO)** | Is slot filled? | ENRICH (fill) |
| **L3 (NANO)** | Is value verified? | ENRICH (verify) |

### Unknown Nodes (KU Matrix)

An unknown node is a typed `[U]` with schema-driven expectations:

```
[U:Person]           # KU: Known type (person), Unknown value
[U:Company #cyprus]  # KU: Known type (Cyprus company), Unknown value
```

KU Matrix (2×2) — applies to ANY node class (S, L, X, N):

```
                 VALUE
              K         U
         ┌─────────┬─────────┐
TYPE   K │   KK    │   KU    │
         ├─────────┼─────────┤
       U │   UK    │   UU    │
         └─────────┴─────────┘
```

- **KK** (Known Type, Known Value): `domain.com` — we know it's a domain AND which one
- **KU** (Known Type, Unknown Value): `p?` — we know we want a person, but which one?
- **UK** (Unknown Type, Known Value): raw ID `12345` — we have it, but what IS it?
- **UU** (Unknown Type, Unknown Value): `ent?` — any entity type, any instance

### Triad Model: [NODE:KU] - [X:KU] - [NODE:KU]

NEXUS (X) connects any two nodes:
- **S-X-S**: Person - officer_of - Company
- **S-X-L**: Company - registered_in - Jurisdiction
- **L-X-L**: Domain - links_to - Domain

Each position has **CLASS** (S/L/N) and **KU state** (KK/KU/UK/UU):

```
LEFT - MIDDLE - RIGHT    QUERY                  MEANING
[S:KU]-[X:UU]-[L:KK]     p? :!domain.com       (seeking persons, any connection, from known domain)
[S:KK]-[X:UK]-[S:KK]     John x Acme           (known entities, what's the relationship?)
[L:KU]-[X:KU]-[L:KK]     bl? :!domain.com      (seeking domains, via backlinks, to known domain)
```

The schema predicts what slots the unknown node will have when materialized.

**See also:** [QUERY_CONSTRUCTION.md](./QUERY_CONSTRUCTION.md) for the full **STATE + INTENT = ACTION** model.

### VOID = Confirmed Absence

**VOID is a finding, not a gap.**

```
sanctions? :#target → ∅     # Confirmed: NOT sanctioned
```

This is different from "haven't checked yet" (gap).

### Path Illumination

Orthogonal to DISCOVER/ENRICH:

| State | Meaning |
|-------|---------|
| **ILLUMINATED** | We have explored this path |
| **DARK** | Path exists but unexplored |

A path can be ILLUMINATED + empty (no results) or DARK + suspected (likely fruitful).

### Syntax Mapping

| Intent | Pattern | Example |
|--------|---------|---------|
| DISCOVER | `[venue]? :#anchor` | `cuk: :#john_smith` |
| DISCOVER | `@type? :[source]` | `@p? :registry_data` |
| ENRICH | `/enrich :#target` | `/enrich :#acme_ltd` |
| VERIFY | `verify! :#slot` | `verify! :#ubo_chain` |

---

## NEXUS: Edges as First-Class Nodes

Relationships are not just edges—they are **nodes with properties**.

### The Reified Model

Traditional: `Person --[officer_of]--> Company`

SASTRE: `Person --[party_a]--> NEXUS_NODE --[party_b]--> Company`

The NEXUS node contains:
- **Party A / Party B**: The endpoints
- **Relation Type**: officer_of, shareholder_of, etc.
- **Slots**: Role-specific data (appointment_date, share_percentage)
- **State**: IDENTIFIED, SOUGHT, or SPECULATED
- **Provenance**: Where this was discovered

### Edge States

| State | Meaning | Typical Source |
|-------|---------|----------------|
| `IDENTIFIED` | Confirmed, verified | Registry, verified document |
| `SOUGHT` | Actively searching | Investigation gap |
| `SPECULATED` | Hypothesis, unverified | Pattern analysis |

### The Intersection Operator `x`

Find or explore connections:

```
A x B       # Find nexus between A and B
A x [?]     # Find what connects to A
[?] x B     # Find what connects to B
```

### Promoting Relationships

```
co_occurrence → SPECULATED → SOUGHT → IDENTIFIED
```

---

## Grid Syntax

### Grid Commands

Switch view AND apply filter:

```
/gridS              # SUBJECT view
/gridX              # NEXUS view
/gridN              # NARRATIVE view
/gridL              # LOCATION view

/gridS{filter}      # SUBJECT view + filter
/gridX{filter}      # NEXUS view + filter
```

### Grid Structure (Three Columns)

| Column | Name | Contains | Addressable |
|--------|------|----------|-------------|
| **A** | Primary | Nodes of current VIEW CLASS | Yes |
| **B** | Details | Snippets, metadata, properties | No |
| **C** | Related | ALL connected nodes as badges | Yes |

**Column A** always contains nodes of the current view's CLASS:
- `/gridS` → Column A = SUBJECT nodes
- `/gridX` → Column A = NEXUS nodes
- `/gridN` → Column A = NARRATIVE nodes
- `/gridL` → Column A = LOCATION nodes

### The Column A Optimization

When selecting Column A, the CLASS is implicit:

```
/gridS{A} => cuk!                          # All subjects → cuk!
/gridS{A} => IF @person THEN puk! ELSE cuk!  # Type-level distinction
/gridS{C} => IF @p THEN puk! ELSE cuk!     # Column C may contain any CLASS
```

---

## Cell References

| Pattern | Type | Example | Description |
|---------|------|---------|-------------|
| `{row}{col}` | Cell | `1A`, `3C` | Single cell |
| `{start}-{end}{col}` | Range | `1-5A`, `2-10C` | Row range in column |
| `{col}` | Column | `A`, `C` | Entire column |
| `{row}` | Row | `1`, `5` | Entire row |

### Examples

```
/gridS{1A}          # First subject
/gridS{1-5A}        # First 5 subjects
/gridS{A}           # All subjects in column A
/gridX{C}           # All related nodes in NEXUS view
/gridS{1-10A} => sanctions?   # Process rows 1-10
```

---

## Search Syntax

### Basic Search

```
"John Smith"                    # Exact phrase
John Smith                      # Keywords
"John Smith" UK                 # Phrase + keyword
```

### Country Engine Operators

```
cuk: "Acme Ltd"                 # UK company search
puk: "John Smith"               # UK person search
reguk: "12345678"               # UK registry lookup
lituk: "Acme Ltd"               # UK litigation search
```

### Brute Search

```
/brute "John Smith"             # All 40+ engines
/brute "John Smith" uk! pdf!    # With filters
```

### Entity Extraction from URLs

```
p!:?domain.com                  # Extract persons from domain
c!:?domain.com                  # Extract companies
e!:?domain.com                  # Extract emails
```

### OSINT Operators

```
email@domain.com?               # Email OSINT lookup
+1234567890?                    # Phone OSINT lookup
whois!:domain.com               # WHOIS lookup
username?                       # Username breach search
```

---

## Actions and Chaining

### The `=>` Operator

```
input => operation => operation => output
```

### Tag Actions

```
=> +#TAG                        # Apply tag
=> +#watcher[Header Text]       # Create watcher
```

### Chain Examples

```
# Basic investigation flow
+#subject => cuk: :#subject => @P? => +#officers => sanctions? :#officers

# Extract and tag
/gridS{A} => @p? => +#extracted_persons

# Multi-step with enrichment
"Acme Ltd" => +#target => cuk: :#target => @p? => +#officers => /enrich :#officers
```

---

## Conditional Logic

### IF THEN ELSE

```
IF condition THEN action1 ELSE action2
```

### Condition Types

| Condition | Meaning |
|-----------|---------|
| `#tag` | Tag exists / has results |
| `filled? :#slot` | Slot is populated |
| `sufficient? :#section` | Section meets sufficiency |
| `@CLASS` or `@type` | Type check |

### Examples

```
IF #adverse THEN phase:escalation ELSE phase:writing
IF NOT filled? :#section_ubo THEN foreach #shareholders => c: [COMPANY]
IF @person THEN puk! ELSE cuk!
/gridS{C} => IF @p THEN puk! ELSE IF @c THEN cuk! ELSE skip
```

---

## Tags as Placeholders

Tags are the universal mechanism for storing and referencing results.

### Tag Operations

```
+#tag       # Save/tag current output
:#tag       # Reference saved tag
```

### The Pattern

Tag input first, reference throughout:

```
"Acme Ltd" => +#subject
cuk: :#subject => +#registry_data
@p? :#registry_data => +#officers
sanctions? :#officers => +#sanctions_hits
```

### NOT Template Variables

```
❌ cuk: {company}              # Wrong
✓ cuk: :#subject               # Correct
```

---

## Complete Reference Tables

### Operator Quick Reference

| Operator | Type | Purpose |
|----------|------|---------|
| `?` | Query | Search for |
| `!` | Filter | From source |
| `/` | Command | Do action |
| `@` | Type | Entity type |
| `#` | Node/Tag | Specific node |
| `=>` | Chain | Sequential |
| `x` | Intersection | Find nexus |
| `[?]` | Unknown | Ghost node |

### CLASS → types Mapping

| CLASS | Nature | types |
|-------|--------|-------|
| SUBJECT | DYNAMIC/AGENCY | person, company, email, phone, username, theme, phenomenon |
| LOCATION | STATIC | jurisdiction, address, domain, url, filetype, year, language |
| NEXUS | CONNECTING | query, source, officer_of, shareholder_of, director_of, etc. |
| NARRATIVE | DIRECTING | project, note, watcher, template, tag, event, timeline |

### Grid Command → CLASS

| Command | CLASS | Column A Contains |
|---------|-------|-------------------|
| `/gridS` | SUBJECT | Entities, Concepts |
| `/gridX` | NEXUS | Relationships |
| `/gridN` | NARRATIVE | Documents, Watchers |
| `/gridL` | LOCATION | Places, Domains, Times |

### Two Engines Summary

| Engine | Symbol | Action |
|--------|--------|--------|
| DISCOVER | `[?] → [KK]` | Bring into existence |
| ENRICH | `[KK] → [KK+]` | Learn more about it |

---

## Implementation Notes

### Parser Location

**File:** `server/utils/gridSyntaxParser.ts`

**Key Exports:**
```typescript
parseGridSyntax(input: string): GridSyntaxParsed
toSyntax(parsed: GridSyntaxParsed): string
createGridState(options: {...}): GridSyntaxParsed
executeGridSyntax(parsed, projectId): Promise<GridFilterResult>
```

### KU Router (Known/Unknown Matrix)

**File:** `BACKEND/modules/syntax/ku_router.py`

Routes unknown nodes `[U]` to concrete discovery/enrichment actions using the KU matrix.

```python
from modules.syntax.ku_router import KURouter, route_ku

router = KURouter()

# Route an unknown node (KU: Known type, Unknown value)
action = router.route(
    unknown={"class": "SUBJECT", "type": "person"},
    known={"class": "LOCATION", "type": "jurisdiction", "value": "UK"}
)
# Returns: RoutingAction(intent='EXTRACT', engine='companies_house_api', syntax='puk: :#anchor', ...)

# Quick routing
action = route_ku("SUBJECT", "person", "LOCATION", "jurisdiction", "UK")

# Get enrichment slots
slots = router.get_enrichment_slots("SUBJECT", "company")
# Returns: ['registration_number', 'status', 'incorporation_date', ...]

# Triad intent (K=Known, U=Unknown)
intent = router.triad_intent("[K]-[U]-[K]")
# Returns: {'intent': 'DISCOVER', 'subtype': 'TRACE', 'action': 'Find link...'}
```

### Routing Configuration Files

| File | Purpose |
|------|---------|
| `discovery_routing_matrix.json` | Full routing rules with explanations |
| `routing_lookup.json` | Fast lookup table for routing decisions |
| `discovery_routing_matrix_schema.json` | JSON Schema for validation |
| `ku_router.py` | Python router consuming the JSON files (KU matrix) |

---

*This document consolidates all syntax specifications for the SASTRE investigation system.*
