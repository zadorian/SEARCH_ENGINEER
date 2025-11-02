#!/usr/bin/env python3
"""
EDGAR Integration for Corporate Search System
Enhanced wrapper for the existing EDGAR tool in the Corporate Search project
"""

import os
import subprocess
import json
import csv
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class EdgarSearchIntegration:
    """
    Integration wrapper for the EDGAR tool within the Corporate Search system.
    Provides a Python API for the command-line EDGAR tool.
    """
    
    def __init__(self, output_dir: str = None):
        """
        Initialize the EDGAR integration.

        Args:
            output_dir: Directory for output files (defaults to local edgar_output/)
        """
        # Use current directory or specified output directory
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            # Create local output directory in the current working directory
            self.output_dir = Path.cwd() / "edgar_output"

        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Try to find EDGAR-main directory, fall back to current directory
        self.project_root = Path("/Users/brain/Desktop/Corporate_Search")
        self.edgar_dir = self.project_root / "EDGAR-main"

        # If EDGAR directory doesn't exist, use current directory
        if not self.edgar_dir.exists():
            self.edgar_dir = Path.cwd()

        # Find the right Python command
        self.python_cmd = self._find_python_command()
        
    def _find_python_command(self) -> str:
        """Find the correct Python command that has edgar-tool installed."""
        for cmd in ['python3.10', 'python3', 'python']:
            try:
                # Check if edgar-tool is available
                subprocess.run(
                    [cmd, '-m', 'edgar_tool.cli', '--help'], 
                    check=True, 
                    capture_output=True,
                    cwd=str(self.edgar_dir)
                )
                return cmd
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        
        logger.warning("Could not find edgar-tool, defaulting to python3")
        return 'python3'
    
    def text_search(
        self,
        search_terms: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        filing_form: Optional[str] = None,
        entity_id: Optional[str] = None,
        company_name: Optional[str] = None,
        inc_in: Optional[str] = None,
        output_format: str = "csv"
    ) -> Dict[str, Any]:
        """
        Perform a text search on EDGAR filings.
        
        Args:
            search_terms: List of search terms/phrases
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            filing_form: Filing form category
            entity_id: Specific entity CIK
            company_name: Company name or ticker
            inc_in: Incorporation location
            output_format: Output format (csv, json, jsonl)
            
        Returns:
            Dictionary with results file path and metadata
        """
        # Generate output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"edgar_text_search_{timestamp}.{output_format}"
        
        # Build command
        cmd = [self.python_cmd, '-m', 'edgar_tool.cli', 'text_search']
        
        # Add search terms (without quotes - subprocess handles escaping)
        for term in search_terms:
            cmd.append(term)

        # Add optional parameters
        if start_date:
            cmd.extend(['--start_date', start_date])
        if end_date:
            cmd.extend(['--end_date', end_date])
        if filing_form:
            cmd.extend(['--filing_form', filing_form])
        if entity_id:
            cmd.extend(['--entity_id', entity_id])
        if company_name:
            cmd.extend(['--company_name', company_name])
        if inc_in:
            cmd.extend(['--inc_in', inc_in])
        
        cmd.extend(['--output', str(output_file)])
        
        # Execute search
        logger.info(f"Executing EDGAR search: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                text=True,
                cwd=str(self.edgar_dir)
            )
            
            if result.returncode != 0:
                logger.error(f"Search failed: {result.stderr}")
                return {
                    'success': False,
                    'error': result.stderr,
                    'output_file': None
                }
            
            # Parse results
            results_data = self._parse_results(output_file, output_format)
            
            return {
                'success': True,
                'output_file': str(output_file),
                'result_count': len(results_data),
                'results': results_data,
                'command': ' '.join(cmd)
            }
            
        except Exception as e:
            logger.error(f"Error executing search: {e}")
            return {
                'success': False,
                'error': str(e),
                'output_file': None
            }
    
    def rss_monitor(
        self,
        tickers: List[str],
        output_format: str = "csv",
        every_n_mins: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Monitor RSS feed for specific tickers.
        
        Args:
            tickers: List of stock tickers to monitor
            output_format: Output format (csv, json, jsonl)
            every_n_mins: If set, monitor periodically
            
        Returns:
            Dictionary with results
        """
        # Generate output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"edgar_rss_{timestamp}.{output_format}"
        
        # Build command
        cmd = [self.python_cmd, '-m', 'edgar_tool.cli', 'rss']
        cmd.extend(tickers)
        cmd.extend(['--output', str(output_file)])
        
        if every_n_mins:
            cmd.extend(['--every_n_mins', str(every_n_mins)])
        
        # Execute
        logger.info(f"Starting RSS monitor: {' '.join(cmd)}")
        
        try:
            if every_n_mins:
                # For periodic monitoring, run in background
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=str(self.edgar_dir)
                )
                return {
                    'success': True,
                    'output_file': str(output_file),
                    'process_id': process.pid,
                    'mode': 'periodic',
                    'interval_minutes': every_n_mins
                }
            else:
                # One-time fetch
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(self.edgar_dir)
                )
                
                if result.returncode != 0:
                    return {
                        'success': False,
                        'error': result.stderr
                    }
                
                results_data = self._parse_results(output_file, output_format)
                
                return {
                    'success': True,
                    'output_file': str(output_file),
                    'result_count': len(results_data),
                    'results': results_data,
                    'mode': 'one-time'
                }
                
        except Exception as e:
            logger.error(f"Error with RSS monitor: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _parse_results(self, output_file: Path, format: str) -> List[Dict[str, Any]]:
        """Parse results from output file."""
        if not output_file.exists():
            return []
        
        results = []
        
        try:
            if format == 'csv':
                with open(output_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    results = list(reader)
            elif format == 'json':
                with open(output_file, 'r', encoding='utf-8') as f:
                    results = json.load(f)
            elif format == 'jsonl':
                with open(output_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        results.append(json.loads(line))
        except Exception as e:
            logger.error(f"Error parsing results: {e}")
        
        return results
    
    def search_company_filings(
        self,
        company_name: str,
        filing_types: Optional[List[str]] = None,
        years_back: int = 5
    ) -> Dict[str, Any]:
        """
        Convenience method to search all filings for a specific company.
        
        Args:
            company_name: Company name or ticker
            filing_types: Specific filing types (defaults to common types)
            years_back: Number of years to search back
            
        Returns:
            Search results
        """
        if not filing_types:
            filing_types = ['10-K', '10-Q', '8-K', 'DEF 14A']
        
        # Calculate date range
        end_date = date.today().strftime('%Y-%m-%d')
        start_date = date(date.today().year - years_back, 1, 1).strftime('%Y-%m-%d')
        
        # Build search
        search_terms = []  # Empty search terms to get all filings
        
        return self.text_search(
            search_terms=search_terms,
            company_name=company_name,
            start_date=start_date,
            end_date=end_date,
            output_format='json'
        )
    
    def search_by_keywords(
        self,
        keywords: List[str],
        companies: Optional[List[str]] = None,
        date_range: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Search for specific keywords across filings.
        
        Args:
            keywords: Keywords to search for
            companies: Optional list of companies to limit search
            date_range: Optional dict with 'start' and 'end' dates
            
        Returns:
            Search results
        """
        results = {}
        
        if companies:
            # Search each company separately
            for company in companies:
                result = self.text_search(
                    search_terms=keywords,
                    company_name=company,
                    start_date=date_range.get('start') if date_range else None,
                    end_date=date_range.get('end') if date_range else None,
                    output_format='json'
                )
                results[company] = result
        else:
            # General search
            results = self.text_search(
                search_terms=keywords,
                start_date=date_range.get('start') if date_range else None,
                end_date=date_range.get('end') if date_range else None,
                output_format='json'
            )
        
        return results


# Example usage functions
def example_basic_search():
    """Example: Basic text search."""
    edgar = EdgarSearchIntegration()
    
    # Search for AI mentions in recent filings
    results = edgar.text_search(
        search_terms=["artificial intelligence", "machine learning"],
        start_date="2023-01-01",
        output_format="json"
    )
    
    if results['success']:
        print(f"Found {results['result_count']} results")
        print(f"Results saved to: {results['output_file']}")
        
        # Show first few results
        for i, result in enumerate(results['results'][:3]):
            print(f"\nResult {i+1}:")
            print(f"  Company: {result.get('Entity Name', 'N/A')}")
            print(f"  Form: {result.get('Filing Type', 'N/A')}")
            print(f"  Date: {result.get('Filed', 'N/A')}")
    
    return results


def example_company_search():
    """Example: Search specific company filings."""
    edgar = EdgarSearchIntegration()
    
    # Get Apple's recent filings
    results = edgar.search_company_filings(
        company_name="Apple Inc",
        filing_types=['10-K', '10-Q', '8-K'],
        years_back=2
    )
    
    if results['success']:
        print(f"Found {results['result_count']} Apple filings")
    
    return results


def example_rss_monitoring():
    """Example: Monitor RSS feed for tech stocks."""
    edgar = EdgarSearchIntegration()
    
    # One-time check of tech stock filings
    results = edgar.rss_monitor(
        tickers=['AAPL', 'MSFT', 'GOOGL', 'NVDA'],
        output_format='json'
    )
    
    if results['success']:
        print(f"RSS feed check complete: {results['result_count']} new filings")
    
    return results


def example_cross_reference_search():
    """Example: Cross-reference with other Corporate Search tools."""
    edgar = EdgarSearchIntegration()
    
    # This example shows how EDGAR could be used with other tools
    # For instance, after finding a company in OpenCorporates
    
    company_name = "Tesla Inc"  # Found via OpenCorporates
    
    # Search for recent material events
    results = edgar.text_search(
        search_terms=[""],  # Empty search to get all filings
        company_name=company_name,
        filing_form="all_annual_quarterly_and_current_reports",
        start_date="2024-01-01",
        output_format="json"
    )
    
    if results['success']:
        print(f"Found {results['result_count']} filings for {company_name}")
        
        # Filter for 8-K forms (material events)
        material_events = [
            r for r in results['results'] 
            if r.get('Filing Type', '').startswith('8-K')
        ]
        print(f"Material events (8-K): {len(material_events)}")
    
    return results


if __name__ == "__main__":
    print("EDGAR Integration Examples for Corporate Search\n")
    
    print("1. Basic Keyword Search:")
    example_basic_search()
    print("\n" + "="*60 + "\n")
    
    print("2. Company Filings Search:")
    example_company_search()
    print("\n" + "="*60 + "\n")
    
    print("3. RSS Feed Monitoring:")
    example_rss_monitoring()
    print("\n" + "="*60 + "\n")
    
    print("4. Cross-Reference Search:")
    example_cross_reference_search()
