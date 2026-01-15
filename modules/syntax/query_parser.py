"""
LinkLater Query Parser

Parses syntax-based queries into structured intent.

Syntax:
  OPERATOR(s) : TARGET

Examples:
  p? c? :!example.com
  ?bl :!example.com
  ent?:2024! !example.com
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class QueryIntent:
    """Parsed query intent."""
    raw_query: str
    operators: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list) # Search terms
    target: str = ""
    target_type: str = "unknown"  # domain, url, keyword
    historical_modifiers: List[str] = field(default_factory=list)
    context_modifiers: List[str] = field(default_factory=list)  # :tor, :onion
    filters: Dict[str, str] = field(default_factory=dict)  # year=2024

    @property
    def is_historical(self) -> bool:
        """Check if query is historical."""
        return bool(self.historical_modifiers)

def parse_query(query: str) -> Optional[QueryIntent]:
    """Parse a query string into intent."""
    if not query:
        return None

    # Split by colon to separate operators from target
    if ':' in query:
        parts = query.split(':', 1)
        ops_part = parts[0].strip()
        target_part = parts[1].strip()
    else:
        # Implicit if no colon (assume target if starts with !)
        if query.strip().startswith('!'):
            ops_part = ""
            target_part = query.strip()
        else:
            return None # Invalid format

    intent = QueryIntent(raw_query=query)

    # Parse operators and keywords
    if ops_part:
        # Handle quoted keywords first to avoid splitting them
        # Simple extraction of "quoted strings"
        quoted = re.findall(r'"([^"]*)"', ops_part)
        for q in quoted:
            intent.keywords.append(q)
            ops_part = ops_part.replace(f'"{q}"', "") # Remove processed

        # Split remaining by space
        ops = ops_part.split()
        for op in ops:
            if op.endswith('?') or op.startswith('?'):
                intent.operators.append(op)
            elif op.endswith('!'):
                # Historical modifier like 2024!
                if re.match(r'\d{4}(-(\d{4}))?!', op):
                    intent.historical_modifiers.append(op[:-1])
                elif op in ['pdf!', 'doc!', 'word!', 'xls!', 'ppt!', 'file!']:
                     intent.operators.append(op) # Filetype discovery
            else:
                # Treat as keyword if not empty/whitespace
                if op.strip():
                    intent.keywords.append(op)

    # Parse target and context
    if target_part:
        # Check for modifiers in target string
        target_words = target_part.split()
        final_target_words = []
        
        for word in target_words:
            # Context modifiers (after target)
            if word.lower() in [':tor', ':onion']:
                intent.context_modifiers.append(word.lower())
            
            # Historical modifier: <- (standalone or prefix)
            elif word == '<-' or word.startswith('<-'):
                intent.historical_modifiers.append("full_history")
                # If it was a prefix like <-!domain.com, keep the rest
                if len(word) > 2:
                    remainder = word[2:]
                    final_target_words.append(remainder)
            
            # Historical modifiers (ending in !)
            elif word.endswith('!') and not word.startswith('!'):
                if re.match(r'\d{4}(-(\d{4}))?!', word):
                    intent.historical_modifiers.append(word[:-1])
                elif word in ['pdf!', 'doc!', 'word!', 'xls!', 'ppt!', 'file!']:
                     intent.operators.append(word) # Filetype discovery
                else:
                    final_target_words.append(word)
            else:
                final_target_words.append(word)
        
        target_clean = ' '.join(final_target_words)

        if target_clean.startswith('!'):
            intent.target = target_clean[1:]
            intent.target_type = "domain"
        elif target_clean.endswith('!'):
             intent.target = target_clean[:-1] # Remove trailing !
             intent.target_type = "page"
        else:
             intent.target = target_clean
             # Auto-detect type
             if '.' in target_clean and not ' ' in target_clean:
                 intent.target_type = "domain"
             else:
                 intent.target_type = "keyword"

    return intent
