#!/usr/bin/env python3
"""
Username discovery helper.

Operator triggers:
- username:query
- u:query

This module returns direct platform profile URLs and integrates with EYE-D for 
breach database searches (DeHashed, OSINT Industries).
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional
import asyncio

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    from Search_Engines.exact_phrase_recall_runner_baresearch import bare_social
except ImportError:
    print("Warning: Could not import bare_social from Search_Engines")
    def bare_social(term, page=1, exact=False):
        return f"https://www.google.com/search?q=site:instagram.com+OR+site:twitter.com+OR+site:facebook.com+OR+site:linkedin.com+%22{term}%22"

# Try to import EYE-D integration
try:
    from Search_Types.subject.entity_search import EyeDSearchHandler
    EYE_D_AVAILABLE = True
except ImportError:
    EYE_D_AVAILABLE = False
    print("Warning: EYE-D integration not available for username searches")

# Try to import Sherlock integration
try:
    from sherlock_integration import search_username_sherlock_sync
    SHERLOCK_AVAILABLE = True
except ImportError:
    try:
        # Try relative import if running as module
        from .sherlock_integration import search_username_sherlock_sync
        SHERLOCK_AVAILABLE = True
    except ImportError:
        SHERLOCK_AVAILABLE = False
        print("Warning: Sherlock integration not available for username searches")


def detect_username_query(q: str) -> bool:
    ql = q.strip().lower()
    return ql.startswith('username:') or ql.startswith('u:')


def extract_username(q: str) -> str:
    q = q.strip()
    if q.lower().startswith('username:'):
        return q[len('username:'):].strip().strip('"\'')
    if q.lower().startswith('u:'):
        return q[len('u:'):].strip().strip('"\'')
    return q


def search_sync(query: str, pages: int = 2, exact: bool = False, include_breach_data: bool = True) -> List[Dict]:
    term = extract_username(query)
    rows: List[Dict] = []
    
    # ==== SEARCH ENGINES - GENERAL USERNAME SEARCH ====
    
    # Google
    rows.append({
        'title': f'Google Search: {term}',
        'url': f'https://www.google.com/search?q={term}',
        'source': 'google',
        'snippet': f'General Google search for username {term}'
    })
    
    # Bing
    rows.append({
        'title': f'Bing Search: {term}',
        'url': f'https://www.bing.com/search?q={term}',
        'source': 'bing',
        'snippet': f'General Bing search for username {term}'
    })
    
    # Yandex
    rows.append({
        'title': f'Yandex Search: {term}',
        'url': f'https://yandex.com/search/?text={term}',
        'source': 'yandex',
        'snippet': f'General Yandex search for username {term}'
    })
    
    # DuckDuckGo
    rows.append({
        'title': f'DuckDuckGo Search: {term}',
        'url': f'https://duckduckgo.com/?q={term}',
        'source': 'duckduckgo',
        'snippet': f'General DuckDuckGo search for username {term}'
    })
    
    # ==== PEOPLE SEARCH & OSINT AGGREGATORS ====
    
    # Pipl
    rows.append({
        'title': f'Pipl People Search: {term}',
        'url': f'https://pipl.com/search/?q={term}',
        'source': 'pipl',
        'snippet': f'Pipl people search for {term}'
    })
    
    # PeekYou
    rows.append({
        'title': f'PeekYou Profile: {term}',
        'url': f'https://www.peekyou.com/{term}',
        'source': 'peekyou',
        'snippet': f'PeekYou profile search for {term}'
    })
    
    # WebMii
    rows.append({
        'title': f'WebMii Search: {term}',
        'url': f'http://webmii.com/people?n={term}',
        'source': 'webmii',
        'snippet': f'WebMii web presence search for {term}'
    })
    
    # ==== USERNAME AVAILABILITY CHECKERS ====
    
    # NameCheckUp
    rows.append({
        'title': f'NameCheckUp: {term}',
        'url': f'https://namecheckup.com/check/{term}',
        'source': 'namecheckup',
        'snippet': f'Check {term} availability across multiple platforms'
    })
    
    # Namechk
    rows.append({
        'title': f'Namechk: {term}',
        'url': f'https://namechk.com/{term}',
        'source': 'namechk',
        'snippet': f'Username availability check for {term}'
    })
    
    # WhatsMyName
    rows.append({
        'title': f'WhatsMyName OSINT: {term}',
        'url': f'https://whatsmyname.app/?username={term}',
        'source': 'whatsmyname',
        'snippet': f'OSINT username tool query for {term}'
    })
    
    # UserSearch.org
    rows.append({
        'title': f'UserSearch.org: {term}',
        'url': f'https://usersearch.org/results/?username={term}',
        'source': 'usersearch',
        'snippet': f'Username search for {term}'
    })
    
    # Social Searcher
    rows.append({
        'title': f'Social Searcher: {term}',
        'url': f'https://www.social-searcher.com/social-buzz/?q1={term}',
        'source': 'social_searcher',
        'snippet': f'Real-time social media search for {term}'
    })
    
    # Google Social Dork - Exhaustive social search
    social_sites = 'site:facebook.com+OR+site:twitter.com+OR+site:instagram.com+OR+site:linkedin.com+OR+site:tiktok.com'
    rows.append({
        'title': f'Google Social Dork: {term}',
        'url': f'https://www.google.com/search?q=%22{term}%22+{social_sites}',
        'source': 'google_social_dork',
        'snippet': f'Exhaustive Google search for {term} across major social platforms'
    })
    
    # ==== MAJOR SOCIAL MEDIA PLATFORMS ====
    
    # Twitter/X
    rows.append({
        'title': f'Twitter/X Profile: @{term}',
        'url': f'https://x.com/{term}',
        'source': 'twitter_x',
        'snippet': f'Check if @{term} exists on Twitter/X'
    })
    
    # Instagram
    rows.append({
        'title': f'Instagram Profile: @{term}',
        'url': f'https://www.instagram.com/{term}',
        'source': 'instagram',
        'snippet': f'Check if @{term} exists on Instagram'
    })
    
    # Threads
    rows.append({
        'title': f'Threads Profile: @{term}',
        'url': f'https://www.threads.com/@{term}',
        'source': 'threads',
        'snippet': f'Check if @{term} exists on Threads'
    })
    
    # ==== DEVELOPER & TECH PLATFORMS ====
    
    # GitHub
    rows.append({
        'title': f'GitHub Profile: {term}',
        'url': f'https://github.com/{term}',
        'source': 'github',
        'snippet': f'Check if {term} exists on GitHub'
    })
    
    # Reddit
    rows.append({
        'title': f'Reddit Profile: u/{term}',
        'url': f'https://www.reddit.com/user/{term}',
        'source': 'reddit',
        'snippet': f'Check if u/{term} exists on Reddit'
    })
    
    # YouTube
    rows.append({
        'title': f'YouTube Channel: @{term}',
        'url': f'https://www.youtube.com/@{term}',
        'source': 'youtube',
        'snippet': f'Check if @{term} channel exists on YouTube'
    })
    
    # ==== PROFESSIONAL PLATFORMS ====
    
    # LinkedIn
    rows.append({
        'title': f'LinkedIn Profile: {term}',
        'url': f'https://www.linkedin.com/in/{term}',
        'source': 'linkedin',
        'snippet': f'Check if {term} exists on LinkedIn'
    })
    
    # Medium
    rows.append({
        'title': f'Medium Profile: @{term}',
        'url': f'https://medium.com/@{term}',
        'source': 'medium',
        'snippet': f'Check if @{term} exists on Medium'
    })
    
    # ==== ADDITIONAL PLATFORMS ====
    
    # TikTok
    rows.append({
        'title': f'TikTok Profile: @{term}',
        'url': f'https://www.tiktok.com/@{term}',
        'source': 'tiktok',
        'snippet': f'Check if @{term} exists on TikTok'
    })
    
    # Snapchat
    rows.append({
        'title': f'Snapchat Profile: {term}',
        'url': f'https://www.snapchat.com/add/{term}',
        'source': 'snapchat',
        'snippet': f'Check if {term} exists on Snapchat'
    })
    
    # Pinterest
    rows.append({
        'title': f'Pinterest Profile: {term}',
        'url': f'https://www.pinterest.com/{term}',
        'source': 'pinterest',
        'snippet': f'Check if {term} exists on Pinterest'
    })
    
    # Telegram
    rows.append({
        'title': f'Telegram Profile: @{term}',
        'url': f'https://t.me/{term}',
        'source': 'telegram',
        'snippet': f'Check if @{term} exists on Telegram'
    })
    
    # Discord (server invite link pattern)
    rows.append({
        'title': f'Discord Server: {term}',
        'url': f'https://discord.gg/{term}',
        'source': 'discord',
        'snippet': f'Check if {term} is a Discord server invite'
    })
    
    # Twitch
    rows.append({
        'title': f'Twitch Channel: {term}',
        'url': f'https://www.twitch.tv/{term}',
        'source': 'twitch',
        'snippet': f'Check if {term} streams on Twitch'
    })
    
    # DeviantArt
    rows.append({
        'title': f'DeviantArt Profile: {term}',
        'url': f'https://www.deviantart.com/{term}',
        'source': 'deviantart',
        'snippet': f'Check if {term} exists on DeviantArt'
    })
    
    # ==== BREACH DATABASE SEARCHES (EYE-D Integration) ====
    
    if include_breach_data and EYE_D_AVAILABLE:
        # Search breach databases via EYE-D
        breach_results = search_breach_databases(term)
        if breach_results:
            rows.extend(breach_results)
    
    # ==== AGGREGATOR SEARCHES ====
    
    # Add BareSearch social media results
    for p in range(1, max(1, pages) + 1):
        rows.append({
            'title': f'BareSearch Social Media p{p}: {term}',
            'url': bare_social(term, page=p, exact=exact),
            'source': 'baresearch_social',
            'snippet': f'Aggregated social media search page {p}'
        })
    
    # ==== SHERLOCK PROJECT INTEGRATION ====
    
    if SHERLOCK_AVAILABLE:
        try:
            # Search username across 400+ sites using Sherlock patterns
            sherlock_results = search_username_sherlock_sync(term)
            
            # Add found profiles to results
            for result in sherlock_results:
                rows.append({
                    'title': f'[SHERLOCK] {result["site"]}: {term}',
                    'url': result['url'],
                    'source': 'sherlock',
                    'snippet': f'Found profile on {result["site"]} ({result.get("category", "unknown")} site)',
                    'confidence': 'high',
                    'verified': True,
                    'category': result.get('category', 'unknown')
                })
            
            # Add summary if profiles found
            if sherlock_results:
                categories = {}
                for r in sherlock_results:
                    cat = r.get('category', 'unknown')
                    categories[cat] = categories.get(cat, 0) + 1
                
                summary = f"Sherlock found {len(sherlock_results)} profiles: " + ", ".join([f"{count} {cat}" for cat, count in categories.items()])
                rows.insert(0, {
                    'title': f'[SHERLOCK SUMMARY] {term}',
                    'url': '#sherlock-results',
                    'source': 'sherlock',
                    'snippet': summary,
                    'is_summary': True
                })
        except Exception as e:
            print(f"Sherlock search error: {e}")
            # Add error notification but continue
            rows.append({
                'title': f'[SHERLOCK] Error searching for {term}',
                'url': '#',
                'source': 'sherlock',
                'snippet': f'Sherlock integration error: {str(e)}',
                'is_error': True
            })
    
    return rows


def search_breach_databases(username: str) -> List[Dict]:
    """
    Search breach databases using EYE-D integration.
    Returns results from DeHashed, OSINT Industries, etc.
    """
    if not EYE_D_AVAILABLE:
        return []
    
    results = []
    
    try:
        # Initialize EYE-D handler
        handler = EyeDSearchHandler()
        
        # Run async search in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            eye_d_results = loop.run_until_complete(handler.search_username(username))
        finally:
            loop.close()
        
        # Process EYE-D results
        if eye_d_results and eye_d_results.get('results'):
            for result in eye_d_results['results']:
                source = result.get('source', 'unknown')
                data = result.get('data', {})
                
                # Create entry for each breach source
                if 'dehashed' in source.lower():
                    results.append({
                        'title': f'DeHashed Breach Data: {username}',
                        'url': f'https://dehashed.com/search?query={username}',
                        'source': 'dehashed',
                        'snippet': f'Found {len(data) if isinstance(data, list) else 1} breach records',
                        'data': data
                    })
                elif 'osint' in source.lower():
                    results.append({
                        'title': f'OSINT Industries: {username}',
                        'url': f'https://osint.industries/search/{username}',
                        'source': 'osint_industries',
                        'snippet': f'OSINT data available for {username}',
                        'data': data
                    })
        
        # Add extracted entities if available
        if eye_d_results and eye_d_results.get('entities'):
            entities_summary = f"Found {len(eye_d_results['entities'])} related entities"
            results.append({
                'title': f'Related Entities for {username}',
                'url': '#',
                'source': 'eye_d_entities',
                'snippet': entities_summary,
                'entities': eye_d_results['entities']
            })
            
    except Exception as e:
        print(f"Error searching breach databases: {e}")
    
    return results


def get_all_profile_urls(username: str) -> Dict[str, str]:
    """
    Generate all possible profile URLs for a username.
    Returns a dictionary mapping platform names to URLs.
    """
    return {
        # Major Social Media
        'twitter_x': f'https://x.com/{username}',
        'instagram': f'https://www.instagram.com/{username}',
        'threads': f'https://www.threads.com/@{username}',
        'facebook': f'https://www.facebook.com/{username}',
        
        # Developer & Tech
        'github': f'https://github.com/{username}',
        'gitlab': f'https://gitlab.com/{username}',
        'bitbucket': f'https://bitbucket.org/{username}',
        'stackoverflow': f'https://stackoverflow.com/users/{username}',
        'reddit': f'https://www.reddit.com/user/{username}',
        'hackernews': f'https://news.ycombinator.com/user?id={username}',
        
        # Video & Streaming
        'youtube': f'https://www.youtube.com/@{username}',
        'twitch': f'https://www.twitch.tv/{username}',
        'vimeo': f'https://vimeo.com/{username}',
        
        # Professional
        'linkedin': f'https://www.linkedin.com/in/{username}',
        'medium': f'https://medium.com/@{username}',
        'dev_to': f'https://dev.to/{username}',
        'behance': f'https://www.behance.net/{username}',
        'dribbble': f'https://dribbble.com/{username}',
        
        # Messaging & Communication
        'telegram': f'https://t.me/{username}',
        'discord': f'https://discord.gg/{username}',
        'slack': f'https://{username}.slack.com',
        'keybase': f'https://keybase.io/{username}',
        
        # Other Platforms
        'tiktok': f'https://www.tiktok.com/@{username}',
        'snapchat': f'https://www.snapchat.com/add/{username}',
        'pinterest': f'https://www.pinterest.com/{username}',
        'tumblr': f'https://{username}.tumblr.com',
        'flickr': f'https://www.flickr.com/photos/{username}',
        'soundcloud': f'https://soundcloud.com/{username}',
        'spotify': f'https://open.spotify.com/user/{username}',
        'patreon': f'https://www.patreon.com/{username}',
        'onlyfans': f'https://onlyfans.com/{username}',
        
        # Forums & Communities
        'producthunt': f'https://www.producthunt.com/@{username}',
        'angellist': f'https://angel.co/{username}',
        'goodreads': f'https://www.goodreads.com/{username}',
        
        # Code & Documentation
        'npm': f'https://www.npmjs.com/~{username}',
        'pypi': f'https://pypi.org/user/{username}',
        'dockerhub': f'https://hub.docker.com/u/{username}',
        'rubygems': f'https://rubygems.org/profiles/{username}',
        
        # Gaming
        'steam': f'https://steamcommunity.com/id/{username}',
        'xbox': f'https://account.xbox.com/profile?gamertag={username}',
        'psn': f'https://psnprofiles.com/{username}',
        
        # Breach Databases (via EYE-D)
        'dehashed': f'https://dehashed.com/search?query={username}',
        'haveibeenpwned': f'https://haveibeenpwned.com/account/{username}',
    }


def check_username_availability(username: str, platforms: Optional[List[str]] = None) -> Dict[str, str]:
    """
    Generate URLs to check username availability on specified platforms.
    If no platforms specified, returns top platforms.
    """
    all_urls = get_all_profile_urls(username)
    
    if platforms:
        # Return only requested platforms
        return {p: all_urls[p] for p in platforms if p in all_urls}
    else:
        # Return top platforms by default
        top_platforms = [
            'twitter_x', 'instagram', 'github', 'reddit', 'youtube',
            'linkedin', 'tiktok', 'facebook', 'telegram', 'discord'
        ]
        return {p: all_urls[p] for p in top_platforms if p in all_urls}


