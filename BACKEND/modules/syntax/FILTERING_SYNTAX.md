# SASTRE Filtering Syntax Specification

**Version:** 2.0
**Date:** 2026-01-01
**Status:** Draft - Decisions Required

---

## Two Modes: SEARCH vs GRID

The syntax bar operates in two modes, distinguished by the `#:` prefix:

| Mode | Prefix | Purpose | Target |
|------|--------|---------|--------|
| **SEARCH** | (none) | External search - find new data | Search engines, registries, web |
| **GRID** | `#:` | Internal filter - narrow existing data | Local graph/corpus |

```
"John Smith"                    # SEARCH mode - find externally
#: @person #john_smith          # GRID mode - filter internal graph
```

**Grid mode is the focus of this document.**

---

## Core Syntax Structure

```
#: [SELECTION] [BOOLEAN] [FILTERS] => [ACTION]
```

### Components

| Component | Syntax | Purpose |
|-----------|--------|---------|
| Mode prefix | `#:` | Enters grid filtering mode |
| Selection | `@CLASS`, `@type`, `#node` | What to select |
| Boolean | `AND`, `OR`, `()` | Combine selections |
| Filters | `##dimension:value` | Narrow selection |
| Action | `=> +#tag` | What to do with results |

---

## CLASSES (CAPITALISED) vs types (lowercase)

**This is a fundamental distinction. CLASSES are the four grid view modes, types are specific node types.**

### CLASSES (CAPITALISED) - Grid View Modes

| CLASS | Short | Contains (types) |
|-------|-------|------------------|
| `@SUBJECT` | `@S` | `@person`, `@company`, `@email`, `@phone`, `@username` |
| `@NEXUS` | `@X` | `@query`, `@source`, relationship nodes (`#officer_of`, etc.) |
| `@NARRATIVE` | `@N` | `@document`, `@note` |
| `@LOCATION` | `@L` | `@address`, `@jurisdiction`, `@domain` |

### types (lowercase)

| type | Short | CLASS | Description |
|------|-------|-------|-------------|
| `@person` | `@p` | SUBJECT | Individual people |
| `@company` | `@c` | SUBJECT | Organizations |
| `@email` | `@e` | SUBJECT | Email addresses |
| `@phone` | `@t` | SUBJECT | Phone numbers |
| `@username` | `@u` | SUBJECT | Online usernames |
| `@query` | `@q` | NEXUS | Search query nodes |
| `@source` | `@src` | NEXUS | Source relationships (extracted_from, found_at) |
| `@document` | `@doc` | NARRATIVE | Documents |
| `@note` | - | NARRATIVE | Notes |
| `@address` | `@addr` | LOCATION | Physical addresses |
| `@jurisdiction` | - | LOCATION | Legal jurisdictions |
| `@domain` | `@dom` | LOCATION | Web domains |

### Usage in Grid Filter

```
#: @SUBJECT                     # All subjects (persons + companies + assets)
#: @person                      # Only persons
#: @S                           # Short form = @SUBJECT
#: @p                           # Short form = @person
```

---

## Node References

### Specific Node Reference: `#nodename`

Reference a specific tagged node:

```
#: #john_smith                  # The node tagged john_smith
#: #acme                        # The node tagged acme
```

### Scope Control with `!`

The `!` position determines scope:

| Syntax | Meaning |
|--------|---------|
| `!#node` | FROM this node (as source/filter) |
| `#node!` | TO this node (as target) |

```
#: !#acme @person               # Persons FROM acme (connected to acme)
#: @person #acme!               # Persons connected TO acme
```

---

## Boolean Logic

**Explicit AND/OR required between nodes.**

### Operators

| Operator | Meaning |
|----------|---------|
| `AND` | Both conditions must match |
| `OR` | Either condition matches |
| `()` | Grouping |

### Examples

```
#: #john_smith AND #acme        # Nodes connected to BOTH
#: #john_smith OR #jane_doe     # Nodes connected to EITHER
#: @person AND (#acme OR #beta) # Persons connected to acme OR beta
```

### Invalid (missing explicit operator)

```
#: #john_smith #acme            # INVALID - need AND or OR
#: @person #acme                # VALID - @type and #node is implicit AND
```

---

## Dimension Filters (##)

Narrow selections with `##dimension:value`:

