#!/usr/bin/env python3
"""
Google Maps platform integration via Apify.

Uses Apify actor compass/crawler-google-places (nwua9Gu5YrADL7ZDj) for:
- Business/place search by location and query
- Place details extraction (reviews, images, contacts, hours)
- Contact enrichment from websites
- Business leads enrichment
- Social media profile enrichment
- Neighborhood/area data extraction

Full capabilities from the Google Maps Scraper actor.
"""

import os
import logging
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


# =============================================================================
# APIFY CONFIGURATION
# =============================================================================

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")
GOOGLE_MAPS_ACTOR_ID = "nwua9Gu5YrADL7ZDj"  # compass/crawler-google-places


def _get_apify_client():
    """Get Apify client."""
    if not APIFY_TOKEN:
        raise ValueError("APIFY_API_TOKEN or APIFY_TOKEN environment variable required")
    try:
        from apify_client import ApifyClient
        return ApifyClient(APIFY_TOKEN)
    except ImportError:
        raise ImportError("apify-client not installed. Run: pip install apify-client")


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class GoogleMapsPlace:
    """Structured Google Maps place data."""
    place_id: str
    title: str
    address: str = ""

    # Location
    neighborhood: str = ""
    street: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country_code: str = ""
    location: Dict[str, float] = field(default_factory=dict)  # lat, lng
    plus_code: str = ""

    # Business info
    category_name: str = ""
    categories: List[str] = field(default_factory=list)
    website: str = ""
    phone: str = ""
    phone_unformatted: str = ""
    price: str = ""

    # Ratings
    total_score: float = 0.0
    reviews_count: int = 0
    reviews_distribution: Dict[str, int] = field(default_factory=dict)

    # Status
    permanently_closed: bool = False
    temporarily_closed: bool = False

    # Additional
    opening_hours: List[Dict[str, str]] = field(default_factory=list)
    additional_info: Dict[str, Any] = field(default_factory=dict)
    images: List[str] = field(default_factory=list)

    # Social
    instagrams: List[str] = field(default_factory=list)
    facebooks: List[str] = field(default_factory=list)
    linkedins: List[str] = field(default_factory=list)
    twitters: List[str] = field(default_factory=list)

    # URLs
    url: str = ""
    image_url: str = ""
    menu: str = ""

    # Raw data
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "GoogleMapsPlace":
        """Create from Apify API response."""
        location = data.get("location", {}) or {}

        return cls(
            place_id=data.get("placeId", "") or data.get("fid", ""),
            title=data.get("title", ""),
            address=data.get("address", ""),
            neighborhood=data.get("neighborhood", ""),
            street=data.get("street", ""),
            city=data.get("city", ""),
            state=data.get("state", ""),
            postal_code=data.get("postalCode", ""),
            country_code=data.get("countryCode", ""),
            location={"lat": location.get("lat"), "lng": location.get("lng")} if location else {},
            plus_code=data.get("plusCode", ""),
            category_name=data.get("categoryName", ""),
            categories=data.get("categories", []) or [],
            website=data.get("website", ""),
            phone=data.get("phone", ""),
            phone_unformatted=data.get("phoneUnformatted", ""),
            price=data.get("price", ""),
            total_score=data.get("totalScore", 0.0) or 0.0,
            reviews_count=data.get("reviewsCount", 0) or 0,
            reviews_distribution=data.get("reviewsDistribution", {}) or {},
            permanently_closed=data.get("permanentlyClosed", False),
            temporarily_closed=data.get("temporarilyClosed", False),
            opening_hours=data.get("openingHours", []) or [],
            additional_info=data.get("additionalInfo", {}) or {},
            images=data.get("imageUrls", []) or [],
            instagrams=data.get("instagrams", []) or [],
            facebooks=data.get("facebooks", []) or [],
            linkedins=data.get("linkedIns", []) or [],
            twitters=data.get("twitters", []) or [],
            url=data.get("url", ""),
            image_url=data.get("imageUrl", ""),
            menu=data.get("menu", ""),
            raw=data,
        )


