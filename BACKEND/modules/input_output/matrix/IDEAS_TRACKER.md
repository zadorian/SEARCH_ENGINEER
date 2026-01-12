# IDEAS & IMPROVEMENTS TRACKER
*Central location for all analysis findings, improvement opportunities, and pending work*
*Last updated: 2025-12-30*

---

## ACTIVE WORK

### Domain Consolidation
- **Status**: Running in background
- **Progress**: ~80K/178M (will take 2-3 hours)
- **Script**: `scripts/consolidate_domains_to_atlas.py`
- **Log**: `/tmp/domain_consolidation.log`

---

## EXISTING VECTOR DATABASES & EMBEDDINGS

### Elasticsearch Indices with Vectors
| Index | Doc Count | Model | Dims | Purpose |
|-------|-----------|-------|------|---------|
| `matrix_type_embeddings` | 2,461 | all-MiniLM-L6-v2 | 384 | IO Matrix field types for semantic routing |
| `domain_category_embeddings` | ~100 | all-MiniLM-L6-v2 | 384 | DMOZ/Curlie category search |
| `cymonides-2` (embedded_edges field) | 13M+ | text-embedding-3-large | 3072 | Domain content chunks for RAG |

### Embedding Files (JSON)
| File | Size | Model | Purpose |
|------|------|-------|---------|
| `BACKEND/modules/CYMONIDES/industry_embeddings.json` | 1.8MB | all-MiniLM-L6-v2 | LinkedIn industry semantic search |
| `BACKEND/modules/LINKLATER/.cache/concept_embeddings.json` | 3.5MB | text-embedding-3-large | LINKLATER concept classifiers |

### Embedding Modules (Code)
| Module | Model | Storage | Purpose |
|--------|-------|---------|---------|
| `BACKEND/modules/DEFINITIONAL/unified_categories/embeddings.py` | all-MiniLM-L6-v2 | ES | Domain category search |
| `BACKEND/modules/CYMONIDES/industry_matcher.py` | all-MiniLM-L6-v2 | JSON | LinkedIn industry matching |
| `BACKEND/modules/LINKLATER/domain_embedder.py` | text-embedding-3-large | ES (cymonides-2) | RAG for domain content |
| `server/modules/engines/supabase_vector_manager_v2.py` | OpenAI | Supabase | External vector storage |
| `BACKEND/modules/BRUTE/adapter/vector_embedder.py` | varies | ? | Search result embedding |
| `BACKEND/modules/SASTRE/similarity/vectors.py` | ? | ? | Entity similarity |

---

## STRATEGIC EMBEDDINGS (TO IMPLEMENT)

**Reference file**: `BACKEND/modules/CYMONIDES/strategic_embeddings.json`

### Already Implemented
| Embedding | Module | Size | Filters |
|-----------|--------|------|---------|
| Domain Categories | `BACKEND/modules/DEFINITIONAL/unified_categories/embeddings.py` | ~5K | 178M domains |
| LinkedIn Industries | `BACKEND/modules/CYMONIDES/industry_matcher.py` | ~150 | 2.9M profiles |

### Next to Implement (Priority Order)
1. **Job Title Clusters** - Group 50K titles into ~500 semantic clusters
2. **Geographic Regions** - Hierarchical UK counties/districts + regions
3. **Schema.org Types** - 200 types for 10M WDC entities
4. **Legal Entity Designators** - LTD, PLC, GMBH, LLC mappings
5. **Red Flag Terms** - 200 investigation red flag terms

---

## QUERY PATTERNS (from 16-agent analysis)

**Reference file**: `BACKEND/modules/CYMONIDES/query_patterns.json`

### Data Quality Issues Discovered
- `openownership.subject_name`: 0% populated (mapping error?)
- 83.7% of domains in `domains_unified` unenriched
- GARBAGE_NAME fields: 30-50% contamination

### Advanced Patterns to Implement
1. **Multi-hop traversal queries** - Recursive ownership chains, breach networks
2. **Anomaly scoring system** - 0-100 scores for companies, persons, domains, emails
3. **Function_score queries** - Custom relevance ranking
4. **Significant_terms aggregation** - Find unusual co-occurrences

