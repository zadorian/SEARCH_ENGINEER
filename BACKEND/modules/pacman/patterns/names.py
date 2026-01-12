"""
PACMAN Patterns - Person and Company Names
"""

import re
from typing import Set

# Person name pattern (Unicode-aware, 2-3 words)
PERSON_NAME = re.compile(
    r'\b([A-ZÀ-ÖØ-ÞĀ-ŐŒ-Ž][a-zà-öø-ÿā-őœ-ž]+(?:\s+[A-ZÀ-ÖØ-ÞĀ-ŐŒ-Ž][a-zà-öø-ÿā-őœ-ž]+){1,2})\b',
    re.UNICODE
)

# Words that look like names but aren't
NAME_EXCLUSIONS: Set[str] = {
    # Days/Months
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
    'september', 'october', 'november', 'december',
    # Nationalities
    'american', 'british', 'german', 'french', 'spanish', 'italian', 'russian',
    'chinese', 'japanese', 'korean', 'indian', 'brazilian', 'mexican', 'canadian',
    'australian', 'dutch', 'polish', 'hungarian', 'czech', 'swedish', 'norwegian',
    'danish', 'finnish', 'turkish', 'greek', 'portuguese', 'belgian', 'swiss',
    'austrian', 'european', 'asian', 'african', 'international', 'global',
    # Business words
    'company', 'corporation', 'limited', 'incorporated', 'holding', 'group',
    'managing', 'executive', 'financial', 'technical', 'general', 'special',
    'senior', 'junior', 'national', 'regional', 'local', 'annual', 'quarterly',
    # Legal
    'case', 'docket', 'file', 'claim', 'appeal', 'court', 'tribunal', 'matter',
    'total', 'amount', 'value', 'payment', 'pursuant', 'subject', 'exhibit',
    # Web
    'news', 'home', 'about', 'contact', 'services', 'products', 'privacy', 'terms',
    'click', 'read', 'more', 'learn', 'view', 'download', 'subscribe', 'share',
    'login', 'sign', 'register',
    # Greetings
    'dear', 'please', 'thank', 'thanks', 'sincerely', 'regards', 'best',
}

# Company legal suffixes (lowercase)
COMPANY_SUFFIXES: Set[str] = {
    # English
    'ltd', 'llc', 'inc', 'corp', 'plc', 'co', 'limited', 'corporation', 'incorporated',
    'llp', 'lp', 'company',
    # German
    'gmbh', 'ag', 'kg', 'ohg', 'ug', 'gbr', 'ev', 'kgaa',
    # French
    'sa', 'sas', 'sarl', 'sasu', 'snc', 'sci', 'eurl',
    # Italian
    'spa', 'srl', 'sapa',
    # Spanish
    'sl', 'sau', 'scl',
    # Dutch/Belgian
    'bv', 'nv', 'vof', 'cv', 'cvba',
    # Nordic
    'ab', 'as', 'asa', 'oy', 'oyj', 'a/s',
    # Eastern Europe
    'sp', 'kft', 'zrt', 'nyrt', 'bt', 'doo', 'dd', 'ad', 'ood', 'eood',
    # Russian
    'jsc', 'pjsc', 'ojsc', 'ooo', 'zao', 'pao',
    # Other
    'pte', 'pty', 'bhd', 'sdn', 'kk',
}

# Build company pattern dynamically
_suffix_pattern = '|'.join(re.escape(s) for s in COMPANY_SUFFIXES)
COMPANY_NAME = re.compile(
    rf'\b((?:[A-Z][A-Za-z0-9\-&]+\s*){{1,5}})({_suffix_pattern})\b',
    re.I
)
