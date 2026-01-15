# Complete Filtering Guide: All Available Filters

**Date**: 2025-10-17
**Feature**: Comprehensive multi-dimensional filtering for backlink search

---

## 📊 Overview

Your link sets system now supports **11 types of filters** that can be combined for powerful, targeted searches:

### Filter Categories

1. **🏷️ Category Filters** - Content type (news, tech, business, etc.)
2. **🌍 Geographic Filters** - Country/region-based
3. **🏛️ Institutional Filters** - Government, academic, military sites
4. **📈 Authority Filters** - Domain rank and backlink authority
5. **⭐ Quality Filters** - Relevance score and SEO value
6. **🔗 Link Type Filters** - DoFollow/NoFollow status
7. **🔤 Content Filters** - Anchor text keywords
8. **🔗 URL Pattern Filters** - Source and target URL patterns
9. **🎯 Source Filters** - Specific TLDs or domains
10. **📊 Limit Filters** - Result count and pagination
11. **🔍 Combination Filters** - Multiple filters at once

---

## 🏷️ Category Filtering

### Available Categories (16 types)

View all categories:

```bash
python search_link_sets.py --list-categories
```

**Categories:**

- 📰 **news** - News & Media sites
- 💼 **business** - Business & Corporate
- 💻 **technology** - Technology & Software
- 🎓 **education** - Education & Academic
- 🛒 **shopping** - Shopping & E-commerce
- 🎬 **entertainment** - Entertainment & Movies
- 🏥 **health** - Health & Medical
- ✈️ **travel** - Travel & Tourism
- 💰 **finance** - Finance & Banking
- ⚽ **sports** - Sports
- 🍕 **food_drink** - Food & Drink
- 🎨 **arts** - Arts & Culture
- 🎮 **games** - Games
- 📚 **reference** - Reference & Information
- 🔬 **science** - Science & Research
- 🖥️ **computers_electronics** - Computers & Electronics

### Usage Examples

```bash
# News sites linking to target
python search_link_sets.py tier1 --domain=target.com --category=news

# Technology sites only
python search_link_sets.py tier1 --domain=software.com --category=technology

# Education sites only
python search_link_sets.py tier1 --domain=research.com --category=education

# Business sites only
python search_link_sets.py tier1 --domain=startup.com --category=business
```

### Enrichment Required

**Important**: Category filtering requires running enrichment first:

```bash
# Step 1: Categorize Majestic Million (if not done)
cd ../Search-Engineer.02/iv. LOCATION/a. KNOWN_UNKNOWN/authority/
python categorize_majestic_million.py

# Step 2: Enrich your link set
cd /path/to/WIKIMAN-PRO/LINKDATA
python enrich_with_categories.py tier1 CC-MAIN-2024-10
```

---

## 🌍 Geographic Filtering

60+ countries supported. See [COUNTRY_FILTERING_GUIDE.md](COUNTRY_FILTERING_GUIDE.md) for details.

```bash
# UK sites
python search_link_sets.py tier1 --domain=target.com --country=uk

# German sites
python search_link_sets.py tier1 --domain=target.com --country=de

# Government sites worldwide
python search_link_sets.py tier1 --domain=target.com --country=gov

# Education sites worldwide
python search_link_sets.py tier1 --domain=target.com --country=edu
```

---

## 📈 Authority Filtering

### Max Rank Filter

Filter by **Majestic Million global rank** (1-1,000,000):

```bash
# Top 1,000 sites only
python search_link_sets.py tier1 --domain=target.com --max-rank=1000

# Top 10,000 sites only
python search_link_sets.py tier1 --domain=target.com --max-rank=10000

# Top 100,000 sites only
python search_link_sets.py tier1 --domain=target.com --max-rank=100000
```

**Use cases**:

- Filter for high-authority backlinks only
- Exclude long-tail sites
- Focus on mainstream media

### Min Authority Filter

Filter by **referring subnets** (backlink authority):

