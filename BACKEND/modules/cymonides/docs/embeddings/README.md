# CYMONIDES Embedding System

**Standard Model:** `intfloat/multilingual-e5-large` (1024D)
**Status:** ✅ Production Ready
**Last Updated:** 2026-01-08

---

## Quick Start

### Import StandardEmbedder:
```python
import sys
sys.path.insert(0, '/data')
from shared.embedders import get_embedder, encode_query, encode_passage

# Get embedder
embedder = get_embedder()

# Encode query
query_vec = embedder.encode_query("search term")

# Encode document
doc_vec = embedder.encode_passage("document text")
```

---

## Common Tasks

### 1. Batch Embed Domains

```bash
cd /data/CYMONIDES/scripts

# Embed 1000 domains with descriptions
python3 embed_domain_batch.py --limit 1000 --batch-size 32

# Custom query
python3 embed_domain_batch.py --query '{"term": {"country": "US"}}' --limit 5000
```

### 2. Semantic Search

```bash
cd /data/CYMONIDES/scripts

# Basic search
python3 semantic_search.py "AI research companies" --limit 20

# With filters
python3 semantic_search.py "fintech startups" --country US --limit 10
```

### 3. Test StandardEmbedder

```bash
cd /data
python3 shared/embedders/standard_embedder.py
# Expected: ✅ All tests passed
```

---

## Files in This Directory

| File | Description |
|------|-------------|
| `EMBEDDING_STANDARDIZATION.md` | Complete standardization documentation |
| `README.md` | This file - quick reference |

---

## Related Directories

| Directory | Purpose |
|-----------|---------|
| `/data/CYMONIDES/embedders/` | StandardEmbedder utility (copy of /data/shared/embedders) |
| `/data/CYMONIDES/scripts/` | Embedding scripts (embed_domain_batch.py, semantic_search.py) |
| `/data/shared/embedders/` | Original StandardEmbedder location |

---

## Modules Using StandardEmbedder

1. ✅ **NEXUS** - Relationship/code embeddings (already using)
2. ✅ **SUBJECT** - Profession/industry embeddings (already using)
3. ✅ **Industry Matcher** - LinkedIn industry matching (updated)
4. ✅ **PACMAN Tripwire** - Theme/red flag matching (updated)
5. ✅ **PACMAN Domain Embedder** - Domain content embeddings (updated, OpenAI removed)

---

## Elasticsearch Indexes with Vectors

| Index | Field | Dims | Documents |
|-------|-------|------|-----------|
| `nexus_relationships` | `vector` | 1024 | 79 |
| `nexus_codes` | `vector` | 1024 | 464 |
| `cymonides-2` | `content_embedding_e5` | 1024 | Growing |
| `domains_unified` | `content_vector_e5` | 1024 | To be added |

---

## Performance

**Embedding Speed (CPU):**
- Single doc: ~200-500ms
- Batch of 32: ~2-5 seconds
- Parallel (10 processes): ~5,000-10,000 docs/min

**Search Speed:**
- Vector kNN: <200ms
- Hybrid search: <300ms

**Storage:**
- Per document: 4KB (1024D × 4 bytes)
- 30-50M domains: 120-200GB

---

## Troubleshooting

**Error: "No module named 'shared.embedders'"**
```python
import sys
sys.path.insert(0, '/data')
from shared.embedders import get_embedder
```

**Error: "Model download slow"**
- First use downloads 1.1GB model (~5-10 min)
- Cached at: `~/.cache/torch/sentence_transformers/`

**Error: "Out of memory"**
```python
# Reduce batch size
embedder.encode_batch_passages(texts, batch_size=16)  # Default: 32
```

---

## Support

**Documentation:** `/data/CYMONIDES/docs/embeddings/EMBEDDING_STANDARDIZATION.md`

**Code:** 
- `/data/CYMONIDES/embedders/standard_embedder.py`
- `/data/CYMONIDES/scripts/`

**Testing:**
```bash
cd /data
python3 shared/embedders/standard_embedder.py
```
