# EYE-D System Review (OSINT, Graph Node Persistence, Recursion)

Scope:
- EYE-D’s execution surfaces (UI, Flask, CLI, MCP)
- Where EYE-D graph **nodes/edges persist** (and what is “source of truth”)
- Where EYE-D **recurses/expands** (UI expansion + chain reaction + persistence sync loops)
- A deterministic “EDITH-style” write-up path for EYE-D outputs

---

## 1) Component Map (what exists in this repo)

### Web UI (graph explorer)
- **Frontend**: `EYE-D/index.html`
- **Graph logic**: `EYE-D/graph.js` (vis.js datasets + expansion UI)
- **Optional persistence bridges**:
  - `EYE-D/graph-c1-integration.js` (C-1 Elasticsearch)
  - `EYE-D/graph-sql-integration.js` (external Drill Search SQL bridge)

### Flask server (API + persistence + integrations)
- **Backend**: `EYE-D/server.py`
- Responsibilities:
  - OSINT proxy endpoints (DeHashed, WHOIS, screenshot/entity extraction, etc.)
  - Local cache persistence (`/api/cache/*`)
  - Project persistence (`/api/projects/*`)
  - C-1 Elasticsearch graph endpoints (`/api/c1/*`)
  - Optional integrations (Postgres project listing, entity facts, SE import hooks)

### OSINT execution layer (aggregation)
- **Unified search**: `EYE-D/unified_osint.py`
  - Multi-source lookups (email/phone/username/linkedin/whois/ip/people)
  - Lead extraction into a shared “entities” list
  - Automated recursive expansion via `run_chain_reaction()`
- **CLI**: `EYE-D/cli.py` (auto-detect input type and call `UnifiedSearcher`)

### MCP server (tool interface)
- **MCP**: `EYE-D/mcp_server.py`
  - Exposes OSINT tools as callable MCP tools
  - Optionally indexes outputs to C-1 via `C1Bridge` (from `LINKLATER/c1_bridge.py`)

---

## 2) Output Shapes (what “comes out” of EYE-D)

### A) Structured EYE-D results (UnifiedSearcher / MCP)
Typical shape (sources vary; this is “best-effort” but consistent enough for routing):
```json
{
  "query": "…",
  "query_type": "entity_search|chain_reaction",
  "subtype": "email|phone|username|whois|linkedin|ip|person",
  "timestamp": "…",
  "results": [
    { "source": "dehashed|rocketreach|osintindustries|whoisxmlapi_history|…", "data": "…" }
  ],
  "entities": [
    { "type": "EMAIL|PHONE|USERNAME|DOMAIN|URL|IP_ADDRESS|NAME|…", "value": "…", "context": "…" }
  ]
}
```

### B) Legacy OSINTIndustries dumps (array of strings)
Some saved outputs in `EYE-D/*.json` are arrays of **stringified Python objects**, e.g.:
```json
[
  "OSINTResult(module='hibp', raw_data={...}, registered=True, ...)",
  "OSINTResult(module='dropbox', raw_data={...}, registered=True, name='…', ...)"
]
```
This is still JSON, but it is not structured JSON objects. It can be summarized, but it’s not ideal for indexing and deterministic reporting.

### C) output.py formatted JSON (sections + graph)
`EYE-D/output.py` can produce a “sections + graph” JSON bundle for OSINT Industries style data. It is a separate formatting path from UnifiedSearcher.

---

## 3) Node Persistence (where nodes/edges “live”)

EYE-D currently supports multiple persistence backends. Which one is authoritative depends on configuration and the path used (UI vs MCP vs CLI).

### Layer 0: In-memory graph (always)
`EYE-D/graph.js` maintains:
- `nodes` and `edges` (vis.js datasets)
- dedupe helpers (`valueToNodeMap`, counters, caches)
- “UI-only” nodes (query nodes, check indicators, clusters)

Without persistence, the graph resets on refresh.

### Layer 1: Local disk cache (Flask cache dir)
Stored under `EYE-D/cache/`:
- `search_cache.pkl` (pickle) — caches search responses
- `graph_state.json` — graph snapshot (vis.js compatible)

API:
- `GET /api/cache/load`
- `POST /api/cache/save`
- `POST /api/cache/clear`

The UI uses this via `saveGraphState()` / `loadCacheFromStorage()` in `EYE-D/graph.js`.

Notes:
- This cache is effectively “warm state”. In current code it is *not* the primary truth when C-1 is active.
- Cache is not strongly scoped by projectId; treat it as best-effort persistence.

### Layer 2: SQLite projects DB (local EYE-D projects)
`EYE-D/projects.py` stores:
- a projects table with `graph_data` per project
- a project_data table for typed blobs

The Flask server defaults to:
- `EYE-D/cache/projects.db`

Endpoints:
- `GET/POST /api/projects`
- `POST /api/projects/<id>/switch`
- `GET /api/projects/active`
- `POST /api/projects/<id>/graph`

In the UI, SQLite `graph_data` is now primarily a **fallback** if C-1 loading is unavailable.

### Layer 3 (primary for graph persistence): C-1 Elasticsearch graph
This is the most “complete” persistence flow for nodes/edges/positions.

