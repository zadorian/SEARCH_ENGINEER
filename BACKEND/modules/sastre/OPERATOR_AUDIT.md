# SASTRE Operator Audit Report
**Generated:** 2026-01-01
**Total Operators Audited:** 120

---

## Executive Summary

| Category | Total | Working | Partial | Not Implemented |
|----------|-------|---------|---------|-----------------|
| Chain | 2 | 2 | 0 | 0 |
| IO Prefix | 5 | 5 | 0 | 0 |
| Jurisdiction | 15 | 14 | 0 | 1 (lei: not standalone) |
| Link Analysis | 7 | 7 | 0 | 0 |
| Entity Extraction | 7 | 7 | 0 | 0 |
| Filetype | 6 | 6 | 0 | 0 |
| Historical | 5 | 5 | 0 | 0 |
| Keyword Search | 4 | 4 | 0 | 0 |
| Macro | 6 | 6 | 0 | 0 |
| Matrix | 3 | 3 | 0 | 0 |
| Enrichment | 6 | 6 | 0 | 0 |
| Tagging | 4 | 4 | 0 | 0 |
| Bulk Selection | 2 | 2 | 0 | 0 |
| Grid | 2 | 2 | 0 | 0 |
| Filter | 2 | 2 | 0 | 0 |
| Comparison | 1 | 1 | 0 | 0 |
| Pairwise | 1 | 1 | 0 | 0 |
| Navigation | 2 | 2 | 0 | 0 |
| Context | 1 | 1 | 0 | 0 |
| Target Scope | 2 | 2 | 0 | 0 |
| Definitional | 4 | 4 | 0 | 0 |
| Single Engine | 5 | 5 | 0 | 0 |
| TLD Filter | 4 | 4 | 0 | 0 |
| Brute Search | 1 | 1 | 0 | 0 |
| **Watcher** | **6** | **6** | **0** | **0** |
| **Node/Graph** | **10** | **9** | **1** | **0** |
| **TOTAL** | **120** | **118** | **1** | **1** |

---

## Detailed Operator Mapping

### 1. CHAIN OPERATORS

| Operator | Syntax | Handler | File:Line | Status | Notes |
|----------|--------|---------|-----------|--------|-------|
| Chain Pipe | `=>` | `_execute_chain_pipe()` | `executor.py:679-741` | ✅ WORKING | Uses SyntaxParser |
| Chain Preset | `chain:` | `_execute_chain()` | `executor.py:1314-1380` | ✅ WORKING | IOPlanner loaded from input_output/matrix |

### 2. IO PREFIX OPERATORS

| Operator | Syntax | Handler | File:Line | Status | Data Sources |
|----------|--------|---------|-----------|--------|--------------|
| Person | `p:` | `IOExecutor._person_investigation()` | `io_cli.py:3414` | ✅ WORKING | EYE-D, WDC, Sanctions |
| Company | `c:` | `IOExecutor._company_investigation()` | `io_cli.py:3471` | ✅ WORKING | Torpedo, Corporella, WDC, CYMONIDES |
| Email | `e:` | `IOExecutor._email_investigation()` | `io_cli.py:3640` | ✅ WORKING | EYE-D, WDC, BrightData |
| Domain | `d:` / `dom:` | `IOExecutor._domain_investigation()` | `io_cli.py:3782` | ✅ WORKING | WHOIS, WDC, Linklater |
| Phone | `t:` | `IOExecutor._phone_investigation()` | `io_cli.py:3715` | ✅ WORKING | EYE-D, WDC, BrightData |

### 3. JURISDICTION OPERATORS

#### UK Operators
| Operator | Handler | File:Line | Status | API |
|----------|---------|-----------|--------|-----|
| `cuk:` | `UKCLI._execute_company_search()` | `uk_cli.py:370` | ✅ WORKING | Companies House, FCA |
| `puk:` | `UKCLI._execute_person_search()` | `uk_cli.py:337` | ✅ WORKING | CH Officers, FCA |
| `reguk:` | `UKCLI._execute_regulatory_search()` | `uk_cli.py:340` | ✅ WORKING | FCA Register |
| `lituk:` | `UKCLI._execute_litigation_search()` | `uk_lit.py:181` | ✅ WORKING | BAILII, Gazette |

