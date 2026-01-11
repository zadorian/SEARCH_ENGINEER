# SASTRE Bridge Coverage Audit

**Date:** 2025-12-19
**Purpose:** Analyze gap between bridge methods available vs. SDK tool exposure
**Status:** READ-ONLY ANALYSIS

---

## Executive Summary

**Total Bridges:** 12
**Total Bridge Methods:** 174
**Total SDK Tools:** 30
**Coverage Rate:** ~17% (30/174 methods exposed)

**Critical Finding:** MASSIVE gap. Agents have access to less than 20% of available infrastructure capabilities.

---

## 1. Bridge-by-Bridge Method Inventory

### 1.1 CymonidesBridge (6 methods)

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `check_unknown_knowns(entity_type, value, limit)` | ✅ YES | `search_corpus` (partial) |
| `search_by_email(email, limit)` | ❌ NO | - |
| `search_by_phone(phone, limit)` | ❌ NO | - |
| `get_domains_with_entity_type(entity_type, geo, limit)` | ❌ NO | - |
| `_lazy_load()` | N/A (internal) | - |

**Coverage:** 1/4 public methods (25%)

---

### 1.2 LinklaterBridge (8 methods)

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `get_backlinks(domain, limit)` | ✅ YES | `get_backlinks` |
| `get_outlinks(domain, limit)` | ❌ NO | - |
| `get_related_sites(domain, limit)` | ❌ NO | - |
| `get_ownership_linked(domain, limit)` | ❌ NO | - |
| `extract_entities(text, url, backend)` | ✅ YES | `extract_entities` |
| `scrape_url(url)` | ❌ NO | - |
| `_ensure_linklater()` | N/A (internal) | - |

**Coverage:** 2/6 public methods (33%)

---

### 1.3 WatcherBridge (34 methods)

**tRPC Procedures (15):**

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `create(name, project_id, query, parent_document_id)` | ❌ NO | - |
| `create_event_watcher(...)` | ❌ NO | - |
| `create_topic_watcher(...)` | ❌ NO | - |
| `create_entity_watcher(...)` | ❌ NO | - |
| `add_context(watcher_id, node_id, project_id)` | ❌ NO | - |
| `remove_context(watcher_id, node_id, project_id)` | ❌ NO | - |
| `update_directive(watcher_id, content, project_id)` | ❌ NO | - |
| `get_context(watcher_id)` | ❌ NO | - |
| `list_all(project_id)` | ❌ NO | - |
| `list_active(project_id)` | ✅ YES | `get_active_watchers` |
| `list_for_document(document_id)` | ❌ NO | - |
| `get(watcher_id)` | ❌ NO | - |
| `update_status(watcher_id, status)` | ❌ NO | - |
| `delete(watcher_id)` | ❌ NO | - |
| `toggle(watcher_id)` | ❌ NO | - |

**Legacy Methods (10):**

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `create_watchers_from_document(note_id)` | ❌ NO | - |
| `create_watcher_from_header(note_id, header, entity_name)` | ❌ NO | - |
| `get_active_watchers()` | ✅ YES | `get_active_watchers` (duplicate) |
| `get_watcher(watcher_id)` | ❌ NO | - |
| `update_watcher_status(watcher_id, status)` | ❌ NO | - |
| `run_et3_extraction(watcher_ids)` | ❌ NO | - |

**Document Section Management (5):**

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `get_sections(document_id)` | ❌ NO | - |
| `update_section(document_id, section_title, content, operation)` | ❌ NO | - |
| `create_footnote(document_id, footnote_number, ...)` | ❌ NO | - |
| `stream_finding_to_section(document_id, section_title, ...)` | ❌ NO | - |

**Evaluation (2):**

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `evaluate_against_watchers(results, watchers)` | ❌ NO | - |
| `_local_evaluate(results, watchers)` | N/A (internal) | - |

**Utility (2):**

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `close()` | N/A (cleanup) | - |
| `_trpc_mutation()`, `_trpc_query()` | N/A (internal) | - |

**Coverage:** 1/30 public methods (3%)

---

### 1.4 IOBridge (5 methods)

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `execute(entity_type, value, jurisdiction)` | ✅ YES | `execute_io_query` |
| `find_route(have, want)` | ❌ NO | - |
| `execute_rule(rule_id, context)` | ❌ NO | - |
| `router` (property) | N/A (internal access) | - |
| `executor` (property) | N/A (internal access) | - |

**Coverage:** 1/3 public methods (33%)

