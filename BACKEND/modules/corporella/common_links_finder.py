#!/usr/bin/env python3
"""
Script with two main functions:
1. Find common domains that are linked to by a given list of referring domains using Ahrefs API.
   This helps identify potential PBN footprints, coordinated link networks, or common affiliate programs.
2. Find domains with similar backlink profiles to a target domain (when using --similar flag).
   This identifies potential competitors or related sites receiving links from the same sources.
"""
import requests
from collections import defaultdict
from typing import List, Dict, Set, Tuple, Optional
import time
import json
import sys
import os
import argparse
from urllib.parse import urlparse
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Try to load environment variables from dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv module not installed, using default or environment variables

# Ahrefs API configuration
AHREFS_API_TOKEN = os.getenv("AHREFS_API_KEY", "001VsvfrsqI3boNHFLs-XUTfgIkSm_jbrash5Cvh")
API_ENDPOINT = "https://apiv2.ahrefs.com"

# Headers
HEADERS = {
    "Accept": "application/json"
}

# Rate-limit control
DELAY = 2.0  # seconds between requests

def get_domain_from_url(url: str) -> str:
    """Extract the domain from a URL."""
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        parsed = urlparse(url)
        domain = parsed.netloc
        return domain.lower().replace('www.', '')
    except Exception as e:
        return url.lower().replace('www.', '')

def get_linked_domains(referring_domain: str, max_links: int = 100) -> Set[str]:
    """
    Get domains that are linked from a given referring domain.
    Uses Ahrefs API to fetch linked domains.
    Limits results to max_links to conserve API usage.
    """
    target_domains = set()
    
    # First check if domain exists in Ahrefs
    check_params = {
        "token": AHREFS_API_TOKEN,
        "from": "domain_rating",  # This should be valid for all accounts
        "target": referring_domain,
        "mode": "domain",
        "limit": 1,
        "output": "json"
    }
    
    try:
        logger.info(f"Checking if domain exists in Ahrefs database: {referring_domain}")
        response = requests.get(API_ENDPOINT, params=check_params, headers=HEADERS)
        
        if response.status_code != 200:
            logger.error(f"Error: API returned status code {response.status_code}")
            logger.error(f"Response: {response.text}")
            return set()
            
        data = response.json()
        
        if 'error' in data:
            logger.error(f"API Error: {data['error']}")
            return set()
            
        logger.info(f"Domain found in Ahrefs database")
        
        # Try refdomains endpoint without where clause - limit to conserve API usage
        params = {
            "token": AHREFS_API_TOKEN,
            "from": "refdomains",
            "target": referring_domain,
            "mode": "domain",
            "limit": max_links,  # Limit to conserve API usage
            "output": "json"
        }
        
        logger.info(f"Fetching outgoing links for: {referring_domain} (limited to {max_links})")
        response = requests.get(API_ENDPOINT, params=params, headers=HEADERS)
        
        if response.status_code != 200:
            logger.error(f"Error: API returned status code {response.status_code}")
            logger.error(f"Response: {response.text}")
            return set()
            
        data = response.json()
        
        if 'error' in data:
            logger.error(f"API Error: {data['error']}")
            # Try alternative endpoint
            logger.info("Trying alternative endpoint...")
            params["from"] = "linked_domains"
            params["limit"] = max_links  # Ensure limit is also set here
            response = requests.get(API_ENDPOINT, params=params, headers=HEADERS)
            
            if response.status_code != 200:
                logger.error(f"Error with alternative endpoint: {response.status_code}")
                return set()
                
            data = response.json()
            if 'error' in data:
                logger.error(f"API Error with alternative endpoint: {data['error']}")
                return set()
            
            links = data.get("linked_domains", [])
            if links:
                actual_count = len(links)
                logger.info(f"Found {actual_count} outgoing links (limited to {max_links})")
                for link in links:
                    domain_to = link.get("domain", "")
                    if domain_to:
                        target_domains.add(domain_to.lower())
                return target_domains
        
        # Process links from refdomains endpoint if available
        links = data.get("refdomains", [])
        
        if not links:
            logger.info(f"No outgoing links found for {referring_domain}")
            return set()
            
        actual_count = len(links)
        logger.info(f"Found {actual_count} outgoing links (limited to {max_links})")
        
        for link in links:
            domain_to = link.get("refdomain", "")
            if domain_to:
                target_domains.add(domain_to.lower())
    
    except Exception as e:
        logger.error(f"Error fetching data for {referring_domain}: {e}")
    
    logger.info(f"Found {len(target_domains)} unique target domains")
    time.sleep(DELAY)
    return target_domains

def get_backlink_domains(domain: str, limit: int = 1000) -> Set[str]:
    """
    Get domains that link to the target domain.
    Returns a set of domains that link to the target.
    """
    referring_domains = set()
    
    # Check if domain exists in Ahrefs
    check_params = {
        "token": AHREFS_API_TOKEN,
        "from": "domain_rating", 
        "target": domain,
        "mode": "domain",
        "limit": 1,
        "output": "json"
    }
    
    try:
        logger.info(f"Checking if domain exists in Ahrefs database: {domain}")
        response = requests.get(API_ENDPOINT, params=check_params, headers=HEADERS)
        
        if response.status_code != 200:
            logger.error(f"Error: API returned status code {response.status_code}")
            logger.error(f"Response: {response.text}")
            return set()
            
        data = response.json()
        
        if 'error' in data:
            logger.error(f"API Error: {data['error']}")
            return set()
            
        logger.info(f"Domain found in Ahrefs database")
        
        # Get referring domains
        params = {
            "token": AHREFS_API_TOKEN,
            "from": "refdomains",
            "target": domain,
            "mode": "domain",
            "limit": limit,
            "order_by": "domain_rating:desc",  # Get highest authority domains first
            "output": "json"
        }
        
        logger.info(f"Fetching domains linking to: {domain}")
        response = requests.get(API_ENDPOINT, params=params, headers=HEADERS)
        
        if response.status_code != 200:
            logger.error(f"Error: API returned status code {response.status_code}")
            logger.error(f"Response: {response.text}")
            return set()
            
        data = response.json()
        
        if 'error' in data:
            logger.error(f"API Error: {data['error']}")
            return set()
        
        # Process referring domains
        refs = data.get("refdomains", [])
        
        if not refs:
            logger.info(f"No referring domains found for {domain}")
            return set()
            
        logger.info(f"Found {len(refs)} referring domains")
        
        for ref in refs:
            ref_domain = ref.get("refdomain", "")
            if ref_domain:
                referring_domains.add(ref_domain.lower())
    
    except Exception as e:
        logger.error(f"Error fetching referring domains for {domain}: {e}")
    
    time.sleep(DELAY)
    return referring_domains