```bash
# High authority sites (10,000+ referring subnets)
python search_link_sets.py tier1 --domain=target.com --min-authority=10000

# Medium authority (1,000+ referring subnets)
python search_link_sets.py tier1 --domain=target.com --min-authority=1000

# Very high authority (50,000+ referring subnets)
python search_link_sets.py tier1 --domain=target.com --min-authority=50000
```

**Use cases**:

- Find backlinks from highly-linked sites
- Identify influential sources
- SEO link building (high DA/PA sites)

---

## ⭐ Quality Filtering

### Min Score Filter

Filter by **relevance score** (0-100):

```bash
# High quality only (score ≥ 60)
python search_link_sets.py tier1 --domain=target.com --min-score=60

# Very high quality (score ≥ 70)
python search_link_sets.py tier1 --domain=target.com --min-score=70

# Medium quality+ (score ≥ 50)
python search_link_sets.py tier1 --domain=target.com --min-score=50
```

**Relevance score factors**:

- Base score: 10
- Anchor text length: +5/+5
- DoFollow status: +20
- Root domain: +15
- Keyword matches: +10 each

---

## 🔗 Link Type Filtering

### DoFollow Only Filter

Exclude NoFollow links (show only SEO-valuable links):

```bash
# DoFollow links only
python search_link_sets.py tier1 --domain=target.com --dofollow-only

# DoFollow + high quality
python search_link_sets.py tier1 --domain=target.com --dofollow-only --min-score=60
```

**Use cases**:

- SEO link building
- PageRank flow analysis
- Exclude sponsored/NoFollow links

---

## 🔤 Content Filtering

### Anchor Text Keywords

Filter by anchor text keywords (comma-separated):

```bash
# Security-related backlinks
python search_link_sets.py tier1 --domain=target.com --anchor-keywords="security,privacy"

# Research-related
python search_link_sets.py tier1 --domain=target.com --anchor-keywords="research,study,paper"

# Product-related
python search_link_sets.py tier1 --domain=target.com --anchor-keywords="tool,software,platform"
```

**Use cases**:

- Find contextually relevant backlinks
- Identify brand mentions
- Discover topic-specific citations

---

## 🔗 URL Pattern Filtering

### Target URL Contains

Filter by patterns in **target URLs** (where links point TO):

```bash
# Links pointing to blog posts
python search_link_sets.py tier1 --domain=target.com --target-url-contains="/blog/"

# Links to research papers
python search_link_sets.py tier1 --domain=target.com --target-url-contains="/research/"

# Links to PDF documents
python search_link_sets.py tier1 --domain=target.com --target-url-contains=".pdf"

# Links to product pages (multiple patterns)
python search_link_sets.py tier1 --domain=target.com --target-url-contains="/product/,/shop/"
```

### Source URL Contains

Filter by patterns in **source URLs** (where links come FROM):

```bash
# Links from blog posts
python search_link_sets.py tier1 --domain=target.com --source-url-contains="/blog/"

# Links from press releases
python search_link_sets.py tier1 --domain=target.com --source-url-contains="/press/,/news/"

# Links from research pages
python search_link_sets.py tier1 --domain=target.com --source-url-contains="/research/,/publication/"

# Links from article pages
python search_link_sets.py tier1 --domain=target.com --source-url-contains="/article/,/story/"
```

### Combined URL Filtering

Filter both source AND target URLs:

```bash
# Blog posts linking to research pages
python search_link_sets.py tier1 \
  --domain=target.com \
  --source-url-contains="/blog/" \
  --target-url-contains="/research/"

# Press releases linking to product pages
python search_link_sets.py tier1 \
  --domain=target.com \
  --source-url-contains="/press/" \
  --target-url-contains="/product/"

# Academic citations (edu blog → research paper)
python search_link_sets.py tier1 \
  --domain=research.edu \
  --source-url-contains="/blog/,/news/" \
  --target-url-contains="/paper/,.pdf"
```

