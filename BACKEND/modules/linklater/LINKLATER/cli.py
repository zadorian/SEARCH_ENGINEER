#!/usr/bin/env python3
"""
LinkLater CLI - Minimal version for sastre batch processing.
Uses CCFirstScraper for CC + Wayback scraping (FREE).
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import List, Dict, Any
from types import SimpleNamespace

# Import CCFirstScraper
sys.path.insert(0, str(Path(__file__).parent.parent))
from LINKLATER.scraping.cc_first_scraper import CCFirstScraper, ScrapeResult


class LinkLaterCLI:
    """LinkLater command-line interface."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.scraper = CCFirstScraper(
            extract_binary=getattr(args, "extract_binary", True),
            cc_only=getattr(args, "cc_only", False),
            convert_to_markdown=getattr(args, "format", "json") in ["markdown", "md"],
            timeout=getattr(args, "timeout", 30.0),
        )

    async def scrape_single(self, url: str) -> Dict[str, Any]:
        """Scrape a single URL."""
        if self.args.verbose:
            print(f"Scraping: {url}", file=sys.stderr)

        result = await self.scraper.get_content(url)

        if self.args.verbose:
            print(f"  Source: {result.source}, Latency: {result.latency_ms}ms, Len: {len(result.content)}", file=sys.stderr)

        return self._format_result(result)

    async def scrape_batch(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Scrape multiple URLs with progress tracking."""
        total = len(urls)

        def progress_callback(done, total, url, source):
            if self.args.verbose:
                pct = (done / total) * 100
                print(f"[{done}/{total} - {pct:.1f}%] {url[:60]} -> {source}", file=sys.stderr)

        if self.args.verbose:
            print(f"Batch scraping {total} URLs with {self.args.concurrent} concurrent", file=sys.stderr)

        start = time.time()
        results = await self.scraper.batch_scrape(
            urls,
            max_concurrent=self.args.concurrent,
            progress_callback=progress_callback if self.args.verbose else None
        )
        elapsed = time.time() - start

        if self.args.verbose:
            print(f"Batch complete in {elapsed:.2f}s", file=sys.stderr)
            self._print_stats()

        return [self._format_result(r) for r in results.values()]

    def _format_result(self, result: ScrapeResult) -> Dict[str, Any]:
        """Format ScrapeResult to dict."""
        return {
            "url": result.url,
            "source": result.source,
            "content": result.content,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "timestamp": result.timestamp,
            "error": result.error
        }

    def _print_stats(self):
        """Print scraping statistics."""
        stats = self.scraper.get_stats()
        print(f"Stats: CC={stats['cc_hits']} WB={stats['wayback_hits']} Fail={stats['failures']} Rate={stats['archive_hit_rate']}", file=sys.stderr)

    def output_results(self, results: Any):
        """Output results in requested format."""
        if self.args.format == "json":
            output = json.dumps(results, indent=2, ensure_ascii=False)
        elif self.args.format in ["markdown", "md"]:
            if isinstance(results, list):
                output = "\n\n---\n\n".join(r.get("content", "") for r in results)
            else:
                output = results.get("content", "")
        else:  # text
            if isinstance(results, list):
                output = "\n\n".join(r.get("content", "") for r in results)
            else:
                output = results.get("content", "")

        if self.args.output:
            Path(self.args.output).write_text(output, encoding="utf-8")
            if self.args.verbose:
                print(f"Output written to: {self.args.output}", file=sys.stderr)
        else:
            print(output)

    async def run(self):
        """Main execution."""
        # Get URLs
        if self.args.url:
            urls = [self.args.url]
        elif self.args.file:
            urls = Path(self.args.file).read_text().strip().split("\n")
            urls = [u.strip() for u in urls if u.strip()]
        else:
            print("Error: Must provide --url or --file", file=sys.stderr)
            sys.exit(1)

        # Scrape
        if len(urls) == 1:
            results = await self.scrape_single(urls[0])
        else:
            results = await self.scrape_batch(urls)

        # Output
        self.output_results(results)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="LinkLater CLI - CC + Wayback batch scraper (FREE)"
    )

    # URL input
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--url", "-u", help="Single URL to scrape")
    input_group.add_argument("--file", "-f", help="File containing URLs (one per line)")

    # Options
    parser.add_argument("--cc-only", action="store_true", default=False,
                        help="Common Crawl + Wayback only (no paid Firecrawl)")
    parser.add_argument("--output", "-o", help="Output file (stdout if not specified)")
    parser.add_argument("--format", choices=["json", "markdown", "md", "text"], default="json",
                        help="Output format [default: json]")
    parser.add_argument("--concurrent", "-c", type=int, default=50,
                        help="Max concurrent requests [default: 50]")
    parser.add_argument("--timeout", "-t", type=float, default=30.0,
                        help="Request timeout in seconds [default: 30.0]")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output with progress")
    parser.add_argument("--extract-binary", action="store_true", default=True,
                        help="Extract text from binary files (PDF, DOCX, etc)")

    args = parser.parse_args()

    # Run
    cli = LinkLaterCLI(args)
    asyncio.run(cli.run())


if __name__ == "__main__":
    main()
