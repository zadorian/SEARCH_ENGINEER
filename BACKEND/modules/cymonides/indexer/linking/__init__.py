"""
Entity Linking Module for Cymonides Indexer
Links documents to canonical entities in C-3 during indexing
"""

from .linker import EntityLinker, LinkResult, LinkStrategy
from .matchers import EmailMatcher, DomainMatcher, PhoneMatcher, NameMatcher

__all__ = [
    'EntityLinker',
    'LinkResult',
    'LinkStrategy',
    'EmailMatcher',
    'DomainMatcher', 
    'PhoneMatcher',
    'NameMatcher',
]