**Use cases**:

- Find links from specific page types (blogs, press, etc.)
- Target specific URL structures
- Identify document backlinks (.pdf, .doc, etc.)
- Filter out homepage-to-homepage links
- Track content-specific citations

**Pattern matching**:

- Case-insensitive regex matching
- Comma-separated = OR logic (matches ANY pattern)
- Supports partial URLs, file extensions, URL parameters
- Examples: `/blog/`, `.pdf`, `/category/`, `?id=`, `/2024/`

---

## 🎯 Source Filtering

### Direct TLD Filter

Filter by specific TLD (alternative to country):

```bash
# .edu sites only
python search_link_sets.py tier1 --domain=target.com --source-tld=.edu

# .gov sites only
python search_link_sets.py tier1 --domain=target.com --source-tld=.gov

# .org sites only
python search_link_sets.py tier1 --domain=target.com --source-tld=.org
```

**Use cases**:

- More precise than country filters
- Target specific TLDs not covered by country codes

---

## 🔥 Powerful Filter Combinations

### Example 1: High-Quality News Sites

```bash
python search_link_sets.py tier1 \
  --domain=target.com \
  --category=news \
  --max-rank=10000 \
  --min-score=60 \
  --dofollow-only
```

**Finds**: Top 10K news sites with high-quality DoFollow backlinks

---

### Example 2: UK Education Sites

```bash
python search_link_sets.py tier1 \
  --domain=target.com \
  --country=uk \
  --category=education \
  --min-score=50
```

**Finds**: UK universities/schools linking to target with good relevance

---

### Example 3: Authoritative Technology Press

```bash
python search_link_sets.py tier1 \
  --domain=startup.com \
  --category=technology \
  --max-rank=5000 \
  --min-authority=10000 \
  --anchor-keywords="innovation,startup,launch"
```

**Finds**: Top 5K tech sites with high authority mentioning innovation/startup

---

### Example 4: Government Research Citations

```bash
python search_link_sets.py tier1 \
  --domain=research-lab.edu \
  --country=gov \
  --anchor-keywords="research,study,report" \
  --min-score=60
```

**Finds**: Government sites citing research with relevant anchor text

---

### Example 5: German Business Press

```bash
python search_link_sets.py tier1 \
  --domain=company.com \
  --country=de \
  --category=business \
  --max-rank=20000 \
  --dofollow-only
```

**Finds**: Top 20K German business sites with DoFollow links

---

## 📊 Complete Filter Reference

| Filter                  | Flag                    | Type    | Example                           | Use Case                     |
| ----------------------- | ----------------------- | ------- | --------------------------------- | ---------------------------- |
| **Category**            | `--category`            | String  | `--category=news`                 | Content type filtering       |
| **Site Type**           | `--site-type`           | String  | `--site-type=government`          | Institutional filtering      |
| **Country**             | `--country`             | String  | `--country=uk`                    | Geographic filtering         |
| **Source TLD**          | `--source-tld`          | String  | `--source-tld=.edu`               | Precise TLD filtering        |
| **Min Score**           | `--min-score`           | Integer | `--min-score=60`                  | Quality threshold            |
| **Max Rank**            | `--max-rank`            | Integer | `--max-rank=10000`                | Authority filter (rank)      |
| **Min Authority**       | `--min-authority`       | Integer | `--min-authority=5000`            | Authority filter (subnets)   |
| **DoFollow Only**       | `--dofollow-only`       | Flag    | `--dofollow-only`                 | SEO-valuable links           |
| **Anchor Keywords**     | `--anchor-keywords`     | String  | `--anchor-keywords="word1,word2"` | Content relevance            |
| **Target URL Contains** | `--target-url-contains` | String  | `--target-url-contains="/blog/"`  | Filter by target URL pattern |
| **Source URL Contains** | `--source-url-contains` | String  | `--source-url-contains="/press/"` | Filter by source URL pattern |
| **Limit**               | `--limit`               | Integer | `--limit=500`                     | Result count                 |
| **Archive**             | `--archive`             | String  | `--archive=CC-MAIN-2024-10`       | Specific crawl               |

