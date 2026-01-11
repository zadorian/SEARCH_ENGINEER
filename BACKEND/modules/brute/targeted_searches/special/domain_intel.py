#!/usr/bin/env python3
"""
Domain Intelligence Search - Comprehensive domain analysis tools
Provides IP address, DNS, Leaks, and miscellaneous domain intelligence
"""

from typing import List, Dict, Optional
from urllib.parse import quote, urlparse
import logging

logger = logging.getLogger(__name__)


def clean_domain(query: str) -> str:
    """Extract clean domain from various input formats"""
    # Remove common prefixes
    if query.startswith('domain:'):
        query = query[7:].strip()
    if query.startswith('site:'):
        query = query[5:].strip()
    
    # Parse URL if needed
    if '://' in query:
        parsed = urlparse(query)
        domain = parsed.netloc or parsed.path
    else:
        domain = query
    
    # Clean up
    domain = domain.strip().lower()
    if domain.startswith('www.'):
        domain = domain[4:]
    
    return domain


def search(query: str) -> List[Dict]:
    """
    Main search function for domain intelligence
    Returns categorized domain analysis links
    
    Args:
        query: Domain name or URL to analyze
        
    Returns:
        List of categorized domain intelligence service URLs
    """
    domain = clean_domain(query)
    encoded_domain = quote(domain)
    
    results = []
    
    # === IP ADDRESS TAB ===
    results.extend(get_ip_searches(domain, encoded_domain))
    
    # === DNS TAB ===
    results.extend(get_dns_searches(domain, encoded_domain))
    
    # === LEAKS TAB ===
    results.extend(get_leak_searches(domain, encoded_domain))
    
    # === MISCELLANEOUS TAB ===
    results.extend(get_misc_searches(domain, encoded_domain))
    
    return results


def get_ip_searches(domain: str, encoded_domain: str) -> List[Dict]:
    """Get IP address related searches"""
    return [
        # === IP ADDRESS & REVERSE IP ===
        {
            'title': f'SecurityTrails IP/DNS: {domain}',
            'url': f'https://securitytrails.com/domain/{domain}/dns',
            'category': 'ip_address',
            'source': 'securitytrails',
            'description': 'IP history, DNS records, subdomains'
        },
        {
            'title': f'ViewDNS Reverse IP: {domain}',
            'url': f'https://viewdns.info/reverseip/?host={domain}&t=1',
            'category': 'ip_address',
            'source': 'viewdns',
            'description': 'Find other sites on same IP'
        },
        {
            'title': f'Shodan Search: {domain}',
            'url': f'https://www.shodan.io/search?query={encoded_domain}',
            'category': 'ip_address',
            'source': 'shodan',
            'description': 'Internet-connected devices and services'
        },
        {
            'title': f'Censys Search: {domain}',
            'url': f'https://search.censys.io/search?resource=hosts&q={encoded_domain}',
            'category': 'ip_address',
            'source': 'censys',
            'description': 'Internet hosts and certificates'
        },
        {
            'title': f'IPInfo: {domain}',
            'url': f'https://ipinfo.io/{domain}',
            'category': 'ip_address',
            'source': 'ipinfo',
            'description': 'IP geolocation and network info'
        },
        {
            'title': f'BGPView: {domain}',
            'url': f'https://bgpview.io/search?query={encoded_domain}',
            'category': 'ip_address',
            'source': 'bgpview',
            'description': 'BGP routing and ASN information'
        },
    ]


def get_dns_searches(domain: str, encoded_domain: str) -> List[Dict]:
    """Get DNS related searches"""
    return [
        # === DNS RECORDS & HISTORY ===
        {
            'title': f'DNSDumpster: {domain}',
            'url': f'https://dnsdumpster.com/',
            'category': 'dns',
            'source': 'dnsdumpster',
            'description': 'DNS recon & research (manual search required)'
        },
        {
            'title': f'ViewDNS DNS Records: {domain}',
            'url': f'https://viewdns.info/dnsrecord/?domain={domain}',
            'category': 'dns',
            'source': 'viewdns',
            'description': 'All DNS records for domain'
        },
        {
            'title': f'DNS History: {domain}',
            'url': f'https://viewdns.info/dnshistory/?domain={domain}',
            'category': 'dns',
            'source': 'viewdns',
            'description': 'Historical DNS records'
        },
        {
            'title': f'MXToolbox DNS: {domain}',
            'url': f'https://mxtoolbox.com/SuperTool.aspx?action=a%3a{domain}&run=toolpage',
            'category': 'dns',
            'source': 'mxtoolbox',
            'description': 'DNS lookup and diagnostics'
        },
        {
            'title': f'DNS Checker: {domain}',
            'url': f'https://dnschecker.org/all-dns-records-of-domain.php?query={domain}&rtype=ALL',
            'category': 'dns',
            'source': 'dnschecker',
            'description': 'Global DNS propagation check'
        },
        {
            'title': f'Subdomain Finder: {domain}',
            'url': f'https://subdomainfinder.c99.nl/scans/new?domain={domain}',
            'category': 'dns',
            'source': 'c99',
            'description': 'Subdomain enumeration'
        },
        {
            'title': f'crt.sh SSL Certs: {domain}',
            'url': f'https://crt.sh/?q={encoded_domain}',
            'category': 'dns',
            'source': 'crtsh',
            'description': 'Certificate transparency logs'
        },
    ]