### Core Dimensions

| Dimension | Example | Description |
|-----------|---------|-------------|
| `##jurisdiction:XX` | `##jurisdiction:CY` | Country code |
| `##filetype:ext` | `##filetype:pdf`, `##pdf` | File type |
| `##source:type` | `##source:registry` | Data source |
| `##year:YYYY` | `##2020`, `##2019-2023` | Year or range |
| `##state:value` | `##unchecked`, `##verified` | Node state |
| `##confidence:op` | `##confidence:>0.8` | Confidence threshold |
| `##limit:N` | `##limit:10` | Result limit |

### Shorthand Forms

```
##pdf                           # = ##filetype:pdf
##uk                            # = ##jurisdiction:UK
##2020                          # = ##year:2020
##2019-2023                     # = ##year:2019-2023
```

### Examples

```
#: @company ##jurisdiction:CY               # Cyprus companies
#: @SOURCE ##pdf ##unchecked                # Unchecked PDFs
#: @SUBJECT ##jurisdiction:PA ##2020-2023   # Panama entities 2020-2023
```

---

## NEXUS Nodes: Relationships as First-Class Citizens

### The Reified Nexus

Relationships are not just edges - they are **nodes** with:
- **Party A**: One endpoint
- **Party B**: Other endpoint
- **Slots**: Role-specific data fields
- **State**: IDENTIFIED, SOUGHT, SPECULATED

### Relationship Node Types

From `relationships.json` edge types become node types:

```
#officer_of         # Person is officer of company
#shareholder_of     # Entity owns shares in company
#director_of        # Person is director of company
#beneficial_owner_of # UBO relationship
#transaction        # Financial transaction
#co_occurrence      # Baseline: entities mentioned together
```

### Filtering Relationship Nodes

```
#: #officer_of                  # All officer_of relationships
#: #officer_of #acme            # Officer relationships involving acme
#: #officer_of ##state:SOUGHT   # Officer relationships being searched for
```

### Edge States

| State | Meaning |
|-------|---------|
| `IDENTIFIED` | Confirmed, verified relationship |
| `SOUGHT` | Actively searching for this relationship |
| `SPECULATED` | Hypothesis, unverified |

```
#: @NEXUS ##state:SOUGHT        # All relationships being searched for
#: #shareholder_of ##state:SPECULATED  # Speculated shareholdings
```

---

## Intersection Operator: `x` (TIMES/CROSS)

Find or create nexus between entities.

### Syntax

```
A x B                           # Find/create nexus between A and B
A x [?]                         # Find unknown entity connected to A
[?] x B                         # Find unknown entity connected to B
```

### Query Types

| Pattern | K-U Quadrant | Purpose |
|---------|--------------|---------|
| `A x B` | Known-Known | Verify/find link between two knowns |
| `A x [?]` | Known-Unknown | Find what connects to A |
| `[?] x B` | Known-Unknown | Find what connects to B |

### Examples

```
#: #john_smith x #acme                    # Link between John and Acme
#: #john_smith x [?] ##jurisdiction:PA    # John's Panama connections
#: [?] x #acme #officer_of                # Who are Acme's officers?
```

---

## Actions (=>)

What to do with filtered results.

### Tag Application: `=> +#TAG`

```
#: @company ##jurisdiction:CY => +#OFFSHORE
#: @NEXUS ##unchecked => +#PRIORITY_CHECK
```

### Watcher Creation: `=> +#watcher[Header]`

```
#: @SUBJECT ##flagged => +#watcher[Flagged Entities]
#: #adverse AND @person => +#watcher[Adverse Persons]
```

---

## Cell, Column, and Row References

The grid supports direct cell addressing for precise selection and actions.

### Grid Column Semantics (FIXED)

| Column | Name | Contains | Selection Implications |
|--------|------|----------|------------------------|
| **A** | Primary | Unique nodes of current VIEW CLASS | Selecting A = implicit CLASS filter (no IF THEN for class) |
| **B** | Details | Snippets, metadata, properties | Not directly addressable in syntax |
| **C** | Related | ALL connected nodes as badges | May contain any CLASS/type (IF THEN may be needed) |

**Key Insight:** `/gridS` sets Column A to SUBJECT nodes. Selecting `A` is therefore already filtered to subjects—no need for `IF @SUBJECT THEN`.

