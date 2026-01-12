"""
EYE-D OSINT Integration Module
Provides classification and data source access for OSINT searches
"""

from .classifier import classify_eyed_query, classify_query_pattern, get_search_endpoint
from .claude_utils import should_clean_with_claude, clean_with_claude

# Output handlers (the clean module exports)
from .output.email import EmailOutputHandler
from .output.phone import PhoneOutputHandler
from .output.username import UsernameOutputHandler
from .output.person_name import PersonNameOutputHandler
from .output.domain_url import DomainUrlOutputHandler

__all__ = [
    # Classifiers
    'classify_eyed_query',
    'classify_query_pattern',
    'get_search_endpoint',
    'should_clean_with_claude',
    'clean_with_claude',
    # Output handlers
    'EmailOutputHandler',
    'PhoneOutputHandler',
    'UsernameOutputHandler',
    'PersonNameOutputHandler',
    'DomainUrlOutputHandler',
]