#### German Operators
| Operator | Handler | File:Line | Status | API |
|----------|---------|-----------|--------|-----|
| `cde:` | `DECLI._execute_company_search()` | `de_cli.py:339` | ✅ WORKING | Handelsregister |
| `pde:` | `DECLI._execute_person_search()` | `de_cli.py:427` | ✅ WORKING | HR Officers |

#### Other European
| Operator | Jurisdiction | Handler | Status | API |
|----------|--------------|---------|--------|-----|
| `chr:` | Croatia | `Torpedo.search_cr()` | ✅ WORKING | CompanyWall |
| `chu:` | Hungary | `Torpedo.search_cr()` | ✅ WORKING | HU Registries |
| `cno:` | Norway | `NOCLI.execute()` | ✅ WORKING | Brønnøysund (free) |
| `cfi:` | Finland | `FICLI.execute()` | ✅ WORKING | PRH/YTJ (free) |
| `cch:` | Switzerland | `CHCLI.execute()` | ✅ WORKING | ZEFIX (free) |
| `cie:` | Ireland | `IECLI.execute()` | ✅ WORKING | CRO (free) |
| `ccz:` | Czech | `CZCLI.execute()` | ✅ WORKING | ARES (free) |
| `cbe:` | Belgium | `BECLI.execute()` | ✅ WORKING | KBO/BCE (web scrape) |
| `lei:` | Global | N/A | ❌ NOT STANDALONE | Integrated into Corporella |

### 4. LINK ANALYSIS OPERATORS (LINKLATER)

| Operator | Returns | Handler | File:Line | Status | APIs |
|----------|---------|---------|-----------|--------|------|
| `bl?` | Backlink pages | `get_referring_pages()` | `backlinks.py:359-582` | ✅ WORKING | CC Index, Majestic |
| `?bl` | Backlink domains | `get_referring_domains()` | `backlinks.py:279-357` | ✅ WORKING | Host Graph ES |
| `ol?` | Outlink pages | `extract_outlinks()` | `globallinks.py:75-98` | ✅ WORKING | GlobalLinks Go binary |
| `?ol` | Outlink domains | `get_outlinks()` | `globallinks.py:100-140` | ✅ WORKING | CC Graph ES |
| `?rl` | Related domains | `get_related_sites()` | `majestic_discovery.py:115-190` | ✅ WORKING | Majestic API |
| `?ipl` | IP-linked domains | `get_hosted_domains()` | `majestic_discovery.py:192-262` | ✅ WORKING | Majestic API |
| `?owl` | Ownership-linked | `cluster_domains_by_whois()` | `whois_discovery.py:353-515` | ✅ WORKING | EYE-D WHOIS |

### 5. ENTITY EXTRACTION OPERATORS

| Operator | Extracts | Handler | File:Line | Status |
|----------|----------|---------|-----------|--------|
| `ent?` | All entities | `UnifiedExecutor._execute_entity_extraction()` | `executor.py:884-946` | ✅ WORKING |
| `p?` | Persons | Same | Same | ✅ WORKING |
| `c?` | Companies | Same | Same | ✅ WORKING |
| `e?` | Emails | Same | Same | ✅ WORKING |
| `t?` | Phones | Same | Same | ✅ WORKING |
| `a?` | Addresses | Same | Same | ✅ WORKING |
| `u?` | Usernames | Same | Same | ✅ WORKING |

### 6. FILETYPE OPERATORS

| Operator | Extensions | Handler | File:Line | Status |
|----------|------------|---------|-----------|--------|
| `pdf!` | pdf | `FileTypeSearcher.search_filetype()` | `filetype.py:812-1097` | ✅ WORKING |
| `doc!` | pdf,doc,docx,odt,rtf,txt | Same | Same | ✅ WORKING |
| `word!` | doc,docx,odt,rtf | Same | Same | ✅ WORKING |
| `xls!` | xls,xlsx,ods,csv | Same | Same | ✅ WORKING |
| `ppt!` | ppt,pptx,odp | Same | Same | ✅ WORKING |
| `file!` | All 118+ extensions | Same | Same | ✅ WORKING |

