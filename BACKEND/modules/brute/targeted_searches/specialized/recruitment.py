#!/usr/bin/env python3
"""
Recruitment/Job Search Operator - Searches for job listings and career opportunities
Supports job:, career:, recruitment:, hire: operators with schema integration
Leverages job platforms and Schema.org JobPosting structured data
"""

import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime
import time
import re

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import event streaming for filtering events
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    logging.warning("Event streaming not available for recruitment search")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Recruitment search engines
RECRUITMENT_ENGINES = [
    'GO',  # Google - with schema search and Google Jobs
    'BI',  # Bing
    'BR',  # Brave
    'DD',  # DuckDuckGo
    'YA',  # Yandex
]

# Major job platforms
JOB_PLATFORMS = {
    'linkedin': 'site:linkedin.com/jobs',
    'indeed': 'site:indeed.com',
    'glassdoor': 'site:glassdoor.com',
    'monster': 'site:monster.com',
    'ziprecruiter': 'site:ziprecruiter.com',
    'careerbuilder': 'site:careerbuilder.com',
    'simplyhired': 'site:simplyhired.com',
    'dice': 'site:dice.com',
    'angellist': 'site:angel.co OR site:wellfound.com',
    'stackoverflow': 'site:stackoverflow.com/jobs',
    'remoteok': 'site:remoteok.io',
    'weworkremotely': 'site:weworkremotely.com',
    'flexjobs': 'site:flexjobs.com',
    'upwork': 'site:upwork.com',
    'freelancer': 'site:freelancer.com',
    'toptal': 'site:toptal.com',
    'hired': 'site:hired.com',
    'greenhouse': 'site:boards.greenhouse.io',
    'lever': 'site:jobs.lever.co',
    'workday': 'site:myworkdayjobs.com',
}

# LinkedIn-specific job search URLs
LINKEDIN_JOB_URLS = {
    'basic': 'https://www.linkedin.com/jobs/search/?keywords={query}',
    'remote': 'https://www.linkedin.com/jobs/search/?keywords={query}&f_WT=2',
    'location': 'https://www.linkedin.com/jobs/search/?keywords={query}&location={location}',
    'experience': {
        'entry': 'https://www.linkedin.com/jobs/search/?keywords={query}&f_E=2',
        'associate': 'https://www.linkedin.com/jobs/search/?keywords={query}&f_E=3',
        'mid-senior': 'https://www.linkedin.com/jobs/search/?keywords={query}&f_E=4',
        'director': 'https://www.linkedin.com/jobs/search/?keywords={query}&f_E=5',
        'executive': 'https://www.linkedin.com/jobs/search/?keywords={query}&f_E=6',
    },
    'job_type': {
        'full-time': 'https://www.linkedin.com/jobs/search/?keywords={query}&f_JT=F',
        'part-time': 'https://www.linkedin.com/jobs/search/?keywords={query}&f_JT=P',
        'contract': 'https://www.linkedin.com/jobs/search/?keywords={query}&f_JT=C',
        'internship': 'https://www.linkedin.com/jobs/search/?keywords={query}&f_JT=I',
    },
    'posted': {
        '24h': 'https://www.linkedin.com/jobs/search/?keywords={query}&f_TPR=r86400',
        'week': 'https://www.linkedin.com/jobs/search/?keywords={query}&f_TPR=r604800',
        'month': 'https://www.linkedin.com/jobs/search/?keywords={query}&f_TPR=r2592000',
    }
}

# Schema.org structured data queries for jobs
JOB_SCHEMAS = [
    'more:pagemap:jobposting',
    'more:pagemap:jobposting-title',
    'more:pagemap:jobposting-hiringorganization',
    'more:pagemap:jobposting-joblocation',
    'more:pagemap:jobposting-dateposted',
    'more:pagemap:jobposting-employmenttype',
    'more:pagemap:jobposting-experiencerequirements',
    'more:pagemap:jobposting-qualifications',
    'more:pagemap:jobposting-responsibilities',
    'more:pagemap:jobposting-skills',
    'more:pagemap:jobposting-salarycurrency',
    'more:pagemap:jobposting-basesalary',
    'more:pagemap:hiringorganization',
]