---

## 🎯 Filter Decision Tree

```
START: What are you looking for?

├─ News coverage?
│  └─ Use: --category=news --max-rank=10000
│
├─ Academic citations?
│  └─ Use: --country=edu --category=education --min-score=60
│
├─ Government links?
│  └─ Use: --country=gov --min-score=50
│
├─ High-authority backlinks?
│  └─ Use: --max-rank=5000 --min-authority=10000 --dofollow-only
│
├─ Country-specific press?
│  └─ Use: --country=XX --category=news --max-rank=20000
│
├─ SEO link building?
│  └─ Use: --dofollow-only --min-score=60 --max-rank=50000
│
├─ Brand mentions?
│  └─ Use: --anchor-keywords="brand,product" --min-score=40
│
└─ Topical relevance?
   └─ Use: --category=XXX --anchor-keywords="keywords" --min-score=50
```

---

## 📋 Workflow Examples

### OSINT Investigation Workflow

```bash
# Step 1: Find all backlinks
python search_link_sets.py tier1 --domain=target.com --limit=1000 --output=all.csv

# Step 2: Filter for news sites
python search_link_sets.py tier1 --domain=target.com --category=news --output=news.csv

# Step 3: Filter by country
python search_link_sets.py tier1 --domain=target.com --country=ru --output=russia.csv

# Step 4: High-authority sites
python search_link_sets.py tier1 --domain=target.com --max-rank=10000 --output=authority.csv

# Step 5: Analyze results
# Compare news.csv vs russia.csv vs authority.csv
```

---

### SEO Audit Workflow

```bash
# Step 1: All DoFollow backlinks
python search_link_sets.py tier1 --domain=mysite.com --dofollow-only --output=dofollow.csv

# Step 2: High-quality DoFollow
python search_link_sets.py tier1 --domain=mysite.com --dofollow-only --min-score=60 --output=quality.csv

# Step 3: Authority sites only
python search_link_sets.py tier1 --domain=mysite.com --max-rank=50000 --dofollow-only --output=authority_dofollow.csv

# Step 4: Calculate metrics
# Total DoFollow vs Quality DoFollow vs Authority DoFollow
```

---

### Competitor Analysis Workflow

```bash
# Step 1: All competitor backlinks
python search_link_sets.py tier1 --domain=competitor.com --output=competitor_all.json

# Step 2: News coverage
python search_link_sets.py tier1 --domain=competitor.com --category=news --max-rank=20000 --output=competitor_press.csv

# Step 3: Tech coverage
python search_link_sets.py tier1 --domain=competitor.com --category=technology --output=competitor_tech.csv

# Step 4: Identify gaps
# Find sites linking to competitor but not to you
```

---

## 🚀 Advanced Queries

### Query 1: Investigative Journalism

**Goal**: Find investigative news sites mentioning target

```bash
python search_link_sets.py tier1 \
  --domain=target.com \
  --category=news \
  --anchor-keywords="investigation,report,expose,scandal" \
  --min-score=60 \
  --format=json \
  --output=investigative_coverage.json
```

---

### Query 2: Academic Research Network

**Goal**: Map academic citations across countries

```bash
# US universities
python search_link_sets.py tier1 --domain=research.com --country=us --category=education --output=us_edu.csv

# UK universities
python search_link_sets.py tier1 --domain=research.com --country=uk --category=education --output=uk_edu.csv

# EU universities
for country in de fr it es nl; do
  python search_link_sets.py tier1 --domain=research.com --country=$country --category=education --output=${country}_edu.csv
done
```

---

### Query 3: High-Authority Tech Press

**Goal**: Find top tech publications

