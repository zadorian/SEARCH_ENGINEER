#!/usr/bin/env python3
"""Re-process existing submarine content with PACMAN extraction."""

import re
import sys
from datetime import datetime
from typing import Dict, List, Set

from elasticsearch import Elasticsearch
from elasticsearch.helpers import scan, bulk

try:
    from names_dataset import NameDataset
    _nd = NameDataset()
    HAS_NAMES = True
    print("[PACMAN] names-dataset loaded", file=sys.stderr)
except ImportError:
    _nd = None
    HAS_NAMES = False
    print("[PACMAN] names-dataset not available", file=sys.stderr)

# === PATTERNS ===
FAST_PATTERNS = {
    'LEI': re.compile(r'\b[A-Z0-9]{4}00[A-Z0-9]{12}\d{2}\b'),
    'UK_CRN': re.compile(r'\b(?:CRN|Company\s*(?:No|Number|Reg))[:\s]*([A-Z]{0,2}\d{6,8})\b', re.I),
    'IBAN': re.compile(r'\b([A-Z]{2}\d{2}[A-Z0-9]{4,30})\b'),
    'BTC': re.compile(r'\b([13][a-km-zA-HJ-NP-Z1-9]{25,34})\b'),
    'ETH': re.compile(r'\b(0x[a-fA-F0-9]{40})\b'),
    'IMO': re.compile(r'\bIMO[:\s]*(\d{7})\b', re.I),
    'EMAIL': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', re.I),
    'PHONE': re.compile(r'(?:\+|00)[\d\s\-\(\)]{10,20}'),
}

NAME_PATTERN = re.compile(
    r'\b([A-ZÀ-ÖØ-ÞĀ-ŐŒ-Ž][a-zà-öø-ÿā-őœ-ž]+(?:\s+[A-ZÀ-ÖØ-ÞĀ-ŐŒ-Ž][a-zà-öø-ÿā-őœ-ž]+){1,2})\b',
    re.UNICODE
)

NAME_EXCLUSIONS: Set[str] = {
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
    'september', 'october', 'november', 'december', 'american', 'british', 'german',
    'french', 'spanish', 'italian', 'russian', 'chinese', 'japanese', 'korean',
    'company', 'corporation', 'limited', 'incorporated', 'holding', 'group',
    'managing', 'executive', 'financial', 'technical', 'annual', 'quarterly',
    'privacy', 'terms', 'contact', 'about', 'home', 'services', 'products',
    'click', 'read', 'more', 'learn', 'view', 'download', 'subscribe',
}

COMPANY_SUFFIXES: Set[str] = {
    'ltd', 'llc', 'inc', 'corp', 'plc', 'gmbh', 'ag', 'kg', 'sa', 'sas',
    'sarl', 'srl', 'sl', 'bv', 'nv', 'ab', 'as', 'oy', 'kft', 'zrt', 'bt',
    'doo', 'dd', 'ad', 'ood', 'eood', 'jsc', 'pjsc', 'limited', 'corporation',
}

_suffix_pattern = '|'.join(re.escape(s) for s in COMPANY_SUFFIXES)
COMPANY_PATTERN = re.compile(rf'\b((?:[A-Z][A-Za-z0-9\-&]+\s*){{1,5}})({_suffix_pattern})\b', re.I)


def extract_persons(text: str) -> List[str]:
    if not HAS_NAMES or not text:
        return []
    results = []
    seen = set()
    for match in NAME_PATTERN.finditer(text):
        candidate = match.group(1)
        words = candidate.split()
        if any(w.lower() in NAME_EXCLUSIONS for w in words):
            continue
        result = _nd.search(words[0])
        if result and result.get('first_name'):
            if candidate.lower() not in seen:
                seen.add(candidate.lower())
                results.append(candidate)
                if len(results) >= 20:
                    break
    return results


def extract_companies(text: str) -> List[str]:
    if not text:
        return []
    results = []
    seen = set()
    for match in COMPANY_PATTERN.finditer(text):
        name = match.group(1).strip() + ' ' + match.group(2)
        if name.lower() not in seen:
            seen.add(name.lower())
            results.append(name)
            if len(results) >= 20:
                break
    return results


def extract_fast(content: str) -> Dict[str, List[str]]:
    if not content:
        return {}
    entities = {}
    for name, pattern in FAST_PATTERNS.items():
        matches = pattern.findall(content)
        if matches:
            entities[name] = list(set(matches))[:10]
    # Person/Company extraction
    persons = extract_persons(content)
    if persons:
        entities['PERSON'] = persons
    companies = extract_companies(content)
    if companies:
        entities['COMPANY'] = companies
    return entities


def main():
    es = Elasticsearch(['http://localhost:9200'])
    
    # Count docs without entities
    count = es.count(index='submarine-linkedin', body={
        'query': {'bool': {'must_not': {'exists': {'field': 'entities.PERSON'}}}}
    })['count']
    print(f"[REPROCESS] {count} docs need entity extraction", file=sys.stderr)
    
    # Scan and update
    actions = []
    processed = 0
    entities_found = 0
    
    for doc in scan(es, index='submarine-linkedin', 
                    query={'query': {'bool': {'must_not': {'exists': {'field': 'entities.PERSON'}}}}},
                    scroll='5m', size=1000):
        content = doc['_source'].get('content', '')
        if not content:
            continue
            
        entities = extract_fast(content)
        
        if entities:
            entities_found += 1
            actions.append({
                '_op_type': 'update',
                '_index': 'submarine-linkedin',
                '_id': doc['_id'],
                'doc': {'entities': entities}
            })
        
        processed += 1
        
        if len(actions) >= 500:
            success, _ = bulk(es, actions, raise_on_error=False)
            print(f"[BATCH] Processed {processed}, updated {success}, entities found: {entities_found}", file=sys.stderr)
            actions = []
    
    # Final batch
    if actions:
        success, _ = bulk(es, actions, raise_on_error=False)
        print(f"[FINAL] Processed {processed}, updated {success}, entities found: {entities_found}", file=sys.stderr)
    
    print(f"[DONE] Total processed: {processed}, total with entities: {entities_found}")


if __name__ == '__main__':
    main()
