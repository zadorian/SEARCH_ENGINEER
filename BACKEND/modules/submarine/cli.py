#!/usr/bin/env python3
"""
SUBMARINE CLI - Smart Archive Search

Intelligently searches Common Crawl using all available indices
as "submerging points" to filter before touching raw WARC data.

USAGE:
    # Plan a search (shows what will be fetched)
    python cli.py plan "+1-234-567-8900"

    # Execute a search
    python cli.py search "john.smith@example.com"

    # Search with extraction
    python cli.py search --extract "Company Name"

    # Resume interrupted search
    python cli.py resume /path/to/plan.json

COMPONENTS:
    PERISCOPE - CC Index API client
    SONAR     - Our Elastic index scanner
    PLANNER   - Dive plan orchestrator
    DEEP_DIVE - Go-based WARC fetcher
    EXTRACTION- PACMAN entity pipeline
"""

import asyncio
import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add SUBMARINE to path
sys.path.insert(0, "/data/SUBMARINE")

from sonar.elastic_scanner import Sonar
from periscope.cc_index import Periscope
from dive_planner.planner import DivePlanner, DivePlan
from deep_dive.diver import DeepDiver
from extraction.pacman_bridge import extract_from_content, PACMANExtractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def _parse_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [p.strip() for p in value.split(",") if p.strip()]


def _load_torpedo_news_domains(
    jurisdiction: Optional[str],
    *,
    min_reliability: float = 0.0,
    limit: int = 50000,
) -> List[str]:
    try:
        from TORPEDO.paths import news_sources_path  # type: ignore

        path = Path(news_sources_path())
    except Exception:
        path = Path("/data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/sources/news.json")

    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    jur_key: Optional[str] = None
    if jurisdiction:
        jur = jurisdiction.strip().upper()
        if jur == "UK":
            jur = "GB"
        jur_key = jur

    sources: List[Dict[str, Any]] = []
    if jur_key:
        items = data.get(jur_key) or []
        if isinstance(items, list):
            sources = items
    else:
        for items in (data or {}).values():
            if isinstance(items, list):
                sources.extend(items)

    best: Dict[str, float] = {}
    for s in sources:
        if not isinstance(s, dict):
            continue
        dom = (s.get("domain") or "").strip().lower()
        if dom.startswith("www."):
            dom = dom[4:]
        if not dom or "." not in dom:
            continue
        try:
            rel = float(s.get("reliability", 0.0) or 0.0)
        except Exception:
            rel = 0.0
        if rel < float(min_reliability or 0.0):
            continue
        prev = best.get(dom, -1.0)
        if rel > prev:
            best[dom] = rel

    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    domains = [d for d, _ in ranked][: max(0, int(limit))]
    return domains


async def cmd_plan(args):
    """Create a dive plan without executing."""
    planner = DivePlanner()

    try:
        print(f"\n{'='*60}")
        print(f"SUBMARINE DIVE PLAN")
        print(f"{'='*60}")
        print(f"Query: {args.query}")
        print(f"Max domains: {args.max_domains}")
        print(f"Archive: {args.archive}")
        print()

        plan = await planner.create_plan(
            args.query,
            max_domains=args.max_domains,
            max_pages_per_domain=args.max_pages,
            cc_archives=_parse_csv(args.archive) if args.archive else None,
            filter_status=args.status,
            filter_mime=args.mime,
            filter_languages=args.language,
            from_ts=args.from_ts,
            to_ts=args.to_ts,
            domain_allowlist=(
                _load_torpedo_news_domains(args.jurisdiction, min_reliability=args.min_reliability)
                if args.news
                else None
            ),
            tld_include=_parse_csv(args.tld_include) or None,
            tld_exclude=_parse_csv(args.tld_exclude) or None,
            url_contains=args.keyword,
        )

        print(f"\n{'='*60}")
        print(f"PLAN SUMMARY")
        print(f"{'='*60}")
        print(f"Query type: {plan.query_type}")
        print(f"Domains found: {plan.total_domains}")
        print(f"Pages to fetch: {plan.total_pages}")
        print(f"Estimated time: {plan.estimated_time_seconds:.1f}s ({plan.estimated_time_seconds/60:.1f} min)")
        print(f"SONAR indices used: {len(plan.sonar_indices_used)}")
        print()

        if plan.targets:
            print("TOP TARGETS:")
            for i, t in enumerate(plan.targets[:20], 1):
                print(f"  {i:2}. [{t.priority}] {t.domain}: {t.estimated_pages} pages (from {t.source})")

        # Compare to brute force
        brute = await planner.estimate_brute_force()
        brute_hours = brute["brute_force_estimate"]["total_time_hours"]
        speedup = brute_hours * 3600 / max(plan.estimated_time_seconds, 1)

        print(f"\n{'='*60}")
        print(f"VS BRUTE FORCE")
        print(f"{'='*60}")
        print(f"Brute force: ~{brute_hours:.1f} hours ({brute_hours*60:.0f} minutes)")
        print(f"SUBMARINE: ~{plan.estimated_time_seconds/60:.1f} minutes")
        print(f"SPEEDUP: {speedup:.0f}x faster")

        # Save plan
        if args.output:
            plan.save(args.output)
            print(f"\nPlan saved to: {args.output}")
        else:
            # Default output path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output = f"/data/SUBMARINE/plans/{args.query.replace(' ', '_')[:30]}_{timestamp}.json"
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            plan.save(output)
            print(f"\nPlan saved to: {output}")

    finally:
        await planner.close()


