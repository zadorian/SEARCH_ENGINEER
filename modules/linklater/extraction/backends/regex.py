"""
Regex Backend for Entity Extraction

Fallback extraction using regex patterns only (no API required).
Based on enrichment/entity_patterns.py patterns.
"""

import re
from typing import List
from ..models import Entity, ExtractionResult


# Person name patterns
PERSON_PATTERNS = [
    # Title + Name
    r'(?:Mr\.|Ms\.|Mrs\.|Dr\.|Prof\.)\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
    # Name, Title
    r'([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*,\s*(?:CEO|CFO|CTO|COO|CMO|President|Director|Manager|Founder)',
    # Title Name (CEO John Smith)
    r'(?:CEO|CFO|CTO|COO|CMO|President|Director|Manager|Founder|Owner|Partner|Chief|Head of|VP|Vice President|Chairman)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
    # Name said/stated
    r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:said|stated|announced|reported|explained|commented)',
    # by/author Name
    r'(?:by|author|contact|written by)\s*:?\s*([A-Z][a-z]+\s+[A-Z][a-z]+)',
]

# Company patterns
COMPANY_PATTERNS = [
    # Legal suffixes
    r'([A-Z][A-Za-z\s&]+(?:Inc\.|LLC|Ltd\.|Corp\.|Corporation|Company|Group|Holdings|Partners|Associates|Solutions|Technologies|Services|Consulting|International))',
    # Copyright Company
    r'©\s*\d{4}\s*([A-Z][A-Za-z\s&]+)',
    # Founded by Company
    r'(?:About|Founded by|Owned by|Partner with|Client)\s+([A-Z][A-Za-z\s&]+)',
]

# Email pattern
EMAIL_PATTERN = r'[\w.-]+@[\w.-]+\.\w+'

# Phone patterns
PHONE_PATTERNS = [
    r'\+1[\s\-\.]?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}',  # US +1
    r'\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}',  # US local
    r'\+\d{1,3}[\s\-\.]?\d{2,4}[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,4}',  # International
]


class RegexBackend:
    """Regex-only entity extraction backend."""

    async def extract(
        self,
        html: str,
        url: str = "",
        entity_types: List[str] = None
    ) -> ExtractionResult:
        """Extract entities from HTML using regex patterns."""
        from bs4 import BeautifulSoup

        result = ExtractionResult()

        # Convert HTML to text
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(separator=' ')

        # Track seen values to avoid duplicates
        seen_persons = set()
        seen_companies = set()
        seen_emails = set()
        seen_phones = set()

        # Extract persons
        if entity_types is None or "person" in entity_types:
            for pattern in PERSON_PATTERNS:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    name = match.group(1).strip() if match.lastindex else match.group().strip()
                    # Basic validation
                    if len(name) > 3 and ' ' in name and name.lower() not in seen_persons:
                        seen_persons.add(name.lower())
                        result.persons.append(Entity(
                            value=name,
                            type="person",
                            archive_urls=[url] if url else []
                        ))

        # Extract companies
        if entity_types is None or "company" in entity_types:
            for pattern in COMPANY_PATTERNS:
                for match in re.finditer(pattern, text):
                    name = match.group(1).strip() if match.lastindex else match.group().strip()
                    if len(name) > 3 and name.lower() not in seen_companies:
                        seen_companies.add(name.lower())
                        result.companies.append(Entity(
                            value=name,
                            type="company",
                            archive_urls=[url] if url else []
                        ))

        # Extract emails
        if entity_types is None or "email" in entity_types:
            for email in re.findall(EMAIL_PATTERN, html):
                email = email.lower()
                if email not in seen_emails:
                    seen_emails.add(email)
                    result.emails.append(Entity(
                        value=email,
                        type="email",
                        archive_urls=[url] if url else []
                    ))

        # Extract phones
        if entity_types is None or "phone" in entity_types:
            for pattern in PHONE_PATTERNS:
                for phone in re.findall(pattern, text):
                    cleaned = re.sub(r'[^\d+]', '', phone)
                    if len(cleaned) >= 10 and cleaned not in seen_phones:
                        seen_phones.add(cleaned)
                        result.phones.append(Entity(
                            value=phone.strip(),
                            type="phone",
                            archive_urls=[url] if url else []
                        ))

        return result
