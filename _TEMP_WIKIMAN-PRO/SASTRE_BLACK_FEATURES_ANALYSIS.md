# Sastre-Black Features Analysis - WIKIMAN-PRO Missing Capabilities

**Analysis Date:** 2025-10-17
**Source:** My-SASTRE-Cloud/Sastre-Black/DomainSearch/
**Files Analyzed:** related_entity.py, common_links_finder.py

---

## 🔥 Executive Summary

Sastre-Black contains **7 ADVANCED FEATURES** that WIKIMAN-PRO completely lacks. These are sophisticated link analysis and entity extraction capabilities that would significantly enhance investigative research.

---

## 📁 Files Analyzed

### 1. **related_entity.py**
Entity-based domain discovery using NER + combination search

### 2. **common_links_finder.py**
Advanced Ahrefs link pattern analysis (1,389 lines!)

---

## 🆕 NEW Features Not in WIKIMAN-PRO

### **Feature 1: Entity Combination Search** 🔥🔥🔥
**Source:** `related_entity.py`

**What it does:**
- Extracts entities (people, companies) from a domain
- Generates SMART COMBINATION QUERIES:
  - 5-person combinations (weight: 5)
  - 3-person combinations (weight: 3)
  - 2-person combinations (weight: 2)
- Searches across Google, Bing, Brave simultaneously
- Scores URLs by combination weight
- Returns top 50 URLs with highest entity co-occurrence

**Impact:** REVOLUTIONARY - Discovers hidden relationships through entity combinations

**Example:**
```python
# Extract entities from aboitiz.com
entities = ['Jon Ramon Aboitiz', 'Erramon Aboitiz', 'Sabin Aboitiz']

# Generate combinations:
# 5-person: "Jon Ramon Aboitiz" AND "Erramon Aboitiz" AND ... site:aboitiz.com
# 3-person: "Jon Ramon Aboitiz" AND "Erramon Aboitiz" AND "Sabin Aboitiz" site:aboitiz.com
# Scores URLs: 5 points for 5-person match, 3 for 3-person, 2 for 2-person
```

**WIKIMAN-PRO Status:** ❌ COMPLETELY MISSING

---

### **Feature 2: Similar Backlink Profile Discovery** 🔥🔥
**Source:** `common_links_finder.py` (line 265)

**What it does:**
- Finds domains with SIMILAR backlink profiles
- Identifies potential competitors or related sites
- Steps:
  1. Get all domains linking to target
  2. For each referring domain, find what ELSE they link to
  3. Find domains with minimum shared referrers (default: 3)
  4. Sort by number of shared backlinks

**Impact:** HIGH - Competitor and related site discovery

**Example:**
```bash
python common_links_finder.py aboitiz.com --similar --min-shared 5
# Finds domains that share 5+ backlink sources with aboitiz.com
```

**WIKIMAN-PRO Status:** ❌ MISSING

---

### **Feature 3: Co-Linked Domain Discovery** 🔥🔥
**Source:** `common_links_finder.py` (line 329)

**What it does:**
- Finds domains frequently linked ALONGSIDE target domain
- Reveals "guilt by association" patterns
- Process:
  1. Get domains linking to target
  2. For each referring domain, get its outbound links
  3. Find domains most commonly linked together with target

**Impact:** HIGH - Network mapping and relationship discovery

**Example:**
```bash
python common_links_finder.py aboitiz.com --colinked
# Shows: Sites that link to aboitiz.com also link to: [list]
```

**WIKIMAN-PRO Status:** ❌ MISSING

---

### **Feature 4: Backlinks Twice Removed** 🔥🔥
**Source:** `common_links_finder.py` (line 382)

**What it does:**
- Finds domains that link to YOUR backlinks
- 2-degree backlink analysis
- Reveals ecosystem around your backlink sources
- Path tracking: domain → first_level → target

**Impact:** MEDIUM-HIGH - Extended network discovery

**Example:**
```bash
python common_links_finder.py aboitiz.com --twice-removed
# Finds: Domain X → links to → Domain Y → links to → aboitiz.com
```

**WIKIMAN-PRO Status:** ❌ MISSING

---

### **Feature 5: Domain Comparison (Common Backlinks + Outlinks)** 🔥🔥🔥
**Source:** `common_links_finder.py` (line 436)

**What it does:**
- Compare MULTIPLE domains simultaneously
- Find common backlinks (domains linking to all targets)
- Find common outlinks (domains all targets link to)
- Backlist filtering for SEO spam
- Authority scoring based on outlink count