def find_common_link_targets(ref_domains: List[str]) -> Dict[str, dict]:
    """
    Takes a list of referring domains, returns a dict of targets with details.
    """
    all_targets = defaultdict(lambda: {"count": 0, "referrers": []})
    
    for domain in ref_domains:
        logger.info(f"\nAnalyzing outgoing links from: {domain}")
        target_domains = get_linked_domains(domain)
        
        for target in target_domains:
            all_targets[target]["count"] += 1
            all_targets[target]["referrers"].append(domain)
    
    # Convert to regular dict and sort by count
    result = {k: v for k, v in sorted(
        all_targets.items(), 
        key=lambda item: item[1]["count"], 
        reverse=True
    )}
    
    return result

def find_similar_backlink_profiles(target_domain: str, min_shared: int = 3, max_links: int = 100, max_backlinks: int = 10) -> Dict[str, dict]:
    """
    Finds domains with similar backlink profiles to the target domain.
    Returns a dict of domains that share backlinks with the target.
    
    Parameters:
    - target_domain: The domain to find similar profiles for
    - min_shared: Minimum number of shared referring domains required
    - max_links: Maximum number of outgoing links to analyze per referring domain
    - max_backlinks: Maximum number of backlink sources to analyze
    """
    # Step 1: Get all domains linking to the target
    logger.info(f"Finding sites that link to {target_domain}")
    referring_domains = get_backlink_domains(target_domain)
    
    if not referring_domains:
        return {}
        
    logger.info(f"Found {len(referring_domains)} sites linking to {target_domain}")
    
    # Step 2: For each referring domain, find what other domains they link to
    similar_domains = defaultdict(lambda: {"count": 0, "shared_referrers": []})
    
    # Use a counter to sample only a portion of referring domains if there are too many
    # Limit to max_backlinks for faster results
    sample_limit = min(max_backlinks, len(referring_domains))
    sample_count = 0
    
    # Get the top X domains by authority (they're already sorted by domain_rating)
    sampled_domains = list(referring_domains)[:sample_limit]
    logger.info(f"For efficiency, analyzing only top {sample_limit} referring domains by authority")
    
    for ref_domain in sampled_domains:
        sample_count += 1
        logger.info(f"\nAnalyzing outgoing links from referring domain {sample_count}/{sample_limit}: {ref_domain}")
        
        # Get domains that this referring domain links to, with max_links limit
        other_targets = get_linked_domains(ref_domain, max_links=max_links)
        
        # Ignore the original target domain in results
        if target_domain in other_targets:
            other_targets.remove(target_domain)
        
        # Add each target to our similar domains dict
        for other_domain in other_targets:
            similar_domains[other_domain]["count"] += 1
            similar_domains[other_domain]["shared_referrers"].append(ref_domain)
    
    # Filter out domains with too few shared referrers
    filtered_results = {
        domain: data 
        for domain, data in similar_domains.items() 
        if data["count"] >= min_shared
    }
    
    # Sort by count of shared referring domains
    result = {k: v for k, v in sorted(
        filtered_results.items(), 
        key=lambda item: item[1]["count"], 
        reverse=True
    )}
    
    return result

def find_colinked_domains(target_domain: str, max_links: int = 100, max_ref_domains: int = 10) -> Dict[str, dict]:
    """
    For a target domain, find other domains that its referring domains also link to.
    This reveals domains frequently linked alongside the target domain.
    
    Parameters:
    - target_domain: The domain to analyze
    - max_links: Maximum number of outgoing links to fetch per referring domain
    - max_ref_domains: Maximum number of referring domains to analyze
    """
    # Step 1: Get domains linking to the target
    logger.info(f"Finding domains that link to {target_domain}")
    ref_domains = get_backlink_domains(target_domain)
    
    if not ref_domains:
        return {}
        
    logger.info(f"Found {len(ref_domains)} domains linking to {target_domain}")
    
    # Step 2: For each referring domain, get its outgoing links
    colinked_domains = defaultdict(lambda: {"count": 0, "referrers": []})
    
    # Limit the number of referring domains to analyze
    sample_limit = min(max_ref_domains, len(ref_domains))
    sampled_domains = list(ref_domains)[:sample_limit]
    logger.info(f"For efficiency, analyzing only top {sample_limit} referring domains by authority")
    
    for i, ref_domain in enumerate(sampled_domains, 1):
        logger.info(f"\nAnalyzing outgoing links from referring domain {i}/{sample_limit}: {ref_domain}")
        
        # Get domains that this referring domain links to
        outgoing_links = get_linked_domains(ref_domain, max_links=max_links)
        
        # Remove the original target from results
        if target_domain in outgoing_links:
            outgoing_links.remove(target_domain)
            
        logger.info(f"Found {len(outgoing_links)} other domains linked to by {ref_domain}")
        
        # Add each linked domain to our results
        for linked_domain in outgoing_links:
            colinked_domains[linked_domain]["count"] += 1
            colinked_domains[linked_domain]["referrers"].append(ref_domain)
    
    # Sort by count (number of referring domains linking to this domain)
    result = {k: v for k, v in sorted(
        colinked_domains.items(),
        key=lambda item: item[1]["count"],
        reverse=True
    )}
    
    return result

