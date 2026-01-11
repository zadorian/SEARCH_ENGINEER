"""
EYE-D OSINT Integration Module
Provides classification and data source access for OSINT searches
"""

from .classifier import classify_eyed_query, classify_query_pattern, get_search_endpoint
from .claude_utils import should_clean_with_claude, clean_with_claude
from .legend import (
    EmailInput,
    PhoneInput,
    DomainUrlInput,
    PersonNameInput,
    EyeDModule,
    models as eyed_models,
    resources as eyed_resources,
)

__all__ = [
    'classify_eyed_query',
    'classify_query_pattern',
    'get_search_endpoint',
    'should_clean_with_claude',
    'clean_with_claude',
    'EmailInput',
    'PhoneInput',
    'DomainUrlInput',
    'PersonNameInput',
    'EyeDModule',
    'eyed_models',
    'eyed_resources',
]
