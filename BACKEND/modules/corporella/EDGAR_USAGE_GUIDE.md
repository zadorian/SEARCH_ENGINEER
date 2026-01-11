# EDGAR Tool Usage Guide

## Overview

The EDGAR tool in your Corporate Search system provides access to SEC filings for US public companies. It's located in `/EDGAR-main/` and offers both command-line and programmatic interfaces.

## Quick Start

### 1. Using the Interactive Menu

The easiest way to start:

```bash
cd /Users/brain/Desktop/Corporate_Search/EDGAR-main
python edgar_menu.py
```

This provides a user-friendly menu with options for:

- Text search across filings
- RSS feed monitoring by ticker
- Finding latest results

### 2. Command Line Usage

#### Text Search Examples

```bash
# Basic search
python -m edgar_tool.cli text_search "artificial intelligence"

# Search with date range
python -m edgar_tool.cli text_search "merger acquisition" --start_date "2023-01-01" --end_date "2023-12-31"

# Search specific company
python -m edgar_tool.cli text_search "revenue growth" --company_name "Apple Inc"

# Search by filing type
python -m edgar_tool.cli text_search "climate change" --filing_form "all_annual_quarterly_and_current_reports"

# Search with incorporation location
python -m edgar_tool.cli text_search "offshore drilling" --inc_in "TX"
```

#### RSS Feed Monitoring

```bash
# One-time check
python -m edgar_tool.cli rss "AAPL" "MSFT" "GOOGL" --output "tech_filings.csv"

# Periodic monitoring (every 30 minutes)
python -m edgar_tool.cli rss "TSLA" --every_n_mins 30 --output "tesla_monitor.json"
```

### 3. Using the Python Integration

Use the new `edgar_integration.py` wrapper:

```python
from edgar_integration import EdgarSearchIntegration

# Initialize
edgar = EdgarSearchIntegration()

# Search for keywords
results = edgar.text_search(
    search_terms=["blockchain", "cryptocurrency"],
    start_date="2024-01-01",
    output_format="json"
)

# Get specific company filings
apple_filings = edgar.search_company_filings(
    company_name="Apple Inc",
    years_back=2
)

# Monitor RSS feed
rss_results = edgar.rss_monitor(
    tickers=['NVDA', 'AMD'],
    output_format='json'
)
```

## Filing Form Categories

Use these values for the `--filing_form` parameter:

- `all` - All filing types
- `all_annual_quarterly_and_current_reports` - 10-K, 10-Q, 8-K
- `all_section_16` - Insider trading forms
- `registration_statements` - IPO and securities registrations
- `proxy_materials` - Proxy statements (DEF 14A)

## Common Filing Types

- **10-K** - Annual report
- **10-Q** - Quarterly report
- **8-K** - Current report (material events)
- **DEF 14A** - Proxy statement
- **S-1** - IPO registration
- **Forms 3/4/5** - Insider trading

## Integration with Other Tools

### Cross-Reference Workflow

1. Find company in OpenCorporates
2. Get official name and identifiers
3. Search EDGAR for filings
4. Cross-check with Companies House (for UK companies)
5. Check OCCRP Aleph for investigative records

### Example Integration Script

```python
# After finding a company in OpenCorporates
company_info = {
    'name': 'Tesla Inc',
    'jurisdiction': 'US',
    'identifier': '1318605'  # CIK
}

# Search EDGAR
edgar = EdgarSearchIntegration()
filings = edgar.text_search(
    search_terms=[""],
    entity_id=company_info['identifier'],
    filing_form="all_annual_quarterly_and_current_reports",
    start_date="2024-01-01"
)

# Process results
if filings['success']:
    for filing in filings['results']:
        print(f"{filing['Filing Type']} - {filing['Filed']} - {filing['Description']}")
```

## Output Formats

- **CSV** - Default, opens in Excel
- **JSON** - Structured data for programming
- **JSONL** - JSON Lines, one record per line

## Tips & Best Practices

1. **Rate Limiting**: The tool has built-in delays to respect SEC limits
2. **Date Formats**: Always use YYYY-MM-DD format
3. **Company Names**: Use exact names as registered with SEC
4. **Large Searches**: Break into smaller date ranges if timeout occurs
5. **Monitoring**: Use RSS feed for real-time updates instead of repeated searches

## Troubleshooting

### Common Issues

1. **No results found**
   - Check company name spelling
   - Try broader date range
   - Use fewer/different keywords

2. **Command not found**
   - Ensure you're in the EDGAR-main directory
   - Check Python version (3.7+ required)
   - Install dependencies: `pip install -r requirements.txt`

3. **Rate limit errors**
   - Add `--min_wait 5.0 --max_wait 10.0` for longer delays
   - Reduce search scope

### File Locations

- **Output files**: `/EDGAR-main/output/`
- **Search results**: Named with timestamp (e.g., `edgar_search_20240101_123456.csv`)
- **Configuration**: Check `edgar_tool/constants.py` for defaults

## Advanced Features

### Custom Date Ranges

```bash
# Last 30 days
python -m edgar_tool.cli text_search "earnings" --start_date "30d"

# Specific quarter
python -m edgar_tool.cli text_search "Q3 results" \
    --start_date "2023-07-01" --end_date "2023-09-30"
```

### Multiple Search Terms

```bash
# Search for multiple phrases
python -m edgar_tool.cli text_search "climate risk" "environmental impact" "carbon emissions"

# Exact phrase matching
python -m edgar_tool.cli text_search '"revenue guidance"' '"forward looking statements"'
```

### Batch Processing

Create a script for batch searches:

```python
companies = ['Apple Inc', 'Microsoft Corporation', 'Amazon.com Inc']
search_terms = ['AI', 'artificial intelligence', 'machine learning']

for company in companies:
    results = edgar.text_search(
        search_terms=search_terms,
        company_name=company,
        start_date="2024-01-01",
        output_format="json"
    )
    # Process results...
```

## Next Steps

1. Set up automated monitoring for key companies
2. Create alerts for specific filing types
3. Build analysis pipelines for extracted data
4. Integrate with other Corporate Search tools
5. Generate periodic reports on filing trends

---

For more details, see the full documentation in `/EDGAR-main/README.md`
