#!/usr/bin/env python3
"""
Pattern Matcher for News Search Results
========================================
Uses learned patterns to automatically filter out "no results" pages.
Ensures only domains with actual results appear in search output.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional


class NewsPatternMatcher:
    """Matches search results against learned patterns to filter empty results."""

    def __init__(self, patterns_file: Optional[str] = None):
        """Initialize with patterns database."""
        if patterns_file is None:
            patterns_file = Path(__file__).parent / "news_patterns_database.json"

        self.patterns = {}
        self.load_patterns(patterns_file)

    def load_patterns(self, patterns_file: Path):
        """Load the patterns database."""
        if isinstance(patterns_file, str):
            patterns_file = Path(patterns_file)

        if patterns_file.exists():
            try:
                with open(patterns_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.patterns = data.get('patterns', {})
                    print(f"✓ Loaded patterns for {len(self.patterns)} domains")
            except Exception as e:
                print(f"Warning: Could not load patterns: {e}")
                self.patterns = {}
        else:
            print(f"Warning: Patterns file not found: {patterns_file}")
            self.patterns = {}

    def has_results(self, domain: str, content: str) -> bool:
        """
        Check if the content from a domain has actual results.
        Returns True if results found, False if it's a "no results" page.
        """
        if not content:
            return False

        content_lower = content.lower()

        # Get patterns for this domain
        domain_patterns = self.patterns.get(domain, {})

        # Check for known "no results" indicators for this domain
        no_results_indicators = domain_patterns.get('no_results_indicators', [])
        if no_results_indicators:
            for indicator in no_results_indicators:
                if indicator.lower() in content_lower:
                    return False  # Found a "no results" indicator

        # Check for general "no results" patterns
        general_no_results = [
            'no results found',
            'no matches found',
            'nothing found',
            '0 results',
            'zero results',
            'your search did not match',
            'no articles found',
            'no stories found',
            'try different keywords',
            'couldn\'t find',
            'no items match',
            'search returned no',
            'keine ergebnisse',  # German
            'aucun résultat',    # French
            'sin resultados',     # Spanish
            'nessun risultato',   # Italian
            'sem resultados',     # Portuguese
        ]

        for pattern in general_no_results:
            if pattern in content_lower:
                return False

        # Check minimum content requirements
        success_indicators = domain_patterns.get('success_indicators', {})
        min_words = success_indicators.get('min_words', 100)
        requires_links = success_indicators.get('requires_links', False)

        # Count words
        word_count = len(content.split())
        if word_count < min_words:
            return False

        # Check for links if required
        if requires_links:
            # Look for any HTML links or markdown links
            link_patterns = [
                r'href="[^"]+"',           # HTML links
                r'\[([^\]]+)\]\([^\)]+\)',  # Markdown links
                r'https?://[^\s]+',         # URLs
            ]

            has_links = False
            for pattern in link_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    has_links = True
                    break

            if not has_links:
                return False

        # Check reliability score
        reliability = domain_patterns.get('reliability', 0.5)
        if reliability < 0.3:
            # This domain is known to be unreliable
            return False

        # If we passed all checks, assume we have results
        return True

    def filter_results(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter a list of search results to remove "no results" pages.

        Args:
            search_results: List of result dicts with 'domain' and 'content' keys

        Returns:
            Filtered list with only results that have actual content
        """
        filtered = []

        for result in search_results:
            domain = result.get('domain', '')
            content = result.get('content', '')

            if self.has_results(domain, content):
                filtered.append(result)
            else:
                # Log filtered results for debugging
                print(f"   ✗ Filtered out {domain} (no results detected)")

        return filtered

    def get_reliable_domains(self, min_reliability: float = 0.8) -> List[str]:
        """Get list of domains with high reliability scores."""
        reliable = []
        for domain, patterns in self.patterns.items():
            if patterns.get('reliability', 0) >= min_reliability:
                reliable.append(domain)
        return sorted(reliable)

    def get_broken_domains(self) -> List[str]:
        """Get list of domains that are broken or don't support search."""
        broken = []
        for domain, patterns in self.patterns.items():
            if patterns.get('pattern') in ['broken', 'no_search', 'error']:
                broken.append(domain)
        return sorted(broken)

    def update_pattern(self, domain: str, has_results: bool, content: str):
        """
        Update patterns based on new observations.
        This allows the system to learn and improve over time.
        """
        if domain not in self.patterns:
            self.patterns[domain] = {
                'reliability': 0.5,
                'no_results_indicators': [],
                'success_indicators': {
                    'min_words': 100,
                    'requires_links': False
                }
            }

        # Update based on observation
        if not has_results:
            # Look for new no-results indicators
            content_lower = content.lower()
            potential_indicators = [
                'no results', 'nothing found', '0 results',
                'no matches', 'try again', 'couldn\'t find'
            ]

            for indicator in potential_indicators:
                if indicator in content_lower and indicator not in self.patterns[domain]['no_results_indicators']:
                    self.patterns[domain]['no_results_indicators'].append(indicator)

        # Adjust reliability based on consistency
        # (This is a simple heuristic - could be improved with ML)
        word_count = len(content.split())
        if has_results and word_count > 200:
            # Increase reliability
            self.patterns[domain]['reliability'] = min(1.0, self.patterns[domain]['reliability'] + 0.1)
        elif not has_results and word_count < 100:
            # Decrease reliability
            self.patterns[domain]['reliability'] = max(0.0, self.patterns[domain]['reliability'] - 0.1)

    def save_patterns(self, output_file: Optional[str] = None):
        """Save updated patterns back to file."""
        if output_file is None:
            output_file = Path(__file__).parent / "news_patterns_database.json"

        data = {
            'patterns': self.patterns,
            'metadata': {
                'total_domains': len(self.patterns),
                'reliable': len(self.get_reliable_domains()),
                'broken': len(self.get_broken_domains())
            }
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        print(f"✓ Saved patterns for {len(self.patterns)} domains")


# Integration helper for news.py
def filter_news_results(results: List[Dict[str, Any]],
                       patterns_file: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Convenience function to filter news search results.

    Usage in news.py:
        from pattern_matcher import filter_news_results
        filtered = filter_news_results(raw_results)
    """
    matcher = NewsPatternMatcher(patterns_file)
    return matcher.filter_results(results)


def test_pattern_matcher():
    """Test the pattern matcher with sample data."""
    print("Testing Pattern Matcher")
    print("-" * 40)

    # Create test patterns
    test_patterns = {
        'patterns': {
            'bbc.com': {
                'reliability': 0.95,
                'no_results_indicators': ['Sorry, no results were found'],
                'success_indicators': {'min_words': 200, 'requires_links': True}
            },
            'cnn.com': {
                'reliability': 0.9,
                'no_results_indicators': ['Your search did not match any documents'],
                'success_indicators': {'min_words': 150, 'requires_links': True}
            },
            'brokensite.com': {
                'reliability': 0.1,
                'pattern': 'broken'
            }
        }
    }

    # Save test patterns
    test_file = Path('/tmp/test_patterns.json')
    with open(test_file, 'w') as f:
        json.dump(test_patterns, f)

    # Initialize matcher
    matcher = NewsPatternMatcher(test_file)

    # Test cases
    test_cases = [
        {
            'domain': 'bbc.com',
            'content': 'Breaking news: Major event... [Read more](http://example.com) ' * 50,
            'expected': True
        },
        {
            'domain': 'bbc.com',
            'content': 'Sorry, no results were found for your search.',
            'expected': False
        },
        {
            'domain': 'cnn.com',
            'content': 'Your search did not match any documents.',
            'expected': False
        },
        {
            'domain': 'unknown.com',
            'content': 'Some content here ' * 50,
            'expected': True
        },
        {
            'domain': 'brokensite.com',
            'content': 'Some content',
            'expected': False  # Low reliability
        }
    ]

    # Run tests
    passed = 0
    for i, test in enumerate(test_cases, 1):
        result = matcher.has_results(test['domain'], test['content'])
        status = "✓" if result == test['expected'] else "✗"
        passed += (result == test['expected'])
        print(f"  Test {i}: {status} {test['domain']} - Expected: {test['expected']}, Got: {result}")

    print(f"\nPassed {passed}/{len(test_cases)} tests")

    # Test filtering
    print("\nTesting batch filtering:")
    results = [
        {'domain': 'bbc.com', 'content': 'Real news content ' * 100},
        {'domain': 'cnn.com', 'content': 'Your search did not match any documents.'},
        {'domain': 'reuters.com', 'content': 'Latest updates... ' * 50}
    ]

    filtered = matcher.filter_results(results)
    print(f"  Filtered {len(results)} results to {len(filtered)}")


if __name__ == "__main__":
    test_pattern_matcher()