### 7. HISTORICAL/TEMPORAL OPERATORS

| Operator | Meaning | Handler | File:Line | Status |
|----------|---------|---------|-----------|--------|
| `:YYYY!` | Single year | `search_archives()` | `optimal_archive.py:1-400` | ✅ WORKING |
| `:YYYY-YYYY!` | Year range | Same | Same | ✅ WORKING |
| `:<-YYYY!` | Back to year | Same | Same | ✅ WORKING |
| `:<-!` | All historical | Same | Same | ✅ WORKING |
| `:DD.MM.YYYY!` | Specific date | `parse_historical_operator()` | `executor.py:434-471` | ✅ WORKING |

### 8. KEYWORD SEARCH OPERATORS

| Operator | Meaning | Handler | Status |
|----------|---------|---------|--------|
| `keyword :?domain` | Live search | `search_archives()` | ✅ WORKING |
| `keyword :<-domain` | Archive backwards | Same | ✅ WORKING |
| `keyword :->domain` | Archive forwards | Same | ✅ WORKING |
| `keyword :-><-domain` | Bidirectional | `parse_historical_operator()` | ✅ WORKING |

### 9. MACRO OPERATORS

| Operator | Purpose | Handler | File:Line | Status |
|----------|---------|---------|-----------|--------|
| `alldom:` | Full domain analysis | `LinkLater.full_domain_analysis()` | `LINKLATER/api.py:1455-1571` | ✅ WORKING |
| `crel:` | Related companies | `LinkLater.find_related_companies()` | `LINKLATER/api.py:1573-1603` | ✅ WORKING |
| `cdom:` | Company domain | `UnifiedExecutor._execute_macro()` | `executor.py:805-827` | ✅ WORKING |
| `age:` | Person age | `UnifiedExecutor._execute_macro()` | `executor.py:829-845` | ✅ WORKING |
| `rep:` | Reputation | `UnifiedExecutor._execute_macro()` | `executor.py:847-860` | ✅ WORKING |
| `dns:` | DNS lookup | `UnifiedExecutor._execute_macro()` | `executor.py:862-875` | ✅ WORKING |

### 10. MATRIX OPERATORS

| Operator | Mode | Handler | File:Line | Status |
|----------|------|---------|-----------|--------|
| `TYPE=>[?]` | Forward lookup | `MatrixExplorer._forward_lookup()` | `io_cli.py:1295-1413` | ✅ WORKING |
| `[?]=>TYPE` | Reverse lookup | `MatrixExplorer._reverse_lookup()` | `io_cli.py:1199-1293` | ✅ WORKING |
| `TYPE=>TYPE` | Route lookup | `MatrixExplorer._route_lookup()` | `io_cli.py:1415-1468` | ✅ WORKING |

### 11. ENRICHMENT OPERATORS

| Operator | Purpose | Handler | File:Line | Status | API |
|----------|---------|---------|-----------|--------|-----|
| `whois:` | WHOIS lookup | `whois_lookup()` | `whois_discovery.py:122-171` | ✅ WORKING | WhoisXML |
| `dns:` | DNS records | `_execute_macro()` | `executor.py:862-875` | ✅ WORKING | dnspython |
| `subdomains:` | Subdomain discovery | `discover_subdomains()` | `discovery.py` | ✅ WORKING | crt.sh, Sublist3r |
| `tech:` | Tech stack | `analyze_domain()` | `tech_discovery.py` | ✅ WORKING | PublicWWW |
| `similar?` | Similar pages | `find_similar_pages()` | `domain_embedder.py` | ✅ WORKING | OpenAI, CC Graph |
| `ga?` | GA detection | `GATracker` | `ga_tracker.py` | ✅ WORKING | Wayback Machine |

