#!/usr/bin/env python3
"""
FORENSIC SEARCH - Example Usage
===============================
Demonstrates all features of the forensic search system.
"""

import json
import asyncio
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from forensic_api import ForensicAPI, build_queries, score_result, expand_role
from query_refiner import DynamicQuestioner, MandatoryQueryBuilder


def example_1_basic_query_building():
    """Example 1: Build queries for a common name (requires expansion)"""
    print("\n" + "="*60)
    print("EXAMPLE 1: Basic Query Building (Common Name)")
    print("="*60)
    
    api = ForensicAPI()
    
    result = api.build_queries(
        target="John Smith",
        company="Acme Corporation",
        role="Director"
    )
    
    print(f"\nTarget: {result['meta']['target']}")
    print(f"Total queries generated: {result['statistics']['total_queries']}")
    print(f"\nTier distribution:")
    for tier, count in result['statistics']['tier_distribution'].items():
        print(f"  {tier}: {count}")
    
    print(f"\nName variations generated:")
    for var in result['refinement']['name_variations'][:5]:
        print(f"  • {var}")
    
    print(f"\nNegative fingerprints (to exclude false positives):")
    for fp in result['refinement']['negative_fingerprints'][:5]:
        print(f"  • -{fp}")
    
    print(f"\nSample MANDATORY queries:")
    
    # Show filetype queries (MANDATORY)
    print("\n  filetype queries:")
    for q in result['queries_by_tier'].get('tier4_filetype', [])[:2]:
        print(f"    {q}")
    
    # Show inurl queries (MANDATORY)
    print("\n  inurl queries:")
    for q in result['queries_by_tier'].get('tier5_inurl', [])[:2]:
        print(f"    {q}")
    
    # Show temporal queries (MANDATORY)
    print("\n  temporal queries:")
    for q in result['queries_by_tier'].get('tier6_temporal', [])[:2]:
        print(f"    {q}")
    
    # Show archive queries (MANDATORY)
    print("\n  archive queries:")
    for q in result['queries_by_tier'].get('tier7_archive', [])[:2]:
        print(f"    {q}")


def example_2_unique_name():
    """Example 2: Build queries for a unique term (minimal expansion)"""
    print("\n" + "="*60)
    print("EXAMPLE 2: Unique Target (Minimal Expansion Needed)")
    print("="*60)
    
    api = ForensicAPI()
    
    # Unique company name - should NOT over-expand
    result = api.build_queries(
        target="Xylophigous Holdings",
        pivot="Project Nightshade"
    )
    
    print(f"\nTarget: {result['meta']['target']}")
    print(f"Total queries: {result['statistics']['total_queries']}")
    
    print(f"\n⚠️  Note: Unique terms should be used ALONE or with minimal context")
    print(f"    Every added word is an exclusion risk!")
    
    print(f"\nBase queries (using unique anchor alone):")
    for q in result['queries_by_tier'].get('tier0_net', []):
        print(f"  {q}")


def example_3_forensic_scoring():
    """Example 3: Score results with forensic criteria"""
    print("\n" + "="*60)
    print("EXAMPLE 3: Forensic Scoring (Depth Priority)")
    print("="*60)
    
    api = ForensicAPI()
    
    # Test URLs with different characteristics
    test_cases = [
        ("http://obscure-forum.net/thread/12345", "forum", "page_4_plus"),
        ("http://small-company.io/staff-directory.pdf", "pdf", "artifact_only"),
        ("https://www.linkedin.com/in/johnsmith", "linkedin", "page_1"),
        ("https://en.wikipedia.org/wiki/John_Smith", "wikipedia", "page_1"),
        ("http://local-news.org/2015/article", "local_news", "page_3"),
        ("http://web.archive.org/web/2012/company-site/staff.html", "directory", "archive"),
    ]
    
    print(f"\nScoring results (higher = better forensic value):\n")
    print(f"{'URL':<55} {'Score':>6} {'Recommendation'}")
    print("-" * 90)
    
    for url, source_type, position in test_cases:
        result = api.score_result(url, source_type, position)
        score = result['forensic_score']
        rec = result['recommendation'].split(" - ")[0]
        print(f"{url[:54]:<55} {score:>6} {rec}")
    
    print(f"\n⚠️  Key insight: Page 1 results are PENALIZED (-20)")
    print(f"    Page 4+ results get BONUS (+20)")
    print(f"    PDFs and forums score higher than Wikipedia/LinkedIn")


def example_4_role_expansion():
    """Example 4: Expand roles for OR-stacking"""
    print("\n" + "="*60)
    print("EXAMPLE 4: Role OR-Expansion")
    print("="*60)
    
    api = ForensicAPI()
    
    roles = ["director", "ceo", "engineer", "consultant", "manager"]
    
    for role in roles:
        variations = api.expand_role(role)
        or_clause = " OR ".join(f'"{v}"' for v in variations[:5])
        
        print(f"\n{role.upper()}:")
        print(f"  Variations: {', '.join(variations[:5])}")
        print(f"  OR clause: ({or_clause})")
    
    print(f"\n⚠️  Use OR-stacking when the role term is common")
    print(f"    This covers the 'semantic neighborhood'")


