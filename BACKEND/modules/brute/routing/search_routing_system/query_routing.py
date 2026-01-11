#!/usr/bin/env python3
"""
Query Routing and Analysis for Search Integration

This module handles query analysis, operator detection, and routing decisions
for the unified search system. It determines which search systems to use
and how to optimize queries for different search backends.

Key Components:
- Operator detection (date, filetype, language, proximity, etc.)
- Special scenario detection for investigative queries
- Dataset prioritization for HuggingFace searches
- Query optimization and transformation

Originally extracted from search_interpreter.py to improve modularity.
"""

import re
import logging
from typing import Dict, List, Tuple, Any, Optional

# Engine matrix selection
try:
    from ..matrix_registry import get_engines  # type: ignore
except Exception:
    # Fallback import when executed directly
    from pathlib import Path as _Path
    import sys as _sys
    _router_root = _Path(__file__).resolve().parents[1]
    _sys.path.insert(0, str(_router_root))
    from matrix_registry import get_engines  # type: ignore

# Optional capabilities filter
try:
    from ..capabilities_registry import filter_engine_codes  # type: ignore
except Exception:
    # Fallback import when executed directly
    from pathlib import Path as _Path2
    import sys as _sys2
    _router_root2 = _Path2(__file__).resolve().parents[1]
    _sys2.path.insert(0, str(_router_root2))
    try:
        from capabilities_registry import filter_engine_codes  # type: ignore
    except Exception:
        def filter_engine_codes(engine_codes, operator_type, level, region=None, modality=None):
            return engine_codes

# Import metadata for analysis (optional)
try:
    from .dataset_metadata import DATASET_METADATA, SPECIAL_SCENARIOS
except Exception:
    DATASET_METADATA = {}
    SPECIAL_SCENARIOS = {}

logger = logging.getLogger(__name__)

# Import AI brain if available
try:
    from TOOLS.openai_chatgpt import chat_sync, analyze, GPT5_MODELS
    BRAIN_AVAILABLE = True
except ImportError:
    BRAIN_AVAILABLE = False

# Import HuggingFace functions if available
try:
    from huggingface import get_prioritized_datasets, DEFAULT_DATASETS
    HUGGINGFACE_AVAILABLE = True
except ImportError:
    HUGGINGFACE_AVAILABLE = False


