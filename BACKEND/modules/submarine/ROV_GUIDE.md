# ROV (Remotely Operated Vehicle) - Authentication System Guide

## Overview

ROV enables SUBMARINE/JESTER to scrape behind paywalls and login walls by injecting browser cookies into requests. Like a remotely operated underwater vehicle, it navigates protected content by carrying authentication credentials.

## Quick Start

### 1. Create Auth Session Directory

```bash
mkdir -p /data/auth_sessions
chmod 700 /data/auth_sessions  # Keep secure!
```

### 2. Export Cookies from Browser

**Option A: Chrome Extension (Easiest)**
1. Install "EditThisCookie" extension from Chrome Web Store
2. Log into target website (e.g., nytimes.com)
3. Click EditThisCookie icon → Export → "JSON format"
4. Save content to: `/data/auth_sessions/nytimes.com.json`

**Option B: Firefox Extension**
1. Install "Cookie Quick Manager"
2. Log into target website
3. Export cookies as JSON
4. Save to: `/data/auth_sessions/DOMAIN.json`

**Option C: Manual Chrome DevTools**
1. Log into website
2. Open DevTools (F12) → Application tab → Cookies
3. Select your domain
4. Copy cookies manually to JSON format (see template below)

### 3. Configure JESTER

```python
from modules.JESTER import Jester, JesterConfig

config = JesterConfig(
    use_auth_sessions=True,
    auth_session_dir="/data/auth_sessions"
)

jester = Jester(config)
result = await jester.scrape("https://nytimes.com/premium-article")
# Will automatically use cookies if nytimes.com.json exists
```

## Cookie File Format

### JSON Format (Recommended)

File: `/data/auth_sessions/example.com.json`

```json
[
    {
        "name": "session_id",
        "value": "abc123xyz456...",
        "domain": ".example.com",
        "path": "/",
        "expires": 1735689600,
        "secure": true,
        "httpOnly": true,
        "sameSite": "Lax"
    },
    {
        "name": "user_token",
        "value": "def789...",
        "domain": ".example.com",
        "path": "/",
        "expires": 1767225600,
        "secure": true,
        "httpOnly": false
    }
]
```

### Netscape Format (Alternative)

File: `/data/auth_sessions/example.com.json`

```
# Netscape HTTP Cookie File
.example.com	TRUE	/	TRUE	1735689600	session_id	abc123xyz456
.example.com	TRUE	/	TRUE	1767225600	user_token	def789
```

## Testing Cookies

```bash
# Test SessionInjector directly
cd /data/SUBMARINE
python3 -m rov.session_injector /data/auth_sessions nytimes.com

# Output shows:
# - Available domains
# - Cookie count
# - Expiration status
# - Validation results
```

## Automated Cookie Export (Playwright)

```python
from playwright.sync_api import sync_playwright
import json

def export_cookies_for_site(url: str, output_file: str):
    """
    Launch browser, let user login, export cookies.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        page.goto(url)
        print(f"Please log in to {url}")
        input("Press Enter after logging in...")
        
        # Export cookies
        cookies = context.cookies()
        
        with open(output_file, "w") as f:
            json.dump(cookies, f, indent=2)
        
        print(f"Exported {len(cookies)} cookies to {output_file}")
        browser.close()

# Usage
export_cookies_for_site(
    "https://nytimes.com/login",
    "/data/auth_sessions/nytimes.com.json"
)
```

## How It Works

1. **Domain Matching**: SessionInjector looks for `DOMAIN.json` in auth_session_dir
2. **Cookie Loading**: Parses JSON or Netscape format
3. **Injection**: JESTER/LINKLATER automatically injects cookies into requests for matching domains
4. **Login Detection**: If a login page is detected despite cookies, system falls back to non-authenticated scraping

## Supported Sites Examples

```bash
/data/auth_sessions/
├── nytimes.com.json          # New York Times
├── wsj.com.json              # Wall Street Journal
├── ft.com.json               # Financial Times
├── bloomberg.com.json        # Bloomberg
├── linkedin.com.json         # LinkedIn (for profile scraping)
├── pacer.gov.json            # PACER (US court records)
└── lexisnexis.com.json       # LexisNexis
```

## Troubleshooting

### Cookies Not Working

**Check expiration:**
```python
from SUBMARINE.rov import SessionInjector

injector = SessionInjector("/data/auth_sessions")
result = injector.validate_cookies("nytimes.com")
print(result)  # Shows expired count
```

**Solution:** Re-export cookies from browser

### Still Seeing Login Page

**Possible causes:**
- Cookies expired → Re-export
- Wrong domain format → Use base domain (e.g., `example.com` not `www.example.com`)
- IP-based restrictions → Site blocks server IP
- 2FA required → Cookies alone won't work

### Permissions Error

```bash
chmod 700 /data/auth_sessions
chown $USER:$USER /data/auth_sessions/*
```

## Security Notes

- **Cookie files = full account access** - protect like passwords
- Store in secure location (`/data/auth_sessions` with 700 permissions)
- Don't commit to git (add to .gitignore)
- Rotate cookies periodically
- Use dedicated accounts for scraping when possible

## Integration with JESTER Tiers

```python
# JESTER automatically uses ROV across all tiers:

# JESTER_A (httpx) - Injects cookies into headers
# JESTER_B (Colly) - Adds Cookie header
# JESTER_C (Rod) - Sets browser cookies before navigation
# JESTER_D (Playwright) - Uses context.add_cookies()
```

## API Usage

```python
from SUBMARINE.rov import SessionInjector

# Initialize
injector = SessionInjector("/data/auth_sessions")

# Load cookies for domain
cookies = injector.load_cookies("nytimes.com")
# Returns: [{"name": "...", "value": "...", ...}, ...]

# List available domains
domains = injector.list_available_domains()
# Returns: ["nytimes.com", "wsj.com", ...]

# Validate cookies
status = injector.validate_cookies("nytimes.com")
# Returns: {"valid": True, "count": 5, "expired": 0, "issues": []}

# Clear cache (force reload from disk)
injector.clear_cache()
```

## Environment Variables

```bash
# Optional: Set default auth session directory
export AUTH_SESSION_DIR="/data/auth_sessions"

# JESTER will use this if auth_session_dir not specified in config
```

## Complete Example

```python
from modules.JESTER import Jester, JesterConfig
from SUBMARINE.rov import SessionInjector

# Setup
config = JesterConfig(
    use_auth_sessions=True,
    auth_session_dir="/data/auth_sessions"
)

jester = Jester(config)

# Test authentication
injector = SessionInjector("/data/auth_sessions")
validation = injector.validate_cookies("nytimes.com")

if validation['valid']:
    print(f"✓ {validation['count']} valid cookies for nytimes.com")
    
    # Scrape authenticated content
    result = await jester.scrape("https://nytimes.com/premium-article")
    
    if result.success:
        print(f"✓ Scraped {len(result.content)} chars")
        print(f"  Method: {result.method}")
    else:
        print(f"✗ Failed: {result.error}")
else:
    print(f"✗ Invalid cookies: {validation['issues']}")
    print("Re-export cookies from browser")
```

## Next Steps

1. Export cookies for your target sites
2. Test with `python3 -m rov.session_injector /data/auth_sessions DOMAIN`
3. Configure JESTER with `use_auth_sessions=True`
4. Monitor logs for "ROV" messages showing cookie injection