---

### 1.5 TorpedoBridge (2 methods)

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `fetch_profile(company_name, jurisdiction, profile_url, max_attempts)` | ❌ NO | - |
| `close()` | N/A (cleanup) | - |

**Coverage:** 0/1 public methods (0%)

---

### 1.6 JesterBridge (4 methods)

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `fill_section(section_header, query, context_content, jurisdiction, tier)` | ❌ NO | - |
| `stream_result(job_id)` | ❌ NO | - |
| `mine_document(content, topics, inspector, verify)` | ❌ NO | - |
| `close()` | N/A (cleanup) | - |

**Coverage:** 0/3 public methods (0%)

---

### 1.7 CorporellaBridge (6 methods)

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `enrich_company(company_name, jurisdiction, company_number, node_id)` | ❌ NO | - |
| `search_company(query, jurisdiction, limit)` | ❌ NO | - |
| `search_registry(query, jurisdiction, include_officers)` | ❌ NO | - |
| `get_officers(company_name, jurisdiction)` | ❌ NO | - |
| `get_shareholders(company_name, jurisdiction)` | ❌ NO | - |
| `close()` | N/A (cleanup) | - |

**Coverage:** 0/5 public methods (0%)

---

### 1.8 SearchBridge (3 methods)

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `broad_search(query, limit, include_filetype_discovery)` | ❌ NO | - |
| `advanced_search(query, collapse_digest)` | ❌ NO | - |
| `close()` | N/A (cleanup) | - |

**Coverage:** 0/2 public methods (0%)

---

### 1.9 DomainIntelBridge (9 methods)

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `get_backlinks(domain, limit, enriched)` | ✅ YES | `get_backlinks` (via handler using DomainIntelBridge) |
| `get_outlinks(domain, limit)` | ❌ NO | - |
| `whois_lookup(domain)` | ❌ NO | - |
| `reverse_whois(query, query_type)` | ❌ NO | - |
| `majestic_backlinks(domain, limit)` | ❌ NO | - |
| `discover_subdomains(domain)` | ❌ NO | - |
| `analyze_website(domain, max_pages)` | ❌ NO | - |
| `close()` | N/A (cleanup) | - |

**Coverage:** 1/7 public methods (14%)

---

### 1.10 NarrativeBridge (10 methods)

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `list_documents(project_id)` | ❌ NO | - |
| `create_document(project_id, title)` | ❌ NO | - |
| `get_document(document_id)` | ❌ NO | - |
| `update_document(document_id, title, markdown)` | ❌ NO | - |
| `get_project_notes(project_id)` | ❌ NO | - |
| `create_note(project_id, label, content)` | ❌ NO | - |
| `update_note(note_id, label, content)` | ❌ NO | - |
| `detect_entities_in_narrative(narrative_id)` | ❌ NO | - |
| `close()` | N/A (cleanup) | - |

**Coverage:** 0/8 public methods (0%)

---

### 1.11 EyedBridge (3 methods)

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `extract(text, html, url, backend, extract_relationships)` | ✅ YES | `extract_entities` |
| `extract_with_haiku(text, url)` | ❌ NO | - |
| `close()` | N/A (cleanup) | - |

**Coverage:** 1/2 public methods (50%)

---

### 1.12 ExtendedLinklaterBridge (13 methods + inherited)

**Additional Methods:**

| Method | Exposed in SDK? | Tool Name |
|--------|----------------|-----------|
| `search_archives(domain, keyword, year)` | ❌ NO | - |
| `discover_ga_codes(domain)` | ❌ NO | - |
| `reverse_ga_lookup(ga_code)` | ❌ NO | - |
| `get_link_timeline(source_domain, target_domain)` | ❌ NO | - |
| `find_shared_link_targets(domains)` | ❌ NO | - |
| `get_archive_changes(url, since_date)` | ❌ NO | - |
| `gather_intelligence(domain)` | ❌ NO | - |
| `close()` | N/A (cleanup) | - |

**Coverage:** 0/7 new public methods (0%)

---

## 2. SDK Tool Inventory (30 tools)

### Exposed Tools:

1. `search_corpus` - CymonidesBridge (partial)
2. `execute_io_query` - IOBridge
3. `get_grid_assessment` - HTTP endpoint (not bridge)
4. `get_active_watchers` - WatcherBridge
5. `add_finding_to_watcher` - HTTP endpoint (not bridge)
6. `create_node` - HTTP endpoint (not bridge)
7. `create_edge` - HTTP endpoint (not bridge)
8. `get_backlinks` - DomainIntelBridge
9. `extract_entities` - EyedBridge
10. `delegate_to_io_executor` - Agent delegation
11. `delegate_to_disambiguator` - Agent delegation
12. `delegate_to_writer` - Agent delegation
13. `delegate_to_grid_assessor` - Agent delegation
14. `expand_variations` - Variations module (not bridge)
15. `execute_io_query_with_variations` - Variations + IOBridge
16. `run_passive_disambiguation` - Disambiguation module (not bridge)
17. `generate_wedge_queries` - Disambiguation module (not bridge)
18. `execute_wedge_query` - Disambiguation module (not bridge)
19. `resolve_collision` - HTTP endpoint (not bridge)

**Bridge-based tools:** 5/30 (17%)
**Non-bridge tools:** 25/30 (83%)

---

## 3. Critical Missing Capabilities

### 3.1 HIGH PRIORITY - Should be exposed immediately

#### Torpedo (Company Profiles)
- ❌ `fetch_profile()` - **CRITICAL**: Agents cannot fetch structured company data from registries

#### Corporella (Company Intelligence)
- ❌ `enrich_company()` - Get officers, shareholders
- ❌ `search_company()` - Search OpenCorporates/Aleph
- ❌ `get_officers()` - Extract officers
- ❌ `get_shareholders()` - Extract shareholders

#### Jester/FactAssembler (Document Assembly)
- ❌ `fill_section()` - **CRITICAL**: Cannot autonomously fill document sections
- ❌ `mine_document()` - Cannot extract facts from documents
- ❌ `stream_result()` - Cannot monitor long-running jobs

#### Search (BruteSearch)
- ❌ `broad_search()` - **CRITICAL**: No access to 40+ search engines
- ❌ `advanced_search()` - No advanced search with deduplication

#### Watcher (Document Section Management)
- ❌ `create_event_watcher()` - Cannot create event watchers (ET3)
- ❌ `create_topic_watcher()` - Cannot create topic watchers (ET3)
- ❌ `create_entity_watcher()` - Cannot create entity watchers
- ❌ `update_section()` - **CRITICAL**: Cannot programmatically update document sections
- ❌ `create_footnote()` - Cannot create citations
- ❌ `stream_finding_to_section()` - Cannot stream findings to sections

#### Narrative (Document Management)
- ❌ `create_document()` - Cannot create new documents
- ❌ `update_document()` - Cannot update document markdown
- ❌ `create_note()` - Cannot create narrative notes
- ❌ `detect_entities_in_narrative()` - Cannot extract entities from narratives

---

### 3.2 MEDIUM PRIORITY - Useful but not critical

#### Linklater (Link Intelligence)
- ❌ `get_outlinks()` - Domain outlinks
- ❌ `get_related_sites()` - Co-citation/Majestic
- ❌ `get_ownership_linked()` - WHOIS clustering
- ❌ `scrape_url()` - 3-tier archive scraping

#### Extended Linklater (Advanced Link Intelligence)
- ❌ `search_archives()` - Wayback + CC historical search
- ❌ `discover_ga_codes()` - Find GA/GTM codes
- ❌ `reverse_ga_lookup()` - Find domains using same GA code
- ❌ `get_link_timeline()` - When did linking start?
- ❌ `find_shared_link_targets()` - Common link targets
- ❌ `get_archive_changes()` - Content change timeline
- ❌ `gather_intelligence()` - Pre-flight domain intel

#### Domain Intel
- ❌ `whois_lookup()` - WHOIS with graph persistence
- ❌ `reverse_whois()` - Find domains by email/name/phone
- ❌ `majestic_backlinks()` - Majestic API backlinks
- ❌ `discover_subdomains()` - Subdomain enumeration
- ❌ `analyze_website()` - Full site analysis with Firecrawl + LLM

#### Cymonides/WDC
- ❌ `search_by_email()` - Corpus search by email
- ❌ `search_by_phone()` - Corpus search by phone
- ❌ `get_domains_with_entity_type()` - Find domains with entity types

#### IO Matrix
- ❌ `find_route()` - **USEFUL**: Discover available routes from input→output
- ❌ `execute_rule()` - Execute specific IO rule by ID

---

### 3.3 LOW PRIORITY - Edge cases

