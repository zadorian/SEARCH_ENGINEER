#!/usr/bin/env python3
"""
Social Media search type: returns direct links to Facebook and Twitter/X search verticals.
No scraping; complies with ToS.
"""

from typing import List, Dict, Optional
from urllib.parse import quote
from brute.engines.facebook import (
    facebook_results as fb_results,
    facebook_top_by_date as fb_top_by_date,
    facebook_photos_by_date as fb_photos_by_date,
    facebook_videos_by_date as fb_videos_by_date,
    facebook_get_user_id as fb_get_user_id,
)


# Twitter/X URL generators
def _twitter_quote(query: str) -> str:
    """Quote a query for Twitter/X URLs"""
    return quote(query)

def twitter_search(query: str) -> str:
    """General Twitter/X search"""
    return f"https://x.com/search?q={_twitter_quote(query)}&f=live"

def twitter_from_user(username: str, query: str = "") -> str:
    """Tweets from a specific user (outgoing)"""
    search_query = f"from:{username}"
    if query:
        search_query += f" {query}"
    return f"https://x.com/search?q={_twitter_quote(search_query)}&f=live"

def twitter_to_user(username: str, query: str = "") -> str:
    """Tweets to a specific user (incoming/mentions)"""
    search_query = f"to:{username}"
    if query:
        search_query += f" {query}"
    return f"https://x.com/search?q={_twitter_quote(search_query)}&f=live"

def twitter_replies_from_user(username: str) -> str:
    """Replies from a specific user"""
    return f"https://x.com/search?q={_twitter_quote(f'from:{username} filter:replies')}&src=typed_query&f=live"

def twitter_followers(username: str) -> str:
    """User's followers list"""
    return f"https://x.com/{username}/followers"

def twitter_following(username: str) -> str:
    """User's following list"""
    return f"https://x.com/{username}/following"

def twitter_profile(username: str) -> str:
    """Direct link to user profile"""
    return f"https://x.com/{username}"

def twitter_from_user_date_range(username: str, since: str, until: str, query: str = "") -> str:
    """Tweets from a user within a date range"""
    search_query = f"from:{username}"
    if query:
        search_query += f" {query}"
    search_query += f" since:{since} until:{until}"
    return f"https://x.com/search?q={_twitter_quote(search_query)}&src=typd&f=live"

def twitter_to_user_date_range(username: str, since: str, until: str, query: str = "") -> str:
    """Tweets to a user within a date range"""
    search_query = f"to:{username}"
    if query:
        search_query += f" {query}"
    search_query += f" since:{since} until:{until}"
    return f"https://x.com/search?q={_twitter_quote(search_query)}&src=typd&f=live"

def twitter_outlinks(username: str, query: str = "") -> str:
    """Tweets from a user that contain links (outlinks)"""
    search_query = f"from:{username} filter:links"
    if query:
        search_query += f" {query}"
    return f"https://x.com/search?q={_twitter_quote(search_query)}&src=typed_query&f=live"

def twitter_historic_google(username: str, include_status: bool = False) -> str:
    """Search historic Twitter content via Google (includes deleted/archived tweets)"""
    if include_status:
        # Search for specific status updates (individual tweets)
        site_query = f"site:twitter.com/{username}/status/"
    else:
        # Search for all content from user's profile
        site_query = f"site:twitter.com/{username}"
    return f"https://www.google.com/search?q={quote(site_query)}"

def twitter_historic_google_with_query(username: str, query: str, include_status: bool = False) -> str:
    """Search historic Twitter content via Google with additional search terms"""
    if include_status:
        site_query = f"site:twitter.com/{username}/status/ {query}"
    else:
        site_query = f"site:twitter.com/{username} {query}"
    return f"https://www.google.com/search?q={quote(site_query)}"

def twitter_find_by_real_name(real_name: str) -> str:
    """Search for Twitter profiles by real name (returns potential usernames)"""
    # Search Twitter profiles for the real name
    search_query = f'site:twitter.com "{real_name}" -inurl:status'
    return f"https://www.google.com/search?q={quote(search_query)}"

