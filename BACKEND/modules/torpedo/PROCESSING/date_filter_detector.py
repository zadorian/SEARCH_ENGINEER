#!/usr/bin/env python3
"""
TORPEDO DATE FILTER DETECTOR - Detect and configure date filtering for news sources

Detects:
1. Existing date parameters in search templates
2. Known date patterns for major news outlets
3. Tests date URL construction for verification

Output: date_filtering config for sources/news.json:
{
    "supported": true,
    "date_format": "YYYY-MM-DD",
    "param_from": "from",
    "param_to": "to",
    "template_date": "https://site.com/search?q={q}&from={date_from}&to={date_to}"
}
"""

import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime


# ─────────────────────────────────────────────────────────────
# KNOWN DATE PATTERNS FOR MAJOR NEWS OUTLETS
# ─────────────────────────────────────────────────────────────

KNOWN_DATE_OUTLETS = {
    # German
    "spiegel.de": {
        "supported": True,
        "date_format": "YYYYMMDD",
        "param_from": "from",
        "param_to": "to",
        "notes": "Compact date format without separators"
    },
    "zeit.de": {
        "supported": True,
        "date_format": "DD.MM.YYYY",
        "param_from": "from",
        "param_to": "to",
        "notes": "German date format with dots"
    },
    "faz.net": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "start",
        "param_to": "end"
    },
    "welt.de": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "from",
        "param_to": "to"
    },
    "sueddeutsche.de": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "from",
        "param_to": "to"
    },
    "handelsblatt.com": {
        "supported": True,
        "date_format": "YYYYMMDD",
        "param_from": "from",
        "param_to": "to"
    },
    "tagesschau.de": {
        "supported": True,
        "date_format": "DD.MM.YYYY",
        "param_from": "datum_von",
        "param_to": "datum_bis"
    },
    "focus.de": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "fromDate",
        "param_to": "toDate"
    },

    # UK
    "bbc.co.uk": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "from",
        "param_to": "to"
    },
    "theguardian.com": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "fromDate",
        "param_to": "toDate"
    },
    "reuters.com": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "dateFrom",
        "param_to": "dateTo"
    },
    "ft.com": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "dateTo",  # FT uses reverse
        "param_to": "dateFrom"
    },
    "telegraph.co.uk": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "from",
        "param_to": "to"
    },

    # US
    "nytimes.com": {
        "supported": True,
        "date_format": "YYYYMMDD",
        "param_from": "startDate",
        "param_to": "endDate"
    },
    "washingtonpost.com": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "datefilter",
        "param_to": None,  # Uses range format
        "notes": "Uses datefilter=YYYY-MM-DD..YYYY-MM-DD"
    },
    "wsj.com": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "min-date",
        "param_to": "max-date"
    },
    "bloomberg.com": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "time_frame",
        "param_to": None,
        "notes": "Uses time_frame presets"
    },

    # French
    "lemonde.fr": {
        "supported": True,
        "date_format": "DD-MM-YYYY",
        "param_from": "dateFrom",
        "param_to": "dateTo"
    },
    "lefigaro.fr": {
        "supported": True,
        "date_format": "DD-MM-YYYY",
        "param_from": "dateFrom",
        "param_to": "dateTo"
    },
    "liberation.fr": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "from_date",
        "param_to": "to_date"
    },

    # Italian
    "corriere.it": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "from",
        "param_to": "to"
    },
    "repubblica.it": {
        "supported": True,
        "date_format": "YYYYMMDD",
        "param_from": "from",
        "param_to": "to"
    },
    "ilsole24ore.com": {
        "supported": True,
        "date_format": "DD/MM/YYYY",
        "param_from": "data_inizio",
        "param_to": "data_fine"
    },

    # Spanish
    "elpais.com": {
        "supported": True,
        "date_format": "DD/MM/YYYY",
        "param_from": "fechadesde",
        "param_to": "fechahasta"
    },
    "elmundo.es": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "desde",
        "param_to": "hasta"
    },

    # Dutch
    "nrc.nl": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "from",
        "param_to": "to"
    },
    "volkskrant.nl": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "fromDate",
        "param_to": "toDate"
    },

    # Austrian/Swiss
    "derstandard.at": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "from",
        "param_to": "to"
    },
    "nzz.ch": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "from",
        "param_to": "to"
    },

    # Polish
    "gazeta.pl": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "od",
        "param_to": "do"
    },
    "wyborcza.pl": {
        "supported": True,
        "date_format": "YYYY-MM-DD",
        "param_from": "dataOd",
        "param_to": "dataDo"
    },

    # Russian
    "kommersant.ru": {
        "supported": True,
        "date_format": "DD.MM.YYYY",
        "param_from": "from_date",
        "param_to": "to_date"
    },
    "rbc.ru": {
        "supported": True,
        "date_format": "DD.MM.YYYY",
        "param_from": "dateFrom",
        "param_to": "dateTo"
    },
}


# ─────────────────────────────────────────────────────────────
# DATE PARAMETER DETECTION PATTERNS
# ─────────────────────────────────────────────────────────────

DATE_PARAM_PATTERNS = [
    # From/To style
    (r'[?&](from|date_from|start_date|dateFrom|fromDate|startDate|minDate|od|desde|von|da|van)=', 'from'),
    (r'[?&](to|date_to|end_date|dateTo|toDate|endDate|maxDate|do|hasta|bis|a|tot)=', 'to'),
    # Range style
    (r'[?&](range|dateRange|period|timeframe|zeitraum)=', 'range'),
    # Year style
    (r'[?&](year|yyyy|yr|anno|jahr|annee)=', 'year'),
]