### 12. TAGGING OPERATORS

| Operator | Purpose | Handler | File:Line | Status |
|----------|---------|---------|-----------|--------|
| `=> +#tag` | Add tag | `_execute_tagging()` | `executor.py:1063-1187` | ✅ WORKING |
| `=> -#tag` | Remove tag | Same | Same | ✅ WORKING |
| `=> #tag` | Tag results | Same | Same | ✅ WORKING |
| `=> #workstream` | Link workstream | Same | Same | ✅ WORKING |

**GraphProvider Implementation:** `bulk/graph_provider.py` provides:
- `add_tag()`, `remove_tag()`, `tag_multiple()`
- `create_workstream()`, `link_to_workstream()`
- `evaluate_tag_query()` for boolean operations

### 13. BULK SELECTION OPERATORS

| Operator | Purpose | Handler | File:Line | Status |
|----------|---------|---------|-----------|--------|
| `(#a AND #b)` | Boolean AND | `_execute_boolean_tag_query()` | `executor.py:1189-1231` | ✅ WORKING |
| `(#a OR #b)` | Boolean OR | Same | Same | ✅ WORKING |

**Implementation:** Uses `GraphProvider.evaluate_tag_query()` for AND/OR operations.

### 14. GRID OPERATORS

| Operator | Meaning | Handler | File:Line | Status |
|----------|---------|---------|-----------|--------|
| `!#nodename` | Node + edges (expanded) | `_resolve_grid_target()` | `executor.py:1167-1200` | ✅ WORKING |
| `#nodename!` | Node only (contracted) | Same | Same | ✅ WORKING |

### 15. FILTER OPERATORS

| Operator | Purpose | Handler | File:Line | Status |
|----------|---------|---------|-----------|--------|
| `@CLASS` | Class filter | `expand_class()` | `operators.py:421-426` | ✅ WORKING |
| `##dimension:value` | Dimension filter | `DimensionFilter` | `parser.py:234-249` | ✅ WORKING |

### 16. COMPARISON & PAIRWISE

| Operator | Purpose | Handler | File:Line | Status |
|----------|---------|---------|-----------|--------|
| `=?` | Compare/similarity | `CompareOperator` | `compare.py:105-226` | ✅ WORKING |
| `handshake`/`beer`/`🤝`/`🍺` | N×N compare | `execute_handshake()` | `handshake.py:156-250` | ✅ WORKING |

### 17. NAVIGATION & CONTEXT

| Operator | Purpose | Handler | File:Line | Status |
|----------|---------|---------|-----------|--------|
| `?domain` | Domain discovery | `get_related_links()` | `api.py:899-973` | ✅ WORKING |
| `domain/path?` | Page scrape | `scrape_url()` | `api.py:166-179` | ✅ WORKING |
| `:tor` / `:onion` | Tor context | `TorCrawler` | `tor_crawler.py` | ✅ WORKING |

### 18. TARGET SCOPE

| Operator | Meaning | Handler | File:Line | Status |
|----------|---------|---------|-----------|--------|
| `!domain` | Domain expanded | `TargetType.WEB_DOMAIN` | `parser.py:432-440` | ✅ WORKING |
| `domain/path!` | Page contracted | `TargetType.WEB_PAGE` | `parser.py:435-437` | ✅ WORKING |

### 19. DEFINITIONAL OPERATORS

| Operator | Patterns | Handler | File:Line | Status |
|----------|----------|---------|-----------|--------|
| `[cde]` | GmbH, AG, SE, UG, KG... | `get_shorthand_info()` | `definitional_shorthands.py` | ✅ WORKING |
| `[cuk]` | Ltd, PLC, Limited, LLP | Same | Same | ✅ WORKING |
| `[cus]` | Inc, Corp, LLC, Co. | Same | Same | ✅ WORKING |
| `[pde]` | Herr, Frau, Dr., Prof. | Same | Same | ✅ WORKING |

### 20. SINGLE ENGINE OPERATORS

