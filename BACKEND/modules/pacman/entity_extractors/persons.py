"""
PACMAN Person Extractor
Uses names-dataset for validation + regex patterns
"""

import re
from typing import Dict, List, Set, Optional
from pathlib import Path

# Try to load names-dataset if available
FIRST_NAMES: Set[str] = set()
try:
    from names_dataset import NameDataset
    nd = NameDataset()
    # Load common first names (top countries)
    for country in ['US', 'GB', 'DE', 'FR', 'ES', 'IT', 'NL', 'BE', 'CH', 'AT']:
        try:
            names = nd.get_top_names(n=10000, country_alpha2=country)
            if names:
                FIRST_NAMES.update(n.upper() for n in names.get('M', []))
                FIRST_NAMES.update(n.upper() for n in names.get('F', []))
        except:
            pass
except ImportError:
    # Fallback: common first names
    FIRST_NAMES = {
        'JOHN', 'JAMES', 'MICHAEL', 'DAVID', 'ROBERT', 'WILLIAM', 'RICHARD', 'THOMAS',
        'MARY', 'PATRICIA', 'JENNIFER', 'LINDA', 'ELIZABETH', 'BARBARA', 'SUSAN',
        'PETER', 'PAUL', 'MARK', 'STEVEN', 'ANDREW', 'DANIEL', 'MATTHEW', 'ANTHONY',
        'SARAH', 'KAREN', 'NANCY', 'BETTY', 'MARGARET', 'SANDRA', 'ASHLEY', 'DOROTHY',
        'HANS', 'KLAUS', 'WOLFGANG', 'HEINRICH', 'FRANZ', 'FRITZ', 'HELMUT', 'WERNER',
        'MARIE', 'ANNA', 'SOPHIE', 'EMMA', 'LUISE', 'HELGA', 'INGRID', 'URSULA',
        'JEAN', 'PIERRE', 'JACQUES', 'MICHEL', 'PHILIPPE', 'ALAIN', 'BERNARD',
        'GIUSEPPE', 'GIOVANNI', 'FRANCESCO', 'ANTONIO', 'MARIO', 'LUIGI', 'PAOLO',
    }

# Titles that indicate a person
TITLES = {
    'MR', 'MRS', 'MS', 'MISS', 'DR', 'PROF', 'SIR', 'LADY', 'LORD', 'DAME',
    'HERR', 'FRAU', 'MONSIEUR', 'MADAME', 'MADEMOISELLE', 'SIGNOR', 'SIGNORA',
    'DON', 'DONA', 'SENOR', 'SENORA', 'SENORITA',
}

# Words that disqualify a match as a person
EXCLUSIONS = {
    'LIMITED', 'LTD', 'LLC', 'INC', 'CORP', 'CORPORATION', 'COMPANY', 'CO',
    'GMBH', 'AG', 'SA', 'SRL', 'BV', 'NV', 'PLC', 'LP', 'LLP',
    'TRUST', 'FUND', 'FOUNDATION', 'ASSOCIATION', 'INSTITUTE', 'UNIVERSITY',
    'BANK', 'INSURANCE', 'HOLDINGS', 'GROUP', 'PARTNERS', 'INVESTMENTS',
    'THE', 'AND', 'OF', 'FOR', 'IN', 'AT', 'BY', 'TO', 'WITH',
}

# Pattern for potential person names (2-4 capitalized words)
PERSON_PATTERN = re.compile(
    r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b'
)


def extract_persons(content: str, max_results: int = 30) -> List[Dict]:
    """
    Extract person names from content.
    
    Returns list of dicts with:
        - name: The extracted name
        - confidence: float 0-1
        - source: 'title', 'first_name', 'pattern'
    """
    if not content:
        return []
    
    results = []
    seen = set()
    
    # Method 1: Title + Name (highest confidence)
    for title in TITLES:
        pattern = re.compile(rf'\b{title}\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,2}})\b', re.I)
        for match in pattern.finditer(content):
            name = match.group(1).strip()
            if name.upper() not in seen and not _is_excluded(name):
                seen.add(name.upper())
                results.append({
                    'name': name,
                    'confidence': 0.95,
                    'source': 'title'
                })
    
    # Method 2: Known first name + surname (high confidence)
    for match in PERSON_PATTERN.finditer(content):
        name = match.group(1)
        parts = name.split()
        if len(parts) >= 2:
            first = parts[0].upper()
            if first in FIRST_NAMES and name.upper() not in seen and not _is_excluded(name):
                seen.add(name.upper())
                results.append({
                    'name': name,
                    'confidence': 0.85,
                    'source': 'first_name'
                })
    
    # Method 3: Pattern only (lower confidence, needs AI validation)
    for match in PERSON_PATTERN.finditer(content):
        name = match.group(1)
        if name.upper() not in seen and not _is_excluded(name):
            parts = name.split()
            if len(parts) >= 2 and all(len(p) > 1 for p in parts):
                seen.add(name.upper())
                results.append({
                    'name': name,
                    'confidence': 0.5,
                    'source': 'pattern'
                })
    
    # Sort by confidence, limit results
    results.sort(key=lambda x: x['confidence'], reverse=True)
    return results[:max_results]


def _is_excluded(name: str) -> bool:
    """Check if name contains exclusion words."""
    words = set(name.upper().split())
    return bool(words & EXCLUSIONS)


def validate_person(name: str) -> float:
    """
    Validate if a string is likely a person name.
    Returns confidence score 0-1.
    """
    if not name:
        return 0.0
    
    parts = name.split()
    if len(parts) < 2:
        return 0.1
    
    # Check for exclusions
    if _is_excluded(name):
        return 0.0
    
    # Check first name
    first = parts[0].upper()
    if first in FIRST_NAMES:
        return 0.85
    
    # Check for title
    if first.rstrip('.') in TITLES:
        return 0.9
    
    # Pattern match only
    if all(p[0].isupper() and p[1:].islower() for p in parts if len(p) > 1):
        return 0.5
    
    return 0.2