async def cmd_search(args):
    """Execute a full search: plan + dive + extract."""
    planner = DivePlanner()
    diver = DeepDiver()

    try:
        print(f"\n{'='*60}")
        print(f"SUBMARINE SEARCH")
        print(f"{'='*60}")
        print(f"Query: {args.query}")
        print()

        # Step 1: Create plan
        print("[1/3] Creating dive plan...")
        plan = await planner.create_plan(
            args.query,
            max_domains=args.max_domains,
            max_pages_per_domain=args.max_pages,
            cc_archives=_parse_csv(args.archive) if args.archive else None,
            filter_status=args.status,
            filter_mime=args.mime,
            filter_languages=args.language,
            from_ts=args.from_ts,
            to_ts=args.to_ts,
            domain_allowlist=(
                _load_torpedo_news_domains(args.jurisdiction, min_reliability=args.min_reliability)
                if args.news
                else None
            ),
            tld_include=_parse_csv(args.tld_include) or None,
            tld_exclude=_parse_csv(args.tld_exclude) or None,
            url_contains=args.keyword,
        )

        print(f"      Found {plan.total_domains} domains, {plan.total_pages} pages")
        print(f"      Estimated time: {plan.estimated_time_seconds:.1f}s")

        if plan.total_pages == 0:
            print("\n[!] No pages to fetch. Try a different query.")
            return

        output = args.output or (
            f"/data/SUBMARINE/results/"
            f"{args.query.replace(' ', '_')[:30]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ndjson"
        )
        Path(output).parent.mkdir(parents=True, exist_ok=True)

        plan_output = args.plan_output or (
            output.replace(".ndjson", ".plan.json") if output.endswith(".ndjson") else (output + ".plan.json")
        )
        plan.save(plan_output, full=True)
        print(f"      Plan saved: {plan_output}")

        # Step 2: Execute dive
        print(f"\n[2/3] Executing dive ({plan.total_pages} pages)...")
        count = 0

        extractor = PACMANExtractor() if args.extract else None
        all_entities = []
        entity_counts = {}
        entities_output = output.replace(".ndjson", "_entities.ndjson") if args.extract else None

        out_f = open(output, "w", encoding="utf-8")
        ent_f = open(entities_output, "w", encoding="utf-8") if entities_output else None

        try:
            async for result in diver.execute_plan(plan, checkpoint_path=Path(plan_output)):
                count += 1
                out_f.write(json.dumps(result.to_dict()) + "\n")

                if count <= 10 or count % 50 == 0:
                    content_len = len(result.content) if result.content else 0
                    print(f"      [{count}] {result.url[:60]}... ({content_len} bytes)")

                if extractor and result.content:
                    extraction = extractor.extract(result.content, url=result.url, domain=result.domain)
                    for e in extraction.entities:
                        all_entities.append(e)
                        entity_counts[e.entity_type] = entity_counts.get(e.entity_type, 0) + 1
                        if ent_f:
                            ent_f.write(json.dumps({
                                "value": e.value,
                                "type": e.entity_type,
                                "confidence": e.confidence,
                                "source": e.source,
                                "url": result.url,
                            }) + "\n")

                if args.extract and count % 50 == 0:
                    print(f"      Extracted entities from {count} pages...")
        finally:
            try:
                out_f.close()
            except Exception:
                pass
            if ent_f:
                try:
                    ent_f.close()
                except Exception:
                    pass

        print(f"      Fetched {count} pages")

        # Step 3: Extract (if enabled)
        if args.extract:
            print(f"\n[3/3] Extracting entities...")
            print(f"      Extracted {len(all_entities)} entities")
            print(f"      By type: {entity_counts}")
            if entities_output:
                print(f"      Entities saved: {entities_output}")
        else:
            print(f"\n[3/3] Extraction skipped (use --extract to enable)")

        print(f"\n{'='*60}")
        print(f"SEARCH COMPLETE")
        print(f"{'='*60}")
        print(f"Pages fetched: {count}")
        print(f"Results saved: {output}")
        print(f"Plan file: {plan_output}")

    finally:
        await planner.close()


