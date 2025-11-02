#!/usr/bin/env python3
"""
Intelligent Public Records Categorization System
Uses multiple signals: Curlie paths, domain patterns, content analysis, wiki sections
"""

import json
import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlparse

class IntelligentCategorizer:
    def __init__(self):
        # Define comprehensive category mappings and patterns
        self.initialize_patterns()
        
    def initialize_patterns(self):
        """Initialize comprehensive categorization patterns"""
        
        # Curlie path mappings (path fragments -> category)
        # ORDER MATTERS: More specific patterns first
        self.curlie_mappings = {
            # Corporate/Business (check BEFORE government)
            '/Secretary_of_State': 'corporate_registry',
            '/Business_and_Corporate_Law': 'corporate_registry',
            '/Business/': 'corporate_registry',
            '/Corporate': 'corporate_registry',
            '/Companies': 'corporate_registry',
            '/Chamber_of_Commerce': 'corporate_registry',
            '/Trade_Register': 'corporate_registry',
            '/Business_Registry': 'corporate_registry',
            '/Commercial_Registry': 'corporate_registry',
            
            # Courts/Legal
            '/Law/': 'court_records',
            '/Courts': 'court_records',
            '/Judiciary': 'court_records',
            '/Legal': 'court_records',
            '/Litigation': 'court_records',
            '/Justice': 'court_records',
            '/Tribunals': 'court_records',
            
            # Government (general)
            '/Government/': 'government',
            '/Executive': 'government',
            '/Legislative': 'government',
            '/Agencies': 'government',
            '/Ministries': 'government',
            '/Federal': 'government',
            '/State_Government': 'government',
            '/Municipal': 'government',
            
            # Regulatory/Oversight
            '/Regulatory': 'regulatory',
            '/Regulation': 'regulatory',
            '/Oversight': 'regulatory',
            '/Compliance': 'regulatory',
            '/Licensing': 'regulatory',
            '/Financial_Services': 'regulatory',
            '/Consumer_Protection': 'regulatory',
            '/Competition': 'regulatory',
            '/Antitrust': 'regulatory',
            '/Data_Protection': 'regulatory',
            '/Privacy': 'regulatory',
            
            # Financial/Securities
            '/Finance/': 'securities',
            '/Stock_Exchange': 'securities',
            '/Securities': 'securities',
            '/Capital_Markets': 'securities',
            '/Investment': 'securities',
            '/Public_Companies': 'securities',
            
            # Property/Land
            '/Real_Estate/': 'land_registry',
            '/Property': 'land_registry',
            '/Land_Registry': 'land_registry',
            '/Cadastr': 'land_registry',
            '/Deeds': 'land_registry',
            
            # Intellectual Property
            '/Patents': 'intellectual_property',
            '/Trademarks': 'intellectual_property',
            '/Copyright': 'intellectual_property',
            '/Intellectual_Property': 'intellectual_property',
            
            # Tax/Revenue
            '/Taxation': 'tax_records',
            '/Revenue': 'tax_records',
            '/Tax': 'tax_records',
            '/Customs': 'tax_records',
            
            # Bankruptcy/Insolvency
            '/Bankruptcy': 'bankruptcy',
            '/Insolvency': 'bankruptcy',
            '/Liquidation': 'bankruptcy',
        }
        
        # Domain pattern rules with priority scores
        self.domain_patterns = {
            'corporate_registry': {
                'patterns': [
                    (r'sos\.|secretary.*state', 10),  # Secretary of State
                    (r'companies.*house|companieshouse', 10),  # Companies House
                    (r'business.*registry|registry.*business', 9),
                    (r'trade.*register|handels', 9),  # Trade registers
                    (r'corporation|incorporat', 8),
                    (r'chamber.*commerce|handelskammer', 8),
                    (r'commercial.*register', 8),
                    (r'kvk\.|breg\.|rcs\.|krs\.', 9),  # Known registry domains
                ],
                'keywords': ['company', 'business', 'corporation', 'llc', 'ltd', 'gmbh', 'incorporation']
            },
            
            'regulatory': {
                'patterns': [
                    (r'fsa\.|fca\.|sec\.|cftc\.|finra', 10),  # Financial regulators
                    (r'central.*bank|bank.*central', 10),
                    (r'financial.*authority|financial.*supervision', 10),
                    (r'securities.*commission|securities.*exchange', 10),
                    (r'competition.*authority|antitrust', 9),
                    (r'consumer.*protection', 9),
                    (r'data.*protection|privacy.*commission', 9),
                    (r'telecom.*authority|energy.*regulator', 8),
                    (r'health.*authority|medical.*board', 8),
                    (r'bar.*association|law.*society', 8),
                    (r'oversight|compliance|regulat', 7),
                ],
                'keywords': ['regulatory', 'authority', 'commission', 'oversight', 'supervision', 'compliance']
            },
            
            'court_records': {
                'patterns': [
                    (r'court|tribunal|judiciary', 10),
                    (r'justice\.|justic', 9),
                    (r'pacer\.|bailii', 10),  # Known court databases
                    (r'supremecourt|high.*court|appeal.*court', 9),
                    (r'district.*court|circuit.*court', 8),
                    (r'legal.*decision|case.*law', 8),
                ],
                'keywords': ['court', 'tribunal', 'judge', 'case', 'litigation', 'verdict', 'ruling']
            },
            
            'securities': {
                'patterns': [
                    (r'sec\.gov|edgar', 10),  # SEC EDGAR
                    (r'sedar|sedi', 10),  # Canadian securities
                    (r'stock.*exchange|bourse|bolsa|borsa', 9),
                    (r'nasdaq|nyse|lse\.|ftse', 10),
                    (r'financial.*market|capital.*market', 8),
                    (r'listed.*compan|public.*compan', 8),
                ],
                'keywords': ['securities', 'stock', 'exchange', 'trading', 'disclosure', 'filing', 'prospectus']
            },
            
            'land_registry': {
                'patterns': [
                    (r'land.*registry|registry.*land', 10),
                    (r'cadastr|catast', 10),
                    (r'property.*register|real.*estate.*register', 9),
                    (r'deed|title.*office', 9),
                    (r'mortgage.*registry', 8),
                ],
                'keywords': ['land', 'property', 'real estate', 'cadastral', 'deed', 'title', 'parcel']
            },
            
            'intellectual_property': {
                'patterns': [
                    (r'patent|uspto|epo\.org|wipo', 10),
                    (r'trademark|copyright', 9),
                    (r'intellectual.*property|ip.*office', 9),
                    (r'design.*right|industrial.*property', 8),
                ],
                'keywords': ['patent', 'trademark', 'copyright', 'intellectual property', 'ip']
            },
            
            'tax_records': {
                'patterns': [
                    (r'irs\.gov|hmrc|revenue', 10),
                    (r'tax.*authority|tax.*office', 9),
                    (r'customs|tariff', 8),
                    (r'fiscal|vat\.|ein\.|tin\.', 8),
                ],
                'keywords': ['tax', 'revenue', 'fiscal', 'customs', 'vat', 'tariff']
            },
            
            'bankruptcy': {
                'patterns': [
                    (r'bankruptcy|insolvency', 10),
                    (r'liquidation|receivership', 9),
                    (r'chapter.*(7|11|13)', 9),
                    (r'creditor|debtor', 7),
                ],
                'keywords': ['bankruptcy', 'insolvency', 'liquidation', 'creditor', 'debtor']
            },
            
            'government': {
                'patterns': [
                    (r'\.gov(?:\.|$)', 8),  # .gov domains
                    (r'\.gob\.|\.gouv\.|\.govt\.', 8),
                    (r'ministry|department|agency', 7),
                    (r'federal|national|state.*gov', 7),
                    (r'parliament|congress|senate|assembly', 7),
                ],
                'keywords': ['government', 'ministry', 'department', 'agency', 'federal', 'administration']
            }
        }
        
        # Wiki section mappings
        self.wiki_section_map = {
            'cr': 'corporate_registry',
            'lit': 'court_records',
            'reg': 'regulatory',
            'ass': 'land_registry',  # Assets typically means property/land
            'misc': None  # Don't assume category for misc
        }
        
    def categorize(self, record: Dict) -> Tuple[str, float, Dict]:
        """
        Categorize a record using multiple signals
        Returns: (category, confidence, signals_used)
        """
        signals = defaultdict(float)
        evidence = defaultdict(list)
        
        # Extract data from record
        domain = record.get('domain', '').lower()
        url = record.get('url', '').lower()
        curlie_label = record.get('curlie_label', '').lower()
        wiki_section = record.get('wiki_section', '')
        description = record.get('description', '').lower()
        name = record.get('name', '').lower()
        
        # Combine all text for analysis
        full_text = f"{domain} {url} {description} {name}"
        
        # Signal 1: Wiki section (highest confidence if present)
        if wiki_section and wiki_section in self.wiki_section_map:
            mapped_cat = self.wiki_section_map[wiki_section]
            if mapped_cat:
                signals[mapped_cat] += 30
                evidence[mapped_cat].append(f"wiki_section:{wiki_section}")
        
        # Signal 2: Curlie path analysis (check specific before general)
        if curlie_label:
            # Sort mappings by specificity (longer paths first)
            sorted_mappings = sorted(self.curlie_mappings.items(), 
                                    key=lambda x: len(x[0]), reverse=True)
            for path_fragment, category in sorted_mappings:
                if path_fragment.lower() in curlie_label:
                    signals[category] += 20
                    evidence[category].append(f"curlie_path:{path_fragment}")
                    break  # Take first match
        
        # Signal 3: Domain pattern matching (check specific patterns first)
        # Check Secretary of State FIRST (before generic government)
        if re.search(r'sos\.|secretary.*state', domain):
            signals['corporate_registry'] += 15
            evidence['corporate_registry'].append("domain:secretary_of_state")
        
        # Then check other patterns
        for category, rules in self.domain_patterns.items():
            for pattern, score in rules['patterns']:
                if re.search(pattern, domain):
                    signals[category] += score
                    evidence[category].append(f"domain_pattern:{pattern}")
                    break  # Take strongest pattern per category
        
        # Signal 4: Content keyword analysis
        for category, rules in self.domain_patterns.items():
            keyword_matches = 0
            for keyword in rules['keywords']:
                if keyword in full_text:
                    keyword_matches += 1
                    evidence[category].append(f"keyword:{keyword}")
            
            if keyword_matches > 0:
                signals[category] += min(keyword_matches * 3, 15)  # Cap at 15
        
        # Signal 5: Government domain detection (boost specific categories if present)
        gov_tlds = ['.gov', '.gob.', '.gouv.', '.govt.', '.gc.ca', '.gov.uk', '.gov.au']
        if any(tld in domain for tld in gov_tlds):
            # Boost the strongest non-government signal if it exists
            non_gov_signals = {k: v for k, v in signals.items() if k != 'government'}
            if non_gov_signals:
                strongest = max(non_gov_signals.items(), key=lambda x: x[1])
                if strongest[1] >= 10:  # If there's a reasonably strong signal
                    signals[strongest[0]] += 10
                    evidence[strongest[0]].append(f"gov_domain+{strongest[0]}_signals")
                else:
                    signals['government'] += 10
                    evidence['government'].append("gov_domain")
            else:
                signals['government'] += 10
                evidence['government'].append("gov_domain")
        
        # Determine category with highest confidence
        if signals:
            best_category = max(signals.items(), key=lambda x: x[1])
            category = best_category[0]
            confidence = min(best_category[1] / 50, 1.0)  # Normalize to 0-1
            
            return category, confidence, {
                'signals': dict(signals),
                'evidence': dict(evidence),
                'top_signals': sorted(signals.items(), key=lambda x: x[1], reverse=True)[:3]
            }
        
        # Default fallback
        return 'public_records', 0.1, {'signals': {}, 'evidence': {}}
    
    def categorize_batch(self, records: List[Dict]) -> List[Dict]:
        """Categorize a batch of records"""
        results = []
        for record in records:
            category, confidence, analysis = self.categorize(record)
            
            # Update record
            record['type'] = category
            record['category_confidence'] = round(confidence, 3)
            record['category_analysis'] = analysis
            
            # Mark if recategorized
            if record.get('type') != category:
                record['recategorized'] = True
                record['old_type'] = record.get('type')
            
            results.append(record)
        
        return results