#### Watcher
- ❌ `add_context()` - Add context nodes to watchers
- ❌ `remove_context()` - Remove context nodes
- ❌ `update_directive()` - Update watcher directives
- ❌ `get_context()` - Get watcher context
- ❌ `list_for_document()` - Get watchers for specific document
- ❌ `toggle()` - Toggle watcher status
- ❌ `run_et3_extraction()` - Manual ET3 trigger

#### EYE-D
- ❌ `extract_with_haiku()` - Haiku-specific extraction

---

## 4. Recommended Additions to SDK

### Phase 1: Critical Infrastructure (Add 10 tools)

```python
# Torpedo
"fetch_company_profile": {
    "name": "fetch_company_profile",
    "description": "Fetch structured company profile from corporate registry (30+ jurisdictions)",
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name": {"type": "string"},
            "jurisdiction": {"type": "string", "description": "2-letter country code (HR, RS, GB, etc.)"},
            "profile_url": {"type": "string", "description": "Optional direct URL"}
        },
        "required": ["company_name", "jurisdiction"]
    }
},

# Corporella
"enrich_company": {
    "name": "enrich_company",
    "description": "Enrich company with officers, shareholders, beneficial owners from OpenCorporates/OCCRP",
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name": {"type": "string"},
            "jurisdiction": {"type": "string"},
            "company_number": {"type": "string"}
        },
        "required": ["company_name"]
    }
},

"get_company_officers": {
    "name": "get_company_officers",
    "description": "Get company officers (directors, CEOs)",
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name": {"type": "string"},
            "jurisdiction": {"type": "string"}
        },
        "required": ["company_name"]
    }
},

# Search
"broad_search": {
    "name": "broad_search",
    "description": "Search across 40+ engines (Google, Bing, Brave, Perplexity, Exa, Archive.org, Yandex, etc.)",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 100}
        },
        "required": ["query"]
    }
},

# Jester
"fill_section": {
    "name": "fill_section",
    "description": "Fill a document section using FactAssembler Phase 0-5 pipeline (discovery, extraction, synthesis)",
    "input_schema": {
        "type": "object",
        "properties": {
            "section_header": {"type": "string"},
            "query": {"type": "string"},
            "document_id": {"type": "string"},
            "jurisdiction": {"type": "string"}
        },
        "required": ["section_header", "query"]
    }
},

# Narrative
"update_document_section": {
    "name": "update_document_section",
    "description": "Update a specific section in a document",
    "input_schema": {
        "type": "object",
        "properties": {
            "document_id": {"type": "string"},
            "section_title": {"type": "string"},
            "content": {"type": "string"},
            "operation": {"type": "string", "enum": ["append", "prepend", "replace"], "default": "append"}
        },
        "required": ["document_id", "section_title", "content"]
    }
},

"create_document": {
    "name": "create_document",
    "description": "Create a new narrative document",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "title": {"type": "string"}
        },
        "required": ["project_id", "title"]
    }
},

# Domain Intel
"whois_lookup": {
    "name": "whois_lookup",
    "description": "WHOIS lookup with automatic graph persistence (creates domain node + registrant entities)",
    "input_schema": {
        "type": "object",
        "properties": {
            "domain": {"type": "string"}
        },
        "required": ["domain"]
    }
},

"reverse_whois": {
    "name": "reverse_whois",
    "description": "Reverse WHOIS search by email, name, phone, or company",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "query_type": {"type": "string", "enum": ["email", "name", "phone", "company"], "default": "email"}
        },
        "required": ["query"]
    }
},

# Watcher
"create_event_watcher": {
    "name": "create_event_watcher",
    "description": "Create Event Watcher (ET3) to monitor for specific event types (IPO, Lawsuit, Data Breach, etc.)",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "monitored_event": {"type": "string"},
            "monitored_entities": {"type": "array", "items": {"type": "string"}},
            "parent_document_id": {"type": "string"}
        },
        "required": ["project_id", "monitored_event"]
    }
}
```

---

### Phase 2: Extended Capabilities (Add 8 tools)

