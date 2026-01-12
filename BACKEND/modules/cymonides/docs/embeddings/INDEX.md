# CYMONIDES Embedding Documentation Index

**Last Updated:** 2026-01-08

---

## Quick Links

| Document | Purpose |
|----------|---------|
| **[README.md](README.md)** | Quick start guide and common tasks |
| **[EMBEDDING_STANDARDIZATION.md](EMBEDDING_STANDARDIZATION.md)** | Complete standardization documentation |
| **[MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)** | Updating existing code to StandardEmbedder |

---

## Documentation Files

### 1. README.md
**Quick Reference**
- Import StandardEmbedder
- Common tasks (batch embed, semantic search)
- Troubleshooting

### 2. EMBEDDING_STANDARDIZATION.md
**Complete Documentation**
- Executive summary
- Model details (intfloat/multilingual-e5-large)
- All modules updated
- Storage and performance benchmarks
- Cost savings ($500-2,000+)
- Usage guide
- Elasticsearch integration
- Verification tests

### 3. MIGRATION_GUIDE.md
**Developer Guide**
- Migration patterns (from SentenceTransformer, OpenAI, etc.)
- Dimension changes
- Batch processing updates
- Query vs passage encoding
- Testing after migration
- Common issues and solutions

---

## Code Locations

### StandardEmbedder Utility:
- **Primary:** `/data/shared/embedders/`
- **Copy:** `/data/CYMONIDES/embedders/`

### Scripts:
- `/data/CYMONIDES/scripts/embed_domain_batch.py` - Batch embed domains
- `/data/CYMONIDES/scripts/semantic_search.py` - Semantic search CLI

---

## Updated Modules

1. ✅ **StandardEmbedder** - NEW utility (1024D)
2. ✅ **NEXUS** - Already using (1024D)
3. ✅ **SUBJECT** - Already using (1024D)
4. ✅ **Industry Matcher** - Updated (384D → 1024D)
5. ✅ **PACMAN Tripwire** - Updated (768D → 1024D)
6. ✅ **PACMAN Domain Embedder** - Updated (OpenAI 3072D → e5-large 1024D)

---

## Key Information

**Standard Model:** `intfloat/multilingual-e5-large`
**Dimensions:** 1024
**Storage per doc:** 4KB
**Cost:** FREE (no API fees)
**Languages:** 100+

**Performance (CPU):**
- Single: ~200-500ms
- Batch (32): ~2-5s
- Throughput: ~5,000-10,000 docs/min (parallel)

**Elasticsearch Field Name:** `content_vector_e5`

---

## Getting Started

### 1. Test StandardEmbedder:
```bash
cd /data
python3 shared/embedders/standard_embedder.py
```

### 2. Batch Embed Domains:
```bash
cd /data/CYMONIDES/scripts
python3 embed_domain_batch.py --limit 1000
```

### 3. Semantic Search:
```bash
cd /data/CYMONIDES/scripts
python3 semantic_search.py "AI research companies"
```

---

## Backups

Original files backed up before modification:

1. `/data/INPUT_OUTPUT/matrix/industry_matcher.py.backup_384d`
2. `/data/PACMAN/embeddings/tripwire_embeddings.py.backup_768d`
3. `/data/PACMAN/embeddings/domain_embedder.py.backup_openai3072d`

---

## Support

**Questions or Issues?**
- Check the documentation files above
- Test with: `python3 /data/shared/embedders/standard_embedder.py`
- Review migration guide for code updates

**Implementation Date:** 2026-01-08
**Status:** ✅ PRODUCTION READY