def find_backlinks_twice_removed(target_domain: str, max_links: int = 100, max_ref_domains: int = 10, max_second_level: int = 5) -> Dict[str, dict]:
    """
    Find domains that link to your backlinks ("backlinks twice removed").
    This reveals the ecosystem around your backlink sources.
    
    Parameters:
    - target_domain: The domain to analyze
    - max_links: Maximum number of backlinks to fetch per domain
    - max_ref_domains: Maximum number of first-level backlinks to analyze
    - max_second_level: Maximum number of second-level domains to analyze per first-level domain
    """
    # Step 1: Get first level backlinks (domains linking directly to target)
    logger.info(f"Finding domains linking to {target_domain}")
    first_level_domains = get_backlink_domains(target_domain, limit=max_links)
    
    if not first_level_domains:
        return {}
        
    logger.info(f"Found {len(first_level_domains)} domains linking directly to {target_domain}")
    
    # Step 2: Get second level backlinks (domains linking to your backlinks)
    second_level_domains = defaultdict(lambda: {"count": 0, "paths": []})
    
    # Limit number of first-level domains to analyze
    sample_limit = min(max_ref_domains, len(first_level_domains))
    sampled_domains = list(first_level_domains)[:sample_limit]
    logger.info(f"For efficiency, analyzing backlinks for top {sample_limit} referring domains")
    
    for i, first_level in enumerate(sampled_domains, 1):
        logger.info(f"\nAnalyzing backlinks for referring domain {i}/{sample_limit}: {first_level}")
        
        # Get domains linking to this first level domain
        second_domains = get_backlink_domains(first_level, limit=max_second_level)
        logger.info(f"Found {len(second_domains)} domains linking to {first_level}")
        
        # Add each second level domain to our results
        for second_domain in second_domains:
            # Skip if it's the target domain or a first level domain to avoid loops
            if second_domain == target_domain or second_domain in first_level_domains:
                continue
                
            # Record the path: second_domain -> first_level -> target_domain
            second_level_domains[second_domain]["count"] += 1
            second_level_domains[second_domain]["paths"].append(first_level)
    
    # Sort by count (number of different paths to target)
    result = {k: v for k, v in sorted(
        second_level_domains.items(),
        key=lambda item: item[1]["count"],
        reverse=True
    )}
    
    return result

def compare_domains(domains: List[str], max_links: int = 100, filter_seo_spam: bool = True) -> Dict[str, Dict]:
    """
    Compare multiple domains to find both common backlinks and common outbound links.
    
    Parameters:
    - domains: List of domains to compare
    - max_links: Maximum links to fetch per domain
    - filter_seo_spam: Whether to filter out SEO spam domains
    
    Returns a dict with two keys:
    - 'common_backlinks': Domains that link to multiple input domains
    - 'common_outlinks': Domains that are linked to by multiple input domains
    """
    if len(domains) < 2:
        logger.error("Need at least 2 domains to compare")
        return {"common_backlinks": {}, "common_outlinks": {}}
    
    # Initialize results
    results = {
        "common_backlinks": defaultdict(lambda: {"count": 0, "targets": []}),
        "common_outlinks": defaultdict(lambda: {"count": 0, "sources": []})
    }
    
    # Explicit backlist of domains to ignore
    backlist_domains = {
        # Specific domains to explicitly ignore
        "rankva.com",
        "jacobverghese.info",
        "crossover-p.com",
        "itxoft.com",
        "agmermer.pro",
        "exlinko.org",
        "linkbox.agency",
        "seoflox.io"
    }
    
    def is_backlisted(domain: str) -> bool:
        """Check if a domain is in the explicit backlist."""
        if not filter_seo_spam:
            return False  # Skip filtering if disabled
        return domain.lower() in backlist_domains
    
    # Step 1: Get backlinks for each domain
    all_backlinks = {}
    for domain in domains:
        logger.info(f"Getting backlinks for: {domain}")
        backlinks = get_backlink_domains(domain, limit=max_links)
        
        # Filter out domains from our input list to avoid circular references
        # Also filter out explicitly backlisted domains
        filtered_backlinks = {
            backlink for backlink in backlinks 
            if backlink not in domains and not is_backlisted(backlink)
        }
        
        all_backlinks[domain] = filtered_backlinks
        logger.info(f"Found {len(filtered_backlinks)} legitimate backlinks for {domain} (filtered out backlisted domains)")
        
        # Check for common backlinks with previously processed domains
        for backlink in filtered_backlinks:
            for prev_domain in domains:
                if prev_domain == domain:
                    continue  # Skip self
                if prev_domain in all_backlinks and backlink in all_backlinks[prev_domain]:
                    results["common_backlinks"][backlink]["count"] += 1
                    if domain not in results["common_backlinks"][backlink]["targets"]:
                        results["common_backlinks"][backlink]["targets"].append(domain)
                    if prev_domain not in results["common_backlinks"][backlink]["targets"]:
                        results["common_backlinks"][backlink]["targets"].append(prev_domain)
    
    # Step 2: Get outbound links for each domain
    all_outlinks = {}
    for domain in domains:
        logger.info(f"Getting outbound links for: {domain}")
        outlinks = get_linked_domains(domain, max_links=max_links)
        
        # Filter out domains from our input list to avoid circular references
        # Also filter out explicitly backlisted domains
        filtered_outlinks = {
            outlink for outlink in outlinks 
            if outlink not in domains and not is_backlisted(outlink)
        }
        
        all_outlinks[domain] = filtered_outlinks
        logger.info(f"Found {len(filtered_outlinks)} legitimate outbound links for {domain} (filtered out backlisted domains)")
        
        # Check for common outbound links with previously processed domains
        for outlink in filtered_outlinks:
            for prev_domain in domains:
                if prev_domain == domain:
                    continue  # Skip self
                if prev_domain in all_outlinks and outlink in all_outlinks[prev_domain]:
                    results["common_outlinks"][outlink]["count"] += 1
                    if domain not in results["common_outlinks"][outlink]["sources"]:
                        results["common_outlinks"][outlink]["sources"].append(domain)
                    if prev_domain not in results["common_outlinks"][outlink]["sources"]:
                        results["common_outlinks"][outlink]["sources"].append(prev_domain)
    
    # Sort results by count (most common first)
    sorted_backlinks = {k: v for k, v in sorted(
        results["common_backlinks"].items(),
        key=lambda item: len(item[1]["targets"]),
        reverse=True
    )}
    
    sorted_outlinks = {k: v for k, v in sorted(
        results["common_outlinks"].items(),
        key=lambda item: len(item[1]["sources"]),
        reverse=True
    )}
    
    return {
        "common_backlinks": sorted_backlinks,
        "common_outlinks": sorted_outlinks
    }

