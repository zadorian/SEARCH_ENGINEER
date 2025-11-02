#!/usr/bin/env python3
"""Parse natural language queries into structured components."""

from __future__ import annotations

import json
import logging
import re
import time
import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

try:  # Optional dependency for rich country metadata
    import pycountry  # type: ignore
except ImportError:  # pragma: no cover - fallback handled below
    pycountry = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "event": "%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

# Performance logging
Path("logs").mkdir(exist_ok=True)
perf_logger = logging.getLogger("performance")
if not perf_logger.handlers:
    perf_handler = logging.FileHandler("logs/performance.log")
    perf_handler.setFormatter(logging.Formatter("%(message)s"))
    perf_logger.addHandler(perf_handler)
perf_logger.setLevel(logging.INFO)


# 50-country dictionary (lowercase lookup)
COUNTRY_DICTIONARY = {
    # Tier 1 (MVP focus)
    "hungary": "hu",
    "hungarian": "hu",
    "germany": "de",
    "german": "de",
    "deutschland": "de",
    "uk": "gb",
    "united kingdom": "gb",
    "britain": "gb",
    "british": "gb",
    "england": "gb",
    "bosnia": "ba",
    "bosnian": "ba",
    "bosnia and herzegovina": "ba",

    # Tier 2 (EU countries)
    "france": "fr",
    "french": "fr",
    "spain": "es",
    "spanish": "es",
    "españa": "es",
    "italy": "it",
    "italian": "it",
    "italia": "it",
    "netherlands": "nl",
    "dutch": "nl",
    "holland": "nl",
    "poland": "pl",
    "polish": "pl",
    "polska": "pl",
    "austria": "at",
    "austrian": "at",
    "österreich": "at",
    "belgium": "be",
    "belgian": "be",
    "belgique": "be",
    "belgië": "be",

    # Additional EU countries
    "portugal": "pt",
    "portuguese": "pt",
    "greece": "gr",
    "greek": "gr",
    "czech republic": "cz",
    "czechia": "cz",
    "czech": "cz",
    "romania": "ro",
    "romanian": "ro",
    "denmark": "dk",
    "danish": "dk",
    "sweden": "se",
    "swedish": "se",
    "finland": "fi",
    "finnish": "fi",
    "ireland": "ie",
    "irish": "ie",
    "croatia": "hr",
    "croatian": "hr",
    "slovakia": "sk",
    "slovak": "sk",
    "slovenia": "si",
    "slovenian": "si",
    "bulgaria": "bg",
    "bulgarian": "bg",
    "lithuania": "lt",
    "lithuanian": "lt",
    "latvia": "lv",
    "latvian": "lv",
    "estonia": "ee",
    "estonian": "ee",
    "luxembourg": "lu",
    "malta": "mt",
    "cyprus": "cy",

    # Non-EU European
    "switzerland": "ch",
    "swiss": "ch",
    "norway": "no",
    "norwegian": "no",
    "iceland": "is",
    "serbia": "rs",
    "ukraine": "ua",
    "turkey": "tr",

    # Americas
    "usa": "us",
    "united states": "us",
    "america": "us",
    "american": "us",
    "canada": "ca",
    "canadian": "ca",
    "brazil": "br",
    "brazilian": "br",
    "mexico": "mx",
    "mexican": "mx",
    "argentina": "ar",
    "chile": "cl",

    # Asia
    "china": "cn",
    "chinese": "cn",
    "japan": "jp",
    "japanese": "jp",
    "india": "in",
    "indian": "in",
    "singapore": "sg",
    "hong kong": "hk",
    "south korea": "kr",
    "korea": "kr",
}


# Source type patterns
SOURCE_TYPE_PATTERNS = {
    "corporate_registry": [
        r"corporate.*(?:registry|register|records?)",
        r"company.*(?:registry|register|records?|search)",
        r"business.*(?:registry|register|records?)",
        r"commercial.*(?:registry|register)",
        r"trade.*register",
    ],
    # Additional types (deferred to Phase 2+)
    "litigation": [
        r"litigation",
        r"court.*(?:records?|cases?)",
        r"legal.*(?:records?|proceedings?)",
    ],
    "assets": [
        r"asset.*(?:registry|register|records?)",
        r"property.*(?:registry|register|records?)",
    ],
}


