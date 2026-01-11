#!/usr/bin/env python3
"""
UK Company Due Diligence - Complete End-to-End Example

This demonstrates the FULL FLOW using the template: operator:

1. template:company_dd:UK :#TescoPlc
   → Loads UK jurisdiction template + Company DD genre
   → Creates 12 watchers for each section
   → Executes initial queries in PARALLEL

2. Automatic iteration loop runs until:
   → 80% sections filled (sufficient)
   → OR max_iterations (10) reached

3. Results grouped by section with sources

USAGE:
    cd /Users/attic/01. DRILL_SEARCH/drill-search-app/BACKEND/modules/SASTRE
    python examples/uk_company_dd.py "Tesco PLC"
    python examples/uk_company_dd.py "Barclays Bank"
"""

import asyncio
import sys
import json
from pathlib import Path

# Add paths
SASTRE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = SASTRE_DIR.parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SASTRE_DIR))


async def run_uk_company_dd(company_name: str):
    """
    Execute a full UK Company DD using the template operator.

    Args:
        company_name: Name of the UK company to investigate
    """
    from executor import UnifiedExecutor

    print("=" * 70)
    print(f"UK COMPANY DUE DILIGENCE: {company_name}")
    print("=" * 70)

    # Create executor
    executor = UnifiedExecutor()

    # Build template query
    # Format: template:genre:jurisdiction :#entity_name
    entity_tag = company_name.replace(" ", "_").replace(".", "")
    query = f"template:company_dd:UK :#{entity_tag}"

    print(f"\n[QUERY] {query}\n")

    # Execute template-driven investigation
    result = await executor.execute(query, project_id="uk_dd_example")

    # Check for errors
    if "error" in result:
        print(f"[ERROR] {result['error']}")
        if "traceback" in result:
            print(result["traceback"])
        return result

    # Display template context
    print("\n[TEMPLATE LOADED]")
    print(f"  Genre: {result.get('genre')}")
    print(f"  Jurisdiction: {result.get('jurisdiction')}")
    print(f"  Entity: {result.get('entity')}")
    print(f"  Template Mode: {result.get('is_template_mode')}")

    # Display sections
    sections = result.get("sections", [])
    print(f"\n[SECTIONS] ({len(sections)} total)")
    for i, section in enumerate(sections, 1):
        print(f"  {i:2}. {section}")

    # Display watchers created
    watchers = result.get("watchers_created", [])
    print(f"\n[WATCHERS CREATED] ({len(watchers)} total)")
    for watcher in watchers[:5]:
        print(f"  • {watcher}")
    if len(watchers) > 5:
        print(f"  ... and {len(watchers) - 5} more")

    # Display initial queries executed
    initial_results = result.get("initial_results", [])
    print(f"\n[INITIAL QUERIES] ({len(initial_results)} executed in parallel)")

    for ir in initial_results:
        action = ir.get("action", "unknown")
        if "error" in ir:
            print(f"  ✗ {action}: {ir['error']}")
        else:
            inner = ir.get("result", {})
            if "error" in inner:
                print(f"  ⚠ {action}: {inner.get('error', 'unknown error')}")
            else:
                count = len(inner.get("results", inner.get("profile", {})))
                executor_type = inner.get("_executor", "unknown")
                print(f"  ✓ {action}: {count} results ({executor_type})")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Sections defined: {result.get('section_count', 0)}")
    print(f"  Watchers created: {len(watchers)}")
    print(f"  Queries executed: {result.get('initial_queries_executed', 0)}")
    print(f"  Template context:")
    tc = result.get("template_context", {})
    print(f"    Genre template: {'✓' if tc.get('genre_template') else '✗'}")
    print(f"    Jurisdiction template: {'✓' if tc.get('jurisdiction_template') else '✗'}")
    print(f"    Writing style: {'✓' if tc.get('writing_style') else '✗'}")

    return result


async def run_parallel_example():
    """
    Demonstrate parallel execution with multiple operators.
    """
    from executor import UnifiedExecutor

    print("\n" + "=" * 70)
    print("PARALLEL EXECUTION EXAMPLE")
    print("=" * 70)

    executor = UnifiedExecutor()

    # This query uses parallel syntax { a, b, c }
    # After the macros.py fix, these execute truly in parallel
    query = '{ cuk: Tesco PLC, cuk: Sainsbury }  => +#uk_retailers'

    print(f"\n[QUERY] {query}\n")
    print("(Both registry lookups execute concurrently using asyncio.gather)")

    result = await executor.execute(query, project_id="parallel_example")

    if "error" in result:
        print(f"[ERROR] {result['error']}")
    else:
        print(f"[RESULT] {json.dumps(result, indent=2, default=str)[:500]}...")

    return result


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        company_name = " ".join(sys.argv[1:])
    else:
        company_name = "Tesco PLC"

    print("""
╔═══════════════════════════════════════════════════════════════════════╗
║                    SASTRE UK COMPANY DD EXAMPLE                       ║
║                                                                       ║
║  This demonstrates the end-to-end flow with:                          ║
║  • template: operator (auto-loads sections + watchers)                ║
║  • Parallel execution (asyncio.gather for { } syntax)                 ║
║  • Iteration loop (max_iterations with sufficiency check)             ║
║  • Cascade callbacks (on_slot_fed with full context)                  ║
╚═══════════════════════════════════════════════════════════════════════╝
""")

    asyncio.run(run_uk_company_dd(company_name))


if __name__ == "__main__":
    main()
