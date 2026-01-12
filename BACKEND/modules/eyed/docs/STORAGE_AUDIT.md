# EYE-D Storage System Audit

## Current Architecture

### ✅ PRIMARY STORAGE: Cymonides-1 (Elasticsearch)

**What it stores:**
- All nodes (entities, companies, persons, emails, phones, etc.)
- All edges (relationships between entities)
- Node metadata (position, type, UI data)
- Embedded edges within nodes

**Index naming:**
`cymonides-1-{projectId}`

**Implementation:**
- `/data/EYE-D/server.py` uses `C1Bridge` from `LINKLATER.c1_bridge`
- `/api/c1/sync-node` - Upserts nodes to C-1
- `/api/c1/sync-edge` - Upserts edges to C-1 (as embedded_edges)
- `/api/c1/export` - Exports full project graph from C-1

**Status:** ✅ FULLY OPERATIONAL - Primary storage system

---

### SQLite Usage (Fallback & Cache Only)

**File:** `/data/EYE-D/cache/projects.db`
**Module:** `/data/EYE-D/projects.py`

**What it stores:**
1. **Project metadata ONLY** (fallback when PostgreSQL unavailable):
   - Project ID, name, description
   - Created/updated timestamps
   - Active status
   
2. **Local cache** (NOT primary storage):
   - Temporary graph state snapshots
   - Project listings when PostgreSQL is down

**NOT stored in SQLite:**
- ❌ Nodes (stored in C-1)
- ❌ Edges (stored in C-1)
- ❌ Entity data (stored in C-1)
- ❌ Relationships (stored in C-1)

**Code evidence:**
```python
# Line 1897-1898 in server.py
# Fall back to SQLite project manager if PostgreSQL not available
print("[SQLite] Falling back to SQLite project manager")
projects = project_manager.get_all_projects()
```

**Primary project manager:**
```python
# Line 1892 in server.py
pg_projects = get_postgresql_projects()  # Primary
```

---

### Additional SQLite Reference

**File:** `/data/EYE-D/search_graph.db`
**Purpose:** Bidirectional sync with SE (Search Engineer) Grid
**Code:**
```python
# Line 2531-2533 in server.py
se_db_path = "/Users/attic/SE/WEBAPP/search_graph.db"
print(f"[SE Grid Sync] Storing {len(nodes)} nodes and {len(edges)} edges in search_graph.db")
```

**Status:** Cross-system sync feature (optional, not primary storage)

---

## Summary

### ✅ CORRECT ARCHITECTURE
- **Primary node/edge storage:** Cymonides-1 (Elasticsearch) ✓
- **SQLite role:** Fallback for project metadata only ✓
- **No SQLite for entities:** All entities go to C-1 ✓

### Current Flow

1. User adds node → `/api/c1/sync-node` → C1Bridge → Cymonides-1
2. User adds edge → `/api/c1/sync-edge` → C1Bridge → Cymonides-1 (embedded_edges)
3. Export graph → `/api/c1/export` → Reads from Cymonides-1
4. Project metadata → PostgreSQL (primary) or SQLite (fallback)

### Recommendation

**Status: NO CHANGES NEEDED**

EYE-D is already correctly using Cymonides-1 as the primary storage system. SQLite is only used as:
1. Fallback for project metadata (when PostgreSQL unavailable)
2. Cross-system sync with Search Engineer

This is the correct architecture pattern:
- Heavy data (nodes/edges) → Elasticsearch (Cymonides-1)
- Metadata (projects) → PostgreSQL/SQLite
- No mixed concerns

**If you want to ensure SQLite is NEVER used for nodes/edges:**
Current code already enforces this - all node/edge operations go through C1Bridge with no SQLite alternative path.