@dataclass
class NeighborhoodInfo:
    """Neighborhood information extracted from Google Maps."""
    neighborhood: str
    city: str
    state: str = ""
    country_code: str = ""
    postal_code: str = ""
    plus_code: str = ""
    location: Dict[str, float] = field(default_factory=dict)

    # Nearby places for context
    nearby_places: List[str] = field(default_factory=list)
    nearby_categories: List[str] = field(default_factory=list)

    # Area characteristics
    price_level: str = ""  # $ to $$$$
    popular_categories: List[str] = field(default_factory=list)


# =============================================================================
# CORE SCRAPING FUNCTIONS
# =============================================================================

def search_places(
    search_terms: Union[str, List[str]],
    location: Optional[str] = None,
    max_results: int = 50,
    *,
    # Geolocation
    country_code: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    custom_geolocation: Optional[Dict[str, Any]] = None,
    # Filters
    category_filters: Optional[List[str]] = None,
    min_stars: Optional[str] = None,  # "two", "three", "four", etc.
    website_filter: str = "allPlaces",  # "withWebsite", "withoutWebsite"
    skip_closed: bool = False,
    # Detail scraping
    scrape_details: bool = False,
    max_reviews: int = 0,
    max_images: int = 0,
    # Enrichment
    scrape_contacts: bool = False,
    max_leads: int = 0,
    language: str = "en",
    timeout_secs: int = 300,
) -> List[GoogleMapsPlace]:
    """
    Search Google Maps for places.

    Args:
        search_terms: Search query or list of queries
        location: Location query (e.g., "New York, USA")
        max_results: Maximum places per search term
        country_code: Country code (e.g., "us")
        city: City name
        state: State name
        postal_code: Postal code
        custom_geolocation: GeoJSON polygon/point for custom area
        category_filters: Filter by categories
        min_stars: Minimum star rating
        website_filter: Filter by website presence
        skip_closed: Skip closed places
        scrape_details: Scrape detail pages (slower but more data)
        max_reviews: Number of reviews to scrape
        max_images: Number of images to scrape
        scrape_contacts: Extract contacts from websites
        max_leads: Number of business leads per place
        language: Results language
        timeout_secs: Timeout in seconds

    Returns:
        List of GoogleMapsPlace objects
    """
    client = _get_apify_client()

    # Normalize search terms
    if isinstance(search_terms, str):
        search_terms = [search_terms]

    run_input = {
        "searchStringsArray": search_terms,
        "maxCrawledPlacesPerSearch": max_results,
        "language": language,
        "skipClosedPlaces": skip_closed,
        "website": website_filter,
        "scrapePlaceDetailPage": scrape_details,
        "maxReviews": max_reviews,
        "maxImages": max_images,
        "scrapeContacts": scrape_contacts,
        "maximumLeadsEnrichmentRecords": max_leads,
    }

    # Location
    if location:
        run_input["locationQuery"] = location
    if country_code:
        run_input["countryCode"] = country_code
    if city:
        run_input["city"] = city
    if state:
        run_input["state"] = state
    if postal_code:
        run_input["postalCode"] = postal_code
    if custom_geolocation:
        run_input["customGeolocation"] = custom_geolocation

    # Filters
    if category_filters:
        run_input["categoryFilterWords"] = category_filters
    if min_stars:
        run_input["placeMinimumStars"] = min_stars

    run = client.actor(GOOGLE_MAPS_ACTOR_ID).call(
        run_input=run_input,
        timeout_secs=timeout_secs,
    )

    results = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    return [GoogleMapsPlace.from_api(r) for r in results]


def get_place_by_id(place_id: str, scrape_details: bool = True) -> Optional[GoogleMapsPlace]:
    """
    Get a single place by Google Place ID.

    Args:
        place_id: Google Place ID (e.g., "ChIJreV9aqYWdkgROM_boL6YbwA")
        scrape_details: Whether to scrape full details

    Returns:
        GoogleMapsPlace or None
    """
    client = _get_apify_client()

    run_input = {
        "placeIds": [place_id],
        "scrapePlaceDetailPage": scrape_details,
    }

    run = client.actor(GOOGLE_MAPS_ACTOR_ID).call(run_input=run_input)
    results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    if results:
        return GoogleMapsPlace.from_api(results[0])
    return None


