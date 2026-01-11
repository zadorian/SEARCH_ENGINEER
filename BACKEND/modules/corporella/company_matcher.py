"""
Company matching algorithms for identifying the same company across different data sources
"""
import re
from typing import Dict, Tuple, List, Optional, Any
from difflib import SequenceMatcher
from models.unified_company import UnifiedCompanyProfile, ConfidenceLevel
import logging

logger = logging.getLogger(__name__)


class CompanyMatcher:
    """
    Sophisticated matching algorithm to identify the same company across different data sources
    """
    
    # Company type suffixes to normalize
    COMPANY_SUFFIXES = [
        'LIMITED', 'LTD', 'LLC', 'L.L.C.', 'INC', 'INCORPORATED', 'CORP', 'CORPORATION',
        'COMPANY', 'CO', 'PLC', 'P.L.C.', 'LP', 'L.P.', 'LLP', 'L.L.P.',
        'GMBH', 'AG', 'SA', 'S.A.', 'SRL', 'S.R.L.', 'BV', 'B.V.', 'NV', 'N.V.',
        'PTY', 'PTY LTD', 'PROPRIETARY LIMITED', 'PVT', 'PVT LTD', 'PRIVATE LIMITED'
    ]
    
    # Common words to ignore in matching
    IGNORE_WORDS = ['THE', 'AND', '&', 'OF', 'FOR', 'IN']
    
    def __init__(self):
        self.suffix_pattern = self._build_suffix_pattern()
    
    def _build_suffix_pattern(self) -> re.Pattern:
        """Build regex pattern for company suffixes"""
        suffix_regex = '|'.join(re.escape(suffix) for suffix in self.COMPANY_SUFFIXES)
        return re.compile(rf'\b({suffix_regex})\b\.?$', re.IGNORECASE)
    
    def normalize_company_name(self, name: str) -> str:
        """
        Normalize company name for matching
        - Remove company type suffixes
        - Convert to uppercase
        - Remove special characters
        - Remove common words
        """
        if not name:
            return ""
        
        # Convert to uppercase
        normalized = name.upper().strip()
        
        # Remove company type suffixes
        normalized = self.suffix_pattern.sub('', normalized).strip()
        
        # Remove special characters but keep spaces
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
        
        # Remove common words
        words = normalized.split()
        filtered_words = [w for w in words if w not in self.IGNORE_WORDS]
        
        return ' '.join(filtered_words)
    
    def extract_company_number(self, number: str) -> str:
        """Extract and normalize company registration number"""
        if not number:
            return ""
        
        # Remove all non-alphanumeric characters
        return re.sub(r'[^A-Z0-9]', '', number.upper())
    
    def fuzzy_match_score(self, str1: str, str2: str) -> float:
        """Calculate fuzzy match score between two strings"""
        if not str1 or not str2:
            return 0.0
        
        return SequenceMatcher(None, str1, str2).ratio()
    
    def match_addresses(self, addr1: Any, addr2: Any) -> float:
        """Calculate address similarity score"""
        if not addr1 or not addr2:
            return 0.0
        
        # Compare countries first
        country1 = getattr(addr1, 'country', '').upper()
        country2 = getattr(addr2, 'country', '').upper()
        
        if country1 and country2 and country1 != country2:
            return 0.0
        
        # Compare cities
        city1 = getattr(addr1, 'city', '').upper()
        city2 = getattr(addr2, 'city', '').upper()
        
        if city1 and city2:
            city_score = self.fuzzy_match_score(city1, city2)
            if city_score < 0.8:
                return city_score * 0.5
        
        # Compare full addresses
        full1 = getattr(addr1, 'raw_address', '').upper()
        full2 = getattr(addr2, 'raw_address', '').upper()
        
        return self.fuzzy_match_score(full1, full2)
    
    def match_people(self, people1: List[Any], people2: List[Any]) -> Tuple[float, int]:
        """
        Match people (officers/directors) between two companies
        Returns (match_score, number_of_matches)
        """
        if not people1 or not people2:
            return 0.0, 0
        
        matches = 0
        names1 = {p.name.upper() for p in people1 if hasattr(p, 'name')}
        names2 = {p.name.upper() for p in people2 if hasattr(p, 'name')}
        
        # Check for exact matches
        exact_matches = names1.intersection(names2)
        matches = len(exact_matches)
        
        # Check for fuzzy matches
        for name1 in names1 - exact_matches:
            for name2 in names2 - exact_matches:
                if self.fuzzy_match_score(name1, name2) > 0.9:
                    matches += 1
                    break
        
        # Calculate score based on overlap
        total_unique = len(names1.union(names2))
        if total_unique > 0:
            score = matches / total_unique
        else:
            score = 0.0
        
        return score, matches
    
    def match_companies(self, company1: Dict[str, Any], company2: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """
        Match companies based on multiple criteria
        Returns (confidence_score, match_details)
        """
        match_details = {
            'criteria_matched': [],
            'scores': {}
        }
        
        # Extract relevant fields
        name1 = company1.get('name', '')
        name2 = company2.get('name', '')
        
        # Normalize names
        norm_name1 = self.normalize_company_name(name1)
        norm_name2 = self.normalize_company_name(name2)
        
        # 1. Company Number + Jurisdiction (100% confidence)
        numbers1 = company1.get('company_numbers', {})
        numbers2 = company2.get('company_numbers', {})
        
        if numbers1 and numbers2:
            for jurisdiction, num1 in numbers1.items():
                num2 = numbers2.get(jurisdiction)
                if num2 and self.extract_company_number(num1) == self.extract_company_number(num2):
                    match_details['criteria_matched'].append('company_number_jurisdiction')
                    match_details['scores']['company_number'] = 1.0
                    return ConfidenceLevel.EXACT.value / 100, match_details
        
        # 2. Exact Name + Same Country (95% confidence)
        country1 = company1.get('countries', [])[0] if company1.get('countries') else None
        country2 = company2.get('countries', [])[0] if company2.get('countries') else None
        
        if country1 and country2 and country1 == country2:
            if name1.upper() == name2.upper():
                match_details['criteria_matched'].append('exact_name_same_country')
                match_details['scores']['name'] = 1.0
                return ConfidenceLevel.VERY_HIGH.value / 100, match_details
        
        # 3. Normalized Name + Same Country (85% confidence)
        if country1 and country2 and country1 == country2:
            if norm_name1 == norm_name2:
                match_details['criteria_matched'].append('normalized_name_same_country')
                match_details['scores']['normalized_name'] = 1.0
                return ConfidenceLevel.HIGH.value / 100, match_details
        
        # 4. Fuzzy Name Match + Same Country (80% confidence)
        name_score = self.fuzzy_match_score(norm_name1, norm_name2)
        match_details['scores']['fuzzy_name'] = name_score
        
        if country1 and country2 and country1 == country2:
            if name_score > 0.9:
                match_details['criteria_matched'].append('fuzzy_name_same_country')
                return ConfidenceLevel.MEDIUM.value / 100, match_details
        
        # 5. Shared Directors/Officers (70% confidence)
        officers1 = company1.get('officers', [])
        officers2 = company2.get('officers', [])
        directors1 = company1.get('directors', [])
        directors2 = company2.get('directors', [])
        
        all_people1 = officers1 + directors1
        all_people2 = officers2 + directors2
        
        if all_people1 and all_people2:
            people_score, people_matches = self.match_people(all_people1, all_people2)
            match_details['scores']['people'] = people_score
            match_details['people_matches'] = people_matches
            
            if people_matches >= 2 or people_score > 0.5:
                match_details['criteria_matched'].append('shared_people')
                return ConfidenceLevel.LOW.value / 100, match_details
        
        # 6. Similar Address (60% confidence)
        addr1 = company1.get('registered_address') or company1.get('headquarters_address')
        addr2 = company2.get('registered_address') or company2.get('headquarters_address')
        
        if addr1 and addr2:
            addr_score = self.match_addresses(addr1, addr2)
            match_details['scores']['address'] = addr_score
            
            if addr_score > 0.8:
                match_details['criteria_matched'].append('similar_address')
                return ConfidenceLevel.MINIMAL.value / 100, match_details
        
        # Calculate overall score if no specific criteria matched
        overall_score = (
            name_score * 0.5 +
            match_details.get('scores', {}).get('people', 0) * 0.3 +
            match_details.get('scores', {}).get('address', 0) * 0.2
        )
        
        return overall_score, match_details
    
    def find_best_match(self, company: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Optional[Tuple[Dict[str, Any], float, Dict[str, Any]]]:
        """
        Find the best matching company from a list of candidates
        Returns (best_match, confidence_score, match_details) or None
        """
        best_match = None
        best_score = 0.0
        best_details = {}
        
        for candidate in candidates:
            score, details = self.match_companies(company, candidate)
            if score > best_score:
                best_score = score
                best_match = candidate
                best_details = details
        
        # Only return matches above a minimum threshold
        if best_score >= 0.6:
            return best_match, best_score, best_details
        
        return None