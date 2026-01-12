#!/usr/bin/env python3
"""
Generate IO Matrix chains from mined methodology patterns.

Each successful mined pattern becomes a chain entry:
- Input codes (what you have)
- Output codes (what you get)
- Module to execute
- Source/aggregator
- Jurisdiction
- Success rate from historical data
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional

MINED_DIR = Path(__file__).parent
MATRIX_DIR = MINED_DIR.parent


def load_json(filename: str) -> Dict:
    """Load JSON file."""
    path = MINED_DIR / filename
    if path.exists():
        return json.loads(path.read_text())
    return {}


def load_mappings() -> Dict:
    """Load methodology mappings."""
    return load_json("methodology_mappings.json")


def load_methodology() -> List[Dict]:
    """Load mined methodology patterns."""
    data = load_json("mined_methodology.json")
    return data.get("patterns", [])


def normalize_method(method: str, mappings: Dict) -> str:
    """Normalize method variants to canonical names."""
    methods_map = mappings.get("methods_to_modules", {})

    # Direct match
    if method in methods_map:
        return method

    # Fuzzy matching for variants
    variants = {
        # Court/litigation variants
        "court_records_search": "court_search",
        "civil_litigation_search": "court_search",
        "criminal_records_search": "court_search",
        "case_law_analysis": "court_search",
        "arbitration_records": "court_search",

        # Corporate registry variants
        "beneficial_ownership_search": "corporate_registry_search",
        "beneficial_ownership_analysis": "corporate_registry_search",
        "ownership_structure_search": "corporate_registry_search",
        "company_incorporation_search": "corporate_registry_search",
        "cross_border_corporate_search": "corporate_registry_search",
        "corporate_database_search": "corporate_registry_search",
        "corporate_directory_search": "corporate_registry_search",
        "corporate_aggregator_search": "corporate_registry_search",

        # Financial variants
        "financial_records_search": "financial_filings_analysis",
        "financial_analysis": "financial_filings_analysis",
        "annual_report_analysis": "financial_filings_analysis",
        "stock_exchange_filings": "financial_filings_analysis",
        "sec_filings_search": "financial_filings_analysis",

        # Property variants
        "property_records_search": "land_registry_search",
        "property_search": "land_registry_search",
        "real_estate_search": "land_registry_search",

        # Social media variants
        "linkedin_search": "social_media_monitoring",
        "linkedin_profiling": "social_media_monitoring",
        "social_media_search": "social_media_monitoring",
        "social_media_analysis": "social_media_monitoring",
        "social_media_osint": "social_media_monitoring",

        # Domain variants
        "domain_search": "website_analysis",
        "domain_analysis": "website_analysis",
        "domain_registration_lookup": "domain_registration_search",
        "whois_analysis": "domain_registration_search",
        "web_archive_analysis": "website_analysis",

        # Sanctions variants
        "pep_screening": "sanctions_screening",
        "watchlist_screening": "sanctions_screening",
        "compliance_screening": "sanctions_screening",

        # OSINT variants
        "data_breach_analysis": "osint",
        "offshore_leaks_search": "osint",
        "dark_web_monitoring": "osint",

        # Regulatory variants
        "regulatory_filing_analysis": "regulatory_search",
        "regulatory_records_search": "regulatory_search",
        "regulatory_monitoring": "regulatory_search",

        # Insolvency variants
        "insolvency_search": "bankruptcy_search",
        "insolvency_registry_search": "bankruptcy_search",
    }

    return variants.get(method, method)


def get_input_codes_for_goal(goal: str, mappings: Dict) -> List[int]:
    """Get input codes based on investigation goal."""
    goals = mappings.get("investigation_goals_to_codes", {})
    goal_info = goals.get(goal, {})

    # Default input codes by entity type
    default_inputs = {
        "trace_ubo": [13, 42],  # company_name
        "corporate_structure": [13, 42],
        "verify_identity": [7, 31],  # person_name
        "find_assets": [7, 13, 31, 42],  # person or company
        "litigation_history": [7, 13, 31, 42],
        "sanctions_check": [7, 13, 31, 42],
        "contact_discovery": [7, 13, 31, 42],
        "domain_intelligence": [6],  # domain
    }

    return default_inputs.get(goal, [13, 42])


def get_output_codes_for_method(method: str, goal: str, mappings: Dict) -> List[int]:
    """Get output codes based on method and goal."""
    goals = mappings.get("investigation_goals_to_codes", {})
    goal_info = goals.get(goal, {})

    if goal_info.get("output_codes"):
        return goal_info["output_codes"]

    # Method-specific outputs
    method_outputs = {
        "corporate_registry_search": [42, 43, 47, 48, 49, 50, 59, 67, 72, 73],
        "court_search": [17],
        "land_registry_search": [20, 106],
        "social_media_monitoring": [38, 160, 188],
        "website_analysis": [6, 46, 191, 200, 201],
        "domain_registration_search": [191, 200, 201],
        "sanctions_screening": [],
        "financial_filings_analysis": [42, 43, 48, 49, 50],
        "osint": [1, 2, 3, 32, 33, 38],
        "regulatory_search": [42, 43, 58],
        "bankruptcy_search": [17, 42],
    }

    return method_outputs.get(method, [])


def infer_goal_from_description(description: str) -> str:
    """Infer investigation goal from pattern description."""
    desc_lower = description.lower()

    if any(kw in desc_lower for kw in ["beneficial", "owner", "shareholder", "ownership", "ubo"]):
        return "trace_ubo"
    elif any(kw in desc_lower for kw in ["property", "land", "real estate", "asset"]):
        return "find_assets"
    elif any(kw in desc_lower for kw in ["court", "litigation", "lawsuit", "legal"]):
        return "litigation_history"
    elif any(kw in desc_lower for kw in ["sanction", "pep", "watchlist"]):
        return "sanctions_check"
    elif any(kw in desc_lower for kw in ["identity", "background", "biographical"]):
        return "verify_identity"
    elif any(kw in desc_lower for kw in ["domain", "website", "backlink"]):
        return "domain_intelligence"
    else:
        return "corporate_structure"


def generate_chain_id(method: str, jurisdiction: str, source: str) -> str:
    """Generate unique chain ID."""
    # Clean source name
    source_clean = source.replace(" ", "_").replace(".", "_")[:30]
    return f"MINED_{method.upper()}_{jurisdiction}_{source_clean}".upper()


def generate_chains() -> List[Dict]:
    """Generate chain definitions from mined patterns."""
    mappings = load_mappings()
    patterns = load_methodology()

    chains = []
    seen_ids = set()

    # Group patterns by jurisdiction + method + source for aggregation
    grouped = defaultdict(list)
    for p in patterns:
        if not p.get("success"):
            continue

        method = normalize_method(p.get("method", "unknown"), mappings)
        jur = p.get("jurisdiction", "GLOBAL")
        source = p.get("source_used", "")

        if not source:
            continue

        key = (method, jur, source)
        grouped[key].append(p)

    for (method, jur, source), group in grouped.items():
        # Calculate success rate
        success_count = len(group)

        # Get module
        methods_map = mappings.get("methods_to_modules", {})
        method_info = methods_map.get(method, {})
        module = method_info.get("module")

        # Skip non-automatable methods
        if method_info.get("automatable") == False:
            continue

        if not module:
            continue

        # Infer goal from first pattern's description
        goal = infer_goal_from_description(group[0].get("description", ""))

        # Get codes
        input_codes = get_input_codes_for_goal(goal, mappings)
        output_codes = get_output_codes_for_method(method, goal, mappings)

        if not output_codes:
            continue

        # Get friction
        friction = group[0].get("friction", "unknown")

        # Generate chain ID
        chain_id = generate_chain_id(method, jur, source)
        if chain_id in seen_ids:
            continue
        seen_ids.add(chain_id)

        # Get aggregator
        sources_map = mappings.get("sources_to_aggregators", {})
        aggregator = sources_map.get(source, source)

        # Build chain
        chain = {
            "id": chain_id,
            "label": f"{method.replace('_', ' ').title()} via {source}",
            "requires_any": input_codes,
            "requires_all": [],
            "returns": output_codes,
            "friction": friction.title() if friction != "unknown" else "Open",
            "jurisdiction": jur,
            "category": goal,
            "mined": True,
            "success_count": success_count,
            "original_description": group[0].get("description", "")[:200],
            "chain_config": {
                "type": "single_step",
                "steps": [
                    {
                        "step": 1,
                        "action": method.upper(),
                        "input_fields": input_codes,
                        "output_fields": output_codes,
                        "description": group[0].get("description", "")[:150]
                    }
                ]
            },
            "resources": [
                {
                    "type": "module",
                    "import": f"BACKEND.modules.{module}",
                    "method": f"execute_{method}",
                    "description": f"Execute via {module} module"
                }
            ]
        }

        # Add API resource if we have aggregator
        if aggregator and aggregator != source:
            chain["resources"].append({
                "type": "api",
                "name": source,
                "url": f"https://{aggregator}/" if not aggregator.startswith("http") else aggregator,
                "jurisdiction": jur
            })

        chains.append(chain)

    return chains


def generate_manual_tasks() -> List[Dict]:
    """Generate task definitions for non-automatable methods."""
    mappings = load_mappings()
    patterns = load_methodology()

    tasks = []
    seen = set()

    for p in patterns:
        if not p.get("success"):
            continue

        method = p.get("method", "unknown")
        methods_map = mappings.get("methods_to_modules", {})
        method_info = methods_map.get(method, {})

        # Only include non-automatable methods
        if method_info.get("automatable") != False and method_info.get("module"):
            continue

        jur = p.get("jurisdiction", "GLOBAL")
        source = p.get("source_used", "")

        key = (method, jur)
        if key in seen:
            continue
        seen.add(key)

        task = {
            "id": f"TASK_{method.upper()}_{jur}",
            "type": "manual",
            "method": method,
            "jurisdiction": jur,
            "description": p.get("description", "")[:200],
            "source_example": source,
            "friction": p.get("friction", "restricted"),
            "requires_fieldwork": True,
            "note": "This method requires human intervention and cannot be automated"
        }
        tasks.append(task)

    return tasks


def main():
    """Generate and save chains."""
    print("Generating chains from mined methodology...")

    chains = generate_chains()
    print(f"Generated {len(chains)} automatable chains")

    tasks = generate_manual_tasks()
    print(f"Generated {len(tasks)} manual task definitions")

    # Save chains
    output = {
        "version": "1.0.0",
        "generated_from": "mined_methodology.json",
        "description": "IO Matrix chains derived from 6,126 mined investigation patterns",
        "automatable_chains": chains,
        "manual_tasks": tasks,
        "statistics": {
            "total_chains": len(chains),
            "total_manual_tasks": len(tasks),
            "jurisdictions": list(set(c["jurisdiction"] for c in chains)),
            "categories": list(set(c["category"] for c in chains)),
        }
    }

    output_path = MINED_DIR / "generated_chains.json"
    output_path.write_text(json.dumps(output, indent=2))
    print(f"Saved to {output_path}")

    # Print summary
    print("\n=== Summary ===")
    print(f"Chains by jurisdiction:")
    jur_counts = defaultdict(int)
    for c in chains:
        jur_counts[c["jurisdiction"]] += 1
    for jur, count in sorted(jur_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {jur}: {count}")

    print(f"\nChains by category:")
    cat_counts = defaultdict(int)
    for c in chains:
        cat_counts[c["category"]] += 1
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