### Cell Reference Syntax

| Pattern | Description | Example |
|---------|-------------|---------|
| `{row}{col}` | Single cell | `1A`, `3C` |
| `{start}-{end}{col}` | Row range in column | `1-5A`, `2-10C` |
| `{col}` | Entire column | `A`, `C` |
| `{row}` | Entire row | `1`, `5` |

### Examples

```
/gridS{1A}                          # First subject in column A
/gridS{1-5A}                        # First 5 subjects
/gridS{A}                           # All subjects in column A
/gridX{C}                           # All related nodes in NEXUS view
/gridS{3}                           # Row 3 (all columns)
```

### Cell References with Actions

Since Column A is class-determined by the view, actions on A don't need class conditions:

```
# Column A selections - CLASS is implicit
/gridS{A} => cuk!                   # All subjects → UK company search
/gridS{1-5A} => sanctions?          # First 5 subjects → sanctions check
/gridX{A} => /enrich                # All nexus nodes → enrichment

# Column C selections - may need type/class conditions
/gridS{C} => IF @p THEN puk! ELSE cuk!    # Related: persons→puk, else→cuk
/gridS{3C} => IF @company THEN reguk!     # Row 3 related: if company→registry
```

### The Column A Optimization

When selecting Column A, the CLASS is predetermined by the view:

| View | Column A Contains | Implicit When Selecting A |
|------|-------------------|---------------------------|
| `/gridS` | SUBJECT nodes | Already @SUBJECT—no `IF @SUBJECT` needed |
| `/gridX` | NEXUS nodes | Already @NEXUS—no `IF @NEXUS` needed |
| `/gridN` | NARRATIVE nodes | Already @NARRATIVE—no `IF @NARRATIVE` needed |
| `/gridL` | LOCATION nodes | Already @LOCATION—no `IF @LOCATION` needed |

**Still Valid:** Type-level conditions on Column A (e.g., `IF @person THEN puk! ELSE cuk!` within SUBJECT view)

### Cell Range Operations

```
# Process multiple cells
/gridS{1-10A} => sanctions?         # Check sanctions for rows 1-10 subjects
/gridS{1-5A AND 8-12A} => cuk!      # Rows 1-5 and 8-12

# Column-wide operations
/gridS{A} => +#PRIORITY             # Tag all subjects as priority
/gridX{C} => IF ##unchecked THEN /verify   # Verify unchecked related nodes
```

---

## Grid Command Operator (/grid)

Switch grid view AND apply filter in one command.

### Syntax

```
/gridS            # Switch to SUBJECT view
/gridX            # Switch to NEXUS view
/gridN            # Switch to NARRATIVE view
/gridL            # Switch to LOCATION view

/grid[SXNL]{filter}    # View + filter in {}
```

### Examples

```
/gridS                              # SUBJECT view, no filter
/gridX                              # NEXUS view (relationships)
/gridL{@p AND #tag1}                # LOCATION view, persons with tag1
/gridX{#officer_of ##state:SOUGHT}  # NEXUS view, sought officer relationships

# Chained with action
/gridL{(@p AND #tag1) OR #tag2} => IF @p THEN cuk!
```

### How it Works

1. `/grid` + letter (S/X/N/L) sets Column A to that CLASS
2. `{}` contains the filter expression (optional)
3. Column C shows ALL connected nodes as badges
4. Can chain with `=>` for actions after the command

---

## Bidirectional Synchronization

**CRITICAL: Grid state and syntax bar MUST stay synchronized.**

### Grid -> Syntax

When user clicks/selects in grid:
1. Selection updates internal filter state
2. Filter state serializes to syntax string via `toSyntax()`
3. Syntax string displays in bar

```typescript
// Example: User clicks to filter by Cyprus companies in SUBJECT view
gridState = {
  isGridMode: true,
  class: 'SUBJECT',
  type: 'company',
  filters: [{ dimension: 'jurisdiction', value: 'CY' }]
}
syntaxBar.value = toSyntax(gridState)  // "/gridS{@c ##jurisdiction:CY}"
```

### Syntax -> Grid

When user types in syntax bar:
1. Syntax string parses to filter state via `parseGridSyntax()`
2. Filter state applies to grid
3. Grid updates to show filtered results