class QueryRouter:
    """Handles query analysis and routing decisions for the search system"""
    
    def __init__(self):
        self.brain = None if BRAIN_AVAILABLE else None
    
    def detect_operator_type(self, query: str) -> Dict[str, Any]:
        """
        Detect operator type and extract parameters from query.
        Returns dict with operator_type, parameters, and cleaned_query.
        """
        
        # Date search operators: yyyy!, yyyy-yyyy!, <- yyyy!, yyyy ->!
        date_patterns = [
            (r'^(\d{4})\s*!\s*(.+)$', 'date_single'),  # 2024! query
            (r'^(\d{4})\s*-\s*(\d{4})\s*!\s*(.+)$', 'date_range'),  # 2020-2023! query
            (r'^<-\s*(\d{4})\s*!\s*(.+)$', 'date_before'),  # <- 2022! query
            (r'^(\d{4})\s*->\s*!\s*(.+)$', 'date_after'),  # 2023 ->! query
        ]
        
        for pattern, date_type in date_patterns:
            match = re.match(pattern, query.strip())
            if match:
                if date_type == 'date_single':
                    return {
                        'operator_type': 'date',
                        'date_type': 'single',
                        'year': match.group(1),
                        'cleaned_query': match.group(2).strip(),
                        'original_query': query
                    }
                elif date_type == 'date_range':
                    return {
                        'operator_type': 'date',
                        'date_type': 'range',
                        'start_year': match.group(1),
                        'end_year': match.group(2),
                        'cleaned_query': match.group(3).strip(),
                        'original_query': query
                    }
                elif date_type == 'date_before':
                    return {
                        'operator_type': 'date',
                        'date_type': 'before',
                        'year': match.group(1),
                        'cleaned_query': match.group(2).strip(),
                        'original_query': query
                    }
                elif date_type == 'date_after':
                    return {
                        'operator_type': 'date',
                        'date_type': 'after',
                        'year': match.group(1),
                        'cleaned_query': match.group(2).strip(),
                        'original_query': query
                    }
        
        # Filetype operators: pdf!, document!, spreadsheet!, etc. OR pdf:, document:, etc.
        filetype_patterns = [
            'pdf', 'document', 'spreadsheet', 'presentation', 'image', 
            'video', 'audio', 'archive', 'code', 'database', 'config'
        ]
        for filetype in filetype_patterns:
            # Match filetype! or filetype: at word boundaries or at start of query
            pattern = rf'(?:^|\s)({re.escape(filetype)})(?:!|:)\s*(.*?)$'
            match = re.search(pattern, query.strip(), re.IGNORECASE)
            if match:
                # Remove the filetype!/filetype: part from query
                cleaned_query = re.sub(rf'\b{re.escape(filetype)}(?:!|:)\s*', '', query.strip(), flags=re.IGNORECASE).strip()
                return {
                    'operator_type': 'filetype',
                    'filetype': filetype,
                    'cleaned_query': cleaned_query,
                    'original_query': query
                }
        
        # Language operators: lang:XX or :XX:
        lang_match = re.match(r'^(?:lang:(\w{2})|:(\w{2}):)\s*(.+)$', query.strip())
        if lang_match:
            lang_code = lang_match.group(1) or lang_match.group(2)
            return {
                'operator_type': 'language',
                'language_code': lang_code,
                'cleaned_query': lang_match.group(3).strip(),
                'original_query': query
            }

        # Media operators: video:, image:
        vmatch = re.match(r'^video:\s*(.+)$', query.strip(), flags=re.IGNORECASE)
        if vmatch:
            return {
                'operator_type': 'video',
                'cleaned_query': vmatch.group(1).strip(),
                'original_query': query
            }
        imatch = re.match(r'^image:\s*(.+)$', query.strip(), flags=re.IGNORECASE)
        if imatch:
            return {
                'operator_type': 'image_search',
                'cleaned_query': imatch.group(1).strip(),
                'original_query': query
            }

        # Explicit news: and academic: operators
        news_match = re.match(r'^news:\s*(.+)$', query.strip(), flags=re.IGNORECASE)
        if news_match:
            return {
                'operator_type': 'news',
                'cleaned_query': news_match.group(1).strip(),
                'original_query': query
            }
        # Academic with : suffix or as keyword
        acad_match = re.match(r'^(academic:|scholar:)\s*(.+)$', query.strip(), flags=re.IGNORECASE)
        if acad_match:
            return {
                'operator_type': 'academic',
                'cleaned_query': acad_match.group(2).strip(),
                'original_query': query
            }
        # Check for academic/scholar as keywords
        if re.search(r'\b(academic|scholar)\b', query.strip(), flags=re.IGNORECASE):
            return {
                'operator_type': 'academic',
                'cleaned_query': query.strip(),
                'original_query': query
            }

        # Book and author operators
        book_match = re.match(r'^(book:|books:)\s*(.+)$', query.strip(), flags=re.IGNORECASE)
        if book_match:
            return {
                'operator_type': 'book',
                'cleaned_query': book_match.group(2).strip(),
                'original_query': query
            }
        author_match = re.match(r'^(author:)\s*(.+)$', query.strip(), flags=re.IGNORECASE)
        if author_match:
            return {
                'operator_type': 'author',
                'author': author_match.group(2).strip(),
                'cleaned_query': author_match.group(2).strip(),
                'original_query': query
            }

        # Social operator: social:query (generic social media search)
        social_match = re.match(r'^(social:)\s*(.+)$', query.strip(), flags=re.IGNORECASE)
        if social_match:
            return {
                'operator_type': 'social',
                'cleaned_query': social_match.group(2).strip(),
                'original_query': query
            }

        # YouTube comments operator: comments:<video_url_or_id> or ytc:<...>
        comments_match = re.match(r'^(?:comments:|ytc:)\s*(.+)$', query.strip(), flags=re.IGNORECASE)
        if comments_match:
            return {
                'operator_type': 'comments',
                'cleaned_query': comments_match.group(1).strip(),
                'original_query': query
            }

        # Username / handle operators: @handle, username:handle, channel:handle
        handle_match = re.match(r'^@([A-Za-z0-9._-]{2,})\s*$', query.strip())
        if handle_match:
            return {
                'operator_type': 'username',
                'handle': handle_match.group(1),
                'platform': 'any',
                'cleaned_query': handle_match.group(1),
                'original_query': query
            }
        # Allow optional '@' in username/channel forms
        uname_match = re.match(r'^(username:|channel:)\s*@?([A-Za-z0-9._-]{2,})\s*(.*)$', query.strip(), flags=re.IGNORECASE)
        if uname_match:
            return {
                'operator_type': 'username',
                'handle': uname_match.group(2),
                'platform': 'any',
                'cleaned_query': (uname_match.group(2) + ' ' + uname_match.group(3)).strip(),
                'original_query': query
            }

        # Person operator (p:, person:, people:)
        person_match = re.match(r'^(?:p:|person:|people:)\s*(.+)$', query.strip(), flags=re.IGNORECASE)
        if person_match:
            return {
                'operator_type': 'person',
                'name': person_match.group(1).strip(),
                'cleaned_query': person_match.group(1).strip(),
                'original_query': query
            }

        # Corporate operator (c:, corp:, corporate:, company:, org:, organisation:, organization:)
        company_match = re.match(r'^(?:c:|corp:|corporate:|company:|org:|organisation:|organization:)\s*(.+)$', query.strip(), flags=re.IGNORECASE)
        if company_match:
            return {
                'operator_type': 'corporate',
                'name': company_match.group(1).strip(),
                'cleaned_query': company_match.group(1).strip(),
                'original_query': query
            }
        
        # Proximity operators
        # Supported forms (engine-agnostic):
        # - term1 N! term2   (our compact form)
        # - term1 ~N term2   (tilde form)
        # - term1 NEAR:N term2 / NEAR N
        # - term1 AROUND(N) term2
        prox_regexes = [
            r'(.+?)\s+(\d+)!+\s+(.+)',
            r'(.+?)\s+~\s*(\d+)\s+(.+)',
            r'(.+?)\s+NEAR[:\s]*?(\d+)\s+(.+)',
            r'(.+?)\s+AROUND\(\s*(\d+)\s*\)\s+(.+)',
        ]
        for rx in prox_regexes:
            m = re.search(rx, query.strip(), flags=re.IGNORECASE)
            if m:
                return {
                    'operator_type': 'proximity',
                    'left': m.group(1).strip(),
                    'distance': int(m.group(2)),
                    'right': m.group(3).strip(),
                    'original_query': query
                }
        
        # NOT operator: NOT or -term
        if ' NOT ' in query:
            parts = query.split(' NOT ', 1)
            return {
                'operator_type': 'not',
                'positive_terms': parts[0].strip(),
                'negative_terms': parts[1].strip(),
                'original_query': query
            }
        
        # Check for -term exclusions
        if re.search(r'\s+-\S+', query):
            negative_terms = []
            positive_query = query
            for match in re.finditer(r'\s+-(\S+)', query):
                negative_terms.append(match.group(1))
                positive_query = positive_query.replace(match.group(0), '')
            
            if negative_terms:
                return {
                    'operator_type': 'not',
                    'positive_terms': positive_query.strip(),
                    'negative_terms': ' '.join(negative_terms),
                    'original_query': query
                }
        
        # OR operator: / or OR
        if ' / ' in query or ' OR ' in query:
            delimiter = ' / ' if ' / ' in query else ' OR '
            terms = [t.strip() for t in query.split(delimiter)]
            return {
                'operator_type': 'or',
                'terms': terms,
                'original_query': query
            }
        
        # Site operator: site:domain
        site_match = re.match(r'^site:(\S+)\s*(.*)$', query.strip())
        if site_match:
            return {
                'operator_type': 'site',
                'domain': site_match.group(1),
                'cleaned_query': site_match.group(2).strip(),
                'original_query': query
            }
        
        # InURL operator: inurl:keyword
        inurl_match = re.match(r'^inurl:(\S+)\s*(.*)', query)
        if inurl_match:
            return {
                'operator_type': 'inurl',
                'url_keyword': inurl_match.group(1),
                'cleaned_query': inurl_match.group(2).strip(),
                'original_query': query
            }
        
        # News detection (keyword-based)
        news_keywords = ['latest', 'breaking', 'news', 'today', 'yesterday', 'update']
        query_lower = query.lower()
        if any(keyword in query_lower for keyword in news_keywords):
            return {
                'operator_type': 'news',
                'cleaned_query': query,
                'original_query': query
            }
        
        # Title operators: intitle:, allintitle:
        title_match = re.match(r'^(intitle:|allintitle:)(.+)$', query.strip())
        if title_match:
            return {
                'operator_type': 'title',
                'title_type': 'all' if title_match.group(1) == 'allintitle:' else 'any',
                'title_terms': title_match.group(2).strip(),
                'original_query': query
            }
        
        # Location operators: near:, location:
        location_match = re.match(r'^(near:|location:)(.+)$', query.strip())
        if location_match:
            return {
                'operator_type': 'location',
                'location': location_match.group(2).strip(),
                'original_query': query
            }
        
        # Age estimation operator: age!:domain or age!:url
        age_match = re.match(r'^age!:(.+)$', query.strip())
        if age_match:
            target = age_match.group(1).strip()
            # Determine if it's a URL or domain
            is_url = target.startswith(('http://', 'https://')) or '/' in target
            return {
                'operator_type': 'age',
                'target': target,
                'is_url': is_url,
                'original_query': query
            }
        
        # Default: no operator detected
        return {
            'operator_type': 'none',
            'cleaned_query': query,
            'original_query': query
        }
    
    def detect_special_scenarios(self, query: str) -> List[Dict[str, Any]]:
        """Detect special investigative scenarios in the query"""
        query_lower = query.lower()
        detected_scenarios = []
        
        for scenario_name, scenario_data in SPECIAL_SCENARIOS.items():
            for keyword in scenario_data["keywords"]:
                if keyword in query_lower:
                    detected_scenarios.append({
                        "name": scenario_name,
                        "description": scenario_data["description"],
                        "datasets": scenario_data["datasets"],
                        "matched_keyword": keyword
                    })
                    break  # Only match once per scenario
        
        return detected_scenarios
    
    async def get_enhanced_dataset_priority(self, query: str, special_scenarios: List[Dict]) -> List[Tuple[str, str, str, str, bool]]:
        """Get dataset priority with comprehensive analysis and special scenario enhancement"""
        if not HUGGINGFACE_AVAILABLE:
            return []
        
        # Analyze query to determine optimal datasets using AI and metadata
        query_analysis = await self._analyze_query_for_datasets(query, special_scenarios)
        
        # Get standard HuggingFace prioritization as baseline
        try:
            standard_datasets = await get_prioritized_datasets(query)
        except Exception:
            standard_datasets = []
        
        # Build enhanced dataset list with intelligent prioritization
        enhanced_datasets = []
        used_datasets = set()
        
        # 1. First priority: Special scenario datasets (if detected)
        if special_scenarios:
            for scenario in special_scenarios:
                for dataset_name in scenario['datasets']:
                    if dataset_name not in used_datasets:
                        if dataset_name in DEFAULT_DATASETS:
                            cfg, split, col, scripted = DEFAULT_DATASETS[dataset_name]
                            enhanced_datasets.append((dataset_name, cfg, split, col, scripted))
                        else:
                            enhanced_datasets.append((dataset_name, "default", "train", "text", False))
                        used_datasets.add(dataset_name)
        
        # 2. Second priority: High-priority datasets based on query analysis
        high_priority_datasets = query_analysis.get('high_priority_datasets', [])
        for dataset_name in high_priority_datasets:
            if dataset_name not in used_datasets and dataset_name in DATASET_METADATA:
                if dataset_name in DEFAULT_DATASETS:
                    cfg, split, col, scripted = DEFAULT_DATASETS[dataset_name]
                    enhanced_datasets.append((dataset_name, cfg, split, col, scripted))
                else:
                    enhanced_datasets.append((dataset_name, "default", "train", "text", False))
                used_datasets.add(dataset_name)
        
        # 3. Third priority: Standard datasets (avoiding duplicates)
        for dataset_tuple in standard_datasets:
            if dataset_tuple[0] not in used_datasets:
                enhanced_datasets.append(dataset_tuple)
                used_datasets.add(dataset_tuple[0])
        
        # 4. Fourth priority: Remaining relevant datasets from metadata
        remaining_datasets = query_analysis.get('relevant_datasets', [])
        for dataset_name in remaining_datasets:
            if dataset_name not in used_datasets and dataset_name in DATASET_METADATA:
                if dataset_name in DEFAULT_DATASETS:
                    cfg, split, col, scripted = DEFAULT_DATASETS[dataset_name]
                    enhanced_datasets.append((dataset_name, cfg, split, col, scripted))
                else:
                    enhanced_datasets.append((dataset_name, "default", "train", "text", False))
                used_datasets.add(dataset_name)
        
        return enhanced_datasets
    
    async def _analyze_query_for_datasets(self, query: str, special_scenarios: List[Dict]) -> Dict[str, Any]:
        """Analyze query to determine optimal datasets using comprehensive metadata"""
        if not self.brain:
            return self._fallback_dataset_analysis(query, special_scenarios)
        
        # Create detailed dataset analysis prompt
        dataset_info = ""
        for name, metadata in DATASET_METADATA.items():
            dataset_info += f"\n{name}:\n"
            dataset_info += f"  Description: {metadata['description']}\n"
            dataset_info += f"  Size: {metadata['size']}\n"
            dataset_info += f"  Languages: {', '.join(metadata['languages'])}\n"
            dataset_info += f"  Optimal for: {', '.join(metadata['optimal_for'])}\n"
            dataset_info += f"  Priority Score: {metadata['priority_score']}\n"
            dataset_info += f"  Strengths: {', '.join(metadata['strengths'])}\n"
            dataset_info += f"  Limitations: {', '.join(metadata['limitations'])}\n"
        
        special_info = ""
        if special_scenarios:
            special_info = f"\nSPECIAL SCENARIOS DETECTED:\n"
            for scenario in special_scenarios:
                special_info += f"- {scenario['description']}: {', '.join(scenario['datasets'])}\n"
        
        prompt = f"""
        Analyze this query to determine optimal HuggingFace datasets for search:
        
        Query: "{query}"
        {special_info}
        
        Available datasets with comprehensive metadata:
        {dataset_info}
        
        Based on the query analysis and dataset metadata, determine:
        
        1. HIGH_PRIORITY_DATASETS: Datasets with highest relevance (priority_score >= 0.8 and optimal_for matches)
        2. RELEVANT_DATASETS: Other datasets that could be useful (priority_score >= 0.5)
        3. QUERY_CHARACTERISTICS: What type of information is being sought?
        4. GEOGRAPHIC_FOCUS: Any geographic/language preferences?
        5. DOMAIN_FOCUS: Industry, sector, or domain focus?
        6. REASONING: Explain the dataset selection logic
        
        Consider:
        - Dataset size and coverage
        - Language requirements
        - Data structure (structured vs unstructured)
        - Specific use cases and strengths
        - Limitations and potential issues
        - Special scenarios if detected
        
        Return JSON:
        {{
            "high_priority_datasets": ["dataset1", "dataset2"],
            "relevant_datasets": ["dataset3", "dataset4"],
            "query_characteristics": "description",
            "geographic_focus": "region/language",
            "domain_focus": "industry/sector",
            "reasoning": "detailed explanation"
        }}
        """
        
        try:
            request = dict()
            
            response = await self.brain.process_request(request)
            if response and response.structured_data:
                return response.structured_data
                
        except Exception as e:
            logger.error(f"Dataset analysis error: {e}")
        
        return self._fallback_dataset_analysis(query, special_scenarios)
    
    def _fallback_dataset_analysis(self, query: str, special_scenarios: List[Dict]) -> Dict[str, Any]:
        """Fallback dataset analysis without AI"""
        query_lower = query.lower()
        high_priority = []
        relevant = []
        
        # Check for high-priority datasets based on keywords
        for dataset_name, metadata in DATASET_METADATA.items():
            if metadata['priority_score'] >= 0.8:
                # Check if query matches optimal use cases
                for use_case in metadata['optimal_for']:
                    if any(keyword in query_lower for keyword in use_case.split('_')):
                        high_priority.append(dataset_name)
                        break
            elif metadata['priority_score'] >= 0.5:
                relevant.append(dataset_name)
        
        # Add special scenario datasets
        if special_scenarios:
            for scenario in special_scenarios:
                for dataset in scenario['datasets']:
                    if dataset not in high_priority:
                        high_priority.append(dataset)
        
        return {
            'high_priority_datasets': high_priority,
            'relevant_datasets': relevant,
            'query_characteristics': 'general search',
            'geographic_focus': 'global',
            'domain_focus': 'general',
            'reasoning': 'Fallback analysis based on keyword matching and priority scores'
        }
    
    def determine_search_strategy(self, operator_info: Dict[str, Any], special_scenarios: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Determine which search systems to use based on operator and scenario analysis.
        
        Returns:
            Dictionary with recommended systems, priorities, and reasoning
        """
        strategy = {
            'recommended_systems': [],
            'primary_system': None,
            'reasoning': '',
            'query_type': operator_info.get('operator_type', 'none'),
            'information_need': 'general',
            'estimated_quality': 0.5
        }
        
        operator_type = operator_info.get('operator_type', 'none')
        
        # Determine search strategy based on operator type
        if operator_type == 'filetype':
            strategy['recommended_systems'] = ['bangs', 'directory']
            strategy['primary_system'] = 'bangs'
            strategy['information_need'] = 'file_discovery'
            strategy['reasoning'] = f"Filetype search for {operator_info.get('filetype')} files best handled by specialized engines"
            strategy['estimated_quality'] = 0.8
            
        elif operator_type == 'date':
            strategy['recommended_systems'] = ['bangs', 'huggingface']
            strategy['primary_system'] = 'bangs'
            strategy['information_need'] = 'temporal_data'
            strategy['reasoning'] = "Date-specific searches benefit from news engines and archived datasets"
            strategy['estimated_quality'] = 0.7
            
        elif operator_type == 'site' or operator_type == 'inurl':
            strategy['recommended_systems'] = ['directory', 'bangs']
            strategy['primary_system'] = 'directory'
            strategy['information_need'] = 'site_specific'
            strategy['reasoning'] = "Site/URL searches best handled by directory and specialized engines"
            strategy['estimated_quality'] = 0.9
            
        elif special_scenarios:
            # High-value investigative scenarios
            strategy['recommended_systems'] = ['huggingface', 'bangs', 'directory']
            strategy['primary_system'] = 'huggingface'
            strategy['information_need'] = 'investigative'
            scenario_names = [s['name'] for s in special_scenarios]
            strategy['reasoning'] = f"Special investigative scenarios detected: {', '.join(scenario_names)}"
            strategy['estimated_quality'] = 0.95
            
        else:
            # General search - use all systems
            strategy['recommended_systems'] = ['huggingface', 'directory', 'bangs']
            strategy['primary_system'] = 'huggingface'
            strategy['information_need'] = 'general'
            strategy['reasoning'] = "General search benefits from comprehensive multi-system approach"
            strategy['estimated_quality'] = 0.6
        
        return strategy

    def select_engines(self, operator_info: Dict[str, Any], level: str = "L1") -> List[str]:
        """
        Return engine codes to use for this query based on operator/search-type and matrix.
        Falls back to 'site' for site:, 'inurl' for inurl:, 'intitle' for title, or 'language',
        'filetype', 'date', 'news', 'proximity', 'book', 'academic', else default 'site'.
        """
        op = operator_info.get('operator_type', 'none')
        mapping = {
            'site': 'site',
            'inurl': 'inurl',
            'title': 'intitle',
            'language': 'language',
            'filetype': 'filetype',
            'date': 'date',
            'news': 'news',
            'proximity': 'proximity',
            'book': 'book',
            'academic': 'academic',
            # Extended operator keys → matrix keys
            'image_search': 'image',
            'video': 'video',
            'reverse_image': 'reverse_image',
            'author': 'author',
            'username': 'username',
            'comments': 'comments',
            'person': 'person',
            'company': 'company',
            'social': 'social',
        }
        st = mapping.get(op, 'site')
        codes = get_engines(st, level)
        # Apply optional capabilities filtering
        region = operator_info.get('region')
        modality = None
        if op in ['image_search', 'video', 'reverse_image']:
            modality = 'media'
        filtered = filter_engine_codes(codes, op, level, region=region, modality=modality)
        # Ensure YouTube is attempted for video/username/comments if key present
        try:
            if op == 'video':
                import os
                # Prefer youtube engines first
                if os.getenv('YOUTUBE_API_KEY'):
                    if 'YT' not in filtered:
                        filtered.insert(0, 'YT')
                    if 'YTC' not in filtered:
                        filtered.insert(1, 'YTC')
            if op == 'username':
                import os
                if os.getenv('YOUTUBE_API_KEY') and 'YTU' not in filtered:
                    filtered.insert(0, 'YTU')
            if op == 'comments':
                import os
                if os.getenv('YOUTUBE_API_KEY'):
                    if 'YTC' in filtered:
                        # Move YTC to front
                        filtered = ['YTC'] + [c for c in filtered if c != 'YTC']
                    else:
                        filtered.insert(0, 'YTC')
            # Academic fallback: ensure EX is included to guarantee results if specialist engines not available
            if op == 'academic':
                if 'EX' not in filtered:
                    filtered.insert(0, 'EX')
            # Ensure Archive.org always participates for maximum recall
            if 'AR' not in filtered:
                filtered.append('AR')
        except Exception:
            pass
        return filtered

    def build_engine_instances(self, operator_info: Dict[str, Any], level: str = "L1") -> Dict[str, Any]:
        """Return instantiated engines for the selected engine codes."""
        codes = self.select_engines(operator_info, level)
        try:
            from ..engine_dispatcher import build_engines_from_codes  # type: ignore
        except Exception:
            # Fallback to direct import for isolated execution
            from pathlib import Path as _Path
            import sys as _sys
            _router_root = _Path(__file__).resolve().parents[1]
            _sys.path.insert(0, str(_router_root))
            from engine_dispatcher import build_engines_from_codes  # type: ignore
        return build_engines_from_codes(codes)


# Export main functionality
__all__ = [
    'QueryRouter'
]