@dataclass
class ParsedQuery:
    """Structured query components."""

    country_code: str
    country_name: str
    source_type: str
    entity_name: Optional[str] = None
    original_query: str = ""

    def to_dict(self):
        """Convert to dictionary."""
        return {
            "country_code": self.country_code,
            "country_name": self.country_name,
            "source_type": self.source_type,
            "entity_name": self.entity_name,
            "original_query": self.original_query,
        }


class QueryParseError(Exception):
    """Query parsing error."""
    pass


class AmbiguousQueryError(QueryParseError):
    """Query is ambiguous and requires clarification."""
    pass


class QueryParser:
    """Parse natural language queries into structured components.

    Supports query templates:
    - "Get <country> corporate info for <company name>"
    - "Search <country> company registry for <company name>"
    - "Find <country> corporate records for <company name>"
    - "<company name> in <country> corporate registry"

    Features:
    - 50-country dictionary lookup
    - Regex-based entity name extraction
    - Source type detection (corporate_registry only for MVP)
    - Performance instrumentation
    """

    def __init__(self):
        """Initialize query parser."""
        self.country_dict = COUNTRY_DICTIONARY
        self.country_patterns = {
            name: re.compile(rf"\b{re.escape(name)}\b")
            for name in self.country_dict.keys()
        }
        self.fallback_map, self.fallback_keys = self._build_country_fallbacks()
        self.source_patterns = SOURCE_TYPE_PATTERNS

    def parse(self, query: str) -> ParsedQuery:
        """Parse query into structured components.

        Args:
            query: Natural language query string

        Returns:
            ParsedQuery with country, source type, and entity name

        Raises:
            AmbiguousQueryError: If query is ambiguous
            QueryParseError: If query cannot be parsed
        """
        start_time = time.time()

        try:
            query_lower = query.lower().strip()

            # Extract country
            country_code, country_name = self._extract_country(query_lower)

            # Extract source type (default to corporate_registry for MVP)
            source_type = self._extract_source_type(query_lower)

            # Extract entity name
            entity_name = self._extract_entity_name(query, query_lower, country_name)

            result = ParsedQuery(
                country_code=country_code,
                country_name=country_name,
                source_type=source_type,
                entity_name=entity_name,
                original_query=query,
            )

            duration_ms = (time.time() - start_time) * 1000
            perf_logger.info(
                json.dumps({
                    "operation": "query_parser.parse",
                    "duration_ms": round(duration_ms, 2),
                    "status": "success",
                    "country": country_code,
                    "source_type": source_type,
                })
            )

            logger.info(f"Parsed query: {country_code}/{source_type}, entity={entity_name}")

            return result

        except (QueryParseError, AmbiguousQueryError):
            duration_ms = (time.time() - start_time) * 1000
            perf_logger.info(
                json.dumps({
                    "operation": "query_parser.parse",
                    "duration_ms": round(duration_ms, 2),
                    "status": "error",
                })
            )
            raise
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            perf_logger.info(
                json.dumps({
                    "operation": "query_parser.parse",
                    "duration_ms": round(duration_ms, 2),
                    "status": "error",
                    "error": str(e),
                })
            )
            raise QueryParseError(f"Failed to parse query: {e}")

    def _extract_country(self, query_lower: str) -> Tuple[str, str]:
        """Extract country code and name from query.

        Args:
            query_lower: Lowercased query string

        Returns:
            Tuple of (country_code, country_name)

        Raises:
            AmbiguousQueryError: If multiple countries detected
            QueryParseError: If no country found
        """
        found_countries = []

        # Check for each country in dictionary
        for country_name, pattern in self.country_patterns.items():
            if pattern.search(query_lower):
                found_countries.append((self.country_dict[country_name], country_name))

        if not found_countries:
            fallback = self._fallback_country_lookup(query_lower)
            if not fallback:
                raise QueryParseError(
                    "No country detected in query. "
                    "Please specify a country (e.g., 'Hungary', 'Germany', 'UK')."
                )
            return fallback

        if len(found_countries) > 1:
            # Filter out duplicates (same country_code)
            unique_codes = {}
            for code, name in found_countries:
                if code not in unique_codes:
                    unique_codes[code] = name
                elif len(name) > len(unique_codes[code]):
                    # Prefer longer match (e.g., "united kingdom" over "kingdom")
                    unique_codes[code] = name

            if len(unique_codes) > 1:
                country_list = ", ".join(unique_codes.values())
                raise AmbiguousQueryError(
                    f"Multiple countries detected: {country_list}. "
                    f"Please specify only one country."
                )

            # Use the unique country
            country_code = list(unique_codes.keys())[0]
            country_name = unique_codes[country_code]
        else:
            country_code, country_name = found_countries[0]

        return country_code, country_name

    def _normalize_phrase(self, phrase: str) -> str:
        return re.sub(r"[^a-z]+", " ", phrase.lower()).strip()

    def _build_country_fallbacks(self) -> tuple[dict[str, tuple[str, str]], list[str]]:
        synonyms: dict[str, tuple[str, str]] = {}

        irregular = {
            "united states": ["usa", "us", "u s", "america", "american", "u.s.", "u.s.a", "u.s.a."],
            "united kingdom": ["uk", "u k", "britain", "great britain", "british"],
            "south korea": ["korea", "korean", "republic of korea"],
            "north korea": ["dprk", "north korean", "democratic people's republic of korea"],
            "czech republic": ["czechia", "czech"],
            "eswatini": ["swaziland", "swazi"],
            "myanmar": ["burma", "burmese"],
            "ivory coast": ["cote d ivoire", "ivorian"],
            "bosnia and herzegovina": ["bosnia", "bosnian", "herzegovina"],
            "vatican city": ["holy see", "vatican"],
            "timor leste": ["east timor"],
            "germany": ["german"],
            "france": ["french"],
            "spain": ["spanish"],
            "portugal": ["portuguese"],
            "greece": ["greek"],
            "poland": ["polish"],
            "netherlands": ["dutch", "holland"],
            "belgium": ["belgian"],
            "sweden": ["swedish"],
            "norway": ["norwegian"],
            "finland": ["finnish"],
            "denmark": ["danish"],
            "ireland": ["irish"],
            "switzerland": ["swiss"],
            "croatia": ["croatian"],
            "serbia": ["serbian"],
            "slovenia": ["slovenian"],
            "slovakia": ["slovak", "slovakian"],
            "romania": ["romanian"],
            "bulgaria": ["bulgarian"],
            "hungary": ["hungarian"],
            "italy": ["italian"],
            "austria": ["austrian"],
            "canada": ["canadian"],
            "mexico": ["mexican"],
            "brazil": ["brazilian"],
            "argentina": ["argentinian", "argentine"],
            "chile": ["chilean"],
            "china": ["chinese"],
            "japan": ["japanese"],
            "india": ["indian"],
            "australia": ["australian"],
            "new zealand": ["kiwi"],
            "russia": ["russian"],
            "ukraine": ["ukrainian"],
            "belarus": ["belarusian"],
            "latvia": ["latvian"],
            "lithuania": ["lithuanian"],
            "estonia": ["estonian"],
        }

        if pycountry is None:
            for name, code in self.country_dict.items():
                norm = self._normalize_phrase(name)
                if norm:
                    synonyms.setdefault(norm, (code, name))
            keys = sorted(synonyms.keys(), key=len, reverse=True)
            return synonyms, keys

        for country in pycountry.countries:
            iso2 = country.alpha_2.lower()
            display = country.name.lower()

            names = {country.name}
            for attr in ("official_name", "common_name"):
                if hasattr(country, attr):
                    names.add(getattr(country, attr))

            for name in names:
                norm = self._normalize_phrase(name)
                if not norm:
                    continue
                synonyms.setdefault(norm, (iso2, display))

                parts = norm.split()
                if len(parts) > 1:
                    for part in parts:
                        if len(part) > 3:
                            synonyms.setdefault(part, (iso2, display))

                if norm in irregular:
                    for alt in irregular[norm]:
                        alt_norm = self._normalize_phrase(alt)
                        if alt_norm:
                            synonyms.setdefault(alt_norm, (iso2, display))

            synonyms.setdefault(iso2, (iso2, display))
            if hasattr(country, "alpha_3"):
                synonyms.setdefault(country.alpha_3.lower(), (iso2, display))

            for name in names:
                lower_name = name.lower()
                if lower_name.endswith("ia"):
                    base = lower_name[:-2]
                    synonyms.setdefault(base + "ian", (iso2, display))
                if lower_name.endswith("ium"):
                    synonyms.setdefault(lower_name[:-3] + "ian", (iso2, display))
                if lower_name.endswith("a"):
                    synonyms.setdefault(lower_name[:-1] + "an", (iso2, display))

        keys = sorted(synonyms.keys(), key=len, reverse=True)
        return synonyms, keys

    def _fallback_country_lookup(self, query_lower: str) -> Optional[Tuple[str, str]]:
        normalized_query = self._normalize_phrase(query_lower)
        if not normalized_query:
            return None

        padded = f" {normalized_query} "
        for key in self.fallback_keys:
            if f" {key} " in padded:
                iso2, name = self.fallback_map[key]
                return iso2, name

        tokens = set(normalized_query.split())
        for token in tokens:
            matches = difflib.get_close_matches(token, self.fallback_keys, n=1, cutoff=0.88)
            if matches:
                iso2, name = self.fallback_map[matches[0]]
                return iso2, name

        return None

    def _extract_source_type(self, query_lower: str) -> str:
        """Extract source type from query.

        Args:
            query_lower: Lowercased query string

        Returns:
            Source type string (default: "corporate_registry")
        """
        # Check each source type pattern
        for source_type, patterns in self.source_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return source_type

        # Default to corporate_registry for MVP
        return "corporate_registry"

    def _extract_entity_name(
        self,
        query: str,
        query_lower: str,
        country_name: str,
    ) -> Optional[str]:
        """Extract entity name from query.

        Args:
            query: Original query string (with capitalization)
            query_lower: Lowercased query string
            country_name: Detected country name

        Returns:
            Entity name or None
        """
        # Strategy 1: Extract from "for <entity>" pattern
        for_pattern = re.search(r"\bfor\s+([A-Z][^\s,\.]+(?:\s+[A-Z][^\s,\.]*)*)", query)
        if for_pattern:
            entity = for_pattern.group(1).strip()
            # Remove trailing punctuation
            entity = re.sub(r"[,\.!?]+$", "", entity)
            if entity and entity.lower() not in self.country_dict:
                return entity

        # Strategy 2: Extract capitalized words (likely company name)
        # Skip if query uses "in <country>" pattern (Strategy 4 will handle)
        if not re.match(r"^[A-Z].*\s+in\s+", query):
            # Match sequences of capitalized words not in country dictionary
            cap_pattern = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", query)
            skip_words = {"get", "search", "find", "info", "records", "corporate", "company", "registry"}
            for candidate in cap_pattern:
                candidate_lower = candidate.lower()
                words = candidate_lower.split()
                if not words:
                    continue
                if all(word in skip_words or word in self.country_dict for word in words):
                    continue
                if candidate_lower not in self.country_dict and len(candidate) > 2:
                    return candidate

        # Strategy 3: Extract quoted text
        quote_pattern = re.search(r'["\']([^"\']+)["\']', query)
        if quote_pattern:
            return quote_pattern.group(1).strip()

        # Strategy 4: Extract from "in <country>" pattern (entity before "in")
        # Match everything from start until " in " (non-greedy)
        in_pattern = re.search(r"^(.+?)\s+in\s+", query)
        if in_pattern:
            entity = in_pattern.group(1).strip()
            # Verify it's not a country name and starts with capital
            if (entity and
                entity[0].isupper() and
                entity.lower() not in self.country_dict):
                return entity

        return None


if __name__ == "__main__":
    # Quick test
    import sys

    print("Testing QueryParser...")

    parser = QueryParser()

    test_queries = [
        "Get Hungarian corporate info for MOL Group",
        "Search Germany company registry for Siemens AG",
        "Find UK corporate records for Tesla",
        "MOL Group in Hungary corporate registry",
        "france corporate registry search for Total SA",
    ]

    try:
        for query in test_queries:
            result = parser.parse(query)
            print(f"✓ '{query}'")
            print(f"  → {result.country_code}/{result.source_type}, entity={result.entity_name}")

        print("\n✓ All tests passed!")

    except Exception as e:
        print(f"\n✗ Test failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
