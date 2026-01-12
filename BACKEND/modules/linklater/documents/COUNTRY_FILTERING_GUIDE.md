# Country Filtering Guide for Link Sets

**Date**: 2025-10-17
**Feature**: Geographic backlink analysis with country-based filtering

---

## 🌍 Overview

The link sets search system now supports **country-based filtering**, allowing you to find backlinks from specific countries instantly. This is essential for:

- **OSINT investigations**: Find which countries link to a target
- **Media analysis**: Identify international press coverage
- **Geopolitical research**: Map cross-border relationships
- **Compliance**: Find jurisdiction-specific backlinks
- **Threat intelligence**: Track activity from specific regions

---

## 🚀 Quick Examples

### Find UK Backlinks

```bash
python search_link_sets.py tier1 --domain=microsoft.com --country=uk
```

**What it searches**: `.uk`, `.co.uk`, `.ac.uk`, `.gov.uk`, `.org.uk`

### Find German Backlinks

```bash
python search_link_sets.py tier1 --domain=target.com --country=de
```

**What it searches**: `.de`

### Find US Government Sites

```bash
python search_link_sets.py tier1 --domain=target.com --country=gov
```

**What it searches**: `.gov`, `.gov.uk`, `.gov.au`, `.gov.ca`

### Find Education Sites Worldwide

```bash
python search_link_sets.py tier1 --domain=target.com --country=edu
```

**What it searches**: `.edu`, `.ac.uk`, `.edu.au`, `.ac.jp`

---

## 📋 Complete Country List

### View Available Countries

```bash
python search_link_sets.py --list-countries
```

**Output**:

```
🌍 Available Country Codes
============================================================
ae       → .ae
ar       → .ar, .com.ar
at       → .at
au       → .au, .com.au, .gov.au, .edu.au
be       → .be
bg       → .bg
br       → .br, .com.br
ca       → .ca
ch       → .ch
...
uk       → .uk, .co.uk, .ac.uk, .gov.uk, .org.uk
us       → .us, .gov, .edu, .mil
...
```

---

## 🌐 Supported Countries & Regions

### Major Countries (60+ supported)

| Region           | Countries                                                                      |
| ---------------- | ------------------------------------------------------------------------------ |
| **Europe**       | uk, de, fr, es, it, nl, pl, se, ch, at, be, no, dk, fi, ie, pt, gr, cz, ro, hu |
| **Americas**     | us, ca, br, mx, ar, cl, co, ve, pe                                             |
| **Asia-Pacific** | jp, cn, in, au, kr, sg, my, id, th, vn, ph, nz, hk, tw                         |
| **Middle East**  | il, ae, sa, tr                                                                 |
| **Africa**       | za, eg, ng, ke                                                                 |
| **EU**           | eu (European Union-wide)                                                       |

### Special Categories

| Code  | Description      | TLDs                            |
| ----- | ---------------- | ------------------------------- |
| `gov` | Government sites | .gov, .gov.uk, .gov.au, .gov.ca |
| `edu` | Education sites  | .edu, .ac.uk, .edu.au, .ac.jp   |
| `mil` | Military sites   | .mil                            |

---

## 🎯 Use Cases

### Use Case 1: International Press Coverage

**Question**: "Which UK news sites link to our product?"

```bash
python search_link_sets.py tier1 \
  --domain=ourproduct.com \
  --country=uk \
  --min-score=60 \
  --format=csv \
  --output=uk_press.csv
```

**Result**: CSV with all UK backlinks (includes .uk, .co.uk domains)

---

### Use Case 2: Government Backlinks

**Question**: "Do any government sites link to this domain?"

```bash
python search_link_sets.py tier1 \
  --domain=target.com \
  --country=gov \
  --format=table
```

**Result**: Table showing all .gov backlinks

---

### Use Case 3: Academic Research

**Question**: "Which universities cite our research?"

```bash
python search_link_sets.py tier1 \
  --domain=research-lab.com \
  --country=edu \
  --min-score=50
```

**Result**: List of education sites (.edu, .ac.uk, etc.)

---

### Use Case 4: Competitive Intelligence

**Question**: "Where do German companies link to our competitor?"

```bash
python search_link_sets.py tier2 \
  --domain=competitor.com \
  --country=de \
  --format=json \
  --output=de_competitor_backlinks.json
```

**Result**: JSON with German backlinks for analysis

---

### Use Case 5: Cross-Country Analysis