```bash
python search_link_sets.py tier1 \
  --domain=startup.com \
  --category=technology \
  --max-rank=3000 \
  --min-authority=15000 \
  --anchor-keywords="launch,startup,funding,innovation" \
  --dofollow-only \
  --limit=200 \
  --format=csv \
  --output=tech_press_coverage.csv
```

---

### Query 4: Government Cybersecurity Links

**Goal**: Find government cybersecurity agencies linking to target

```bash
python search_link_sets.py tier1 \
  --domain=security-firm.com \
  --country=gov \
  --anchor-keywords="security,cyber,threat,vulnerability" \
  --min-score=60 \
  --format=json \
  --output=gov_cyber_links.json
```

---

## 📊 Performance Tips

### 1. Start Broad, Then Narrow

```bash
# Bad: Too many filters at once (might return 0 results)
python search_link_sets.py tier1 --domain=target.com --category=news --country=uk --max-rank=1000 --min-score=80

# Good: Start broad
python search_link_sets.py tier1 --domain=target.com --category=news

# Then add filters incrementally
python search_link_sets.py tier1 --domain=target.com --category=news --country=uk
```

---

### 2. Use Category + Country Combinations

```bash
# Very effective combinations:
--category=news --country=us        # US news sites
--category=education --country=uk   # UK universities
--category=technology --max-rank=10000  # Top tech sites
--category=business --country=de    # German business sites
```

---

### 3. Authority Filters for Quality

```bash
# Instead of just min-score, use authority metrics:
--max-rank=10000 --min-authority=5000 --min-score=50

# This finds: Top 10K sites + high authority + decent relevance
```

---

## 🎓 Filter Best Practices

### DO ✅

1. **Combine complementary filters**:

   ```bash
   --category=news --max-rank=5000 --dofollow-only
   ```

2. **Use anchor keywords for context**:

   ```bash
   --category=technology --anchor-keywords="AI,machine learning"
   ```

3. **Export filtered results for analysis**:
   ```bash
   --format=csv --output=filtered_results.csv
   ```

### DON'T ❌

1. **Don't over-filter initially**:

   ```bash
   # Too restrictive - might return zero results
   --category=news --country=uk --max-rank=100 --min-score=90
   ```

2. **Don't ignore DoFollow for SEO**:

   ```bash
   # For link building, always use:
   --dofollow-only
   ```

3. **Don't forget to check category availability**:
   ```bash
   # First check: --list-categories
   # Then filter:  --category=news
   ```

---

## 🔄 Maintenance & Updates

### Keep Category Data Fresh

```bash
# Monthly: Recategorize Majestic Million
cd ../Search-Engineer.02/iv. LOCATION/a. KNOWN_UNKNOWN/authority/
python categorize_majestic_million.py

# Re-enrich link sets
cd /path/to/WIKIMAN-PRO/LINKDATA
python enrich_with_categories.py tier1 CC-MAIN-2024-10
```

---

## 📝 Summary

**Available Filters**: 11 types
**Categories**: 16 content types
**Countries**: 60+ supported
**Institutional Types**: 3 (government, academic, military)
**Combinations**: Unlimited

**Most Powerful Combinations**:

1. Category + Country + Authority
2. Category + Max Rank + DoFollow
3. Country + Anchor Keywords + Min Score
4. Category + Min Authority + Anchor Keywords
5. Site Type + URL Pattern + Category
6. Source URL + Target URL + Anchor Keywords

**Next Steps**:

1. ✅ Run enrichment: `python enrich_with_categories.py tier1 CC-MAIN-2024-10`
2. ✅ List options: `python search_link_sets.py --list-categories --list-site-types`
3. ✅ Try filtering: `python search_link_sets.py tier1 --domain=example.com --category=news`
4. ✅ Try URL patterns: `python search_link_sets.py tier1 --domain=example.com --source-url-contains="/blog/"`
5. ✅ Combine filters for powerful queries!

---

**Generated**: 2025-10-17
**Version**: 2.0
**Status**: Production-ready with enrichment + URL pattern filtering
