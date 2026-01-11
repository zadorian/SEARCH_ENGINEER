"""
Targeted search taxonomy aligned to grid filter dimensions.

Location -> source dimensions (country, format, language, date, category)
Subject -> entity and concept dimensions
Nexus -> query/operator dimensions
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

TARGETED_SEARCH_TAXONOMY: Dict[str, Dict[str, List[str]]] = {
    "location": {
        "country": ["location", "location_improved", "address"],
        "domain": ["site", "indom", "alldom", "ip", "related", "link"],
        "format": ["filetype", "pdf", "document", "image", "video", "audio", "reverse_image"],
        "language": ["language", "language_not"],
        "date": ["date"],
        "category": [
            "news",
            "blog",
            "forum",
            "review",
            "social_media",
            "public_records",
            "book",
            "feed",
            "tor",
            "huggingface",
            "domain_intel",
        ],
    },
    "subject": {
        "entity": ["author_search"],
        "concept": ["event", "academic", "medical", "crypto", "product", "edu", "recruitment"],
    },
    "nexus": {
        "query_ops": ["definitional", "inurl", "intext", "inanchor", "title", "anchor", "script"],
    },
}


def flatten_taxonomy(
    taxonomy: Dict[str, Dict[str, Iterable[str]]] = TARGETED_SEARCH_TAXONOMY,
) -> Dict[str, Tuple[str, str]]:
    """Return a mapping of search_type -> (dimension, subdimension)."""
    flattened: Dict[str, Tuple[str, str]] = {}
    for dimension, groups in taxonomy.items():
        for subdimension, search_types in groups.items():
            for search_type in search_types:
                flattened[search_type] = (dimension, subdimension)
    return flattened


SEARCH_TYPE_INDEX = flatten_taxonomy()