def get_places_by_url(urls: List[str], scrape_details: bool = True) -> List[GoogleMapsPlace]:
    """
    Get places from Google Maps URLs.

    Args:
        urls: List of Google Maps URLs
        scrape_details: Whether to scrape full details

    Returns:
        List of GoogleMapsPlace objects
    """
    client = _get_apify_client()

    run_input = {
        "startUrls": [{"url": url} for url in urls],
        "scrapePlaceDetailPage": scrape_details,
    }

    run = client.actor(GOOGLE_MAPS_ACTOR_ID).call(run_input=run_input)
    results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    return [GoogleMapsPlace.from_api(r) for r in results]


# =============================================================================
# NEIGHBORHOOD ENRICHMENT
# =============================================================================

def enrich_address_with_neighborhood(
    address: str,
    *,
    search_radius_km: float = 1.0,
    include_nearby: bool = True,
    max_nearby_places: int = 10,
) -> NeighborhoodInfo:
    """
    Enrich an address with neighborhood information from Google Maps.

    Args:
        address: Full address to enrich
        search_radius_km: Search radius in kilometers
        include_nearby: Include nearby places for context
        max_nearby_places: Maximum nearby places to include

    Returns:
        NeighborhoodInfo with neighborhood data
    """
    client = _get_apify_client()

    # Search for the address itself first
    run_input = {
        "searchStringsArray": [address],
        "maxCrawledPlacesPerSearch": 1,
        "scrapePlaceDetailPage": True,
        "language": "en",
    }

    run = client.actor(GOOGLE_MAPS_ACTOR_ID).call(run_input=run_input, timeout_secs=120)
    results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    if not results:
        logger.warning(f"No results for address: {address}")
        return NeighborhoodInfo(neighborhood="", city="")

    place = results[0]

    neighborhood = place.get("neighborhood", "")
    city = place.get("city", "")
    state = place.get("state", "")
    country_code = place.get("countryCode", "")
    postal_code = place.get("postalCode", "")
    plus_code = place.get("plusCode", "")
    location = place.get("location", {})

    nearby_places = []
    nearby_categories = []

    # Get nearby places if requested
    if include_nearby and location:
        nearby_input = {
            "customGeolocation": {
                "type": "Point",
                "coordinates": [location.get("lng"), location.get("lat")],
                "radiusKm": search_radius_km,
            },
            "searchStringsArray": ["*"],  # All places
            "maxCrawledPlacesPerSearch": max_nearby_places,
            "scrapePlaceDetailPage": False,
        }

        nearby_run = client.actor(GOOGLE_MAPS_ACTOR_ID).call(
            run_input=nearby_input, timeout_secs=180
        )
        nearby_results = list(client.dataset(nearby_run["defaultDatasetId"]).iterate_items())

        for nr in nearby_results:
            nearby_places.append(nr.get("title", ""))
            if nr.get("categoryName"):
                nearby_categories.append(nr.get("categoryName"))

    # Determine price level from nearby places
    price_levels = [r.get("price", "") for r in results if r.get("price")]
    price_level = max(set(price_levels), key=price_levels.count) if price_levels else ""

    # Get popular categories
    popular_categories = list(set(nearby_categories))[:10]

    return NeighborhoodInfo(
        neighborhood=neighborhood,
        city=city,
        state=state,
        country_code=country_code,
        postal_code=postal_code,
        plus_code=plus_code,
        location=location,
        nearby_places=nearby_places,
        nearby_categories=nearby_categories,
        price_level=price_level,
        popular_categories=popular_categories,
    )


