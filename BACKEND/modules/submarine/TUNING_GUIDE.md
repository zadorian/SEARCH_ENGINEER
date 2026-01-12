# SUBMARINE TUNING GUIDE

**All configurable performance parameters for optimal crawling**

---

## Quick Tuning Chart

| Scenario | Workers | Concurrent/Worker | ES Heap | Max Pages | Time Multiplier |
|----------|---------|-------------------|---------|-----------|-----------------|
| **Maximum Speed** | 19 | 30 | 32GB | 30 | 1.0× (fastest) |
| **Balanced** | 19 | 20 | 24GB | 50 | 1.3× |
| **Conservative** | 10 | 20 | 24GB | 50 | 2.0× |
| **ES Stability** | 8 | 15 | 24GB | 50 | 2.5× |
| **Heavy Sites** | 10 | 10 | 24GB | 100 | 3.0× |

---

## 1. Worker Count

**File:** `/data/SUBMARINE/launch_parallel_crawl.sh`  
**Line:** `WORKERS=19`

**Guidelines:**
- **Maximum:** 20 (matches CPU cores, leaves 1 for system)
- **Balanced:** 15-19 (recommended)
- **Conservative:** 8-12 (ES stability issues)
- **Minimum:** 5 (below this, too slow)

**When to reduce:**
- ES connection errors
- High memory usage (>90%)
- Server load >20

**Command:**
```bash
sed -i 's/WORKERS=19/WORKERS=15/' /data/SUBMARINE/launch_parallel_crawl.sh
```

---

## 2. Concurrent Domains per Worker

**File:** `/data/SUBMARINE/jester_crawler_pacman.py`  
**Line 491:** `DOMAINS_CONCURRENT = 20`

**Guidelines:**
- **Light sites:** 30-40 (news, blogs)
- **Balanced:** 20 (recommended default)
- **Heavy sites:** 10-15 (JS-heavy, slow)
- **ES stability:** 10-15

**Impact:**
- Higher = faster but more memory/connections
- Lower = slower but more stable

**Change:**
```bash
sed -i 's/DOMAINS_CONCURRENT = 20/DOMAINS_CONCURRENT = 30/' /data/SUBMARINE/jester_crawler_pacman.py
```

**Total concurrent domains = Workers × Concurrent:**
- 19 workers × 20 = 380 domains
- 19 workers × 30 = 570 domains (maximum recommended)

---

## 3. HTTP Concurrency per Domain

**File:** `/data/SUBMARINE/jester_crawler_pacman.py`  
**Lines 51-53:**
```python
CONCURRENT_A = 200  # httpx requests
CONCURRENT_B = 50   # Colly Go
CONCURRENT_C = 25   # Rod Go
```

**CONCURRENT_A (httpx - Tier A):**
- **Fast sites:** 300-500
- **Balanced:** 200 (default)
- **Rate-limited:** 50-100

**CONCURRENT_B (Colly - Tier B):**
- **Maximum:** 100
- **Balanced:** 50 (default)
- **Conservative:** 25

**CONCURRENT_C (Rod - Tier C):**
- **Maximum:** 50
- **Balanced:** 25 (default)
- **Memory-limited:** 10-15

**Change:**
```bash
# For faster crawling
sed -i 's/CONCURRENT_A = 200/CONCURRENT_A = 300/' /data/SUBMARINE/jester_crawler_pacman.py

# For slower sites
sed -i 's/CONCURRENT_A = 200/CONCURRENT_A = 100/' /data/SUBMARINE/jester_crawler_pacman.py
```

---

## 4. Pages per Domain

**Parameter:** `--max-pages`  
**Default:** 50

**Guidelines:**
- **Quick survey:** 10-20 pages
- **Balanced:** 50 pages (default)
- **Deep crawl:** 100-200 pages
- **Exhaustive:** 500+ pages (slow)

**Usage:**
```bash
./launch_parallel_crawl.sh domains.txt 100  # 100 pages per domain
```

**Time impact:**
- 20 pages: 0.4× base time
- 50 pages: 1.0× base time
- 100 pages: 1.8× base time (not 2× due to 404s/redirects)

---

