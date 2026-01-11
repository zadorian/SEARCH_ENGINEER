#!/usr/bin/env python3
"""
ALLDOM Native Bridge: WHOIS

Complete WHOIS intelligence module for domain investigation.

CAPABILITIES:
1. Current WHOIS     - fetch_current_whois_record()
2. Historic WHOIS    - get_whois_history() with date filtering
3. Reverse WHOIS     - By registrant (name/org/email), historic mode
4. Reverse Nameserver- Find domains sharing nameservers
5. Domain Clustering - cluster_domains_by_whois() finds ALL registrants over time
6. Entity Extraction - Extract persons, companies, emails, phones, addresses
7. Privacy Detection - 40+ privacy indicators
8. Batch Operations  - Concurrent lookups with semaphore

OPERATORS:
- whois:domain       - Current WHOIS lookup
- whois!domain       - Historic WHOIS (all records over time)
- whois?term         - Reverse WHOIS (by registrant name/email/org)
- ?ns:nameserver     - Reverse nameserver search
- ?cluster:domain    - Full domain clustering (historic + reverse)
"""

import os
import re
import time
import logging
import asyncio
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load environment
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

# =============================================================================
# API CONFIGURATION
# =============================================================================

WHOIS_HISTORY_URL = "https://whois-history.whoisxmlapi.com/api/v1"
WHOIS_REVERSE_URL = "https://reverse-whois-api.whoisxmlapi.com/api/v2"
WHOIS_LOOKUP_URL = "https://www.whoisxmlapi.com/whoisserver/WhoisService"

# Privacy indicators - if any appear, the field is redacted
PRIVACY_INDICATORS = [
    "data redacted",
    "redacted for privacy",
    "privacy protect",
    "whoisguard",
    "domains by proxy",
    "domainsbyproxy",
    "contact privacy",
    "private registration",
    "identity protect",
    "withheld for privacy",
    "not disclosed",
    "gdpr masked",
    "redacted",
    "privacyguardian",
    "registration private",
    "domain administrator",
    "domain admin",
    "dns admin",
    "hostmaster",
    "domain owner",
    "administrator",
    "admin contact",
    "technical contact",
    "tech contact",
    "abuse@",
    "postmaster@",
    "hostmaster@",
    "webmaster@",
    "noreply@",
    "no-reply@",
]

TECHNICAL_EMAIL_PREFIXES = (
    "abuse@",
    "whois@",
    "dns@",
    "hostmaster@",
    "postmaster@",
    "webmaster@",
    "noreply@",
    "no-reply@",
)

EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_REGEX = re.compile(r"\+?\d[\d\s().-]{6,}\d")


# =============================================================================
# EXCEPTIONS
# =============================================================================