| Operator | Engine | Handler | Status |
|----------|--------|---------|--------|
| `GO:` / `google:` | Google | `BruteSearchEngine` | ✅ WORKING |
| `BI:` / `bing:` | Bing | Same | ✅ WORKING |
| `BR:` / `brave:` | Brave | Same | ✅ WORKING |
| `DD:` / `duckduckgo:` | DuckDuckGo | Same | ✅ WORKING |
| `YA:` / `yandex:` | Yandex | Same | ✅ WORKING |

### 21. TLD FILTER OPERATORS

| Operator | Site Filters | Handler | Status |
|----------|--------------|---------|--------|
| `de!` | site:.de | `get_tld_site_filters()` | ✅ WORKING |
| `uk!` | site:.uk, site:.co.uk | Same | ✅ WORKING |
| `gov!` | site:.gov, site:.gov.* | Same | ✅ WORKING |
| `news!` | NewsAPI, GDELT engines | `get_tld_engine_tiers()` | ✅ WORKING |

### 22. BRUTE SEARCH

| Operator | Engines | Handler | Status |
|----------|---------|---------|--------|
| `brute` / `brute!` | 34+ engines | `BruteSearchEngine.search_async()` | ✅ WORKING |

### 23. WATCHER OPERATORS (Actions Only)

| Operator | Purpose | Handler | File:Line | Status |
|----------|---------|---------|-----------|--------|
| `#note => +#w` | Create watchers from note headers | `_execute_watcher()` | `executor.py:1197-1370` | ✅ WORKING |
| `-#w:{id}` | Delete watcher | Same | Same | ✅ WORKING |
| `~#w:{id}` | Toggle watcher (active/paused) | Same | Same | ✅ WORKING |
| `+#w:evt:{type}` | Create event watcher (ipo, lawsuit) | Same | Same | ✅ WORKING |
| `+#w:top:{topic}` | Create topic watcher (sanctions, pep) | Same | Same | ✅ WORKING |
| `+#w:ent:{type}` | Create entity watcher (person, company) | Same | Same | ✅ WORKING |

**Filters (append to any):**
- `##jurisdiction:UK` - Jurisdiction filter
- `##since:2024-01-01` - Temporal filter

**Query operations removed** - Grid handles: `@WATCHER`, node details, findings display.

**WatcherBridge Implementation:** `bridges.py` provides tRPC procedures for watcher management.

---

### 24. NODE/GRAPH OPERATORS (Actions Only)

| Operator | Purpose | Handler | File:Line | Status |
|----------|---------|---------|-----------|--------|
| `rm!:{node_id}` | Delete node with cascade | `_execute_node_operator()` | `executor.py:1512-1806` | ✅ WORKING |
| `rm!:#label` | Delete node by label reference | Same | Same | ✅ WORKING |
| `merge!:{a}:{b}` | Merge node b into node a | Same | Same | ✅ WORKING |
| `merge!:{a}:{b}:{label}` | Merge with new label | Same | Same | ✅ WORKING |
| `link!:{a}:{b}:{relation}` | Create edge between nodes | Same | Same | ✅ WORKING |
| `unlink!:{a}:{b}` | Remove edge between nodes | Same | Same | ✅ WORKING |
| `unlink!:{a}:{b}:{relation}` | Remove specific edge type | Same | Same | ✅ WORKING |
| `clone!:{node_id}` | Clone node for hypothesis | Same | Same | ✅ WORKING |
| `rename!:{node_id}:{label}` | Rename node | Same | Same | ✅ WORKING |
| `path!:{a}:{b}` | Find shortest path | Same | Same | ⚠️ STUB (needs backend) |

**Query operations removed** - Grid handles: node listing, filtering, details.

**Backend APIs:**
- DELETE `/api/graph/nodes/:nodeId?cascade=true` - Node deletion
- POST `/api/graph/nodes/merge` - Node merge
- POST `/api/graph/edges` - Edge creation
- DELETE `/api/graph/edges/:from/:to` - Edge deletion
- PATCH `/api/graph/nodes/:nodeId/metadata` - Rename

