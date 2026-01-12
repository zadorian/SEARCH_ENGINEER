# PACMAN Architecture & File Reference

**Pattern And Content Analysis Module** - Entity extraction via regex patterns, AI backends, and classification.

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PACMAN ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                              ┌─────────────┐                                │
│                              │   INPUT     │                                │
│                              │ (URL/Text)  │                                │
│                              └──────┬──────┘                                │
│                                     │                                       │
│          ┌──────────────────────────┼──────────────────────────┐           │
│          ▼                          ▼                          ▼           │
│   ┌─────────────┐           ┌─────────────┐           ┌─────────────┐      │
│   │  PATTERNS   │           │ CLASSIFIERS │           │ AI BACKENDS │      │
│   │ (regex)     │           │(tier/tripwire)          │(GPT/Claude/ │      │
│   │             │           │             │           │ GLiNER)     │      │
│   └──────┬──────┘           └──────┬──────┘           └──────┬──────┘      │
│          │                         │                         │             │
│          │    ┌────────────────────┴────────────────────┐   │             │
│          └───▶│           ENTITY EXTRACTORS             │◀──┘             │
│               │  (persons, companies, identifiers)      │                 │
│               └────────────────────┬────────────────────┘                 │
│                                    │                                       │
│                                    ▼                                       │
│               ┌────────────────────────────────────────┐                  │
│               │            BATCH RUNNERS               │                  │
│               │    (tiered, blitz - high concurrency)  │                  │
│               └────────────────────┬───────────────────┘                  │
│                                    │                                       │
│                                    ▼                                       │
│               ┌────────────────────────────────────────┐                  │
│               │           ELASTICSEARCH                │                  │
│               │  (pacman-tiered, pacman-blitz indexes) │                  │
│               └────────────────────────────────────────┘                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
PACMAN/
├── __init__.py              # Module exports (Pacman, PacmanResult, extract, classify)
├── pacman_cli.py            # CLI interface
├── test_pacman.py           # Tests
│
├── config/
│   └── settings.py          # Concurrency, timeouts, ES config, paths
│
├── patterns/                # ⭐ REGEX PATTERNS (fast, free)
│   ├── __init__.py          # Exports ALL_PATTERNS
│   ├── identifiers.py       # LEI, IBAN, SWIFT, VAT, IMO, MMSI, ISIN, DUNS
│   ├── contacts.py          # EMAIL, PHONE (international formats)
│   ├── crypto.py            # BTC, ETH, LTC, XRP, XMR addresses
│   ├── company_numbers.py   # CRN patterns by jurisdiction
│   └── names.py             # Name patterns (titles, formats)
│
├── entity_extractors/       # ⭐ EXTRACTION ENGINES
│   ├── __init__.py
│   ├── fast.py              # Regex-only extraction (~5ms)
│   ├── persons.py           # Person name extraction (names-dataset)
│   └── companies.py         # Company name extraction (suffix detection)
│
├── classifiers/             # ⭐ URL/CONTENT CLASSIFICATION
│   ├── __init__.py
│   ├── tier.py              # FULL/EXTRACT/URL_ONLY/SKIP classification
│   └── tripwire.py          # Red flag detection (Aho-Corasick)
│
├── ai_backends/             # ⭐ AI EXTRACTION BACKENDS
│   ├── __init__.py
│   ├── base.py              # ExtractionBackend base class, EntityType enum
│   ├── regex.py             # Regex backend (free, ~5ms)
│   ├── gliner.py            # GLiNER NER model (free, ~100ms)
│   ├── haiku.py             # Claude Haiku (cheap, fast)
│   ├── gpt.py               # GPT-4/GPT-5 (expensive, accurate)
│   └── gemini.py            # Gemini (good value)
│
├── batch_runners/           # ⭐ HIGH-CONCURRENCY RUNNERS
│   ├── __init__.py
│   ├── base.py              # BaseRunner, RunnerResult, RunnerStatus
│   ├── tiered.py            # A→B→C→D tiered scraping
│   └── blitz.py             # Blitz mode (500+ concurrent)
│
├── link_extractors/         # LINK EXTRACTION
│   ├── __init__.py
│   └── extractor.py         # Outlink extraction
│
├── embeddings/              # EMBEDDING & SIMILARITY
│   ├── __init__.py
│   ├── domain_embedder.py   # Domain classification via embeddings
│   ├── golden_lists.py      # Reference entity lists
│   └── tripwire_embeddings.py # Red flag pattern embeddings
│
└── bridges/                 # INTEGRATIONS
    └── subject_nexus_bridge.py  # Subject/entity graph integration
```

---

## Core Components

### 1. PATTERNS (patterns/)

Fast, free regex patterns for structured data extraction.

| File | Patterns |
|------|----------|
| **identifiers.py** | LEI, IBAN, SWIFT, VAT, IMO, MMSI, ISIN, DUNS |
| **contacts.py** | EMAIL, PHONE_INTL, PHONE_US, PHONE_UK, PHONE_EU |
| **crypto.py** | BTC, BTC_BECH32, ETH, LTC, XRP, XMR |
| **company_numbers.py** | UK CRN, DE HRB, FR SIREN, etc. |
| **names.py** | Title patterns, name formats |

```python
from PACMAN.patterns import ALL_PATTERNS