class WhoisApiException(Exception):
    """Custom exception for WhoisXMLAPI errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


# =============================================================================
# DATACLASSES - Structured Output for Node Creation
# =============================================================================

@dataclass
class WhoisRecord:
    """WHOIS record with structured fields for deterministic node creation."""
    domain: str
    registrant_name: Optional[str] = None
    registrant_org: Optional[str] = None
    registrant_email: Optional[str] = None
    registrant_country: Optional[str] = None
    registrar: Optional[str] = None
    created_date: Optional[str] = None
    updated_date: Optional[str] = None
    expires_date: Optional[str] = None
    nameservers: List[str] = field(default_factory=list)
    status: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WhoisClusterResult:
    """Result from WHOIS clustering with confidence scoring for edge weight."""
    domain: str
    match_type: str  # registrant_name, registrant_org, registrant_email, nameserver
    match_value: str
    confidence: float
    whois_data: Optional[Dict[str, Any]] = None


@dataclass
class WhoisDiscoveryResponse:
    """Full discovery response with metadata."""
    query_domain: str
    method: str
    total_found: int
    results: List[WhoisClusterResult]
    elapsed_ms: int = 0
    api_calls_used: int = 0


# =============================================================================
# API CLIENT - Low-Level Functions
# =============================================================================

def _get_api_key() -> Optional[str]:
    """Get API key from environment (multiple fallbacks)."""
    return (
        os.getenv("WHOIS_API_KEY")
        or os.getenv("WHOISXMLAPI_KEY")
        or os.getenv("WHOISXML_API_KEY")
    )


def _make_request(
    method: str,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
    max_retries: int = 2,
) -> Dict[str, Any]:
    """HTTP request wrapper with retries and rate limit handling."""
    retries = 0
    headers: Dict[str, str] = {"Accept": "application/json"}

    while retries <= max_retries:
        try:
            if method.upper() == "GET":
                response = requests.get(url, params=params, headers=headers, timeout=timeout)
            elif method.upper() == "POST":
                headers["Content-Type"] = "application/json"
                response = requests.post(url, params=params, json=json_data, headers=headers, timeout=timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            if response.status_code == 429:
                wait_time = 2 * (retries + 1)
                if retries < max_retries:
                    time.sleep(wait_time)
                    retries += 1
                    continue
                raise WhoisApiException("Rate limit exceeded after max retries.", status_code=429, response_text=response.text)

            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as exc:
            raise WhoisApiException(f"HTTP Error: {exc.response.status_code}", status_code=exc.response.status_code, response_text=exc.response.text) from exc
        except requests.exceptions.RequestException as exc:
            raise WhoisApiException(f"Request failed: {exc}") from exc
        except ValueError as exc:
            raise WhoisApiException(f"Failed to decode JSON response: {exc}") from exc

    raise WhoisApiException("Max retries exceeded but no specific error caught.")


def normalize_domain(domain: str) -> str:
    """Normalize domain (lowercase, remove protocol/www/trailing slash)."""
    domain = (domain or "").strip().lower()
    if domain.startswith("http"):
        domain = re.sub(r"^https?://", "", domain)
    domain = domain.split("/")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def is_privacy_protected(value: Optional[str]) -> bool:
    """Check if WHOIS field value indicates privacy protection."""
    if not value:
        return False
    lower_value = value.lower()
    return any(indicator in lower_value for indicator in PRIVACY_INDICATORS)


def should_skip_email(email: str) -> bool:
    """Check if email should be skipped (technical/generic addresses)."""
    return email.lower().startswith(TECHNICAL_EMAIL_PREFIXES)


# =============================================================================
# CORE WHOIS OPERATIONS
# =============================================================================

def fetch_current_whois_record(domain: str, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
    """
    Get CURRENT WHOIS record for a domain.

    Returns raw API response dict or None if lookup fails.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.warning("[WHOIS] Missing API key for current lookup")
        return None

    domain = normalize_domain(domain)
    params = {
        "apiKey": api_key,
        "domainName": domain,
        "outputFormat": "JSON",
        "preferFresh": "1",
    }
    data = _make_request("GET", WHOIS_LOOKUP_URL, params=params, timeout=timeout)
    record = data.get("WhoisRecord", {})
    return record if isinstance(record, dict) and record else None


