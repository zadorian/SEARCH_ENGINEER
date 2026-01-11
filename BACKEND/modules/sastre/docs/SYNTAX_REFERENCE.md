# SASTRE Syntax Reference Card

**ONE interface for ALL investigation queries: `execute(query)`**

---

## Chain Operators (Multi-Step Investigations)

Execute full investigation chains with section-grouped outputs.

| Syntax | Description | Steps |
|--------|-------------|-------|
| `chain: due_diligence c: Acme Corp :US` | Full Due Diligence Report | 33 |
| `chain: ubo c: Siemens AG :DE` | Ultimate Beneficial Owners | 4+ |
| `chain: officers c: Tesco PLC :GB` | Officers + Sanctions | 4 |
| `chain: pep p: John Smith` | Politically Exposed Person | 2 |
| `chain: full_company c: Example Ltd` | Complete Company Investigation | 7 |

**Due Diligence Sections:** Corporate Overview, Ownership Structure, Management, Litigation, Regulatory, Financial, Media, OSINT

---

## IO Prefixes (Entity Investigation)

Single-entity lookups across all configured sources.

| Prefix | Entity Type | Example |
|--------|-------------|---------|
| `p:` | Person | `p: John Smith` |
| `c:` | Company | `c: Acme Corp :US` |
| `e:` | Email | `e: john@example.com` |
| `d:` | Domain | `d: example.com` |
| `t:` | Phone | `t: +1-555-0123` |

**Jurisdiction modifier:** Add `:XX` at end (e.g., `:US`, `:DE`, `:GB`)

---

## Registry Operators (Company Profiles)

Direct registry lookups via Torpedo.

| Operator | Registry | Jurisdiction |
|----------|----------|--------------|
| `csr:` | Serbian Company Registry | RS |
| `chr:` | Croatian Company Registry | HR |
| `csi:` | Slovenian Company Registry | SI |
| `chu:` | Hungarian Company Registry | HU |
| `cde:` | German Company Registry | DE |
| `cuk:` | UK Companies House | GB |
| `cus:` | US SEC/State Registries | US |
| `cpl:` | Polish Company Registry | PL |
| `ccz:` | Czech Company Registry | CZ |
| `cro:` | Romanian Company Registry | RO |

**Example:** `cuk: Tesco PLC` → Full UK Companies House profile

---

## Link Analysis Operators

Backlinks and outlinks from web archives.

| Operator | Returns | Example |
|----------|---------|---------|
| `bl?` | Backlink pages | `bl? :!domain.com` |
| `?bl` | Backlink domains (fast) | `?bl :!domain.com` |
| `ol?` | Outlink pages | `ol? :!domain.com` |
| `?ol` | Outlink domains (fast) | `?ol :!domain.com` |

---

## Entity Extraction Operators

Extract entities from sources.

| Operator | Extracts | Example |
|----------|----------|---------|
| `ent?` | All entities | `ent? :!domain.com` |
| `p?` | Persons only | `p? :!domain.com` |
| `c?` | Companies only | `c? :!domain.com` |
| `e?` | Emails only | `e? :!domain.com` |
| `t?` | Phone numbers | `t? :!domain.com` |
| `a?` | Addresses | `a? :!domain.com` |

**Combine:** `p? c? e? :!domain.com` → Persons, companies, and emails

---

## Historical/Archive Operators

Search historical snapshots.

| Syntax | Description |
|--------|-------------|
| `ent? :2022! !domain.com` | Entities from 2022 archives |
| `ent? :2020-2024! !domain.com` | Entities from date range |
| `keyword :<-domain.com` | Archive keyword search |

---

## Filetype Operators

Find documents by type.

| Operator | Finds |
|----------|-------|
| `pdf!` | PDF documents |
| `doc!` | Word documents |
| `xls!` | Excel files |
| `ppt!` | PowerPoint files |

**Example:** `pdf! :!example.com` → All PDFs on example.com

---

## Grid Operators (Node Operations)

Query the investigation graph.

| Operator | Description | Example |
|----------|-------------|---------|
| `ent?` | Entities from node | `ent? :!#querynode` |
| `=?` | Compare nodes | `=? :!#node1 #node2` |

**Scope modifiers:**
- `!target` → Expanded (include edges)
- `target!` → Contracted (node only)
- `#nodename` → Grid node reference

---

## Filters & Modifiers

Apply to any query.

| Modifier | Description | Example |
|----------|-------------|---------|
| `@CLASS` | Class filter | `@PERSON`, `@COMPANY`, `@SOURCE` |
| `##dimension:val` | Dimension filter | `##jurisdiction:CY` |
| `##unchecked` | State filter | `##unchecked`, `##verified` |
| `##2020` | Year filter | Entities from 2020 |
| `=> #tag` | Tag results | `ent? :!domain.com => #EXTRACTED` |

---

## Query Compiler (Natural Language)

The orchestrator uses IntentTranslator to convert questions to syntax.

| Natural Language | Translated Syntax |
|-----------------|-------------------|
| "Who is connected to John Smith?" | `ent? :!#john_smith => #CONNECTIONS` |
| "Is John Smith linked to Acme?" | `=? :!#john_smith #acme_corp` |
| "Check sanctions for John Smith" | `sanctions? :!#john_smith` |
| "What companies does John own?" | `c? :!#john_smith` |

**51 intent patterns available**

---

## Routing Summary

```
execute(query)
    │
    ├── chain: ──────► IOPlanner.execute_chain()
    │                   (33-step due diligence, UBO chains, etc.)
    │
    ├── #nodename ───► Grid (Cymonides/Elasticsearch)
    │
    ├── csr: chr: ───► Torpedo (Registry profiles)
    │
    ├── p: c: e: ────► IOExecutor (Entity investigation)
    │
    ├── bl? ent? ────► QueryExecutor (Link analysis)
    │
    └── "phrase" ────► BruteSearch (40+ engines)
```

---

## Examples

```python
from SASTRE import execute

# Full due diligence on US company
await execute("chain: due_diligence c: Acme Corp :US")

# Person investigation with variations
await execute("p: John Smith")

# UK company profile from Companies House
await execute("cuk: Tesco PLC")

# Backlinks to domain
await execute("bl? :!suspicious-domain.com")

# Historical entities from 2022
await execute("ent? :2022! !target-domain.com")

# Compare two nodes
await execute("=? :!#john_smith #acme_corp")
```
