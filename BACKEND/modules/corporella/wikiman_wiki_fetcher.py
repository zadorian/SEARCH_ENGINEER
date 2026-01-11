"""
WIKIMAN Wiki Fetcher for Corporella Claude
Fetches jurisdiction-specific public records sections from WIKIMAN-PRO wiki cache
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
import re

# Path to WIKIMAN-PRO wiki cache
WIKIMAN_WIKI_CACHE = Path(__file__).parent.parent / "0. WIKIMAN-PRO" / "wiki_cache"


class WikiManWikiFetcher:
    """
    Fetches public records wiki sections from WIKIMAN-PRO for a given jurisdiction
    """

    def __init__(self):
        self.cache_path = WIKIMAN_WIKI_CACHE

    def fetch_wiki_for_jurisdiction(self, jurisdiction: str) -> Optional[Dict[str, Any]]:
        """
        Fetch wiki page for jurisdiction and parse public records sections

        Args:
            jurisdiction: Jurisdiction code (e.g., "GB", "us_ca", "SG")

        Returns:
            {
                "ok": True/False,
                "jurisdiction": str,
                "wiki_file": str,
                "sections": {
                    "corporate_registry": {"content": str, "links": [...]},
                    "litigation": {"content": str, "links": [...]},
                    "regulatory": {"content": str, "links": [...]},
                    "asset_registries": {"content": str, "links": [...]},
                    "licensing": {"content": str, "links": [...]},
                    "political": {"content": str, "links": [...]},
                    "further_public_records": {"content": str, "links": [...]},
                    "media": {"content": str, "links": [...]},
                    "breaches": {"content": str, "links": [...]},
                }
            }
        """

        # Map jurisdiction codes to wiki filenames
        wiki_file = self._get_wiki_filename(jurisdiction)

        if not wiki_file:
            return {
                "ok": False,
                "error": f"No wiki file found for jurisdiction: {jurisdiction}"
            }

        wiki_path = self.cache_path / wiki_file

        if not wiki_path.exists():
            return {
                "ok": False,
                "error": f"Wiki file not found: {wiki_file}"
            }

        # Read wiki content
        try:
            wiki_content = wiki_path.read_text(encoding='utf-8')
        except Exception as e:
            return {
                "ok": False,
                "error": f"Failed to read wiki file: {str(e)}"
            }

        # Parse sections (with special handling for US states)
        if jurisdiction.lower().startswith("us_"):
            # Extract state name from jurisdiction code (us_ca -> California)
            state_code = jurisdiction.lower().split("_")[1]
            state_name = self._get_state_name(state_code)
            sections = self._parse_us_state_sections(wiki_content, state_name)
        else:
            sections = self._parse_wiki_sections(wiki_content)

        return {
            "ok": True,
            "jurisdiction": jurisdiction,
            "wiki_file": wiki_file,
            "sections": sections
        }

    def _get_wiki_filename(self, jurisdiction: str) -> Optional[str]:
        """
        Map jurisdiction code to WIKIMAN wiki filename

        Examples:
            "GB" -> "gb.md"
            "us_ca" -> "us.md"  (US has all states in one file)
            "SG" -> "sg.md"
            "HK" -> "hong_kong.md"
        """

        jurisdiction_lower = jurisdiction.lower()

        # Map common jurisdiction codes (using country-level domain codes)
        mapping = {
            "gb": "gb.md",  # United Kingdom (Great Britain)
            "uk": "gb.md",  # Alternative UK code (maps to same file)
            "sg": "sg.md",  # Singapore
            "hk": "hong_kong.md",  # Hong Kong
            "au": "au.md",  # Australia
            "de": "de.md",  # Germany (Deutschland)
            "fr": "fr.md",  # France
            "nl": "nl.md",  # Netherlands
            "es": "es.md",  # Spain (España)
            "it": "it.md",  # Italy
            "ca": "ca.md",  # Canada
            "mx": "mx.md",  # Mexico
            "br": "br.md",  # Brazil
            "jp": "jp.md",  # Japan
            "cn": "cn.md",  # China
            "in": "in.md",  # India
            "ua": "ua.md",  # Ukraine
        }

        # Handle US states - all in us.md
        if jurisdiction_lower.startswith("us_"):
            return "us.md"

        # Check mapping
        if jurisdiction_lower in mapping:
            return mapping[jurisdiction_lower]

        # Try direct filename
        potential_file = f"{jurisdiction_lower}.md"
        if (self.cache_path / potential_file).exists():
            return potential_file

        return None

    def _get_state_name(self, state_code: str) -> str:
        """
        Convert US state code to full state name
        """
        state_mapping = {
            "al": "Alabama", "ak": "Alaska", "az": "Arizona", "ar": "Arkansas",
            "ca": "California", "co": "Colorado", "ct": "Connecticut", "de": "Delaware",
            "fl": "Florida", "ga": "Georgia", "hi": "Hawaii", "id": "Idaho",
            "il": "Illinois", "in": "Indiana", "ia": "Iowa", "ks": "Kansas",
            "ky": "Kentucky", "la": "Louisiana", "me": "Maine", "md": "Maryland",
            "ma": "Massachusetts", "mi": "Michigan", "mn": "Minnesota", "ms": "Mississippi",
            "mo": "Missouri", "mt": "Montana", "ne": "Nebraska", "nv": "Nevada",
            "nh": "New Hampshire", "nj": "New Jersey", "nm": "New Mexico", "ny": "New York",
            "nc": "North Carolina", "nd": "North Dakota", "oh": "Ohio", "ok": "Oklahoma",
            "or": "Oregon", "pa": "Pennsylvania", "ri": "Rhode Island", "sc": "South Carolina",
            "sd": "South Dakota", "tn": "Tennessee", "tx": "Texas", "ut": "Utah",
            "vt": "Vermont", "va": "Virginia", "wa": "Washington", "wv": "West Virginia",
            "wi": "Wisconsin", "wy": "Wyoming"
        }
        return state_mapping.get(state_code.lower(), state_code.upper())

    def _parse_us_state_sections(self, wiki_content: str, state_name: str) -> Dict[str, Dict[str, Any]]:
        """
        Parse US state-specific sections from us.md wiki file

        US wiki format:
        ==California==
        ===Corporate Registry===
        [content]
        ===Litigation===
        [content]
        ...
        """
        sections = {
            "corporate_registry": {"content": "", "links": []},
            "litigation": {"content": "", "links": []},
            "regulatory": {"content": "", "links": []},
            "asset_registries": {"content": "", "links": []},
            "licensing": {"content": "", "links": []},
            "political": {"content": "", "links": []},
            "further_public_records": {"content": "", "links": []},
            "media": {"content": "", "links": []},
            "breaches": {"content": "", "links": []},
        }

        # Find the state section (==California==)
        state_pattern = rf"==\s*{re.escape(state_name)}\s*=="
        state_match = re.search(state_pattern, wiki_content, re.IGNORECASE)

        if not state_match:
            return sections  # State not found, return empty sections

        state_start = state_match.end()

        # Find next state section (or end of file)
        next_state = re.search(r"\n==\s*[^=]+\s*==", wiki_content[state_start:])
        state_end = state_start + next_state.start() if next_state else len(wiki_content)

        state_content = wiki_content[state_start:state_end]

        # Now parse subsections within this state
        # Note: Some states use === (subsection) and some use == (section) inconsistently
        section_patterns = {
            "corporate_registry": r"=+\s*Corporate Registry\s*=+",
            "litigation": r"=+\s*Litigation\s*=+",
            "regulatory": r"=+\s*Regulatory\s*=+",
            "asset_registries": r"=+\s*Asset Registries\s*=+",
            "licensing": r"=+\s*Licensing\s*=+",
            "political": r"=+\s*Political\s*=+",
            "further_public_records": r"=+\s*Further Public Records\s*=+",
            "media": r"=+\s*Media\s*=+",
            "breaches": r"=+\s*Breaches\s*=+",
        }

        for section_name, pattern in section_patterns.items():
            section_match = re.search(pattern, state_content, re.IGNORECASE)

            if section_match:
                section_start = section_match.end()

                # Find next subsection (any number of =) - but NOT if it's part of a link
                next_section = re.search(r"\n=+\s*[A-Z]", state_content[section_start:])
                section_end = section_start + next_section.start() if next_section else len(state_content)

                content = state_content[section_start:section_end].strip()

                if content:
                    links = self._extract_links(content)
                    sections[section_name] = {
                        "content": content,
                        "links": links
                    }

        return sections

    def _parse_wiki_sections(self, wiki_content: str) -> Dict[str, Dict[str, Any]]:
        """
        Parse wiki content into sections with extracted links

        Returns:
            {
                "corporate_registry": {"content": str, "links": [{"url": str, "title": str}]},
                ...
            }
        """

        sections = {
            "corporate_registry": {"content": "", "links": []},
            "litigation": {"content": "", "links": []},
            "regulatory": {"content": "", "links": []},
            "asset_registries": {"content": "", "links": []},
            "licensing": {"content": "", "links": []},
            "political": {"content": "", "links": []},
            "further_public_records": {"content": "", "links": []},
            "media": {"content": "", "links": []},
            "breaches": {"content": "", "links": []},
        }

        # Section headers to match
        section_patterns = {
            "corporate_registry": r"==+\s*Corporate Registry\s*==+",
            "litigation": r"==+\s*Litigation\s*==+",
            "regulatory": r"==+\s*Regulatory\s*==+",
            "asset_registries": r"==+\s*Asset Registries\s*==+",
            "licensing": r"==+\s*Licensing\s*==+",
            "political": r"==+\s*Political\s*==+",
            "further_public_records": r"==+\s*Further Public Records\s*==+",
            "media": r"==+\s*Media\s*==+",
            "breaches": r"==+\s*Breaches\s*==+",
        }

        for section_name, pattern in section_patterns.items():
            section_content = self._extract_section_content(wiki_content, pattern)

            if section_content:
                # Extract links from content
                links = self._extract_links(section_content)

                sections[section_name] = {
                    "content": section_content.strip(),
                    "links": links
                }

        return sections

    def _extract_section_content(self, wiki_content: str, section_pattern: str) -> str:
        """
        Extract content between section header and next SAME-LEVEL section header
        Only stops at == headers, not === subsections
        """

        # Find section start
        match = re.search(section_pattern, wiki_content, re.IGNORECASE)

        if not match:
            return ""

        start_pos = match.end()

        # Find next SAME-LEVEL section (exactly == not ===)
        # Look for newline, then exactly 2 equals, then non-equals, then exactly 2 equals
        next_section = re.search(r"\n==[^=].*?==\s*$", wiki_content[start_pos:], re.MULTILINE)

        if next_section:
            end_pos = start_pos + next_section.start()
            return wiki_content[start_pos:end_pos]
        else:
            return wiki_content[start_pos:]

    def _extract_links(self, content: str) -> List[Dict[str, str]]:
        """
        Extract links from wiki content

        Supports:
        - Bold Wiki: '''[URL Title]'''
        - Markdown: [Title](URL)
        - MediaWiki: [URL Title]
        - Plain URLs: https://...
        """

        links = []

        # Bold Wiki link pattern: '''[URL Title]'''
        bold_wiki_pattern = r"'''?\[([^\s\]]+)\s+([^\]]+)\]'''?"
        for match in re.finditer(bold_wiki_pattern, content):
            url = match.group(1)
            title = match.group(2)

            # Clean up title
            title = re.sub(r'\(.*?\)', '', title).strip()  # Remove (pub), (priv), (civ), etc.

            links.append({
                "url": url,
                "title": title,
                "type": "bold_wiki"
            })

        # MediaWiki link pattern: [URL Title] (only if not already captured as bold)
        mediawiki_pattern = r'\[([^\s\]]+)\s+([^\]]+)\]'
        for match in re.finditer(mediawiki_pattern, content):
            url = match.group(1)
            title = match.group(2)

            # Skip if already found as bold wiki link
            if url not in [link["url"] for link in links]:
                # Clean up title
                title = re.sub(r'\(.*?\)', '', title).strip()  # Remove (pub), (priv), etc.

                links.append({
                    "url": url,
                    "title": title,
                    "type": "mediawiki"
                })

        # Markdown link pattern: [Title](URL)
        markdown_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
        for match in re.finditer(markdown_pattern, content):
            title = match.group(1)
            url = match.group(2)

            # Skip if already found as MediaWiki link
            if url not in [link["url"] for link in links]:
                links.append({
                    "url": url,
                    "title": title,
                    "type": "markdown"
                })

        # Plain URL pattern: https://... or http://...
        plain_url_pattern = r'(?<!\[)(https?://[^\s\)]+)'
        for match in re.finditer(plain_url_pattern, content):
            url = match.group(1)

            # Skip if already found
            if url not in [link["url"] for link in links]:
                # Extract domain as title
                domain = re.match(r'https?://([^/]+)', url)
                title = domain.group(1) if domain else url

                links.append({
                    "url": url,
                    "title": title,
                    "type": "plain"
                })

        return links


def fetch_wiki_for_jurisdiction(jurisdiction: str) -> Dict[str, Any]:
    """
    Convenience function to fetch wiki for jurisdiction
    """
    fetcher = WikiManWikiFetcher()
    return fetcher.fetch_wiki_for_jurisdiction(jurisdiction)


# Example usage
if __name__ == "__main__":
    import json

    # Test UK
    print("=" * 80)
    print("TESTING UK WIKI FETCH")
    print("=" * 80)
    uk_wiki = fetch_wiki_for_jurisdiction("GB")

    if uk_wiki["ok"]:
        print(f"✅ Found wiki: {uk_wiki['wiki_file']}")
        print(f"   Sections found: {len(uk_wiki['sections'])}")

        # Show Corporate Registry section
        corp_section = uk_wiki['sections']['corporate_registry']
        print(f"\n   Corporate Registry:")
        print(f"   - Content length: {len(corp_section['content'])} chars")
        print(f"   - Links found: {len(corp_section['links'])}")

        for link in corp_section['links'][:5]:
            print(f"     • {link['title']}: {link['url'][:60]}...")
    else:
        print(f"❌ Error: {uk_wiki['error']}")

    # Test US
    print("\n" + "=" * 80)
    print("TESTING US WIKI FETCH")
    print("=" * 80)
    us_wiki = fetch_wiki_for_jurisdiction("us_ca")

    if us_wiki["ok"]:
        print(f"✅ Found wiki: {us_wiki['wiki_file']}")
        print(f"   Sections found: {len(us_wiki['sections'])}")

        # Show Corporate Registry section
        corp_section = us_wiki['sections']['corporate_registry']
        print(f"\n   Corporate Registry:")
        print(f"   - Content length: {len(corp_section['content'])} chars")
        print(f"   - Links found: {len(corp_section['links'])}")

        for link in corp_section['links'][:5]:
            print(f"     • {link['title']}: {link['url'][:60]}...")
    else:
        print(f"❌ Error: {us_wiki['error']}")