def twitter_find_by_real_name_x(real_name: str) -> str:
    """Search for X.com profiles by real name using current domain"""
    # Search X.com profiles for the real name
    search_query = f'site:x.com "{real_name}" -inurl:status'
    return f"https://www.google.com/search?q={quote(search_query)}"

def twitter_find_verified(real_name: str) -> str:
    """Search for verified Twitter accounts by real name"""
    # Look for profiles with verification patterns
    search_query = f'site:twitter.com "{real_name}" ("verified account" OR "blue checkmark" OR "official")'
    return f"https://www.google.com/search?q={quote(search_query)}"

# Instagram URL generators
def instagram_profile(username: str) -> str:
    """Direct link to Instagram profile"""
    return f"https://www.instagram.com/{username}/"

def instagram_channel(username: str) -> str:
    """Instagram channel/reels view"""
    return f"https://www.instagram.com/{username}/channel/"

def instagram_tagged(username: str) -> str:
    """Photos where user is tagged"""
    return f"https://www.instagram.com/{username}/tagged/"

def instagram_analysis(username: str) -> str:
    """Instagram profile analyzer tool"""
    return f"https://toolzu.com/profile-analyzer/instagram/?username={username}"

# Threads URL generator
def threads_profile(username: str) -> str:
    """Direct link to Threads profile"""
    return f"https://www.threads.com/@{username}"

def instagram_results(username: str) -> List[Dict]:
    """Return Instagram and Threads search result links"""
    results = []
    
    if username:
        results.extend([
            {"title": f"Instagram Profile: @{username}", 
             "url": instagram_profile(username), 
             "search_engine": "instagram", "engine_badge": "IG",
             "description": "Instagram profile page"},
            {"title": f"Instagram Channel: @{username}", 
             "url": instagram_channel(username), 
             "search_engine": "instagram", "engine_badge": "IG",
             "description": "Instagram channel/reels"},
            {"title": f"Instagram Tagged: @{username}", 
             "url": instagram_tagged(username), 
             "search_engine": "instagram", "engine_badge": "IG",
             "description": "Photos where user is tagged"},
            {"title": f"Instagram Analysis: @{username}", 
             "url": instagram_analysis(username), 
             "search_engine": "toolzu", "engine_badge": "TZ",
             "description": "Profile analytics and insights"},
            {"title": f"Threads Profile: @{username}", 
             "url": threads_profile(username), 
             "search_engine": "threads", "engine_badge": "TH",
             "description": "Threads profile (Meta's Twitter alternative)"},
        ])
    
    return results

