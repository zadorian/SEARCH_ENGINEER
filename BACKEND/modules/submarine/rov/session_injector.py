"""
ROV Session Injector - Authentication Plugin for SUBMARINE

Enables scraping behind paywalls and logged-in pages by injecting
browser session cookies into requests.

Directory Structure:
    auth_sessions/
    ├── example.com.json
    ├── nytimes.com.json
    └── linkedin.com.json

Cookie File Format (Netscape or JSON):
    
    # Netscape format (from browser extensions like "EditThisCookie"):
    .example.com\tTRUE\t/\tTRUE\t1234567890\tsession_id\tabc123xyz
    
    # JSON format (cleaner):
    [
        {
            "name": "session_id",
            "value": "abc123xyz",
            "domain": ".example.com",
            "path": "/",
            "expires": 1234567890,
            "httpOnly": true,
            "secure": true
        }
    ]

Usage:
    from SUBMARINE.rov.session_injector import SessionInjector
    
    injector = SessionInjector("/data/auth_sessions")
    cookies = injector.load_cookies("example.com")
    # Returns list of cookie dicts ready for requests/playwright
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SessionInjector:
    """
    Manages authentication sessions for web scraping.
    
    Loads browser cookies from files and provides them to scrapers
    to bypass login walls and access authenticated content.
    """
    
    def __init__(self, session_dir: str):
        """
        Initialize the session injector.
        
        Args:
            session_dir: Directory containing cookie files (e.g., /data/auth_sessions)
        """
        self.session_dir = Path(session_dir)
        self._cache: Dict[str, List[Dict[str, Any]]] = {}
        
        if not self.session_dir.exists():
            logger.warning(f"Session directory does not exist: {session_dir}")
            logger.info(f"Create it with: mkdir -p {session_dir}")
        else:
            logger.info(f"ROV SessionInjector initialized with {session_dir}")
    
    def load_cookies(self, domain: str) -> Optional[List[Dict[str, Any]]]:
        """
        Load cookies for a specific domain.
        
        Args:
            domain: Domain name (e.g., "example.com")
        
        Returns:
            List of cookie dicts with keys: name, value, domain, path, expires, httpOnly, secure
            Returns None if no cookies found for domain
        """
        # Check cache first
        if domain in self._cache:
            logger.debug(f"[ROV] Using cached cookies for {domain}")
            return self._cache[domain]
        
        # Try exact match first
        cookie_file = self.session_dir / f"{domain}.json"
        if not cookie_file.exists():
            # Try with leading dot (e.g., .example.com)
            cookie_file = self.session_dir / f".{domain}.json"
        
        if not cookie_file.exists():
            # Try base domain (remove subdomain)
            parts = domain.split('.')
            if len(parts) > 2:
                base_domain = '.'.join(parts[-2:])
                cookie_file = self.session_dir / f"{base_domain}.json"
        
        if not cookie_file.exists():
            logger.debug(f"[ROV] No cookies found for {domain}")
            return None
        
        try:
            with open(cookie_file, 'r') as f:
                content = f.read().strip()
            
            # Try JSON format first
            if content.startswith('[') or content.startswith('{'):
                cookies = self._parse_json_cookies(content)
            else:
                # Try Netscape format
                cookies = self._parse_netscape_cookies(content)
            
            if cookies:
                logger.info(f"[ROV] Loaded {len(cookies)} cookies for {domain}")
                self._cache[domain] = cookies
                return cookies
            else:
                logger.warning(f"[ROV] Cookie file exists but contains no valid cookies: {cookie_file}")
                return None
                
        except Exception as e:
            logger.error(f"[ROV] Error loading cookies for {domain}: {e}")
            return None
    
    def _parse_json_cookies(self, content: str) -> List[Dict[str, Any]]:
        """Parse cookies from JSON format."""
        data = json.loads(content)
        
        # Handle both array of cookies and single cookie object
        if isinstance(data, dict):
            data = [data]
        
        cookies = []
        for cookie in data:
            if not isinstance(cookie, dict):
                continue
            
            # Normalize cookie format
            normalized = {
                'name': cookie.get('name'),
                'value': cookie.get('value'),
                'domain': cookie.get('domain', ''),
                'path': cookie.get('path', '/'),
                'expires': cookie.get('expires', cookie.get('expirationDate')),
                'httpOnly': cookie.get('httpOnly', False),
                'secure': cookie.get('secure', False),
                'sameSite': cookie.get('sameSite', 'Lax')
            }
            
            # Only add if name and value exist
            if normalized['name'] and normalized['value'] is not None:
                cookies.append(normalized)
        
        return cookies
    
    def _parse_netscape_cookies(self, content: str) -> List[Dict[str, Any]]:
        """
        Parse cookies from Netscape format (browser export format).
        
        Format: domain\tflag\tpath\tsecure\texpires\tname\tvalue
        Example: .example.com\tTRUE\t/\tTRUE\t1234567890\tsession_id\tabc123
        """
        cookies = []
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            
            try:
                parts = line.split('\t')
                if len(parts) < 7:
                    continue
                
                domain, flag, path, secure, expires, name, value = parts[:7]
                
                cookie = {
                    'name': name,
                    'value': value,
                    'domain': domain,
                    'path': path,
                    'expires': int(expires) if expires.isdigit() else None,
                    'httpOnly': False,  # Netscape format doesn't specify
                    'secure': secure.upper() == 'TRUE',
                    'sameSite': 'Lax'
                }
                
                cookies.append(cookie)
            except Exception as e:
                logger.debug(f"[ROV] Skipping malformed cookie line: {line[:50]}... ({e})")
                continue
        
        return cookies
    
    def clear_cache(self):
        """Clear the cookie cache (forces reload from disk)."""
        self._cache.clear()
        logger.debug("[ROV] Cookie cache cleared")
    
    def list_available_domains(self) -> List[str]:
        """List all domains with stored cookies."""
        if not self.session_dir.exists():
            return []
        
        domains = []
        for file in self.session_dir.glob("*.json"):
            domain = file.stem
            if domain.startswith('.'):
                domain = domain[1:]
            domains.append(domain)
        
        return sorted(domains)
    
    def validate_cookies(self, domain: str) -> Dict[str, Any]:
        """
        Validate cookies for a domain.
        
        Returns:
            Dict with keys: valid, count, expired, issues
        """
        import time
        
        cookies = self.load_cookies(domain)
        if not cookies:
            return {
                'valid': False,
                'count': 0,
                'expired': 0,
                'issues': ['No cookies found']
            }
        
        now = time.time()
        expired = 0
        issues = []
        
        for cookie in cookies:
            expires = cookie.get('expires')
            if expires and expires < now:
                expired += 1
        
        if expired == len(cookies):
            issues.append('All cookies expired')
        elif expired > 0:
            issues.append(f'{expired} cookies expired')
        
        return {
            'valid': len(cookies) > 0 and expired < len(cookies),
            'count': len(cookies),
            'expired': expired,
            'issues': issues
        }


def export_cookies_from_browser_instructions():
    """
    Print instructions for exporting cookies from browsers.
    """
    return """