def get_domain_outlink_count(domain: str) -> int:
    """Get the count of outbound links from a domain. Fewer outlinks often indicate more authority."""
    try:
        # First check if domain exists in Ahrefs
        check_params = {
            "token": AHREFS_API_TOKEN,
            "from": "domain_rating",
            "target": domain,
            "mode": "domain",
            "limit": 1,
            "output": "json"
        }
        
        response = requests.get(API_ENDPOINT, params=check_params, headers=HEADERS)
        if response.status_code != 200:
            logger.error(f"Error getting domain rating: {response.status_code}")
            return 999999  # High number indicates error/low priority
            
        # Now get stats
        stats_params = {
            "token": AHREFS_API_TOKEN,
            "from": "linked_domains_count",  # This endpoint gives just the count
            "target": domain,
            "mode": "domain",
            "output": "json"
        }
        
        response = requests.get(API_ENDPOINT, params=stats_params, headers=HEADERS)
        if response.status_code != 200:
            logger.error(f"Error getting outlink count: {response.status_code}")
            return 999999  # High number indicates error/low priority
            
        data = response.json()
        
        if 'error' in data:
            logger.error(f"API Error: {data['error']}")
            return 999999
            
        # Try to get the count from the response
        if 'stats' in data and 'linked_domains' in data['stats']:
            return data['stats']['linked_domains']
        else:
            # Fallback to counting manually
            outlinks = get_linked_domains(domain, max_links=500)
            return len(outlinks)
            
    except Exception as e:
        logger.error(f"Error checking outlink count: {e}")
        return 999999  # High number indicates error/low priority
        
    return 999999  # Default high number

def display_domain_rankings(domains: Dict[str, Dict], title: str, domain_type: str, max_to_show: int = 50, 
                          check_outlinks: bool = True):
    """
    Display domain rankings with additional authority indicators.
    
    Parameters:
    - domains: Dictionary of domains with their data
    - title: Section title
    - domain_type: Type of domains (backlinks or outlinks)
    - max_to_show: Maximum number of domains to show
    - check_outlinks: Whether to check outbound link counts
    """
    print(f"\n{title}")
    print("=" * 50)
    
    # Sort domains by count first
    sorted_domains = sorted(
        domains.items(),
        key=lambda item: (
            # Primary sort by count (descending)
            len(item[1]["targets" if domain_type == "backlinks" else "sources"]), 
            # Secondary sort by domain name (ascending)
            item[0]
        ),
        reverse=True
    )
    
    # Now if requested, check outlink counts and add to data for display
    displayed_count = 0
    
    if check_outlinks and sorted_domains:
        print("Analyzing domain authority (checking outbound links)...")
        
        # Convert to list of tuples with outlink counts
        domains_with_outlinks = []
        
        for domain, data in sorted_domains:
            # Only check domains we'll actually display
            if displayed_count >= max_to_show:
                break
                
            displayed_count += 1
            
            # Get count of outlinks (fewer is better)
            outlink_count = get_domain_outlink_count(domain)
            
            # Lower means higher quality (fewer outlinks)
            authority_score = min(10, max(1, 10 - int(outlink_count / 100)))
            
            domains_with_outlinks.append((
                domain,
                data,
                outlink_count,
                authority_score
            ))
        
        # Now sort based on primary sort by count, secondary by authority score
        domains_with_outlinks.sort(
            key=lambda x: (
                # First by count (descending)
                len(x[1]["targets" if domain_type == "backlinks" else "sources"]),
                # Then by authority score (descending)
                x[3],
                # Then by outlink count (ascending)
                -x[2],
                # Finally alphabetical
                x[0]
            ),
            reverse=True
        )
        
        # Display the results
        if not domains_with_outlinks:
            print(f"No {domain_type} found")
            return
            
        # Print header
        print(f"{'Domain':<40} {'Count':<5} {'Authority':<8} {'Outlinks':<8} {'Details'}")
        print("-" * 100)
            
        for domain, data, outlink_count, authority_score in domains_with_outlinks:
            items = data["targets" if domain_type == "backlinks" else "sources"]
            count = len(items)
            
            # Generate stars for authority (★☆)
            stars = "★" * authority_score + "☆" * (10 - authority_score)
            
            # Format outlink count
            if outlink_count >= 999999:
                outlink_str = "Unknown"
            else:
                outlink_str = f"{outlink_count:,}"
                
            # Format details
            details = ", ".join(items[:3])
            if len(items) > 3:
                details += f", and {len(items) - 3} more"
                
            print(f"{domain:<40} {count:<5} {stars:<10} {outlink_str:<8} {details}")
    
    else:
        # Simple display without outlink analysis
        if not sorted_domains:
            print(f"No {domain_type} found")
            return
            
        for domain, data in sorted_domains:
            if displayed_count >= max_to_show:
                break
                
            displayed_count += 1
            
            items = data["targets" if domain_type == "backlinks" else "sources"]
            count = len(items)
            items_str = ", ".join(items)
            
            if domain_type == "backlinks":
                print(f"{domain} → links to {count} input domains: {items_str}")
            else:
                print(f"{domain} ← linked by {count} input domains: {items_str}")
                
    # Display message if we hit the limit
    if displayed_count == max_to_show and len(sorted_domains) > max_to_show:
        print(f"\nShowing top {max_to_show} results out of {len(sorted_domains)} found.")
        print(f"Use --max-results parameter to see more.")

