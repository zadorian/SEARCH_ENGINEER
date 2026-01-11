import aiohttp
import asyncio
from datetime import datetime
import re
from typing import Dict, List, Optional
import json

# Regular expressions for analytics codes
UA_PATTERN = r'UA-\d+-\d+'
GA4_PATTERN = r'G-[A-Z0-9]{7,}'
GTM_PATTERN = r'GTM-[A-Z0-9]+'

def validate_dates(start_date: str, end_date: str) -> bool:
    """Validate that start_date is before end_date."""
    start = datetime.strptime(start_date, "%d/%m/%Y:%H:%M")
    end = datetime.strptime(end_date, "%d/%m/%Y:%H:%M")
    return start < end

def get_14_digit_timestamp(date_str: str) -> str:
    """Convert date string to 14-digit timestamp."""
    dt = datetime.strptime(date_str, "%d/%m/%Y:%H:%M")
    return dt.strftime("%Y%m%d%H%M%S")

def format_timestamp(timestamp: str) -> str:
    """Convert 14-digit timestamp to readable format."""
    try:
        dt = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
        return dt.strftime("%Y-%m-%d")
    except Exception as e:
        return timestamp

async def fetch_snapshots(session: aiohttp.ClientSession, url: str, from_date: str, to_date: Optional[str] = None) -> List[str]:
    """Fetch list of snapshots from Wayback CDX API."""
    cdx_url = f"https://web.archive.org/cdx/search/cdx"
    params = {
        'url': url,
        'output': 'json',
        'fl': 'timestamp',
        'filter': '!statuscode:[45]..', # Exclude error pages
        'from': from_date,
        'to': to_date if to_date else '',
        'collapse': 'timestamp:8' # Remove duplicates within same day
    }
    
    async with session.get(cdx_url, params=params) as response:
        data = await response.json()
        return [row[0] for row in data[1:]] if len(data) > 1 else []

async def fetch_snapshot_content(session: aiohttp.ClientSession, url: str, timestamp: str) -> str:
    """Fetch content of a specific snapshot."""
    wb_url = f"https://web.archive.org/web/{timestamp}/{url}"
    async with session.get(wb_url) as response:
        return await response.text()

async def analyze_codes(session: aiohttp.ClientSession, url: str, from_date: str, to_date: Optional[str] = None) -> Dict:
    """Analyze historical and current analytics codes for a URL."""
    results = {
        'current_codes': {'UA': [], 'GA': [], 'GTM': []},
        'historical_codes': {
            'UA': {},
            'GA': {},
            'GTM': {}
        }
    }
    
    try:
        # Get list of snapshots
        snapshots = await fetch_snapshots(session, url, from_date, to_date)
        
        # Track when codes were seen
        code_dates = {'UA': {}, 'GA': {}, 'GTM': {}}
        
        # Process each snapshot
        for timestamp in snapshots:
            content = await fetch_snapshot_content(session, url, timestamp)
            
            # Find codes in this snapshot
            ua_codes = set(re.findall(UA_PATTERN, content))
            ga_codes = set(re.findall(GA4_PATTERN, content))
            gtm_codes = set(re.findall(GTM_PATTERN, content))
            
            formatted_date = format_timestamp(timestamp)
            
            # Update tracking for each code type
            for code in ua_codes:
                if code not in code_dates['UA']:
                    code_dates['UA'][code] = {'first_seen': formatted_date, 'last_seen': formatted_date}
                else:
                    code_dates['UA'][code]['last_seen'] = formatted_date
            
            for code in ga_codes:
                if code not in code_dates['GA']:
                    code_dates['GA'][code] = {'first_seen': formatted_date, 'last_seen': formatted_date}
                else:
                    code_dates['GA'][code]['last_seen'] = formatted_date
                    
            for code in gtm_codes:
                if code not in code_dates['GTM']:
                    code_dates['GTM'][code] = {'first_seen': formatted_date, 'last_seen': formatted_date}
                else:
                    code_dates['GTM'][code]['last_seen'] = formatted_date
        
        # Get current codes
        current_content = await fetch_snapshot_content(session, url, "")
        results['current_codes']['UA'] = list(set(re.findall(UA_PATTERN, current_content)))
        results['current_codes']['GA'] = list(set(re.findall(GA4_PATTERN, current_content)))
        results['current_codes']['GTM'] = list(set(re.findall(GTM_PATTERN, current_content)))
        
        # Add historical data
        results['historical_codes']['UA'] = code_dates['UA']
        results['historical_codes']['GA'] = code_dates['GA']
        results['historical_codes']['GTM'] = code_dates['GTM']
        
        return results
    
    except Exception as e:
        print(f"Error analyzing {url}: {str(e)}")
        return results

async def main():
    # Get URLs
    urls = input("Enter URLs (space-separated): ").split()
    if not urls:
        print("No URLs provided!")
        return

    # Get date range (optional)
    use_dates = input("Use date range? (y/N): ").lower().startswith('y')
    if use_dates:
        start_date = input("Start date (dd/mm/YYYY:HH:MM) [01/10/2012:00:00]: ") or "01/10/2012:00:00"
        end_date = input("End date (dd/mm/YYYY:HH:MM) [none]: ") or None
        
        if start_date and end_date and not validate_dates(start_date, end_date):
            print("Error: Start date must be before end date")
            return
    else:
        start_date = "01/10/2012:00:00"
        end_date = None

    start_timestamp = get_14_digit_timestamp(start_date)
    end_timestamp = get_14_digit_timestamp(end_date) if end_date else None

    async with aiohttp.ClientSession() as session:
        try:
            for url in urls:
                print(f"\n=== {url} ===")
                results = await analyze_codes(session, url, start_timestamp, end_timestamp)
                
                # Display current codes
                print("\nCurrent Codes:")
                for code_type in ['UA', 'GA', 'GTM']:
                    if results['current_codes'][code_type]:
                        for code in results['current_codes'][code_type]:
                            print(f"{code_type}: {code}")
                
                # Display historical codes
                print("\nHistorical Codes:")
                for code_type in ['UA', 'GA', 'GTM']:
                    if results['historical_codes'][code_type]:
                        for code, dates in results['historical_codes'][code_type].items():
                            print(f"{code_type}: {code} ({dates['first_seen']} to {dates['last_seen']})")

        except aiohttp.ClientError:
            print("Error: Rate limited by archive.org. Wait 5 minutes and try again.")
            return

async def analyze_ga_history(domain: str) -> None:
    """Handler for GA command"""
    async with aiohttp.ClientSession() as session:
        try:
            start_date = "01/10/2012:00:00"
            start_timestamp = get_14_digit_timestamp(start_date)
            
            print(f"\n=== {domain} ===")
            results = await analyze_codes(session, domain, start_timestamp)
            
            # Display current codes
            print("\nCurrent Codes:")
            for code_type in ['UA', 'GA', 'GTM']:
                if results['current_codes'][code_type]:
                    for code in results['current_codes'][code_type]:
                        print(f"{code_type}: {code}")
            
            # Display historical codes
            print("\nHistorical Codes:")
            for code_type in ['UA', 'GA', 'GTM']:
                if results['historical_codes'][code_type]:
                    for code, dates in results['historical_codes'][code_type].items():
                        print(f"{code_type}: {code} ({dates['first_seen']} to {dates['last_seen']})")

        except aiohttp.ClientError:
            print("Error: Rate limited by archive.org. Wait 5 minutes and try again.")

if __name__ == "__main__":
    asyncio.run(main())