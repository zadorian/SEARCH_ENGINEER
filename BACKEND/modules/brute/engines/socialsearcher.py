import requests
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any

class SocialSearcher:
    code = "SS"
    name = "social_searcher"
    def __init__(self):
        self.api_key = os.getenv('SOCIAL_SEARCHER_API_KEY', 'decdab3ea83f1df1c6386f620a6ca72f')
        self.base_urls = [
            'https://www.social-searcher.com/api/v2/search',
            'https://api.social-searcher.com/v2/search',
            'https://social-searcher.com/api/v2/search'
        ]
        self.base_url = self.base_urls[0]
        self.platform_mapping = {
            'reddit': 'reddit', 'reddit.com': 'reddit',
            'youtube': 'youtube', 'youtube.com': 'youtube', 'yt': 'youtube',
            'vk': 'vkontakte', 'vk.com': 'vkontakte', 'vk.ru': 'vkontakte', 'vkontakte': 'vkontakte',
            'tumblr': 'tumblr', 'tumblr.com': 'tumblr', 'web': 'web'
        }

    def parse_query(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        parts = query.split(':')
        if len(parts) == 2:
            search_term = parts[0].strip()
            platform = parts[1].strip().lower().rstrip('?')
            if platform in ['twitter', 'twitter.com', 'x', 'x.com']:
                return None, None
            platform = self.platform_mapping.get(platform)
            if platform is None:
                return None, None
            return search_term, platform
        return query.strip(), None

    def search(self, query: str, content_type: str = None, lang: str = None, max_results: int = 100) -> List[Dict[str, Any]]:
        exact_phrase = None
        if query.startswith('"') and query.endswith('"'):
            exact_phrase = query[1:-1].lower()
        search_term, platform = self.parse_query(query)
        if search_term is None:
            return []
        all_posts: List[Dict[str, Any]] = []
        for base_url in self.base_urls:
            page = 0
            requestid = None
            limit = min(100, max_results)
            while len(all_posts) < max_results:
                params = {
                    'q': search_term,
                    'key': self.api_key,
                    'network': platform if platform else 'all',
                    'limit': limit,
                    'page': page
                }
                if content_type:
                    params['type'] = content_type
                if lang:
                    params['lang'] = lang
                if requestid:
                    params['requestid'] = requestid
                try:
                    response = requests.get(base_url, params=params, timeout=10)
                    if response.status_code != 200:
                        break
                    data = response.json()
                    posts = data.get('posts', [])
                    if not posts:
                        break
                    if exact_phrase:
                        filtered_posts = []
                        for post in posts:
                            text = (post.get('text', '') or '').lower()
                            title = (post.get('title', '') or '').lower()
                            if exact_phrase in text or exact_phrase in title:
                                filtered_posts.append(post)
                        posts = filtered_posts
                    all_posts.extend(posts)
                    if len(all_posts) >= max_results:
                        all_posts = all_posts[:max_results]
                        break
                    page += 1
                    meta = data.get('meta', {})
                    requestid = meta.get('requestid')
                    if not requestid:
                        break
                except requests.RequestException:
                    break
                except Exception:
                    break
            if all_posts:
                break
        if not all_posts:
            return []
        return all_posts

__all__ = ['SocialSearcher']