**Question**: "Compare UK vs US backlinks to our site"

```bash
# UK backlinks
python search_link_sets.py tier1 --domain=mysite.com --country=uk --output=uk.csv

# US backlinks
python search_link_sets.py tier1 --domain=mysite.com --country=us --output=us.csv

# Compare
diff uk.csv us.csv
```

---

### Use Case 6: Multi-Country Investigation

**Question**: "Find backlinks from EU countries"

```bash
# Search each country individually
for country in uk de fr es it nl; do
  python search_link_sets.py tier1 \
    --domain=target.com \
    --country=$country \
    --format=csv \
    --output=backlinks_${country}.csv
done

# Combine results
cat backlinks_*.csv > eu_backlinks_combined.csv
```

---

## 🔍 Advanced Filtering

### Combine Country + Quality Score

```bash
# High-quality UK backlinks only
python search_link_sets.py tier1 \
  --domain=target.com \
  --country=uk \
  --min-score=70
```

### Multiple TLD Countries

Some countries use multiple TLDs. The system automatically handles this:

```bash
# UK includes: .uk, .co.uk, .ac.uk, .gov.uk, .org.uk
python search_link_sets.py tier1 --domain=target.com --country=uk
```

```bash
# Australia includes: .au, .com.au, .gov.au, .edu.au
python search_link_sets.py tier1 --domain=target.com --country=au
```

```bash
# Japan includes: .jp, .co.jp, .ne.jp
python search_link_sets.py tier1 --domain=target.com --country=jp
```

---

## 📊 Country Statistics

### Count Backlinks by Country

Use MongoDB aggregation to see country distribution:

```javascript
// Connect to MongoDB
mongo localhost:27017/linksets

// Count backlinks by TLD (approximates country)
db.linksets_tier1_CC_MAIN_2024_10.aggregate([
  {$match: {target_domain: "microsoft.com"}},
  {$group: {
    _id: {$substr: ["$source_domain",
                    {$subtract: [{$indexOfBytes: ["$source_domain", "."]}, 0]},
                    -1]},
    count: {$sum: 1}
  }},
  {$sort: {count: -1}},
  {$limit: 20}
])
```

**Output**:

```
{ "_id" : ".com", "count" : 12543 }
{ "_id" : ".uk", "count" : 2341 }
{ "_id" : ".de", "count" : 1823 }
{ "_id" : ".edu", "count" : 1521 }
{ "_id" : ".fr", "count" : 982 }
...
```

---

## 🗺️ Country-Specific Intelligence

### European Union Focus

```bash
# EU-wide TLD
python search_link_sets.py tier1 --domain=target.com --country=eu

# Major EU countries
for country in de fr it es nl pl; do
  echo "=== $country ==="
  python search_link_sets.py tier1 --domain=target.com --country=$country --limit=10
done
```

### Five Eyes Intelligence Alliance

```bash
# Five Eyes countries (US, UK, CA, AU, NZ)
for country in us uk ca au nz; do
  python search_link_sets.py tier1 \
    --domain=target.com \
    --country=$country \
    --format=csv \
    --output=fiveeyes_${country}.csv
done
```

### BRICS Nations

```bash
# Brazil, Russia, India, China, South Africa
for country in br ru in cn za; do
  python search_link_sets.py tier1 \
    --domain=target.com \
    --country=$country \
    --format=json \
    --output=brics_${country}.json
done
```

---

## 🛠️ Technical Details

### How Country Filtering Works

1. **Country code lookup**: Maps 2-letter code to TLD list

   ```python
   'uk' → ['.uk', '.co.uk', '.ac.uk', '.gov.uk', '.org.uk']
   ```

2. **MongoDB regex query**: Matches domains ending with those TLDs

   ```javascript
   {
     $or: [
       { source_domain: { $regex: "\.uk$", $options: "i" } },
       { source_domain: { $regex: "\.co\.uk$", $options: "i" } },
       { source_domain: { $regex: "\.ac\.uk$", $options: "i" } },
       { source_domain: { $regex: "\.gov\.uk$", $options: "i" } },
       { source_domain: { $regex: "\.org\.uk$", $options: "i" } },
     ];
   }
   ```

3. **Performance**: Uses MongoDB indexes, query time <1 second

### Adding Custom Countries

Edit `search_link_sets.py` and add to `COUNTRY_CODES` dict:

```python
COUNTRY_CODES = {
    # ... existing codes ...
    'custom': ['.custom.tld'],  # Add your custom TLD
}
```