def twitter_results(query: str, username: Optional[str] = None, date_info: Optional[Dict] = None) -> List[Dict]:
    """Return Twitter/X search result links"""
    results = []
    
    # Check if this is an outlinks search request
    if date_info and date_info.get('is_outlinks') and username:
        additional = date_info.get('additional_query', '')
        
        results.extend([
            {"title": f"Tweets with Links from @{username}", 
             "url": twitter_outlinks(username, additional), 
             "search_engine": "twitter", "engine_badge": "X",
             "description": "Tweets containing external links"},
        ])
        
        # Add regular profile and search links
        results.extend([
            {"title": f"Twitter/X Profile: @{username}", 
             "url": twitter_profile(username), 
             "search_engine": "twitter", "engine_badge": "X"},
            {"title": f"All Tweets from @{username}", 
             "url": twitter_from_user(username, additional), 
             "search_engine": "twitter", "engine_badge": "X"},
        ])
    # Check if this is a historic search request
    elif date_info and date_info.get('is_historic') and username:
        # Historic Twitter search via Google
        additional = date_info.get('additional_query', '')
        
        results.extend([
            {"title": f"Historic Twitter: @{username} (All Content via Google)", 
             "url": twitter_historic_google(username, include_status=False), 
             "search_engine": "google", "engine_badge": "GO",
             "description": "Search archived/deleted tweets via Google"},
            {"title": f"Historic Twitter: @{username} (Status Updates via Google)", 
             "url": twitter_historic_google(username, include_status=True), 
             "search_engine": "google", "engine_badge": "GO",
             "description": "Search specific tweet statuses via Google"},
        ])
        
        # If there's additional query text, add searches with that text
        if additional:
            results.extend([
                {"title": f"Historic Twitter: @{username} + '{additional}'", 
                 "url": twitter_historic_google_with_query(username, additional, include_status=False), 
                 "search_engine": "google", "engine_badge": "GO"},
                {"title": f"Historic Twitter Statuses: @{username} + '{additional}'", 
                 "url": twitter_historic_google_with_query(username, additional, include_status=True), 
                 "search_engine": "google", "engine_badge": "GO"},
            ])
        
        # Also add current profile link for reference
        results.append(
            {"title": f"Current Twitter/X Profile: @{username}", 
             "url": twitter_profile(username), 
             "search_engine": "twitter", "engine_badge": "X"}
        )
    # Check if we have date range information
    elif date_info and date_info.get('start_date') and date_info.get('end_date') and username:
        # Date-ranged searches for a specific user
        start = date_info['start_date']
        end = date_info['end_date']
        additional = date_info.get('additional_query', '')
        
        # Format date display
        date_display = f"{start[:4]}-{end[:4]}" if start[:4] != end[:4] else start[:4]
        
        results.extend([
            {"title": f"Tweets FROM @{username} ({date_display})", 
             "url": twitter_from_user_date_range(username, start, end, additional), 
             "search_engine": "twitter", "engine_badge": "X"},
            {"title": f"Tweets TO @{username} ({date_display})", 
             "url": twitter_to_user_date_range(username, start, end, additional), 
             "search_engine": "twitter", "engine_badge": "X"},
        ])
        
        # Also add regular profile links
        results.extend([
            {"title": f"Twitter/X Profile: @{username}", "url": twitter_profile(username), "search_engine": "twitter", "engine_badge": "X"},
            {"title": f"@{username} Followers", "url": twitter_followers(username), "search_engine": "twitter", "engine_badge": "X"},
            {"title": f"@{username} Following", "url": twitter_following(username), "search_engine": "twitter", "engine_badge": "X"},
        ])
    elif username:
        # Regular user-specific searches without date range
        results.extend([
            {"title": f"Twitter/X Profile: @{username}", "url": twitter_profile(username), "search_engine": "twitter", "engine_badge": "X"},
            {"title": f"Tweets from @{username}", "url": twitter_from_user(username), "search_engine": "twitter", "engine_badge": "X"},
            {"title": f"Tweets to @{username}", "url": twitter_to_user(username), "search_engine": "twitter", "engine_badge": "X"},
            {"title": f"Replies from @{username}", "url": twitter_replies_from_user(username), "search_engine": "twitter", "engine_badge": "X"},
            {"title": f"@{username} Followers", "url": twitter_followers(username), "search_engine": "twitter", "engine_badge": "X"},
            {"title": f"@{username} Following", "url": twitter_following(username), "search_engine": "twitter", "engine_badge": "X"},
        ])
    else:
        # General search
        results.append(
            {"title": f"Twitter/X Search: {query}", "url": twitter_search(query), "search_engine": "twitter", "engine_badge": "X"}
        )
    
    return results