### Schema Improvements Identified
- 47 improvements across 12 indices
- IP fields should be `ip` type not `keyword`
- Missing `.keyword` subfields on several text fields
- Derived fields needed: `has_breach`, `ubo_depth`, `risk_score`

---

## FIELD GROUPS

**Reference file**: `BACKEND/modules/CYMONIDES/field_groups.json`
**Resolver**: `BACKEND/modules/CYMONIDES/field_group_resolver.py`

43 semantic field groups across all indices:
- HIGH quality: EMAIL_RAW, EMAIL_DOMAIN, COMPANY_NAME, etc.
- MEDIUM quality: MIXED_NAME, USERNAME, etc.
- GARBAGE: Fields to exclude from user search

---

## FUZZY MATCHING PLAYBOOK

From ultrathink analysis:
- Use `fuzziness: "AUTO"` (not fixed values)
- `prefix_length: 2` for performance
- Company names: Strip designators before matching
- Person names: Handle reversed order, initials, nicknames
- Addresses: Normalize street abbreviations

---

## MULTI-HOP TRAVERSAL WORKFLOWS

5 key workflows identified:
1. **Person → Companies → Co-owners** (ownership network)
2. **Email → Breaches → Domains** (breach correlation)
3. **Company → UBOs → Ultimate Owners** (recursive)
4. **Domain → Backlinks → Related Domains** (link graph)
5. **Address → Properties → Owners** (property chain)

---

## RED FLAG DETECTION

Categories to implement:
- **Sanctions**: SDN, OFAC, blacklisted, designated
- **Fraud**: ponzi, pyramid scheme, embezzlement
- **PEP**: politically exposed, government official
- **Distress**: liquidation, insolvency, dissolved

---

## MULTI-DIMENSIONAL INDEXING OPPORTUNITIES

**Reference file**: `BACKEND/modules/CYMONIDES/multidimensional_indexing.json`

### New Dimensions Identified

| Dimension | Source | Type | Purpose |
|-----------|--------|------|---------|
| Ownership Control Spectrum | entity_links.control_types | ordinal | Filter by control strength (passive → full) |
| Breach Security Posture | breach_records.hash_type | ordinal | Filter by security tier (plaintext → bcrypt) |
| Publisher Credibility | wdc-*.publisher | ordinal | Filter by source reliability |
| Temporal Recency | entity_links.first_seen | ordinal | Filter by ownership age |
| Geographic Hierarchy | uk_ccod.county | hierarchical | Regional semantic expansion |
| Product Taxonomy | wdc-product-entities.category | hierarchical | Product category semantic |
| Link Relationship Type | cc_web_graph_edges.rel | categorical + semantic | Link intent classification |
| Schema Type Semantics | wdc-*.type | semantic | Business type matching |

### Compound Filter Examples
- `Person + UK + >25% ownership + acquired 2020-2024 + in breach records`
- `Company + offshore jurisdiction + multiple ownership layers + property assets`
- `Email + plaintext breach + same domain as company officer`

### Implementation Phases
1. **Derive Ordinals** - Add security_tier, credibility_tier, ownership_strength fields
2. **Embed Semantics** - Create embeddings for job titles, anchor texts, control types
3. **Composite Vectors** - embed(entity_type + industry + jurisdiction) as single vector

---

## NOTES

- All analysis from 2025-12-30 session (16 agents across 3 rounds)
- Industry embeddings were in `_archive/generated/`, copied to main `matrix/` dir
- Domain consolidation uses SQLite as intermediate storage before writing to atlas

---

## LINKS TO REFERENCE FILES

- `BACKEND/modules/CYMONIDES/strategic_embeddings.json` - Embedding opportunities
- `BACKEND/modules/CYMONIDES/query_patterns.json` - Query pattern analysis
- `BACKEND/modules/CYMONIDES/field_groups.json` - Semantic field groups
- `BACKEND/modules/CYMONIDES/field_group_resolver.py` - Python resolver
- `BACKEND/modules/DEFINITIONAL/unified_categories/` - Category embeddings