## 5. Crawl Depth

**Parameter:** `--max-depth`  
**Default:** 2

**Guidelines:**
- **Front page only:** 0 (use jester_tiered_pacman.py instead)
- **Light crawl:** 1 (front page + direct links)
- **Balanced:** 2 (default - goes 2 levels deep)
- **Deep crawl:** 3-4 (very slow, often redundant)

**Usage:**
```bash
./launch_parallel_crawl.sh domains.txt 50 3  # Depth 3
```

**Time impact:**
- Depth 1: 0.5× base time
- Depth 2: 1.0× base time
- Depth 3: 2.5× base time (exponential growth)

---

## 6. Elasticsearch Heap

**File:** `/etc/elasticsearch/jvm.options.d/heap.options`

**Current:** 24GB

**Guidelines:**
- **Minimum:** 16GB
- **Balanced:** 24GB (current)
- **Maximum:** 32GB (leaves 32GB for system/workers)
- **Never exceed:** 50% of total RAM (64GB server = 32GB max)

**Change:**
```bash
echo -e '-Xms28g\n-Xmx28g' > /etc/elasticsearch/jvm.options.d/heap.options
systemctl restart elasticsearch
```

**When to increase:**
- Frequent ES OOM kills
- Many workers (15+)
- Large documents

**When to decrease:**
- System OOM (not ES OOM)
- Workers getting killed
- High swap usage

---

## 7. Worker Batch Launching

**File:** `/data/SUBMARINE/launch_parallel_crawl.sh`  
**Lines:**
```bash
WORKERS_PER_BATCH=5  # Workers per batch
BATCH_DELAY=60       # Seconds between batches
```

**WORKERS_PER_BATCH:**
- **Fast:** 8-10 (if ES stable)
- **Balanced:** 5 (default)
- **Conservative:** 3 (ES connection issues)

**BATCH_DELAY:**
- **Fast:** 30 seconds
- **Balanced:** 60 seconds (default)
- **Conservative:** 90-120 seconds

**When to increase delays:**
- ES connection errors during startup
- Workers failing immediately
- Connection refused in logs

---

## 8. ES Index Settings

**Shards:** 3 (default)  
**Replicas:** 0 (single-node cluster)

**Change shards** (before index creation):
```bash
# In launch_parallel_crawl.sh, line ~42
sed -i 's/number_of_shards: 3/number_of_shards: 5/' /data/SUBMARINE/launch_parallel_crawl.sh
```

**Guidelines:**
- **Small crawl (<1M docs):** 1-2 shards
- **Medium (1-10M docs):** 3-5 shards (default 3)
- **Large (10M+ docs):** 5-10 shards

**More shards = better indexing parallelism but higher overhead**

---

## 9. URL Filtering

**File:** `/data/SUBMARINE/jester_crawler_pacman.py`  
**Lines 28-29:**
```python
SKIP_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.gif', ...}
SKIP_PATHS = {'wp-content', 'wp-includes', 'cdn-cgi', ...}
```

**Add more exclusions:**
```python
SKIP_EXTENSIONS.add('.mp4')
SKIP_EXTENSIONS.add('.zip')
SKIP_PATHS.add('downloads')
SKIP_PATHS.add('media')
```

**When to add:**
- Crawling many media-heavy sites
- Want only HTML content
- Reducing storage

---

## 10. PACMAN Entity Extraction

**Enabled by default on all pages**

**To disable** (faster but no entities):
```bash
# In jester_crawler_pacman.py, comment out extraction calls
# Lines where extract_fast() is called
```

**Extraction patterns** (lines 47-61):
- EMAIL, PHONE, LEI, IBAN, BTC, ETH, etc.

**To add custom patterns:**
```python
FAST_PATTERNS['CUSTOM'] = re.compile(r'your-pattern-here')
```

---

## Recommended Configurations

### For Speed (Stable ES)
```bash
# launch_parallel_crawl.sh
WORKERS=19
WORKERS_PER_BATCH=8
BATCH_DELAY=30

# jester_crawler_pacman.py
DOMAINS_CONCURRENT = 30
CONCURRENT_A = 300

# Command
./launch_parallel_crawl.sh domains.txt 30 2  # 30 pages, depth 2

# ES heap
echo -e '-Xms32g\n-Xmx32g' > /etc/elasticsearch/jvm.options.d/heap.options
```