async def cmd_resume(args):
    """Resume an interrupted search from a plan file."""
    plan = DivePlan.load(args.plan_file)
    diver = DeepDiver()

    print(f"\n{'='*60}")
    print(f"RESUMING DIVE")
    print(f"{'='*60}")
    print(f"Plan: {args.plan_file}")
    print(f"Completed: {len(plan.completed_domains)} domains")
    print(f"Remaining: {plan.total_domains - len(plan.completed_domains)} domains")

    if not diver.available:
        print("\n[!] ccwarc binary not available; cannot resume.")
        return

    output = args.output or (
        str(Path(args.plan_file).with_suffix("")) + f".resume_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ndjson"
    )
    Path(output).parent.mkdir(parents=True, exist_ok=True)

    extractor = PACMANExtractor() if args.extract else None
    entities_output = output.replace(".ndjson", "_entities.ndjson") if args.extract else None

    count = 0
    out_f = open(output, "a", encoding="utf-8")
    ent_f = open(entities_output, "a", encoding="utf-8") if entities_output else None

    try:
        async for result in diver.execute_plan(plan, checkpoint_path=Path(args.plan_file)):
            count += 1
            out_f.write(json.dumps(result.to_dict()) + "\n")

            if count <= 10 or count % 50 == 0:
                content_len = len(result.content) if result.content else 0
                print(f"      [{count}] {result.url[:60]}... ({content_len} bytes)")

            if extractor and result.content:
                extraction = extractor.extract(result.content, url=result.url, domain=result.domain)
                for e in extraction.entities:
                    if ent_f:
                        ent_f.write(json.dumps({
                            "value": e.value,
                            "type": e.entity_type,
                            "confidence": e.confidence,
                            "source": e.source,
                            "url": result.url,
                        }) + "\n")
    finally:
        try:
            out_f.close()
        except Exception:
            pass
        if ent_f:
            try:
                ent_f.close()
            except Exception:
                pass

    print(f"\nResumed pages fetched: {count}")
    print(f"Results saved: {output}")
    if entities_output:
        print(f"Entities saved: {entities_output}")


async def cmd_sonar(args):
    """Test SONAR index scanning."""
    sonar = Sonar()

    try:
        print(f"\n{'='*60}")
        print(f"SONAR INDEX SCAN")
        print(f"{'='*60}")
        print(f"Query: {args.query}")
        print()

        result = await sonar.scan_all(args.query, limit=args.limit)

        print(f"Type detected: {sonar._detect_query_type(args.query)}")
        print(f"Domains found: {len(result.domains)}")
        print(f"URLs found: {len(result.urls)}")
        print(f"Total hits: {result.total_hits}")
        print(f"Indices scanned: {result.indices_scanned}")

        if result.domains:
            print(f"\nSample domains:")
            for d in list(result.domains)[:20]:
                print(f"  - {d}")

    finally:
        await sonar.close()


async def cmd_periscope(args):
    """Test PERISCOPE CC Index lookup."""
    periscope = Periscope(archive=args.archive)

    try:
        print(f"\n{'='*60}")
        print(f"PERISCOPE CC INDEX LOOKUP")
        print(f"{'='*60}")
        print(f"Domain: {args.domain}")
        print(f"Archive: {args.archive}")
        print()

        records = await periscope.lookup_domain(args.domain, limit=args.limit)
        estimate = periscope.estimate_fetch_size(records)

        print(f"Records found: {len(records)}")
        print(f"Total size: {estimate['total_mb']:.2f} MB")
        print(f"Unique WARCs: {estimate['unique_warc_files']}")
        print(f"Est. fetch time: {estimate['est_minutes']:.1f} min")

        if records:
            print(f"\nSample records:")
            for r in records[:10]:
                print(f"  - {r.url[:70]}...")

    finally:
        await periscope.close()