def get_leak_searches(domain: str, encoded_domain: str) -> List[Dict]:
    """Get data leak and breach searches"""
    return [
        # === LEAKS & BREACHES ===
        {
            'title': f'LeakIX: {domain}',
            'url': f'https://leakix.net/search?q={encoded_domain}',
            'category': 'leaks',
            'source': 'leakix',
            'description': 'Leaked databases and configs'
        },
        {
            'title': f'DeHashed: {domain}',
            'url': f'https://dehashed.com/search?query={encoded_domain}',
            'category': 'leaks',
            'source': 'dehashed',
            'description': 'Breach database search'
        },
        {
            'title': f'Have I Been Pwned Domain: {domain}',
            'url': f'https://haveibeenpwned.com/DomainSearch?domain={domain}',
            'category': 'leaks',
            'source': 'haveibeenpwned',
            'description': 'Domain breach search'
        },
        {
            'title': f'IntelX: {domain}',
            'url': f'https://intelx.io/?s={encoded_domain}',
            'category': 'leaks',
            'source': 'intelx',
            'description': 'OSINT archive search'
        },
        {
            'title': f'Snusbase: {domain}',
            'url': f'https://snusbase.com/search?q={encoded_domain}',
            'category': 'leaks',
            'source': 'snusbase',
            'description': 'Leaked database search'
        },
        {
            'title': f'LeakCheck: {domain}',
            'url': f'https://leakcheck.io/domain/{domain}',
            'category': 'leaks',
            'source': 'leakcheck',
            'description': 'Data breach search'
        },
        {
            'title': f'GhostProject: {domain}',
            'url': f'https://ghostproject.fr/search/{encoded_domain}',
            'category': 'leaks',
            'source': 'ghostproject',
            'description': 'Leaked credentials search'
        },
    ]


def get_misc_searches(domain: str, encoded_domain: str) -> List[Dict]:
    """Get miscellaneous domain intelligence searches"""
    return [
        # === MISCELLANEOUS ===
        {
            'title': f'WHOIS Lookup: {domain}',
            'url': f'https://whois.domaintools.com/{domain}',
            'category': 'miscellaneous',
            'source': 'domaintools',
            'description': 'Domain registration info'
        },
        {
            'title': f'BuiltWith: {domain}',
            'url': f'https://builtwith.com/{domain}',
            'category': 'miscellaneous',
            'source': 'builtwith',
            'description': 'Technology stack analysis'
        },
        {
            'title': f'Wayback Machine: {domain}',
            'url': f'https://web.archive.org/web/*/{domain}',
            'category': 'miscellaneous',
            'source': 'archive',
            'description': 'Historical snapshots'
        },
        {
            'title': f'URLVoid: {domain}',
            'url': f'https://www.urlvoid.com/scan/{domain}',
            'category': 'miscellaneous',
            'source': 'urlvoid',
            'description': 'Website reputation check'
        },
        {
            'title': f'VirusTotal: {domain}',
            'url': f'https://www.virustotal.com/gui/domain/{domain}',
            'category': 'miscellaneous',
            'source': 'virustotal',
            'description': 'Malware and security analysis'
        },
        {
            'title': f'Spyse: {domain}',
            'url': f'https://spyse.com/target/domain/{domain}',
            'category': 'miscellaneous',
            'source': 'spyse',
            'description': 'Cyber threat intelligence'
        },
        {
            'title': f'Hunter.io: {domain}',
            'url': f'https://hunter.io/search/{domain}',
            'category': 'miscellaneous',
            'source': 'hunter',
            'description': 'Email finder for domain'
        },
        {
            'title': f'Netcraft: {domain}',
            'url': f'https://sitereport.netcraft.com/?url={domain}',
            'category': 'miscellaneous',
            'source': 'netcraft',
            'description': 'Site technology report'
        },
        {
            'title': f'RiskIQ: {domain}',
            'url': f'https://community.riskiq.com/search/{domain}',
            'category': 'miscellaneous',
            'source': 'riskiq',
            'description': 'Digital footprint'
        },
        {
            'title': f'PublicWWW: {domain}',
            'url': f'https://publicwww.com/websites/{encoded_domain}/',
            'category': 'miscellaneous',
            'source': 'publicwww',
            'description': 'Source code search'
        },
    ]


def search_by_category(query: str, category: str) -> List[Dict]:
    """
    Search specific category of domain intelligence
    
    Args:
        query: Domain to search
        category: One of 'ip_address', 'dns', 'leaks', 'miscellaneous'
        
    Returns:
        List of URLs for the specified category
    """
    domain = clean_domain(query)
    encoded_domain = quote(domain)
    
    if category == 'ip_address':
        return get_ip_searches(domain, encoded_domain)
    elif category == 'dns':
        return get_dns_searches(domain, encoded_domain)
    elif category == 'leaks':
        return get_leak_searches(domain, encoded_domain)
    elif category == 'miscellaneous':
        return get_misc_searches(domain, encoded_domain)
    else:
        # Return all if category not specified
        return search(query)


def main():
    """Main entry point for domain intelligence search - compatible with SearchRouter"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Domain intelligence search')
    parser.add_argument('-q', '--query', required=True, help='Domain to investigate')
    args = parser.parse_args()
    
    query = args.query
    
    # Extract clean domain
    if ':' in query:
        domain = query.split(':', 1)[1].strip()
    else:
        domain = query
    
    print(f"\n🔍 Domain Intelligence: {domain}")
    
    # Use the search function
    results = search(domain)
    
    if results:
        print(f"\nGenerated {len(results)} domain intelligence searches:")
        for i, result in enumerate(results[:30], 1):
            print(f"\n{i}. {result.get('title', 'No Title')}")
            print(f"   URL: {result.get('url')}")
    else:
        print("\nNo domain intelligence results generated.")
    
    return results