def example_5_negative_fingerprinting():
    """Example 5: Identify negative fingerprints"""
    print("\n" + "="*60)
    print("EXAMPLE 5: Negative Fingerprinting")
    print("="*60)
    
    questioner = DynamicQuestioner()
    
    # Terms that have homonym conflicts
    test_anchors = [
        "Apple",
        "Amazon",
        "Jaguar",
        "Mercury",
        "Python",
        "John Smith",  # Common name
    ]
    
    for anchor in test_anchors:
        fingerprints = questioner.identify_negative_fingerprints(anchor)
        
        print(f"\n{anchor}:")
        if fingerprints:
            exclusion = " ".join(f"-{fp}" for fp in fingerprints[:5])
            print(f"  Exclude: {', '.join(fingerprints[:5])}")
            print(f"  Query:   \"{anchor}\" {exclusion}")
        else:
            print(f"  No specific exclusions identified")
    
    print(f"\n⚠️  Negative fingerprints remove false positives WITHOUT")
    print(f"    poisoning the main query. Use as a SEPARATE tier.")


def example_6_dynamic_questioning():
    """Example 6: See all questions applied to a query"""
    print("\n" + "="*60)
    print("EXAMPLE 6: Dynamic Questioning System")
    print("="*60)
    
    questioner = DynamicQuestioner()
    
    refinement = questioner.refine_query(
        anchor="Jane Doe",
        pivot="M&A specialist",
        company="Global Partners",
        location="London",
        role="Managing Director"
    )
    
    print(f"\nQuestions applied to refine the query:\n")
    for i, q in enumerate(refinement.questions_applied, 1):
        print(f"  {i}. {q}")
    
    print(f"\nResults of questioning:")
    print(f"  Name variations: {len(refinement.or_variations)}")
    print(f"  Negative fingerprints: {len(refinement.negative_fingerprints)}")
    print(f"  Context terms: {len(refinement.context_terms)}")
    print(f"  Expanded queries: {len(refinement.expanded_queries)}")


def example_7_url_validation():
    """Example 7: Validate URLs for authenticity"""
    print("\n" + "="*60)
    print("EXAMPLE 7: URL Authenticity Validation")
    print("="*60)
    
    api = ForensicAPI()
    
    # Mix of valid and potentially hallucinated URLs
    test_urls = [
        "https://www.example.com/staff/john-smith",
        "http://obscure-site.io/directory.pdf",
        "https://invalid----domain.com/page",
        "http://example123456789012345.com/too-many-numbers",
        "https://fake-domain-placeholder.test/page",
        "http://web.archive.org/web/2015/site.com",
    ]
    
    print(f"\nValidating URLs:\n")
    for url in test_urls:
        result = api.validate_url(url)
        status = "✓ VALID" if result['is_valid'] else "✗ INVALID"
        print(f"  {status}: {url[:50]}")
        if not result['is_valid']:
            print(f"           Reason: {result['reason']}")
    
    print(f"\n⚠️  Invalid URLs receive SEVERE PENALTY (score = 0)")
    print(f"    This prevents hallucinated results from polluting output")


def example_8_export():
    """Example 8: Export queries to file"""
    print("\n" + "="*60)
    print("EXAMPLE 8: Export to JSON")
    print("="*60)
    
    api = ForensicAPI()
    
    result = api.build_queries(
        target="Test Target",
        company="Test Company",
        role="Manager"
    )
    
    # Export to JSON
    json_file = api.export_queries(result, format="json")
    print(f"\n  Exported JSON: {json_file}")
    
    # Export to TXT
    txt_file = api.export_queries(result, format="txt")
    print(f"  Exported TXT: {txt_file}")
    
    print(f"\n  Files contain all queries organized by tier")


async def example_9_ai_investigation():
    """Example 9: AI-powered investigation (requires API key)"""
    print("\n" + "="*60)
    print("EXAMPLE 9: AI-Powered Investigation")
    print("="*60)
    
    if not os.getenv("GOOGLE_API_KEY"):
        print(f"\n  ⚠️  GOOGLE_API_KEY not set")
        print(f"     Set environment variable to enable AI features")
        print(f"     Rule-based queries (examples 1-8) still work!")
        return
    
    api = ForensicAPI()
    
    print(f"\n  Running AI investigation...")
    
    try:
        result = await api.investigate(
            target="John Smith",
            context="Director at Acme Corp, involved in 2019 merger"
        )
        
        print(f"\n  ✓ AI investigation complete")
        print(f"  Generated {len(result.get('queries', []))} queries")
        
        if result.get('queries'):
            print(f"\n  Sample AI-generated queries:")
            for q in result['queries'][:3]:
                print(f"    [{q.get('tier', 'N/A')}] {q.get('q', '')[:60]}...")
    
    except Exception as e:
        print(f"\n  ✗ Error: {e}")


def main():
    """Run all examples"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║       FORENSIC SEARCH SYSTEM - EXAMPLES                      ║
║                                                              ║
║   "We seek the Witness buried on page 47"                    ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Run examples
    example_1_basic_query_building()
    example_2_unique_name()
    example_3_forensic_scoring()
    example_4_role_expansion()
    example_5_negative_fingerprinting()
    example_6_dynamic_questioning()
    example_7_url_validation()
    example_8_export()
    
    # AI example (async)
    asyncio.run(example_9_ai_investigation())
    
    print("\n" + "="*60)
    print("ALL EXAMPLES COMPLETE")
    print("="*60)
    print("\nKey takeaways:")
    print("  1. Page 1 results are PENALIZED in forensic scoring")
    print("  2. filetype:pdf, inurl:, before:/after: are MANDATORY")
    print("  3. Negative fingerprinting prevents false positives")
    print("  4. Unique terms should be used ALONE (don't over-expand)")
    print("  5. Common names need OR-stacking for semantic coverage")
    print("  6. Invalid/hallucinated URLs get SEVERE penalty (score=0)")
    print()


if __name__ == "__main__":
    main()