---

## 📈 Performance

### Query Performance by Country Complexity

| Country          | TLDs | Query Time |
| ---------------- | ---- | ---------- |
| Germany (.de)    | 1    | 0.1s       |
| France (.fr)     | 1    | 0.1s       |
| UK               | 5    | 0.3s       |
| Australia        | 4    | 0.3s       |
| US (gov/edu/mil) | 4    | 0.3s       |

**Note**: Multi-TLD countries take slightly longer due to $or query

---

## 🎓 Best Practices

### 1. Start with Specific Countries

```bash
# Good: Targeted country
python search_link_sets.py tier1 --domain=target.com --country=uk

# Less effective: Too broad
python search_link_sets.py tier1 --domain=target.com --source-tld=.com
```

### 2. Combine with Quality Filters

```bash
# High-quality UK backlinks only
python search_link_sets.py tier1 \
  --domain=target.com \
  --country=uk \
  --min-score=60
```

### 3. Export for Further Analysis

```bash
# Export to CSV for Excel/pandas
python search_link_sets.py tier1 \
  --domain=target.com \
  --country=de \
  --format=csv \
  --output=german_backlinks.csv

# Export to JSON for programmatic processing
python search_link_sets.py tier1 \
  --domain=target.com \
  --country=fr \
  --format=json \
  --output=french_backlinks.json
```

### 4. Use Special Categories

```bash
# Government sites across all countries
python search_link_sets.py tier1 --domain=target.com --country=gov

# Universities worldwide
python search_link_sets.py tier1 --domain=target.com --country=edu
```

---

## 🔄 Comparison: Country vs TLD Filtering

### Method 1: Country Code (Recommended)

```bash
python search_link_sets.py tier1 --domain=target.com --country=uk
```

**Advantages**:

- ✅ Automatically includes all UK TLDs (.uk, .co.uk, .ac.uk, .gov.uk, .org.uk)
- ✅ Shorter syntax
- ✅ More intuitive

### Method 2: Direct TLD

```bash
python search_link_sets.py tier1 --domain=target.com --source-tld=.co.uk
```

**Advantages**:

- ✅ More precise (single TLD only)
- ✅ Can search ANY TLD (not just predefined countries)

**Use this when**:

- You want ONLY .co.uk (not .uk, .ac.uk, etc.)
- You need a TLD not in the country list

---

## 🌍 Real-World Examples

### Example 1: Track Russian Links (OSINT)

```bash
python search_link_sets.py tier1 \
  --domain=target.com \
  --country=ru \
  --format=csv \
  --output=russian_links.csv
```

**Use**: Monitor Russian state/media links to target

---

### Example 2: EU Compliance Check

```bash
# Check for GDPR-relevant backlinks
for country in uk de fr it es nl be; do
  python search_link_sets.py tier1 \
    --domain=ourcompany.com \
    --country=$country \
    --output=eu_${country}_links.csv
done
```

**Use**: Identify EU data processing relationships

---

### Example 3: Academic Citation Map

```bash
# Find which universities cite your research
python search_link_sets.py tier1 \
  --domain=research-institute.edu \
  --country=edu \
  --min-score=70 \
  --format=json \
  --output=university_citations.json
```

**Use**: Track academic impact

---

### Example 4: Government Influence Mapping

```bash
# Find all government links to target organization
python search_link_sets.py tier1 \
  --domain=ngo.org \
  --country=gov \
  --format=csv \
  --output=government_links.csv
```

**Use**: Map government relationships

---

## 📝 Summary

**What you can do**:

- ✅ Filter by 60+ countries
- ✅ Search multiple TLDs per country automatically
- ✅ Use special categories (gov, edu, mil)
- ✅ Combine with quality/score filters
- ✅ Export to CSV/JSON for analysis
- ✅ Instant results (<1 second)

**Common use cases**:

- 🔍 OSINT investigations
- 📰 Media coverage analysis
- 🎓 Academic citation tracking
- 🏛️ Government relationship mapping
- 🌐 Geopolitical research
- 🛡️ Threat intelligence

**Next steps**:

1. Try: `python search_link_sets.py --list-countries`
2. Test: `python search_link_sets.py tier1 --domain=microsoft.com --country=uk`
3. Explore: Combine country + quality filters for targeted results

---

**Generated**: 2025-10-17
**Version**: 1.0
**Feature**: Country-based geographic backlink filtering
