# SUBMARINE - Smart Submersion Search Architecture

> **"Never brute-force what you can intelligently surface."**

## Core Principle

Instead of scanning 3.5 billion CC pages for a phone number (24 hours),
use ALL available indices as **submerging points** to narrow the target set
BEFORE touching raw WARC/WET data.

**Result:** 24 hours → minutes (for targeted searches)

---

## SUBMERGING POINTS (Filters Applied Before Fetch)

### 1. CC INDEX API (First Gate)
Query Common Crawl index for:
- Specific domains
- URL patterns (contains keyword)
- Date ranges
- MIME types
- Status codes
- Languages

**Output:** List of (WARC file, offset, length) tuples → fetch ONLY these segments

### 2. OUR ELASTIC INDICES (Intelligence Layer)

| Index | What It Knows | Use Case |
|-------|--------------|----------|
| `cymonides-1-*` | Known entities, queries, relationships | "Find pages mentioning THIS company" |
| `cymonides-2` | Raw ingest corpus (scraped/search results) | "Already have this content (raw)?" |
| `cymonides-3` | Home/unified corpus (deduped + normalized docs) | "Already have this content (home)?" |
| `atlas-domains` | Domain metadata, categories | "Corporate sites only" |
| `atlas-urls` | URL-level intelligence | "Skip already-processed URLs" |
| `onion-*` | Dark web pages | Include/exclude Tor |

### 3. DOMAIN INTELLIGENCE

| Source | Filter |
|--------|--------|
| Domain rankings | Top 1M only / Long tail only |
| Torpedo news sources | News domains by country |
| Category taxonomy | Corporate, government, news, social |
| TLD filtering | .gov only, exclude .ru, etc |
| WHOIS age | Domains older than X years |

### 4. TEMPORAL FILTERS

- CC archive selection (CC-MAIN-2024-51, etc.)
- First-seen / last-seen dates
- Crawl date ranges
- Content age (via page timestamps)

### 5. CONTENT HINTS (From CC Index)

- MIME type (text/html, application/pdf)
- Content length (skip tiny/huge)
- Detected language
- Charset

---

## ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                        SUBMARINE                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   PERISCOPE  │    │   SONAR      │    │   TORPEDO    │       │
│  │  (CC Index)  │    │ (Our Indices)│    │   (News)     │       │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘       │
│         │                   │                   │                │
│         └─────────┬─────────┴─────────┬─────────┘                │
│                   │                   │                          │
│                   ▼                   ▼                          │
│         ┌─────────────────────────────────────┐                  │
│         │         DIVE PLANNER                │                  │
│         │  (Merge & dedupe target URLs)       │                  │
│         │  (Calculate WARC segments needed)   │                  │
│         │  (Estimate time/bandwidth)          │                  │
│         └─────────────────┬───────────────────┘                  │
│                           │                                      │
│                           ▼                                      │
│         ┌─────────────────────────────────────┐                  │
│         │         DEEP DIVE                   │                  │
│         │  (Go WARC fetcher - parallel)       │                  │
│         │  (Stream decompress + regex)        │                  │
│         │  (No local storage needed)          │                  │
│         └─────────────────┬───────────────────┘                  │
│                           │                                      │
│                           ▼                                      │
│         ┌─────────────────────────────────────┐                  │
│         │         EXTRACTION                  │                  │
│         │  (PACMAN entity extraction)         │                  │
│         │  (Pattern matching)                 │                  │
│         │  (Results → Cymonides)              │                  │
│         └─────────────────────────────────────┘                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## MODULES

### PERISCOPE - CC Index Intelligence
- Query CC Index API for domain/URL patterns
- Returns WARC coordinates (file, offset, length)
- Supports wildcard domains, URL contains, date ranges

### SONAR - Our Index Scanner
- Query our Elastic indices for relevant domains/URLs
- Cross-reference with CC Index to get WARC locations
- Exclude already-processed content (dedup)

### TORPEDO - News Source Filter
- Use Torpedo news source database
- Filter by country, language, category
- News-specific date handling

### DIVE PLANNER - Target Coordinator
- Merge results from all submerging points
- Deduplicate URLs
- Calculate optimal WARC fetch order (minimize file touches)
- Estimate time and bandwidth
- Generate fetch manifest

### DEEP DIVE - Go WARC Streamer
- Parallel HTTP range requests to CC S3
- Stream decompress (gzip)
- Apply regex/pattern on-the-fly
- Zero local storage (pure streaming)
- Report matches in real-time

### EXTRACTION - Entity Pipeline
- PACMAN patterns (phone, email, company, etc.)
- GLiNER NER (if needed)
- Results → Cymonides nodes + edges

---

## EXAMPLE WORKFLOWS

### 1. Find Phone Number Globally
```
INPUT: +36 1 234 5678

PERISCOPE: Skip (no domain hint)
SONAR: Check if number exists in our indices → found in 3 domains
DIVE PLANNER: Get CC coordinates for those 3 domains (500 URLs)
DEEP DIVE: Fetch 500 WARC segments, search for phone pattern
EXTRACTION: Create nodes for matches

TIME: ~2 minutes (vs 24 hours brute force)
```

### 2. Find All Mentions of Company in News
```
INPUT: "Acme Corp" in news sources

TORPEDO: Get list of 50,000 news domains
PERISCOPE: Query CC Index for those domains + "acme"
SONAR: Exclude already-in-corpus URLs
DIVE PLANNER: 15,000 target URLs across 200 WARC files
DEEP DIVE: Parallel fetch + extract
EXTRACTION: Company mentions → Cymonides

TIME: ~30 minutes
```

### 3. Domain Deep Dive
```
INPUT: example.com full history

PERISCOPE: Query CC Index for example.com (all archives 2013-2024)
SONAR: What do we already have?
DIVE PLANNER: 50,000 unique URLs, 2,000 WARC segments
DEEP DIVE: Fetch all, extract content
EXTRACTION: Full entity extraction

TIME: ~1 hour
```

---

## SUBMERGING POINT PRIORITY

For maximum efficiency, apply filters in this order:

1. **Domain filter** (most selective)
2. **Date range** (reduces archives to search)
3. **Our indices** (dedup what we have)
4. **CC Index query** (get precise WARC coordinates)
5. **Content hints** (MIME, language, size)

Each step should reduce the target set by 10-1000x.

---

## FILE STRUCTURE

```
/data/SUBMARINE/
├── 1_CONCEPT.md          # This file
├── 2_TODO.md             # Tasks
├── 3_LOGS.md             # Session logs
├── periscope/            # CC Index client
│   ├── cc_index.py       # Python client
│   └── cc_index.go       # Go client (faster)
├── sonar/                # Our index scanner
│   ├── elastic_scanner.py
│   └── dedup.py
├── dive_planner/         # Target coordinator
│   ├── planner.py
│   └── manifest.py
├── deep_dive/            # Go WARC streamer
│   ├── cmd/
│   │   └── submarine/
│   │       └── main.go
│   └── pkg/
│       ├── warc/
│       └── patterns/
├── extraction/           # Entity extraction
│   └── pacman_bridge.py
└── cli.py                # Unified CLI
```

---

## DEPENDENCIES

- CC Index API (cdx-api.commoncrawl.org)
- Our Elasticsearch cluster
- Go 1.21+ (for WARC streaming)
- PACMAN patterns (/data/PACMAN)

---

## METRICS

Track for each dive:
- URLs targeted vs URLs fetched
- Bytes downloaded
- Time elapsed
- Matches found
- Dedup hits (already had content)
- Filter efficiency (% reduction at each submerging point)
