# Migration Guide: Updating to StandardEmbedder

**For:** Developers updating code to use the standardized embedding system
**Date:** 2026-01-08

---

## Overview

All embedding code should now use `StandardEmbedder` for consistency.

**Standard Model:** `intfloat/multilingual-e5-large` (1024D)

---

## Migration Patterns

### Pattern 1: From SentenceTransformer

**Before:**
```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')  # or any other model
embedding = model.encode("text")
```

**After:**
```python
import sys
sys.path.insert(0, '/data')
from shared.embedders import get_embedder

embedder = get_embedder()

# For queries (searches)
embedding = embedder.encode_query("text")

# For passages (indexing)
embedding = embedder.encode_passage("text")
```

---

### Pattern 2: From OpenAI Embeddings

**Before:**
```python
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key=api_key)
response = await client.embeddings.create(
    input=["text1", "text2"],
    model="text-embedding-3-large"
)
embeddings = [e.embedding for e in response.data]
```

**After:**
```python
import sys
sys.path.insert(0, '/data')
from shared.embedders import get_embedder

embedder = get_embedder()

# Synchronous (no async needed)
embeddings = embedder.encode_batch_passages(
    ["text1", "text2"],
    batch_size=32
)
```

**Benefits:**
- FREE (no API costs)
- No rate limits
- Faster (no network latency)
- Synchronous (simpler code)

---

### Pattern 3: Custom Models

**Before:**
```python
from sentence_transformers import SentenceTransformer

# Custom model
model = SentenceTransformer('intfloat/multilingual-e5-base')  # 768D
embedding = model.encode("passage: text")
```

**After:**
```python
import sys
sys.path.insert(0, '/data')
from shared.embedders import get_embedder

# StandardEmbedder uses e5-large (1024D) automatically
embedder = get_embedder()
embedding = embedder.encode_passage("text")  # prefix added automatically
```

**Note:** Prefixes (`query:`, `passage:`) are added automatically by StandardEmbedder.

---

## Dimension Changes

If your code stores or checks embedding dimensions:

**Before:**
```python
EMBEDDING_DIM = 384   # all-MiniLM-L6-v2
EMBEDDING_DIM = 768   # e5-base
EMBEDDING_DIM = 3072  # OpenAI text-embedding-3-large
```

**After:**
```python
from shared.embedders import EMBEDDING_DIM  # Always 1024

# Or
embedder = get_embedder()
dims = embedder.dimensions  # 1024
```

---

## Elasticsearch Mapping Updates

### Before (various dimensions):
```json
{
  "content_embedding": {
    "type": "dense_vector",
    "dims": 384  // or 768, or 3072
  }
}
```

### After (standardized):
```json
{
  "content_vector_e5": {
    "type": "dense_vector",
    "dims": 1024,
    "index": true,
    "similarity": "cosine",
    "index_options": {
      "type": "int8_hnsw",
      "m": 16,
      "ef_construction": 100
    }
  }
}
```

---

## Batch Processing

### Before (OpenAI):
```python
async def embed_batch(texts):
    response = await client.embeddings.create(
        input=texts,
        model="text-embedding-3-large"
    )
    return [e.embedding for e in response.data]
```

### After (StandardEmbedder):
```python
def embed_batch(texts):
    embedder = get_embedder()
    return embedder.encode_batch_passages(
        texts,
        batch_size=32,
        show_progress=True
    )
```

**Changes:**
- Synchronous (no `async`/`await`)
- Batching handled internally
- No API costs
- Progress bar optional

---

## Error Handling

### Before:
```python
try:
    response = await client.embeddings.create(...)
except OpenAIError as e:
    logger.error(f"API error: {e}")
```

### After:
```python
try:
    embeddings = embedder.encode_batch_passages(...)
except Exception as e:
    logger.error(f"Embedding error: {e}")
```

**Note:** StandardEmbedder has no API errors (network, rate limits, etc.)

---

## Query vs Passage Encoding

**Important:** e5 models use different prefixes for asymmetric search.

### Queries (what you're searching for):
```python
query_vec = embedder.encode_query("AI research companies")
# Internally adds prefix: "query: AI research companies"
```

