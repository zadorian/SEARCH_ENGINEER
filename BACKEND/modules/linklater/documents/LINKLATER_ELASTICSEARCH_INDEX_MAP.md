# LinkLater Elasticsearch Index Architecture
**Last Updated:** 2025-12-03
**Complete audit of all Elasticsearch indices used by LinkLater module**

---

## Core DRILL Indices (Crawling & Extraction)

### 1. `drill_pages`
- **File:** `python-backend/modules/linklater/drill/indexer.py:111`
- **Status:** NOT CREATED (defined but not initialized)
- **Purpose:** Full page content with metadata, entities, embeddings
- **Schema:** text content, HTML, extracted entities, dense_vector embeddings (384 dims)
- **Used By:** DrillIndexer, Crawler

### 2. `drill_entities`
- **File:** `python-backend/modules/linklater/drill/indexer.py:112`
- **Status:** NOT CREATED
- **Purpose:** Extracted entities (companies, persons, emails, phones)
- **Schema:** entity_type, entity_value, source_url, context, embeddings
- **Used By:** DrillIndexer, Entity extraction pipeline

### 3. `drill_links`
- **File:** `python-backend/modules/linklater/drill/indexer.py:113`
- **Status:** NOT CREATED
- **Purpose:** Outlink graph for link analysis
- **Schema:** source_url, target_url, anchor_text, link_type
- **Used By:** DrillIndexer, Link graph analysis

### 4. `drill_crawl_jobs`
- **File:** `python-backend/modules/linklater/drill/scheduler.py:XX`
- **Status:** UNKNOWN
- **Purpose:** Job scheduler state tracking
- **Used By:** CrawlScheduler

### 5. `drill_links_enriched`
- **File:** `python-backend/modules/linklater/drill/linkpipeline.py:XX`
- **Status:** UNKNOWN
- **Purpose:** Enriched link pipeline with embeddings
- **Schema:** kNN vector search for semantic link analysis
- **Used By:** LinkPipeline

### 6. `drill_link_alerts`
- **File:** `python-backend/modules/linklater/alerts/link_alerts.py:XX`
- **Status:** UNKNOWN
- **Purpose:** Suspicious link pattern monitoring
- **Used By:** LinkAlerts

### 7. `drill_entity_timeline`
- **File:** `python-backend/modules/linklater/enrichment/entity_timeline.py:XX`
- **Status:** UNKNOWN
- **Purpose:** Track when entities first appeared in domain content
- **Used By:** Entity timeline tracker

---

## Discovery & Filetypes

### 8. `cc_domain_filetypes`
- **File:** `python-backend/modules/linklater/discovery/filetype_index.py:XX`
- **Status:** ✅ EXISTS (62 docs, 39KB)
- **Purpose:** Track document types (PDF, DOC, etc.) found per domain
- **Used By:** Filetype discovery, PDF hunting

### 9. `ga-edges`
- **File:** `python-backend/modules/linklater/discovery/ga_tracker.py:XX`
- **Status:** NOT FOUND IN ES
- **Purpose:** Google Analytics tracking code relationships
- **Used By:** GA tracker reverse lookup

---

## Tor/Onion Indices

### 10. `onion-pages`
- **File:** `python-backend/modules/linklater/tor/ahmia_importer.py` (UNIFIED_INDEX)
- **File:** `python-backend/modules/linklater/tor/onion_browser.py` (ES_INDEX)
- **Status:** ✅ EXISTS (128 docs, 1.7MB)
- **Purpose:** Onion site page content
- **Used By:** Ahmia importer, Onion browser, Tor crawler

### 11. `onion-graph-nodes`
- **File:** `python-backend/modules/linklater/tor/mcp_server.py:XX`
- **Status:** ✅ EXISTS (4,673 docs, 2.5MB)
- **Purpose:** Onion site nodes in link graph
- **Used By:** Tor MCP server