class DateFilterDetector:
    """Detect date filtering capability for news sources."""

    def __init__(self):
        self.known_outlets = KNOWN_DATE_OUTLETS

    def detect_from_template(self, template: str) -> Optional[Dict]:
        """
        Detect date filtering params from existing search template.

        Returns date_filtering config if detected.
        """
        if not template:
            return None

        detected = {
            "supported": False,
            "detected_params": []
        }

        for pattern, param_type in DATE_PARAM_PATTERNS:
            match = re.search(pattern, template, re.I)
            if match:
                detected["supported"] = True
                detected["detected_params"].append({
                    "type": param_type,
                    "param": match.group(1)
                })

        if detected["supported"]:
            # Try to determine format from existing values in template
            detected["date_format"] = self._guess_format_from_template(template)
            return detected

        return None

    def detect_from_domain(self, domain: str) -> Optional[Dict]:
        """
        Get known date filtering config for a major outlet.
        """
        if not domain:
            return None

        # Normalize domain
        domain_clean = domain.lower().replace("www.", "")

        # Check exact match first
        if domain_clean in self.known_outlets:
            return self.known_outlets[domain_clean].copy()

        # Check partial match (e.g., "query.nytimes.com" -> "nytimes.com")
        for known_domain, config in self.known_outlets.items():
            if known_domain in domain_clean or domain_clean.endswith(known_domain):
                return config.copy()

        return None

    def detect(self, domain: str, template: str) -> Optional[Dict]:
        """
        Detect date filtering capability from domain and template.

        Priority:
        1. Known outlet patterns (most reliable)
        2. Existing params in template
        """
        # Try known outlet first
        config = self.detect_from_domain(domain)
        if config:
            # Add template_date if we can build it
            if template and "{date_from}" not in template:
                config["template_date"] = self._build_date_template(
                    template,
                    config.get("param_from"),
                    config.get("param_to")
                )
            return config

        # Try detecting from template
        config = self.detect_from_template(template)
        if config:
            return config

        return None

    def _guess_format_from_template(self, template: str) -> str:
        """Guess date format from template URL patterns."""
        # Look for format hints
        if re.search(r'\d{8}', template):  # YYYYMMDD
            return "YYYYMMDD"
        elif re.search(r'\d{2}\.\d{2}\.\d{4}', template):  # DD.MM.YYYY
            return "DD.MM.YYYY"
        elif re.search(r'\d{2}/\d{2}/\d{4}', template):  # DD/MM/YYYY or MM/DD/YYYY
            return "DD/MM/YYYY"
        elif re.search(r'\d{4}-\d{2}-\d{2}', template):  # YYYY-MM-DD
            return "YYYY-MM-DD"
        else:
            return "YYYY-MM-DD"  # Default ISO format

    def _build_date_template(
        self,
        base_template: str,
        param_from: Optional[str],
        param_to: Optional[str]
    ) -> str:
        """Build date-enabled template from base template."""
        if not base_template or not param_from:
            return base_template

        # Parse existing template
        parsed = urlparse(base_template)

        # Build date params
        date_params = []
        if param_from:
            date_params.append(f"{param_from}={{date_from}}")
        if param_to:
            date_params.append(f"{param_to}={{date_to}}")

        # Add to query string
        separator = "&" if parsed.query else "?"
        date_suffix = "&".join(date_params)

        return f"{base_template}{separator}{date_suffix}"

    def format_date(self, date_str: str, target_format: str) -> str:
        """
        Format date string to target format.

        Input: YYYY-MM-DD (ISO)
        Output: Format specified by target_format
        """
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")

            format_map = {
                "YYYY-MM-DD": "%Y-%m-%d",
                "DD-MM-YYYY": "%d-%m-%Y",
                "DD.MM.YYYY": "%d.%m.%Y",
                "DD/MM/YYYY": "%d/%m/%Y",
                "MM/DD/YYYY": "%m/%d/%Y",
                "YYYYMMDD": "%Y%m%d",
                "timestamp": None  # Special case
            }

            if target_format == "timestamp":
                return str(int(d.timestamp()))

            py_format = format_map.get(target_format, "%Y-%m-%d")
            return d.strftime(py_format)
        except:
            return date_str


# ─────────────────────────────────────────────────────────────
# BATCH PROCESSING
# ─────────────────────────────────────────────────────────────

def detect_date_filters_for_sources(sources: List[Dict]) -> Tuple[int, List[Dict]]:
    """
    Detect date filtering for a list of sources.

    Returns: (count_detected, updated_sources)
    """
    detector = DateFilterDetector()
    count = 0
    updated = []

    for source in sources:
        domain = source.get("domain", "")
        template = source.get("search_template", "")

        config = detector.detect(domain, template)

        if config:
            source["date_filtering"] = config
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

    detector = DateFilterDetector()
    total_detected = 0
    by_jurisdiction = {}

    for jur, sources in data.items():
        if not isinstance(sources, list):
            continue

        detected = 0
        for source in sources:
            domain = source.get("domain", "")
            template = source.get("search_template", "")

            config = detector.detect(domain, template)
            if config:
                detected += 1
                source["date_filtering"] = config

        if detected:
            by_jurisdiction[jur] = detected
            total_detected += detected

    print(f"=== DATE FILTER DETECTION RESULTS ===")
    print(f"Total detected: {total_detected}")
    print(f"\nBy jurisdiction:")
    for jur, count in sorted(by_jurisdiction.items(), key=lambda x: -x[1]):
        print(f"  {jur}: {count}")

    # Save if requested
    if len(sys.argv) > 1 and sys.argv[1] == "--save":
        with open(sources_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n✓ Saved to {sources_path}")
