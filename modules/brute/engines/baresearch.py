"""
BareSearch URL generator (no scraping).

Builds category URLs for baresearch.org for different verticals.
"""

from urllib.parse import quote


def _q(query: str) -> str:
    return quote(f'"{query}"')


def bare_general(query: str) -> str:
    return f"https://baresearch.org/search?q={_q(query)}&language=auto&time_range=&safesearch=0&categories=general"


def bare_videos(query: str) -> str:
    return f"https://baresearch.org/search?q={_q(query)}&language=auto&time_range=&safesearch=0&categories=videos"


def bare_news(query: str) -> str:
    return f"https://baresearch.org/search?q={_q(query)}&language=auto&time_range=&safesearch=0&categories=news"


def bare_music(query: str) -> str:
    return f"https://baresearch.org/search?q={_q(query)}&language=auto&time_range=&safesearch=0&categories=music"


def bare_it(query: str) -> str:
    return f"https://baresearch.org/search?q={quote(query)}&language=auto&time_range=&safesearch=0&categories=it"


def bare_science(query: str) -> str:
    return f"https://baresearch.org/search?q={quote(query)}&language=auto&time_range=&safesearch=0&categories=science"


def bare_files(query: str) -> str:
    return f"https://baresearch.org/search?q={quote(query)}&language=auto&time_range=&safesearch=0&categories=files"


# Social media category with optional pagination; username discovery helper
def bare_social(query: str, page: int = 1, exact: bool = False) -> str:
    q = _q(query) if exact else quote(query)
    page_param = f"&pageno={int(page)}" if page and int(page) > 1 else ""
    return f"https://baresearch.org/search?q={q}&language=auto&time_range=&safesearch=0{page_param}&categories=social+media"


def bare_social_media(query: str, page: int = 1) -> str:
    p = f"&pageno={int(page)}" if page and page != 1 else ""
    return f"https://baresearch.org/search?q={quote(query)}&language=auto&time_range=&safesearch=0{p}&categories=social+media"


