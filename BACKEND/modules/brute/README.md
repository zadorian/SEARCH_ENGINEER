# brute

Multi-engine search orchestrator - maximum recall across 40+ search engines with memory-optimized streaming, filtering, and categorization.

## Architecture

```
                                brute
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  ┌──────────────┐                                               │
│  │    Query     │                                               │
│  └──────┬───────┘                                               │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  Engine Orchestration                    │   │
│  │  ┌─────┐┌─────┐┌─────┐┌─────┐┌─────┐┌─────┐┌─────┐       │   │
│  │  │ GO  ││ BI  ││ BR  ││ DD  ││ YA  ││ YE  ││ ...│ 40+   │   │
│  │  │Google│Bing │Brave │DDG  │Yandex│ Yep  │engines│       │   │
│  │  └──┬──┘└──┬──┘└──┬──┘└──┬──┘└──┬──┘└──┬──┘└──┬──┘       │   │
│  │     └──────┴──────┴──────┴──────┴──────┴──────┘          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  Processing Pipeline                     │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   │
│  │  │   Memory    │  │   Snippet   │  │   Filter    │       │   │
│  │  │  Streaming  │  │ Aggregation │  │   Manager   │       │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   │
│  │  │ Checkpoint  │  │  Progress   │  │  Engine     │       │   │
│  │  │   Manager   │  │   Monitor   │  │  Analytics  │       │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Output Layer                          │   │
│  │  ┌─────────────────────────────────────────────────────┐ │   │
│  │  │              SQLite Storage + Entity Graph          │ │   │
│  │  │  • Disk-based deduplication                         │ │   │
│  │  │  • Categorization (gpt-4.1-nano)                    │ │   │
│  │  │  • Exact phrase filtering                           │ │   │
│  │  └─────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼                                       │
│               ┌─────────────────┐                               │
│               │ Search Results  │                               │
│               │  • url          │                               │
│               │  • title        │                               │
│               │  • snippet      │                               │
│               │  • engines[]    │                               │
│               └─────────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
```

## Engine Codes (40+)

| Code | Engine | Code | Engine |
|------|--------|------|--------|
| GO | Google | BI | Bing |
| BR | Brave | DD | DuckDuckGo |
| YA | Yandex | YE | Yep |
| QW | Qwant | AR | Archive.org |
| EX | Exa | GD | GDELT |
| GR | Grok | NA | NewsAPI |
| PW | PublicWWW | SS | SocialSearcher |
| BO | BoardReader | AL | Aleph |
| HF | HuggingFace | W | WikiLeaks |
| OA | OpenAlex | GU | Gutenberg |
| CR | Crossref | OL | OpenLibrary |
| PM | PubMed | AX | Arxiv |
| SE | Searx | WP | Wikipedia |
| NT | Nitter | MU | Marginalia |
| SG | Sogou | BK | Baidu |
| AA | Academic | LG | Lingva |
| BA | BASE | JS | JavaScript |

## Public API

```python
from brute.brute import BruteSearch

# Initialize
search = BruteSearch()

# Run search (streams to disk)
results = await search.run(
    query="your search query",
    engines=["GO", "BI", "BR", "DD"],
    max_results=1000
)

# With filtering
results = await search.run(
    query='"exact phrase"',
    enable_filtering=True
)

# Resume interrupted search
results = await search.resume("search_20250106_143022")
```

## Structure

```
brute/
├── __init__.py
├── brute.py              # Main orchestrator (176K lines)
├── engines/              # 40+ engine implementations
│   ├── google.py
│   ├── bing.py
│   ├── brave.py
│   └── ...
├── filtering/            # Exact phrase filtering
│   └── core/
├── categorizer/          # AI categorization
├── infrastructure/       # Storage, checkpoints, monitoring
│   ├── result_storage.py
│   ├── checkpoint_manager.py
│   ├── progress_monitor.py
│   └── snippet_aggregator.py
├── execution/            # Cascade executor, analytics
├── adapter/              # Engine adapters
├── config/
└── tests/
```

## Features

| Feature | Description |
|---------|-------------|
| Memory streaming | Disk-based processing prevents crashes |
| Snippet aggregation | Merges snippets from multiple engines |
| Exact phrase filtering | Filters results by quoted phrases |
| Checkpoint/resume | Auto-saves progress |
| Engine analytics | Per-engine performance tracking |
| Circuit breaker | Handles engine failures gracefully |

## Dependencies

- aiohttp (async HTTP)
- SQLite (disk storage)
- psutil (memory monitoring)
