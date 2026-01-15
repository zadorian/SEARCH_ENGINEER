# JESTER Architecture & File Reference

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              JESTER ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│   │   SCRAPER   │───▶│  EXTRACTOR  │───▶│ CLASSIFIER  │───▶│  REPORTER   │ │
│   │  (scraper)  │    │ (extractor) │    │(classifier) │    │ (reporter)  │ │
│   └──────┬──────┘    └─────────────┘    └─────────────┘    └─────────────┘ │
│          │                                                                  │
│          ▼                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                        SCRAPING TIERS                                │  │
│   │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────────┐  │  │
│   │  │JESTER_A │  │JESTER_B │  │JESTER_C │  │JESTER_D │  │ FIRECRAWL │  │  │
│   │  │ httpx   │  │  Colly  │  │   Rod   │  │Playwright│  │   API     │  │  │
│   │  │ Python  │  │   Go    │  │   Go    │  │  Python │  │  Fallback │  │  │
│   │  │  100/s  │  │  500/s  │  │  100/s  │  │   50/s  │  │   Paid    │  │  │
│   │  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └───────────┘  │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                           MAPPER                                     │  │
│   │  URL Discovery: subdomains, sitemaps, search, archives, backlinks   │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                      ELASTICSEARCH                                   │  │
│   │              jester_atoms index (structured storage)                 │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## File Reference

### Core Files (⭐ = Primary Entry Points)

| File | Purpose |
|------|---------|
| **scraper.py** ⭐ | Unified scraping with tiered fallback (A→B→C→D→Firecrawl) |
| **__init__.py** | Module exports: Jester, JesterConfig, JesterMethod, JesterResult |
| **jester_cli.py** | CLI interface for scraping operations |
| **jester_mcp.py** | MCP server for Claude/AI integration |

### Scraping Backend (scraping/)

| File | Purpose |
|------|---------|
| **go_bridge.py** | Python interface to Colly/Rod Go binaries |
| **crawler.py** | Drill/DrillConfig for Playwright tier (JESTER_D) |
| **go/bin/colly_crawler_linux** | Go binary: static HTML scraping (500 concurrent) |
| **go/bin/rod_crawler_linux** | Go binary: JS rendering (100 concurrent) |

### URL Discovery (MAPPER/)

| File | Purpose |
|------|---------|
| **mapper.py** ⭐ | Main URL discovery orchestrator |
| **config.py** | API keys, rate limits, timeouts |
| **models.py** | Data models (DiscoveredURL, etc) |
| **benchmark.py** | Performance testing |
| **sources/subdomains.py** | crt.sh, WhoisXML, DNSDumpster |
| **sources/sitemaps.py** | sitemap.xml parsing |
| **sources/search_engines.py** | Google, Bing, Brave site: queries |
| **sources/backlinks.py** | Majestic, CC WebGraph |
| **sources/firecrawl.py** | Firecrawl MAP + CRAWL |
| **sources/elasticsearch_source.py** | Query existing ES index |
| **sources/backdrill_bridge.py** | Archive lookup integration |
| **sources/linklater_bridge.py** | Link relationship integration |

### Processing Pipeline

| File | Purpose |
|------|---------|
| **extractor.py** | Scrape + extract outlinks/entities in one call |
| **gliner_extractor.py** | GLiNER NER model for entity extraction |
| **classifier.py** | AI classification (Claude/GPT) into topics |
| **reporter.py** | Generate markdown reports from atoms |

### Data & Execution

| File | Purpose |
|------|---------|
| **executor.py** | SeekLeech engine - Matrix source query execution |
| **harvester.py** | Research component - find/download content |
| **ingester.py** | PDF/document ingestion to atoms |
| **elastic_manager.py** | Elasticsearch CRUD operations |

### Analysis & Integration

| File | Purpose |
|------|---------|
| **inspector_gadget.py** | Gemini long-context document analysis |
| **auditor.py** | Quality/validation checks |
| **linklater_bridge.py** | Link relationship module integration |
| **main.py** | Legacy CLI entry point |

### Scripts (Experiments & Validation)

| File | Purpose |
|------|---------|
| run_experiments.py | Wave 1 experiments |
| run_experiments_wave2.py | Wave 2 experiments |
| run_news_experiments.py | News source testing |
| run_enhanced_discovery.py | Enhanced URL discovery |
| run_seekleech_full.py | Full SeekLeech pipeline |
| classify_news_sources.py | News source classification |
| classify_scrape_method.py | Scrape method analysis |
| retry_blocked_brightdata.py | Retry blocked URLs via BrightData |
| merge_brightdata_to_sources.py | Merge BrightData results |
| validate_news_full_pipeline.py | Full pipeline validation |
| verify_deployment.py | Deployment health checks |
| verify_smart_fill.py | Smart fill feature tests |
| verify_with_strict_criteria.py | Strict validation tests |
| test_seekleech.py | SeekLeech unit tests |

---

## Data Flow

```
URL Input
    │
    ▼
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│ SCRAPER │────▶│EXTRACTOR│────▶│CLASSIFIER────▶│REPORTER │
│  (A→D)  │     │(outlinks│     │ (AI tag)│     │(markdown│
│         │     │entities)│     │         │     │ output) │
└─────────┘     └─────────┘     └─────────┘     └─────────┘
    │                │                │              │
    ▼                ▼                ▼              ▼
┌─────────────────────────────────────────────────────────┐
│                    ELASTICSEARCH                         │
│                   (jester_atoms)                         │
└─────────────────────────────────────────────────────────┘
```

---

## Scraping Tiers

| Tier | Backend | Concurrency | When Used |
|------|---------|-------------|-----------|
| **A** | httpx (Python) | 100 | Fast, simple sites (~60%) |
| **B** | Colly (Go) | 500 | Static HTML at scale |
| **C** | Rod (Go) | 100 | JavaScript required |
| **D** | Playwright | 50 | Complex SPAs |
| **-** | Firecrawl API | - | When all tiers fail |
| **-** | BrightData | - | Last resort (expensive) |

---

## Usage Examples

### Basic Scraping
```python
from modules.JESTER import Jester, JesterMethod

jester = Jester()
result = await jester.scrape("https://example.com")
print(result.html, result.method)
```

### Batch Scraping (High Concurrency)
```python
# Native Go concurrency
results = await jester.scrape_batch_b(urls, max_concurrent=500)
results = await jester.scrape_batch_c(urls, max_concurrent=100)
```

### URL Discovery
```python
from modules.JESTER.MAPPER import Mapper

async with Mapper() as mapper:
    async for url in mapper.map_domain("example.com"):
        print(url.url, url.source)
```

### CLI
```bash
python jester_cli.py scrape https://example.com
python jester_cli.py scrape https://example.com --method B
python jester_cli.py batch urls.txt --concurrent 500
```

---

## Concurrency Limits (sastre server)

| Tier | Default | Peak | Notes |
|------|---------|------|-------|
| A | 100 | 1000 | Python asyncio |
| B | 500 | 2000 | Go native |
| C | 100 | 200 | Go + Chrome |
| D | 50 | 100 | Playwright |

Server specs: 20 cores, 64GB RAM, ulimit=65535

---

## Related Modules

| Module | Relationship |
|--------|--------------|
| **PACMAN** | Uses JESTER for scraping, extracts entities |
| **LINKLATER** | Uses JESTER for fetching, analyzes link relationships |
| **TORPEDO** | Uses JESTER scraper for company profiles |
| **BACKDRILL** | Archive/historical lookups |