### Passages (what you're indexing):
```python
doc_vec = embedder.encode_passage("This company does AI research")
# Internally adds prefix: "passage: This company does AI research"
```

**Rule:** 
- Use `encode_query()` for search queries
- Use `encode_passage()` for documents/content

---

## Re-generating Embeddings

If you have existing embeddings in old dimensions:

### Option 1: Batch Re-embed
```bash
cd /data/CYMONIDES/scripts
python3 embed_domain_batch.py --limit 100000
```

### Option 2: On-demand Re-embed
```python
from elasticsearch import Elasticsearch
from shared.embedders import get_embedder

es = Elasticsearch(["http://localhost:9200"])
embedder = get_embedder()

# Get document
doc = es.get(index="domains_unified", id="example.com")

# Extract content
content = doc['_source']['company_description']

# Generate new embedding
new_embedding = embedder.encode_passage(content)

# Update
es.update(
    index="domains_unified",
    id="example.com",
    body={
        "doc": {
            "content_vector_e5": new_embedding
        }
    }
)
```

---

## Testing After Migration

### 1. Test Import:
```python
import sys
sys.path.insert(0, '/data')
from shared.embedders import get_embedder
embedder = get_embedder()
print(f"Dimensions: {embedder.dimensions}")  # Should be 1024
```

### 2. Test Single Encoding:
```python
vec = embedder.encode_query("test")
assert len(vec) == 1024, f"Expected 1024, got {len(vec)}"
print("✅ Single encoding works")
```

### 3. Test Batch Encoding:
```python
vecs = embedder.encode_batch_passages(["test1", "test2"])
assert len(vecs) == 2, "Expected 2 vectors"
assert all(len(v) == 1024 for v in vecs), "All vectors should be 1024D"
print("✅ Batch encoding works")
```

### 4. Test Similarity:
```python
import numpy as np

vec1 = embedder.encode_passage("AI research")
vec2 = embedder.encode_passage("artificial intelligence")

similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
assert similarity > 0.7, f"Expected high similarity, got {similarity}"
print(f"✅ Similarity works: {similarity:.4f}")
```

---

## Common Issues

### Issue 1: Wrong dimensions in Elasticsearch

**Symptom:** Error about vector dimensions mismatch

**Solution:** Check your ES mapping:
```bash
curl -s http://localhost:9200/your_index/_mapping | jq '.[] | .mappings.properties | to_entries[] | select(.value.type == "dense_vector")'
```

Update if needed:
```bash
curl -X PUT http://localhost:9200/your_index/_mapping -H 'Content-Type: application/json' -d '{
  "properties": {
    "content_vector_e5": {
      "type": "dense_vector",
      "dims": 1024,
      "index": true,
      "similarity": "cosine"
    }
  }
}'
```

### Issue 2: Async code with sync embedder

**Symptom:** `RuntimeError: cannot be called from a running event loop`

**Solution:** StandardEmbedder is synchronous. If you need to call from async code:

```python
import asyncio

async def async_function():
    embedder = get_embedder()
    
    # Option 1: Just call it (it's fast)
    embedding = embedder.encode_passage("text")
    
    # Option 2: Run in executor if blocking concerns
    loop = asyncio.get_event_loop()
    embedding = await loop.run_in_executor(
        None, 
        embedder.encode_passage, 
        "text"
    )
```

### Issue 3: Model not downloading

**Symptom:** Hangs on first use

**Solution:** Model downloads on first use (~1.1GB, 5-10 min)
```bash
# Pre-download
python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-large')"
```

---

## Checklist

Before deploying code with StandardEmbedder:

- [ ] Import `get_embedder` from `shared.embedders`
- [ ] Use `encode_query()` for search queries
- [ ] Use `encode_passage()` for documents
- [ ] Update dimension constants to 1024
- [ ] Update Elasticsearch mappings to 1024
- [ ] Remove OpenAI imports and API keys
- [ ] Test single and batch encoding
- [ ] Test similarity calculations
- [ ] Run on sample data before production

---

**Questions?** See `/data/CYMONIDES/docs/embeddings/EMBEDDING_STANDARDIZATION.md`