Key pieces:
- `LINKLATER/c1_bridge.py`: node schema + embedded edges + per-project index naming `cymonides-1-{projectId}`
- `EYE-D/server.py`: `/api/c1/export`, `/api/c1/sync-node`, `/api/c1/sync-edge`, `/api/c1/sync-position`
- `EYE-D/graph-c1-integration.js`: loads graph and syncs changes
- `EYE-D/graph.js`: wraps `nodes.add` / `edges.add` to auto-sync to C-1

What persists:
- Node identity, label/type, metadata snapshots
- Embedded edge relationships (no separate edge index)
- Node positions (debounced writes)

### Layer 4: External Drill Search SQL bridge (optional)
`EYE-D/graph-sql-integration.js` expects an external server (default `http://localhost:3000`) with endpoints:
- `/api/eyed/sync-node`, `/api/eyed/sync-position`, `/api/eyed/export`
- `/api/eyed/expand-query`, `/api/eyed/collapse-query`

This is not handled by the EYE-D Flask server; it’s a bridge to another component.

### Layer 5: Optional Postgres “projects list” (can be inconsistent)
`EYE-D/server.py` can list projects from Postgres when `DATABASE_URL` is set by reading a `nodes` table filtered to `typeName='project'`.

Risk:
- `GET /api/projects` may return Postgres projects, but create/switch/active project endpoints are still SQLite-backed.
- This creates a “two authorities” problem for project lifecycle.

### Layer 6: Other persistence hooks (environment-specific)
Not all of these are active on this server:
- `EYE-D/entities.py` references Supabase/Postgres + Redis for URL-linked entity lookups.
- `EYE-D/server.py` includes SE import/sync hooks guarded behind optional imports and environment-specific paths.

---

## 4) Recursiveness / Recursive Expansion

### A) UI recursion (expand by double-click)
In `EYE-D/graph.js`, double-click routes to:
- query node toggles (query ↔ check indicator)
- URL node context actions
- `expandNode(node)` for all other nodes

This is user-driven recursion: every newly created node can be expanded again.

`nodeExpansionCache` records prior expansions (mostly informational). It does not block re-expansion; repeat expansions re-run searches.

### B) Domain “reverse expansion”
In `handleDomainNodeExpansion()`:
- Fetches domain WHOIS
- Extracts registrant signals (email/name/org where not privacy-redacted)
- Runs reverse-WHOIS and DeHashed searches
- Aggregates discovered domains + results back into the graph

This can fan out quickly (many domains), and each domain is then expandable again.

### C) Automated recursion: `UnifiedSearcher.run_chain_reaction()`
This is EYE-D’s primary automated recursive subsystem.

What it does:
- Performs a breadth-first walk over extracted leads.
- Uses a `visited` set with normalized keys (`_chain_key()` + `_normalize_chain_value()`).
- Uses a `depth` hop limit.
- Filters candidate leads via `_filter_relevant_entities()`:
  - dedupe up-front
  - bounded candidate list sizes
  - optional AI filtering (if available) to keep leads “on-subject”

Where it can blow up:
- If extraction yields many emails/phones/usernames, branching factor can spike.
- If normalization is too permissive, the visited set may not collapse near-duplicates.

Existing mitigations are good (depth + visited + bounding), but if you extend entity types, keep caps per type and a global max-steps ceiling.

### D) Persistence recursion (sync feedback loops)
When persistence is event-driven, loading a graph can trigger “sync” calls again.
EYE-D prevents this:
- `graph-c1-integration.js` sets a “sync suppressed” flag while loading from C-1.
- `graph.js` checks `isC1SyncSuppressed()` before auto-syncing node/edge creation.
- SQL integration uses its own suppression flag around expand/collapse.

---

## 5) EDITH-style write-up of EYE-D outputs (deterministic)

Script:
- `EYE-D/edith_writeup.py`

Usage:
- `python3 EYE-D/edith_writeup.py EYE-D/result.json`
- `python3 EYE-D/edith_writeup.py EYE-D/result.json -o /data/results/eyed_writeup.md`
- `python3 EYE-D/edith_writeup.py EYE-D/result.json --include-raw -o eyed_writeup.md`

Supports:
- Structured UnifiedSearcher/MCP results
- Legacy OSINTResult string dumps (best-effort parsing)
- output.py formatted JSON bundles (high-level summary)

---

## 6) Recommendations (high impact, minimal disruption)

### Persistence / “source of truth”
- Choose one authoritative project store (SQLite vs Postgres vs external project service). If Postgres is enabled, either:
  - fully implement create/switch/active in Postgres too, or
  - disable Postgres listing for the UI to avoid mismatched IDs/states.
- Treat `EYE-D/cache/graph_state.json` as best-effort cache unless you scope it per projectId.
- Normalize legacy outputs into structured JSON objects if you want deterministic indexing + reporting.

### Recursion safety
- Keep chain reaction bounded: add a global `max_steps` ceiling and per-type caps if you expand entity types.
- For UI fan-out expansions (reverse WHOIS, etc.), consider “preview then accept” when C-1 sync is active to avoid persisting large noisy graphs.

### Reporting hygiene
- Adopt a “report bundle” convention per investigation: raw JSON + write-up Markdown stored together so EDITH/SASTRE can cite and rehydrate sources deterministically.

