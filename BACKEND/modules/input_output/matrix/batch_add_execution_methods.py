#!/usr/bin/env python3
"""
Batch update rules.json to add execution methods for metadata-only rules.

This script analyzes rules without executable resources and adds appropriate
execution methods based on pattern matching against rule labels and categories.

Based on RuleExecutor's supported resource types:
- module: Import Python module and call method
- api: Call REST API endpoint
- brute_search: Execute BruteSearch via Node.js
- script: Run Python script via subprocess
- url: Scrape URL via BrightData
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

# Path to rules.json
RULES_PATH = Path(__file__).parent / "rules.json"
BACKUP_PATH = Path(__file__).parent / "rules.json.backup"


class RuleUpdater:
    """Updates rules with execution methods based on pattern matching."""

    def __init__(self):
        self.stats = {
            'total': 0,
            'no_resources': 0,
            'updated': 0,
            'by_category': {}
        }

    def load_rules(self) -> List[Dict]:
        """Load rules from JSON file."""
        with open(RULES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_rules(self, rules: List[Dict]):
        """Save rules to JSON file with backup."""
        # Create backup
        import shutil
        shutil.copy2(RULES_PATH, BACKUP_PATH)
        print(f"✓ Backup created: {BACKUP_PATH}")

        # Save updated rules
        with open(RULES_PATH, 'w', encoding='utf-8') as f:
            json.dump(rules, f, indent=2, ensure_ascii=False)
        print(f"✓ Updated rules saved: {RULES_PATH}")

    def categorize_rule(self, rule: Dict) -> str:
        """Categorize rule based on label, id, and category field."""
        label = rule.get('label', '').lower()
        rule_id = rule.get('id', '').lower()
        category = rule.get('category', '').lower()

        # Check patterns in order of specificity
        patterns = [
            # Special categories (check these first - very specific)
            ('arbitrage', ['arbitrage:', 'arbitrage', '→', 'cross-border']),
            ('playbook', ['playbook']),  # Matches category field
            ('analysis', ['analysis', 'risk assessment', 'threat intel']),
            ('database_search', ['database', 'records search', 'lookup']),

            # Standard categories
            ('corporate_registry', ['corporate registry', 'companies house', 'business register',
                                   'commercial register', 'company registration']),
            ('sanctions', ['sanction', 'pep', 'politically exposed', 'watchlist', 'ofac',
                          'designated', 'black list']),
            ('news_media', ['news', 'media', 'article', 'press', 'journalism', 'newspaper']),
            ('linkedin', ['linkedin']),
            ('domain', ['domain', 'whois', 'dns', 'registrar']),
            ('phone', ['phone', 'telephone', 'mobile']),
            ('email', ['email', '@', 'mailbox']),
            ('financial', ['filing', 'financial', 'revenue', 'profit', 'balance sheet',
                          'annual report', 'quarterly', 'sec filing']),
            ('beneficial_ownership', ['beneficial owner', 'ultimate beneficial', 'ubo']),
            ('shareholder', ['shareholder', 'share details', 'equity holder']),
            ('litigation', ['litigation', 'lawsuit', 'court case', 'docket', 'legal proceeding']),
            ('property', ['property', 'land record', 'real estate', 'cadastral']),
            ('vehicle', ['vehicle', 'registration', 'license plate', 'vin']),
            ('vessel', ['vessel', 'ship', 'maritime', 'imo number']),
            ('aircraft', ['aircraft', 'airplane', 'tail number', 'aviation']),
            ('license_permit', ['license', 'permit', 'certification', 'accreditation']),
            ('company_officer', ['officer', 'director', 'executive', 'board member']),
            ('company_search', ['company', 'corporate', 'business', 'firm']),
            ('person_search', ['person', 'individual', 'identity']),
            ('government', ['government', 'official', 'public record', 'ministry',
                           'regulatory', 'agency']),
        ]

        # Check against patterns
        for cat_name, keywords in patterns:
            for keyword in keywords:
                if keyword in label or keyword in rule_id or keyword in category:
                    return cat_name

        return 'other'

    def get_execution_method(self, rule: Dict, category: str) -> Optional[Dict]:
        """
        Determine appropriate execution method for a rule.

        Returns resource dict to add, or None if no execution method found.
        """
        label = rule.get('label', '').lower()
        rule_id = rule.get('id', '')

        # Internal System Rules (Skip - these are not executable via RuleExecutor)
        # ===========================================================================
        if rule_id in ['PASSWORD_EXPOSURE_LOOKUP', 'TEXT_INDEX']:
            # These are internal system tools, not external data sources
            return None

        # Special Categories
        # ==================

        # Arbitrage Rules (cross-border intelligence)
        if category == 'arbitrage':
            # Extract source and target jurisdictions from label (e.g., "GB → GE")
            import re
            match = re.search(r'([A-Z]{2})\s*→\s*([A-Z]{2})', label.upper())
            if match:
                source_juris = match.group(1)
                target_juris = match.group(2)
                source_tld = source_juris.lower()
                target_tld = target_juris.lower()
                return {
                    'type': 'brute_search',
                    'engines': ['GO', 'BI', 'BR'],
                    'wave': 'instant_start',
                    'query_template': f'"{{query}}" site:{source_tld} OR site:{target_tld}',
                    'note': f'Auto-added: Arbitrage {source_juris}→{target_juris} via cross-border search'
                }
            else:
                # Generic arbitrage search
                return {
                    'type': 'brute_search',
                    'engines': ['GO', 'BI', 'BR'],
                    'wave': 'instant_start',
                    'query_template': '"{query}" cross-border OR international',
                    'note': 'Auto-added: Generic arbitrage search'
                }

        # Playbook Rules (strategic search methodologies)
        elif category == 'playbook':
            # Playbooks are meta-instructions, use BruteSearch as fallback
            return {
                'type': 'brute_search',
                'engines': ['GO', 'BI', 'BR', 'FC'],
                'wave': 'instant_start',
                'query_template': '"{query}"',
                'note': 'Auto-added: Playbook execution via comprehensive search'
            }

        # Analysis / Risk Assessment
        elif category == 'analysis':
            return {
                'type': 'brute_search',
                'config': {
                    'engines': ['GO', 'BI', 'BR', 'FC'],
                    'wave': 'instant_start',
                    'mode': 'balanced',
                    'newsCategories': ['business', 'politics', 'crime']
                },
                'query_template': '"{query}" analysis OR assessment OR intelligence',
                'note': 'Auto-added: Intelligence analysis via news + open sources'
            }

        # Database / Records Search
        elif category == 'database_search':
            return {
                'type': 'brute_search',
                'engines': ['GO', 'BI', 'BR'],
                'wave': 'instant_start',
                'query_template': '"{query}" database OR records OR registry',
                'note': 'Auto-added: Database search via multiple engines'
            }

        # Standard Categories
        # ===================

        # Corporate Registry Rules
        if category == 'corporate_registry':
            # Check for specific jurisdictions that have Torpedo support
            torpedo_jurisdictions = ['croatia', 'hungary', 'czech', 'slovenia',
                                    'bulgaria', 'romania', 'serbia']
            for juris in torpedo_jurisdictions:
                if juris in label:
                    return {
                        'type': 'module',
                        'import': 'TORPEDO.torpedo.Torpedo',
                        'method': 'fetch_profile',
                        'note': 'Auto-added by batch_add_execution_methods.py'
                    }

            # UK Companies House
            if 'uk' in label or 'united kingdom' in label or 'companies house' in label:
                return {
                    'type': 'module',
                    'import': 'corporella.uk_companies_house_mcp',
                    'method': 'search_company',
                    'note': 'Auto-added by batch_add_execution_methods.py'
                }

            # Default: Use brute_search for corporate registries
            return {
                'type': 'brute_search',
                'engines': ['GO', 'BI', 'BR'],
                'wave': 'instant_start',
                'query_template': '"{company_name}" site:{jurisdiction} corporate registry',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Sanctions & PEP Checks
        elif category == 'sanctions':
            return {
                'type': 'brute_search',
                'engines': ['GO', 'BI'],
                'wave': 'instant_start',
                'query_template': '"{person_name}" OR "{company_name}" sanctions OR OFAC OR watchlist',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # News & Media Searches
        elif category == 'news_media':
            return {
                'type': 'brute_search',
                'config': {
                    'engines': ['GO', 'BI', 'BR', 'FC'],
                    'wave': 'instant_start',
                    'mode': 'balanced',
                    'newsCategories': ['business', 'tech', 'politics']
                },
                'query_template': '"{query}"',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # LinkedIn Lookups
        elif category == 'linkedin':
            return {
                'type': 'brute_search',
                'engines': ['LI', 'GO', 'BI'],
                'wave': 'instant_start',
                'query_template': 'site:linkedin.com "{person_name}"',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Domain Intelligence
        elif category == 'domain':
            # Use LINKLATER for domain analysis
            return {
                'type': 'module',
                'import': 'LINKLATER.api.linklater',
                'method': 'analyze_domain',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Phone Reverse Lookup
        elif category == 'phone':
            return {
                'type': 'module',
                'import': 'EYE-D.unified_osint.UnifiedSearcher',
                'method': 'search_phone',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Email OSINT
        elif category == 'email':
            return {
                'type': 'module',
                'import': 'EYE-D.unified_osint.UnifiedSearcher',
                'method': 'search_email',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Company Officer Search
        elif category == 'company_officer':
            return {
                'type': 'module',
                'import': 'corporella.company_search',
                'method': 'get_officers',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # General Company Search
        elif category == 'company_search':
            return {
                'type': 'module',
                'import': 'corporella.exa_company_search.ExaCompanySearch',
                'method': 'search',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Person Search
        elif category == 'person_search':
            return {
                'type': 'brute_search',
                'engines': ['GO', 'BI', 'PX', 'BR'],
                'wave': 'instant_start',
                'query_template': '"{person_name}" contact OR profile OR biography',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Government & Regulatory
        elif category == 'government':
            return {
                'type': 'brute_search',
                'engines': ['GO', 'BI', 'BR'],
                'wave': 'instant_start',
                'query_template': '"{query}" site:.gov OR site:.eu',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Financial Filings
        elif category == 'financial':
            return {
                'type': 'brute_search',
                'engines': ['GO', 'BI', 'BR'],
                'wave': 'instant_start',
                'query_template': '"{company_name}" financial OR filing OR "annual report" OR 10-K',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Beneficial Ownership
        elif category == 'beneficial_ownership':
            return {
                'type': 'brute_search',
                'engines': ['GO', 'BI', 'BR'],
                'wave': 'instant_start',
                'query_template': '"{company_name}" "beneficial owner" OR UBO OR "ultimate beneficial"',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Shareholder Information
        elif category == 'shareholder':
            return {
                'type': 'brute_search',
                'engines': ['GO', 'BI', 'BR'],
                'wave': 'instant_start',
                'query_template': '"{company_name}" shareholder OR "share capital" OR equity',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Litigation & Court Cases
        elif category == 'litigation':
            return {
                'type': 'brute_search',
                'engines': ['GO', 'BI', 'BR'],
                'wave': 'instant_start',
                'query_template': '"{query}" litigation OR lawsuit OR "court case" OR docket',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Property & Land Records
        elif category == 'property':
            return {
                'type': 'brute_search',
                'engines': ['GO', 'BI', 'BR'],
                'wave': 'instant_start',
                'query_template': '"{query}" property OR "land record" OR cadastral OR deed',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Vehicle Registration
        elif category == 'vehicle':
            return {
                'type': 'brute_search',
                'engines': ['GO', 'BI'],
                'wave': 'instant_start',
                'query_template': '"{query}" vehicle OR registration OR VIN',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Vessel / Maritime
        elif category == 'vessel':
            return {
                'type': 'brute_search',
                'engines': ['GO', 'BI', 'BR'],
                'wave': 'instant_start',
                'query_template': '"{query}" vessel OR ship OR IMO OR maritime',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Aircraft
        elif category == 'aircraft':
            return {
                'type': 'brute_search',
                'engines': ['GO', 'BI', 'BR'],
                'wave': 'instant_start',
                'query_template': '"{query}" aircraft OR airplane OR "tail number" OR FAA',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        # Licenses & Permits
        elif category == 'license_permit':
            return {
                'type': 'brute_search',
                'engines': ['GO', 'BI', 'BR'],
                'wave': 'instant_start',
                'query_template': '"{query}" license OR permit OR certification',
                'note': 'Auto-added by batch_add_execution_methods.py'
            }

        return None

    def process_rules(self, rules: List[Dict], dry_run: bool = False) -> List[Dict]:
        """
        Process rules and add execution methods where missing.

        Args:
            rules: List of rule dicts
            dry_run: If True, don't modify rules, just report stats

        Returns:
            Updated list of rules
        """
        self.stats['total'] = len(rules)
        updated_rules = []

        for rule in rules:
            rule_id = rule.get('id', 'unknown')
            resources = rule.get('resources', [])

            # Track rules without resources
            if not resources:
                self.stats['no_resources'] += 1

                # Categorize the rule
                category = self.categorize_rule(rule)

                # Track by category
                if category not in self.stats['by_category']:
                    self.stats['by_category'][category] = 0
                self.stats['by_category'][category] += 1

                # Get execution method
                execution_method = self.get_execution_method(rule, category)

                if execution_method and not dry_run:
                    # Add resource to rule
                    rule['resources'] = [execution_method]
                    self.stats['updated'] += 1
                    print(f"  ✓ {rule_id} ({category}): Added {execution_method['type']}")
                elif execution_method and dry_run:
                    self.stats['updated'] += 1
                    print(f"  [DRY RUN] {rule_id} ({category}): Would add {execution_method['type']}")

            updated_rules.append(rule)

        return updated_rules

    def print_stats(self):
        """Print statistics about the update."""
        print("\n" + "="*60)
        print("UPDATE STATISTICS")
        print("="*60)
        print(f"Total rules:                {self.stats['total']:,}")
        print(f"Rules without resources:    {self.stats['no_resources']:,}")
        print(f"Rules updated:              {self.stats['updated']:,}")
        print(f"Rules still without exec:   {self.stats['no_resources'] - self.stats['updated']:,}")
        print(f"\nBreakdown by category:")
        for category, count in sorted(self.stats['by_category'].items(),
                                      key=lambda x: x[1], reverse=True):
            print(f"  {category:25s}: {count:4d} rules")
        print("="*60)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Batch add execution methods to rules.json',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (preview changes)
  python batch_add_execution_methods.py --dry-run

  # Apply updates
  python batch_add_execution_methods.py

  # Show only statistics
  python batch_add_execution_methods.py --dry-run --quiet
        """
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without modifying files')
    parser.add_argument('--quiet', action='store_true',
                       help='Suppress per-rule output (show only stats)')

    args = parser.parse_args()

    print("="*60)
    print("BATCH ADD EXECUTION METHODS")
    print("="*60)
    print(f"Rules file: {RULES_PATH}")
    if args.dry_run:
        print("Mode: DRY RUN (no changes will be made)")
    else:
        print("Mode: LIVE UPDATE")
    print("="*60 + "\n")

    # Initialize updater
    updater = RuleUpdater()

    # Load rules
    print("Loading rules...")
    rules = updater.load_rules()
    print(f"✓ Loaded {len(rules):,} rules\n")

    # Process rules
    print("Processing rules...\n")
    if not args.quiet:
        updated_rules = updater.process_rules(rules, dry_run=args.dry_run)
    else:
        # Suppress output during processing
        import sys
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        updated_rules = updater.process_rules(rules, dry_run=args.dry_run)
        sys.stdout = old_stdout

    # Print statistics
    updater.print_stats()

    # Save if not dry run
    if not args.dry_run and updater.stats['updated'] > 0:
        print(f"\nSaving {updater.stats['updated']:,} updates...")
        updater.save_rules(updated_rules)
        print("\n✓ Update complete!")
    elif args.dry_run:
        print("\n✓ Dry run complete. No changes made.")
        print("  Run without --dry-run to apply changes.")
    else:
        print("\n✓ No rules needed updating.")


if __name__ == '__main__':
    main()
