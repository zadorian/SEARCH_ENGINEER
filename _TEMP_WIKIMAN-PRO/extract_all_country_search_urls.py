#!/usr/bin/env python3
"""
Extract ALL Search URLs from Country Files
==========================================
Extracts search URLs from hungary.json, romania.md, and other country files.
Combines with existing search URLs for a master database.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Set
from collections import defaultdict

def extract_hungary_urls():
    """Extract URLs from hungary.json."""
    urls = {}
    hungary_file = Path('Search_Types/corporate/Country_Search/hungary.json')
    
    if hungary_file.exists():
        with open(hungary_file, 'r') as f:
            data = json.load(f)
        
        # Process each category
        for category, entries in data.items():
            for entry in entries:
                if 'url' in entry and 'name' in entry:
                    domain = entry['name']
                    url_template = entry['url']
                    # Convert numbered placeholders to {query}
                    url_template = re.sub(r'\{[0-9]\}', '{query}', url_template)
                    urls[domain] = url_template
    
    return urls

def extract_markdown_urls(file_path: Path) -> Dict[str, str]:
    """Extract URLs from markdown country files."""
    urls = {}
    
    if not file_path.exists():
        return urls
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern to match markdown links [text](url)
    link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    matches = re.findall(link_pattern, content)
    
    for text, url in matches:
        # Clean up the URL
        url = url.strip()
        
        # Skip if it's not a real URL
        if not url.startswith('http'):
            continue
        
        # Extract domain
        domain_match = re.match(r'https?://([^/]+)', url)
        if domain_match:
            domain = domain_match.group(1)
            
            # Check if URL has search parameters
            if any(param in url.lower() for param in ['search', 'query', 'q=', 'keyword', 'find']):
                # This might be a search URL
                # Try to identify the query parameter
                if '=' in url:
                    # Replace common search parameter values with {query}
                    url_template = re.sub(r'(q|query|search|keyword|find)=[^&]*', r'\1={query}', url)
                    urls[domain] = url_template
                else:
                    # Just add the base search URL
                    urls[domain] = url + '?q={query}'
            elif not urls.get(domain):
                # Store base URL for later processing
                urls[domain] = url
    
    return urls

def extract_all_country_urls():
    """Extract all URLs from country search files."""
    all_urls = {}
    
    # Extract from hungary.json
    hungary_urls = extract_hungary_urls()
    all_urls.update(hungary_urls)
    print(f"Extracted {len(hungary_urls)} URLs from hungary.json")
    
    # Extract from markdown files
    country_dir = Path('Search_Types/corporate/Country_Search')
    md_files = ['ro.md', 'ee.md', 'si.md', 'sk.md']
    
    for md_file in md_files:
        file_path = country_dir / md_file
        if file_path.exists():
            country_urls = extract_markdown_urls(file_path)
            all_urls.update(country_urls)
            print(f"Extracted {len(country_urls)} URLs from {md_file}")
    
    return all_urls

def combine_all_search_urls():
    """Combine all search URLs from various sources."""
    
    # Load existing search URLs
    existing_urls = {}
    urls_file = Path('wiki_integration/data/all_search_urls.json')
    if urls_file.exists():
        with open(urls_file, 'r') as f:
            data = json.load(f)
            existing_urls = data.get('direct_search_urls', {})
    
    print(f"Loaded {len(existing_urls)} existing URLs")
    
    # Extract country-specific URLs
    country_urls = extract_all_country_urls()
    print(f"Extracted {len(country_urls)} country-specific URLs")
    
    # Additional manual entries from the files
    manual_urls = {
        # Romanian registries
        'portal.onrc.ro': 'https://portal.onrc.ro/ONRCPortalWeb/appmanager/myONRC/public?q={query}',
        'www.risco.ro': 'https://www.risco.ro/cautare?q={query}',
        'portal.just.ro': 'https://portal.just.ro/SitePages/cautare.aspx?k={query}',
        'www.bpi.ro': 'https://www.bpi.ro/cautare?q={query}',
        
        # Estonian registries
        'ariregister.rik.ee': 'https://ariregister.rik.ee/eng/company?search_name={query}',
        'www.rik.ee': 'https://www.rik.ee/en/e-land-register/search?q={query}',
        
        # Slovenian registries
        'www.ajpes.si': 'https://www.ajpes.si/prs/podjetje.asp?s=1&e={query}',
        'www.sodisce.si': 'https://www.sodisce.si/javne_objave/iskanje/?q={query}',
        
        # Slovak registries
        'www.orsr.sk': 'https://www.orsr.sk/hladaj_osoba.asp?MENO={query}',
        'www.registeruz.sk': 'https://www.registeruz.sk/cruz-public/domain/search/search?q={query}',
        
        # Hungarian registries (formatted)
        'e-cegjegyzek.hu': 'https://www.e-cegjegyzek.hu/?cegadatlap/{query}',
        'opten.hu': 'https://webshop.opten.hu/product/search/{query}',
        'k-monitor.hu': 'https://adatbazis.k-monitor.hu/adatbazis/cimkek/{query}',
        'kozbeszerzes.hu': 'https://www.kozbeszerzes.hu/adatbazis/megtekint/hirdetmeny/ehr-{query}/',
        'ekr.gov.hu': 'https://ekr.gov.hu/portal/ajanlatkero/ajanlatkero-nyilvantartas/{query}/reszletek',
        'birosag.hu': 'https://birosag.hu/kereses?kulcsszo={query}',
        'nav.gov.hu': 'https://nav.gov.hu/kereso?query={query}',
        'mnb.hu': 'https://intezmenykereso.mnb.hu/Details/Index?search={query}',
        
        # European registries
        'e-justice.europa.eu': 'https://e-justice.europa.eu/content_find_a_company-489-en.do?search={query}',
        'www.ebrd.com': 'https://www.ebrd.com/work-with-us/project-finance/project-summary-documents.html?q={query}',
        
        # Global business databases
        'www.dnb.com': 'https://www.dnb.com/business-directory/company-search.html?term={query}',
        'www.kompass.com': 'https://www.kompass.com/searchCompanies?text={query}',
        'www.europages.com': 'https://www.europages.com/en/search-results?what={query}',
        
        # Sanctions and compliance
        'sanctionssearch.ofac.treas.gov': 'https://sanctionssearch.ofac.treas.gov/Details.aspx?id={query}',
        'www.worldbank.org': 'https://www.worldbank.org/en/projects-operations/procurement/debarred-firms?q={query}',
        
        # Offshore and leaks databases
        'offshoreleaks.icij.org': 'https://offshoreleaks.icij.org/search?q={query}',
        'www.occrp.org': 'https://www.occrp.org/en/search?q={query}',
        'aleph.occrp.org': 'https://aleph.occrp.org/search?q={query}',
        
        # Patent and trademark (international)
        'www.tmdn.org': 'https://www.tmdn.org/tmview/welcome?q={query}',
        'euipo.europa.eu': 'https://euipo.europa.eu/eSearch/#advanced/trademarks/1/50/n1={query}',
        
        # Court databases
        'curia.europa.eu': 'https://curia.europa.eu/juris/recherche.jsf?text={query}',
        'www.icc-cpi.int': 'https://www.icc-cpi.int/Pages/search.aspx?k={query}',
        
        # Financial/stock exchanges
        'www.londonstockexchange.com': 'https://www.londonstockexchange.com/search?q={query}',
        'www.euronext.com': 'https://www.euronext.com/en/search_instruments/{query}',
        'www.deutsche-boerse.com': 'https://www.deutsche-boerse.com/dbg-en/search?query={query}',
        'www.six-group.com': 'https://www.six-group.com/en/search.html?q={query}',
        
        # Additional national registries
        'www.kvk.nl': 'https://www.kvk.nl/zoeken/?q={query}',  # Netherlands
        'www.unternehmensregister.de': 'https://www.unternehmensregister.de/ureg/search1.2.html?submitAction=searchList&searchWord={query}',  # Germany
        'www.societe.com': 'https://www.societe.com/cgi-bin/search?champs={query}',  # France
        'www.registroimprese.it': 'https://www.registroimprese.it/en/web/guest/ricerca-impresa?p_p_id=ricercaimpresa&_ricercaimpresa_search={query}',  # Italy
        'www.rbe.es': 'https://www.rbe.es/busqueda?q={query}',  # Spain
        'cvr.dk': 'https://datacvr.virk.dk/data/?q={query}',  # Denmark
        'www.ytj.fi': 'https://www.ytj.fi/en/index/businessidsearch.html?searchText={query}',  # Finland
        'www.zefix.ch': 'https://www.zefix.ch/en/search/entity/list?name={query}',  # Switzerland
        'www.rrp.bg': 'https://www.rrp.bg/en/search?q={query}',  # Bulgaria
        'www.vr.fo': 'https://www.vr.fo/en/search?q={query}',  # Faroe Islands
        'www.virk.is': 'https://www.virk.is/search?q={query}',  # Iceland
        'www.napr.gov.ge': 'https://www.napr.gov.ge/main/search?q={query}',  # Georgia
        
        # Asian registries
        'www.sgs.gov.cn': 'http://www.gsxt.gov.cn/index.html',  # China (requires special handling)
        'www.houjin-bangou.nta.go.jp': 'https://www.houjin-bangou.nta.go.jp/en/search/?q={query}',  # Japan
        'www.kap.go.kr': 'https://www.kap.go.kr/search?q={query}',  # South Korea
        'www.ssm.com.my': 'https://www.ssm.com.my/Pages/Services/Business-Entity-Search.aspx?q={query}',  # Malaysia
        'www.acra.gov.sg': 'https://www.acra.gov.sg/online-services/search?q={query}',  # Singapore
        
        # Latin American registries
        'www.rues.org.co': 'https://www.rues.org.co/RM/Search?name={query}',  # Colombia
        'www.sunarp.gob.pe': 'https://www.sunarp.gob.pe/busqueda?q={query}',  # Peru
        'www.dgii.gov.do': 'https://www.dgii.gov.do/app/WebApps/ConsultasWeb/consultas/rnc.aspx?q={query}',  # Dominican Republic
        'www.rcnacional.com.br': 'https://www.rcnacional.com.br/pesquisa?q={query}',  # Brazil
        
        # African registries
        'www.cipc.co.za': 'https://eservices.cipc.co.za/Search.aspx?q={query}',  # South Africa
        'www.ursb.go.ug': 'https://www.ursb.go.ug/search?q={query}',  # Uganda
        'www.businessregistration.go.ke': 'https://www.businessregistration.go.ke/search?q={query}',  # Kenya
        
        # Middle East registries
        'www.cr.gov.sa': 'https://www.cr.gov.sa/en/search?q={query}',  # Saudi Arabia
        'www.economy.gov.ae': 'https://www.economy.gov.ae/en/search?q={query}',  # UAE
        'www.moci.gov.qa': 'https://www.moci.gov.qa/en/search?q={query}',  # Qatar
    }
    
    # Combine all URLs
    all_urls = {**existing_urls, **country_urls, **manual_urls}
    
    # Remove duplicates and clean
    cleaned_urls = {}
    for domain, url in all_urls.items():
        # Clean domain
        domain = domain.replace('www.', '').strip()
        
        # Ensure URL has {query} placeholder
        if '{query}' not in url and 'search' in url.lower():
            # Try to add query parameter if missing
            if '?' in url:
                url += '&q={query}'
            else:
                url += '?q={query}'
        
        cleaned_urls[domain] = url
    
    # Categorize URLs
    categorized = defaultdict(list)
    
    for domain, url in cleaned_urls.items():
        # Categorize based on domain patterns
        if any(term in domain for term in ['company', 'corporate', 'business', 'registry', 'handels', 'societe']):
            categorized['company_registries'].append({'domain': domain, 'url': url})
        elif any(term in domain for term in ['court', 'justice', 'pacer', 'tribunal', 'birosag']):
            categorized['court_records'].append({'domain': domain, 'url': url})
        elif any(term in domain for term in ['patent', 'trademark', 'uspto', 'wipo', 'euipo']):
            categorized['intellectual_property'].append({'domain': domain, 'url': url})
        elif any(term in domain for term in ['sanction', 'ofac', 'compliance', 'debarred']):
            categorized['sanctions_compliance'].append({'domain': domain, 'url': url})
        elif any(term in domain for term in ['offshore', 'leak', 'icij', 'occrp']):
            categorized['offshore_leaks'].append({'domain': domain, 'url': url})
        elif any(term in domain for term in ['stock', 'exchange', 'bourse', 'nasdaq', 'nyse']):
            categorized['stock_exchanges'].append({'domain': domain, 'url': url})
        elif any(term in domain for term in ['.gov', '.gob.', '.gouv.']):
            categorized['government'].append({'domain': domain, 'url': url})
        else:
            categorized['other'].append({'domain': domain, 'url': url})
    
    # Create output
    output = {
        'metadata': {
            'total_urls': len(cleaned_urls),
            'categories': len(categorized),
            'sources': ['existing_database', 'hungary.json', 'romania.md', 'estonia.md', 'slovenia.md', 'slovakia.md', 'manual_additions']
        },
        'all_search_urls': cleaned_urls,
        'by_category': dict(categorized),
        'statistics': {
            category: len(items) for category, items in categorized.items()
        }
    }
    
    # Save comprehensive database
    output_file = Path('wiki_integration/data/master_search_urls.json')
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    # Create simple text file for easy use
    txt_file = Path('wiki_integration/data/master_search_urls.txt')
    with open(txt_file, 'w') as f:
        f.write("# MASTER SEARCH URL DATABASE\n")
        f.write(f"# Total: {len(cleaned_urls)} search URLs\n\n")
        
        for category, items in categorized.items():
            f.write(f"\n## {category.upper().replace('_', ' ')}\n")
            for item in sorted(items, key=lambda x: x['domain']):
                f.write(f"{item['url']}\n")
    
    print(f"\n{'='*60}")
    print("MASTER SEARCH URL DATABASE CREATED")
    print(f"{'='*60}")
    print(f"Total URLs: {len(cleaned_urls)}")
    print(f"\nCategories:")
    for category, count in output['statistics'].items():
        print(f"  {category}: {count}")
    print(f"\nSaved to:")
    print(f"  - {output_file}")
    print(f"  - {txt_file}")
    
    return output

if __name__ == "__main__":
    combine_all_search_urls()