**Impact:** VERY HIGH - Network analysis and PBN detection

**Example:**
```bash
python common_links_finder.py domain1.com domain2.com domain3.com --compare
# Output:
# COMMON BACKLINKS: [domains linking to all 3]
# COMMON OUTLINKS: [domains all 3 link to]
```

**Features:**
- Explicit backlist (rankva.com, linkbox.agency, etc.)
- Filter circular references
- Authority stars (★★★★★☆☆☆☆☆)
- Outlink count analysis

**WIKIMAN-PRO Status:** ❌ COMPLETELY MISSING

---

### **Feature 6: Anchor Text Search with Context** 🔥🔥
**Source:** `common_links_finder.py` (line 730, 824, 981)

**What it does:**
- Multiple anchor text analysis modes:
  1. `get_backlinks_with_anchors()` - Anchors with context
  2. `analyze_anchors()` - Dedicated anchor endpoint
  3. `search_anchor_texts()` - Multi-domain anchor search
- Features:
  - Anchor text + surrounding context (text_pre, text_post)
  - Nofollow flag detection
  - First seen dates
  - Grouped by referring domain
  - Search term filtering

**Impact:** HIGH - Advanced SEO and link analysis

**Example:**
```bash
python common_links_finder.py aboitiz.com --anchors --anchor-term "energy"
# Finds all backlinks with "energy" in anchor text + context
```

**Special Syntax:**
```bash
python common_links_finder.py sastreconsulting.com?
# Auto-detects "sastre" as search term from domain
```

**WIKIMAN-PRO Status:** ⚠️ PARTIAL - Has basic anchor analysis, lacks context extraction

---

### **Feature 7: Authority Scoring by Outlink Count** 🔥
**Source:** `common_links_finder.py` (line 552, 604)

**What it does:**
- Calculates domain authority based on OUTLINK count
- **Principle:** Fewer outlinks = Higher authority
- Generates 1-10 star rating (★★★★★☆☆☆☆☆)
- Formula: `authority_score = min(10, max(1, 10 - int(outlink_count / 100)))`

**Impact:** MEDIUM - Quality filtering for backlinks

**Display:**
```
Domain                          Count  Authority   Outlinks   Details
----------------------------------------------------------------------------
authoritysite.com               5      ★★★★★★★★☆☆  245       domain1, domain2, ...
spamsite.com                    3      ★☆☆☆☆☆☆☆☆☆  8,542     domain3, domain4, ...
```

**WIKIMAN-PRO Status:** ❌ MISSING

---

## 📊 Complete Feature Comparison

| Feature | WIKIMAN-PRO | Sastre-Black | Priority |
|---------|-------------|--------------|----------|
| **Entity Combination Search** | ❌ | ✅ | 🔥🔥🔥 CRITICAL |
| **Similar Backlink Profiles** | ❌ | ✅ | 🔥🔥 HIGH |
| **Co-Linked Domains** | ❌ | ✅ | 🔥🔥 HIGH |
| **Backlinks Twice Removed** | ❌ | ✅ | 🔥 MEDIUM |
| **Multi-Domain Comparison** | ❌ | ✅ | 🔥🔥🔥 CRITICAL |
| **Anchor Text + Context** | ⚠️ Basic | ✅ Advanced | 🔥🔥 HIGH |
| **Authority by Outlinks** | ❌ | ✅ | 🔥 MEDIUM |
| **Weighted Entity Scoring** | ❌ | ✅ | 🔥🔥 HIGH |
| **SEO Spam Backlist** | ✅ InvestigatorSEO | ✅ Explicit list | ✅ Both have |
| **Multi-Engine Search** | ❌ | ✅ Google+Bing+Brave | 🔥🔥 HIGH |
| **NER Integration** | ❌ | ✅ Azure Text Analytics | 🔥🔥🔥 CRITICAL |

---

## 🏗️ Integration Strategy

### **Phase 1: Entity-Based Discovery (HIGHEST PRIORITY)**
**Timeline:** 1-2 weeks

Add to WIKIMAN-PRO:
```
RELATED/
├── entity_discovery.py    # NEW: Entity combination search
├── ner_integration.py     # NEW: Azure NER or spaCy
└── multi_engine.py        # NEW: Google+Bing+Brave search
```

**Key Functions to Port:**
```python
# From related_entity.py:
- extract_entities_from_url() → NER extraction
- search_entity_combinations() → Weighted combination search
- Entity scoring: 5-person (weight=5), 3-person (weight=3), 2-person (weight=2)
```