def get_backlinks_with_anchors(domain: str, limit: int = 100) -> Dict[str, List[Dict]]:
    """
    Get backlinks with anchor text information for a target domain.
    
    Parameters:
    - domain: Target domain to analyze
    - limit: Maximum number of backlinks to fetch
    
    Returns a dictionary with referring domains as keys and lists of anchor text data as values.
    """
    backlinks_with_anchors = {}
    
    # Check if domain exists in Ahrefs
    check_params = {
        "token": AHREFS_API_TOKEN,
        "from": "domain_rating", 
        "target": domain,
        "mode": "domain",
        "limit": 1,
        "output": "json"
    }
    
    try:
        logger.info(f"Checking if domain exists in Ahrefs database: {domain}")
        response = requests.get(API_ENDPOINT, params=check_params, headers=HEADERS)
        
        if response.status_code != 200:
            logger.error(f"Error: API returned status code {response.status_code}")
            return {}
            
        data = response.json()
        if 'error' in data:
            logger.error(f"API Error: {data['error']}")
            return {}
            
        # Get backlinks with anchor text
        params = {
            "token": AHREFS_API_TOKEN,
            "from": "backlinks",
            "target": domain,
            "mode": "domain",
            "limit": limit,
            "output": "json"
        }
        
        logger.info(f"Fetching backlinks with anchor text for: {domain}")
        response = requests.get(API_ENDPOINT, params=params, headers=HEADERS)
        
        if response.status_code != 200:
            logger.error(f"Error: API returned status code {response.status_code}")
            return {}
            
        data = response.json()
        if 'error' in data:
            logger.error(f"API Error: {data['error']}")
            return {}
        
        # Process backlinks
        links = data.get("backlinks", [])
        
        if not links:
            logger.info(f"No backlinks found for {domain}")
            return {}
            
        logger.info(f"Found {len(links)} backlinks for {domain}")
        
        # Group backlinks by referring domain
        for link in links:
            ref_domain = link.get("refdomain", "")
            anchor = link.get("anchor", "")
            url_from = link.get("url_from", "")
            
            if not ref_domain:
                continue
                
            ref_domain = ref_domain.lower()
            
            if ref_domain not in backlinks_with_anchors:
                backlinks_with_anchors[ref_domain] = []
                
            backlinks_with_anchors[ref_domain].append({
                "anchor": anchor,
                "url_from": url_from,
                "nofollow": link.get("nofollow", False),
                "text_pre": link.get("text_pre", ""),
                "text_post": link.get("text_post", "")
            })
            
    except Exception as e:
        logger.error(f"Error fetching backlinks with anchors: {e}")
    
    time.sleep(DELAY)
    return backlinks_with_anchors

