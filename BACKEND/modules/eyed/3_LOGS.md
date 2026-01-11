# EYE-D - LOGS

> **Auto-updated by AI agents.** See `AGENT.md` for protocols.

---

## 2025-12-31 - GPT-5 - Linklater WHOIS Copy

**Completed:**
- Copied Linklater WHOIS discovery into EYE-D and adjusted path handling for the local module layout.
- Aligned the EYE-D whois wrapper to use the Linklater discovery helpers for historic/reverse lookups.

**Files:**
- `BACKEND/modules/EYE-D/whois_discovery.py`
- `BACKEND/modules/EYE-D/whois.py`

## 2025-12-31 - GPT-5 - Structured WHOIS History

**Completed:**
- Added Linklater-format structured WHOIS history to EYE-D’s `/api/whois` response (`structured_history`).
- Included distinct registrants extracted across historical records.

**Files:**
- `BACKEND/modules/EYE-D/whois.py`
- `BACKEND/modules/EYE-D/server.py`

## 2025-12-31 - GPT-5 - Shared WHOISXMLAPI

**Completed:**
- Centralized WhoisXML API calls and deterministic extraction in `BACKEND/modules/eyed/whoisxmlapi.py`.
- Updated EYE-D WHOIS wrapper and Linklater WHOIS discovery to use the shared helper; unified OSINT WHOIS now uses deterministic records.

**Files:**
- `BACKEND/modules/eyed/whoisxmlapi.py`
- `BACKEND/modules/EYE-D/whois.py`
- `BACKEND/modules/LINKLATER/discovery/whois_discovery.py`
- `BACKEND/modules/eyed/unified_osint.py`

## 2025-12-04 - Claude (Opus 4.5) - Documentation Session

**Duration:** Part of larger session
**Context:** Consolidating module documentation, standardizing AI protocols

**Completed:**
- Created `1_CONCEPT.md` with full module documentation
- Created `2_TODO.md` with outstanding tasks
- Created `3_LOGS.md` (this file)
- Documented all OSINT resources and their codes
- Mapped input/output Matrix codes (1,2,6,7 → 187-198)
- Documented connection type standardization

**Key Findings:**
- EYE-D has extensive feature history in CLAUDE.md (development log)
- Legend-aligned structure mirrors corporate modules for Matrix routing
- Five standardized connection types: Gray/White/Blue/Green/Red
- SQL integration enables cross-project entity sharing

**Architecture Summary:**
| Component | Purpose |
|-----------|---------|
| web/server.py | Flask API backend |
| web/graph.js | Vis.js graph frontend |
| legend/ | Matrix-aligned wrapper |
| resources/ | Individual OSINT sources |

**Next Steps:**
- Fix Google API credential configuration
- Complete legend module production hardening
- See `2_TODO.md` for full task list

---

## 2025-07-04 - Claude - MD Upload Feature

**Duration:** Multi-session
**Context:** Adding document upload for entity extraction

**Completed:**
- File upload endpoint with validation
- Frontend upload button and handler
- Document node creation for MD files
- Entity extraction in semi-circle pattern
- Green SOURCE edges from document to entities

**Key Features:**
- Reuses existing Claude entity extraction logic
- Maintains consistency with URL extraction patterns

---

## 2025-07-03 - Claude - URL Entity Extraction

**Duration:** Multi-session
**Context:** Extracting entities from web pages

**Completed:**
- Firecrawl scraping → Claude extraction → JSON entities
- Menu option "Extract Entities" on URL nodes
- Semi-circle node arrangement
- Green SOURCE edges, cyan relationship edges

**Technical Notes:**
- Uses same tool as image entity extraction
- Staggered animation for visual appeal

---

## 2025-07-02 - Claude - Major Feature Sprint

**Duration:** Full day
**Context:** Multiple feature implementations and bug fixes

**Completed:**
- Google search progress indication (live updates)
- Connection types standardization (5 types only)
- Duplicate node prevention (case-insensitive)
- Search provider selection modal
- URL paste feature with auto-connection
- Backlinks display as list node
- OCCRP Aleph "Unknown" fix
- Server resilience (fetchWithRetry, health checks)

**Blockers Resolved:**
- TypeError in findSimilarNodes (undefined data.value)
- TypeError in createNewNode (undefined type parameter)
- Case-sensitive duplicate detection

**Key Learning:**
- All node creation must pass type parameter to addNode()
- valueToNodeMap keys must be case-insensitive

---

## Template for Future Entries

```markdown
## [DATE] - [AGENT] - [SESSION TYPE]
**Duration:** X hours
**Context:** Why this work was done

**Completed:**
- Item 1
- Item 2

**Key Findings:**
- Finding 1
- Finding 2

**Blockers:** Any issues encountered

**Next Steps:** What should happen next
```
