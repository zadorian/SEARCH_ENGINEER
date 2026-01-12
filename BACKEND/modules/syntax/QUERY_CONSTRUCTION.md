# Query Construction Model

## The Formula

```
STATE + INTENT = ACTION
```

- **STATE**: Epistemic position (what you know/don't know) — the KU matrix
- **INTENT**: What you want to do (DISCOVER or ENRICH)
- **ACTION**: The concrete query/operation to execute

---

## STATE: The KU Matrix

### 2×2 Matrix (applies to ALL node classes)

```
                 VALUE
              K         U
         ┌─────────┬─────────┐
TYPE   K │   KK    │   KU    │
         ├─────────┼─────────┤
       U │   UK    │   UU    │
         └─────────┴─────────┘
```

| State | Meaning | Example |
|-------|---------|---------|
| **KK** | Known Type, Known Value | `John Smith` — specific person we have |
| **KU** | Known Type, Unknown Value | `p?` — seeking persons, don't know which |
| **UK** | Unknown Type, Known Value | `ID#12345` — have it, what is it? |
| **UU** | Unknown Type, Unknown Value | `ent?` — anything, any instance |

### Node Classes

| Code | Class | Description |
|------|-------|-------------|
| **S** | SUBJECT | Entities with agency (person, company, email, phone) |
| **L** | LOCATION | Venues/contexts (domain, jurisdiction, url, address) |
| **X** | NEXUS | Relationships (officer_of, links_to, registered_in) |
| **N** | NARRATIVE | Documents/notes (project, watcher, template) |

---

## STATE: The Triad Model

```
[NODE:KU] - [X:KU] - [NODE:KU]
    ↓         ↓         ↓
  LEFT     MIDDLE     RIGHT
```

### Structure

- **LEFT**: First node (S, L, or N) with its KU state
- **MIDDLE**: Relationship (X) with its KU state
- **RIGHT**: Second node (S, L, or N) with its KU state

### NEXUS Connects Any Combination

```
S - X - S    Person ←──officer_of──→ Company
S - X - L    Company ←──registered_in──→ Jurisdiction
L - X - L    Domain ←──links_to──→ Domain
L - X - S    Domain ←──hosted_by──→ Company
N - X - S    Watcher ←──monitors──→ Person
```

### KU States for NEXUS (X)

| State | Meaning | Example |
|-------|---------|---------|
| **X:KK** | Known type, Known instance | "John Smith is director of Acme (appointment #123)" |
| **X:KU** | Known type, Unknown instances | "Find all officer relationships" |
| **X:UK** | Unknown type, Known connection | "John x Acme" — connected somehow, how? |
| **X:UU** | Unknown type, Unknown instances | "Find any relationships" |

### Investigative Reality

We often don't know the relationship type upfront (X:UK). Two strategies:

#### Strategy 1: FOCUS ON NODES

Query each node's relationships — the connection reveals itself.

```
STATE:   [S:KK]-[X:UK]-[S:KK]     John ??? Acme

ACTION:  Query John's positions
         → "director of Acme Corp" revealed

ACTION:  Query Acme's officers
         → "John Smith, director" revealed

RESULT:  X:UK → X:KK (relationship discovered indirectly)
```

#### Strategy 2: EXPERIMENT WITH TYPES

Try different relationship type hypotheses directly.

```
STATE:   [S:KK]-[X:UK]-[S:KK]     John ??? Acme

TRY:     officer_of?      → HIT!
         shareholder_of?  → miss
         beneficial_owner_of? → miss

RESULT:  X:UK → X:KK (relationship discovered via experimentation)
```

#### Same for Link Analysis (L-X-L)

```
STATE:   [L:KK]-[X:UK]-[L:KK]     domain1.com ??? domain2.com

STRATEGY 1 (FOCUS ON NODES):
         Query domain1's outlinks → find link to domain2
         Query domain2's backlinks → find link from domain1

STRATEGY 2 (EXPERIMENT):
         bl?  → backlinks?
         ol?  → outlinks?
         ?rl  → related links?
```

The query syntax (`bl?`) specifies a type, but epistemically the investigator may still be in **UK territory** — hypothesizing/experimenting to discover the actual relationship type.

---

## INTENT: What You Want To Do

| Intent | Symbol | Description |
|--------|--------|-------------|
| **DISCOVER** | `[?] → [KK]` | Bring unknowns into existence |
| **ENRICH** | `[KK] → [KK+]` | Learn more about knowns |

### DISCOVER Subtypes

| Subtype | Anchor | Venue | Description |
|---------|--------|-------|-------------|
| **TRACE** | known | unknown | Find where known subject appears |
| **EXTRACT** | unknown | known | Find what exists in known venue |
| **NET** | unknown | unknown | Cast wide, discover both |

### ENRICH Subtypes

| Subtype | Description |
|---------|-------------|
| **FILL** | Populate empty slots on known node |
| **VERIFY** | Confirm existing slot values |

---

## ACTION: The Concrete Query

### Same State, Different Intents → Different Actions

```
STATE:  [S:KK]-[X:KK]-[S:KK]
        "John Smith - director_of - Acme Corp"

INTENT: ENRICH
ACTION: reg_uk: Acme Corp => officers
        → Get appointment date, share percentage, verify status

INTENT: DISCOVER
ACTION: reg?: John Smith
        → Find OTHER companies John is director of
```

### Query Examples with Full Decomposition

```
QUERY: p? :!domain.com

STATE:  [S:KU] - [X:UU] - [L:KK]
        seeking   any      known
        persons   link     domain.com

INTENT: DISCOVER (EXTRACT)
        → Extract unknown subjects from known venue

ACTION: Scrape domain.com, run NER for persons
```

```
QUERY: bl? :!domain.com

STATE:  [L:KU] - [X:UK] - [L:KK]
        seeking   trying    known
        domains   backlink  domain.com
                  hypothesis

INTENT: DISCOVER (EXTRACT)
        → Find domains linking to known domain

ACTION: Query backlink index for domain.com
```

```
QUERY: John x Acme

STATE:  [S:KK] - [X:UK] - [S:KK]
        known    unknown   known
        person   relation  company

INTENT: DISCOVER (TRACE)
        → Find how two known entities connect

ACTION: Graph traversal, co-occurrence search, registry lookup
```

```
QUERY: sanctions? :John Smith

STATE:  [S:KK] - [X:KU] - [L:KK]
        known    seeking    known
        person   sanction   sanctions
                 status     lists

INTENT: ENRICH (VERIFY)
        → Check if known person appears on sanctions lists

ACTION: Query OpenSanctions, OFAC, EU lists
        VOID = finding (NOT_SANCTIONED)
```

---

## Summary

```
┌─────────────────────────────────────────────────────────┐
│                  QUERY CONSTRUCTION                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   STATE (KU Matrix)                                      │
│   ├── Position: [NODE:KU] - [X:KU] - [NODE:KU]          │
│   ├── NODE class: S, L, N                                │
│   ├── KU state: KK, KU, UK, UU                          │
│   └── Epistemic: What you actually know/don't know       │
│                                                          │
│   + INTENT                                               │
│   ├── DISCOVER: Bring unknowns into existence           │
│   │   ├── TRACE: Find where known appears               │
│   │   ├── EXTRACT: Find what's in known venue           │
│   │   └── NET: Cast wide                                │
│   └── ENRICH: Learn more about knowns                   │
│       ├── FILL: Populate empty slots                    │
│       └── VERIFY: Confirm values                        │
│                                                          │
│   = ACTION                                               │
│   └── The concrete query/operation to execute            │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Canonical Sources (Single Source of Truth)

| File | Purpose |
|------|---------|
| `/data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/entity_class_type_matrix.json` | **CENTRAL REGISTRY** - NODE class hierarchy (SUBJECT, NEXUS, LOCATION, NARRATIVE) |
| `/data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/relationships.json` | **NEXUS ONTOLOGY** - 101 relationship types with hierarchical subtypes |
| `/data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/types.json` | **I/O TYPES** - Quick-lookup for entity type definitions |
| `/data/CLASSES/SUBJECT/industries.json` | **CONCEPT** - Industry classification (NAICS/NACE-based) |
| `/data/CLASSES/SUBJECT/professions.json` | **CONCEPT** - Profession classification (SOC/ISCO-based) |