---

### **Phase 2: Advanced Link Analysis (HIGH PRIORITY)**
**Timeline:** 2 weeks

Add to WIKIMAN-PRO:
```
RELATED/
├── backlinks.py              # ENHANCE: Add similarity analysis
├── link_comparison.py        # NEW: Multi-domain comparison
└── network_analysis.py       # NEW: Co-linked + twice-removed
```

**Key Functions to Port:**
```python
# From common_links_finder.py:
- find_similar_backlink_profiles() → Competitor discovery
- find_colinked_domains() → Association mapping
- find_backlinks_twice_removed() → Extended network
- compare_domains() → Multi-domain analysis
```

---

### **Phase 3: Enhanced Anchor Analysis (MEDIUM PRIORITY)**
**Timeline:** 1 week

**Enhance existing RELATED/backlinks.py:**
```python
# Add context extraction:
- get_backlinks_with_anchors() → Full context
- text_pre + anchor + text_post
- Nofollow detection
- First seen tracking
```

---

### **Phase 4: Authority Metrics (LOW PRIORITY)**
**Timeline:** 3 days

**Add to RELATED/analytics.py:**
```python
- get_domain_outlink_count() → Authority metric
- calculate_authority_score() → Star rating
- display_with_authority() → Enhanced output
```

---

## 💡 Implementation Examples

### **Example 1: Entity Combination Search**
```python
# New module: RELATED/entity_discovery.py

from related_entity import search_entity_combinations
from ner_integration import extract_entities

async def discover_related_urls(domain: str):
    # Extract entities
    entities = await extract_entities(domain)

    # Generate weighted combinations
    urls = await search_entity_combinations(entities, domain)

    # urls are pre-scored: 5-person combos = highest score
    return sorted(urls, key=lambda x: x['score'], reverse=True)
```

### **Example 2: Multi-Domain Comparison**
```python
# New module: RELATED/link_comparison.py

from common_links_finder import compare_domains

def compare_competitors(domains: List[str]):
    results = compare_domains(
        domains,
        max_links=100,
        filter_seo_spam=True
    )

    return {
        'common_backlinks': results['common_backlinks'],  # PBN detection
        'common_outlinks': results['common_outlinks']     # Relationship mapping
    }
```

### **Example 3: Similar Profile Discovery**
```python
# Enhance RELATED/backlinks.py

from common_links_finder import find_similar_backlink_profiles

async def find_competitors(target: str):
    similar = find_similar_backlink_profiles(
        target,
        min_shared=5,  # Require 5+ shared backlinks
        max_links=100,
        max_backlinks=20
    )

    return similar  # Sorted by shared backlink count
```

---

## 🎯 Quick Win Recommendations

### **Immediate Actions (This Week):**

1. **Port Entity Combination Search** ✅ CRITICAL
   - Copy NER extraction logic
   - Implement weighted combination queries
   - Integrate with existing search engines
   - **ROI:** Massive - unique discovery capability

2. **Add Multi-Domain Comparison** ✅ CRITICAL
   - Port `compare_domains()` function
   - Implement backlist filtering
   - Add to RELATED module
   - **ROI:** High - PBN detection + network analysis

3. **Implement Similar Profiles** ✅ HIGH
   - Port `find_similar_backlink_profiles()`
   - Add competitor discovery feature
   - **ROI:** High - competitive intelligence

### **Next Steps (Next 2 Weeks):**

4. **Co-Linked Domains** ✅ HIGH
5. **Backlinks Twice Removed** ✅ MEDIUM
6. **Enhanced Anchor Context** ✅ HIGH
7. **Authority Scoring** ✅ LOW

---

## 🔍 Code Quality Analysis

### **Sastre-Black Strengths:**
✅ **Comprehensive error handling** - API failover, fallback endpoints
✅ **Rate limiting** - 2-second delays between requests
✅ **Modular design** - Separate functions for each analysis type
✅ **CLI interface** - argparse with multiple modes
✅ **Authority metrics** - Outlink-based quality scoring
✅ **Backlist system** - Explicit SEO spam filtering

### **Integration Considerations:**
⚠️ **Hardcoded API keys** - Need to move to env vars
⚠️ **Synchronous code** - Convert to async for WIKIMAN-PRO
⚠️ **Azure NER dependency** - Consider spaCy alternative
✅ **Ahrefs API** - Already used in WIKIMAN-PRO

---

## 📈 Expected Benefits

