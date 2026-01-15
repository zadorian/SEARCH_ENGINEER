# Filtering

## Location in Project Hierarchy

```
Search_Engineer/
├── 🔧 Filtering/ ← YOU ARE HERE (27 files)
│   ├── filters/
│   │   ├── relevance_filter.py
│   │   ├── quality_filter.py
│   │   └── (6 more filters...)
│   ├── ranking/
│   ├── integration/
│   ├── dates/
│   └── core/
```

**Purpose:**  
Comprehensive filtering infrastructure for result quality, relevance, geographic, temporal, and exact phrase matching.

**Key Components:**

- `filters/` - Individual filter implementations
- `ranking/` - Result ranking algorithms
- `integration/` - Integration modules
- `dates/` - Enhanced date extraction
- `core/` - Core filtering infrastructure
- `config/` - Filter configuration

**Key Files:**

- `filters/relevance_filter.py` - Relevance scoring
- `filters/quality_filter.py` - Quality assessment
- `filters/geographic_filter.py` - Location-based filtering
- `filters/temporal_filter.py` - Time-based filtering
- `filters/exact_phrase_filter.py` - Exact phrase matching
- `ranking/hybrid_ranker.py` - Combined ranking approach
- `ranking/scoring_engine.py` - Score calculation

**Consumers & Dependencies:**

- **↑ Imported by:** `Search_Types/brute.py` (filtering pipeline)
- **↑ Imported by:** All search type handlers for result filtering
- **↓ Dependencies:** `ScrapeR/phrase_matcher.py`

**Example Imports:**

```python
from Filtering.filters.relevance_filter import RelevanceFilter
from Filtering.ranking.hybrid_ranker import HybridRanker
from Filtering.dates.date_extractor_enhanced import extract_date_info
```
