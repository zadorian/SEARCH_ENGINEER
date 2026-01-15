# Domain Intelligence Datasets

Complete inventory of domain datasets - both indexed and online/CLI sources.

## Indexed Domain Datasets

### 1. Common Crawl Domain Graph (536M total)

#### A. Domain Vertices (100M domains)
**Index:** `cymonides_cc_domain_vertices`
- **Status:** ✅ Indexed (100,662,487 docs, 7.5GB)
- **Location:** `../../metadata/cymonides_cc_domain_vertices/`
- **Fields:** `domain`, `reversed_domain`, `vertex_id`, `count`
- **Use:** Master domain list, existence checks, TLD queries

#### B. Domain Edges (435M links)
**Index:** `cymonides_cc_domain_edges`
- **Status:** ✅ Indexed (435,770,000 docs, 16.5GB)
- **Location:** `../../metadata/cymonides_cc_domain_edges/`
- **Fields:** `source_domain`, `target_domain`, `source_vertex_id`, `target_vertex_id`, `count`
- **Use:** Backlink/outlink analysis, authority scoring, network mapping

#### C. Host-Level Graph (656M total)
**Index:** `cc_web_graph_host_edges` + `cc_host_vertices`
- **Status:** ✅ Indexed
  - Edges: 421,203,112 docs (28.6GB)
  - Vertices: 235,648,112 docs (12.7GB)
- **Granularity:** Host-level (www.example.com vs api.example.com)
- **Use:** Subdomain analysis, infrastructure mapping

#### D. CC Web Graph Edges (14.9M)
**Index:** `cc_web_graph_edges`
- **Status:** ✅ Indexed (14,965,000 docs, 787MB)
- **Purpose:** Additional edge data
- **Use:** Complementary link graph

**Sample Queries:**
```bash
# Domain lookup
curl "http://localhost:9200/cymonides_cc_domain_vertices/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": { "term": { "domain": "example.com" } }
}'

# Backlinks (who links TO this domain)
curl "http://localhost:9200/cymonides_cc_domain_edges/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": { "term": { "target_domain": "example.com" } },
  "size": 100,
  "sort": [{ "count": "desc" }]
}'

# Outlinks (who does this domain link TO)
curl "http://localhost:9200/cymonides_cc_domain_edges/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": { "term": { "source_domain": "example.com" } },
  "size": 100
}'
```

### 2. Top Domains (8.6M domains)
**Index:** `top_domains`
- **Status:** ✅ Indexed (8,671,244 docs, 1.5GB)
- **Content:** Ranked domains by various metrics
- **Use:** Authority scoring, popularity checks
- **Fields:** `domain`, `rank`, `metrics` (varies by source)

### 3. Unified Domain Profiles (5.8M domains)
**Index:** `unified_domain_profiles`
- **Status:** ✅ Indexed (5,851,357 docs, 885MB)
- **Content:** Aggregated domain intelligence
- **Use:** Comprehensive domain metadata, multi-source aggregation

### 4. Domain Enrichments
**Index:** `cymonides_source_enrichments`
- **Status:** ✅ Indexed (5 docs, 34KB)
- **Location:** `../../metadata/cymonides_source_enrichments/`
- **Content:** DRILL operation results per domain
- **Fields:** `domain`, `cc_coverage`, `search_pages`, `api_endpoints`, `entity_pages`, `outlinks`
- **Use:** Crawlability analysis, site structure

### 5. Domain File Types
**Index:** `cc_domain_filetypes`
- **Status:** ✅ Indexed (62 docs, 38KB)
- **Content:** File type distribution per domain
- **Use:** Content analysis, tech stack hints

### 6. Other Domain Indices
**Index:** `domains_complete`
- **Status:** ✅ Indexed (300 docs, 212KB)
- **Content:** Completed domain analysis records

## File-Based CC Data (Python Access)

### 7. CC Webgraph Host Edges (421M edges)
**Location:** `/Users/attic/Library/CloudStorage/GoogleDrive-tyrion02@gmail.com/My Drive/Datasets/cc_webgraph_host_edges_indexed_421M/`
- **Status:** ✅ File-based (NOT in ES, used by AllDom module)
- **Format:** Custom indexed files for fast lookups
- **Module:** `python-backend/modules/alldom/`
- **Use:** Python-side backlink analysis, domain ranking

**Note:** This is the SAME data as `cc_web_graph_host_edges` ES index, but optimized for file-based access. Python modules (AllDom) use this, Node.js services use the ES index.

## Online/CLI Domain Sources (Not Indexed)

### 8. Majestic Million & API
**Type:** ✅ Online API + Rankings
- **Source:** https://api.majestic.com
- **Module:** `python-backend/modules/discovery/majestic_discovery.py`
- **Module:** `python-backend/modules/alldom/sources/majestic_backlinks.py`
- **API Key:** `MAJESTIC_API_KEY` (in .env)
- **Capabilities:**
  - GetRelatedSites (co-citation analysis)
  - GetHostedDomains (co-hosted domains)
  - GetRefDomains (backlink sources)
  - Trust Flow / Citation Flow metrics
- **Use:** Real-time backlink analysis, competitor discovery
- **Download:** Majestic Million top 1M domains (daily CSV)

**API Usage:**
```python
from discovery.majestic_discovery import MajesticDiscovery

majestic = MajesticDiscovery()
related = majestic.get_related_sites("example.com")
backlinks = majestic.get_ref_domains("example.com")
```

### 9. Tranco List
**Type:** ⏳ Online Rankings (can download)
- **Source:** https://tranco-list.eu
- **Content:** Research-grade domain rankings
- **Update:** Daily
- **Size:** Top 1M domains (CSV)
- **Use:** Authority ranking, blocking spam/malware domains
- **Module:** Referenced in `python-backend/modules/alldom/cc_suite.py`