class RecruitmentSearch:
    """
    Recruitment/Job search operator implementation.
    Routes searches to job platforms and uses schema-enhanced queries.
    """
    
    def __init__(self, event_emitter=None):
        """Initialize recruitment search with optional event streaming."""
        self.event_emitter = event_emitter
        self.available_engines = self._check_available_engines()
        
        if STREAMING_AVAILABLE and event_emitter:
            self.streamer = SearchTypeEventEmitter(event_emitter)
        else:
            self.streamer = None
    
    def _check_available_engines(self) -> List[str]:
        """Check which recruitment-supporting engines are available in the system."""
        available = []
        
        try:
            from brute.targeted_searches.brute import ENGINE_CONFIG
            
            for engine_code in RECRUITMENT_ENGINES:
                if engine_code in ENGINE_CONFIG:
                    available.append(engine_code)
                    logger.info(f"Recruitment engine {engine_code} available")
        except ImportError:
            logger.error("Could not import ENGINE_CONFIG from brute.py")
            available = ['GO', 'BI', 'BR']
        
        if not available:
            available = ['GO', 'BI', 'BR']
        
        logger.info(f"Available recruitment engines: {available}")
        return available
    
    def _extract_job_filters(self, query: str) -> Tuple[str, Optional[Dict]]:
        """
        Extract job-related filters from query.
        
        Patterns:
        - remote or remote-only
        - location:NYC
        - level:senior, level:junior, level:entry
        - type:fulltime, type:contract, type:parttime
        - salary>100k
        
        Returns:
            Tuple of (cleaned_query, filters)
        """
        filters = {}
        cleaned_query = query
        
        # Remote work pattern
        if any(word in query.lower() for word in ['remote', 'remote-only', 'work from home', 'wfh']):
            filters['remote'] = True
            cleaned_query = re.sub(r'\b(remote|remote-only|work from home|wfh)\b', '', 
                                  cleaned_query, flags=re.IGNORECASE)
        
        # Location pattern
        location_pattern = r'\blocation\s*:\s*([^\s]+)'
        match = re.search(location_pattern, query, re.IGNORECASE)
        if match:
            filters['location'] = match.group(1)
            cleaned_query = re.sub(location_pattern, '', cleaned_query, flags=re.IGNORECASE)
        
        # Level pattern
        level_pattern = r'\blevel\s*:\s*(entry|junior|mid|senior|lead|principal|staff)'
        match = re.search(level_pattern, query, re.IGNORECASE)
        if match:
            filters['level'] = match.group(1).lower()
            cleaned_query = re.sub(level_pattern, '', cleaned_query, flags=re.IGNORECASE)
        
        # Employment type pattern
        type_pattern = r'\btype\s*:\s*(fulltime|full-time|parttime|part-time|contract|freelance|internship)'
        match = re.search(type_pattern, query, re.IGNORECASE)
        if match:
            filters['employment_type'] = match.group(1).lower().replace('-', '')
            cleaned_query = re.sub(type_pattern, '', cleaned_query, flags=re.IGNORECASE)
        
        # Salary pattern
        salary_pattern = r'\bsalary\s*[>]\s*(\d+)k?'
        match = re.search(salary_pattern, query, re.IGNORECASE)
        if match:
            salary = int(match.group(1))
            if query.lower()[match.end()-1] == 'k':
                salary *= 1000
            filters['min_salary'] = salary
            cleaned_query = re.sub(salary_pattern, '', cleaned_query, flags=re.IGNORECASE)
        
        # Common level keywords
        for level in ['entry level', 'junior', 'senior', 'lead', 'principal', 'staff']:
            if level in query.lower() and 'level' not in filters:
                filters['level'] = level.replace(' ', '_')
                cleaned_query = re.sub(rf'\b{level}\b', '', cleaned_query, flags=re.IGNORECASE)
        
        return cleaned_query.strip(), filters if filters else None
    
    def _build_linkedin_job_urls(self, query: str, filters: Optional[Dict] = None) -> List[Dict]:
        """Build LinkedIn-specific job search URLs."""
        from urllib.parse import quote
        linkedin_results = []
        encoded_query = quote(query)
        
        # Basic LinkedIn job search
        linkedin_results.append({
            "title": f"LinkedIn Jobs: {query}",
            "url": LINKEDIN_JOB_URLS['basic'].format(query=encoded_query),
            "search_engine": "linkedin",
            "engine_badge": "LI",
            "description": "Search LinkedIn job postings"
        })
        
        # Apply filters if present
        if filters:
            # Remote jobs
            if 'remote' in filters:
                linkedin_results.append({
                    "title": f"LinkedIn Remote: {query}",
                    "url": LINKEDIN_JOB_URLS['remote'].format(query=encoded_query),
                    "search_engine": "linkedin",
                    "engine_badge": "LI",
                    "description": "Remote job opportunities"
                })
            
            # Location-specific jobs
            if 'location' in filters:
                location_encoded = quote(filters['location'])
                linkedin_results.append({
                    "title": f"LinkedIn Jobs in {filters['location']}: {query}",
                    "url": LINKEDIN_JOB_URLS['location'].format(query=encoded_query, location=location_encoded),
                    "search_engine": "linkedin",
                    "engine_badge": "LI",
                    "description": f"Jobs in {filters['location']}"
                })
            
            # Experience level
            if 'level' in filters:
                level_map = {
                    'entry': 'entry',
                    'entry_level': 'entry',
                    'junior': 'associate',
                    'mid': 'mid-senior',
                    'senior': 'mid-senior',
                    'lead': 'director',
                    'principal': 'director',
                    'staff': 'director',
                    'executive': 'executive'
                }
                mapped_level = level_map.get(filters['level'], 'mid-senior')
                if mapped_level in LINKEDIN_JOB_URLS['experience']:
                    linkedin_results.append({
                        "title": f"LinkedIn {filters['level'].title()}: {query}",
                        "url": LINKEDIN_JOB_URLS['experience'][mapped_level].format(query=encoded_query),
                        "search_engine": "linkedin",
                        "engine_badge": "LI",
                        "description": f"{filters['level'].title()} level positions"
                    })
            
            # Employment type
            if 'employment_type' in filters:
                type_map = {
                    'fulltime': 'full-time',
                    'parttime': 'part-time',
                    'contract': 'contract',
                    'freelance': 'contract',
                    'internship': 'internship'
                }
                mapped_type = type_map.get(filters['employment_type'], 'full-time')
                if mapped_type in LINKEDIN_JOB_URLS['job_type']:
                    linkedin_results.append({
                        "title": f"LinkedIn {mapped_type.title()}: {query}",
                        "url": LINKEDIN_JOB_URLS['job_type'][mapped_type].format(query=encoded_query),
                        "search_engine": "linkedin",
                        "engine_badge": "LI",
                        "description": f"{mapped_type.title()} positions"
                    })
        
        # Recently posted jobs (last 24 hours)
        linkedin_results.append({
            "title": f"LinkedIn New Today: {query}",
            "url": LINKEDIN_JOB_URLS['posted']['24h'].format(query=encoded_query),
            "search_engine": "linkedin",
            "engine_badge": "LI",
            "description": "Jobs posted in last 24 hours"
        })
        
        return linkedin_results
    
    def _build_job_queries(self, query: str, include_platforms: bool = True, 
                          include_schemas: bool = True, filters: Optional[Dict] = None) -> List[str]:
        """Build comprehensive job search queries."""
        queries = []
        
        # Base queries
        queries.append(f'"{query}" jobs')
        queries.append(f'"{query}" careers')
        queries.append(f'"{query}" hiring')
        queries.append(f'"{query}" position')
        queries.append(f'"{query}" vacancy')
        queries.append(f'"{query}" opening')
        queries.append(f'"{query}" recruitment')
        
        # Add filter-specific queries
        if filters:
            base = query
            if 'remote' in filters:
                queries.append(f'{query} remote')
                queries.append(f'remote {query}')
            if 'level' in filters:
                level = filters['level'].replace('_', ' ')
                queries.append(f'{level} {query}')
            if 'location' in filters:
                queries.append(f'{query} {filters["location"]}')
            if 'employment_type' in filters:
                queries.append(f'{query} {filters["employment_type"]}')
        
        # Platform-specific searches
        if include_platforms:
            top_platforms = ['indeed', 'glassdoor', 'ziprecruiter', 
                           'angellist', 'dice', 'remoteok', 'greenhouse']
            for platform_name in top_platforms:
                if platform_name in JOB_PLATFORMS:
                    platform_filter = JOB_PLATFORMS[platform_name]
                    platform_query = f'{platform_filter} {query}'
                    if filters and 'remote' in filters:
                        platform_query += ' remote'
                    queries.append(platform_query)
        
        # Schema-enhanced searches (Google API only)
        if include_schemas and 'GO' in self.available_engines:
            for schema in JOB_SCHEMAS:
                queries.append(f'{schema} {query}')
            
            # Specific job schema combinations
            queries.extend([
                f'more:pagemap:jobposting-title:"{query}"',
                f'more:pagemap:jobposting {query}',
                f'more:pagemap:hiringorganization {query}',
            ])
            
            if filters:
                if 'location' in filters:
                    queries.append(f'more:pagemap:jobposting-joblocation:"{filters["location"]}" {query}')
                if 'employment_type' in filters:
                    queries.append(f'more:pagemap:jobposting-employmenttype:{filters["employment_type"]} {query}')
        
        # Job-specific patterns
        queries.extend([
            f'"{query}" apply now',
            f'"{query}" job description',
            f'"{query}" requirements',
            f'"{query}" qualifications',
            f'"{query}" responsibilities',
            f'we are hiring {query}',
            f'looking for {query}',
            f'join our team {query}',
        ])
        
        return queries
    
    async def search(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """Execute recruitment search across available engines."""
        # Extract job filters and clean query
        cleaned_query, filters = self._extract_job_filters(query)
        
        logger.info(f"Starting recruitment search for: '{cleaned_query}'")
        if filters:
            logger.info(f"Filters: {filters}")
        
        if self.streamer:
            await self.streamer.emit_search_started('recruitment', cleaned_query, self.available_engines)
        
        # Build comprehensive job queries
        job_queries = self._build_job_queries(cleaned_query, filters=filters)
        
        # Get LinkedIn-specific job URLs
        linkedin_job_urls = self._build_linkedin_job_urls(cleaned_query, filters)
        
        try:
            from brute.targeted_searches.brute import BruteSearchEngine
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"results/recruitment_{timestamp}.json"
            
            all_results = []
            
            # Add LinkedIn job URLs to results first (direct links)
            all_results.extend(linkedin_job_urls)
            
            for job_query in job_queries[:12]:
                logger.info(f"Searching with query: '{job_query}'")
                
                searcher = BruteSearchEngine(
                    keyword=job_query,
                    output_file=output_file,
                    engines=self.available_engines,
                    max_workers=min(len(self.available_engines), 5),
                    event_emitter=self.event_emitter,
                    return_results=True
                )
                
                searcher.search()
                
                if hasattr(searcher, 'final_results'):
                    results = searcher.final_results
                    for result in results:
                        result['search_type'] = 'recruitment'
                        result['job_query'] = cleaned_query
                        result['query_variant'] = job_query
                        if filters:
                            result['filters'] = filters
                    all_results.extend(results)
            
            # Deduplicate results
            seen_urls = set()
            unique_results = []
            for result in all_results:
                url = result.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_results.append(result)
            
            # Score and sort results
            scored_results = self._score_job_results(unique_results, cleaned_query, filters)
            
            if self.streamer:
                await self.streamer.emit_search_completed('recruitment', len(scored_results))
            
            return scored_results[:max_results]
            
        except Exception as e:
            logger.error(f"Recruitment search failed: {e}")
            return []
    
    def _score_job_results(self, results: List[Dict], query: str,
                          filters: Optional[Dict] = None) -> List[Dict]:
        """Score and sort job results by relevance."""
        query_lower = query.lower()
        
        def score_result(result):
            score = 0
            url = result.get('url', '').lower()
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()
            
            # Check if from known job platform (highest priority)
            major_platforms = ['linkedin.com/jobs', 'indeed.com', 'glassdoor.com',
                             'ziprecruiter.com', 'angel.co', 'wellfound.com', 'dice.com',
                             'greenhouse.io', 'lever.co', 'myworkdayjobs.com']
            for platform in major_platforms:
                if platform in url:
                    score += 60
                    break
            
            # Check for job schema markup
            if 'query_variant' in result:
                variant = result['query_variant']
                if 'more:pagemap:jobposting' in variant:
                    score += 50
            
            # Job keywords in title
            job_keywords = ['hiring', 'job', 'position', 'opening', 'vacancy', 
                          'career', 'opportunity', 'role', 'seeking', 'wanted']
            for keyword in job_keywords:
                if keyword in title:
                    score += 25
                    break
            
            # Query appears in title
            if query_lower in title:
                score += 30
            
            # Date posted indicators (fresh jobs are better)
            date_pattern = r'\b(posted|updated|added)\s*(today|yesterday|\d+\s*days?\s*ago)'
            if re.search(date_pattern, snippet, re.IGNORECASE):
                score += 20
            
            # Application keywords
            apply_keywords = ['apply now', 'apply today', 'submit application', 
                            'send resume', 'send cv', 'apply online']
            for keyword in apply_keywords:
                if keyword in snippet.lower():
                    score += 15
                    break
            
            # Salary information
            if '$' in snippet or 'salary' in snippet.lower() or 'compensation' in snippet.lower():
                score += 12
            
            # Remote work indicators
            if filters and 'remote' in filters:
                if any(word in snippet.lower() for word in ['remote', 'work from home', 'wfh', 'distributed']):
                    score += 18
            
            # Level matching
            if filters and 'level' in filters:
                level = filters['level'].replace('_', ' ')
                if level in snippet.lower():
                    score += 15
            
            # Requirements/qualifications
            if any(word in snippet.lower() for word in ['requirements', 'qualifications', 
                                                         'experience', 'skills', 'degree']):
                score += 8
            
            return score
        
        # Score all results
        for result in results:
            result['job_score'] = score_result(result)
        
        # Sort by score
        results.sort(key=lambda x: x.get('job_score', 0), reverse=True)
        
        return results
    
    def search_sync(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """Synchronous wrapper for search method."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.search(query, max_results))
        finally:
            loop.close()

def detect_recruitment_query(query: str) -> bool:
    """Detect if a query should be routed to recruitment search."""
    query_lower = query.lower()
    
    recruitment_patterns = [
        'job:',
        'jobs:',
        'career:',
        'careers:',
        'recruitment:',
        'hire:',
        'hiring:',
        'position:',
        'vacancy:',
        'opening:',
    ]
    
    for pattern in recruitment_patterns:
        if pattern in query_lower:
            return True
    
    return False

def extract_recruitment_query(query: str) -> str:
    """Extract the actual search query from a recruitment search query."""
    query = query.strip()
    
    prefixes = [
        'job:', 'jobs:', 'career:', 'careers:', 'recruitment:', 'hire:', 
        'hiring:', 'position:', 'vacancy:', 'opening:',
        'Job:', 'Jobs:', 'Career:', 'Careers:', 'Recruitment:', 'Hire:',
        'Hiring:', 'Position:', 'Vacancy:', 'Opening:'
    ]
    
    for prefix in prefixes:
        if query.startswith(prefix):
            query = query[len(prefix):].strip()
            if query.startswith('"') and query.endswith('"'):
                query = query[1:-1]
            elif query.startswith("'") and query.endswith("'"):
                query = query[1:-1]
            return query
    
    return query.strip()

# Main entry point
async def run_recruitment_search(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Main entry point for recruitment search."""
    clean_query = extract_recruitment_query(query)
    searcher = RecruitmentSearch(event_emitter)
    return await searcher.search(clean_query)

def run_recruitment_search_sync(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for recruitment search."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_recruitment_search(query, event_emitter))
    finally:
        loop.close()


def main():
    """Main entry point for Job/career search - compatible with SearchRouter"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Job/career search')
    parser.add_argument('-q', '--query', required=True, help='Search query')
    args = parser.parse_args()
    
    query = args.query
    
    # Extract clean query by removing operator prefix
    if ':' in query:
        clean_query = query.split(':', 1)[1].strip()
    else:
        clean_query = query
    
    print(f"\n🔍 Job/career search: {clean_query}")
    
    # Try to use existing search function if available
    try:
        if 'run_recruitment_search_sync' in globals():
            results = globals()['run_recruitment_search_sync'](clean_query)
        elif 'search' in globals():
            results = search(clean_query)
        else:
            print("Note: This search type needs full implementation")
            results = []
    except Exception as e:
        print(f"Search implementation in progress: {e}")
        results = []
    
    if results:
        print(f"\nFound {len(results)} results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No Title')}")
            print(f"   URL: {result.get('url')}")
            if result.get('snippet'):
                print(f"   {result['snippet'][:200]}...")
    else:
        print("\nNo results found (implementation may be pending).")
    
    return results

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        test_query = ' '.join(sys.argv[1:])
    else:
        test_query = "job:python developer remote"
    
    print(f"Testing recruitment search with: {test_query}")
    
    if detect_recruitment_query(test_query):
        print("Recruitment query detected!")
        clean_query = extract_recruitment_query(test_query)
        print(f"Extracted query: '{clean_query}'")
        
        results = run_recruitment_search_sync(test_query)
        
        print(f"\nFound {len(results)} job results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            print(f"   Score: {result.get('job_score', 0)}")
            if 'filters' in result:
                print(f"   Filters: {result['filters']}")
    else:
        print("Not a recruitment query")