def analyze_anchors(domain: str, anchor_text: str = "", limit: int = 30) -> Dict:
    """
    Get anchor texts pointing to a given domain. If anchor_text is empty, returns all anchors.
    Uses the 'anchors' endpoint of Ahrefs API which is more efficient for anchor text analysis.
    
    Parameters:
    - domain: Target domain to analyze
    - anchor_text: Optional text to filter anchors 
    - limit: Maximum number of results to return
    
    Returns dictionary with anchor data.
    """
    # Check if domain exists in Ahrefs
    check_params = {
        "token": AHREFS_API_TOKEN,
        "from": "domain_rating", 
        "target": domain,
        "mode": "domain",
        "limit": 1,
        "output": "json"
    }
    
    try:
        logger.info(f"Checking if domain exists in Ahrefs database: {domain}")
        response = requests.get(API_ENDPOINT, params=check_params, headers=HEADERS)
        
        if response.status_code != 200:
            logger.error(f"Error: API returned status code {response.status_code}")
            logger.error(f"Response: {response.text}")
            return {'error': f"API error: {response.status_code}"}
            
        data = response.json()
        if 'error' in data:
            logger.error(f"API Error: {data['error']}")
            return {'error': data['error']}
        
        # First try the anchors endpoint
        logger.info(f"Trying anchors endpoint for: {domain}")
        params = {
            "token": AHREFS_API_TOKEN,
            "from": "anchors",
            "target": domain,
            "mode": "domain",
            "limit": limit * 2,  # Request more to ensure we get enough results after filtering
            "order_by": "backlinks:desc",
            "output": "json"
        }
        
        response = requests.get(API_ENDPOINT, params=params, headers=HEADERS)
        
        if response.status_code != 200:
            logger.error(f"Error with anchors endpoint: {response.status_code}")
            logger.error(f"Response: {response.text}")
        else:
            data = response.json()
            if not 'error' in data and 'anchors' in data and data['anchors']:
                # Successful response with data
                logger.info(f"Found {len(data['anchors'])} anchors using anchors endpoint")
                
                # Filter results if anchor_text is provided
                if anchor_text:
                    anchor_text_lower = anchor_text.lower()
                    filtered_anchors = [
                        anchor for anchor in data['anchors']
                        if anchor_text_lower in anchor.get('anchor', '').lower()
                    ]
                    logger.info(f"Filtered to {len(filtered_anchors)} anchors matching '{anchor_text}'")
                    return {
                        'anchors': filtered_anchors,
                        'total_found': len(filtered_anchors)
                    }
                
                return {
                    'anchors': data['anchors'],
                    'total_found': len(data['anchors'])
                }
        
        # If we reach here, the anchors endpoint didn't work, try backlinks endpoint
        logger.info(f"Trying backlinks endpoint for: {domain}")
        params = {
            "token": AHREFS_API_TOKEN,
            "from": "backlinks",
            "target": domain,
            "mode": "domain",
            "limit": limit * 2,  # Request more to ensure we get enough
            "output": "json"
        }
        
        response = requests.get(API_ENDPOINT, params=params, headers=HEADERS)
        
        if response.status_code != 200:
            logger.error(f"Error with backlinks endpoint: {response.status_code}")
            logger.error(f"Response: {response.text}")
            return {'error': f"Failed to fetch data from both endpoints"}
            
        data = response.json()
        if 'error' in data:
            logger.error(f"API Error with backlinks endpoint: {data['error']}")
            return {'error': data['error']}
        
        if 'backlinks' not in data or not data['backlinks']:
            logger.info(f"No backlinks found for {domain}")
            return {'anchors': [], 'total_found': 0}
            
        # Extract anchor texts from backlinks
        logger.info(f"Found {len(data['backlinks'])} backlinks, extracting anchors")
        anchor_dict = {}  # Use dict to deduplicate
        
        for link in data['backlinks']:
            anchor = link.get('anchor', '')
            if not anchor or anchor.strip() == '':
                continue
                
            # Skip if anchor doesn't contain search term
            if anchor_text and anchor_text.lower() not in anchor.lower():
                continue
                
            # Count backlinks per anchor
            if anchor not in anchor_dict:
                anchor_dict[anchor] = {
                    'anchor': anchor,
                    'backlinks': 1,
                    'refdomains': set([link.get('refdomain', '')]),
                    'first_seen': link.get('first_seen', ''),
                }
            else:
                anchor_dict[anchor]['backlinks'] += 1
                anchor_dict[anchor]['refdomains'].add(link.get('refdomain', ''))
        
        # Convert to list format like the anchors endpoint
        anchors_list = []
        for anchor_data in anchor_dict.values():
            anchors_list.append({
                'anchor': anchor_data['anchor'],
                'backlinks': anchor_data['backlinks'],
                'refdomains': len(anchor_data['refdomains']),
                'first_seen': anchor_data['first_seen'],
            })
        
        # Sort by number of backlinks (descending)
        anchors_list.sort(key=lambda x: x['backlinks'], reverse=True)
        
        logger.info(f"Extracted {len(anchors_list)} unique anchors from backlinks")
        return {
            'anchors': anchors_list[:limit],  # Limit results
            'total_found': len(anchors_list)
        }
            
    except Exception as e:
        logger.error(f"Error analyzing anchors: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {'error': str(e)}
    
    finally:
        time.sleep(DELAY)

def search_anchor_texts(domains: List[str], search_term: str = None, max_links: int = 100) -> Dict[str, Dict]:
    """
    Search for anchor texts across multiple domains.
    
    Parameters:
    - domains: List of domains to search
    - search_term: Optional term to search for in anchor texts
    - max_links: Maximum backlinks to fetch per domain
    
    Returns: Dictionary of results grouped by domain
    """
    results = {}
    search_term_lower = search_term.lower() if search_term else None
    
    for domain in domains:
        logger.info(f"Searching anchor texts for domain: {domain}")
        
        # Always try the dedicated analyze_anchors function first
        # This will automatically try both 'anchors' and 'backlinks' endpoints
        anchor_data = analyze_anchors(domain, search_term_lower, max_links)
        
        if 'error' in anchor_data:
            logger.error(f"Error searching anchor texts for {domain}: {anchor_data['error']}")
            # Try fallback to get_backlinks_with_anchors as a last resort
            if not search_term_lower:
                logger.info(f"Trying fallback method for {domain}")
                domain_backlinks = get_backlinks_with_anchors(domain, max_links)
                
                if domain_backlinks:
                    results[domain] = domain_backlinks
                    logger.info(f"Fallback successful, found {len(domain_backlinks)} referring domains")
            continue
        
        # Process successful results from analyze_anchors
        anchor_links = anchor_data.get('anchors', [])
        if not anchor_links:
            logger.info(f"No matching anchor texts found for {domain}")
            continue
            
        logger.info(f"Found {len(anchor_links)} anchors for {domain}")
        
        # Store in the results dictionary
        results[domain] = {
            "all_anchors": {
                "anchors": anchor_links,
                "total_found": anchor_data.get('total_found', len(anchor_links))
            }
        }
    
    return results

def _format_date(date_str: str) -> str:
    """Format date string from API response."""
    if not date_str:
        return 'N/A'
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime('%d %B %Y')
    except Exception as e:
        return date_str

def display_anchor_results(results: Dict[str, Dict], search_term: str = None):
    """Display the results of an anchor text search."""
    if not results:
        print("No anchor text results found.")
        return
        
    title = "ANCHOR TEXT ANALYSIS"
    if search_term:
        title += f" - Search term: '{search_term}'"
    
    print(f"\n{title}")
    print("=" * 80)
    
    total_domains = len(results)
    
    # Calculate totals differently based on result format
    total_refs = 0
    total_links = 0
    
    for domain, data in results.items():
        if "all_anchors" in data:
            # Results from anchors endpoint
            anchors = data["all_anchors"].get("anchors", [])
            total_links += len(anchors)
            # Referring domains count is in each anchor item
            for anchor in anchors:
                total_refs += anchor.get("refdomains", 0)
        else:
            # Results from backlinks endpoint
            total_refs += len(data)
            total_links += sum(len(links) for links in data.values())
    
    print(f"Total domains: {total_domains}")
    print(f"Total referring domains: {total_refs}")
    print(f"Total backlinks/anchors: {total_links}")
    print("-" * 80)
    
    # Display detailed results
    for domain, data in results.items():
        print(f"\nTarget Domain: {domain}")
        
        if "all_anchors" in data:
            # Display results from anchors endpoint
            anchors = data["all_anchors"].get("anchors", [])
            print(f"Found {len(anchors)} matching anchor texts")
            
            for i, anchor in enumerate(anchors, 1):
                anchor_text = anchor.get("anchor", "N/A")
                backlinks = anchor.get("backlinks", 0)
                refdomains = anchor.get("refdomains", 0)
                first_seen = _format_date(anchor.get("first_seen", ""))
                
                print(f"\n  {i}. Anchor: \"{anchor_text}\"")
                print(f"     Backlinks: {backlinks:,}")
                print(f"     Referring Domains: {refdomains:,}")
                if first_seen:
                    print(f"     First Seen: {first_seen}")
        else:
            # Display results from backlinks endpoint
            print(f"Found {len(data)} referring domains with relevant anchor text")
            
            # For each referring domain
            for ref_domain, links in data.items():
                print(f"\n  Referring Domain: {ref_domain}")
                print(f"  Links found: {len(links)}")
                
                # Group by anchor text to avoid repetition
                anchors = {}
                for link in links:
                    anchor = link["anchor"]
                    if anchor not in anchors:
                        anchors[anchor] = []
                    anchors[anchor].append(link)
                
                # Display each unique anchor text
                for anchor, anchor_links in anchors.items():
                    print(f"    Anchor: \"{anchor}\" (used {len(anchor_links)} times)")
                    
                    # Show an example of the context for the first occurrence
                    if len(anchor_links) > 0:
                        example = anchor_links[0]
                        pre_text = example["text_pre"].strip()
                        post_text = example["text_post"].strip()
                        
                        if pre_text or post_text:
                            context = f"{pre_text} [LINK] {post_text}"
                            # Truncate if too long
                            if len(context) > 100:
                                context = context[:97] + "..."
                            print(f"      Context: {context}")
        
        print("-" * 80)

def main():
    parser = argparse.ArgumentParser(description='Analyze domain link patterns using Ahrefs API')
    parser.add_argument('domains', nargs='+', help='One or more domains to analyze (REQUIRED)')
    parser.add_argument('--similar', action='store_true', help='Find domains with similar backlink profiles')
    parser.add_argument('--colinked', action='store_true', help='Find domains co-linked with target domain')
    parser.add_argument('--twice-removed', action='store_true', help='Find backlinks of your backlinks')
    parser.add_argument('--compare', action='store_true', help='Compare domains for common backlinks and outlinks')
    parser.add_argument('--anchors', action='store_true', help='Search for anchor texts in backlinks')
    parser.add_argument('--anchor-term', type=str, help='Search term for anchor text search')
    parser.add_argument('--min-shared', type=int, default=3, help='Minimum number of shared backlinks (default: 3)')
    parser.add_argument('--max-links', type=int, default=100, help='Maximum number of links to analyze per domain (default: 100)')
    parser.add_argument('--max-backlinks', type=int, default=10, help='Maximum number of backlink sources to analyze (default: 10)')
    parser.add_argument('--max-second-level', type=int, default=5, help='Maximum number of second-level domains per first-level domain (default: 5)')
    parser.add_argument('--no-filter', action='store_true', help='Disable filtering of backlisted domains')
    parser.add_argument('--max-results', type=int, default=50, help='Maximum number of results to show (default: 50)')
    parser.add_argument('--simple', action='store_true', help='Skip detailed outlink analysis for faster results')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()
    
    # Set logging level based on debug flag
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # Get domains from arguments
    domains = args.domains
    
    # Check for special domain suffix for anchor search (domain?)
    use_anchor_search = False
    domain_for_anchor = None
    default_anchor_term = None
    
    # Check if any domain ends with ? to trigger anchor search
    for i, domain in enumerate(domains):
        if domain.endswith('?'):
            use_anchor_search = True
            domain_for_anchor = domain.rstrip('?')
            # Use first part of domain as search term if it's a common domain format
            parts = domain_for_anchor.split('.')
            if len(parts) >= 2:
                default_anchor_term = parts[0]  # Use first part (e.g., 'sastrec' from 'sastreconsulting.com')
                # Special case for domains with 'www'
                if default_anchor_term == 'www' and len(parts) >= 3:
                    default_anchor_term = parts[1]  # Use second part for www.domain.com
            else:
                default_anchor_term = domain_for_anchor  # Just use the whole thing
                
            domains[i] = domain_for_anchor  # Update the domain without ?
            
            # Log what we're doing
            logger.info(f"Detected domain? syntax: {domain}")
            logger.info(f"Using domain: {domain_for_anchor}")
            logger.info(f"Default anchor term: {default_anchor_term}")
            break
    
    # If ? suffix was found, override other modes
    if use_anchor_search:
        args.anchors = True
        if not args.anchor_term:
            args.anchor_term = default_anchor_term
            logger.info(f"Using default anchor term: {args.anchor_term}")
        else:
            logger.info(f"Using provided anchor term: {args.anchor_term}")
    
    # Run in "anchor text search" mode
    if args.anchors:
        print(f"Searching for anchor texts across {len(domains)} domains:")
        for i, domain in enumerate(domains, 1):
            print(f"{i}. {domain}")
        
        if args.anchor_term:
            print(f"Searching for term: '{args.anchor_term}'")
        else:
            print("No search term specified - showing all anchor texts")
            
        print(f"Max links per domain: {args.max_links}")
        print("=" * 50)
        
        # Perform the anchor text search
        results = search_anchor_texts(domains, args.anchor_term, args.max_links)
        
        # Display the results
        display_anchor_results(results, args.anchor_term)
    
    # Run in "compare domains" mode
    elif args.compare:
        if len(domains) < 2:
            print("Error: You must provide at least two domains with the --compare flag")
            sys.exit(1)
            
        print(f"Comparing {len(domains)} domains for common backlinks and outbound links:")
        for i, domain in enumerate(domains, 1):
            print(f"{i}. {domain}")
        print(f"Max links per domain: {args.max_links}")
        if not args.no_filter:
            print("Domain filtering: ENABLED (use --no-filter to disable)")
        else:
            print("Domain filtering: DISABLED")
        print("=" * 50)
        
        results = compare_domains(domains, args.max_links, not args.no_filter)
        
        # Display common backlinks results
        display_domain_rankings(
            results["common_backlinks"], 
            "COMMON BACKLINKS (domains that link to multiple input domains)", 
            "backlinks",
            args.max_results,
            not args.simple
        )
        
        # Display common outlinks results
        display_domain_rankings(
            results["common_outlinks"], 
            "COMMON OUTBOUND LINKS (domains that are linked to by multiple input domains)", 
            "outlinks",
            args.max_results,
            not args.simple
        )
    
    # Run in "colinked domains" mode
    elif args.colinked:
        if len(domains) != 1:
            print("Error: You must provide exactly one domain with the --colinked flag")
            sys.exit(1)
            
        target = domains[0]
        print(f"Finding domains that are co-linked with: {target}")
        print(f"This will identify domains that sites linking to {target} also link to")
        print(f"Max links per domain: {args.max_links}, Max backlink sources: {args.max_backlinks}")
        print("=" * 50)
        
        colinked_results = find_colinked_domains(target, args.max_links, args.max_backlinks)
        
        # Convert to format compatible with display_domain_rankings
        formatted_results = {}
        for domain, data in colinked_results.items():
            formatted_results[domain] = {
                "sources": data["referrers"],
                "count": data["count"]
            }
        
        display_domain_rankings(
            formatted_results,
            f"Domains co-linked with {target}",
            "outlinks",
            args.max_results,
            not args.simple
        )
    
    # Run in "backlinks twice removed" mode
    elif args.twice_removed:
        if len(domains) != 1:
            print("Error: You must provide exactly one domain with the --twice-removed flag")
            sys.exit(1)
            
        target = domains[0]
        print(f"Finding backlinks twice removed for: {target}")
        print(f"This will identify domains that link to sites which link to {target}")
        print(f"Max links: {args.max_links}, Level 1 domains: {args.max_backlinks}, Level 2 per domain: {args.max_second_level}")
        print("=" * 50)
        
        twice_removed = find_backlinks_twice_removed(
            target, 
            args.max_links, 
            args.max_backlinks, 
            args.max_second_level
        )
        
        # Convert to format compatible with display_domain_rankings
        formatted_results = {}
        for domain, data in twice_removed.items():
            formatted_results[domain] = {
                "sources": data["paths"],
                "count": data["count"]
            }
        
        display_domain_rankings(
            formatted_results,
            f"Backlinks twice removed for {target}",
            "backlinks",
            args.max_results,
            not args.simple
        )
    
    # Run in "similar backlink profiles" mode
    elif args.similar:
        if len(domains) != 1:
            print("Error: You must provide exactly one domain with the --similar flag")
            sys.exit(1)
            
        target = domains[0]
        print(f"Finding domains with similar backlink profiles to: {target}")
        print(f"This will identify domains receiving links from the same sources as {target}")
        print(f"Max links per domain: {args.max_links}, Max backlink sources: {args.max_backlinks}")
        print("=" * 50)
        
        similar_domains = find_similar_backlink_profiles(target, args.min_shared, args.max_links, args.max_backlinks)
        
        # Convert to format compatible with display_domain_rankings
        formatted_results = {}
        for domain, data in similar_domains.items():
            formatted_results[domain] = {
                "sources": data["shared_referrers"],
                "count": data["count"]
            }
        
        display_domain_rankings(
            formatted_results,
            f"Domains with similar backlink profiles to {target}",
            "outlinks",
            args.max_results,
            not args.simple
        )
    
    # Otherwise, run in traditional "common outbound links" mode 
    else:
        print(f"Analyzing common outbound links across {len(domains)} domains:")
        print(f"Max links per domain: {args.max_links}")
        for i, domain in enumerate(domains, 1):
            print(f"{i}. {domain}")
        
        # Find common domains, passing the max_links parameter
        print("\n===== FINDING COMMON LINKED DOMAINS =====")
        
        # Create a dictionary to store results
        all_targets = defaultdict(lambda: {"count": 0, "referrers": []})
        
        for domain in domains:
            logger.info(f"\nAnalyzing outgoing links from: {domain}")
            target_domains = get_linked_domains(domain, max_links=args.max_links)
            
            for target in target_domains:
                all_targets[target]["count"] += 1
                all_targets[target]["referrers"].append(domain)
        
        # Convert to format compatible with display_domain_rankings
        formatted_results = {}
        for domain, data in all_targets.items():
            if len(data["referrers"]) > 1:  # Only include domains linked by multiple sources
                formatted_results[domain] = {
                    "sources": data["referrers"],
                    "count": data["count"]
                }
        
        display_domain_rankings(
            formatted_results,
            "Common target domains",
            "outlinks",
            args.max_results,
            not args.simple
        )

if __name__ == "__main__":
    main() 