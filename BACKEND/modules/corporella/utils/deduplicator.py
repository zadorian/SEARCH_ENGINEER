"""
Advanced Company Deduplication System
Provides intelligent deduplication of company records from multiple sources
"""

import re
from typing import List, Dict, Optional
from difflib import SequenceMatcher


class CompanyDeduplicator:
    """Advanced deduplication system for company records"""

    # Common company suffixes to normalize
    COMPANY_SUFFIXES = {
        'limited': 'ltd',
        'incorporated': 'inc',
        'corporation': 'corp',
        'company': 'co',
        'gesellschaft mit beschränkter haftung': 'gmbh',
        'aktiengesellschaft': 'ag',
        'société anonyme': 'sa',
        'société à responsabilité limitée': 'sarl',
        'public limited company': 'plc',
        'private limited company': 'ltd',
        'limited liability company': 'llc',
        'limited liability partnership': 'llp',
        'besloten vennootschap': 'bv',
        'naamloze vennootschap': 'nv',
    }

    # Similarity threshold for fuzzy matching
    SIMILARITY_THRESHOLD = 0.85

    @classmethod
    def normalize_company_name(cls, name: str) -> str:
        """
        Normalize company name for comparison

        Args:
            name: Company name to normalize

        Returns:
            Normalized name in uppercase with standardized suffixes
        """
        if not name:
            return ""

        # Convert to lowercase for processing
        normalized = name.lower().strip()

        # Remove common punctuation
        normalized = re.sub(r'[.,\-\'\"&]', ' ', normalized)

        # Replace multiple spaces with single space
        normalized = re.sub(r'\s+', ' ', normalized)

        # Standardize company suffixes
        for long_form, short_form in cls.COMPANY_SUFFIXES.items():
            # Match whole words only
            pattern = r'\b' + re.escape(long_form) + r'\b'
            normalized = re.sub(pattern, short_form, normalized)

        # Remove parenthetical content (often contains old names or translations)
        normalized = re.sub(r'\([^)]*\)', '', normalized)

        # Final cleanup
        normalized = normalized.strip().upper()

        return normalized

    @classmethod
    def calculate_similarity(cls, name1: str, name2: str) -> float:
        """
        Calculate similarity between two company names

        Args:
            name1: First company name
            name2: Second company name

        Returns:
            Similarity score between 0 and 1
        """
        norm1 = cls.normalize_company_name(name1)
        norm2 = cls.normalize_company_name(name2)

        return SequenceMatcher(None, norm1, norm2).ratio()

    @classmethod
    def are_duplicates(cls, result1: Dict, result2: Dict) -> bool:
        """
        Determine if two results represent the same company

        Args:
            result1: First company result dict
            result2: Second company result dict

        Returns:
            True if they are duplicates
        """
        # Check LEI match (highest confidence)
        lei1 = result1.get('lei')
        lei2 = result2.get('lei')
        if lei1 and lei2 and lei1 == lei2:
            return True

        # Check company number and jurisdiction match
        num1 = result1.get('company_number')
        num2 = result2.get('company_number')
        jur1 = result1.get('jurisdiction_code') or result1.get('jurisdiction')
        jur2 = result2.get('jurisdiction_code') or result2.get('jurisdiction')

        if num1 and num2 and num1 == num2 and jur1 == jur2:
            return True

        # Fuzzy name matching for same jurisdiction
        if jur1 == jur2:
            name1 = result1.get('name', '')
            name2 = result2.get('name', '')
            similarity = cls.calculate_similarity(name1, name2)

            if similarity >= cls.SIMILARITY_THRESHOLD:
                return True

        return False

    @classmethod
    def deduplicate(cls, results: List[Dict]) -> List[Dict]:
        """
        Remove duplicate companies from search results

        Args:
            results: List of company search result dicts

        Returns:
            Deduplicated list with highest quality results preserved
        """
        if not results:
            return []

        # Group potential duplicates
        groups = []
        processed = set()

        for i, result in enumerate(results):
            if i in processed:
                continue

            group = [result]
            processed.add(i)

            for j, other in enumerate(results[i+1:], start=i+1):
                if j in processed:
                    continue

                if cls.are_duplicates(result, other):
                    group.append(other)
                    processed.add(j)

            groups.append(group)

        # Select best result from each group
        unique_results = []
        for group in groups:
            best = cls._select_best_result(group)
            unique_results.append(best)

        return unique_results

    @classmethod
    def _select_best_result(cls, group: List[Dict]) -> Dict:
        """
        Select the best result from a group of duplicates

        Args:
            group: List of duplicate results

        Returns:
            Best quality result from the group
        """
        if len(group) == 1:
            return group[0]

        # Score each result
        scored = []
        for result in group:
            score = 0

            # Prefer active companies
            status = str(result.get('current_status', '')).lower()
            if 'active' in status:
                score += 10

            # Prefer results with more data
            if result.get('registered_address'):
                score += 5
            if result.get('company_number'):
                score += 3
            if result.get('lei'):
                score += 3

            # Prefer official sources
            source_priority = {
                'companies_house': 10,
                'edgar': 9,
                'opencorporates': 8,
                'aleph': 5,
            }
            source = str(result.get('source', '')).lower()
            for key, value in source_priority.items():
                if key in source:
                    score += value
                    break

            scored.append((score, result))

        # Return highest scoring result
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]


# Simple usage example
if __name__ == "__main__":
    # Test deduplication
    results = [
        {"name": "Apple Inc.", "company_number": "C0806592", "jurisdiction_code": "us_ca"},
        {"name": "Apple Incorporated", "company_number": "C0806592", "jurisdiction_code": "us_ca"},
        {"name": "Apple Inc", "company_number": "C0806592", "jurisdiction_code": "us_ca"},
        {"name": "Microsoft Corporation", "company_number": "600413485", "jurisdiction_code": "us_wa"},
    ]

    deduplicator = CompanyDeduplicator()
    unique = deduplicator.deduplicate(results)

    print(f"Original: {len(results)} results")
    print(f"After deduplication: {len(unique)} unique companies")

    for company in unique:
        print(f"  - {company['name']} ({company['jurisdiction_code']})")
