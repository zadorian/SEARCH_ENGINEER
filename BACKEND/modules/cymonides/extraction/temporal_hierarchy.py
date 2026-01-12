#!/usr/bin/env python3
"""
Temporal Hierarchy Derivation for CYMONIDES Multi-Axis Proximity System
========================================================================

Derives hierarchical temporal fields from dates for precision-aware queries:

    Input: "2024-06-15" (day precision)
    Output: {
        "published_date": "2024-06-15T00:00:00Z",
        "year": 2024,
        "month": 6,
        "day": 15,
        "yearmonth": "2024-06",
        "decade": "2020s",
        "era": "post_covid",
        "precision": "day"
    }

    Input: "June 2024" (month precision)
    Output: {
        "published_date": "2024-06-01T00:00:00Z",
        "year": 2024,
        "month": 6,
        "day": null,
        "yearmonth": "2024-06",
        "decade": "2020s",
        "era": "post_covid",
        "precision": "month"
    }

    Input: "2024" (year precision)
    Output: {
        "published_date": "2024-01-01T00:00:00Z",
        "year": 2024,
        "month": null,
        "day": null,
        "yearmonth": null,
        "decade": "2020s",
        "era": "post_covid",
        "precision": "year"
    }

Supports period ranges for documents spanning time periods:
    Input: "2019-2021" (period)
    Output: {
        "period_start": "2019-01-01T00:00:00Z",
        "period_end": "2021-12-31T23:59:59Z",
        "period_start_year": 2019,
        "period_end_year": 2021,
        "content_years": [2019, 2020, 2021],
        "precision": "year"
    }
"""

import re
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Era definitions: name -> (start_year, end_year)
ERA_DEFINITIONS = {
    "cold_war": (1947, 1991),
    "post_soviet": (1991, 2000),
    "pre_2008": (2000, 2008),
    "post_2008": (2008, 2019),
    "covid_era": (2020, 2022),
    "post_covid": (2023, 2100),  # Current era
}

# Month name mappings
MONTH_NAMES = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


@dataclass
class TemporalResult:
    """Result of temporal hierarchy derivation."""
    # === PUBLISHING TIME (when doc was created) ===
    published_date: Optional[str] = None  # Full ISO: 2024-06-15T00:00:00Z
    year: Optional[int] = None            # pub_year
    month: Optional[int] = None           # pub_month
    day: Optional[int] = None             # pub_day
    yearmonth: Optional[str] = None       # "2024-06" for grouping
    decade: Optional[str] = None          # "2020s"
    era: Optional[str] = None             # "post_covid"
    precision: str = "unknown"            # "day" | "month" | "year" | "decade" | "unknown"

    # === CONTENT TIME (what period doc discusses) ===
    content_decade: Optional[str] = None  # Primary decade discussed: "2010s"
    content_era: Optional[str] = None     # Primary era discussed: "post_2008"
    content_year_min: Optional[int] = None  # Earliest year in content
    content_year_max: Optional[int] = None  # Latest year in content
    content_year_primary: Optional[int] = None  # Most frequent/central year

    # Period / Range (explicit from text like "2019-2021")
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    period_start_year: Optional[int] = None
    period_end_year: Optional[int] = None

    # Content timeline
    content_years: List[int] = field(default_factory=list)
    temporal_focus: Optional[str] = None  # "historical" | "current" | "future"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for ES indexing (only non-None values)."""
        result = {}
        if self.published_date:
            result["published_date"] = self.published_date
        if self.year is not None:
            result["year"] = self.year
        if self.month is not None:
            result["month"] = self.month
        if self.day is not None:
            result["day"] = self.day
        if self.yearmonth:
            result["yearmonth"] = self.yearmonth
        if self.decade:
            result["decade"] = self.decade
        if self.era:
            result["era"] = self.era
        if self.precision != "unknown":
            result["precision"] = self.precision
        if self.period_start:
            result["period_start"] = self.period_start
        if self.period_end:
            result["period_end"] = self.period_end
        if self.period_start_year is not None:
            result["period_start_year"] = self.period_start_year
        if self.period_end_year is not None:
            result["period_end_year"] = self.period_end_year
        if self.content_years:
            result["content_years"] = self.content_years
        if self.temporal_focus:
            result["temporal_focus"] = self.temporal_focus
        # Content time hierarchy
        if self.content_decade:
            result["content_decade"] = self.content_decade
        if self.content_era:
            result["content_era"] = self.content_era
        if self.content_year_min is not None:
            result["content_year_min"] = self.content_year_min
        if self.content_year_max is not None:
            result["content_year_max"] = self.content_year_max
        if self.content_year_primary is not None:
            result["content_year_primary"] = self.content_year_primary
        return result