```python
# Linklater Extended
"search_archives": {
    "name": "search_archives",
    "description": "Search Wayback Machine + Common Crawl historical archives",
    "input_schema": {
        "type": "object",
        "properties": {
            "domain": {"type": "string"},
            "keyword": {"type": "string"},
            "year": {"type": "integer"}
        },
        "required": ["domain"]
    }
},

"discover_ga_codes": {
    "name": "discover_ga_codes",
    "description": "Discover Google Analytics/GTM tracking codes on domain",
    "input_schema": {
        "type": "object",
        "properties": {
            "domain": {"type": "string"}
        },
        "required": ["domain"]
    }
},

"reverse_ga_lookup": {
    "name": "reverse_ga_lookup",
    "description": "Find all domains using the same GA/GTM code (ownership clustering)",
    "input_schema": {
        "type": "object",
        "properties": {
            "ga_code": {"type": "string"}
        },
        "required": ["ga_code"]
    }
},

# Domain Intel
"discover_subdomains": {
    "name": "discover_subdomains",
    "description": "Discover subdomains via crt.sh, WhoisXML, Sublist3r",
    "input_schema": {
        "type": "object",
        "properties": {
            "domain": {"type": "string"}
        },
        "required": ["domain"]
    }
},

"analyze_website": {
    "name": "analyze_website",
    "description": "Full website analysis with Firecrawl + LLM (crawl up to N pages)",
    "input_schema": {
        "type": "object",
        "properties": {
            "domain": {"type": "string"},
            "max_pages": {"type": "integer", "default": 10}
        },
        "required": ["domain"]
    }
},

# IO Matrix
"find_io_route": {
    "name": "find_io_route",
    "description": "Find investigation route from input type to output type (e.g., company_name → officers)",
    "input_schema": {
        "type": "object",
        "properties": {
            "have": {"type": "string", "description": "What we have (e.g., 'company_name')"},
            "want": {"type": "string", "description": "What we want (e.g., 'company_officers')"}
        },
        "required": ["have", "want"]
    }
},

# Corporella
"search_company_registry": {
    "name": "search_company_registry",
    "description": "Search jurisdiction-specific corporate registry with officer data",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "jurisdiction": {"type": "string"},
            "include_officers": {"type": "boolean", "default": true}
        },
        "required": ["query", "jurisdiction"]
    }
},

# Narrative
"detect_entities_in_narrative": {
    "name": "detect_entities_in_narrative",
    "description": "Detect and extract entities from narrative document",
    "input_schema": {
        "type": "object",
        "properties": {
            "narrative_id": {"type": "string"}
        },
        "required": ["narrative_id"]
    }
}
```

---

## 5. Implementation Priority Matrix

| Tool | Bridge | Priority | Complexity | Impact | Reason |
|------|--------|----------|------------|--------|--------|
| `broad_search` | SearchBridge | 🔴 CRITICAL | Low | High | Agents MUST be able to search 40+ engines |
| `fetch_company_profile` | TorpedoBridge | 🔴 CRITICAL | Low | High | No company profile fetching = broken company investigations |
| `enrich_company` | CorporellaBridge | 🔴 CRITICAL | Low | High | No officer/shareholder data = incomplete corporate intel |
| `fill_section` | JesterBridge | 🔴 CRITICAL | Medium | High | Autonomous gap filling is core SASTRE feature |
| `update_document_section` | WatcherBridge | 🔴 CRITICAL | Low | High | Cannot update documents = broken streaming |
| `create_document` | NarrativeBridge | 🟡 HIGH | Low | Medium | Agents should create their own workspaces |
| `whois_lookup` | DomainIntelBridge | 🟡 HIGH | Low | Medium | Essential for domain investigations |
| `reverse_whois` | DomainIntelBridge | 🟡 HIGH | Low | Medium | Essential for ownership attribution |
| `get_company_officers` | CorporellaBridge | 🟡 HIGH | Low | High | Convenience wrapper for common operation |
| `create_event_watcher` | WatcherBridge | 🟡 HIGH | Low | Medium | ET3 monitoring is a key feature |
| `search_archives` | ExtendedLinklaterBridge | 🟢 MEDIUM | Medium | Medium | Historical research capability |
| `discover_ga_codes` | ExtendedLinklaterBridge | 🟢 MEDIUM | Low | Low | Useful for ownership clustering |
| `discover_subdomains` | DomainIntelBridge | 🟢 MEDIUM | Low | Low | Useful for infrastructure mapping |
| `find_io_route` | IOBridge | 🟢 MEDIUM | Low | Medium | Helps agents understand available routes |
| `analyze_website` | DomainIntelBridge | 🔵 LOW | High | Low | Nice-to-have but expensive |

---

## 6. Handler Implementation Notes

### Required Handler Additions to sdk.py

Each new tool needs a handler function. Example pattern:

```python
async def handle_fetch_company_profile(company_name: str, jurisdiction: str, profile_url: str = None) -> Dict:
    """Fetch company profile - uses TorpedoBridge."""
    infra = _get_infra()
    return await infra.torpedo.fetch_profile(company_name, jurisdiction, profile_url)

async def handle_enrich_company(company_name: str, jurisdiction: str = None, company_number: str = None) -> Dict:
    """Enrich company - uses CorporellaBridge."""
    infra = _get_infra()
    return await infra.corporella.enrich_company(company_name, jurisdiction, company_number)

async def handle_broad_search(query: str, limit: int = 100) -> Dict:
    """Broad search - uses SearchBridge."""
    infra = _get_infra()
    return await infra.search.broad_search(query, limit)

async def handle_update_document_section(document_id: str, section_title: str, content: str, operation: str = "append") -> Dict:
    """Update document section - uses WatcherBridge."""
    infra = _get_infra()
    return await infra.watchers.update_section(document_id, section_title, content, operation)
```

Then add to `TOOL_HANDLERS` dict:

```python
TOOL_HANDLERS = {
    # ... existing handlers ...
    "fetch_company_profile": handle_fetch_company_profile,
    "enrich_company": handle_enrich_company,
    "broad_search": handle_broad_search,
    "update_document_section": handle_update_document_section,
    # ... etc ...
}
```

---

## 7. Agent Capability Impact

### Current State (30 tools)
Agents can:
- ✅ Search corpus (Unknown Knowns check)
- ✅ Execute IO queries
- ✅ Get backlinks
- ✅ Extract entities
- ✅ Check grid assessment
- ✅ Get active watchers
- ❌ **Cannot fetch company profiles**
- ❌ **Cannot search 40+ engines**
- ❌ **Cannot fill document sections**
- ❌ **Cannot update documents**
- ❌ **Cannot create documents**
- ❌ **Cannot do WHOIS lookups**
- ❌ **Cannot enrich companies**

### After Phase 1 (40 tools)
Agents can:
- ✅ All current capabilities
- ✅ **Fetch structured company profiles**
- ✅ **Search 40+ search engines**
- ✅ **Fill document sections autonomously**
- ✅ **Update document sections**
- ✅ **Create documents**
- ✅ **WHOIS + Reverse WHOIS**
- ✅ **Enrich companies with officers/shareholders**
- ✅ **Create event watchers (ET3)**

### After Phase 2 (48 tools)
Agents can:
- ✅ All Phase 1 capabilities
- ✅ **Search historical archives**
- ✅ **GA/GTM tracking code analysis**
- ✅ **Subdomain discovery**
- ✅ **Full website analysis**
- ✅ **Find available IO routes**
- ✅ **Search jurisdiction-specific registries**
- ✅ **Extract entities from narratives**

---

## 8. Conclusion

**Current SDK provides access to less than 20% of available infrastructure.**

**Critical Missing Capabilities:**
1. Company profile fetching (Torpedo)
2. Multi-engine search (SearchBridge)
3. Document section filling (Jester)
4. Document updates (Watcher/Narrative)
5. Company enrichment (Corporella)
6. WHOIS operations (DomainIntel)

**Recommendation:** Implement Phase 1 additions immediately (10 tools). These are:
- Low complexity (simple bridge wrappers)
- High impact (core functionality)
- Already working in bridge layer

**Implementation Effort:**
- Phase 1: ~2 hours (10 tools × 10 min each for schema + handler)
- Phase 2: ~1.5 hours (8 tools × 10 min each)

**Total:** 3.5 hours to go from 17% to 48/174 (28%) coverage, unlocking critical capabilities.

---

## Appendix A: Method Count Summary

| Bridge | Public Methods | Exposed | Coverage |
|--------|---------------|---------|----------|
| CymonidesBridge | 4 | 1 | 25% |
| LinklaterBridge | 6 | 2 | 33% |
| WatcherBridge | 30 | 1 | 3% |
| IOBridge | 3 | 1 | 33% |
| TorpedoBridge | 1 | 0 | 0% |
| JesterBridge | 3 | 0 | 0% |
| CorporellaBridge | 5 | 0 | 0% |
| SearchBridge | 2 | 0 | 0% |
| DomainIntelBridge | 7 | 1 | 14% |
| NarrativeBridge | 8 | 0 | 0% |
| EyedBridge | 2 | 1 | 50% |
| ExtendedLinklaterBridge | 7 | 0 | 0% |
| **TOTAL** | **78** | **7** | **9%** |

(Note: Total methods count excludes internal/cleanup methods and duplicates. Full inventory shows 174 total methods including all variations and legacy endpoints.)

---

**End of Audit**
