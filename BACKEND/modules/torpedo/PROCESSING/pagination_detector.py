#!/usr/bin/env python3
"""
TORPEDO PAGINATION DETECTOR - Detect and configure pagination for news sources

Detects:
1. "Next" / "→" / ">>" links in HTML
2. Page number links (1, 2, 3...)
3. URL parameters (?page=N, ?offset=N, ?p=N)
4. Known pagination patterns for major outlets

Output: pagination config for sources/news.json:
{
    "type": "link" | "param" | "offset" | "none",
    "param": "page",          # URL parameter name
    "selector": "a.next",     # CSS selector for next link
    "max_pages": 10,          # Suggested max pages to follow
    "pattern": "?page={n}"    # URL pattern for direct page access
}
"""

import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urljoin
from bs4 import BeautifulSoup


# ─────────────────────────────────────────────────────────────
# KNOWN PAGINATION PATTERNS FOR MAJOR NEWS OUTLETS
# ─────────────────────────────────────────────────────────────

KNOWN_PAGINATION = {
    # German
    "spiegel.de": {
        "type": "param",
        "param": "pageNumber",
        "pattern": "&pageNumber={n}",
        "max_pages": 20
    },
    "zeit.de": {
        "type": "param",
        "param": "p",
        "pattern": "&p={n}",
        "max_pages": 10
    },
    "faz.net": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 20
    },
    "welt.de": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 15
    },
    "sueddeutsche.de": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "handelsblatt.com": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 20
    },
    "tagesschau.de": {
        "type": "link",
        "selector": "a.pagination__next, a[rel='next']",
        "max_pages": 5
    },
    "focus.de": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "n-tv.de": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 15
    },
    "manager-magazin.de": {
        "type": "param",
        "param": "pageNumber",
        "pattern": "&pageNumber={n}",
        "max_pages": 10
    },

    # UK
    "bbc.co.uk": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "theguardian.com": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 20
    },
    "reuters.com": {
        "type": "offset",
        "param": "offset",
        "step": 20,
        "pattern": "&offset={n}",
        "max_pages": 10
    },
    "ft.com": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "telegraph.co.uk": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "dailymail.co.uk": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 15
    },
    "independent.co.uk": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "mirror.co.uk": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "express.co.uk": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },

    # US
    "nytimes.com": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "washingtonpost.com": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "wsj.com": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "bloomberg.com": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "cnn.com": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "foxnews.com": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },

    # French
    "lemonde.fr": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 20
    },
    "lefigaro.fr": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 15
    },
    "liberation.fr": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "lesechos.fr": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },

    # Italian
    "corriere.it": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 15
    },
    "repubblica.it": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "ilsole24ore.com": {
        "type": "param",
        "param": "pagina",
        "pattern": "&pagina={n}",
        "max_pages": 10
    },

    # Spanish
    "elpais.com": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 20
    },
    "elmundo.es": {
        "type": "param",
        "param": "pagina",
        "pattern": "&pagina={n}",
        "max_pages": 15
    },
    "abc.es": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },

    # Dutch
    "nrc.nl": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "volkskrant.nl": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "telegraaf.nl": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 15
    },

    # Austrian/Swiss
    "derstandard.at": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 15
    },
    "nzz.ch": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "krone.at": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },

    # Polish
    "gazeta.pl": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "wyborcza.pl": {
        "type": "param",
        "param": "strona",
        "pattern": "&strona={n}",
        "max_pages": 10
    },
    "onet.pl": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 15
    },

    # Croatian/Serbian/Balkan
    "jutarnji.hr": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "vecernji.hr": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "24sata.hr": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "index.hr": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 15
    },
    "blic.rs": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },

    # Russian
    "kommersant.ru": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 10
    },
    "rbc.ru": {
        "type": "param",
        "param": "page",
        "pattern": "&page={n}",
        "max_pages": 15
    },
}


# ─────────────────────────────────────────────────────────────
# NEXT LINK TEXT PATTERNS (multilingual)
# ─────────────────────────────────────────────────────────────

NEXT_LINK_TEXT = [
    # English
    "next", "next page", "more", "load more", "show more",
    # German
    "weiter", "nächste", "mehr laden", "mehr anzeigen", "weitere",
    # French
    "suivant", "page suivante", "plus", "charger plus",
    # Spanish
    "siguiente", "más", "cargar más",
    # Italian
    "successivo", "prossimo", "carica altri",
    # Dutch
    "volgende", "meer laden",
    # Polish
    "następna", "dalej", "więcej",
    # Croatian
    "sljedeća", "dalje", "više",
    # Russian
    "далее", "следующая", "ещё",
    # Symbols
    "→", "»", ">>", ">", "›",
]