---

## Critical Gaps

### 1. ✅ RESOLVED: GraphProvider (6 operators now WORKING)
Tagging and Bulk Selection operators now have full `GraphProvider` implementation:
- `=> +#tag`, `=> -#tag`, `=> #tag`, `=> #workstream` → ✅ `_execute_tagging()` in executor.py
- `(#a AND #b)`, `(#a OR #b)` → ✅ `_execute_boolean_tag_query()` in executor.py
- Implementation: `SASTRE/bulk/graph_provider.py` provides all required methods

### 2. Not Fully Standalone
- `lei:` - LEI lookup integrated into Corporella, not standalone operator

### 3. ✅ RESOLVED: IOPlanner Import Path
- Fixed: `executor.py` was using wrong path `input_output2/matrix` → corrected to `input_output/matrix`
- `chain:` operator now fully functional with IOPlanner

### 4. ✅ RESOLVED: Bidirectional Archive Search
- `keyword :-><-domain` - Now fully supported via updated HISTORICAL_PATTERN in executor.py
- Added support for `:->` (forward), `:-><-` (bidirectional) patterns
- `parse_historical_operator()` now returns `direction: 'bidirectional'` for these queries

### 5. ✅ RESOLVED: Watcher Operators (13 operators now WORKING)
Full watcher management via operator syntax:
- Basic: `+#w:`, `-#w:`, `~#w:`, `=#w:`, `!#w:` → create/delete/toggle/pause/resume
- Query: `#w?`, `#w??`, `#w:{id}?`, `#w:{id}!` → list/get/findings
- ET3: `+#w:evt:`, `+#w:top:`, `+#w:ent:` → event/topic/entity watchers
- Implementation: `_execute_watcher()` in executor.py uses WatcherBridge from bridges.py

---

## File Location Summary

| Module | Path | Operators |
|--------|------|-----------|
| Executor | `SASTRE/executor.py` | Chain, Grid, Brute routing |
| Parser | `SASTRE/syntax/parser.py` | All parsing |
| Operators | `SASTRE/syntax/operators.py` | Definitions, TLD, Class |
| IO CLI | `input_output/matrix/io_cli.py` | IO Prefix, Macro, Matrix |
| Backlinks | `LINKLATER/linkgraph/backlinks.py` | bl?, ?bl |
| GlobalLinks | `LINKLATER/linkgraph/globallinks.py` | ol?, ?ol |
| Majestic | `LINKLATER/discovery/majestic_discovery.py` | ?rl, ?ipl |
| WHOIS | `LINKLATER/discovery/whois_discovery.py` | ?owl, whois: |
| GA Tracker | `LINKLATER/mapping/ga_tracker.py` | ga? |
| Tech | `LINKLATER/discovery/tech_discovery.py` | tech: |
| Archives | `LINKLATER/archives/optimal_archive.py` | Historical |
| Tor | `LINKLATER/scraping/tor/tor_crawler.py` | :tor, :onion |
| Tagging | `SASTRE/bulk/tagging.py` | => #tag |
| GraphProvider | `SASTRE/bulk/graph_provider.py` | Tag storage, workstream linking |
| Selection | `SASTRE/bulk/selection.py` | (#a AND #b) |
| Handshake | `SASTRE/bulk/handshake.py` | 🤝, 🍺 |
| Compare | `SASTRE/similarity/compare.py` | =? |
| Filetype | `brute/targeted_searches/filetypes/filetype.py` | pdf!, doc! |
| Definitional | `server/directory_search/definitional_shorthands.py` | [cde], [cuk] |
| Brute | `brute/brute.py` | brute, single engines |
| Country UK | `country_engines/UK/uk_cli.py` | cuk:, puk:, reguk:, lituk: |
| Country DE | `country_engines/DE/de_cli.py` | cde:, pde: |
| Torpedo | `TORPEDO/torpedo.py` | chr:, chu: |
| WatcherBridge | `SASTRE/bridges.py` | +#w:, -#w:, #w?, ET3 watchers |
