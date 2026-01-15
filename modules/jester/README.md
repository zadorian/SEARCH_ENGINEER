# JESTER - The Unified Scraping & Intelligence System



---

## Directory Structure



---

## Core Components

### 1. SCRAPER (scraper.py) ⭐

The **ONLY** scraping interface. Everything uses this.



**Tier Fallback Order:**
| Tier | Backend | Concurrency | Use Case |
|------|---------|-------------|----------|
| A | httpx (Python) | 100 | Fast, simple sites (~60%) |
| B | Colly (Go) | 500 | Static HTML at scale |
| C | Rod (Go) | 100 | JavaScript rendering |
| D | Playwright | 50 | Complex SPAs |
| - | Firecrawl | API | Paid fallback |
| - | BrightData | API | Last resort (56524) |

---

### 2. MAPPER (MAPPER/mapper.py) ⭐

Discovers ALL URLs related to a domain.



**Discovery Sources:**
- **Subdomains**: crt.sh, WhoisXML, DNSDumpster, Sublist3r
- **Sitemaps**: sitemap.xml parsing
- **Search**: Google, Bing, Brave, DuckDuckGo (site: queries)
- **Archives**: Wayback CDX, CommonCrawl Index
- **Backlinks**: Majestic, CC WebGraph

---

### 3. EXTRACTOR (extractor.py)

Scrape + extract in one call.



---

### 4. CLASSIFIER (classifier.py)

AI-powered content classification.



---

### 5. EXECUTOR (executor.py)

SeekLeech engine - executes Matrix source queries.



---

## CLI Usage



---

## Concurrency Limits (sastre server)

| Tier | Default | Peak | Rate |
|------|---------|------|------|
| JESTER_A | 100 | 1000 | ~500 req/s |
| JESTER_B | 500 | 2000 | ~400 req/s |
| JESTER_C | 100 | 200 | ~50 req/s |
| JESTER_D | 50 | 100 | ~20 req/s |

Server: 20 cores, 64GB RAM, ulimit=65535

---

## Data Flow



---

## Environment Variables



---

## Related Modules

- **PACMAN**: Entity extraction patterns (uses JESTER for scraping)
- **LINKLATER**: Link relationship analysis (uses JESTER for fetching)
- **TORPEDO**: Company profile fetching (uses JESTER scraper)
- **BACKDRILL**: Archive/historical lookups