**Result:** ~4-5 hours for 2.8M domains

---

### For Quality (Deep crawl)
```bash
# launch_parallel_crawl.sh
WORKERS=10

# jester_crawler_pacman.py
DOMAINS_CONCURRENT = 15

# Command
./launch_parallel_crawl.sh domains.txt 100 3  # 100 pages, depth 3
```

**Result:** ~20-30 hours for 2.8M domains, very comprehensive

---

### For Stability (ES issues)
```bash
# launch_parallel_crawl.sh
WORKERS=8
WORKERS_PER_BATCH=3
BATCH_DELAY=90

# jester_crawler_pacman.py
DOMAINS_CONCURRENT = 15
CONCURRENT_A = 150

# ES heap (don't go higher)
echo -e '-Xms24g\n-Xmx24g' > /etc/elasticsearch/jvm.options.d/heap.options
```

**Result:** ~12-16 hours for 2.8M domains, stable

---

## Monitoring Commands

```bash
# Active workers
ps aux | grep jester_crawler_pacman | wc -l

# ES health
curl -s http://localhost:9200/_cluster/health | jq .status

# ES heap usage
curl -s http://localhost:9200/_cat/nodes?h=heap.percent

# Document count
curl -s http://localhost:9200/submarine-scrapes/_count | jq .count

# System load
uptime

# Memory usage
free -h

# Worker logs
tail -f /tmp/crawler_1.log
```

---

## Troubleshooting Performance

### Crawl Too Slow
1. Increase `DOMAINS_CONCURRENT` to 30
2. Increase `WORKERS` to 19
3. Reduce `max_pages` to 30
4. Increase `CONCURRENT_A` to 300

### ES OOM Kills
1. Reduce `WORKERS` to 10
2. Reduce `DOMAINS_CONCURRENT` to 15
3. Increase `BATCH_DELAY` to 90
4. Increase ES heap to 28GB (max 32GB)

### Workers Crashing
1. Check `/tmp/crawler_*.log` for errors
2. Reduce `CONCURRENT_A` to 100
3. Reduce `max_pages` to 30
4. Check for network issues

### High Memory Usage
1. Reduce `DOMAINS_CONCURRENT` to 10
2. Reduce `WORKERS` to 10
3. Reduce `CONCURRENT_A` to 100
4. Add more `SKIP_EXTENSIONS`

---

## Quick Tuning Commands

```bash
# Check current settings
grep 'WORKERS=' /data/SUBMARINE/launch_parallel_crawl.sh
grep 'DOMAINS_CONCURRENT' /data/SUBMARINE/jester_crawler_pacman.py
cat /etc/elasticsearch/jvm.options.d/heap.options

# Change workers
sed -i 's/WORKERS=19/WORKERS=15/' /data/SUBMARINE/launch_parallel_crawl.sh

# Change concurrent
sed -i 's/DOMAINS_CONCURRENT = 20/DOMAINS_CONCURRENT = 30/' /data/SUBMARINE/jester_crawler_pacman.py

# Change ES heap
echo -e '-Xms28g\n-Xmx28g' > /etc/elasticsearch/jvm.options.d/heap.options
systemctl restart elasticsearch
```

---

## Current Configuration (Conservative)

```
Workers: 10
Concurrent per worker: 20
Total concurrent: 200
ES heap: 24GB
Max pages: 50
Depth: 2
Expected time: 10-14 hours for 2.8M domains
```

**To return to maximum speed:**
```bash
sed -i 's/WORKERS=10/WORKERS=19/' /data/SUBMARINE/launch_parallel_crawl.sh
sed -i 's/DOMAINS_CONCURRENT = 20/DOMAINS_CONCURRENT = 30/' /data/SUBMARINE/jester_crawler_pacman.py
echo -e '-Xms32g\n-Xmx32g' > /etc/elasticsearch/jvm.options.d/heap.options
systemctl restart elasticsearch
```

**New expected time: 4-6 hours for 2.8M domains**