def get_neighborhood_from_coordinates(
    lat: float,
    lng: float,
    radius_km: float = 0.5,
) -> NeighborhoodInfo:
    """
    Get neighborhood info from coordinates.

    Args:
        lat: Latitude
        lng: Longitude
        radius_km: Search radius

    Returns:
        NeighborhoodInfo
    """
    client = _get_apify_client()

    run_input = {
        "customGeolocation": {
            "type": "Point",
            "coordinates": [lng, lat],  # Note: GeoJSON order is [lng, lat]
            "radiusKm": radius_km,
        },
        "searchStringsArray": ["restaurant", "store", "business"],
        "maxCrawledPlacesPerSearch": 20,
        "scrapePlaceDetailPage": False,
    }

    run = client.actor(GOOGLE_MAPS_ACTOR_ID).call(run_input=run_input, timeout_secs=180)
    results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    if not results:
        return NeighborhoodInfo(
            neighborhood="",
            city="",
            location={"lat": lat, "lng": lng},
        )

    # Get neighborhood from first result with neighborhood data
    neighborhood = ""
    city = ""
    state = ""
    country_code = ""
    postal_code = ""

    for r in results:
        if r.get("neighborhood") and not neighborhood:
            neighborhood = r.get("neighborhood", "")
        if r.get("city") and not city:
            city = r.get("city", "")
        if r.get("state") and not state:
            state = r.get("state", "")
        if r.get("countryCode") and not country_code:
            country_code = r.get("countryCode", "")
        if r.get("postalCode") and not postal_code:
            postal_code = r.get("postalCode", "")

    nearby_places = [r.get("title", "") for r in results if r.get("title")]
    nearby_categories = [r.get("categoryName", "") for r in results if r.get("categoryName")]

    return NeighborhoodInfo(
        neighborhood=neighborhood,
        city=city,
        state=state,
        country_code=country_code,
        postal_code=postal_code,
        location={"lat": lat, "lng": lng},
        nearby_places=nearby_places,
        nearby_categories=list(set(nearby_categories)),
    )


# =============================================================================
# BUSINESS SEARCH HELPERS
# =============================================================================

def search_restaurants(
    location: str,
    max_results: int = 50,
    min_stars: Optional[str] = None,
    price_range: Optional[str] = None,
) -> List[GoogleMapsPlace]:
    """Search for restaurants in a location."""
    return search_places(
        ["restaurant", "cafe", "bistro", "diner"],
        location=location,
        max_results=max_results,
        min_stars=min_stars,
        scrape_details=True,
    )


def search_hotels(
    location: str,
    max_results: int = 50,
    min_stars: Optional[str] = None,
) -> List[GoogleMapsPlace]:
    """Search for hotels in a location."""
    return search_places(
        ["hotel", "motel", "inn", "resort"],
        location=location,
        max_results=max_results,
        min_stars=min_stars,
        scrape_details=True,
    )


def search_businesses(
    query: str,
    location: str,
    max_results: int = 50,
    with_website: bool = False,
    scrape_contacts: bool = False,
) -> List[GoogleMapsPlace]:
    """
    Search for businesses with optional contact enrichment.

    Args:
        query: Business type/category
        location: Location to search
        max_results: Maximum results
        with_website: Only include businesses with websites
        scrape_contacts: Extract contacts from websites

    Returns:
        List of GoogleMapsPlace objects
    """
    return search_places(
        query,
        location=location,
        max_results=max_results,
        website_filter="withWebsite" if with_website else "allPlaces",
        scrape_contacts=scrape_contacts,
        scrape_details=True,
    )


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    "GoogleMapsPlace",
    "NeighborhoodInfo",

    # Core functions
    "search_places",
    "get_place_by_id",
    "get_places_by_url",

    # Neighborhood
    "enrich_address_with_neighborhood",
    "get_neighborhood_from_coordinates",

    # Helpers
    "search_restaurants",
    "search_hotels",
    "search_businesses",

    # Config
    "GOOGLE_MAPS_ACTOR_ID",
]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 3:
        print("Usage: python google_maps.py <query> <location>")
        print("Example: python google_maps.py 'restaurant' 'New York, USA'")
        sys.exit(1)

    query = sys.argv[1]
    location = sys.argv[2]
    max_results = int(sys.argv[3]) if len(sys.argv) > 3 else 10

    places = search_places(query, location=location, max_results=max_results)

    for place in places:
        print(json.dumps({
            "title": place.title,
            "address": place.address,
            "neighborhood": place.neighborhood,
            "city": place.city,
            "rating": place.total_score,
            "reviews": place.reviews_count,
            "phone": place.phone,
            "website": place.website,
        }, indent=2))
