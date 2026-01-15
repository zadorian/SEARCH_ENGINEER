#!/usr/bin/env python3
"""
LinkLater - Archive Intelligence & Binary Extraction Engine

COMPREHENSIVE ARCHIVE EXTRACTION CLI
Extracts text from web archives (Common Crawl, Wayback Machine, Firecrawl)
with support for binary files, entity extraction, and link graph building.

FEATURES:
✅ Binary file extraction (PDF, DOCX, XLSX, PPTX)
✅ Three-tier fallback chain (CC → Wayback → Firecrawl)
✅ Entity extraction (companies, persons, registrations)
✅ Outlink extraction (links from pages to external domains)
✅ Backlink integration (via Common Crawl WebGraph)
✅ Automated pipelines (see pipelines/ directory)

FALLBACK CHAIN (Automatic):
1. Common Crawl (free, bulk archives)
2. Wayback Machine (free, comprehensive historical)
3. Firecrawl (paid, live scraping - API key required)

USAGE EXAMPLES:

# Single URL - automatic binary extraction + fallback
python cli.py --url "https://example.com/report.pdf"

# Multiple URLs from file
python cli.py --file urls.txt --output results.json

# Extract with entity detection
python cli.py --url "https://example.com" --extract-entities

# Extract with outlinks
python cli.py --url "https://example.com" --extract-outlinks

# Full extraction (content + entities + outlinks)
python cli.py --url "https://example.com" --extract-entities --extract-outlinks --verbose

# Batch processing with high concurrency
python cli.py --file urls.txt --concurrent 100 --output batch_results.json

# Common Crawl only (skip Wayback/Firecrawl)
python cli.py --url "https://example.com" --cc-only

# Output formats: json, markdown, text
python cli.py --url "https://example.com" --format json

AUTOMATED PIPELINES:
See pipelines/ directory for one-command workflows:
  ./pipelines/extract_domain_pdfs.sh "company.com"
  ./pipelines/extract_domain_docs.sh "company.com"
  ./pipelines/full_entity_extraction.sh "company.com" graph.json

ENVIRONMENT VARIABLES:
- FIRECRAWL_API_KEY - Required for Firecrawl fallback tier

BINARY FILE SUPPORT:
✅ PDF (.pdf) - pypdf/pdfplumber
✅ Word (.docx) - python-docx
✅ Excel (.xlsx) - openpyxl
✅ PowerPoint (.pptx) - python-pptx
✅ Archives (.zip, .tar, .gz) - lists contents

ENTITY EXTRACTION:
✅ Companies (e.g., "Acme Corporation", "Example Ltd")
✅ Persons (e.g., "John Smith", "Jane Doe")
✅ Registration numbers (e.g., "12345678", "UK987654")

LINK INTELLIGENCE:
✅ Outlinks - Links FROM page to external domains
✅ Backlinks - Links TO page (via CC WebGraph integration)
✅ Knowledge graphs - Nodes (pages/entities) + Edges (mentions/links)

OUTPUT STRUCTURE:
{
  "url": "https://example.com/report.pdf",
  "source": "wayback",  // "cc", "wayback", "firecrawl", or "failed"
  "content": "Extracted text here...",
  "status": 200,
  "latency_ms": 350,
  "timestamp": "20240101123456",
  "companies": [...],   // if --extract-entities
  "persons": [...],     // if --extract-entities
  "outlinks": [...],    // if --extract-outlinks
  "error": null
}

For complete documentation, see LINKLATER_README.md
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import List, Dict, Any
from types import SimpleNamespace

# Import handling for script vs module execution
try:
    from .scraping.cc_first_scraper import CCFirstScraper, ScrapeResult
    from .enrichment.cc_enricher import CCEnricher
except ImportError:
    # Fallback for direct script execution
    sys.path.append(str(Path(__file__).parent))
    from scraping.cc_first_scraper import CCFirstScraper, ScrapeResult
    from enrichment.cc_enricher import CCEnricher


class LinkLaterCLI:
    """LinkLater command-line interface."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.scraper = CCFirstScraper(
            extract_binary=args.extract_binary,
            cc_only=args.cc_only,
            convert_to_markdown=args.format in ['markdown', 'md'],
            timeout=args.timeout,
        )

        # Initialize enricher if entity/outlink extraction requested
        self.enricher = None
        if args.extract_entities or args.extract_outlinks:
            self.enricher = CCEnricher(
                extract_entities=args.extract_entities,
                extract_outlinks=args.extract_outlinks,
                skip_directories=True,
            )

    async def scrape_single(self, url: str) -> Dict[str, Any]:
        """Scrape a single URL."""
        if self.args.verbose:
            print(f"\n{'='*60}")
            print(f"Scraping: {url}")
            print(f"{'='*60}")

        result = await self.scraper.get_content(url)

        if self.args.verbose:
            print(f"Source: {result.source}")
            print(f"Status: {result.status}")
            print(f"Latency: {result.latency_ms}ms")
            print(f"Content length: {len(result.content)} chars")
            if result.error:
                print(f"Error: {result.error}")

        # Enrich with entities/outlinks if requested
        formatted = self._format_result(result)
        if self.enricher and result.content:
            enriched = await self.enricher.enrich_single(url, '', result.content[:1000])

            if self.args.extract_entities:
                formatted['companies'] = enriched.companies
                formatted['persons'] = enriched.persons
                formatted['registrations'] = enriched.registrations

            if self.args.extract_outlinks:
                formatted['outlinks'] = enriched.outlinks

            if self.args.verbose:
                print(f"Entities: {len(enriched.companies)} companies, {len(enriched.persons)} persons")
                print(f"Outlinks: {len(enriched.outlinks)}")

        return formatted

    async def scrape_batch(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Scrape multiple URLs with progress tracking."""
        total = len(urls)
        completed = 0

        def progress_callback(done, total, url, source):
            nonlocal completed
            completed = done
            if self.args.verbose:
                pct = (done / total) * 100
                print(f"[{done}/{total} - {pct:.1f}%] {url[:50]} → {source}")

        if self.args.verbose:
            print(f"\n{'='*60}")
            print(f"Batch scraping {total} URLs")
            print(f"Concurrency: {self.args.concurrent}")
            print(f"{'='*60}\n")

        start = time.time()
        results = await self.scraper.batch_scrape(
            urls,
            max_concurrent=self.args.concurrent,
            progress_callback=progress_callback if self.args.verbose else None
        )
        elapsed = time.time() - start

        if self.args.verbose:
            print(f"\n{'='*60}")
            print(f"Batch complete in {elapsed:.2f}s")
            print(f"{'='*60}\n")
            self._print_stats()

        return [self._format_result(r) for r in results.values()]

    def _format_result(self, result: ScrapeResult) -> Dict[str, Any]:
        """Format ScrapeResult to dict."""
        return {
            'url': result.url,
            'source': result.source,
            'content': result.content,
            'status': result.status,
            'latency_ms': result.latency_ms,
            'timestamp': result.timestamp,
            'error': result.error
        }

    def _print_stats(self):
        """Print scraping statistics."""
        stats = self.scraper.get_stats()
        print("Statistics:")
        print(f"  Common Crawl hits: {stats['cc_hits']}")
        print(f"  Wayback hits: {stats['wayback_hits']}")
        print(f"  Firecrawl hits: {stats['firecrawl_hits']}")
        print(f"  Failures: {stats['failures']}")
        print(f"  Cache hits: {stats['cache_hits']}")
        print(f"  Archive hit rate: {stats['archive_hit_rate']}")
        print(f"  Total success rate: {stats['total_success_rate']}")

    def output_results(self, results: Any):
        """Output results in requested format."""
        # For Matrix Execution Engine, we need specific structure
        if getattr(self.args, 'matrix_mode', False):
            # Calculate fields added
            fields_added = 0
            if isinstance(results, dict):
                if results.get('content'): fields_added += 1
                fields_added += len(results.get('companies', []))
                fields_added += len(results.get('persons', []))
                fields_added += len(results.get('outlinks', []))
            
            output = {
                "fieldsAdded": fields_added,
                "data": results,
                "sources": ["Common Crawl", "Wayback"] + ([results.get('source')] if isinstance(results, dict) and results.get('source') else [])
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
            return

        if self.args.format == 'json':
            output = json.dumps(results, indent=2, ensure_ascii=False)
        elif self.args.format in ['markdown', 'md']:
            if isinstance(results, list):
                output = '\n\n---\n\n'.join(r.get('content', '') for r in results)
            else:
                output = results.get('content', '')
        else:  # text
            if isinstance(results, list):
                output = '\n\n'.join(r.get('content', '') for r in results)
            else:
                output = results.get('content', '')

        if self.args.output:
            Path(self.args.output).write_text(output, encoding='utf-8')
            if self.args.verbose:
                print(f"\n✅ Output written to: {self.args.output}")
        else:
            print(output)

    async def run(self):
        """Main execution."""
        # Get URLs
        if self.args.url:
            urls = [self.args.url]
        elif self.args.file:
            urls = Path(self.args.file).read_text().strip().split('\n')
            urls = [u.strip() for u in urls if u.strip()]
        else:
            print("❌ Error: Must provide --url or --file", file=sys.stderr)
            sys.exit(1)

        # Scrape
        if len(urls) == 1:
            results = await self.scrape_single(urls[0])
        else:
            results = await self.scrape_batch(urls)

        # Output
        self.output_results(results)

        # Stats
        if self.args.verbose and self.args.stats:
            print(f"\n{'='*60}")
            self._print_stats()
            print(f"{'='*60}")


def main():
    """Main entry point."""
    
    # Check for Matrix Execution Engine JSON input
    if len(sys.argv) == 2 and sys.argv[1].strip().startswith('{'):
        try:
            data = json.loads(sys.argv[1])
            
            # Extract inputs
            url = None
            if 'inputs' in data:
                inputs = data.get('inputs', {})
                url = inputs.get('domain_url') or inputs.get('url') or inputs.get('domain') or list(inputs.values())[0]
            else:
                url = data.get('url') or data.get('domain')

            if not url:
                print(json.dumps({"error": "No URL provided in inputs"}))
                sys.exit(1)

            # Construct args for LinkLaterCLI
            args = SimpleNamespace(
                url=url,
                file=None,
                extract_binary=True,
                cc_only=False,
                extract_entities=True, # Default to True for enrichment
                extract_outlinks=True, # Default to True for enrichment
                output=None,
                format='json',
                concurrent=1,
                timeout=30.0,
                verbose=False,
                stats=False,
                matrix_mode=True # Flag for special output format
            )
            
            cli = LinkLaterCLI(args)
            asyncio.run(cli.run())
            return

        except json.JSONDecodeError:
            pass # Fallback to standard argparse

    parser = argparse.ArgumentParser(
        description='LinkLater - Extract text from web archives (CC, Wayback, Firecrawl)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:

  # Single URL
  python cli.py --url "https://example.com/report.pdf"

  # Batch from file
  python cli.py --file urls.txt --output results.json

  # Common Crawl only (no fallback)
  python cli.py --url "https://example.com" --cc-only

  # Disable binary extraction
  python cli.py --url "https://example.com" --no-binary

  # High concurrency batch
  python cli.py --file urls.txt --concurrent 100 --verbose

BINARY EXTRACTION:
  Automatically extracts text from PDF, DOCX, XLSX, PPTX files.
  Install dependencies: pip install pypdf pdfplumber python-docx openpyxl python-pptx

FALLBACK CHAIN:
  1. Common Crawl (free)
  2. Wayback Machine (free)
  3. Firecrawl (paid, requires FIRECRAWL_API_KEY env var)
        """
    )

    # URL input
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--url', '-u', help='Single URL to scrape')
    input_group.add_argument('--file', '-f', help='File containing URLs (one per line)')

    # Binary extraction
    binary_group = parser.add_mutually_exclusive_group()
    binary_group.add_argument('--extract-binary', dest='extract_binary', action='store_true', default=True,
                              help='Extract text from binary files (PDF, DOCX, etc) [default]')
    binary_group.add_argument('--no-binary', dest='extract_binary', action='store_false',
                              help='Disable binary extraction (HTML only)')

    # Source control
    parser.add_argument('--cc-only', action='store_true',
                        help='Common Crawl only (no Wayback/Firecrawl fallback)')

    # Entity and link extraction
    parser.add_argument('--extract-entities', action='store_true',
                        help='Extract entities (companies, persons, registrations)')
    parser.add_argument('--extract-outlinks', action='store_true',
                        help='Extract outlinks (external links from pages)')

    # Output
    parser.add_argument('--output', '-o', help='Output file (stdout if not specified)')
    parser.add_argument('--format', choices=['json', 'markdown', 'md', 'text'], default='json',
                        help='Output format [default: json]')

    # Performance
    parser.add_argument('--concurrent', '-c', type=int, default=50,
                        help='Max concurrent requests for batch mode [default: 50]')
    parser.add_argument('--timeout', '-t', type=float, default=15.0,
                        help='Request timeout in seconds [default: 15.0]')

    # Verbosity
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output with progress and stats')
    parser.add_argument('--stats', '-s', action='store_true', default=True,
                        help='Print statistics at end [default: True]')

    args = parser.parse_args()

    # Run
    cli = LinkLaterCLI(args)
    asyncio.run(cli.run())


if __name__ == '__main__':
    main()
