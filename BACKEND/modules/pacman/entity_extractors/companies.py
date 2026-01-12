"""
PACMAN Company Extractor
Pattern-based company name detection with suffix validation
"""

import re
from typing import Dict, List, Set, Tuple
from ..patterns.company_numbers import ALL_COMPANY_NUMBERS


# Company suffixes by language/jurisdiction
SUFFIXES = {
    # English
    'LIMITED', 'LTD', 'LLC', 'INC', 'INCORPORATED', 'CORP', 'CORPORATION',
    'CO', 'COMPANY', 'PLC', 'LP', 'LLP', 'PLLC',
    # German
    'GMBH', 'AG', 'KG', 'OHG', 'EG', 'GMBH & CO KG', 'UG',
    # French
    'SA', 'SARL', 'SAS', 'SASU', 'SNC', 'SCA', 'EURL',
    # Italian
    'SRL', 'SPA', 'SAPA', 'SNC',
    # Dutch/Belgian
    'BV', 'NV', 'VOF', 'CV', 'BVBA', 'SPRL',
    # Spanish
    'SL', 'SAU', 'SLNE',
    # Nordic
    'AS', 'ASA', 'AB', 'OY', 'OYJ', 'APS', 'A/S',
    # Swiss
    'SAGL',
    # Other
    'SE', 'SCE', 'EEIG', 'KFT', 'ZRT', 'RT', 'DOO', 'DD', 'AD',
    'JSC', 'PJSC', 'OJSC', 'CJSC', 'AO', 'OOO', 'ZAO', 'PAO',
}

# Compile suffix pattern
SUFFIX_PATTERN = '|'.join(re.escape(s) for s in sorted(SUFFIXES, key=len, reverse=True))
COMPANY_WITH_SUFFIX = re.compile(
    rf'\b([A-Z][A-Za-z0-9&\-\s]{{2,50}})\s+({SUFFIX_PATTERN})\b',
    re.IGNORECASE
)

# Pattern for companies without suffix (looser, needs validation)
COMPANY_WORDS = {
    'GROUP', 'HOLDINGS', 'PARTNERS', 'CAPITAL', 'INVESTMENTS', 'VENTURES',
    'INTERNATIONAL', 'GLOBAL', 'WORLDWIDE', 'INDUSTRIES', 'ENTERPRISES',
    'MANAGEMENT', 'CONSULTING', 'SERVICES', 'SOLUTIONS', 'SYSTEMS',
    'TECHNOLOGIES', 'ASSOCIATES', 'ADVISORS', 'FUND', 'TRUST',
}

COMPANY_WORD_PATTERN = '|'.join(re.escape(w) for w in COMPANY_WORDS)
COMPANY_WITH_WORD = re.compile(
    rf'\b([A-Z][A-Za-z0-9&\-\s]{{2,40}})\s+({COMPANY_WORD_PATTERN})\b',
    re.IGNORECASE
)

# Exclusions
EXCLUSIONS = {
    'THE', 'AND', 'OF', 'FOR', 'IN', 'AT', 'BY', 'TO', 'WITH', 'FROM',
    'NEW', 'OLD', 'FIRST', 'SECOND', 'THIRD', 'LAST', 'NEXT', 'BEST',
}


def extract_companies(content: str, max_results: int = 20) -> List[Dict]:
    """
    Extract company names from content.
    
    Returns list of dicts with:
        - name: The extracted company name
        - suffix: Legal suffix if found
        - confidence: float 0-1
        - source: 'suffix', 'word', 'crn'
    """
    if not content:
        return []
    
    results = []
    seen = set()
    
    # Method 1: Company with legal suffix (highest confidence)
    for match in COMPANY_WITH_SUFFIX.finditer(content):
        name = match.group(1).strip()
        suffix = match.group(2).upper()
        full_name = f"{name} {suffix}"
        
        if full_name.upper() not in seen and not _is_excluded(name):
            seen.add(full_name.upper())
            results.append({
                'name': full_name,
                'suffix': suffix,
                'confidence': 0.95,
                'source': 'suffix'
            })
    
    # Method 2: Company with business word (medium confidence)
    for match in COMPANY_WITH_WORD.finditer(content):
        name = match.group(1).strip()
        word = match.group(2).upper()
        full_name = f"{name} {word}"
        
        if full_name.upper() not in seen and not _is_excluded(name):
            seen.add(full_name.upper())
            results.append({
                'name': full_name,
                'suffix': None,
                'confidence': 0.75,
                'source': 'word'
            })
    
    # Method 3: Extract companies from registration numbers
    for crn_type, pattern in ALL_COMPANY_NUMBERS.items():
        for match in pattern.finditer(content):
            # Look for company name before the number
            start = max(0, match.start() - 100)
            context = content[start:match.start()]
            
            # Find potential company name in context
            for suffix_match in COMPANY_WITH_SUFFIX.finditer(context):
                name = suffix_match.group(1).strip()
                suffix = suffix_match.group(2).upper()
                full_name = f"{name} {suffix}"
                
                if full_name.upper() not in seen:
                    seen.add(full_name.upper())
                    results.append({
                        'name': full_name,
                        'suffix': suffix,
                        'crn': match.group(0) if match.group(0) else match.group(1),
                        'crn_type': crn_type,
                        'confidence': 0.90,
                        'source': 'crn'
                    })
    
    # Sort by confidence, limit results
    results.sort(key=lambda x: x['confidence'], reverse=True)
    return results[:max_results]


def _is_excluded(name: str) -> bool:
    """Check if name is just common words."""
    words = set(name.upper().split())
    return len(words - EXCLUSIONS) == 0


def validate_company(name: str) -> Tuple[float, str]:
    """
    Validate if a string is likely a company name.
    Returns (confidence, reason).
    """
    if not name:
        return (0.0, 'empty')
    
    name_upper = name.upper()
    
    # Check for suffix
    for suffix in SUFFIXES:
        if name_upper.endswith(suffix) or f' {suffix}' in name_upper:
            return (0.95, f'has_suffix:{suffix}')
    
    # Check for business words
    for word in COMPANY_WORDS:
        if word in name_upper:
            return (0.75, f'has_word:{word}')
    
    # Too short
    if len(name) < 5:
        return (0.1, 'too_short')
    
    # All caps might be company
    if name.isupper() and len(name.split()) >= 2:
        return (0.5, 'all_caps')
    
    return (0.3, 'pattern_only')


def normalize_suffix(suffix: str) -> str:
    """Normalize company suffix to standard form."""
    suffix = suffix.upper().strip('.')
    
    # Common normalizations
    normalizations = {
        'LTD': 'LIMITED',
        'INC': 'INCORPORATED',
        'CORP': 'CORPORATION',
        'CO': 'COMPANY',
    }
    
    return normalizations.get(suffix, suffix)
