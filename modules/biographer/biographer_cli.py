#!/usr/bin/env python3
"""
BIOGRAPHER CLI - Person Profile Aggregator

Routes person searches to multiple specialists and aggregates results.

Usage:
    python biographer_cli.py person "John Smith"
    python biographer_cli.py person "John Smith" --json
    python biographer_cli.py person "John Smith" --sources eyed,corporella
    python biographer_cli.py person "John Smith" --output-nodes  # Output node graph

Operators routed here:
    p: <name>  →  biographer_cli person <name>

This CLI coordinates:
    - eyed_cli person <name>       → OSINT person search
    - corporella_cli person <name> → Corporate affiliations
    - socialite_cli person <name>  → Social media profiles

Node Architecture:
    Query Node: "p: John Smith"
        ├── [searched] → PRIMARY: "John Smith" (empty, populated by biographer_ai)
        ├── [found] → SECONDARY (a): "John Smith (a)" ← EYE-D
        ├── [found] → SECONDARY (b): "John Smith (b)" ← CORPORELLA
        └── [found] → SECONDARY (c): "John Smith (c)" ← SOCIALITE
"""

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor
import time

# OPTICS integration
try:
    from modules.optics import analyze_optics
    OPTICS_AVAILABLE = True
except ImportError:
    OPTICS_AVAILABLE = False
    analyze_optics = None

# Paths
MODULES_ROOT = Path(__file__).parent.parent

# Import node utilities
try:
    from .nodes import (
        create_biographer_node_set,
        create_secondary_person_node,
        get_suffix_for_source,
        BiographerNodeSet
    )
    from .verification import (
        consolidate_secondaries,
        consolidate_with_disambiguation,
        apply_consolidation,
    )
    from .watcher import (
        create_biographer_watcher,
        create_section_watchers,
        execute_watcher_scan,
        initialize_biographer_with_project_note,
        BiographerWatcher,
        WatcherFinding,
        save_watcher_state,
        PERSON_NOTE_HEADINGS,
    )
    from .context import (
        BiographerContext,
        WatcherContext,
        assemble_biographer_context,
        format_context_for_ai,
        get_biographer_context,
    )
    NODES_AVAILABLE = True
    CONTEXT_AVAILABLE = True
except ImportError:
    # Allow running standalone
    NODES_AVAILABLE = False
    CONTEXT_AVAILABLE = False

# Try to import socialite identifier for cross-platform username search
try:
    from socialite.identifier import SocialIdentifier, search_username_all_platforms
    SOCIALITE_IDENTIFIER_AVAILABLE = True
except ImportError:
    SOCIALITE_IDENTIFIER_AVAILABLE = False


def extract_usernames_from_results(results: List[Dict[str, Any]]) -> List[str]:
    """
    Extract all usernames found from source results.

    Looks for usernames in:
    - breaches[].username
    - social_profiles[].handle/username
    - accounts[].username
    - raw data username fields
    """
    usernames = set()

    for result in results:
        if result.get("status") != "success":
            continue

        data = result.get("results", {})
        if not data:
            continue

        # From breach records
        for breach in data.get("breaches", []):
            if breach.get("username"):
                usernames.add(breach["username"])

        # From social profiles
        for profile in data.get("social_profiles", []):
            if profile.get("username"):
                usernames.add(profile["username"])
            if profile.get("handle"):
                usernames.add(profile["handle"])

        # From accounts list
        for account in data.get("accounts", []):
            if account.get("username"):
                usernames.add(account["username"])

        # Direct username field
        if data.get("username"):
            usernames.add(data["username"])

        # From people records
        for person in data.get("people", []):
            if person.get("username"):
                usernames.add(person["username"])
            # Social handles often in arrays
            for profile in person.get("social_profiles", []):
                if profile.get("username"):
                    usernames.add(profile["username"])
                if profile.get("handle"):
                    usernames.add(profile["handle"])

    # Filter out obvious non-usernames (emails, etc.)
    filtered = []
    for u in usernames:
        if u and isinstance(u, str) and "@" not in u and len(u) >= 3:
            filtered.append(u)

    return filtered


# CLI paths for each source
# Note: Each CLI has a different interface, so we use a command_builder
SOURCE_CLIS = {
    "eyed": {
        "path": MODULES_ROOT / "eyed" / "eyed_cli.py",
        "description": "OSINT person search (email, phone, breaches, LinkedIn)",
        "suffix": "a",
        # eyed: direct query (auto-detects type)
        "build_args": lambda name: [name, "--json"]
    },
    "corporella": {
        "path": MODULES_ROOT / "corporella" / "corporella_cli.py",
        "description": "Corporate affiliations (officers, directors, shareholders)",
        "suffix": "b",
        # corporella: search command (searches companies associated with person)
        "build_args": lambda name: ["search", name, "--json"]
    },
    "socialite": {
        "path": MODULES_ROOT / "socialite" / "socialite_cli.py",
        "description": "Social media profiles (all platforms)",
        "suffix": "c",
        # socialite: unified person search across all platforms
        "build_args": lambda name: ["person", name, "--json", "--writeup"]
    },
}