### 12. `onion-graph-edges`
- **File:** `python-backend/modules/linklater/tor/mcp_server.py:XX`
- **Status:** ✅ EXISTS (241,168 docs, 36MB)
- **Purpose:** Links between onion sites
- **Used By:** Tor MCP server

### 13. `onion-pages-test`
- **Status:** ✅ EXISTS (2 docs, 20KB)
- **Purpose:** Test index for onion pages

### 14. `tor-bridges`
- **File:** `python-backend/modules/linklater/linkgraph/tor_bridges.py` (DEFAULT_INDEX)
- **Status:** ✅ EXISTS (290 docs, 110KB)
- **Purpose:** Tor bridge relay information
- **Used By:** TorBridgeGraph

---

## Common Crawl Web Graph Indices

### 15. `cc_web_graph_host_edges`
- **File:** `server/services/linklater.ts:XX` (Node.js, NOT Python)
- **Status:** ✅ EXISTS (421,203,112 docs, 28.6GB)
- **Purpose:** Host-level link graph from Common Crawl
- **Used By:** Node.js linklater service (tier1Index when level='host')
- **Note:** Python LinkLater uses file-based access via alldom module, NOT this ES index

### 16. `cc_web_graph_edges`
- **File:** `server/services/linklater.ts:XX` (Node.js)
- **Status:** ✅ EXISTS (14,965,000 docs, 787MB)
- **Purpose:** Domain-level link graph
- **Used By:** Node.js linklater service (tier1Index when level='domain')

### 17. `cc_host_vertices`
- **Status:** ✅ EXISTS (235,648,112 docs, 12.7GB)
- **Purpose:** Host vertices (domain metadata)
- **Used By:** Unknown - possibly orphaned?

---

## Cymonides CC Indices (NOT used by LinkLater)

### 18. `cymonides_cc_domain_edges`
- **Status:** ✅ EXISTS (435,770,000 docs, 16.5GB)
- **Purpose:** Domain-level edges
- **Used By:** `python-backend/modules/driller/overnight_driller.py`
- **Used By:** `python-backend/modules/discovery/unified_discovery_engine.py`
- **Note:** Used by Driller and Discovery modules, NOT LinkLater

### 19. `cymonides_cc_domain_vertices`
- **Status:** ✅ EXISTS (100,662,487 docs, 7.5GB)
- **Purpose:** Domain vertices
- **Used By:** `python-backend/modules/driller/overnight_driller.py`
- **Used By:** `python-backend/modules/discovery/unified_discovery_engine.py`
- **Note:** Used by Driller and Discovery modules, NOT LinkLater

---

## Mystery Indices (Purpose Unknown)

### 20. `linklater_corpus`
- **Status:** ✅ EXISTS (282 docs, 1.1MB)
- **Purpose:** UNKNOWN - no references found in code
- **Action Required:** Identify purpose or delete

### 21. `drill-cns`
- **Status:** ✅ EXISTS (1,891 docs, 1.7MB)
- **Purpose:** UNKNOWN - no references found in code
- **Action Required:** Identify purpose or delete

### 22. `drill_atoms`
- **Status:** ✅ EXISTS (4 docs, 22KB)
- **Purpose:** UNKNOWN - no references found in code
- **Action Required:** Identify purpose or delete

---

## Summary Statistics

**Total LinkLater-related indices:** 22
**Actively used:** 11
**Not created yet:** 4
**Unknown purpose:** 3
**Used by other modules (not LinkLater):** 2
**Total storage:** ~89GB across all indices

**Key Finding:** Python LinkLater uses file-based CC access via `alldom` module, NOT the large ES CC indices. The `cc_web_graph_*` indices are used by Node.js service only.

---

## Index Consolidation Opportunities

1. **Delete orphaned indices:** `linklater_corpus`, `drill-cns`, `drill_atoms` (investigate first)
2. **Migrate Cymonides indices:** Should these be under LinkLater namespace?
3. **Create missing DRILL indices:** Initialize `drill_pages`, `drill_entities`, `drill_links`
4. **Archive or delete:** `cc_host_vertices` if truly unused