def search(query: str, username: Optional[str] = None, real_name: Optional[str] = None) -> List[Dict]:
    """Return combined Facebook, Twitter/X, and Instagram search results
    
    Supports special Twitter syntax:
    - 'yyyy! @username :twitter' - Single year search
    - 'yyyy-yyyy! @username :twitter' - Date range search
    - 'u:username yyyy-yyyy! :x' - Alternative syntax
    - 'u:username :<-twitter' - Historic Twitter search via Google
    - '<- @username twitter' - Historic Twitter search (alternative)
    - 'u:username ol! :twitter' - Tweets with links (outlinks)
    - 'ol! @username twitter' - Outlinks (alternative)
    
    Args:
        query: Search query
        username: Social media username if known
        real_name: Real name to search for profiles
    """
    results = []
    
    # Parse the query for Twitter-specific date patterns
    date_info = parse_twitter_date_query(query)
    
    if date_info['is_twitter_search']:
        # This is a Twitter-specific search with potential date range
        username = username or date_info['username']
        results.extend(twitter_results(query, username, date_info))
        
        # Also add basic Facebook results if no date range
        if not date_info['start_date']:
            results.extend(fb_results(query))
    else:
        # Regular search - add Facebook, Twitter, and Instagram results
        results.extend(fb_results(query))
        
        # Auto-detect username if not provided
        if not username:
            username = extract_twitter_username(query)
        
        results.extend(twitter_results(query, username))
        
        # Add Instagram results if we have a username
        if username:
            results.extend(instagram_results(username))
    
    # If real_name is provided, add name search results
    if real_name:
        results.extend(search_by_real_name(real_name))
    
    return results

def search_by_real_name(real_name: str) -> List[Dict]:
    """Search for social media profiles by real name"""
    results = []
    
    # Twitter/X profile searches
    results.extend([
        {"title": f"Find Twitter profiles for: {real_name}",
         "url": twitter_find_by_real_name(real_name),
         "search_engine": "google", "engine_badge": "GO",
         "description": "Search Twitter.com for profiles with this name"},
        {"title": f"Find X.com profiles for: {real_name}",
         "url": twitter_find_by_real_name_x(real_name),
         "search_engine": "google", "engine_badge": "GO",
         "description": "Search X.com for profiles with this name"},
        {"title": f"Find verified accounts for: {real_name}",
         "url": twitter_find_verified(real_name),
         "search_engine": "google", "engine_badge": "GO",
         "description": "Search for verified/official accounts"}
    ])
    
    # Also search Facebook for the name
    from brute.engines.facebook import facebook_people as fb_people
    results.append({
        "title": f"Facebook People: {real_name}",
        "url": fb_people(real_name),
        "search_engine": "facebook", "engine_badge": "FB",
        "description": "Search Facebook for people with this name"
    })
    
    return results


def search_by_date(query: str, start_year: int, start_month: int, start_day: int,
                   end_year: int, end_month: int, end_day: int) -> List[Dict]:
    """Return FB vertical links constrained to the given date range."""
    # Convert individual ints to date strings for the new facebook API
    start_date = f"{start_year}-{start_month:02d}-{start_day:02d}"
    end_date = f"{end_year}-{end_month:02d}-{end_day:02d}"
    return [
        {"title": f"Facebook Top (by date): {query}", "url": fb_top_by_date(query, start_date, end_date), "search_engine": "facebook", "engine_badge": "FB"},
        {"title": f"Facebook Photos (by date): {query}", "url": fb_photos_by_date(query, start_date, end_date), "search_engine": "facebook", "engine_badge": "FB"},
        {"title": f"Facebook Videos (by date): {query}", "url": fb_videos_by_date(query, start_date, end_date), "search_engine": "facebook", "engine_badge": "FB"},
    ]


def resolve_fb_user_id(profile_url: str, access_token: str | None = None) -> Dict:
    """Resolve Facebook user ID. Return {'id': ..., 'name': ...} or {'error': ...}."""
    uid, name_or_err = fb_get_user_id(profile_url, access_token=access_token)
    if uid:
        return {"id": uid, "name": name_or_err}
    return {"error": name_or_err}

def extract_twitter_username(query: str) -> Optional[str]:
    """Try to extract a Twitter username from the query"""
    import re
    # Look for @username pattern
    match = re.search(r'@([A-Za-z0-9_]+)', query)
    if match:
        return match.group(1)
    # Look for u:username pattern
    match = re.search(r'u:([A-Za-z0-9_]+)', query)
    if match:
        return match.group(1)
    # Look for username:username pattern
    match = re.search(r'username:([A-Za-z0-9_]+)', query)
    if match:
        return match.group(1)
    # Look for common patterns like "username zadory" or just "zadory"
    words = query.split()
    if len(words) == 1 and re.match(r'^[A-Za-z0-9_]+$', words[0]):
        return words[0]
    return None