# How to Export Cookies from Your Browser

## Method 1: Chrome/Edge Extension (Recommended)
1. Install "EditThisCookie" or "Cookie-Editor" extension
2. Navigate to the logged-in page (e.g., nytimes.com)
3. Click extension icon → Export → "Netscape format" or "JSON"
4. Save as: /data/auth_sessions/nytimes.com.json

## Method 2: Firefox Extension
1. Install "Cookie Quick Manager"
2. Navigate to logged-in page
3. Click extension → Export → JSON format
4. Save as: /data/auth_sessions/DOMAIN.json

## Method 3: Chrome DevTools (Manual)
1. Open DevTools (F12) → Application → Cookies
2. Select domain
3. Copy cookies to JSON format:
[
    {
        "name": "session_id",
        "value": "abc123...",
        "domain": ".example.com",
        "path": "/",
        "expires": 1735689600,
        "secure": true,
        "httpOnly": true
    }
]

## Method 4: Playwright/Puppeteer (Automated)
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    
    # Navigate and login manually
    page.goto("https://example.com/login")
    input("Press Enter after logging in...")
    
    # Export cookies
    cookies = context.cookies()
    with open("/data/auth_sessions/example.com.json", "w") as f:
        json.dump(cookies, f, indent=2)
```

## Important Notes:
- Cookie files should be named: DOMAIN.json (e.g., nytimes.com.json)
- Keep cookies SECURE - they provide full access to your accounts
- Cookies expire - re-export if scraping fails with login pages
- Test with: injector.validate_cookies("domain.com")
"""


# Standalone testing
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python session_injector.py <session_dir> [domain]")
        print("\nExample:")
        print("  python session_injector.py /data/auth_sessions")
        print("  python session_injector.py /data/auth_sessions nytimes.com")
        print("\nExport Instructions:")
        print(export_cookies_from_browser_instructions())
        sys.exit(1)
    
    session_dir = sys.argv[1]
    injector = SessionInjector(session_dir)
    
    print(f"\n=== ROV SessionInjector ===")
    print(f"Session Dir: {session_dir}")
    print(f"Exists: {Path(session_dir).exists()}")
    
    domains = injector.list_available_domains()
    print(f"\nAvailable Domains ({len(domains)}):")
    for domain in domains:
        print(f"  - {domain}")
    
    if len(sys.argv) > 2:
        test_domain = sys.argv[2]
        print(f"\n=== Testing: {test_domain} ===")
        
        validation = injector.validate_cookies(test_domain)
        print(f"Valid: {validation['valid']}")
        print(f"Count: {validation['count']}")
        print(f"Expired: {validation['expired']}")
        if validation['issues']:
            print(f"Issues: {', '.join(validation['issues'])}")
        
        cookies = injector.load_cookies(test_domain)
        if cookies:
            print(f"\nCookies:")
            for cookie in cookies[:3]:  # Show first 3
                print(f"  - {cookie['name']}: {cookie['value'][:20]}...")
            if len(cookies) > 3:
                print(f"  ... and {len(cookies) - 3} more")
