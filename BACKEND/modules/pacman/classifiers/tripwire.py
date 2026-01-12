"""
PACMAN Tripwire Classifier
Aho-Corasick automaton for fast red flag pattern detection
"""

from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Try to import ahocorasick
_AHOCORASICK_AVAILABLE = False
try:
    import ahocorasick
    _AHOCORASICK_AVAILABLE = True
except ImportError:
    pass


class TripwireCategory(Enum):
    SANCTIONS = 'sanctions'
    PEP = 'pep'
    FRAUD = 'fraud'
    MONEY_LAUNDERING = 'money_laundering'
    TERRORISM = 'terrorism'
    CORRUPTION = 'corruption'
    TAX_EVASION = 'tax_evasion'
    REGULATORY = 'regulatory'
    LITIGATION = 'litigation'


@dataclass
class TripwireHit:
    pattern: str
    category: TripwireCategory
    position: int
    context: str


# Red flag patterns by category
RED_FLAG_PATTERNS = {
    TripwireCategory.SANCTIONS: [
        'sanctions', 'sanctioned', 'ofac', 'sdn list', 'blocked person',
        'designated person', 'restricted entity', 'embargo',
    ],
    TripwireCategory.PEP: [
        'politically exposed', 'pep', 'government official', 'minister',
        'parliament member', 'senior official', 'public official',
    ],
    TripwireCategory.FRAUD: [
        'fraud', 'fraudulent', 'scam', 'ponzi', 'pyramid scheme',
        'securities fraud', 'wire fraud', 'bank fraud', 'investment fraud',
    ],
    TripwireCategory.MONEY_LAUNDERING: [
        'money laundering', 'aml', 'suspicious transaction', 'sar',
        'structuring', 'smurfing', 'layering', 'placement', 'integration',
    ],
    TripwireCategory.TERRORISM: [
        'terrorist', 'terrorism financing', 'extremist', 'terror',
    ],
    TripwireCategory.CORRUPTION: [
        'bribery', 'corrupt', 'corruption', 'kickback', 'embezzlement',
        'fcpa', 'uk bribery act', 'facilitation payment',
    ],
    TripwireCategory.TAX_EVASION: [
        'tax evasion', 'tax fraud', 'offshore account', 'tax haven',
        'shell company', 'panama papers', 'paradise papers',
    ],
    TripwireCategory.REGULATORY: [
        'regulatory action', 'enforcement action', 'fine', 'penalty',
        'cease and desist', 'consent order', 'settlement',
    ],
    TripwireCategory.LITIGATION: [
        'lawsuit', 'litigation', 'indictment', 'charged with',
        'convicted', 'pleaded guilty', 'settlement', 'class action',
    ],
}


class TripwireScanner:
    """Fast pattern scanner using Aho-Corasick."""
    
    def __init__(self):
        self._automaton = None
        self._pattern_map = {}  # pattern -> category
        self._build_automaton()
    
    def _build_automaton(self):
        """Build Aho-Corasick automaton from patterns."""
        if not _AHOCORASICK_AVAILABLE:
            return
        
        self._automaton = ahocorasick.Automaton()
        
        for category, patterns in RED_FLAG_PATTERNS.items():
            for pattern in patterns:
                pattern_lower = pattern.lower()
                self._pattern_map[pattern_lower] = category
                self._automaton.add_word(pattern_lower, pattern_lower)
        
        self._automaton.make_automaton()
    
    def scan(self, content: str, context_window: int = 50) -> List[TripwireHit]:
        """Scan content for red flag patterns."""
        if not content:
            return []
        
        content_lower = content.lower()
        hits = []
        
        if _AHOCORASICK_AVAILABLE and self._automaton:
            for end_pos, pattern in self._automaton.iter(content_lower):
                start_pos = end_pos - len(pattern) + 1
                category = self._pattern_map.get(pattern)
                
                ctx_start = max(0, start_pos - context_window)
                ctx_end = min(len(content), end_pos + context_window + 1)
                context = content[ctx_start:ctx_end]
                
                hits.append(TripwireHit(
                    pattern=pattern,
                    category=category,
                    position=start_pos,
                    context=context
                ))
        else:
            # Fallback: simple string search
            for category, patterns in RED_FLAG_PATTERNS.items():
                for pattern in patterns:
                    pattern_lower = pattern.lower()
                    pos = 0
                    while True:
                        pos = content_lower.find(pattern_lower, pos)
                        if pos == -1:
                            break
                        
                        ctx_start = max(0, pos - context_window)
                        ctx_end = min(len(content), pos + len(pattern) + context_window)
                        context = content[ctx_start:ctx_end]
                        
                        hits.append(TripwireHit(
                            pattern=pattern,
                            category=category,
                            position=pos,
                            context=context
                        ))
                        pos += 1
        
        return hits
    
    def has_red_flags(self, content: str) -> bool:
        """Quick check if content has any red flags."""
        if not content:
            return False
        
        content_lower = content.lower()
        
        if _AHOCORASICK_AVAILABLE and self._automaton:
            for _ in self._automaton.iter(content_lower):
                return True
            return False
        else:
            for patterns in RED_FLAG_PATTERNS.values():
                for pattern in patterns:
                    if pattern.lower() in content_lower:
                        return True
            return False
    
    def get_categories(self, content: str) -> Set[TripwireCategory]:
        """Get all triggered categories."""
        hits = self.scan(content)
        return {hit.category for hit in hits}


# Global scanner instance
_scanner = None

def get_scanner() -> TripwireScanner:
    global _scanner
    if _scanner is None:
        _scanner = TripwireScanner()
    return _scanner


def scan_content(content: str) -> List[TripwireHit]:
    return get_scanner().scan(content)


def has_red_flags(content: str) -> bool:
    return get_scanner().has_red_flags(content)
