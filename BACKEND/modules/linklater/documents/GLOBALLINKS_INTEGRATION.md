# GlobalLinks Integration - Complete Reference

## Overview

LinkLater now has **FULL integration** with ALL GlobalLinks CLI tools. GlobalLinks is a backlink gathering system based on Common Crawl data that processes up to 300,000 pages per minute per thread.

## Binary Detection

All 4 GlobalLinks binaries are auto-detected in 3 candidate locations:
- `categorizer-filterer/globallinks/bin/`
- `categorizer-filterer/globallinks/globallinks-with-outlinker/bin/`
- `categorizer-filterer/globallinks/globallinks-ready/bin/`

### Available Binaries

| Binary | Size | Purpose |
|--------|------|---------|
| **outlinker** | 9.7 MB | Query backlinks/outlinks with advanced filtering |
| **linksapi** | 14 MB | API server for link queries |
| **storelinks** | 13 MB | Link storage/import into tree directory structure |
| **importer** | 11 MB | Data importer (processes Common Crawl WAT files) |

## Python API Methods

### 1. Basic Backlinks/Outlinks

```python
from modules.linklater.api import linklater

# Get backlinks (domains linking TO this domain)
backlinks = await linklater.get_backlinks("example.com", limit=100)
# Returns: List[LinkRecord] with source, target, weight, anchor_text

# Get outlinks (domains this domain links TO)
outlinks = await linklater.get_outlinks("example.com", limit=100)
```

### 2. Advanced Outlink Extraction (NEW)

Extract outlinks with **advanced filtering** capabilities:

```python
# Extract outlinks from BBC to UK government sites
results = await linklater.extract_domain_outlinks(
    domains=["bbc.com"],
    archive="CC-MAIN-2024-10",
    country_tlds=[".gov.uk"],
    max_results=1000
)

# Extract outlinks containing specific keywords
results = await linklater.extract_domain_outlinks(
    domains=["guardian.com", "independent.co.uk"],
    url_keywords=["news", "article"],
    archive="CC-MAIN-2024-10"
)

# Extract with exclusions
results = await linklater.extract_domain_outlinks(
    domains=["example.com"],
    country_tlds=[".uk", ".fr", ".de"],
    exclude_keywords=["spam", "ads"],
    max_results=500
)
```

**Parameters:**
- `domains`: List of source domains to extract from
- `archive`: Common Crawl archive name (e.g., `CC-MAIN-2024-10`)
- `country_tlds`: Filter outlinks to specific country TLDs (`.uk`, `.fr`, `.de`)
- `url_keywords`: Include only outlinks containing these keywords
- `exclude_keywords`: Exclude outlinks containing these keywords
- `max_results`: Maximum results per domain (default: 1000)

### 3. Local Link Data Search (NEW)

Search through locally stored GlobalLinks data:

```python
# Search for all links to BBC in local data
results = await linklater.search_domain_in_links(
    target_domain="bbc.com",
    data_path="data/links/"
)
```

### 4. Binary Detection

```python
# Find specific binary
outlinker_path = linklater.find_globallinks_binary("outlinker")
linksapi_path = linklater.find_globallinks_binary("linksapi")
storelinks_path = linklater.find_globallinks_binary("storelinks")
importer_path = linklater.find_globallinks_binary("importer")
```

## Direct CLI Usage

### Outlinker Commands

#### Extract Outlinks
```bash
./outlinker extract \
  --domains="bbc.com" \
  --country-tlds=".uk" \
  --archive=CC-MAIN-2024-10 \
  --max-results=1000 \
  --format=json
```

#### Search for Target Domain
```bash
./outlinker search \
  --target-domain=bbc.com \
  --input=data/links/
```

#### Filter Existing Data
```bash
./outlinker filter \
  --input=data.json \
  --country-tlds=.uk,.fr
```

### Importer (Data Processing)

Process Common Crawl WAT files:

```bash
./importer CC-MAIN-2021-04 900 4 0-10
# [archive_name] [num_files] [num_threads] [segments]
```

**Parameters:**
- Archive name: e.g., `CC-MAIN-2021-04`
- Number of files: Files to process (900 = 1 segment)
- Number of threads: Processing threads (1-16)
- Segments: Range like `0-10` or list like `2,3,4,5`

### Storelinks (Data Storage)

Distribute backlinks data into tree directory structure:

```bash
./storelinks data/links/compact_0.txt.gz data/linkdb
```

Compact links files:

```bash
./storelinks compacting \
  data/links/sort_50.txt.gz \
  data/links/compact_50.txt.gz
```

## Data Formats

