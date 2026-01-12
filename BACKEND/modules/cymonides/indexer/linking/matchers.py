"""
Entity Matchers - Specialized matchers for different entity types
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
import re
import hashlib


class BaseMatcher(ABC):
    """Base class for entity matchers"""
    
    @abstractmethod
    def normalize(self, value: str) -> str:
        """Normalize value for matching"""
        pass
    
    @abstractmethod
    def extract(self, text: str) -> List[str]:
        """Extract matchable values from text"""
        pass
    
    @abstractmethod
    def similarity(self, a: str, b: str) -> float:
        """Calculate similarity between two values (0-1)"""
        pass
    
    def is_valid(self, value: str) -> bool:
        """Check if value is valid for this matcher"""
        return bool(value and value.strip())


class EmailMatcher(BaseMatcher):
    """Matcher for email addresses"""
    
    EMAIL_PATTERN = re.compile(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        re.IGNORECASE
    )
    
    def normalize(self, value: str) -> str:
        """Normalize email to lowercase"""
        if not value:
            return ""
        email = value.lower().strip()
        # Handle common typos
        email = email.replace(" ", "")
        email = email.replace("..", ".")
        return email
    
    def extract(self, text: str) -> List[str]:
        """Extract email addresses from text"""
        if not text:
            return []
        matches = self.EMAIL_PATTERN.findall(text)
        return [self.normalize(m) for m in matches]
    
    def similarity(self, a: str, b: str) -> float:
        """Exact match for emails"""
        a_norm = self.normalize(a)
        b_norm = self.normalize(b)
        if a_norm == b_norm:
            return 1.0
        # Check if same local part different domain
        if "@" in a_norm and "@" in b_norm:
            a_local = a_norm.split("@")[0]
            b_local = b_norm.split("@")[0]
            if a_local == b_local:
                return 0.7
        return 0.0
    
    def is_valid(self, value: str) -> bool:
        if not value:
            return False
        normalized = self.normalize(value)
        return bool(self.EMAIL_PATTERN.match(normalized))
    
    def get_domain(self, email: str) -> Optional[str]:
        """Extract domain from email"""
        normalized = self.normalize(email)
        if "@" in normalized:
            return normalized.split("@")[1]
        return None


class DomainMatcher(BaseMatcher):
    """Matcher for domain names"""
    
    DOMAIN_PATTERN = re.compile(
        r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}",
        re.IGNORECASE
    )
    
    def normalize(self, value: str) -> str:
        """Normalize domain"""
        if not value:
            return ""
        domain = value.lower().strip()
        # Remove protocol
        if "://" in domain:
            domain = domain.split("://")[1]
        # Remove path
        domain = domain.split("/")[0]
        # Remove port
        domain = domain.split(":")[0]
        # Remove www prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    
    def extract(self, text: str) -> List[str]:
        """Extract domains from text"""
        if not text:
            return []
        matches = self.DOMAIN_PATTERN.findall(text)
        return list(set(self.normalize(m) for m in matches))
    
    def similarity(self, a: str, b: str) -> float:
        """Compare domain similarity"""
        a_norm = self.normalize(a)
        b_norm = self.normalize(b)
        if a_norm == b_norm:
            return 1.0
        # Check if same registered domain
        a_parts = a_norm.split(".")
        b_parts = b_norm.split(".")
        if len(a_parts) >= 2 and len(b_parts) >= 2:
            if a_parts[-2:] == b_parts[-2:]:
                return 0.8
        return 0.0
    
    def is_valid(self, value: str) -> bool:
        if not value:
            return False
        normalized = self.normalize(value)
        return bool(self.DOMAIN_PATTERN.match(normalized))
    
    def get_tld(self, domain: str) -> Optional[str]:
        """Get TLD from domain"""
        normalized = self.normalize(domain)
        if "." in normalized:
            return normalized.split(".")[-1]
        return None


class PhoneMatcher(BaseMatcher):
    """Matcher for phone numbers"""
    
    PHONE_PATTERN = re.compile(
        r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}"
    )
    
    def normalize(self, value: str) -> str:
        """Normalize phone to digits only (with + prefix if present)"""
        if not value:
            return ""
        phone = value.strip()
        has_plus = phone.startswith("+")
        digits = re.sub(r"[^0-9]", "", phone)
        if has_plus:
            digits = "+" + digits
        return digits
    
    def extract(self, text: str) -> List[str]:
        """Extract phone numbers from text"""
        if not text:
            return []
        matches = self.PHONE_PATTERN.findall(text)
        normalized = [self.normalize(m) for m in matches]
        # Filter out too short/long numbers
        return [n for n in normalized if 7 <= len(n.replace("+", "")) <= 15]
    
    def similarity(self, a: str, b: str) -> float:
        """Compare phone number similarity"""
        a_norm = self.normalize(a)
        b_norm = self.normalize(b)
        if a_norm == b_norm:
            return 1.0
        # Check if one is suffix of other (country code difference)
        a_digits = a_norm.replace("+", "")
        b_digits = b_norm.replace("+", "")
        if a_digits.endswith(b_digits) or b_digits.endswith(a_digits):
            return 0.9
        return 0.0
    
    def is_valid(self, value: str) -> bool:
        if not value:
            return False
        normalized = self.normalize(value)
        digits = normalized.replace("+", "")
        return 7 <= len(digits) <= 15


class NameMatcher(BaseMatcher):
    """Matcher for person/company names"""
    
    def normalize(self, value: str) -> str:
        """Normalize name"""
        if not value:
            return ""
        name = value.strip()
        # Remove extra whitespace
        name = " ".join(name.split())
        # Lowercase for comparison
        name = name.lower()
        return name
    
    def extract(self, text: str) -> List[str]:
        """Extract names - basic implementation"""
        # This is a simplified version - real NER would be better
        if not text:
            return []
        # Just return the whole text as a potential name
        return [self.normalize(text)] if len(text) < 100 else []
    
    def similarity(self, a: str, b: str) -> float:
        """Calculate name similarity using Levenshtein-like approach"""
        a_norm = self.normalize(a)
        b_norm = self.normalize(b)
        
        if a_norm == b_norm:
            return 1.0
        
        if not a_norm or not b_norm:
            return 0.0
        
        # Token-based similarity
        a_tokens = set(a_norm.split())
        b_tokens = set(b_norm.split())
        
        if not a_tokens or not b_tokens:
            return 0.0
        
        intersection = len(a_tokens & b_tokens)
        union = len(a_tokens | b_tokens)
        
        return intersection / union if union > 0 else 0.0
    
    def is_valid(self, value: str) -> bool:
        if not value:
            return False
        normalized = self.normalize(value)
        # At least 2 characters, not just numbers
        return len(normalized) >= 2 and not normalized.isdigit()


# Matcher registry
MATCHERS = {
    "email": EmailMatcher(),
    "domain": DomainMatcher(),
    "phone": PhoneMatcher(),
    "name": NameMatcher(),
}


def get_matcher(entity_type: str) -> Optional[BaseMatcher]:
    """Get matcher for entity type"""
    return MATCHERS.get(entity_type)