# ALL_PATTERNS is a dict: {'LEI': re.compile(...), 'IBAN': re.compile(...), ...}
matches = ALL_PATTERNS['LEI'].findall(text)
```

---

### 2. ENTITY EXTRACTORS (entity_extractors/)

| Extractor | Speed | Method |
|-----------|-------|--------|
| **fast.py** | ~5ms | Pure regex, no deps |
| **persons.py** | ~50ms | names-dataset + patterns |
| **companies.py** | ~20ms | Suffix detection + patterns |

```python
from PACMAN.entity_extractors import extract_fast, extract_persons, extract_companies

entities = extract_fast(content)  # {'LEI': [...], 'EMAIL': [...]}
persons = extract_persons(content)  # [{'name': 'John Smith', 'confidence': 0.85}]
companies = extract_companies(content)  # [{'name': 'Acme Ltd', 'suffix': 'LTD'}]
```

---

### 3. CLASSIFIERS (classifiers/)

#### Tier Classifier (tier.py)
Classifies URLs/content into scraping tiers:

| Tier | Action |
|------|--------|
| **FULL** | Full scrape + extraction |
| **EXTRACT** | Entity extraction only |
| **URL_ONLY** | Store URL, no scraping |
| **SKIP** | Skip entirely |

#### Tripwire Classifier (tripwire.py)
Red flag detection using Aho-Corasick automaton:

| Category | Patterns |
|----------|----------|
| SANCTIONS | sanctions, OFAC, SDN list, embargo |
| PEP | politically exposed, government official |
| FRAUD | fraud, ponzi, securities fraud |
| MONEY_LAUNDERING | AML, suspicious transaction, structuring |
| CORRUPTION | bribery, kickback, corrupt |
| LITIGATION | lawsuit, defendant, plaintiff |

---

### 4. AI BACKENDS (ai_backends/)

| Backend | Cost | Speed | Best For |
|---------|------|-------|----------|
| **regex** | FREE | 5ms | Structured data (IDs, emails) |
| **gliner** | FREE | 100ms | General NER |
| **haiku** | /bin/zsh.001 | 500ms | Fast AI extraction |
| **gpt** | /bin/zsh.01 | 1s | Complex extraction |
| **gemini** | /bin/zsh.005 | 800ms | Good balance |

```python
from PACMAN.ai_backends import get_backend, available_backends

# Check what's available
print(available_backends())  # ['regex', 'gliner', 'haiku', ...]

# Use specific backend
backend = get_backend('regex')
entities = await backend.extract(content)
```

---

### 5. BATCH RUNNERS (batch_runners/)

#### Tiered Runner (tiered.py)
Sequential tier fallback: A → B → C → D

| Tier | Backend | Concurrency |
|------|---------|-------------|
| A | httpx | 500 |
| B | Colly | 100 |
| C | Rod | 50 |
| D | Playwright | 20 |

#### Blitz Runner (blitz.py)
Maximum throughput mode: 500+ concurrent

```python
from PACMAN.batch_runners import TieredRunner, BlitzRunner

# Tiered (careful)
runner = TieredRunner()
async for result in runner.run(urls):
    print(result.entities)

# Blitz (aggressive)
runner = BlitzRunner()
async for result in runner.run(urls, concurrent=500):
    print(result.entities)
```

---

## Configuration (config/settings.py)

```python
# Concurrency
CONCURRENT_TIER_A = 500      # httpx
CONCURRENT_TIER_B = 100      # Colly
CONCURRENT_TIER_C = 50       # Rod
CONCURRENT_BLITZ = 500       # Blitz mode

# Timeouts
TIMEOUT_TIER_A = 10
TIMEOUT_TIER_B = 20
TIMEOUT_TIER_C = 45

# Elasticsearch
ES_HOST = 'http://localhost:9200'
ES_INDEX_TIERED = 'pacman-tiered'
ES_INDEX_BLITZ = 'pacman-blitz'

# Extraction limits
MAX_CONTENT_SCAN = 100000    # chars
MAX_PERSONS = 30
MAX_COMPANIES = 20
MAX_IDENTIFIERS = 20
```

---

## CLI Usage

```bash
# Extract from URL
python pacman_cli.py extract https://example.com

# Extract from text
python pacman_cli.py extract --text John Smith is CEO of Acme Ltd

# Classify URL
python pacman_cli.py classify https://linkedin.com/in/johnsmith

# Red flag scan
python pacman_cli.py tripwire The company was sanctioned by OFAC

# Batch extraction
python pacman_cli.py batch urls.txt --concurrent 500
```

---

## Data Flow

```
Input (URL/Text)
    │
    ├─────────────────────────────────────────────┐
    ▼                                             ▼
┌─────────────┐                           ┌─────────────┐
│ CLASSIFIER  │                           │  PATTERNS   │
│ (tier.py)   │                           │  (regex)    │
└──────┬──────┘                           └──────┬──────┘
       │                                         │
       ▼                                         ▼
┌─────────────┐                           ┌─────────────┐
│   TRIPWIRE  │                           │ EXTRACTORS  │
│ (red flags) │                           │(fast/AI)    │
└──────┬──────┘                           └──────┬──────┘
       │                                         │
       └─────────────────┬───────────────────────┘
                         ▼
                ┌─────────────────┐
                │  BATCH RUNNER   │
                │ (tiered/blitz)  │
                └────────┬────────┘
                         ▼
                ┌─────────────────┐
                │  ELASTICSEARCH  │
                └─────────────────┘
```

---

## Related Modules

| Module | Relationship |
|--------|--------------|
| **JESTER** | Provides scraping (PACMAN uses JESTER for fetching) |
| **LINKLATER** | Uses PACMAN for entity extraction on linked pages |
| **TORPEDO** | Uses PACMAN patterns for company data extraction |