def run_cli(source: str, name: str, timeout: int = 120) -> Dict[str, Any]:
    """Run a single source CLI and return results."""
    config = SOURCE_CLIS.get(source)
    if not config:
        return {"source": source, "error": f"Unknown source: {source}"}

    cli_path = config["path"]
    if not cli_path.exists():
        return {"source": source, "error": f"CLI not found: {cli_path}"}

    # Build command args using source-specific builder
    build_args = config.get("build_args")
    if build_args:
        args = build_args(name)
    else:
        # Fallback to old style
        args = [config.get("command", "search"), name, "--json"]

    try:
        result = subprocess.run(
            ["python3", str(cli_path)] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(MODULES_ROOT)
        )

        # Try to parse JSON from stdout
        stdout = result.stdout.strip()

        # For some CLIs, JSON may be at the end after warnings
        json_start = stdout.rfind('\n{')
        if json_start != -1:
            json_str = stdout[json_start+1:]
        elif stdout.startswith('{'):
            json_str = stdout
        else:
            json_str = None

        if result.returncode == 0 and json_str:
            try:
                data = json.loads(json_str)
                return {"source": source, "results": data, "status": "success"}
            except json.JSONDecodeError:
                return {"source": source, "output": result.stdout, "status": "success"}
        elif result.returncode == 0:
            return {"source": source, "output": result.stdout, "status": "success"}
        else:
            return {"source": source, "error": result.stderr or result.stdout or "CLI failed", "status": "error"}

    except subprocess.TimeoutExpired:
        return {"source": source, "error": f"Timeout after {timeout}s", "status": "timeout"}
    except Exception as e:
        return {"source": source, "error": str(e), "status": "error"}


