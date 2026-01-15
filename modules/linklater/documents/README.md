# LINKLATER - Archive Keyword and Link Intelligence

**Common Crawl entity extraction and link intelligence module with AI-accessible MCP interface.**

## What It Does

LINKLATER extracts structured intelligence from Common Crawl archives:

- **Entities**: Companies, People, Locations, Email Addresses, Registration Numbers
- **Link Intelligence**: Outlink analysis, backlink tracking, domain relationships
- **Keyword Variations**: Semantic search with automatic query expansion
- **Batch Processing**: Process hundreds of domains from a simple file list

## Quick Start - Using with Claude Code (MCP)

**After restarting Claude Code**, you can simply ask:

```
"Use LINKLATER to extract entities from example.com"

"Run LINKLATER on domains_list.txt and show me all the companies found"

"Search Common Crawl for 'offshore company' using LINKLATER"
```

No command line needed - just tell Claude what you want!

## Creating a Domain List

Create a text file with one domain per line:

```bash
# domains.txt
example.com
test-domain.org
another-site.net
```

Then just tell Claude:

```
"Use LINKLATER to process domains.txt"
```

## Available MCP Tools

### 1. `extract_domain_entities`

Extract all entities from a single domain's Common Crawl pages.

**Example:**

```
"Extract entities from bebeez.it using LINKLATER"
```

### 2. `batch_extract_domains`

Process multiple domains from a file.

**Example:**

```
"Process the domains in ~/my_targets.txt with LINKLATER, save to results.json"
```

### 3. `keyword_variations_search`

Search with automatic keyword variations.

**Example:**

```
"Search Common Crawl for 'corporate registry' on domain:opencorporates.com using LINKLATER"
```

## Output Format

LINKLATER produces clean, readable reports:

```
================================================================================
LINKLATER ENTITY EXTRACTION RESULTS
Timestamp: 2025-11-26 14:30:00
================================================================================

📍 Domain: example.com
📄 Pages Analyzed: 127

================================================================================
🏢 ENTITIES FOUND
================================================================================

🏢 Companies (23):
  • Acme Corporation
  • Example Holdings Ltd
  • Test Industries Inc
  ...

👤 People (15):
  • John Smith
  • Jane Doe
  ...

📍 Locations (8):
  • London, UK
  • New York, USA
  ...

🔢 Registration Numbers (5):
  • 12345678
  • UK987654321
  ...

📧 Email Addresses (12):
  • contact@example.com
  • info@example.com
  ...
```

## CLI Usage (Direct)

### Single Domain Extraction (with automatic "dig deeper")

```bash
cd ~/DRILL_SEARCH/drill-search-app/python-backend

# Single domain - automatically tries multiple strategies if needed
PYTHONPATH=$(pwd) python3 modules/linklater/linklater_cli.py domain-extract \
  --domain example.com --limit 200 --pretty
```

**Automatic "Dig Deeper" Strategies:**
When no results are found, LINKLATER automatically tries:

1. `*.domain/*` pattern (with subdomains)
2. `domain/*` pattern (exact domain only)
3. Alternative `www.` prefix (tries both with/without)
4. Older CC collections (2025 → 2024 → 2023 → 2022...)

### Batch Domain Spider (Full Feature Set)

For comprehensive multi-domain scanning with outlink discovery:

```bash
cd ~/DRILL_SEARCH/drill-search-app
source venv/bin/activate

# Basic scan
PYTHONPATH=/Users/attic/DRILL_SEARCH/drill-search-app/python-backend:/Users/attic/DRILL_SEARCH/drill-search-app \
python3 scripts/linklater_domain_spider.py \
  --domains-file domains.txt \
  --output results/linklater_scan.json \
  --limit 200 \
  --max-concurrent 10 \
  --max-outlinks 300

# Unlimited outlinks
python3 scripts/linklater_domain_spider.py \
  --domains-file domains.txt \
  --max-outlinks 0 \
  --output results/full_scan.json

# Custom CC collections (for older/specific dates)
python3 scripts/linklater_domain_spider.py \
  --domains-file domains.txt \
  --cc-collections CC-MAIN-2025-47,CC-MAIN-2024-10,CC-MAIN-2023-50
```

**Spider Features:**

- Tries multiple CC collections automatically (2015-2025)
- Extracts entities from each page
- Discovers outlinks (configurable limit)
- Saves detailed per-page results
- Handles older/archived domains

## Architecture

```
linklater/
├── __init__.py              # Module exports
├── cc_first_scraper.py      # Common Crawl API client
├── entity_patterns.py       # Entity extraction patterns
├── keyword_variations.py    # Semantic search
├── cc_enricher.py          # Entity enrichment
├── warc_parser.py          # WARC file parsing
├── linklater_cli.py        # CLI interface
└── README.md               # This file

python-backend/mcp_servers/
└── linklater_mcp.py        # MCP server (AI interface)
```

## Integration with Matrix Router

LINKLATER feeds into the Drill Search Matrix routing system:

- Entities → Elasticsearch nodes
- Link intelligence → Edge relationships
- Enrichment routes → Corporella/AllDom integration

## Requirements

- Python 3.8+
- `cdx-toolkit` for Common Crawl API
- `warcio` for WARC parsing
- `mcp` for AI interface

All dependencies installed via project requirements.

## Troubleshooting

**"No results found"**

- Domain may not be in Common Crawl index
- Try broader date ranges
- Check domain spelling

**"API rate limit"**

- Common Crawl has no hard limits, but add delays for courtesy
- Use `--limit` to reduce load

**"MCP server not found"**

- Restart Claude Code after config changes
- Check path in claude_desktop_config.json
- Verify linklater_mcp.py is executable

## Future Enhancements

- [ ] Recursive outlink following
- [ ] Historical trend analysis
- [ ] Entity relationship mapping
- [ ] Integration with Wayback Machine
- [ ] Cross-domain entity tracking