### Link Format
```
LinkedDomain|LinkedSubdomain|LinkedPath|LinkedQuery|LinkedScheme|
PageHost|PagePath|PageQuery|PageScheme|LinkText|NoFollow|NoIndex|
DateImported|IP
```

Example:
```
blogmedyczny.edu.pl||/czasopisma-kobiece/||2|turysta24.pl|
/tabletki-odchudzajace/||2|Theme Palace|0|0|2023-02-04|51.75.43.178
```

### Page Format
```
sourceHost|sourcePath|sourceQuery|sourceScheme|pageTitle|ip|
date_imported|internal_links_qty|external_links_qty|noindex
```

## Performance & Scale

- **Processing Speed**: 300,000 pages/minute per thread
- **Common Crawl Coverage**: ~6 billion unique external backlinks per month
- **Memory Usage**: ~1.5 GB RAM per thread
- **Storage**: ~2 GB per segment (links + indexes)

## Environment Variables

```bash
# Control number of threads
export GLOBALLINKS_MAXTHREADS=4

# Control WAT files per batch
export GLOBALLINKS_MAXWATFILES=10

# Set data directory
export GLOBALLINKS_DATAPATH=data
```

## Data Storage Locations

```
data/
├── links/              # Final parsed segment links
├── pages/              # Final parsed segment pages
├── linkdb/             # Tree directory structure (from storelinks)
└── tmp/
    ├── links/          # Temporary segment link files
    ├── pages/          # Temporary segment page files
    └── wat/            # Downloaded WAT files
```

## Integration with CC Web Graph

GlobalLinks works **alongside** the CC Web Graph:

| Feature | CC Web Graph | GlobalLinks |
|---------|-------------|-------------|
| **Data Source** | Elasticsearch (157M domains, 2.1B edges) | Precomputed WAT files |
| **Query Speed** | Fast (HTTP API) | Fast (local binaries) |
| **Filtering** | Basic | Advanced (country TLDs, keywords) |
| **Anchor Text** | No | Yes |
| **Custom Crawls** | No | Yes (process any CC archive) |

**Use both for maximum coverage:**

```python
# Combines CC Web Graph + GlobalLinks automatically
backlinks = await linklater.get_backlinks(
    domain="example.com",
    limit=100,
    use_globallinks=True  # Default
)
```

## Docker Usage

```bash
# Build and run
make compose-up \
  ARCHIVENAME="CC-MAIN-2021-04" \
  GLOBALLINKS_MAXWATFILES=6 \
  GLOBALLINKS_MAXTHREADS=4

# Or use Docker Hub image
docker pull krisdevhub/globallinks:latest
docker run --name globallinks-test -d \
  -v ./watdata:/app/data \
  krisdevhub/globallinks:latest \
  /app/importer CC-MAIN-2021-04 4 2
```

## System Requirements

- **Go**: 1.21 or later
- **RAM**: 4GB minimum (6GB recommended for 4 threads)
- **Disk**: 50GB free per segment being processed
- **Tools**: `lzop` must be installed

## MongoDB Integration

Final data can be stored in MongoDB:
- Database: `linkdb`
- Collection: `links`
- Compression: zlib enabled
- Storage: ~1.6 GB per segment (collection + 300 MB indexes)

## Python API Summary

```python
from modules.linklater.api import linklater

# Basic queries (CC Graph + GlobalLinks)
await linklater.get_backlinks(domain, limit=100)
await linklater.get_outlinks(domain, limit=100)

# Advanced extraction (GlobalLinks only)
await linklater.extract_domain_outlinks(
    domains=["example.com"],
    archive="CC-MAIN-2024-10",
    country_tlds=[".uk", ".fr"],
    url_keywords=["news"],
    exclude_keywords=["spam"],
    max_results=1000
)

# Local data search (GlobalLinks only)
await linklater.search_domain_in_links(
    target_domain="bbc.com",
    data_path="data/links/"
)

# Binary detection
linklater.find_globallinks_binary("outlinker")
linklater.find_globallinks_binary("linksapi")
linklater.find_globallinks_binary("storelinks")
linklater.find_globallinks_binary("importer")
```

## Use Cases

1. **Investigative Research**: Find all backlinks to a domain with anchor text
2. **Country-Specific Analysis**: Extract only links to/from specific TLDs
3. **Keyword Tracking**: Find links containing specific keywords
4. **Historical Analysis**: Process any Common Crawl archive
5. **Custom Link Database**: Build your own link index with storelinks
6. **API Integration**: Run linksapi server for web-based queries

---

**Status**: ✅ FULLY INTEGRATED
**Methods Added**: 5 new methods
**Binaries Detected**: 4/4 (outlinker, linksapi, storelinks, importer)
**Date**: 2025-11-30
