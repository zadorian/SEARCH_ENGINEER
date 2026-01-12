#!/usr/bin/env python3
"""
Enrich sources.json with tips from wiki_sections in jurisdictions.json.

Extracts source-specific guidance from wiki content and adds it to matching sources.
"""

import json
import re
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from collections import defaultdict

MATRIX_DIR = Path(__file__).parent.parent


def extract_domain(url: str) -> str:
    """Extract domain from a URL."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        # Remove www prefix for matching
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower()
    except Exception:
        return ""


def extract_tips_from_content(content: str, links: list) -> list:
    """Extract actionable tips from wiki content."""
    tips = []

    if not content:
        return tips

    # Look for patterns that indicate tips/guidance
    tip_patterns = [
        # Instructions
        r"(?:use|search|click|select|choose|enter|look for|check|visit)\s+.+?[.\n]",
        # Availability notes
        r"(?:available|provides|contains|includes|shows|displays)\s+.+?[.\n]",
        # Requirements
        r"(?:requires?|need|must|should)\s+.+?[.\n]",
        # Access notes
        r"(?:free|paid|subscription|login|register)\s+.+?[.\n]",
        # Limitations
        r"(?:only|limited to|restricted|not available)\s+.+?[.\n]",
    ]

    content_clean = content.replace("\n", " ").replace("  ", " ")

    for pattern in tip_patterns:
        matches = re.findall(pattern, content_clean, re.IGNORECASE)
        for match in matches:
            # Clean up the match
            tip = match.strip().rstrip(".")
            if len(tip) > 20 and len(tip) < 200:  # Reasonable tip length
                tips.append(tip)

    # Also extract any text in parentheses that looks like notes
    parens = re.findall(r"\(([^)]+)\)", content)
    for paren in parens:
        if "pub" in paren.lower() or "pay" in paren.lower() or "free" in paren.lower():
            continue  # Skip access markers
        if 15 < len(paren) < 150:
            tips.append(paren)

    return list(set(tips))[:5]  # Limit to 5 tips per source


def extract_search_template_from_content(content: str) -> str:
    """Try to extract a search URL template from wiki content."""
    # Look for search URL patterns
    patterns = [
        r"search.*?(?:url|link|template)[:\s]*([^\s]+\{[^}]+\})",
        r"https?://[^\s]+\?[^\s]*[=\{][^\s]+",
    ]

    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(0)

    return ""


def enrich_sources():
    """Main enrichment function."""

    # Load sources.json
    sources_file = MATRIX_DIR / "sources.json"
    print(f"Loading {sources_file}...")
    with open(sources_file) as f:
        sources_data = json.load(f)

    sources = sources_data.get("sources", {})
    print(f"  Found {len(sources)} sources")

    # Load jurisdictions.json for wiki_sections
    jur_file = MATRIX_DIR / "jurisdictions.json"
    print(f"Loading {jur_file}...")
    with open(jur_file) as f:
        jur_data = json.load(f)

    jurisdictions = jur_data.get("jurisdictions", {})
    print(f"  Found {len(jurisdictions)} jurisdictions")

    # Build domain-to-wiki mapping
    wiki_by_domain = defaultdict(list)
    domain_to_jurisdiction = {}

    for jur_code, jur_info in jurisdictions.items():
        wiki_sections = jur_info.get("wiki_sections", {})

        for section_type, section_data in wiki_sections.items():
            if not isinstance(section_data, dict):
                continue

            content = section_data.get("content", "")
            links = section_data.get("links", [])

            # Extract domains from links
            for link in links:
                url = link.get("url", "")
                title = link.get("title", "")
                domain = extract_domain(url)

                if domain:
                    wiki_by_domain[domain].append({
                        "jurisdiction": jur_code,
                        "section": section_type,
                        "url": url,
                        "title": title,
                        "content": content,
                    })
                    domain_to_jurisdiction[domain] = jur_code

    print(f"\nMapped {len(wiki_by_domain)} domains from wiki")

    # Stats
    stats = {
        "sources_enriched": 0,
        "tips_added": 0,
        "jurisdictions_added": 0,
        "section_types_mapped": defaultdict(int),
    }

    # Enrich sources
    for source_id, source in sources.items():
        domain = source.get("domain", source_id)

        # Try to match with wiki data
        wiki_entries = wiki_by_domain.get(domain, [])

        if not wiki_entries:
            # Try without www
            if domain.startswith("www."):
                wiki_entries = wiki_by_domain.get(domain[4:], [])
            else:
                wiki_entries = wiki_by_domain.get(f"www.{domain}", [])

        if not wiki_entries:
            continue

        # Collect enrichment data
        enriched = False
        all_tips = []

        for entry in wiki_entries:
            content = entry.get("content", "")
            tips = extract_tips_from_content(content, [])

            if tips:
                all_tips.extend(tips)

            # Map section type
            section = entry.get("section", "")
            if section:
                stats["section_types_mapped"][section] += 1

                # Add section type if not set
                if not source.get("wiki_section_type"):
                    source["wiki_section_type"] = section
                    enriched = True

            # Add jurisdiction if not set or more specific
            jur = entry.get("jurisdiction", "")
            if jur and jur != "GLOBAL":
                existing_jurs = source.get("jurisdictions", [])
                if jur not in existing_jurs:
                    existing_jurs.append(jur)
                    source["jurisdictions"] = existing_jurs
                    stats["jurisdictions_added"] += 1
                    enriched = True

        # Add tips
        if all_tips:
            existing_tips = source.get("wiki_tips", [])
            new_tips = [t for t in all_tips if t not in existing_tips][:5]
            if new_tips:
                source["wiki_tips"] = existing_tips + new_tips
                stats["tips_added"] += len(new_tips)
                enriched = True

        if enriched:
            stats["sources_enriched"] += 1

    # Update metadata
    sources_data["meta"]["wiki_enriched"] = True
    sources_data["meta"]["wiki_tips_count"] = stats["tips_added"]
    sources_data["meta"]["updated_at"] = datetime.now().isoformat()
    sources_data["sources"] = sources

    # Write back
    print(f"\nWriting updated sources.json...")
    with open(sources_file, "w") as f:
        json.dump(sources_data, f, indent=2, ensure_ascii=False)

    # Print stats
    print(f"\n=== ENRICHMENT STATS ===")
    print(f"Sources enriched: {stats['sources_enriched']}")
    print(f"Tips added: {stats['tips_added']}")
    print(f"Jurisdictions added: {stats['jurisdictions_added']}")

    print(f"\nSection types mapped:")
    for section, count in sorted(stats["section_types_mapped"].items(), key=lambda x: -x[1])[:10]:
        print(f"  {section}: {count}")


if __name__ == "__main__":
    enrich_sources()