def get_decade(year: int) -> str:
    """Convert year to decade string: 2024 -> '2020s'."""
    return f"{(year // 10) * 10}s"


def get_era(year: int) -> Optional[str]:
    """Get era name for a year."""
    for era_name, (start, end) in ERA_DEFINITIONS.items():
        if start <= year <= end:
            return era_name
    return None


def parse_date_string(date_str: str) -> Tuple[Optional[int], Optional[int], Optional[int], str]:
    """
    Parse various date formats and return (year, month, day, precision).

    Handles:
    - ISO formats: 2024-06-15, 2024-06-15T10:30:00Z
    - Human formats: June 15, 2024; 15 June 2024; June 2024
    - Year only: 2024
    - Decade: 1990s, 2020s
    """
    if not date_str:
        return None, None, None, "unknown"

    date_str = date_str.strip()

    # ISO format: 2024-06-15 or 2024-06-15T10:30:00Z
    iso_full = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})', date_str)
    if iso_full:
        return int(iso_full.group(1)), int(iso_full.group(2)), int(iso_full.group(3)), "day"

    # ISO month: 2024-06
    iso_month = re.match(r'^(\d{4})-(\d{1,2})$', date_str)
    if iso_month:
        return int(iso_month.group(1)), int(iso_month.group(2)), None, "month"

    # Year only: 2024
    year_only = re.match(r'^(\d{4})$', date_str)
    if year_only:
        return int(year_only.group(1)), None, None, "year"

    # Decade: 1990s, 2020s
    decade_match = re.match(r'^(\d{3})0s$', date_str)
    if decade_match:
        year = int(decade_match.group(1)) * 10
        return year, None, None, "decade"

    # Human format: "June 15, 2024" or "15 June 2024"
    human_day_first = re.match(r'^(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', date_str, re.IGNORECASE)
    if human_day_first:
        day = int(human_day_first.group(1))
        month = MONTH_NAMES.get(human_day_first.group(2).lower())
        year = int(human_day_first.group(3))
        return year, month, day, "day"

    human_month_first = re.match(r'^(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})', date_str, re.IGNORECASE)
    if human_month_first:
        month = MONTH_NAMES.get(human_month_first.group(1).lower())
        day = int(human_month_first.group(2))
        year = int(human_month_first.group(3))
        return year, month, day, "day"

    # Month year: "June 2024"
    month_year = re.match(r'^(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', date_str, re.IGNORECASE)
    if month_year:
        month = MONTH_NAMES.get(month_year.group(1).lower())
        year = int(month_year.group(2))
        return year, month, None, "month"

    # Abbreviated month: "Jun 2024"
    abbrev_month = re.match(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+(\d{4})', date_str, re.IGNORECASE)
    if abbrev_month:
        month = MONTH_NAMES.get(abbrev_month.group(1).lower())
        year = int(abbrev_month.group(2))
        return year, month, None, "month"

    return None, None, None, "unknown"


def parse_period_string(period_str: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Parse period/range strings.

    Handles:
    - Year range: 2019-2021, 2019 to 2021, 2019-21
    - Decade range: 1990s-2000s
    """
    if not period_str:
        return None, None

    # Year range: 2019-2021
    year_range = re.match(r'^(\d{4})[-–—](\d{4})$', period_str.strip())
    if year_range:
        return int(year_range.group(1)), int(year_range.group(2))

    # Short year range: 2019-21
    short_range = re.match(r'^(\d{4})[-–—](\d{2})$', period_str.strip())
    if short_range:
        start = int(short_range.group(1))
        end_suffix = int(short_range.group(2))
        century = (start // 100) * 100
        end = century + end_suffix
        return start, end

    # "to" format: 2019 to 2021
    to_range = re.match(r'^(\d{4})\s+to\s+(\d{4})$', period_str.strip(), re.IGNORECASE)
    if to_range:
        return int(to_range.group(1)), int(to_range.group(2))

    return None, None


def derive_temporal_hierarchy(
    date_str: Optional[str] = None,
    period_str: Optional[str] = None,
    content_years: Optional[List[int]] = None,
    text: Optional[str] = None
) -> TemporalResult:
    """
    Derive full temporal hierarchy from date inputs.

    Args:
        date_str: Point-in-time date string (e.g., "2024-06-15", "June 2024", "2024")
        period_str: Period/range string (e.g., "2019-2021")
        content_years: Pre-extracted years from content
        text: Raw text to extract years from (if content_years not provided)

    Returns:
        TemporalResult with all hierarchical fields populated
    """
    result = TemporalResult()

    # Parse point-in-time date
    if date_str:
        year, month, day, precision = parse_date_string(date_str)

        if year:
            result.year = year
            result.decade = get_decade(year)
            result.era = get_era(year)
            result.precision = precision

            if month:
                result.month = month
                result.yearmonth = f"{year:04d}-{month:02d}"

                if day:
                    result.day = day
                    result.published_date = f"{year:04d}-{month:02d}-{day:02d}T00:00:00Z"
                else:
                    result.published_date = f"{year:04d}-{month:02d}-01T00:00:00Z"
            else:
                result.published_date = f"{year:04d}-01-01T00:00:00Z"

    # Parse period/range
    if period_str:
        start_year, end_year = parse_period_string(period_str)
        if start_year and end_year:
            result.period_start = f"{start_year:04d}-01-01T00:00:00Z"
            result.period_end = f"{end_year:04d}-12-31T23:59:59Z"
            result.period_start_year = start_year
            result.period_end_year = end_year

            # Add all years in range to content_years
            period_years = list(range(start_year, end_year + 1))
            if content_years:
                result.content_years = sorted(set(content_years + period_years))
            else:
                result.content_years = period_years

            # If no point date, use period for precision
            if not result.precision or result.precision == "unknown":
                result.precision = "year"

    # Extract years from text if needed
    if text and not content_years:
        year_pattern = r'\b(19[5-9]\d|20[0-4]\d)\b'
        years_found = [int(y) for y in re.findall(year_pattern, text)]
        if years_found:
            result.content_years = sorted(set(result.content_years + years_found))
    elif content_years:
        result.content_years = sorted(set(result.content_years + content_years))

    # Determine temporal focus and CONTENT TIME hierarchy
    if result.content_years:
        current_year = datetime.now().year
        avg_year = sum(result.content_years) / len(result.content_years)

        if avg_year < current_year - 5:
            result.temporal_focus = "historical"
        elif avg_year > current_year:
            result.temporal_focus = "future"
        else:
            result.temporal_focus = "current"

        # === CONTENT TIME HIERARCHY ===
        result.content_year_min = min(result.content_years)
        result.content_year_max = max(result.content_years)

        # Primary year: median of content years (central tendency)
        sorted_years = sorted(result.content_years)
        mid_idx = len(sorted_years) // 2
        result.content_year_primary = sorted_years[mid_idx]

        # Content decade/era from primary year
        result.content_decade = get_decade(result.content_year_primary)
        result.content_era = get_era(result.content_year_primary)

    # If period exists but no content_years derived yet, use period midpoint
    elif result.period_start_year and result.period_end_year:
        result.content_year_min = result.period_start_year
        result.content_year_max = result.period_end_year
        result.content_year_primary = (result.period_start_year + result.period_end_year) // 2
        result.content_decade = get_decade(result.content_year_primary)
        result.content_era = get_era(result.content_year_primary)

    return result


def extract_periods_from_text(text: str) -> List[Tuple[int, int]]:
    """
    Extract period ranges from text.

    Finds patterns like:
    - "from 2019 to 2021"
    - "between 2019 and 2021"
    - "2019-2021"
    - "the 2019-21 period"
    """
    periods = []

    patterns = [
        r'from\s+(\d{4})\s+to\s+(\d{4})',
        r'between\s+(\d{4})\s+and\s+(\d{4})',
        r'(\d{4})[-–—](\d{4})\s+(?:period|era|time)',
        r'(?:during|in)\s+(\d{4})[-–—](\d{4})',
        r'(\d{4})[-–—](\d{2})\s+(?:period|era|time)',  # 2019-21
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                start = int(match.group(1))
                end_str = match.group(2)
                if len(end_str) == 2:
                    end = (start // 100) * 100 + int(end_str)
                else:
                    end = int(end_str)
                if 1950 <= start <= 2050 and 1950 <= end <= 2050 and start <= end:
                    periods.append((start, end))
            except (ValueError, IndexError):
                continue

    return list(set(periods))


# === ES Mapping Update ===

TEMPORAL_HIERARCHY_MAPPING = {
    "temporal": {
        "properties": {
            # Point in time (hierarchical)
            "published_date": {"type": "date"},
            "year": {"type": "integer"},
            "month": {"type": "integer"},
            "day": {"type": "integer"},
            "yearmonth": {"type": "keyword"},
            "decade": {"type": "keyword"},
            "era": {"type": "keyword"},
            "precision": {"type": "keyword"},

            # Period / Range
            "period_start": {"type": "date"},
            "period_end": {"type": "date"},
            "period_start_year": {"type": "integer"},
            "period_end_year": {"type": "integer"},

            # Content timeline
            "content_years": {"type": "long"},
            "temporal_focus": {"type": "keyword"},

            # Legacy fields (backward compat)
            "first_seen": {"type": "date"},
            "last_archived": {"type": "date"},
            "age_days": {"type": "integer"},
        }
    }
}


def update_es_mapping(es_client, index_name: str = "cymonides-2"):
    """
    Update Elasticsearch mapping with hierarchical temporal fields.

    Note: This only adds NEW fields. Existing data will need backfilling.
    """
    try:
        es_client.indices.put_mapping(
            index=index_name,
            body={"properties": TEMPORAL_HIERARCHY_MAPPING}
        )
        logger.info(f"Updated {index_name} mapping with temporal hierarchy fields")
        return True
    except Exception as e:
        logger.error(f"Failed to update mapping: {e}")
        return False


# === Convenience Function ===

def enrich_temporal_fields(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a document with hierarchical temporal fields.

    Takes existing temporal.published_date and derives all hierarchy fields.
    """
    temporal = doc.get("temporal", {})

    # Get existing date
    date_str = temporal.get("published_date")
    content_years = temporal.get("content_years", [])

    # Derive hierarchy
    result = derive_temporal_hierarchy(
        date_str=date_str,
        content_years=content_years
    )

    # Merge with existing temporal fields
    enriched = {**temporal, **result.to_dict()}

    # Preserve legacy fields
    for field in ["first_seen", "last_archived", "age_days", "checked_at",
                  "first_seen_wayback", "first_seen_commoncrawl", "first_seen_memento",
                  "last_seen_wayback", "last_seen_commoncrawl", "last_seen_memento"]:
        if field in temporal:
            enriched[field] = temporal[field]

    doc["temporal"] = enriched
    return doc


if __name__ == "__main__":
    # Test cases
    print("=== Temporal Hierarchy Derivation Tests ===\n")

    test_cases = [
        # (input, expected_precision)
        ("2024-06-15", "day"),
        ("2024-06-15T10:30:00Z", "day"),
        ("2024-06", "month"),
        ("June 2024", "month"),
        ("Jun 2024", "month"),
        ("15 June 2024", "day"),
        ("June 15, 2024", "day"),
        ("2024", "year"),
        ("1990s", "decade"),
    ]

    for date_str, expected_precision in test_cases:
        result = derive_temporal_hierarchy(date_str=date_str)
        status = "OK" if result.precision == expected_precision else "FAIL"
        print(f"[{status}] '{date_str}' -> precision={result.precision}")
        print(f"      year={result.year}, month={result.month}, day={result.day}")
        print(f"      yearmonth={result.yearmonth}, decade={result.decade}, era={result.era}")
        print()

    # Test period parsing
    print("=== Period Parsing Tests ===\n")
    period_cases = [
        "2019-2021",
        "2019-21",
        "2019 to 2021",
    ]

    for period in period_cases:
        result = derive_temporal_hierarchy(period_str=period)
        print(f"'{period}' -> start={result.period_start_year}, end={result.period_end_year}")
        print(f"      content_years={result.content_years}")
        print()

    # Test enrichment
    print("=== Document Enrichment Test ===\n")
    doc = {
        "temporal": {
            "published_date": "2024-06-15",
            "content_years": [2020, 2021, 2022],
            "first_seen": "2024-01-01T00:00:00Z"
        }
    }
    enriched = enrich_temporal_fields(doc)
    print(f"Input: published_date='2024-06-15', content_years=[2020, 2021, 2022]")
    print(f"Output: {enriched['temporal']}")