**Download:**
```bash
# Get latest Tranco list
wget https://tranco-list.eu/top-1m.csv.zip
unzip top-1m.csv.zip
# Can index to ES if needed
```

### 10. Cisco Umbrella (formerly OpenDNS)
**Type:** ⏳ Online Rankings
- **Source:** https://umbrella.cisco.com/blog/cisco-umbrella-1-million
- **Content:** Top 1M domains by DNS queries
- **Update:** Daily
- **Use:** Popularity/usage ranking, security screening
- **Status:** Not currently indexed

### 11. Alexa (Deprecated)
**Type:** ❌ Historical (service shut down 2022)
- **Note:** Referenced in old code, no longer available
- **Replacement:** Use Tranco or Majestic instead

### 12. BigData.com / BuiltWith
**Type:** ⏳ Commercial API (potential integration)
- **BigData.com:** Domain metadata, tech stack
- **BuiltWith:** Technology profiling
- **Status:** Not currently integrated
- **Potential Use:** Tech stack detection, CMS identification

### 13. DomainTools / WhoisXML API
**Type:** ⏳ Commercial API (potential)
- **DomainTools:** WHOIS, DNS, registrar data
- **WhoisXML:** Historical WHOIS, domain age
- **Status:** Referenced in `python-backend/modules/age/` for domain age
- **Current:** Age estimation from Wayback/Carbon Dating

### 14. SecurityTrails
**Type:** ⏳ Commercial API
- **Source:** https://securitytrails.com
- **Content:** DNS history, subdomains, WHOIS
- **Status:** Not integrated
- **Potential Use:** Infrastructure mapping, subdomain discovery

## Dataset Status Summary

| Dataset | Type | Docs/Size | Status | Access |
|---------|------|-----------|--------|--------|
| CC Domain Vertices | ES Index | 100M / 7.5GB | ✅ | Query |
| CC Domain Edges | ES Index | 435M / 16.5GB | ✅ | Query |
| CC Host Edges | ES Index | 421M / 28.6GB | ✅ | Query |
| CC Host Vertices | ES Index | 235M / 12.7GB | ✅ | Query |
| Top Domains | ES Index | 8.6M / 1.5GB | ✅ | Query |
| Domain Profiles | ES Index | 5.8M / 885MB | ✅ | Query |
| CC Host Edges (File) | Files | 421M | ✅ | Python AllDom |
| **Majestic API** | **Online** | **API** | ✅ | **Real-time** |
| **Tranco** | **Online** | **1M CSV** | ⏳ | **Download** |
| Umbrella | Online | 1M | ⏳ | Download |
| BuiltWith | API | - | ⏳ | Potential |
| SecurityTrails | API | - | ⏳ | Potential |

## Integration Workflows

### Complete Domain Intelligence Assembly
```
1. Start with: Domain name
2. Lookup: CC Domain Vertices (existence, vertex_id)
3. Get Backlinks: CC Domain Edges (authority signals)
4. Check Ranking: Top Domains / Tranco (popularity)
5. Enrich: Majestic API (real-time metrics)
6. Profile: Unified Domain Profiles (aggregated data)
7. DRILL: Cymonides Source Enrichments (crawl metadata)
8. Store: Update unified profile
```

### Competitor/Related Domain Discovery
```
1. Input: Target domain
2. API: Majestic GetRelatedSites (co-citation)
3. Graph: CC Edges (shared backlink sources)
4. Filter: By Trust Flow, Citation Flow
5. Rank: By backlink overlap
6. Output: Sorted competitor list
```

### Authority Scoring
```
1. CC Inlink Count (from cymonides_cc_domain_edges)
2. Majestic Trust Flow / Citation Flow
3. Tranco Rank (if in top 1M)
4. PageRank-style calculation on CC graph
5. Weighted composite score
```

## Module Locations

- **AllDom:** `python-backend/modules/alldom/` (file-based CC access)
- **Majestic:** `python-backend/modules/discovery/majestic_discovery.py`
- **LinkLater:** `python-backend/modules/linklater/` (domain crawling)
- **Age Estimation:** `python-backend/modules/age/` (Wayback, Carbon Dating)

## Environment Variables

```bash
# Majestic API
MAJESTIC_API_KEY=your_api_key_here

# Future: Add other domain APIs
# BUILTWITH_API_KEY=...
# SECURITYTRAILS_API_KEY=...
```

## Priority Actions

1. ✅ CC graph fully indexed and operational
2. ⏳ Download & index Tranco list (daily updates)
3. ⏳ Consider indexing Majestic Million (for offline ranking)
4. ⏳ Evaluate BuiltWith/SecurityTrails for tech profiling
5. ⏳ Set up automated Tranco/Umbrella updates

## Related Documentation

- **Use Case:** `../README.md` (Domain Intelligence workflows)
- **CC Metadata:** `../../metadata/cymonides_cc_domain_vertices/metadata.json`
- **AllDom Module:** `python-backend/modules/alldom/README.md` (if exists)
- **Majestic Discovery:** `python-backend/modules/discovery/majestic_discovery.py`

## Notes on CC Data Duplication

The CC webgraph host edges dataset exists in TWO forms:
1. **Elasticsearch:** `cc_web_graph_host_edges` (421M docs, 28.6GB)
   - Used by: Node.js server (`server/services/linklater.ts`)
   - Access: HTTP queries to ES

2. **File-based:** `/Users/attic/Library/CloudStorage/GoogleDrive.../cc_webgraph_host_edges_indexed_421M/`
   - Used by: Python AllDom module
   - Access: Direct file reads (faster for batch operations)

Both contain the SAME data, optimized for different access patterns.