def main():
    """Recategorize all records with intelligent system"""
    print("INTELLIGENT RECATEGORIZATION SYSTEM")
    print("=" * 70)
    
    # Load data
    with open('data/master_registries.json', 'r') as f:
        records = json.load(f)
    
    print(f"Loaded {len(records):,} records")
    
    # Get original distribution
    original_dist = Counter(r.get('type', 'unknown') for r in records)
    print("\nOriginal distribution:")
    for cat, count in original_dist.most_common():
        print(f"  {cat}: {count:,}")
    
    # Initialize categorizer
    categorizer = IntelligentCategorizer()
    
    # Process in batches with progress
    batch_size = 1000
    all_results = []
    
    print(f"\nProcessing {len(records):,} records...")
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        results = categorizer.categorize_batch(batch)
        all_results.extend(results)
        
        if (i + batch_size) % 5000 == 0:
            print(f"  Processed {min(i + batch_size, len(records)):,} records...")
    
    # Analyze results
    new_dist = Counter(r['type'] for r in all_results)
    confidence_by_type = defaultdict(list)
    recategorized = 0
    
    for r in all_results:
        confidence_by_type[r['type']].append(r.get('category_confidence', 0))
        if r.get('recategorized'):
            recategorized += 1
    
    print(f"\n{'=' * 70}")
    print("RECATEGORIZATION COMPLETE")
    print(f"Recategorized {recategorized:,} records")
    
    print("\nNew distribution with average confidence:")
    for cat, count in new_dist.most_common():
        avg_conf = sum(confidence_by_type[cat]) / len(confidence_by_type[cat]) if confidence_by_type[cat] else 0
        change = count - original_dist.get(cat, 0)
        change_str = f"+{change}" if change > 0 else str(change)
        print(f"  {cat}: {count:,} ({change_str}) - avg confidence: {avg_conf:.2f}")
    
    # Save results
    with open('data/master_registries_intelligent.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print("\nSaved to master_registries_intelligent.json")
    
    # Generate quality report
    print(f"\n{'=' * 70}")
    print("QUALITY ANALYSIS")
    
    # Low confidence records
    low_conf = [r for r in all_results if r.get('category_confidence', 0) < 0.3]
    print(f"\nLow confidence categorizations (<0.3): {len(low_conf):,}")
    
    # Sample low confidence
    if low_conf:
        print("Sample low-confidence records:")
        for r in low_conf[:5]:
            print(f"  {r['domain'][:40]} -> {r['type']} (conf: {r.get('category_confidence', 0):.2f})")
    
    # High confidence by category
    print("\nHigh confidence records (>0.7) by category:")
    for cat in new_dist.keys():
        high_conf = [r for r in all_results if r['type'] == cat and r.get('category_confidence', 0) > 0.7]
        print(f"  {cat}: {len(high_conf):,}/{new_dist[cat]:,} ({len(high_conf)*100//new_dist[cat]}%)")

if __name__ == '__main__':
    main()