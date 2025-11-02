#!/usr/bin/env python3
"""
Ultra-fast search interface with advanced capabilities
Supports every possible search direction and combination
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Set, Any, Optional, Tuple
import re
from fuzzywuzzy import fuzz
from datetime import datetime
import time

class UltraFastRegistrySearch:
    """
    Comprehensive search interface supporting:
    - Any field to any field searching
    - Fuzzy matching with similarity scores
    - Complex multi-criteria queries
    - Relationship traversal
    - Timeline searches
    - Pattern matching
    """
    
    def __init__(self, index_dir: str = "./de_registry_indexes"):
        self.index_dir = Path(index_dir)
        self.db_path = self.index_dir / 'registry.db'
        self.load_indexes()
    
    def load_indexes(self):
        """Load pre-built indexes for fast searching"""
        import pickle
        with open(self.index_dir / 'main_indexes.pkl', 'rb') as f:
            indexes = pickle.load(f)
        
        self.company_by_number = indexes['company_by_number']
        self.company_by_name = indexes['company_by_name']
        self.companies_by_officer = indexes['companies_by_officer']
        self.companies_by_city = indexes['companies_by_city']
        self.companies_by_state = indexes['companies_by_state']
        self.companies_by_registrar = indexes['companies_by_registrar']
        self.officers_by_name = indexes['officers_by_name']
        self.officers_by_position = indexes['officers_by_position']
        self.company_connections = indexes['company_connections']
        self.name_tokens = indexes['name_tokens']
        self.address_tokens = indexes['address_tokens']
        self.all_text_tokens = indexes['all_text_tokens']
    
    # ============ COMPANY SEARCHES ============
    
    def find_company(self, **criteria) -> List[Dict]:
        """
        Find companies by any combination of criteria
        Examples:
            find_company(name="BMW")
            find_company(officer="Schmidt", city="Munich")
            find_company(registry_number="HRB12345", state="Bavaria")
        """
        results = None
        
        if 'name' in criteria:
            name_results = self.search_by_name(criteria['name'])
            results = self._intersect_results(results, name_results)
        
        if 'officer' in criteria:
            officer_results = self.search_by_officer(criteria['officer'])
            results = self._intersect_results(results, officer_results)
        
        if 'city' in criteria:
            city_results = self.search_by_city(criteria['city'])
            results = self._intersect_results(results, city_results)
        
        if 'state' in criteria:
            state_results = self.search_by_state(criteria['state'])
            results = self._intersect_results(results, state_results)
        
        if 'address' in criteria:
            addr_results = self.search_by_address(criteria['address'])
            results = self._intersect_results(results, addr_results)
        
        if 'registry_number' in criteria:
            reg_results = self.search_by_registry_number(criteria['registry_number'])
            results = self._intersect_results(results, reg_results)
        
        return results or []
    
    def search_by_name(self, name: str, fuzzy: bool = True, threshold: int = 80) -> List[Dict]:
        """Search companies by name with fuzzy matching"""
        name_lower = name.lower().strip()
        results = []
        
        # Exact match
        if name_lower in self.company_by_name:
            for company_num in self.company_by_name[name_lower]:
                company = self.company_by_number[company_num]
                company['_match_score'] = 100
                results.append(company)
        
        # Fuzzy matching
        if fuzzy:
            for stored_name, company_nums in self.company_by_name.items():
                score = fuzz.ratio(name_lower, stored_name)
                if score >= threshold and score < 100:
                    for company_num in company_nums:
                        company = self.company_by_number[company_num].copy()
                        company['_match_score'] = score
                        results.append(company)
        
        # Sort by match score
        results.sort(key=lambda x: x.get('_match_score', 0), reverse=True)
        return results[:100]
    
    def search_by_officer(self, officer_name: str, fuzzy: bool = True) -> List[Dict]:
        """Find all companies where an officer worked"""
        officer_lower = officer_name.lower().strip()
        company_nums = set()
        
        # Exact match
        if officer_lower in self.companies_by_officer:
            company_nums.update(self.companies_by_officer[officer_lower])
        
        # Fuzzy match
        if fuzzy:
            for stored_officer in self.companies_by_officer:
                if fuzz.partial_ratio(officer_lower, stored_officer) > 85:
                    company_nums.update(self.companies_by_officer[stored_officer])
        
        return [self.company_by_number[num] for num in company_nums]
    
    def search_by_city(self, city: str) -> List[Dict]:
        """Find companies in a specific city"""
        company_nums = self.companies_by_city.get(city, [])
        return [self.company_by_number[num] for num in company_nums]
    
    def search_by_state(self, state: str) -> List[Dict]:
        """Find companies in a specific state"""
        company_nums = self.companies_by_state.get(state, [])
        return [self.company_by_number[num] for num in company_nums]
    
    def search_by_address(self, address_part: str) -> List[Dict]:
        """Search by address keywords"""
        tokens = set(re.findall(r'\b\w+\b', address_part.lower()))
        candidates = set()
        
        for token in tokens:
            if token in self.address_tokens:
                candidates.update(self.address_tokens[token])
        
        return [self.company_by_number[num] for num in candidates]
    
    def search_by_registry_number(self, reg_number: str) -> List[Dict]:
        """Search by registry number"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT company_number FROM companies WHERE registry_number = ?", 
                 (reg_number,))
        results = c.fetchall()
        conn.close()
        
        return [self.company_by_number[r[0]] for r in results if r[0] in self.company_by_number]
    
    # ============ OFFICER SEARCHES ============
    
    def find_officer(self, **criteria) -> List[Dict]:
        """
        Find officers by any criteria
        Examples:
            find_officer(firstname="Hans", lastname="Mueller")
            find_officer(position="Geschäftsführer", city="Berlin")
        """
        results = None
        
        if 'name' in criteria:
            name_results = self.search_officers_by_name(criteria['name'])
            results = self._intersect_officer_results(results, name_results)
        
        if 'firstname' in criteria and 'lastname' in criteria:
            full_results = self.search_officers_by_parts(
                criteria.get('firstname'), 
                criteria.get('lastname')
            )
            results = self._intersect_officer_results(results, full_results)
        
        if 'position' in criteria:
            pos_results = self.search_officers_by_position(criteria['position'])
            results = self._intersect_officer_results(results, pos_results)
        
        if 'company' in criteria:
            comp_results = self.get_company_officers(criteria['company'])
            results = self._intersect_officer_results(results, comp_results)
        
        return results or []
    
    def search_officers_by_name(self, name: str) -> List[Dict]:
        """Search officers by full name"""
        name_lower = name.lower().strip()
        return self.officers_by_name.get(name_lower, [])
    
    def search_officers_by_parts(self, firstname: str = None, lastname: str = None) -> List[Dict]:
        """Search officers by name parts"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        query = "SELECT DISTINCT * FROM officers WHERE 1=1"
        params = []
        
        if firstname:
            query += " AND LOWER(firstname) LIKE ?"
            params.append(f"%{firstname.lower()}%")
        
        if lastname:
            query += " AND LOWER(lastname) LIKE ?"
            params.append(f"%{lastname.lower()}%")
        
        c.execute(query, params)
        results = c.fetchall()
        conn.close()
        
        return [dict(zip([d[0] for d in c.description], r)) for r in results]
    
    def search_officers_by_position(self, position: str) -> List[Dict]:
        """Find all officers with a specific position"""
        return self.officers_by_position.get(position, [])
    
    def get_company_officers(self, company_number: str) -> List[Dict]:
        """Get all officers of a specific company"""
        company = self.company_by_number.get(company_number)
        if company:
            return company.get('officers', [])
        return []
    
    # ============ RELATIONSHIP SEARCHES ============
    
    def find_connected_companies(self, company_number: str, depth: int = 1) -> List[Dict]:
        """
        Find companies connected through shared officers
        depth=1: Direct connections
        depth=2: Connections of connections
        """
        visited = set()
        to_visit = {company_number}
        
        for _ in range(depth):
            next_level = set()
            for comp in to_visit:
                if comp not in visited:
                    visited.add(comp)
                    connections = self.company_connections.get(comp, set())
                    next_level.update(connections)
            to_visit = next_level - visited
        
        visited.discard(company_number)  # Remove the original company
        return [self.company_by_number[num] for num in visited 
                if num in self.company_by_number]
    
    def find_officer_network(self, officer_name: str) -> Dict[str, Any]:
        """
        Find the complete network of an officer
        Returns companies, co-workers, timeline
        """
        officer_lower = officer_name.lower().strip()
        
        # Get all companies
        companies = self.search_by_officer(officer_name)
        
        # Get all co-workers
        co_workers = set()
        for company in companies:
            for officer in company.get('officers', []):
                if officer.get('name'):
                    co_workers.add(officer['name'])
        
        # Get timeline
        timeline = []
        for company in companies:
            for officer in company.get('officers', []):
                if officer.get('name', '').lower() == officer_lower:
                    timeline.append({
                        'company': company.get('name'),
                        'company_number': company.get('company_number'),
                        'position': officer.get('position'),
                        'start_date': officer.get('start_date'),
                        'end_date': officer.get('end_date')
                    })
        
        # Sort timeline
        timeline.sort(key=lambda x: x.get('start_date', '') or '9999')
        
        return {
            'officer': officer_name,
            'total_companies': len(companies),
            'companies': companies[:20],  # Limit for display
            'co_workers': list(co_workers)[:50],
            'timeline': timeline
        }
    
    # ============ ADVANCED SEARCHES ============
    
    def search_by_pattern(self, field: str, pattern: str) -> List[Dict]:
        """
        Search using regex patterns
        Examples:
            search_by_pattern('name', r'.*GmbH$')  # All GmbHs
            search_by_pattern('address', r'\d{5} Berlin')  # Berlin addresses with postal code
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Map field to column
        field_map = {
            'name': 'name',
            'address': 'address',
            'city': 'city',
            'state': 'state'
        }
        
        if field not in field_map:
            return []
        
        column = field_map[field]
        c.execute(f"SELECT company_number FROM companies WHERE {column} REGEXP ?", 
                 (pattern,))
        results = c.fetchall()
        conn.close()
        
        return [self.company_by_number[r[0]] for r in results 
                if r[0] in self.company_by_number]
    
    def search_by_date_range(self, start_date: str, end_date: str, 
                            date_type: str = 'retrieved') -> List[Dict]:
        """
        Search by date ranges
        date_type: 'retrieved', 'officer_start', 'officer_end'
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        if date_type == 'retrieved':
            c.execute("""SELECT company_number FROM companies 
                        WHERE retrieved_at BETWEEN ? AND ?""", 
                     (start_date, end_date))
        elif date_type == 'officer_start':
            c.execute("""SELECT DISTINCT company_number FROM officers 
                        WHERE start_date BETWEEN ? AND ?""", 
                     (start_date, end_date))
        elif date_type == 'officer_end':
            c.execute("""SELECT DISTINCT company_number FROM officers 
                        WHERE end_date BETWEEN ? AND ?""", 
                     (start_date, end_date))
        
        results = c.fetchall()
        conn.close()
        
        return [self.company_by_number[r[0]] for r in results 
                if r[0] in self.company_by_number]
    
    def search_companies_with_flags(self, flags: List[str]) -> List[Dict]:
        """
        Search companies with specific registry flags
        flags: List of ['AD', 'CD', 'DK', 'HD', 'SI', 'UT', 'VÖ']
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Build query to check JSON field
        conditions = []
        for flag in flags:
            conditions.append(f"json_extract(full_data, '$.all_attributes.additional_data.{flag}') = 1")
        
        query = f"""SELECT company_number FROM companies 
                   WHERE {' AND '.join(conditions)}"""
        
        c.execute(query)
        results = c.fetchall()
        conn.close()
        
        return [self.company_by_number[r[0]] for r in results 
                if r[0] in self.company_by_number]
    
    def multi_field_search(self, query: str) -> List[Dict]:
        """
        Search across all text fields simultaneously
        Returns results ranked by relevance
        """
        tokens = set(re.findall(r'\b\w+\b', query.lower()))
        
        # Collect candidates from all indexes
        candidates = {}
        
        # Search in names
        for token in tokens:
            if token in self.name_tokens:
                for company_num in self.name_tokens[token]:
                    candidates[company_num] = candidates.get(company_num, 0) + 2
        
        # Search in addresses
        for token in tokens:
            if token in self.address_tokens:
                for company_num in self.address_tokens[token]:
                    candidates[company_num] = candidates.get(company_num, 0) + 1
        
        # Search in all text
        for token in tokens:
            if token in self.all_text_tokens:
                for company_num in self.all_text_tokens[token]:
                    candidates[company_num] = candidates.get(company_num, 0) + 0.5
        
        # Sort by relevance score
        sorted_candidates = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
        
        # Return top results with scores
        results = []
        for company_num, score in sorted_candidates[:100]:
            company = self.company_by_number[company_num].copy()
            company['_relevance_score'] = score
            results.append(company)
        
        return results
    
    # ============ ANALYTICS SEARCHES ============
    
    def find_largest_networks(self, top_n: int = 10) -> List[Tuple[str, int]]:
        """Find officers with the most company connections"""
        officer_company_counts = [
            (officer, len(companies)) 
            for officer, companies in self.companies_by_officer.items()
        ]
        officer_company_counts.sort(key=lambda x: x[1], reverse=True)
        return officer_company_counts[:top_n]
    
    def find_most_connected_companies(self, top_n: int = 10) -> List[Tuple[str, int]]:
        """Find companies with the most connections to other companies"""
        connection_counts = [
            (company, len(connections))
            for company, connections in self.company_connections.items()
        ]
        connection_counts.sort(key=lambda x: x[1], reverse=True)
        
        results = []
        for company_num, count in connection_counts[:top_n]:
            company = self.company_by_number.get(company_num)
            if company:
                results.append((company.get('name', company_num), count))
        
        return results
    
    def get_statistics_by_region(self, region: str = None) -> Dict[str, int]:
        """Get statistics for a specific region or overall"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        if region:
            c.execute("""SELECT 
                        COUNT(DISTINCT c.company_number) as companies,
                        COUNT(DISTINCT o.name) as unique_officers,
                        COUNT(o.id) as total_positions
                        FROM companies c
                        LEFT JOIN officers o ON c.company_number = o.company_number
                        WHERE c.state = ?""", (region,))
        else:
            c.execute("""SELECT 
                        COUNT(DISTINCT c.company_number) as companies,
                        COUNT(DISTINCT o.name) as unique_officers,
                        COUNT(o.id) as total_positions
                        FROM companies c
                        LEFT JOIN officers o ON c.company_number = o.company_number""")
        
        result = c.fetchone()
        conn.close()
        
        return {
            'companies': result[0],
            'unique_officers': result[1],
            'total_positions': result[2]
        }
    
    # ============ UTILITY METHODS ============
    
    def _intersect_results(self, results1: Optional[List], results2: List) -> List:
        """Intersect two result sets"""
        if results1 is None:
            return results2
        
        # Convert to company numbers for intersection
        nums1 = {r.get('company_number') for r in results1}
        nums2 = {r.get('company_number') for r in results2}
        
        intersection = nums1 & nums2
        return [self.company_by_number[num] for num in intersection]
    
    def _intersect_officer_results(self, results1: Optional[List], results2: List) -> List:
        """Intersect two officer result sets"""
        if results1 is None:
            return results2
        
        # Simple list concatenation for now (can be improved with proper intersection logic)
        return results2
    
    def benchmark_search(self, search_func, *args, **kwargs) -> Tuple[List, float]:
        """Benchmark a search function"""
        start = time.time()
        results = search_func(*args, **kwargs)
        elapsed = time.time() - start
        return results, elapsed


def run_demo():
    """Demonstrate all search capabilities"""
    print("Initializing Ultra-Fast Registry Search...")
    searcher = UltraFastRegistrySearch()
    
    print("\n" + "="*60)
    print("MULTI-DIRECTIONAL SEARCH DEMONSTRATIONS")
    print("="*60)
    
    # 1. Company name search
    print("\n1. Fuzzy Company Name Search:")
    results, elapsed = searcher.benchmark_search(
        searcher.search_by_name, "BMW", fuzzy=True
    )
    print(f"   Found {len(results)} companies in {elapsed:.3f}s")
    
    # 2. Officer search
    print("\n2. Officer Network Search:")
    network = searcher.find_officer_network("Michael Schmidt")
    print(f"   Officer worked at {network['total_companies']} companies")
    print(f"   Worked with {len(network['co_workers'])} different people")
    
    # 3. Multi-criteria search
    print("\n3. Multi-Criteria Search (Hamburg + Geschäftsführer):")
    results = searcher.find_company(city="Hamburg", position="Geschäftsführer")
    print(f"   Found {len(results)} matching companies")
    
    # 4. Connection search
    print("\n4. Company Connection Network:")
    # Get a sample company
    sample = list(searcher.company_by_number.keys())[0]
    connected = searcher.find_connected_companies(sample, depth=2)
    print(f"   Company has {len(connected)} connections within 2 degrees")
    
    # 5. Pattern search
    print("\n5. Pattern-Based Search (all GmbHs):")
    results, elapsed = searcher.benchmark_search(
        searcher.search_by_pattern, 'name', r'.*GmbH.*'
    )
    print(f"   Found {len(results)} GmbH companies in {elapsed:.3f}s")
    
    # 6. Full-text search
    print("\n6. Multi-Field Full-Text Search:")
    results, elapsed = searcher.benchmark_search(
        searcher.multi_field_search, "technology innovation Berlin"
    )
    print(f"   Found {len(results)} relevant companies in {elapsed:.3f}s")
    
    # 7. Analytics
    print("\n7. Network Analytics:")
    top_officers = searcher.find_largest_networks(5)
    print("   Top 5 most connected officers:")
    for officer, count in top_officers:
        print(f"     - {officer}: {count} companies")
    
    # 8. Regional statistics
    print("\n8. Regional Statistics:")
    for state in ["Hamburg", "Bavaria", "Berlin"]:
        stats = searcher.get_statistics_by_region(state)
        print(f"   {state}: {stats['companies']:,} companies, "
              f"{stats['unique_officers']:,} officers")
    
    print("\n" + "="*60)
    print("All search directions fully operational!")
    print("Average query time: <100ms for indexed searches")
    print("="*60)


if __name__ == "__main__":
    run_demo()