```typescript
// Example: User types "/gridL{@p ##uk}"
parsed = parseGridSyntax("/gridL{@p ##uk}")
// { isGridMode: true, class: 'LOCATION', type: 'person', filters: [...] }
gridState = applyFilter(parsed)
grid.refresh()
```

### toSyntax() Function - IMPLEMENTED

Located in `server/utils/gridSyntaxParser.ts`:

```typescript
// Generates /grid syntax from parsed state
export function toSyntax(parsed: GridSyntaxParsed): string {
  // If grid mode with CLASS, use /grid command syntax
  if (parsed.isGridMode && parsed.class) {
    const suffix = classToGridSuffix(parsed.class);  // S, X, N, L
    const innerParts = buildInnerParts(parsed);      // type, nodes, filters

    if (innerParts.length === 0) {
      return `/grid${suffix}`;                       // e.g., "/gridS"
    }
    return `/grid${suffix}{${innerParts.join(' ')}}`; // e.g., "/gridS{@c ##uk}"
  }

  // Fallback: #: prefix when no CLASS
  // ... handles type-only filters
}

// Helper exports for programmatic grid state creation
export function createGridState(options: {...}): GridSyntaxParsed;
export function validateRoundTrip(syntax: string): { valid, original, reparsed };
```

---

## Changes from Current System

### CLASS_MAP Update - IMPLEMENTED

**Old (incorrect):**
```typescript
const CLASS_MAP = {
  '@person': 'PERSON',    // WRONG - person is type, not class
  '@company': 'COMPANY',  // WRONG - company is type, not class
  '@source': 'SOURCE',    // WRONG - source is NEXUS type
};
```

**New (correct) - in gridSyntaxParser.ts:**
```typescript
// CLASSES (CAPITALISED) - Four grid view modes
const CLASS_MAP: Record<string, string> = {
  '@subject': 'SUBJECT',
  '@s': 'SUBJECT',
  '@nexus': 'NEXUS',
  '@x': 'NEXUS',
  '@narrative': 'NARRATIVE',
  '@n': 'NARRATIVE',
  '@location': 'LOCATION',
  '@l': 'LOCATION',
};

// types (lowercase) - Specific node types
const TYPE_MAP: Record<string, string> = {
  // SUBJECT types
  '@person': 'person',
  '@p': 'person',
  '@company': 'company',
  '@c': 'company',
  // NEXUS types
  '@query': 'query',
  '@q': 'query',
  '@source': 'source',    // source is a NEXUS type (extracted_from, found_at)
  '@src': 'source',
  // Contact types (under SUBJECT)
  '@email': 'email',
  '@e': 'email',
  '@phone': 'phone',
  '@t': 'phone',
  '@username': 'username',
  '@u': 'username',
  // LOCATION types
  '@address': 'address',
  '@addr': 'address',
  '@jurisdiction': 'jurisdiction',
  '@domain': 'domain',
  '@dom': 'domain',
  // NARRATIVE types
  '@document': 'document',
  '@doc': 'document',
  '@note': 'note',
};
```

### Parser Updates - IMPLEMENTED

| Feature | Status |
|---------|--------|
| Grid mode prefix (`#:`) | ✅ Implemented |
| Type vs Class distinction | ✅ Implemented |
| Intersection operator (`x`) | ✅ Implemented |
| Unknown slot (`[?]`) | ✅ Implemented |
| Boolean operators (AND/OR) | ✅ Implemented |
| View rotation (`/view:CLASS`) | ✅ Implemented |
| `toSyntax()` for bidirectional sync | ✅ Implemented |
| Edge states (`##state:IDENTIFIED`) | ✅ Implemented in filter parsing |

---

## Undetermined Points (Decisions Needed)

### 1. Property Filter Syntax

Options for filtering by node properties:

| Option | Example | Notes |
|--------|---------|-------|
| `##dimension:value` | `##jurisdiction:CY` | Current system |
| `property:value` | `jurisdiction:CY` | Simpler, no ## |
| `.property:value` | `.jurisdiction:CY` | Dot notation |
| `[property:value]` | `[jurisdiction:CY]` | Bracket definitional |

**Question:** Should `##` prefix be required for all property filters?

### 2. Negation Syntax

How to express NOT:

| Option | Example |
|--------|---------|
| `NOT` keyword | `#: @person NOT ##uk` |
| `!` prefix | `#: @person !##uk` |
| `-` prefix | `#: @person -##uk` |

**Question:** Which negation syntax?

### 3. Range Filter Syntax

For numeric and date ranges:

| Current | Alternative |
|---------|-------------|
| `##2019-2023` | `##year:2019..2023` |
| `##confidence:>0.8` | `##confidence:0.8..1.0` |

**Question:** Keep current or standardize on `..` for ranges?

### 4. Temporal Filter Syntax

Filtering by when relationships were active:

| Option | Example |
|--------|---------|
| `##when:2020` | Active in 2020 |
| `##active:2020` | Explicit active prefix |
| `##during:2019-2023` | During range |

**Question:** Syntax for temporal relationship filtering?

### 5. Direction in Relationship Filter

How to specify A -> B vs B -> A:

| Option | Example |
|--------|---------|
| Position | `#: #john x #acme` (john is Party A) |
| Arrow | `#: #john -> #acme` |
| Explicit | `#: #john ##partyA #acme ##partyB` |

**Question:** Is position-based sufficient?

### 6. co_occurrence Behavior

When two entities appear together:

| Question | Options |
|----------|---------|
| Auto-create? | Always / On threshold / Never |
| Promotion? | Can become stronger edge type |
| Display? | Show as weakest / Hide by default |

**Question:** Define co_occurrence lifecycle?

---

## Complete Example Session

```
# User types in syntax bar:
/gridS{@company ##jurisdiction:CY}

# Grid switches to SUBJECT view, filters to Cyprus companies
# Bar shows: /gridS{@c ##jurisdiction:CY}

# User clicks to add Panama filter in grid UI
# Bar updates to: /gridS{@c ##jurisdiction:CY OR ##jurisdiction:PA}

# User types action:
/gridS{@c ##jurisdiction:CY OR ##jurisdiction:PA} => +#OFFSHORE

# Grid applies tag "OFFSHORE" to all matching companies
# Bar shows complete syntax

# User switches to NEXUS view to see relationships:
/gridX{#officer_of ##state:SOUGHT}

# Grid shows sought officer relationships
# Bar shows: /gridX{#officer_of ##state:SOUGHT}

# User types intersection query:
/gridX{#john_smith x [?] ##jurisdiction:PA}

# NEXUS view shows john_smith's Panama connections
# Bar shows: /gridX{#john_smith x [?] ##jurisdiction:PA}

# ---- CELL REFERENCE EXAMPLES ----

# User clicks rows 1-5 in column A (selects subjects)
# Bar shows: /gridS{1-5A}

# User adds action to search all selected subjects in UK registry:
/gridS{1-5A} => cuk!

# System runs cuk! on first 5 subjects - no IF THEN needed (Column A = SUBJECT)

# User selects column C (all related nodes) and wants conditional action:
/gridS{C} => IF @p THEN puk! ELSE cuk!

# All related persons get puk!, all related companies get cuk!

# User selects specific cell (row 3, column C) for registry lookup:
/gridS{3C} => IF @company THEN reguk!

# Only if row 3's related node is a company, run UK registry search
```

---

## Implementation Status

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | `#:` prefix detection | ✅ Complete |
| 2 | `toSyntax()` bidirectional sync | ✅ Complete |
| 3 | CLASS vs type separation | ✅ Complete |
| 4 | Intersection operator `x` and `[?]` | ✅ Complete |
| 5 | Edge state filtering | ✅ Complete |
| 6 | `/gridS`, `/gridX`, `/gridN`, `/gridL` commands | ✅ Complete |
| 7 | Cell references (`1A`, `1-5A`, `A`, `C`) | ✅ Complete |
| 8 | Action chains (`=> cuk!`, `=> IF @p THEN...`) | ✅ Complete |

### Remaining Work

1. **Frontend Integration:** Connect `toSyntax()` to syntax bar component
2. **Grid Click Handlers:** Call `createGridState()` on user interactions
3. **Live Sync:** Debounce syntax bar updates during grid interactions
4. **Cell Ref Click Handling:** Wire existing `formatCoordinates()` to syntax bar
5. **Decisions Needed:** Resolve undetermined points above