def get_whois_history(
    domain: str,
    since_date: Optional[str] = None,
    created_date_from: Optional[str] = None,
    created_date_to: Optional[str] = None,
    updated_date_from: Optional[str] = None,
    updated_date_to: Optional[str] = None,
    expired_date_from: Optional[str] = None,
    expired_date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get HISTORIC WHOIS records for a domain.

    Returns list of all WHOIS records over time, useful for:
    - Finding pre-privacy registrant data
    - Tracking ownership changes
    - Date-filtered queries
    """
    api_key = _get_api_key()
    if not api_key:
        logger.warning("[WHOIS] Missing API key for history lookup")
        return []

    domain = normalize_domain(domain)
    params: Dict[str, Any] = {
        "apiKey": api_key,
        "domainName": domain,
        "outputFormat": "JSON",
        "mode": "purchase",
    }
    if since_date:
        params["sinceDate"] = since_date
    if created_date_from:
        params["createdDateFrom"] = created_date_from
    if created_date_to:
        params["createdDateTo"] = created_date_to
    if updated_date_from:
        params["updatedDateFrom"] = updated_date_from
    if updated_date_to:
        params["updatedDateTo"] = updated_date_to
    if expired_date_from:
        params["expiredDateFrom"] = expired_date_from
    if expired_date_to:
        params["expiredDateTo"] = expired_date_to

    data = _make_request("GET", WHOIS_HISTORY_URL, params=params)
    records = data.get("records", [])
    return records if isinstance(records, list) else []


def reverse_whois_search(
    search_term: str,
    search_mode: str = "basicSearchTerms",
    search_field: Optional[str] = None,
    search_type: str = "historic",
    mode: str = "purchase",
) -> Dict[str, Any]:
    """
    REVERSE WHOIS search - find domains by registrant.

    Args:
        search_term: Registrant name, email, or organization
        search_mode: basicSearchTerms (default)
        search_field: Optional field filter (e.g., 'telephone')
        search_type: 'historic' (default) or 'current'
        mode: 'purchase' (default)

    Returns:
        Dict with domains list and count
    """
    api_key = _get_api_key()
    if not api_key:
        logger.warning("[WHOIS] Missing API key for reverse lookup")
        return {
            "search_term": search_term,
            "search_type": search_field or search_mode,
            "domains_count": 0,
            "domains": [],
            "error": "missing_api_key",
        }

    payload: Dict[str, Any] = {
        "apiKey": api_key,
        "searchType": search_type,
        "mode": mode,
        search_mode: {
            "include": [search_term],
        },
    }
    if search_field:
        payload[search_mode]["field"] = search_field

    data = _make_request("POST", WHOIS_REVERSE_URL, json_data=payload)
    return {
        "search_term": search_term,
        "search_type": search_field or search_mode,
        "domains_count": data.get("domainsCount", 0),
        "domains": data.get("domainsList", []) or data.get("domains", []),
    }


def reverse_nameserver_search(nameserver: str, limit: int = 100) -> List[str]:
    """
    REVERSE NAMESERVER search - find domains using same nameserver.

    Useful for infrastructure analysis and ownership clustering.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.warning("[WHOIS NS] Missing API key")
        return []

    nameserver = nameserver.lower().strip()
    payload = {
        "apiKey": api_key,
        "searchType": "current",
        "mode": "purchase",
        "basicSearchTerms": {"include": [nameserver]},
        "responseFormat": "json",
    }

    data = _make_request("POST", WHOIS_REVERSE_URL, json_data=payload, timeout=60.0)
    domains = data.get("domainsList", [])
    if not isinstance(domains, list):
        return []
    return [d for d in domains if isinstance(d, str)][:limit]


def whois_lookup(query: str, query_type: str = "domain") -> Dict[str, Any]:
    """
    Unified WHOIS lookup - routes to appropriate function based on query type.

    Args:
        query: Domain, email, phone, or search terms
        query_type: 'domain', 'email', 'terms', 'phone'

    Returns:
        Dict with results
    """
    try:
        if query_type == "domain":
            records = get_whois_history(query)
            return {
                "query": query,
                "query_type": query_type,
                "records": records,
                "count": len(records),
            }
        if query_type == "email":
            return reverse_whois_search(query, "basicSearchTerms")
        if query_type == "terms":
            return reverse_whois_search(query, "basicSearchTerms")
        if query_type == "phone":
            clean_number = re.sub(r"\D", "", query)
            return reverse_whois_search(clean_number, "basicSearchTerms", search_field="telephone")
        return reverse_whois_search(query, "basicSearchTerms")
    except WhoisApiException as exc:
        logger.warning("[WHOIS] Lookup error for %s: %s", query, exc)
        return {"query": query, "query_type": query_type, "error": str(exc)}
    except Exception as exc:
        logger.warning("[WHOIS] Unexpected error for %s: %s", query, exc)
        return {"query": query, "query_type": query_type, "error": f"Unexpected error: {exc}"}


# =============================================================================
# ENTITY EXTRACTION
# =============================================================================

def _format_address(contact: Dict[str, Any]) -> Optional[str]:
    """Format contact address from parts."""
    parts = [
        contact.get("street") or contact.get("street1"),
        contact.get("street2"),
        contact.get("city"),
        contact.get("state"),
        contact.get("postalCode") or contact.get("postal_code"),
        contact.get("country"),
    ]
    cleaned = [str(p).strip() for p in parts if p]
    return ", ".join(cleaned) if cleaned else None


def extract_contacts_from_record(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract all contacts (registrant, admin, tech, billing, zone) from WHOIS record."""
    contacts: List[Dict[str, Any]] = []
    for role, key in [
        ("registrant", "registrantContact"),
        ("administrative", "administrativeContact"),
        ("technical", "technicalContact"),
        ("billing", "billingContact"),
        ("zone", "zoneContact"),
    ]:
        raw_contact = record.get(key)
        if not isinstance(raw_contact, dict):
            continue

        name = raw_contact.get("name")
        organization = raw_contact.get("organization")
        email = raw_contact.get("email")
        phone = raw_contact.get("telephone")
        country = raw_contact.get("country")
        address = _format_address(raw_contact)

        if name and is_privacy_protected(str(name)):
            name = None
        if organization and is_privacy_protected(str(organization)):
            organization = None
        if email and is_privacy_protected(str(email)):
            email = None
        if phone and is_privacy_protected(str(phone)):
            phone = None

        if not any([name, organization, email, phone, address, country]):
            continue

        contacts.append({
            "role": role,
            "name": name,
            "organization": organization,
            "email": email,
            "phone": phone,
            "country": country,
            "address": address,
        })

    return contacts


def _looks_like_company(value: str) -> bool:
    """Check if name looks like a company (has corporate suffix)."""
    lowered = value.lower()
    return any(
        suffix in lowered
        for suffix in (" inc", " llc", " ltd", " corp", " gmbh", " srl", " sa", " s.a.", " plc", " co.", " company")
    )


def _extract_emails_from_text(text: str) -> List[str]:
    """Extract emails from raw text using regex."""
    emails = []
    for match in EMAIL_REGEX.findall(text or ""):
        if not should_skip_email(match):
            emails.append(match)
    return emails


def _extract_phones_from_text(text: str) -> List[str]:
    """Extract phone numbers from raw text using regex."""
    phones = []
    for match in PHONE_REGEX.findall(text or ""):
        cleaned = re.sub(r"\s+", " ", match).strip()
        if cleaned and len(re.sub(r"\D", "", cleaned)) >= 7:
            phones.append(cleaned)
    return phones


def extract_entities_from_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Extract ALL entities from WHOIS records.

    Returns list of entities with type, value, source, and role.
    Types: person, company, email, phone, address
    """
    entities: List[Dict[str, Any]] = []
    seen = set()

    for record in records:
        if not isinstance(record, dict):
            continue

        contacts = extract_contacts_from_record(record)
        for contact in contacts:
            role = contact.get("role")
            name = contact.get("name")
            org = contact.get("organization")
            email = contact.get("email")
            phone = contact.get("phone")
            address = contact.get("address")

            if name:
                entity_type = "company" if _looks_like_company(name) else "person"
                key = (entity_type, name.lower())
                if key not in seen:
                    entities.append({"type": entity_type, "value": name, "source": "whois", "role": role})
                    seen.add(key)

            if org:
                key = ("company", org.lower())
                if key not in seen:
                    entities.append({"type": "company", "value": org, "source": "whois", "role": role})
                    seen.add(key)

            if email:
                key = ("email", email.lower())
                if key not in seen:
                    entities.append({"type": "email", "value": email, "source": "whois", "role": role})
                    seen.add(key)

            if phone:
                key = ("phone", re.sub(r"\D", "", phone))
                if key not in seen:
                    entities.append({"type": "phone", "value": phone, "source": "whois", "role": role})
                    seen.add(key)

            if address:
                key = ("address", address.lower())
                if key not in seen:
                    entities.append({"type": "address", "value": address, "source": "whois", "role": role})
                    seen.add(key)

        # Also extract from raw text
        raw_text = record.get("rawText") or record.get("cleanText") or ""
        for email in _extract_emails_from_text(raw_text):
            key = ("email", email.lower())
            if key not in seen:
                entities.append({"type": "email", "value": email, "source": "whois", "role": "raw"})
                seen.add(key)

        for phone in _extract_phones_from_text(raw_text):
            key = ("phone", re.sub(r"\D", "", phone))
            if key not in seen:
                entities.append({"type": "phone", "value": phone, "source": "whois", "role": "raw"})
                seen.add(key)

    return entities


def summarize_whois_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create summary from WHOIS records (registrar, dates, nameservers, registrant)."""
    if not records:
        return {}

    # Find primary record (prefer non-redacted)
    primary = None
    for record in records:
        if not isinstance(record, dict):
            continue
        registrant = record.get("registrantContact") or {}
        name = registrant.get("name")
        org = registrant.get("organization")
        email = registrant.get("email")
        if any([name, org, email]) and not any(is_privacy_protected(str(v)) for v in [name, org, email] if v):
            primary = record
            break
    if primary is None:
        primary = records[0] if isinstance(records[0], dict) else None
    if not primary:
        return {}

    registrant = primary.get("registrantContact") or {}
    nameservers = primary.get("nameServers") or []
    if isinstance(nameservers, dict):
        nameservers = nameservers.get("hostNames", []) or []
    if isinstance(nameservers, str):
        nameservers = [nameservers]

    return {
        "registrar": primary.get("registrarName"),
        "dates": {
            "created": primary.get("createdDateISO8601") or primary.get("audit", {}).get("createdDate"),
            "updated": primary.get("updatedDateISO8601"),
            "expires": primary.get("expiresDateISO8601"),
        },
        "nameservers": [ns for ns in nameservers if isinstance(ns, str)],
        "registrant": {
            "name": registrant.get("name"),
            "organization": registrant.get("organization"),
            "email": registrant.get("email"),
            "phone": registrant.get("telephone"),
            "country": registrant.get("country"),
        },
        "contacts": extract_contacts_from_record(primary),
    }


# =============================================================================
# DISCOVERY FUNCTIONS - High-Level Operations
# =============================================================================

async def whois_lookup_async(domain: str, timeout: float = 30.0) -> Optional[WhoisRecord]:
    """
    Async WHOIS lookup returning structured WhoisRecord.
    """
    domain = normalize_domain(domain)
    logger.info(f"[WHOIS] Looking up: {domain}")

    try:
        whois_record = await asyncio.to_thread(fetch_current_whois_record, domain, timeout)
        if not whois_record:
            return None

        registrant = whois_record.get("registrant", {})

        nameservers = []
        ns_data = whois_record.get("nameServers", {})
        if isinstance(ns_data, dict):
            hostnames = ns_data.get("hostNames", [])
            if isinstance(hostnames, list):
                nameservers = [ns.lower() for ns in hostnames]

        status = whois_record.get("status", [])
        if isinstance(status, str):
            status = [status]

        return WhoisRecord(
            domain=domain,
            registrant_name=registrant.get("name"),
            registrant_org=registrant.get("organization"),
            registrant_email=registrant.get("email"),
            registrant_country=registrant.get("countryCode"),
            registrar=whois_record.get("registrarName"),
            created_date=whois_record.get("createdDate"),
            updated_date=whois_record.get("updatedDate"),
            expires_date=whois_record.get("expiresDate"),
            nameservers=nameservers,
            status=status,
            raw_data=whois_record,
        )
    except Exception as e:
        logger.error(f"[WHOIS] Lookup error: {e}")
        return None


def historic_whois_lookup_sync(domain: str) -> List[WhoisRecord]:
    """
    Get HISTORIC WHOIS records as structured WhoisRecord list.

    Returns historical records that may contain pre-privacy registrant data.
    """
    logger.info(f"[WHOIS History] Looking up historic records for: {domain}")

    try:
        records = get_whois_history(domain)
        if not records:
            logger.info(f"[WHOIS History] No historic records found for {domain}")
            return []

        logger.info(f"[WHOIS History] Found {len(records)} historic records for {domain}")

        historic_records = []
        for rec in records:
            registrant = rec.get("registrantContact", {})

            nameservers = []
            ns_data = rec.get("nameServers", [])
            if isinstance(ns_data, list):
                for ns in ns_data:
                    if isinstance(ns, str):
                        nameservers.extend([n.strip().lower() for n in ns.split('|')])

            historic_records.append(WhoisRecord(
                domain=domain,
                registrant_name=registrant.get("name"),
                registrant_org=registrant.get("organization"),
                registrant_email=registrant.get("email"),
                registrant_country=registrant.get("country"),
                registrar=rec.get("registrarName"),
                created_date=rec.get("audit", {}).get("createdDate") or rec.get("createdDateISO8601"),
                updated_date=rec.get("updatedDateISO8601"),
                expires_date=rec.get("expiresDateISO8601"),
                nameservers=nameservers,
                status=rec.get("status", []),
                raw_data=rec
            ))

        return historic_records

    except Exception as e:
        logger.error(f"[WHOIS History] Lookup error: {e}")
        return []


async def historic_whois_lookup(domain: str) -> List[WhoisRecord]:
    """Async wrapper for historic_whois_lookup_sync."""
    return await asyncio.to_thread(historic_whois_lookup_sync, domain)


def find_usable_registrant_from_history(records: List[WhoisRecord]) -> Optional[WhoisRecord]:
    """Find first historic record with non-privacy-protected registrant data."""
    for record in records:
        has_usable_name = record.registrant_name and not is_privacy_protected(record.registrant_name)
        has_usable_org = record.registrant_org and not is_privacy_protected(record.registrant_org)
        has_usable_email = record.registrant_email and not is_privacy_protected(record.registrant_email)

        if has_usable_name or has_usable_org or has_usable_email:
            logger.info(f"[WHOIS History] Found usable historic record from {record.created_date}")
            return record

    return None


def find_all_distinct_registrants(records: List[WhoisRecord]) -> List[Dict[str, str]]:
    """
    Find ALL distinct registrant names/orgs/emails from historic records.

    Captures ownership changes over time - crucial for domain attribution.
    """
    seen = set()
    registrants = []

    for record in records:
        if record.registrant_name and not is_privacy_protected(record.registrant_name):
            name_normalized = record.registrant_name.strip().upper()
            if name_normalized and name_normalized not in seen and name_normalized != 'NA':
                seen.add(name_normalized)
                registrants.append({
                    'value': record.registrant_name.strip(),
                    'type': 'name',
                    'date': record.created_date
                })

        if record.registrant_org and not is_privacy_protected(record.registrant_org):
            org_normalized = record.registrant_org.strip().upper()
            if org_normalized and org_normalized not in seen and org_normalized != 'NA':
                seen.add(org_normalized)
                registrants.append({
                    'value': record.registrant_org.strip(),
                    'type': 'org',
                    'date': record.created_date
                })

        if record.registrant_email and not is_privacy_protected(record.registrant_email):
            email_normalized = record.registrant_email.strip().lower()
            if email_normalized and email_normalized not in seen:
                seen.add(email_normalized)
                registrants.append({
                    'value': record.registrant_email.strip(),
                    'type': 'email',
                    'date': record.created_date
                })

    logger.info(f"[WHOIS History] Found {len(registrants)} distinct registrants")
    return registrants


def reverse_whois_by_registrant_sync(registrant: str, limit: int = 100) -> List[WhoisClusterResult]:
    """
    REVERSE WHOIS by registrant - find domains registered by same person/org.

    Uses historic mode to find domains even when current WHOIS is privacy-protected.
    """
    logger.info(f"[WHOIS Reverse] Searching for registrant: {registrant}")
    results = []

    try:
        response = reverse_whois_search(registrant, "basicSearchTerms")
        domains = response.get('domains', [])
        count = response.get('domains_count', 0)

        logger.info(f"[WHOIS Reverse] Found {count} domains for '{registrant}'")

        for domain in domains[:limit]:
            if isinstance(domain, str):
                results.append(WhoisClusterResult(
                    domain=domain,
                    match_type="registrant_historic",
                    match_value=registrant,
                    confidence=0.9
                ))

    except Exception as e:
        logger.error(f"[WHOIS Reverse] Error: {e}")

    return results[:limit]


async def reverse_whois_by_registrant(registrant: str, limit: int = 100) -> List[WhoisClusterResult]:
    """Async wrapper for reverse_whois_by_registrant_sync."""
    return await asyncio.to_thread(reverse_whois_by_registrant_sync, registrant, limit)


async def find_domains_by_nameserver(nameserver: str, limit: int = 100) -> List[WhoisClusterResult]:
    """
    Find domains using same nameserver (infrastructure clustering).
    """
    nameserver = nameserver.lower().strip()
    logger.info(f"[WHOIS NS] Finding domains using nameserver: {nameserver}")
    results = []

    try:
        domains_list = await asyncio.to_thread(reverse_nameserver_search, nameserver, limit)
        for domain in domains_list[:limit]:
            if isinstance(domain, str):
                results.append(WhoisClusterResult(
                    domain=domain,
                    match_type="nameserver",
                    match_value=nameserver,
                    confidence=0.85
                ))
        logger.info(f"[WHOIS NS] Found {len(domains_list)} domains using {nameserver}")
    except Exception as e:
        logger.error(f"[WHOIS NS] Error: {e}")

    return results[:limit]


async def cluster_domains_by_whois(
    domain: str,
    include_nameserver: bool = True,
    limit: int = 100
) -> WhoisDiscoveryResponse:
    """
    COMPREHENSIVE domain clustering via WHOIS data.

    This is the main clustering function that:
    1. Looks up current WHOIS for the target domain
    2. Fetches HISTORIC WHOIS to find ALL distinct registrants over time
    3. Searches for other domains for EACH historic registrant
    4. Optionally searches by nameserver for infrastructure analysis

    Returns WhoisDiscoveryResponse with clustered domains and confidence scores.
    """
    start_time = time.time()
    logger.info(f"[WHOIS Cluster] Starting comprehensive clustering for: {domain}")

    whois_record = await whois_lookup_async(domain)
    api_calls = 1

    if not whois_record:
        logger.warning(f"[WHOIS Cluster] Could not get WHOIS for {domain}")
        return WhoisDiscoveryResponse(
            query_domain=domain,
            method="whois_cluster",
            total_found=0,
            results=[],
            elapsed_ms=int((time.time() - start_time) * 1000),
            api_calls_used=1
        )

    all_results: List[WhoisClusterResult] = []
    searched_registrants: Set[str] = set()

    # ALWAYS fetch historic WHOIS to find ALL distinct registrants
    logger.info(f"[WHOIS Cluster] Fetching historic WHOIS...")
    historic_records = await historic_whois_lookup(domain)
    api_calls += 1

    if historic_records:
        distinct_registrants = find_all_distinct_registrants(historic_records)
        logger.info(f"[WHOIS Cluster] Found {len(distinct_registrants)} distinct historic registrants")

        for reg in distinct_registrants:
            reg_value = reg['value']
            normalized = reg_value.strip().upper()
            if normalized in searched_registrants:
                continue
            searched_registrants.add(normalized)

            logger.info(f"[WHOIS Cluster] Searching for '{reg_value}'...")
            try:
                results = await reverse_whois_by_registrant(reg_value, limit)
                logger.info(f"[WHOIS Cluster]   -> Found {len(results)} domains")
                all_results.extend(results)
                api_calls += 1
            except Exception as e:
                logger.warning(f"[WHOIS Cluster] Error searching for '{reg_value}': {e}")

    else:
        # Fall back to current WHOIS
        logger.info(f"[WHOIS Cluster] No historic records, using current WHOIS only")
        if whois_record.registrant_org and not is_privacy_protected(whois_record.registrant_org):
            results = await reverse_whois_by_registrant(whois_record.registrant_org, limit)
            all_results.extend(results)
            api_calls += 1

        if (whois_record.registrant_name and
            whois_record.registrant_name != whois_record.registrant_org and
            not is_privacy_protected(whois_record.registrant_name)):
            results = await reverse_whois_by_registrant(whois_record.registrant_name, limit)
            all_results.extend(results)
            api_calls += 1

        if whois_record.registrant_email and not is_privacy_protected(whois_record.registrant_email):
            results = await reverse_whois_by_registrant(whois_record.registrant_email, limit)
            all_results.extend(results)
            api_calls += 1

    # Nameserver clustering
    if include_nameserver and whois_record.nameservers:
        for ns in whois_record.nameservers[:2]:
            ns_results = await find_domains_by_nameserver(ns, limit // 2)
            all_results.extend(ns_results)
            api_calls += 1

    # Deduplicate and remove self
    seen = set()
    unique_results = []
    for r in all_results:
        if r.domain not in seen and r.domain != domain:
            seen.add(r.domain)
            unique_results.append(r)

    unique_results.sort(key=lambda x: x.confidence, reverse=True)

    elapsed_ms = int((time.time() - start_time) * 1000)
    method = "whois_cluster_all_historic" if historic_records else "whois_cluster"

    logger.info(f"[WHOIS Cluster] Found {len(unique_results)} related domains in {elapsed_ms}ms")

    return WhoisDiscoveryResponse(
        query_domain=domain,
        method=method,
        total_found=len(unique_results),
        results=unique_results[:limit],
        elapsed_ms=elapsed_ms,
        api_calls_used=api_calls
    )


async def batch_whois_lookup(
    domains: List[str],
    max_concurrent: int = 5
) -> Dict[str, WhoisRecord]:
    """
    Batch WHOIS lookup with concurrency control.
    """
    results = {}
    semaphore = asyncio.Semaphore(max_concurrent)

    async def lookup_with_semaphore(domain: str):
        async with semaphore:
            return domain, await whois_lookup_async(domain)

    tasks = [lookup_with_semaphore(d) for d in domains]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    for resp in responses:
        if isinstance(resp, Exception):
            logger.error(f"[WHOIS Batch] Error: {resp}")
            continue
        domain, record = resp
        if record:
            results[domain] = record

    return results


# =============================================================================
# OPERATOR ENTRY POINTS - For ALLDOM OPERATOR_ROUTES
# =============================================================================

async def lookup(domain: str, **kwargs) -> Dict[str, Any]:
    """
    Current WHOIS lookup (whois:domain operator).

    Returns structured dict for node creation.
    """
    record = await whois_lookup_async(domain)
    if not record:
        return {"error": f"No WHOIS data found for {domain}", "domain": domain}

    return {
        "domain": record.domain,
        "registrant_name": record.registrant_name,
        "registrant_org": record.registrant_org,
        "registrant_email": record.registrant_email,
        "registrant_country": record.registrant_country,
        "registrar": record.registrar,
        "created_date": record.created_date,
        "updated_date": record.updated_date,
        "expires_date": record.expires_date,
        "nameservers": record.nameservers,
        "status": record.status,
    }


async def history(domain: str, **kwargs) -> Dict[str, Any]:
    """
    Historic WHOIS lookup (whois!domain operator).

    Returns all WHOIS records over time with distinct registrants.
    """
    records = await historic_whois_lookup(domain)
    if not records:
        return {"error": f"No historic WHOIS data found for {domain}", "domain": domain, "records": []}

    distinct_registrants = find_all_distinct_registrants(records)

    return {
        "domain": domain,
        "record_count": len(records),
        "distinct_registrants": distinct_registrants,
        "records": [
            {
                "registrant_name": r.registrant_name,
                "registrant_org": r.registrant_org,
                "registrant_email": r.registrant_email,
                "created_date": r.created_date,
                "registrar": r.registrar,
            }
            for r in records
        ],
    }


async def reverse(query: str, query_type: str = "registrant", **kwargs) -> Dict[str, Any]:
    """
    Reverse WHOIS search (whois?term operator).

    Finds domains registered by the same person/org/email.
    """
    results = await reverse_whois_by_registrant(query, limit=kwargs.get("limit", 100))

    return {
        "query": query,
        "query_type": query_type,
        "domains_count": len(results),
        "domains": [
            {
                "domain": r.domain,
                "match_type": r.match_type,
                "match_value": r.match_value,
                "confidence": r.confidence,
            }
            for r in results
        ],
    }


async def nameserver(ns: str, **kwargs) -> Dict[str, Any]:
    """
    Reverse nameserver search (?ns:nameserver operator).

    Finds domains using the same nameserver.
    """
    results = await find_domains_by_nameserver(ns, limit=kwargs.get("limit", 100))

    return {
        "nameserver": ns,
        "domains_count": len(results),
        "domains": [
            {
                "domain": r.domain,
                "match_type": r.match_type,
                "confidence": r.confidence,
            }
            for r in results
        ],
    }


async def cluster(domain: str, **kwargs) -> Dict[str, Any]:
    """
    Full domain clustering (?cluster:domain operator).

    Comprehensive clustering using historic WHOIS, reverse lookups, and nameserver analysis.
    """
    response = await cluster_domains_by_whois(
        domain,
        include_nameserver=kwargs.get("include_nameserver", True),
        limit=kwargs.get("limit", 100)
    )

    return {
        "query_domain": response.query_domain,
        "method": response.method,
        "total_found": response.total_found,
        "elapsed_ms": response.elapsed_ms,
        "api_calls_used": response.api_calls_used,
        "results": [
            {
                "domain": r.domain,
                "match_type": r.match_type,
                "match_value": r.match_value,
                "confidence": r.confidence,
            }
            for r in response.results
        ],
    }


async def entities(domain: str, **kwargs) -> Dict[str, Any]:
    """
    Extract entities from WHOIS records.

    Returns persons, companies, emails, phones, addresses found in WHOIS data.
    """
    records = get_whois_history(domain)
    if not records:
        return {"error": f"No WHOIS data found for {domain}", "domain": domain, "entities": []}

    extracted = extract_entities_from_records(records)

    return {
        "domain": domain,
        "entity_count": len(extracted),
        "entities": extracted,
    }


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ALLDOM WHOIS Bridge")
    parser.add_argument("domain", help="Target domain (e.g., example.com)")
    parser.add_argument("-c", "--cluster", action="store_true", help="Run full clustering")
    parser.add_argument("-H", "--history", action="store_true", help="Get historic WHOIS")
    parser.add_argument("-r", "--reverse", help="Reverse search by registrant")
    parser.add_argument("-n", "--nameserver", help="Reverse search by nameserver")
    parser.add_argument("-l", "--limit", type=int, default=50, help="Max results")

    args = parser.parse_args()

    async def main():
        if args.cluster:
            print(f"\n[CLUSTER] {args.domain}")
            response = await cluster_domains_by_whois(args.domain, limit=args.limit)
            print(f"Found {response.total_found} related domains in {response.elapsed_ms}ms")
            for r in response.results[:20]:
                print(f"  {r.domain} ({r.match_type}: {r.match_value}) [{r.confidence:.0%}]")
        elif args.history:
            print(f"\n[HISTORY] {args.domain}")
            records = await historic_whois_lookup(args.domain)
            registrants = find_all_distinct_registrants(records)
            print(f"Found {len(records)} records, {len(registrants)} distinct registrants")
            for reg in registrants:
                print(f"  {reg['type']}: {reg['value']} (from {reg['date']})")
        elif args.reverse:
            print(f"\n[REVERSE] {args.reverse}")
            results = await reverse_whois_by_registrant(args.reverse, args.limit)
            print(f"Found {len(results)} domains")
            for r in results[:20]:
                print(f"  {r.domain}")
        elif args.nameserver:
            print(f"\n[NAMESERVER] {args.nameserver}")
            results = await find_domains_by_nameserver(args.nameserver, args.limit)
            print(f"Found {len(results)} domains")
            for r in results[:20]:
                print(f"  {r.domain}")
        else:
            print(f"\n[LOOKUP] {args.domain}")
            record = await whois_lookup_async(args.domain)
            if record:
                print(f"Registrant: {record.registrant_name or record.registrant_org}")
                print(f"Email: {record.registrant_email}")
                print(f"Registrar: {record.registrar}")
                print(f"Created: {record.created_date}")
                print(f"Nameservers: {', '.join(record.nameservers)}")
            else:
                print("WHOIS lookup failed")

    asyncio.run(main())