def aggregate_results(results: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    """Aggregate results from all sources into a unified profile."""
    profile = {
        "name": name,
        "identifiers": {},
        "employment": [],
        "social_profiles": [],
        "corporate_roles": [],
        "breach_exposure": [],
        "sources_queried": [],
        "sources_with_data": [],
        "raw_results": {}
    }

    for result in results:
        source = result.get("source", "unknown")
        profile["sources_queried"].append(source)
        profile["raw_results"][source] = result

        if result.get("status") != "success":
            continue

        data = result.get("results", {})
        if not data:
            continue

        profile["sources_with_data"].append(source)

        # Extract from EYE-D results
        if source == "eyed":
            if isinstance(data, dict):
                # Identifiers
                if data.get("email"):
                    profile["identifiers"]["email"] = data["email"]
                if data.get("phone"):
                    profile["identifiers"]["phone"] = data["phone"]
                if data.get("linkedin"):
                    profile["identifiers"]["linkedin"] = data["linkedin"]

                # Breach exposure
                if data.get("breaches"):
                    profile["breach_exposure"].extend(data["breaches"])

                # Social profiles from EYE-D
                if data.get("social_profiles"):
                    profile["social_profiles"].extend(data["social_profiles"])

        # Extract from CORPORELLA results
        elif source == "corporella":
            if isinstance(data, dict):
                # Corporate roles
                if data.get("officers"):
                    for officer in data["officers"]:
                        profile["corporate_roles"].append({
                            "type": "officer",
                            "company": officer.get("company"),
                            "position": officer.get("position"),
                            "source": "corporella"
                        })
                if data.get("directors"):
                    for director in data["directors"]:
                        profile["corporate_roles"].append({
                            "type": "director",
                            "company": director.get("company"),
                            "position": director.get("position"),
                            "source": "corporella"
                        })
                if data.get("shareholders"):
                    for shareholder in data["shareholders"]:
                        profile["corporate_roles"].append({
                            "type": "shareholder",
                            "company": shareholder.get("company"),
                            "shares": shareholder.get("shares"),
                            "source": "corporella"
                        })

                # Employment history
                if data.get("employment"):
                    profile["employment"].extend(data["employment"])

        # Extract from SOCIALITE results
        elif source == "socialite":
            if isinstance(data, dict):
                if data.get("profiles"):
                    for p in data["profiles"]:
                        profile["social_profiles"].append({
                            "platform": p.get("platform"),
                            "handle": p.get("handle") or p.get("username"),
                            "url": p.get("url"),
                            "source": "socialite"
                        })

    # Calculate confidence
    profile["confidence"] = len(profile["sources_with_data"]) / len(profile["sources_queried"]) if profile["sources_queried"] else 0

    return profile


async def search_person(name: str, sources: Optional[List[str]] = None,
                        parallel: bool = True, timeout: int = 120,
                        output_nodes: bool = False,
                        project_id: Optional[str] = None,
                        # Disambiguation context (pre-populate from project)
                        jurisdiction: Optional[str] = None,
                        jurisdictions: Optional[List[str]] = None,
                        industry: Optional[str] = None,
                        related_companies: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Search for a person across all sources.

    Args:
        name: Person name to search
        sources: List of sources to query (default: all)
        parallel: Run searches in parallel
        timeout: Timeout per source in seconds
        output_nodes: Output node graph structure
        project_id: Project ID - auto-creates project note with template and watchers

    Returns:
        If output_nodes=False: Legacy profile dict
        If output_nodes=True: Node graph with query, primary, secondaries, project_note, watcher

    Project Note Integration (when project_id provided):
        1. Creates "Project Note" (default note for project)
        2. Loads person profile template into note (sections as headers)
        3. Creates watchers for each section header
        4. All BRUTE results scanned by Haiku
        5. Findings stream to project note under section headings
        6. biographer_ai makes ADD_VERIFIED/ADD_UNVERIFIED/REJECT decisions
    """
    if sources is None:
        sources = list(SOURCE_CLIS.keys())

    # Filter to valid sources
    sources = [s for s in sources if s in SOURCE_CLIS]

    if not sources:
        return {"error": "No valid sources specified"}

    start_time = time.time()
    raw_input = f"p: {name}"

    # Create node set if nodes mode
    node_set = None
    watcher = None
    section_watchers = []
    project_note = None

    if output_nodes and NODES_AVAILABLE:
        node_set = create_biographer_node_set(
            name=name,
            raw_input=raw_input,
            operator="p:",
            project_id=project_id
        )

        # Auto-create project note + watcher for person search if project_id provided
        # Project note = default note for this person with template headers
        # Watchers = each section header becomes a watcher
        # All BRUTE queries scan through watchers
        # Findings stream to project note under section headings
        if project_id:
            try:
                # Initialize full project note system
                # This creates: project note → loads template → creates section watchers
                init_result = await initialize_biographer_with_project_note(
                    person_name=name,
                    project_id=project_id,
                    subject_node_id=node_set.primary_node.node_id,
                    query_node_id=node_set.query_node.node_id,
                )

                watcher = init_result.get("watcher")
                project_note = init_result.get("project_note")
                section_watchers_data = init_result.get("section_watchers", [])

                # Convert section watcher dicts to list for output
                for sw in section_watchers_data:
                    # Create lightweight watcher objects for compatibility
                    section_watchers.append(type('SectionWatcher', (), sw)())

            except Exception as e:
                # Non-fatal - continue without watcher
                print(f"Warning: Project note/watcher initialization failed: {e}")

    if parallel:
        # Run all CLIs in parallel
        with ThreadPoolExecutor(max_workers=len(sources)) as executor:
            futures = {executor.submit(run_cli, source, name, timeout): source
                      for source in sources}
            results = [future.result() for future in futures]
    else:
        # Run sequentially
        results = [run_cli(source, name, timeout) for source in sources]

    # =========================================================================
    # CROSS-PLATFORM USERNAME SEARCH
    # Extract any usernames found by EYE-D/other sources and search them
    # across all social platforms via socialite identifier
    # =========================================================================
    username_search_results = []
    if SOCIALITE_IDENTIFIER_AVAILABLE:
        found_usernames = extract_usernames_from_results(results)
        if found_usernames:
            print(f"🔍 Found {len(found_usernames)} username(s) - searching across platforms...")
            for username in found_usernames[:5]:  # Limit to 5 to avoid API overload
                try:
                    # Run async identifier search
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Already in async context
                        username_result = await search_username_all_platforms(username)
                    else:
                        username_result = loop.run_until_complete(
                            search_username_all_platforms(username)
                        )
                    if username_result and username_result.total_found > 0:
                        username_search_results.append({
                            "username": username,
                            "platforms_found": [
                                {
                                    "platform": a.platform.value,
                                    "username": a.username,
                                    "url": a.profile_url,
                                    "display_name": a.display_name,
                                    "followers": a.followers,
                                    "verified": a.verified_badge,
                                }
                                for a in username_result.extracted_accounts
                            ]
                        })
                        print(f"   ✓ {username}: found on {username_result.total_found} platforms")
                except Exception as e:
                    print(f"   ✗ {username}: search failed - {e}")

    elapsed = time.time() - start_time

    # Create secondary nodes from results
    if node_set and NODES_AVAILABLE:
        for result in results:
            source = result.get("source", "unknown")
            if result.get("status") == "success" and result.get("results"):
                suffix = SOURCE_CLIS.get(source, {}).get("suffix", "x")
                secondary = create_secondary_person_node(
                    name=name,
                    suffix=suffix,
                    source=source,
                    query_node_id=node_set.query_node.node_id,
                    source_data=result.get("results", {})
                )
                node_set.add_secondary(secondary)

        # Execute watcher scan against results (Haiku evaluates relevance)
        watcher_scan_result = None
        if watcher and results:
            try:
                watcher_scan_result = await execute_watcher_scan(
                    watcher=watcher,
                    results=[r.get("results", {}) for r in results if r.get("status") == "success"],
                )
            except Exception as e:
                watcher_scan_result = {"error": str(e)}

        # Return node structure with watcher
        output = node_set.to_dict()
        output["search_time_seconds"] = round(elapsed, 2)
        output["sources_queried"] = sources
        output["raw_results"] = {r.get("source"): r for r in results}

        # Include cross-platform username search results
        if username_search_results:
            output["cross_platform_usernames"] = username_search_results
            # Also add to social_profiles in aggregated profile
            for usr in username_search_results:
                for platform in usr.get("platforms_found", []):
                    # These are additional profiles found via username search
                    output.setdefault("discovered_social_profiles", []).append({
                        "source_username": usr["username"],
                        "platform": platform["platform"],
                        "handle": platform["username"],
                        "url": platform["url"],
                        "display_name": platform.get("display_name", ""),
                        "followers": platform.get("followers", 0),
                        "verified": platform.get("verified", False),
                        "discovery_method": "cross_platform_username_search"
                    })

        # Include project note info
        if project_note:
            output["project_note"] = {
                "note_id": project_note.note_id,
                "label": project_note.label,
                "project_id": project_note.project_id,
                "template_loaded": project_note.template_loaded,
                "watchers_created": project_note.watchers_created,
                "sections": [s.to_dict() for s in project_note.sections],
            }

        # Include watcher info for biographer_ai
        if watcher:
            output["watcher"] = watcher.to_dict()
            output["watcher"]["scan_result"] = watcher_scan_result
            output["watcher"]["section_headings"] = PERSON_NOTE_HEADINGS if NODES_AVAILABLE else []

        # Include section watchers (from project note headers)
        if section_watchers:
            output["section_watchers"] = [
                getattr(w, '__dict__', w.to_dict() if hasattr(w, 'to_dict') else {})
                for w in section_watchers
            ]

        # Assemble full context for biographer_ai disambiguation decisions
        # This is CRITICAL - biographer_ai needs:
        # 1. Project note (with template populated, sections filled)
        # 2. Active watchers + their attached context (entities, topics)
        # 3. Primary node data (current verified/unverified fields)
        # 4. Pending findings awaiting ADD/REJECT decisions
        if project_id and CONTEXT_AVAILABLE:
            try:
                # Convert section watchers to BiographerWatcher-compatible objects
                sw_list = []
                for sw_data in section_watchers:
                    sw_dict = getattr(sw_data, '__dict__', sw_data)
                    if isinstance(sw_dict, dict):
                        sw_obj = type('BiographerWatcher', (), sw_dict)()
                        sw_obj.watcher_id = sw_dict.get('watcher_id', '')
                        sw_obj.watcher_type = sw_dict.get('watcher_type', 'topic')
                        sw_obj.prompt = sw_dict.get('prompt', '')
                        sw_obj.name = sw_dict.get('name', sw_dict.get('section_header', ''))
                        sw_list.append(sw_obj)

                # Get pending findings from watcher scan
                pending_findings = []
                if watcher_scan_result and watcher_scan_result.get("findings"):
                    pending_findings = watcher_scan_result.get("findings", {}).get("items", [])

                # Assemble context with disambiguation anchors and IO routing
                # CRITICAL: This pre-populates discernable attributes and shows
                # what sources can fill unfilled slots
                biographer_context = asyncio.get_event_loop().run_until_complete(
                    assemble_biographer_context(
                        project_id=project_id,
                        person_name=name,
                        project_note=project_note,
                        primary_node=node_set.primary_node,
                        watcher=watcher,
                        section_watchers=sw_list if sw_list else None,
                        pending_findings=pending_findings,
                        # Disambiguation context
                        jurisdiction=jurisdiction,
                        jurisdictions=jurisdictions,
                        industry=industry,
                        related_companies=related_companies,
                    )
                )

                # Include both structured context and formatted prompt context
                output["biographer_context"] = biographer_context.to_dict()
                output["ai_prompt_context"] = biographer_context.to_prompt_context()

            except Exception as e:
                output["context_error"] = str(e)

        # =========================================================================
        # OPTICS - Media Footprint & Reputation Analysis
        # Run OPTICS on collected brute results for reputation profiling
        # =========================================================================
        if OPTICS_AVAILABLE:
            try:
                # Collect all brute results for OPTICS
                brute_results_for_optics = []
                for r in results:
                    if r.get("status") == "success" and r.get("results"):
                        result_data = r.get("results", {})
                        # Handle both list and dict results
                        if isinstance(result_data, list):
                            brute_results_for_optics.extend(result_data)
                        elif isinstance(result_data, dict):
                            items = result_data.get("items", result_data.get("results", []))
                            if isinstance(items, list):
                                brute_results_for_optics.extend(items)
                
                if brute_results_for_optics:
                    optics_profile = asyncio.get_event_loop().run_until_complete(
                        analyze_optics(
                            entity_name=name,
                            entity_type="private_individual",
                            brute_results=brute_results_for_optics,
                            use_ai_extraction=True
                        )
                    )
                    output["optics_profile"] = optics_profile
                    print(f"📊 OPTICS: {optics_profile.get('volume', {}).get('unique_mentions', 0)} unique mentions")
            except Exception as e:
                output["optics_error"] = str(e)
                print(f"⚠️  OPTICS analysis failed: {e}")

        return output

    # Legacy mode - aggregate into profile
    profile = aggregate_results(results, name)
    profile["search_time_seconds"] = round(elapsed, 2)

    # OPTICS for legacy mode too
    if OPTICS_AVAILABLE:
        try:
            brute_results_for_optics = []
            for r in results:
                if r.get("status") == "success" and r.get("results"):
                    result_data = r.get("results", {})
                    if isinstance(result_data, list):
                        brute_results_for_optics.extend(result_data)
                    elif isinstance(result_data, dict):
                        items = result_data.get("items", result_data.get("results", []))
                        if isinstance(items, list):
                            brute_results_for_optics.extend(items)
            
            if brute_results_for_optics:
                import asyncio
                optics_profile = asyncio.get_event_loop().run_until_complete(
                    analyze_optics(
                        entity_name=name,
                        entity_type="private_individual",
                        brute_results=brute_results_for_optics,
                        use_ai_extraction=True
                    )
                )
                profile["optics_profile"] = optics_profile
        except Exception as e:
            profile["optics_error"] = str(e)

    return profile


def cmd_person(args):
    """Search for a person across all sources."""
    sources = args.sources.split(",") if args.sources else None

    # Parse jurisdictions if provided as comma-separated
    jurisdictions = None
    if getattr(args, 'jurisdictions', None):
        jurisdictions = [j.strip().upper() for j in args.jurisdictions.split(",")]

    # Parse related companies if provided
    related_companies = None
    if getattr(args, 'related_companies', None):
        related_companies = [c.strip() for c in args.related_companies.split(",")]

    result = asyncio.run(search_person(
        name=args.name,
        sources=sources,
        parallel=not args.sequential,
        timeout=args.timeout,
        output_nodes=args.output_nodes,
        project_id=getattr(args, 'project_id', None),
        # Disambiguation context
        jurisdiction=getattr(args, 'jurisdiction', None),
        jurisdictions=jurisdictions,
        industry=getattr(args, 'industry', None),
        related_companies=related_companies,
    ))

    # Node output mode
    if args.output_nodes:
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"\n{'='*60}")
            print(f"BIOGRAPHER NODE GRAPH: {args.name}")
            print(f"{'='*60}")

            print(f"\n[QUERY NODE]")
            print(f"  ID: {result['node_ids']['query']}")
            print(f"  Label: {result['query']['label']}")

            print(f"\n[PRIMARY NODE]")
            print(f"  ID: {result['node_ids']['primary']}")
            print(f"  Label: {result['primary']['label']}")
            print(f"  Status: {result['primary']['metadata'].get('consolidation_status', 'pending')}")

            print(f"\n[SECONDARY NODES] ({len(result['secondaries'])})")
            for sec in result['secondaries']:
                source = sec['metadata'].get('source', 'unknown')
                suffix = sec['metadata'].get('suffix', '?')
                print(f"  ({suffix}) {sec['label']} [source: {source}]")
                print(f"      ID: {sec['node_id']}")

            # Show project note info
            if result.get("project_note"):
                pn = result["project_note"]
                print(f"\n[PROJECT NOTE]")
                print(f"  ID: {pn.get('note_id')}")
                print(f"  Label: {pn.get('label')}")
                print(f"  Template: {'✓' if pn.get('template_loaded') else '✗'}")
                print(f"  Sections: {len(pn.get('sections', []))}")
                for sec in pn.get("sections", [])[:4]:
                    watcher_status = f"[W]" if sec.get('watcher_id') else ""
                    print(f"    • {sec.get('header', 'Unknown')} {watcher_status}")
                if len(pn.get("sections", [])) > 4:
                    print(f"    ... and {len(pn.get('sections', [])) - 4} more")

            # Show watcher info
            if result.get("watcher"):
                watcher = result["watcher"]
                print(f"\n[MAIN WATCHER] Active")
                print(f"  ID: {watcher.get('watcher_id')}")
                print(f"  Prompt: \"{watcher.get('prompt')}\"")
                print(f"  Project: {watcher.get('project_id')}")
                print(f"  Document: {watcher.get('parent_document_id')}")
                if watcher.get("scan_result"):
                    scan = watcher["scan_result"]
                    if scan.get("findings"):
                        print(f"  Findings: {scan['findings'].get('total', 0)}")

            # Show section watchers count
            if result.get("section_watchers"):
                print(f"\n[SECTION WATCHERS] {len(result['section_watchers'])} watchers attached to headers")

            print(f"\nSearch time: {result.get('search_time_seconds', 0)}s")

            # Show errors from raw results
            for source, data in result.get("raw_results", {}).items():
                if data.get("status") == "error":
                    print(f"\n[{source}] Error: {data.get('error')}")
        return

    # Legacy profile output mode
    profile = result
    if args.json:
        print(json.dumps(profile, indent=2, default=str))
    else:
        print(f"\n{'='*60}")
        print(f"PERSON PROFILE: {profile['name']}")
        print(f"{'='*60}")

        print(f"\nSources: {', '.join(profile['sources_with_data'])} "
              f"({len(profile['sources_with_data'])}/{len(profile['sources_queried'])})")
        print(f"Confidence: {profile['confidence']:.0%}")
        print(f"Search time: {profile['search_time_seconds']}s")

        if profile.get("identifiers"):
            print(f"\nIdentifiers:")
            for key, value in profile["identifiers"].items():
                print(f"  {key}: {value}")

        if profile.get("corporate_roles"):
            print(f"\nCorporate Roles ({len(profile['corporate_roles'])}):")
            for role in profile["corporate_roles"][:10]:
                print(f"  - {role.get('position', 'N/A')} at {role.get('company', 'Unknown')}")

        if profile.get("social_profiles"):
            print(f"\nSocial Profiles ({len(profile['social_profiles'])}):")
            for sp in profile["social_profiles"][:10]:
                print(f"  - {sp.get('platform', 'Unknown')}: {sp.get('handle', 'N/A')}")

        if profile.get("breach_exposure"):
            print(f"\nBreach Exposure ({len(profile['breach_exposure'])}):")
            for breach in profile["breach_exposure"][:5]:
                print(f"  - {breach.get('name', 'Unknown breach')}")

        # Show errors
        for source, data in profile.get("raw_results", {}).items():
            if data.get("status") == "error":
                print(f"\n[{source}] Error: {data.get('error')}")


def cmd_sources(args):
    """List available sources."""
    if args.json:
        # Can't serialize lambdas, so create a clean version
        clean_sources = {
            name: {
                "path": str(config["path"]),
                "description": config["description"],
                "suffix": config["suffix"],
                "exists": config["path"].exists()
            }
            for name, config in SOURCE_CLIS.items()
        }
        print(json.dumps(clean_sources, indent=2, default=str))
    else:
        print("\nBIOGRAPHER Sources:")
        print("-" * 40)
        for name, config in SOURCE_CLIS.items():
            exists = "✓" if config["path"].exists() else "✗"
            suffix = config.get("suffix", "?")
            print(f"  {exists} ({suffix}) {name}: {config['description']}")
            print(f"         CLI: {config['path']}")


def cmd_process_findings(args):
    """Process pending findings with full biographer context.

    This is called by biographer_ai to make ADD_VERIFIED/ADD_UNVERIFIED/REJECT
    decisions on watcher findings.

    Input: JSON file from search_person with --project-id
    Output: Context-enriched prompt for AI decision making, or JSON with decisions
    """
    if not NODES_AVAILABLE or not CONTEXT_AVAILABLE:
        print("Error: Node/Context utilities not available. Run from module context.", file=sys.stderr)
        sys.exit(1)

    # Load data from file
    try:
        with open(args.node_file, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {args.node_file}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Check for context
    if "biographer_context" not in data and "ai_prompt_context" not in data:
        print("Error: No biographer context found. Re-run search with --project-id", file=sys.stderr)
        sys.exit(1)

    # Output formatted context for AI
    if args.prompt_only:
        # Just output the AI prompt context for piping to biographer_ai
        prompt_context = data.get("ai_prompt_context", "")
        if not prompt_context and data.get("biographer_context"):
            # Reconstruct from structured context
            ctx = data["biographer_context"]
            prompt_context = f"""## BIOGRAPHER CONTEXT

**Person:** {ctx.get('person_name')}
**Project:** {ctx.get('project_id')}

### Project Note
Note ID: {ctx.get('project_note', {}).get('note_id')}
Label: {ctx.get('project_note', {}).get('label')}

### Pending Findings ({ctx.get('pending_findings_count', 0)})
Review each finding and decide: ADD_VERIFIED, ADD_UNVERIFIED, or REJECT

For REJECT: MUST provide reasoning in this format:
REJECTED: [field]='[value]' from [source]
Reason: [your reasoning]
"""
        print(prompt_context)
        return

    if args.json:
        # Output full structured context
        output = {
            "person_name": data.get("primary", {}).get("label", "Unknown"),
            "project_id": data.get("biographer_context", {}).get("project_id"),
            "context": data.get("biographer_context", {}),
            "pending_findings": data.get("biographer_context", {}).get("pending_findings_count", 0),
            "watchers_active": len(data.get("biographer_context", {}).get("watchers", [])),
            "prompt_context": data.get("ai_prompt_context", ""),
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        # Human-readable context summary
        ctx = data.get("biographer_context", {})
        print(f"\n{'='*60}")
        print(f"BIOGRAPHER CONTEXT FOR AI DECISIONS")
        print(f"{'='*60}")
        print(f"\nPerson: {ctx.get('person_name')}")
        print(f"Project: {ctx.get('project_id')}")

        # Project note
        pn = ctx.get("project_note", {})
        print(f"\n[PROJECT NOTE]")
        print(f"  ID: {pn.get('note_id')}")
        print(f"  Label: {pn.get('label')}")
        print(f"  Sections: {len(pn.get('sections', []))}")

        # Watchers
        watchers = ctx.get("watchers", [])
        print(f"\n[ACTIVE WATCHERS] ({len(watchers)})")
        for w in watchers:
            print(f"  • {w.get('section_header', 'Unknown')} [{w.get('watcher_type')}]")
            print(f"    Prompt: \"{w.get('prompt', '')}\"")

        # Pending findings
        print(f"\n[PENDING FINDINGS] ({ctx.get('pending_findings_count', 0)})")
        print("  → biographer_ai must decide: ADD_VERIFIED / ADD_UNVERIFIED / REJECT")

        # Field sources
        field_sources = ctx.get("field_sources", {})
        if field_sources:
            print(f"\n[FIELD SOURCES] (for verification)")
            for field, sources in field_sources.items():
                print(f"  • {field}: {', '.join(sources)}")

        print(f"\n{'='*60}")
        print("Use --prompt-only to get AI-ready prompt context")
        print("Use --json for structured output")


def cmd_consolidate(args):
    """Consolidate secondary nodes into primary node.

    This is called by biographer_ai after reviewing the node graph.
    It applies verification logic to merge secondaries into primary.

    With --disambiguate: Runs SASTRE disambiguation first to detect
    entity collisions before consolidation. Nodes confirmed as
    different entities (REPEL) are excluded from consolidation.
    """
    if not NODES_AVAILABLE:
        print("Error: Node utilities not available. Run from module context.", file=sys.stderr)
        sys.exit(1)

    # Load node set from file
    try:
        with open(args.node_file, 'r') as f:
            node_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {args.node_file}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Reconstruct nodes from JSON
    from .nodes import Node, Edge, BiographerNodeSet

    def dict_to_node(d: Dict[str, Any]) -> Node:
        """Reconstruct Node from dict."""
        edges = [Edge(e["type"], e["target"], e.get("props", {}))
                 for e in d.get("embedded_edges", [])]
        return Node(
            node_id=d["node_id"],
            node_class=d["node_class"],
            node_type=d["node_type"],
            label=d["label"],
            props=d.get("props", {}),
            embedded_edges=edges,
            metadata=d.get("metadata", {})
        )

    primary_node = dict_to_node(node_data["primary"])
    query_node = dict_to_node(node_data["query"])
    secondary_nodes = [dict_to_node(s) for s in node_data.get("secondaries", [])]

    if not secondary_nodes:
        print("Warning: No secondary nodes to consolidate")
        if args.json:
            print(json.dumps(node_data, indent=2, default=str))
        return

    # Check if disambiguation is requested
    use_disambiguation = getattr(args, 'disambiguate', False)

    if use_disambiguation:
        # Reconstruct BiographerNodeSet for disambiguation
        node_set = BiographerNodeSet(
            query_node=query_node,
            primary_node=primary_node,
            secondary_nodes=secondary_nodes,
        )

        # Get disambiguation anchors from context if available
        anchors = None
        if node_data.get("biographer_context"):
            ctx = node_data["biographer_context"]
            anchors = ctx.get("disambiguation")

        # Run consolidation WITH disambiguation
        result = consolidate_with_disambiguation(
            node_set=node_set,
            anchors=anchors,
            fuzzy_match=args.fuzzy
        )

        # Add disambiguation-specific info to output
        node_data["disambiguation"] = {
            "enabled": True,
            "excluded_nodes": result.excluded_nodes,
            "uncertain_nodes": result.uncertain_nodes,
            "pending_wedge_queries": result.pending_wedge_queries,
        }
    else:
        # Run standard consolidation without disambiguation
        result = consolidate_secondaries(
            primary_node=primary_node,
            secondary_nodes=secondary_nodes,
            fuzzy_match=args.fuzzy
        )

    # Apply to primary
    updated_primary = apply_consolidation(primary_node, result)

    # Update node_data with consolidated primary
    node_data["primary"] = updated_primary.to_dict()
    node_data["consolidation"] = {
        "summary": result.summary,
        "confidence_score": result.confidence_score,
        "disambiguated": getattr(result, 'disambiguated', False),
        "verification_results": [
            {
                "field": vr.field_name,
                "status": vr.status.value,
                "sources": vr.sources,
                "confidence": vr.confidence,
                "notes": vr.notes
            }
            for vr in result.verification_results
        ]
    }

    if args.json:
        print(json.dumps(node_data, indent=2, default=str))
    else:
        print(f"\n{'='*60}")
        print(f"CONSOLIDATION RESULTS: {primary_node.label}")
        print(f"{'='*60}")
        print(f"\nSummary: {result.summary}")
        print(f"Confidence: {result.confidence_score:.0%}")
        print(f"Disambiguated: {'Yes' if getattr(result, 'disambiguated', False) else 'No'}")

        # Show disambiguation results if enabled
        if use_disambiguation and hasattr(result, 'excluded_nodes') and result.excluded_nodes:
            print(f"\n[DISAMBIGUATION]")
            print(f"  Excluded nodes (REPEL - different entity): {len(result.excluded_nodes)}")
            for nid in result.excluded_nodes:
                # Find the node label
                for s in secondary_nodes:
                    if s.node_id == nid:
                        print(f"    - {s.label} (source: {s.metadata.get('source', 'unknown')})")
                        break

        if use_disambiguation and hasattr(result, 'pending_wedge_queries') and result.pending_wedge_queries:
            print(f"\n[WEDGE QUERIES] ({len(result.pending_wedge_queries)} pending)")
            for wq in result.pending_wedge_queries[:3]:
                print(f"    [{wq.get('wedge_type')}] {wq.get('query')}")
            if len(result.pending_wedge_queries) > 3:
                print(f"    ... and {len(result.pending_wedge_queries) - 3} more")

        print(f"\nVerification Results:")
        for vr in result.verification_results:
            status_icon = {"verified": "✓", "unverified": "?", "contradiction": "⚠"}
            icon = status_icon.get(vr.status.value, "•")
            print(f"  {icon} {vr.field_name}: {vr.status.value}")
            print(f"      Sources: {', '.join(vr.sources)}")
            if vr.notes:
                print(f"      Notes: {vr.notes}")

        print(f"\nPrimary Node Updated:")
        print(f"  ID: {updated_primary.node_id}")
        print(f"  Status: {updated_primary.metadata.get('consolidation_status')}")


def main():
    parser = argparse.ArgumentParser(
        description="BIOGRAPHER CLI - Person Profile Aggregator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python biographer_cli.py person "John Smith"
    python biographer_cli.py person "John Smith" --json
    python biographer_cli.py person "John Smith" --sources eyed,corporella
    python biographer_cli.py sources
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # person command
    p_person = subparsers.add_parser("person", help="Search for a person")
    p_person.add_argument("name", help="Person name to search")
    p_person.add_argument("--sources", "-s", help="Comma-separated sources (default: all)")
    p_person.add_argument("--sequential", action="store_true", help="Run sequentially instead of parallel")
    p_person.add_argument("--timeout", "-t", type=int, default=120, help="Timeout per source (seconds)")
    p_person.add_argument("--json", "-j", action="store_true", help="JSON output")
    p_person.add_argument("--output-nodes", "-n", action="store_true",
                         help="Output node graph structure (query, primary, secondaries)")
    p_person.add_argument("--project-id", "-p",
                         help="Project ID - auto-creates project note with template and watchers")
    # Disambiguation context arguments
    p_person.add_argument("--jurisdiction", "-J",
                         help="Primary jurisdiction ISO code (e.g., US, UK, DE) for disambiguation")
    p_person.add_argument("--jurisdictions",
                         help="Comma-separated jurisdictions (e.g., US,UK,DE)")
    p_person.add_argument("--industry",
                         help="Primary industry for disambiguation (e.g., finance, tech)")
    p_person.add_argument("--related-companies",
                         help="Comma-separated related companies for disambiguation")
    p_person.set_defaults(func=cmd_person)

    # sources command
    p_sources = subparsers.add_parser("sources", help="List available sources")
    p_sources.add_argument("--json", "-j", action="store_true", help="JSON output")
    p_sources.set_defaults(func=cmd_sources)

    # process-findings command - for biographer_ai to get context for decisions
    p_findings = subparsers.add_parser("process-findings",
        help="Process findings with full context (for biographer_ai decisions)")
    p_findings.add_argument("node_file", help="JSON file from search with --project-id")
    p_findings.add_argument("--prompt-only", action="store_true",
                           help="Output AI-ready prompt context only")
    p_findings.add_argument("--json", "-j", action="store_true", help="JSON output")
    p_findings.set_defaults(func=cmd_process_findings)

    # consolidate command - for biographer_ai to call after getting node results
    p_consolidate = subparsers.add_parser("consolidate",
        help="Consolidate secondary nodes into primary (called by biographer_ai)")
    p_consolidate.add_argument("node_file", help="JSON file with node set from --output-nodes")
    p_consolidate.add_argument("--fuzzy", action="store_true", help="Use fuzzy matching")
    p_consolidate.add_argument("--disambiguate", "-d", action="store_true",
        help="Run SASTRE disambiguation before consolidation. "
             "Detects entity collisions and excludes REPEL nodes (different entity). "
             "Generates wedge queries for BINARY_STAR cases.")
    p_consolidate.add_argument("--json", "-j", action="store_true", help="JSON output")
    p_consolidate.set_defaults(func=cmd_consolidate)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