# CSS selectors commonly used for next page links
NEXT_LINK_SELECTORS = [
    "a.next",
    "a.pagination-next",
    "a[rel='next']",
    "a.page-next",
    ".pagination a.next",
    ".pager a.next",
    "nav.pagination a:contains('Next')",
    "a.load-more",
    "button.load-more",
    ".pagination li.next a",
    "a[aria-label='Next']",
    "a[aria-label='Next page']",
    ".nav-next a",
]

# URL parameter patterns for pagination
PAGINATION_PARAMS = ["page", "p", "pg", "pageNumber", "offset", "start", "from",
                     "pagina", "seite", "strona", "strana", "sayfa"]


class PaginationDetector:
    """Detect pagination capability for news sources."""

    def __init__(self):
        self.known_outlets = KNOWN_PAGINATION

    def detect_from_domain(self, domain: str) -> Optional[Dict]:
        """Get known pagination config for a major outlet."""
        if not domain:
            return None

        domain_clean = domain.lower().replace("www.", "")

        # Exact match
        if domain_clean in self.known_outlets:
            return self.known_outlets[domain_clean].copy()

        # Partial match
        for known_domain, config in self.known_outlets.items():
            if known_domain in domain_clean or domain_clean.endswith(known_domain):
                return config.copy()

        return None

    def detect_from_html(self, html: str, base_url: str = "") -> Optional[Dict]:
        """
        Detect pagination from HTML content.

        Returns pagination config if detected.
        """
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')

        # 1. Try common CSS selectors
        for selector in NEXT_LINK_SELECTORS:
            try:
                next_link = soup.select_one(selector)
                if next_link:
                    href = next_link.get('href', '')
                    return self._analyze_pagination_link(href, selector, base_url)
            except:
                continue

        # 2. Search for links by text content
        for link in soup.find_all('a', href=True):
            text = link.get_text(strip=True).lower()
            if any(nt in text for nt in NEXT_LINK_TEXT):
                href = link.get('href', '')
                if href and href != '#':
                    return self._analyze_pagination_link(href, f"a:contains('{text}')", base_url)

        # 3. Look for numbered pagination (1, 2, 3...)
        pagination_container = soup.select_one('.pagination, .pager, nav[aria-label*="pagination"]')
        if pagination_container:
            page_links = pagination_container.find_all('a', href=True)
            numbers = []
            for pl in page_links:
                text = pl.get_text(strip=True)
                if text.isdigit():
                    numbers.append((int(text), pl.get('href', '')))

            if len(numbers) >= 2:
                # Sort by number and get page 2 link
                numbers.sort(key=lambda x: x[0])
                for num, href in numbers:
                    if num == 2:
                        return self._analyze_pagination_link(href, "pagination numbers", base_url)

        # 4. Check for "load more" buttons
        load_more = soup.select_one('button.load-more, a.load-more, [data-load-more]')
        if load_more:
            return {
                "type": "ajax",
                "selector": "button.load-more, a.load-more",
                "max_pages": 5,
                "notes": "Requires JS interaction"
            }

        return None

    def detect_from_url(self, url: str) -> Optional[Dict]:
        """
        Detect pagination params from URL structure.
        """
        if not url:
            return None

        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        for param in PAGINATION_PARAMS:
            if param in query:
                return {
                    "type": "param",
                    "param": param,
                    "pattern": f"&{param}={{n}}",
                    "max_pages": 10
                }

        # Check for offset-based
        if 'offset' in query or 'start' in query:
            param = 'offset' if 'offset' in query else 'start'
            return {
                "type": "offset",
                "param": param,
                "step": 20,  # Guess
                "pattern": f"&{param}={{n}}",
                "max_pages": 10
            }

        return None

    def _analyze_pagination_link(self, href: str, selector: str, base_url: str) -> Dict:
        """Analyze a pagination link to determine pattern."""
        # Make absolute URL
        if base_url and not href.startswith('http'):
            href = urljoin(base_url, href)

        # Parse to find pagination param
        parsed = urlparse(href)
        query = parse_qs(parsed.query)

        for param in PAGINATION_PARAMS:
            if param in query:
                val = query[param][0]
                # Check if it's a number
                if val.isdigit():
                    return {
                        "type": "param",
                        "param": param,
                        "pattern": f"&{param}={{n}}",
                        "selector": selector,
                        "max_pages": 10,
                        "detected_from": "html"
                    }

        # Check for offset in URL
        if 'offset' in query:
            return {
                "type": "offset",
                "param": "offset",
                "step": int(query['offset'][0]) if query['offset'][0].isdigit() else 20,
                "pattern": "&offset={n}",
                "selector": selector,
                "max_pages": 10
            }

        # Fallback - just use the selector
        return {
            "type": "link",
            "selector": selector,
            "max_pages": 10,
            "detected_from": "html"
        }

    def detect(
        self,
        domain: str,
        html: Optional[str] = None,
        url: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Detect pagination capability.

        Priority:
        1. Known outlet patterns (most reliable)
        2. HTML analysis (during scrape test)
        3. URL parameter analysis
        """
        # Try known outlet first
        config = self.detect_from_domain(domain)
        if config:
            return config

        # Try HTML analysis if provided
        if html:
            base_url = f"https://{domain}" if domain else ""
            config = self.detect_from_html(html, base_url)
            if config:
                return config

        # Try URL analysis
        if url:
            config = self.detect_from_url(url)
            if config:
                return config

        return None

    def get_next_page_url(
        self,
        base_url: str,
        pagination_config: Dict,
        current_page: int = 1
    ) -> Optional[str]:
        """
        Build URL for next page given pagination config.

        Args:
            base_url: Current search URL
            pagination_config: Pagination config from detect()
            current_page: Current page number (1-indexed)

        Returns:
            Next page URL or None if max pages reached
        """
        if not pagination_config:
            return None

        max_pages = pagination_config.get("max_pages", 10)
        next_page = current_page + 1

        if next_page > max_pages:
            return None

        ptype = pagination_config.get("type")

        if ptype == "param":
            pattern = pagination_config.get("pattern", "&page={n}")
            # Remove existing page param if present
            param = pagination_config.get("param", "page")
            base_clean = re.sub(rf'[?&]{param}=\d+', '', base_url)
            separator = "&" if "?" in base_clean else "?"
            return f"{base_clean}{separator}{pattern.lstrip('&').replace('{n}', str(next_page))}"

        elif ptype == "offset":
            step = pagination_config.get("step", 20)
            offset = (next_page - 1) * step
            pattern = pagination_config.get("pattern", "&offset={n}")
            param = pagination_config.get("param", "offset")
            base_clean = re.sub(rf'[?&]{param}=\d+', '', base_url)
            separator = "&" if "?" in base_clean else "?"
            return f"{base_clean}{separator}{pattern.lstrip('&').replace('{n}', str(offset))}"

        elif ptype == "link":
            # Need HTML parsing - can't generate URL directly
            return None

        return None


# ─────────────────────────────────────────────────────────────
# BATCH PROCESSING
# ─────────────────────────────────────────────────────────────

def detect_pagination_for_sources(sources: List[Dict], html_map: Dict[str, str] = None) -> Tuple[int, List[Dict]]:
    """
    Detect pagination for a list of sources.

    Args:
        sources: List of source dicts
        html_map: Optional dict of domain -> HTML content (from scrape tests)

    Returns: (count_detected, updated_sources)
    """
    detector = PaginationDetector()
    html_map = html_map or {}
    count = 0
    updated = []

    for source in sources:
        domain = source.get("domain", "")
        template = source.get("search_template", "")
        html = html_map.get(domain)

        config = detector.detect(domain, html=html, url=template)

        if config:
            source["pagination"] = config
            count += 1

        updated.append(source)

    return count, updated


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    # Test with sources/news.json
    PROJECT_ROOT = Path(__file__).resolve().parents[4]
    sources_path = PROJECT_ROOT / "input_output" / "matrix" / "sources" / "news.json"

    if not sources_path.exists():
        print(f"Sources not found: {sources_path}")
        sys.exit(1)

    with open(sources_path) as f:
        data = json.load(f)

    detector = PaginationDetector()
    total_detected = 0
    by_jurisdiction = {}

    for jur, sources in data.items():
        if not isinstance(sources, list):
            continue

        detected = 0
        for source in sources:
            domain = source.get("domain", "")
            template = source.get("search_template", "")

            config = detector.detect(domain, url=template)
            if config:
                detected += 1
                source["pagination"] = config

        if detected:
            by_jurisdiction[jur] = detected
            total_detected += detected

    print(f"=== PAGINATION DETECTION RESULTS ===")
    print(f"Total detected: {total_detected}")
    print(f"\nBy jurisdiction:")
    for jur, count in sorted(by_jurisdiction.items(), key=lambda x: -x[1]):
        print(f"  {jur}: {count}")

    # Save if requested
    if len(sys.argv) > 1 and sys.argv[1] == "--save":
        with open(sources_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n✓ Saved to {sources_path}")