def main():
    parser = argparse.ArgumentParser(
        description="SUBMARINE - Smart Archive Search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # plan command
    plan_parser = subparsers.add_parser("plan", help="Create a dive plan")
    plan_parser.add_argument("query", help="Search query (phone, email, name, domain)")
    plan_parser.add_argument("--max-domains", type=int, default=100, help="Max domains to include")
    plan_parser.add_argument("--max-pages", type=int, default=100, help="Max pages per domain")
    plan_parser.add_argument("--archive", default="CC-MAIN-2025-51", help="CC archive to search")
    plan_parser.add_argument("--status", type=int, default=200, help="HTTP status filter (default 200)")
    plan_parser.add_argument("--mime", help="MIME filter (e.g., text/html, application/pdf, pdf)")
    plan_parser.add_argument("--language", help="Language filter (e.g., eng)")
    plan_parser.add_argument("--from", dest="from_ts", help="From timestamp/date (YYYYMMDDhhmmss or YYYY-MM-DD)")
    plan_parser.add_argument("--to", dest="to_ts", help="To timestamp/date (YYYYMMDDhhmmss or YYYY-MM-DD)")
    plan_parser.add_argument("--keyword", help="URL-contains keyword hint (used for CC wildcard matching)")
    plan_parser.add_argument("--news", action="store_true", help="Restrict domains to TORPEDO news sources")
    plan_parser.add_argument("--jurisdiction", help="Jurisdiction code (e.g., US, GB/UK) for --news")
    plan_parser.add_argument("--min-reliability", type=float, default=0.0, help="Minimum source reliability for --news")
    plan_parser.add_argument("--tld-include", help="Comma-separated TLD suffixes to include (e.g., gov,co.uk)")
    plan_parser.add_argument("--tld-exclude", help="Comma-separated TLD suffixes to exclude")
    plan_parser.add_argument("--output", "-o", help="Output file for plan")

    # search command
    search_parser = subparsers.add_parser("search", help="Execute a full search")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--max-domains", type=int, default=50, help="Max domains")
    search_parser.add_argument("--max-pages", type=int, default=50, help="Max pages per domain")
    search_parser.add_argument("--archive", default="", help="CC archives to search (comma-separated; default planner archive)")
    search_parser.add_argument("--status", type=int, default=200, help="HTTP status filter (default 200)")
    search_parser.add_argument("--mime", help="MIME filter (e.g., text/html, application/pdf, pdf)")
    search_parser.add_argument("--language", help="Language filter (e.g., eng)")
    search_parser.add_argument("--from", dest="from_ts", help="From timestamp/date (YYYYMMDDhhmmss or YYYY-MM-DD)")
    search_parser.add_argument("--to", dest="to_ts", help="To timestamp/date (YYYYMMDDhhmmss or YYYY-MM-DD)")
    search_parser.add_argument("--keyword", help="URL-contains keyword hint (used for CC wildcard matching)")
    search_parser.add_argument("--news", action="store_true", help="Restrict domains to TORPEDO news sources")
    search_parser.add_argument("--jurisdiction", help="Jurisdiction code (e.g., US, GB/UK) for --news")
    search_parser.add_argument("--min-reliability", type=float, default=0.0, help="Minimum source reliability for --news")
    search_parser.add_argument("--tld-include", help="Comma-separated TLD suffixes to include (e.g., gov,co.uk)")
    search_parser.add_argument("--tld-exclude", help="Comma-separated TLD suffixes to exclude")
    search_parser.add_argument("--extract", action="store_true", help="Enable entity extraction")
    search_parser.add_argument("--plan-output", help="Output file for plan checkpointing (default derived from output path)")
    search_parser.add_argument("--output", "-o", help="Output file")

    # resume command
    resume_parser = subparsers.add_parser("resume", help="Resume interrupted search")
    resume_parser.add_argument("plan_file", help="Path to plan JSON file")
    resume_parser.add_argument("--output", "-o", help="Output NDJSON file (appends)")
    resume_parser.add_argument("--extract", action="store_true", help="Enable entity extraction while resuming")

    # sonar command (testing)
    sonar_parser = subparsers.add_parser("sonar", help="Test SONAR index scanning")
    sonar_parser.add_argument("query", help="Search query")
    sonar_parser.add_argument("--limit", type=int, default=1000, help="Max results")

    # periscope command (testing)
    periscope_parser = subparsers.add_parser("periscope", help="Test PERISCOPE CC lookup")
    periscope_parser.add_argument("domain", help="Domain to lookup")
    periscope_parser.add_argument("--archive", default="CC-MAIN-2025-51", help="CC archive")
    periscope_parser.add_argument("--limit", type=int, default=100, help="Max records")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Route to command
    if args.command == "plan":
        asyncio.run(cmd_plan(args))
    elif args.command == "search":
        asyncio.run(cmd_search(args))
    elif args.command == "resume":
        asyncio.run(cmd_resume(args))
    elif args.command == "sonar":
        asyncio.run(cmd_sonar(args))
    elif args.command == "periscope":
        asyncio.run(cmd_periscope(args))


if __name__ == "__main__":
    main()
