"""
Startpage URL builder (no scraping). Builds general/news/video/images URLs.

Note: Startpage often presents CAPTCHAs; we only construct links.
"""

from urllib.parse import quote


def _q(query: str) -> str:
    return quote(f'"{query}"')


def sp_web(query: str) -> str:
    return f"https://www.startpage.com/sp/search?t=device&qsr=all&cat=web&language=english&lui=english&query={_q(query)}&sc=riEpm2YLmtY510"


def sp_news(query: str) -> str:
    return f"https://www.startpage.com/sp/search?lui=english&language=english&query={_q(query)}+&cat=news&sc=c3VXnFQl93BG10&t=device&segment=startpage.udog&abd=0&abe=0"


def sp_video(query: str) -> str:
    return f"https://www.startpage.com/sp/search?lui=english&language=english&query={_q(query)}+&cat=video&sc=kjIZ1HHQO5Vd10&t=device&segment=startpage.udog&abd=0&abe=0"


def sp_images(query: str) -> str:
    return f"https://www.startpage.com/sp/search?lui=english&language=english&query={_q(query)}+&cat=images&sc=OsslZKM3p4AA10&t=device&segment=startpage.udog&abd=0&abe=0"


def sp_shopping(query: str) -> str:
    """Startpage shopping vertical."""
    return f"https://www.startpage.com/sp/search?query={quote(query)}&t=device&lui=english&sc=mPPFxwM5gFzS10&cat=shopping&abd=0&abe=0"


def sp_web_qsr(query: str, qsr: str) -> str:
    """Startpage web with specific locale qsr (e.g., en_VN, en_ZA)."""
    return f"https://www.startpage.com/sp/search?t=device&qsr={quote(qsr)}&cat=web&language=english&lui=english&query={_q(query)}"


# Date-filtered web search (/do/search) helpers
def sp_web_with_date(query: str, period: str) -> str:
    """period: 'm' (past month) or 'y' (past year)."""
    if period == 'm':
        sc = '9AFlY7ICAwVQ10'
    elif period == 'y':
        sc = 'Ll1SHpVO75HF10'
    else:
        raise ValueError("period must be 'm' or 'y'")
    return (
        f"https://www.startpage.com/do/search?lui=english&language=english"
        f"&query={_q(query)}&cat=web&sc={sc}&t=device&segment=startpage.udog&with_date={period}"
    )


def sp_web_past_month(query: str) -> str:
    return sp_web_with_date(query, 'm')


def sp_web_past_year(query: str) -> str:
    return sp_web_with_date(query, 'y')