### **For Investigative Research:**
- 🧠 **Entity-based discovery** - Find relationships through name combinations
- 🔍 **Network mapping** - Visualize domain ecosystems
- 🎯 **Competitor identification** - Similar backlink profiles
- 📊 **Authority filtering** - Quality-based link selection

### **For Corporate Intelligence:**
- 🏢 **Company relationship mapping** - Co-linked domains reveal partnerships
- 💼 **Executive network discovery** - Entity combinations find connections
- 🕵️ **PBN detection** - Multi-domain comparison reveals link schemes
- 📈 **Competitive analysis** - Similar profile discovery

### **For Link Analysis:**
- 🔗 **Extended backlink discovery** - 2-degree separation analysis
- ⚓ **Anchor context extraction** - Full text surrounding links
- ⭐ **Authority metrics** - Quality scoring for backlinks
- 🚫 **Spam filtering** - Backlist + behavioral detection

---

## 🚨 Critical Findings

### **Most Valuable Features (Implement First):**

1. **Entity Combination Search** 🔥🔥🔥
   - **Uniqueness:** Not available anywhere else
   - **Impact:** Revolutionary for relationship discovery
   - **Complexity:** Medium (2 weeks)

2. **Multi-Domain Comparison** 🔥🔥🔥
   - **Uniqueness:** Rare capability
   - **Impact:** PBN detection + network analysis
   - **Complexity:** Low (1 week)

3. **Similar Backlink Profiles** 🔥🔥
   - **Uniqueness:** Available in commercial tools only
   - **Impact:** Competitor discovery
   - **Complexity:** Medium (1 week)

### **Dependencies to Address:**
❌ **Azure Text Analytics** - Need API key or switch to spaCy
✅ **Ahrefs API** - Already integrated
✅ **Google/Bing/Brave Search** - Can use existing engines

---

## 💰 Resource Requirements

### **Development Time:**
- **Phase 1 (Entity Discovery):** 1-2 weeks (1 dev)
- **Phase 2 (Link Analysis):** 2 weeks (1 dev)
- **Phase 3 (Anchor Context):** 1 week (1 dev)
- **Phase 4 (Authority):** 3 days (1 dev)

**Total:** 4-5 weeks

### **API Costs:**
- Ahrefs API: Already integrated ✅
- Azure NER: ~$1/1000 requests OR spaCy (free)
- Google/Bing/Brave: Existing integration ✅

---

## 📝 Conclusion

Sastre-Black reveals **7 CRITICAL GAPS** in WIKIMAN-PRO's link analysis capabilities:

**HIGHEST PRIORITY:**
1. ✅ Entity Combination Search (game-changer)
2. ✅ Multi-Domain Comparison (PBN detection)
3. ✅ Similar Backlink Profiles (competitor discovery)

**HIGH PRIORITY:**
4. ✅ Co-Linked Domains (relationship mapping)
5. ✅ Enhanced Anchor Context (SEO analysis)

**MEDIUM PRIORITY:**
6. ✅ Backlinks Twice Removed (extended network)
7. ✅ Authority Scoring (quality metrics)

**Recommendation:** Implement features 1-3 IMMEDIATELY (3-4 weeks) for transformative investigative capabilities. These features are not available in ANY other tool and would give WIKIMAN-PRO a unique competitive advantage.

---

## 🔗 Integration Checklist

### **Entity Discovery Module:**
- [ ] Extract entity extraction logic from related_entity.py
- [ ] Integrate NER (Azure or spaCy)
- [ ] Implement weighted combination search (5/3/2 scoring)
- [ ] Add multi-engine search support
- [ ] Create entity_discovery.py module

### **Link Comparison Module:**
- [ ] Port compare_domains() function
- [ ] Implement backlist filtering
- [ ] Add authority scoring
- [ ] Create link_comparison.py module

### **Network Analysis Module:**
- [ ] Port find_similar_backlink_profiles()
- [ ] Port find_colinked_domains()
- [ ] Port find_backlinks_twice_removed()
- [ ] Create network_analysis.py module

### **Anchor Enhancement:**
- [ ] Add context extraction (text_pre/text_post)
- [ ] Add nofollow detection
- [ ] Add first seen tracking
- [ ] Enhance existing backlinks.py

### **Testing & Integration:**
- [ ] Convert sync code to async
- [ ] Add WebSocket support for streaming
- [ ] Integrate with DrillSearch operators
- [ ] Add to unified related.py orchestrator

---

**Next Step:** Start with Entity Combination Search implementation for immediate high-impact results.