def parse_twitter_date_query(query: str) -> Dict:
    """Parse Twitter search queries with date ranges and special operators
    
    Supports formats:
    - 'yyyy! @username :twitter' or 'yyyy! @username :x'
    - 'yyyy-yyyy! @username :twitter' or 'yyyy-yyyy! @username :x'
    - 'u:username yyyy-yyyy! :twitter' or 'u:username yyyy-yyyy! :x'
    - 'username:username yyyy-yyyy! :twitter'
    - 'u:username :<-twitter' or '<- @username twitter' (historic search)
    - 'u:username ol! :twitter' or 'ol! @username twitter' (outlinks search)
    
    Returns dict with: username, start_date, end_date, is_twitter_search, is_historic, is_outlinks
    """
    import re
    
    result = {
        'username': None,
        'start_date': None,
        'end_date': None,
        'is_twitter_search': False,
        'is_historic': False,
        'is_outlinks': False,
        'additional_query': ''
    }
    
    # Check for outlinks search
    if 'ol!' in query.lower() and (':twitter' in query.lower() or ':x' in query.lower() or 'twitter' in query.lower()):
        result['is_twitter_search'] = True
        result['is_outlinks'] = True
    # Check if this is a historic Twitter search
    elif ':<-twitter' in query.lower() or '<- @' in query.lower() or '<-@' in query.lower():
        result['is_twitter_search'] = True
        result['is_historic'] = True
    # Check if this is a regular Twitter search
    elif ':twitter' in query.lower() or ':x' in query.lower():
        result['is_twitter_search'] = True
    else:
        return result
    
    # Extract username
    result['username'] = extract_twitter_username(query)
    
    # Extract date range (yyyy! or yyyy-yyyy!)
    # Single year pattern
    year_match = re.search(r'(\d{4})!', query)
    if year_match:
        year = year_match.group(1)
        # Year range pattern
        range_match = re.search(r'(\d{4})-(\d{4})!', query)
        if range_match:
            result['start_date'] = f"{range_match.group(1)}-01-01"
            result['end_date'] = f"{range_match.group(2)}-12-31"
        else:
            # Single year
            result['start_date'] = f"{year}-01-01"
            result['end_date'] = f"{year}-12-31"
    
    # Extract any additional query terms (removing date, username, and markers)
    clean_query = re.sub(r'\d{4}(-\d{4})?!', '', query)  # Remove date
    clean_query = re.sub(r'@[A-Za-z0-9_]+', '', clean_query)  # Remove @username
    clean_query = re.sub(r'u:[A-Za-z0-9_]+', '', clean_query)  # Remove u:username
    clean_query = re.sub(r'username:[A-Za-z0-9_]+', '', clean_query)  # Remove username:
    clean_query = re.sub(r':twitter|:x|:<-twitter', '', clean_query, flags=re.IGNORECASE)  # Remove markers
    clean_query = re.sub(r'<-', '', clean_query)  # Remove <- arrow
    clean_query = re.sub(r'ol!', '', clean_query)  # Remove ol! operator
    result['additional_query'] = clean_query.strip()
    
    return result


def main():
    """Main entry point for social media search - compatible with SearchRouter"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Social media platform search')
    parser.add_argument('-q', '--query', required=True, help='Search query')
    args = parser.parse_args()
    
    query = args.query
    
    # Extract clean query
    if ':' in query:
        clean_query = query.split(':', 1)[1].strip()
    else:
        clean_query = query
    
    print(f"\n📱 Social Media Search: {clean_query}")
    
    # Use the search function that exists
    results = search(clean_query)
    
    if results:
        print(f"\nFound {len(results)} social media search URLs:")
        for i, result in enumerate(results[:20], 1):
            print(f"\n{i}. {result.get('title', 'No Title')}")
            print(f"   URL: {result.get('url')}")
            if result.get('snippet'):
                print(f"   {result['snippet'][:150]}...")
    else:
        print("\nNo social media results generated.")
    
    return results
