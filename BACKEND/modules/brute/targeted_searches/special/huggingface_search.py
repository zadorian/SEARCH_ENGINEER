#!/usr/bin/env python3
"""
HuggingFace Dataset Search - Example integration with enhanced storage
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from datasets import load_dataset, get_dataset_config_names, DatasetInfo
from huggingface_hub import list_datasets, DatasetSearchResults
import pandas as pd
from .result_storage_enhanced import EnhancedResultStorage, create_enhanced_storage_callback

logger = logging.getLogger(__name__)


class HuggingFaceSearcher:
    """Search HuggingFace datasets and store results properly"""
    
    def __init__(self):
        self.available_datasets = [
            'fr3on/company',
            'microsoft/DialoGPT-small',
            'squad',
            'imdb',
            'wikitext'
        ]
    
    async def search_datasets(self, 
                            query: str, 
                            datasets: List[str] = None,
                            limit_per_dataset: int = 50) -> Dict[str, Any]:
        """
        Search across HuggingFace datasets
        
        Args:
            query: Search terms to look for in dataset records
            datasets: List of dataset names to search (None for default list)
            limit_per_dataset: Maximum records per dataset
            
        Returns:
            Dictionary with query, results, and metadata
        """
        if datasets is None:
            datasets = self.available_datasets
        
        results = []
        search_metadata = {
            'total_datasets_searched': 0,
            'successful_datasets': [],
            'failed_datasets': [],
            'query_terms': query.lower().split()
        }
        
        for dataset_name in datasets:
            try:
                logger.info(f"Searching dataset: {dataset_name}")
                dataset_results = await self._search_single_dataset(
                    dataset_name, query, limit_per_dataset
                )
                
                if dataset_results:
                    results.extend(dataset_results)
                    search_metadata['successful_datasets'].append(dataset_name)
                
                search_metadata['total_datasets_searched'] += 1
                
            except Exception as e:
                logger.error(f"Error searching dataset {dataset_name}: {e}")
                search_metadata['failed_datasets'].append({
                    'dataset': dataset_name,
                    'error': str(e)
                })
        
        return {
            'query': query,
            'results': results,
            'total_results': len(results),
            'metadata': search_metadata
        }
    
    async def _search_single_dataset(self, 
                                   dataset_name: str, 
                                   query: str, 
                                   limit: int) -> List[Dict[str, Any]]:
        """Search a single dataset"""
        try:
            # Load dataset (using a subset for large datasets)
            if dataset_name == 'fr3on/company':
                # Company dataset example
                return await self._search_company_dataset(query, limit)
            elif dataset_name in ['squad', 'imdb']:
                # Text datasets
                return await self._search_text_dataset(dataset_name, query, limit)
            else:
                # Generic dataset search
                return await self._search_generic_dataset(dataset_name, query, limit)
                
        except Exception as e:
            logger.error(f"Failed to search {dataset_name}: {e}")
            return []
    
    async def _search_company_dataset(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search the company dataset"""
        # Simulate company data (replace with actual dataset loading)
        company_data = [
            {
                'name': 'Apple Inc',
                'website': 'apple.com',
                'industry': 'Technology',
                'employees': 147000,
                'headquarters': 'Cupertino, CA',
                'founded': 1976
            },
            {
                'name': 'Microsoft Corporation',
                'website': 'microsoft.com',
                'industry': 'Technology', 
                'employees': 181000,
                'headquarters': 'Redmond, WA',
                'founded': 1975
            },
            {
                'name': 'Google LLC',
                'website': 'google.com',
                'industry': 'Technology',
                'employees': 139995,
                'headquarters': 'Mountain View, CA',
                'founded': 1998
            },
            {
                'name': 'Amazon.com Inc',
                'website': 'amazon.com',
                'industry': 'E-commerce',
                'employees': 1298000,
                'headquarters': 'Seattle, WA',
                'founded': 1994
            }
        ]
        
        query_terms = query.lower().split()
        results = []
        
        for company in company_data:
            # Search in company fields
            searchable_text = ' '.join([
                str(company.get('name', '')),
                str(company.get('industry', '')),
                str(company.get('headquarters', '')),
                str(company.get('website', ''))
            ]).lower()
            
            # Check if any query term matches
            if any(term in searchable_text for term in query_terms):
                results.append({
                    'dataset': 'fr3on/company',
                    'data': company,
                    'source': 'huggingface',
                    'match_info': {
                        'matched_terms': [term for term in query_terms if term in searchable_text],
                        'match_fields': self._get_matching_fields(company, query_terms)
                    }
                })
                
                if len(results) >= limit:
                    break
        
        return results
    
    async def _search_text_dataset(self, dataset_name: str, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search text-based datasets like IMDB or SQuAD"""
        try:
            # Load a small subset
            dataset = load_dataset(dataset_name, split='train[:1000]')
            
            query_terms = query.lower().split()
            results = []
            
            for i, record in enumerate(dataset):
                # Convert record to searchable text
                if dataset_name == 'imdb':
                    searchable_text = str(record.get('text', '')).lower()
                elif dataset_name == 'squad':
                    searchable_text = ' '.join([
                        str(record.get('question', '')),
                        str(record.get('context', '')),
                        str(record.get('title', ''))
                    ]).lower()
                else:
                    # Generic text search
                    searchable_text = ' '.join([str(v) for v in record.values()]).lower()
                
                # Check for matches
                if any(term in searchable_text for term in query_terms):
                    results.append({
                        'dataset': dataset_name,
                        'data': {
                            'id': i,
                            **dict(record)
                        },
                        'source': 'huggingface',
                        'match_info': {
                            'matched_terms': [term for term in query_terms if term in searchable_text],
                            'record_index': i
                        }
                    })
                    
                    if len(results) >= limit:
                        break
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching text dataset {dataset_name}: {e}")
            return []
    
    async def _search_generic_dataset(self, dataset_name: str, query: str, limit: int) -> List[Dict[str, Any]]:
        """Generic dataset search"""
        try:
            # Try to load a small subset
            dataset = load_dataset(dataset_name, split='train[:500]')
            
            query_terms = query.lower().split()
            results = []
            
            for i, record in enumerate(dataset):
                # Convert all fields to searchable text
                searchable_text = ' '.join([str(v) for v in record.values()]).lower()
                
                if any(term in searchable_text for term in query_terms):
                    results.append({
                        'dataset': dataset_name,
                        'data': {
                            'id': i,
                            **dict(record)
                        },
                        'source': 'huggingface',
                        'match_info': {
                            'matched_terms': [term for term in query_terms if term in searchable_text],
                            'record_index': i
                        }
                    })
                    
                    if len(results) >= limit:
                        break
            
            return results
            
        except Exception as e:
            logger.error(f"Error in generic dataset search {dataset_name}: {e}")
            return []
    
    def _get_matching_fields(self, record: Dict, query_terms: List[str]) -> List[str]:
        """Identify which fields contain matching terms"""
        matching_fields = []
        
        for field, value in record.items():
            value_str = str(value).lower()
            if any(term in value_str for term in query_terms):
                matching_fields.append(field)
        
        return matching_fields
    
    async def search_with_storage(self, 
                                query: str, 
                                project_id: str,
                                datasets: List[str] = None,
                                storage: EnhancedResultStorage = None) -> Dict[str, Any]:
        """
        Search datasets and automatically store results
        
        Args:
            query: Search query
            project_id: Project to store results under
            datasets: Datasets to search
            storage: Storage instance (creates new one if None)
            
        Returns:
            Search results with storage counts
        """
        if storage is None:
            storage = EnhancedResultStorage()
        
        try:
            # Perform search
            search_results = await self.search_datasets(query, datasets)
            
            # Store results
            if search_results['results']:
                counts = storage.store_mixed_results(
                    query, 
                    search_results['results'], 
                    project_id
                )
                
                search_results['storage_counts'] = counts
                search_results['total_stored'] = sum(counts.values())
                
                logger.info(f"Stored {search_results['total_stored']} results: {counts}")
            else:
                search_results['storage_counts'] = {}
                search_results['total_stored'] = 0
            
            return search_results
            
        except Exception as e:
            logger.error(f"Error in search_with_storage: {e}")
            raise
        finally:
            storage.close()


# Example usage and testing
async def example_usage():
    """Example of how to use HuggingFace search with enhanced storage"""
    
    searcher = HuggingFaceSearcher()
    storage = EnhancedResultStorage("hf_test.db")
    
    try:
        print("🔍 Searching for technology companies...")
        
        # Search for technology companies
        results = await searcher.search_with_storage(
            query="technology apple microsoft",
            project_id="tech_companies_2024",
            datasets=['fr3on/company'],
            storage=storage
        )
        
        print(f"📊 Found {results['total_results']} results")
        print(f"💾 Stored {results['total_stored']} records")
        print(f"📈 Storage breakdown: {results['storage_counts']}")
        
        # Show some results
        print("\n📋 Sample results:")
        for i, result in enumerate(results['results'][:3]):
            print(f"\n{i+1}. Dataset: {result['dataset']}")
            print(f"   Data: {result['data']}")
            print(f"   Matches: {result['match_info']['matched_terms']}")
        
        # Search in stored records
        print("\n🔍 Searching stored records for 'apple'...")
        apple_records = storage.search_in_dataset_records(
            'apple', 
            project_id='tech_companies_2024'
        )
        
        for record in apple_records:
            print(f"📄 {record['value']}")
            print(f"   Dataset: {record['dataset_name']}")
            print(f"   Notes: {record['notes'][:100]}...")
        
        # Get dataset summary
        print("\n📊 Dataset summary:")
        summary = storage.get_dataset_summary('tech_companies_2024')
        for dataset, count in summary.items():
            print(f"   {dataset}: {count} records")
        
    finally:
        storage.close()


if __name__ == "__main__":
    # Run example
    asyncio.run(example_usage())
    
    print("\n💡 Usage examples:")
    print("# Basic search")
    print("searcher = HuggingFaceSearcher()")
    print("results = await searcher.search_datasets('technology companies')")
    print()
    print("# Search with storage")
    print("results = await searcher.search_with_storage(")
    print("    'ai machine learning',")
    print("    'ai_research_project'")
    print(")")
    print()
    print("# Search specific datasets")
    print("results = await searcher.search_datasets(")
    print("    'natural language',")
    print("    datasets=['squad', 'imdb']")
    print(")")