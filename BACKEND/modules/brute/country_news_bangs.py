#!/usr/bin/env python3
"""
COUNTRY-SPECIFIC NEWS BANGS MODULE
Automatically searches country-specific news sources when:
1. Dominant language/country detected in results
2. loc: or lang: targeted searches

Integrates with auto_bang_search for country-specific news burst.
"""

import asyncio
import aiohttp
import json
import re
import time
from typing import Optional, List, Dict, Any, Set
from urllib.parse import quote_plus, urlparse
from html import unescape
from datetime import datetime
from pathlib import Path

# Country TLD mappings
COUNTRY_TLDS = {
    'de': ['.de'],
    'fr': ['.fr'],
    'uk': ['.uk', '.co.uk'],
    'es': ['.es'],
    'it': ['.it'],
    'nl': ['.nl'],
    'be': ['.be'],
    'at': ['.at'],
    'ch': ['.ch'],
    'pl': ['.pl'],
    'ru': ['.ru'],
    'br': ['.br'],
    'mx': ['.mx'],
    'ar': ['.ar'],
    'jp': ['.jp'],
    'kr': ['.kr'],
    'cn': ['.cn'],
    'au': ['.au'],
    'nz': ['.nz'],
    'ca': ['.ca'],
    'ie': ['.ie'],
    'se': ['.se'],
    'no': ['.no'],
    'dk': ['.dk'],
    'fi': ['.fi'],
    'pt': ['.pt'],
    'cz': ['.cz'],
    'hu': ['.hu'],
    'ro': ['.ro'],
    'gr': ['.gr'],
    'tr': ['.tr'],
    'in': ['.in'],
    'za': ['.za'],
    'il': ['.il'],
    'ua': ['.ua'],
}

# Language to country mappings (primary countries for each language)
LANGUAGE_TO_COUNTRIES = {
    'de': ['de', 'at', 'ch'],
    'fr': ['fr', 'be', 'ch', 'ca'],
    'es': ['es', 'mx', 'ar'],
    'it': ['it', 'ch'],
    'nl': ['nl', 'be'],
    'pt': ['pt', 'br'],
    'pl': ['pl'],
    'ru': ['ru', 'ua'],
    'ja': ['jp'],
    'ko': ['kr'],
    'zh': ['cn'],
    'sv': ['se'],
    'no': ['no'],
    'da': ['dk'],
    'fi': ['fi'],
    'cs': ['cz'],
    'hu': ['hu'],
    'ro': ['ro'],
    'el': ['gr'],
    'tr': ['tr'],
    'he': ['il'],
    'uk': ['ua'],
    'en': ['uk', 'au', 'ca', 'ie', 'nz', 'za'],  # English-speaking countries (non-US)
}

# Country-specific news bangs - extracted from all_bangs.json + curated additions
COUNTRY_NEWS_BANGS: Dict[str, Dict[str, str]] = {
    'de': {
        'spiegel': 'https://www.spiegel.de/suche/?suchbegriff={q}',
        'zeit': 'https://www.zeit.de/suche/index?q={q}',
        'faz': 'https://www.faz.net/suche/?query={q}',
        'sueddeutsche': 'https://www.sueddeutsche.de/news?search={q}',
        'bild': 'https://www.bild.de/suche.bild.html?query={q}',
        'welt': 'https://www.welt.de/suche/?query={q}',
        'handelsblatt': 'https://www.handelsblatt.com/suche/?query={q}',
        'tagesschau': 'https://www.tagesschau.de/suche2.html?searchText={q}',
        'br': 'https://www.br.de/suche/?query={q}',
        'ndr': 'https://www.ndr.de/suche11.html?query={q}',
        'wdr': 'https://www1.wdr.de/suche/index.jsp?q={q}',
        'focus': 'https://www.focus.de/suche/?q={q}',
        'stern': 'https://www.stern.de/suche/?q={q}',
        'manager_magazin': 'https://www.manager-magazin.de/suche/?suchbegriff={q}',
        'wirtschaftswoche': 'https://www.wiwo.de/suche/?search={q}',
        'heise': 'https://www.heise.de/suche/?q={q}',
        'golem': 'https://www.golem.de/suchmaschine/?q={q}',
        't3n': 'https://t3n.de/suche/?q={q}',
    },
    'fr': {
        'lemonde': 'https://www.lemonde.fr/recherche/?search_keywords={q}',
        'lefigaro': 'https://recherche.lefigaro.fr/recherche/{q}/',
        'liberation': 'https://www.liberation.fr/recherche/?query={q}',
        'leparisien': 'https://www.leparisien.fr/recherche/?query={q}',
        'france24': 'https://www.france24.com/fr/recherche/?query={q}',
        'bfmtv': 'https://www.bfmtv.com/recherche/?query={q}',
        'lexpress': 'https://www.lexpress.fr/recherche/?q={q}',
        'nouvelobs': 'https://www.nouvelobs.com/recherche?q={q}',
        'lesechos': 'https://www.lesechos.fr/recherche?q={q}',
        'latribune': 'https://www.latribune.fr/recherche?q={q}',
        'mediapart': 'https://www.mediapart.fr/search?search_word={q}',
        'huffpost_fr': 'https://www.huffingtonpost.fr/search?q={q}',
        'rfi': 'https://www.rfi.fr/fr/recherche/?query={q}',
    },
    'uk': {
        'bbc': 'https://www.bbc.co.uk/search?q={q}',
        'guardian': 'https://www.theguardian.com/search?q={q}',
        'telegraph': 'https://www.telegraph.co.uk/search/?q={q}',
        'times': 'https://www.thetimes.co.uk/search?q={q}',
        'independent': 'https://www.independent.co.uk/service/search?q={q}',
        'dailymail': 'https://www.dailymail.co.uk/home/search.html?s=&authornamef=&sel=site&searchPhrase={q}',
        'mirror': 'https://www.mirror.co.uk/search?term={q}',
        'express': 'https://www.express.co.uk/search?s={q}',
        'sun': 'https://www.thesun.co.uk/?s={q}',
        'ft': 'https://www.ft.com/search?q={q}',
        'economist': 'https://www.economist.com/search?q={q}',
        'sky': 'https://news.sky.com/search?term={q}',
        'itv': 'https://www.itv.com/news/search?q={q}',
        'channel4': 'https://www.channel4.com/news/search?q={q}',
    },
    'es': {
        'elpais': 'https://elpais.com/buscador/?qt={q}',
        'elmundo': 'https://www.elmundo.es/buscador.html?q={q}',
        'abc': 'https://www.abc.es/hemeroteca/buscador-abc/?q={q}',
        'lavanguardia': 'https://www.lavanguardia.com/buscar?q={q}',
        'elconfidencial': 'https://www.elconfidencial.com/buscar/?text={q}',
        'elperiodico': 'https://www.elperiodico.com/es/buscador/?text={q}',
        '20minutos': 'https://www.20minutos.es/buscar/?q={q}',
        'expansion': 'https://www.expansion.com/buscador/?q={q}',
        'rtve': 'https://www.rtve.es/buscador/?q={q}',
    },
    'it': {
        'corriere': 'https://www.corriere.it/ricerca/?q={q}',
        'repubblica': 'https://ricerca.repubblica.it/ricerca/repubblica?query={q}',
        'lastampa': 'https://www.lastampa.it/ricerca?query={q}',
        'ilsole24ore': 'https://www.ilsole24ore.com/ricerca?q={q}',
        'ansa': 'https://www.ansa.it/sito/search/search.shtml?query={q}',
        'ilmessaggero': 'https://www.ilmessaggero.it/ricerca/?query={q}',
        'ilgiornale': 'https://www.ilgiornale.it/ricerca/{q}/',
        'gazzetta': 'https://www.gazzetta.it/ricerca/?q={q}',
        'fanpage': 'https://www.fanpage.it/search/?q={q}',
        'rainews': 'https://www.rainews.it/ricerca?query={q}',
    },
    'nl': {
        'telegraaf': 'https://www.telegraaf.nl/zoeken?query={q}',
        'ad': 'https://www.ad.nl/zoeken?query={q}',
        'volkskrant': 'https://www.volkskrant.nl/zoeken?query={q}',
        'nrc': 'https://www.nrc.nl/search/?q={q}',
        'nos': 'https://nos.nl/zoeken?q={q}',
        'rtv': 'https://www.rtv.nl/zoeken?q={q}',
        'nu': 'https://www.nu.nl/zoeken?q={q}',
        'fd': 'https://fd.nl/zoeken?q={q}',
    },
    'be': {
        'standaard': 'https://www.standaard.be/zoeken?keyword={q}',
        'nieuwsblad': 'https://www.nieuwsblad.be/zoeken?keyword={q}',
        'hln': 'https://www.hln.be/zoeken?keyword={q}',
        'knack': 'https://www.knack.be/zoek/?q={q}',
        'lesoir': 'https://www.lesoir.be/search?keywords={q}',
        'lalibre': 'https://www.lalibre.be/search?q={q}',
        'rtbf': 'https://www.rtbf.be/recherche?q={q}',
        'vrt': 'https://www.vrt.be/vrtnws/nl/zoeken/?q={q}',
    },
    'at': {
        'derstandard': 'https://www.derstandard.at/suche?q={q}',
        'kurier': 'https://kurier.at/suche?q={q}',
        'krone': 'https://www.krone.at/suche?q={q}',
        'orf': 'https://orf.at/suche/?q={q}',
        'diepresse': 'https://www.diepresse.com/suche?query={q}',
        'profil': 'https://www.profil.at/suche?q={q}',
    },
    'ch': {
        'nzz': 'https://www.nzz.ch/suche?q={q}',
        'tagesanzeiger': 'https://www.tagesanzeiger.ch/search?q={q}',
        'blick': 'https://www.blick.ch/search?q={q}',
        '20min_ch': 'https://www.20min.ch/search?q={q}',
        'srf': 'https://www.srf.ch/suche?q={q}',
        'rts': 'https://www.rts.ch/recherche/?q={q}',
        'swissinfo': 'https://www.swissinfo.ch/eng/search?q={q}',
        'letemps': 'https://www.letemps.ch/recherche?query={q}',
    },
    'pl': {
        'gazeta': 'https://szukaj.wyborcza.pl/{q}',
        'onet': 'https://szukaj.onet.pl/?q={q}',
        'wp': 'https://szukaj.wp.pl/szukaj.html?q={q}',
        'tvn24': 'https://tvn24.pl/szukaj?query={q}',
        'interia': 'https://szukaj.interia.pl/?q={q}',
        'rmf': 'https://www.rmf24.pl/szukaj?q={q}',
        'polsat': 'https://www.polsatnews.pl/search/?q={q}',
    },
    'ru': {
        'ria': 'https://ria.ru/search/?query={q}',
        'tass': 'https://tass.ru/search?searchStr={q}',
        'kommersant': 'https://www.kommersant.ru/search/results?search={q}',
        'rbc': 'https://www.rbc.ru/search/?query={q}',
        'lenta': 'https://lenta.ru/search?query={q}',
        'gazeta_ru': 'https://www.gazeta.ru/search/{q}/',
        'meduza': 'https://meduza.io/search?term={q}',
        'novaya': 'https://novayagazeta.ru/search?q={q}',
    },
    'br': {
        'folha': 'https://search.folha.uol.com.br/?q={q}',
        'globo': 'https://g1.globo.com/busca/?q={q}',
        'estadao': 'https://busca.estadao.com.br/?q={q}',
        'uol': 'https://busca.uol.com.br/result?q={q}',
        'r7': 'https://www.r7.com/busca?q={q}',
        'band': 'https://www.band.uol.com.br/busca?q={q}',
        'bbc_brasil': 'https://www.bbc.com/portuguese/search?q={q}',
    },
    'jp': {
        'nhk': 'https://www.nhk.or.jp/news/html/search/?q={q}',
        'asahi': 'https://www.asahi.com/search/?q={q}',
        'mainichi': 'https://mainichi.jp/search?q={q}',
        'yomiuri': 'https://www.yomiuri.co.jp/search/?keyword={q}',
        'nikkei': 'https://www.nikkei.com/search?keyword={q}',
        'sankei': 'https://www.sankei.com/search/?keyword={q}',
        'japan_times': 'https://www.japantimes.co.jp/?s={q}',
    },
    'kr': {
        'chosun': 'https://search.chosun.com/search/news.search?query={q}',
        'joongang': 'https://news.joins.com/search?keyword={q}',
        'donga': 'https://www.donga.com/news/search?query={q}',
        'hani': 'https://search.hani.co.kr/Search?command=query&media=news&query={q}',
        'kbs': 'https://search.kbs.co.kr/search.html?query={q}',
        'yonhap': 'https://www.yna.co.kr/search/index?query={q}',
    },
    'cn': {
        'xinhua': 'http://so.xinhuanet.com/s?q={q}',
        'chinadaily': 'https://newssearch.chinadaily.com.cn/search?query={q}',
        'scmp': 'https://www.scmp.com/search/{q}',
        'cgtn': 'https://www.cgtn.com/search?keyword={q}',
        'caixin': 'https://search.caixin.com/search/search.jsp?keyword={q}',
    },
    'au': {
        'abc_au': 'https://www.abc.net.au/news/search/?query={q}',
        'smh': 'https://www.smh.com.au/search?text={q}',
        'theage': 'https://www.theage.com.au/search?text={q}',
        'australian': 'https://www.theaustralian.com.au/search-results?q={q}',
        'news_com_au': 'https://www.news.com.au/search-results?q={q}',
        'sbs': 'https://www.sbs.com.au/news/search?query={q}',
        'guardian_au': 'https://www.theguardian.com/au/search?q={q}',
        '9news': 'https://www.9news.com.au/search?q={q}',
    },
    'ca': {
        'cbc': 'https://www.cbc.ca/search?q={q}',
        'globalnews': 'https://globalnews.ca/?s={q}',
        'ctv': 'https://www.ctvnews.ca/search?q={q}',
        'globe_mail': 'https://www.theglobeandmail.com/search/?q={q}',
        'national_post': 'https://nationalpost.com/?s={q}',
        'toronto_star': 'https://www.thestar.com/search.html?q={q}',
        'montreal_gazette': 'https://montrealgazette.com/?s={q}',
        'bnn': 'https://www.bnnbloomberg.ca/search?q={q}',
    },
    'se': {
        'svd': 'https://www.svd.se/sok?q={q}',
        'dn': 'https://www.dn.se/sok/?q={q}',
        'aftonbladet': 'https://www.aftonbladet.se/sok?query={q}',
        'expressen': 'https://www.expressen.se/sok/?q={q}',
        'svt': 'https://www.svt.se/sok?q={q}',
        'sr': 'https://sverigesradio.se/sok?q={q}',
    },
    'no': {
        'vg': 'https://www.vg.no/sok?q={q}',
        'dagbladet': 'https://www.dagbladet.no/sok?q={q}',
        'aftenposten': 'https://www.aftenposten.no/sok?q={q}',
        'nrk': 'https://www.nrk.no/sok/?q={q}',
        'e24': 'https://e24.no/sok?q={q}',
    },
    'dk': {
        'dr': 'https://www.dr.dk/soeg?query={q}',
        'tv2_dk': 'https://nyheder.tv2.dk/search?q={q}',
        'berlingske': 'https://www.berlingske.dk/soeg?q={q}',
        'politiken': 'https://politiken.dk/soeg/?q={q}',
        'jyllands_posten': 'https://jyllands-posten.dk/soeg/?q={q}',
        'bt': 'https://www.bt.dk/soeg?q={q}',
    },
    'fi': {
        'yle': 'https://yle.fi/haku?query={q}',
        'hs': 'https://www.hs.fi/haku/?query={q}',
        'iltalehti': 'https://www.iltalehti.fi/haku?q={q}',
        'iltasanomat': 'https://www.is.fi/haku/?query={q}',
        'mtv': 'https://www.mtvuutiset.fi/haku?q={q}',
    },
    'in': {
        'times_of_india': 'https://timesofindia.indiatimes.com/topic/{q}',
        'hindustan_times': 'https://www.hindustantimes.com/search?q={q}',
        'indian_express': 'https://indianexpress.com/?s={q}',
        'ndtv': 'https://www.ndtv.com/search?searchtext={q}',
        'thehindu': 'https://www.thehindu.com/search/?q={q}',
        'zee_news': 'https://zeenews.india.com/search?search={q}',
        'india_today': 'https://www.indiatoday.in/search/{q}',
        'livemint': 'https://www.livemint.com/Search/Link/Keyword/{q}',
    },
    'za': {
        'news24': 'https://www.news24.com/search?query={q}',
        'timeslive': 'https://www.timeslive.co.za/search?q={q}',
        'ewn': 'https://ewn.co.za/?s={q}',
        'iol': 'https://www.iol.co.za/search?q={q}',
        'dailymaverick': 'https://www.dailymaverick.co.za/?s={q}',
    },
    'il': {
        'haaretz': 'https://www.haaretz.com/search?q={q}',
        'jpost': 'https://www.jpost.com/search?q={q}',
        'timesofisrael': 'https://www.timesofisrael.com/?s={q}',
        'ynet': 'https://www.ynetnews.com/search?q={q}',
        'i24': 'https://www.i24news.tv/en/search/{q}',
    },
    'ie': {
        'rte': 'https://www.rte.ie/search/?q={q}',
        'irishtimes': 'https://www.irishtimes.com/search?q={q}',
        'independent_ie': 'https://www.independent.ie/search/?q={q}',
        'thejournal': 'https://www.thejournal.ie/search/?q={q}',
        'irishmirror': 'https://www.irishmirror.ie/search?term={q}',
    },
    'nz': {
        'nzherald': 'https://www.nzherald.co.nz/search/{q}/',
        'stuff': 'https://www.stuff.co.nz/search?q={q}',
        'rnz': 'https://www.rnz.co.nz/search/results?query={q}',
        'newshub': 'https://www.newshub.co.nz/search.html?q={q}',
        '1news': 'https://www.1news.co.nz/search?q={q}',
    },
}


def get_countries_for_language(lang: str) -> List[str]:
    """Get list of country codes for a language"""
    lang_lower = lang.lower()[:2]
    return LANGUAGE_TO_COUNTRIES.get(lang_lower, [])


def get_country_from_tld(domain: str) -> Optional[str]:
    """Extract country code from domain TLD"""
    domain_lower = domain.lower()
    for country, tlds in COUNTRY_TLDS.items():
        for tld in tlds:
            if domain_lower.endswith(tld):
                return country
    return None


def detect_dominant_country(domains: List[str], min_ratio: float = 0.15) -> Optional[str]:
    """
    Detect if a single country dominates the domain list.
    Returns country code if >= min_ratio of domains are from that country.
    """
    country_counts: Dict[str, int] = {}
    total = 0

    for domain in domains:
        country = get_country_from_tld(domain)
        if country:
            country_counts[country] = country_counts.get(country, 0) + 1
            total += 1

    if total < 5:  # Need at least 5 country domains to detect
        return None

    for country, count in sorted(country_counts.items(), key=lambda x: -x[1]):
        if count / total >= min_ratio:
            return country

    return None


def get_country_news_bangs(country: str) -> Dict[str, str]:
    """Get news bangs for a specific country"""
    return COUNTRY_NEWS_BANGS.get(country.lower(), {})


def get_all_country_bangs_for_languages(languages: List[str]) -> Dict[str, Dict[str, str]]:
    """Get all news bangs for countries associated with given languages"""
    result = {}
    for lang in languages:
        countries = get_countries_for_language(lang)
        for country in countries:
            if country not in result:
                bangs = get_country_news_bangs(country)
                if bangs:
                    result[country] = bangs
    return result


# Import from auto_bang_search for common utilities
from .auto_bang_search import clean_html_to_text, extract_snippets, extract_title


async def check_country_bang(
    session: aiohttp.ClientSession,
    name: str,
    url_template: str,
    query: str,
    keywords: List[str],
    timeout: float,
    country: str,
) -> Optional[Dict[str, Any]]:
    """Check a single country news bang source for keyword matches"""
    url = url_template.replace('{q}', quote_plus(query))
    domain = urlparse(url).netloc.replace('www.', '')

    try:
        start_time = time.time()
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True
        ) as resp:
            if resp.status not in [200, 301, 302]:
                return None

            chunk = await resp.content.read(100000)  # 100KB
            html = chunk.decode('utf-8', errors='ignore')
            elapsed_ms = int((time.time() - start_time) * 1000)

            # Check for keyword matches
            html_lower = html.lower()
            matches = [kw for kw in keywords if kw.lower() in html_lower]

            if not matches:
                return None

            # Extract metadata
            title = extract_title(html) or f"{name} - {query}"
            snippets = extract_snippets(html, keywords)

            return {
                'bang': name,
                'url': url,
                'domain': domain,
                'title': title,
                'source_type': 'country_news',
                'country': country,
                'matched_keywords': matches,
                'snippets': snippets,
                'size_bytes': len(chunk),
                'response_ms': elapsed_ms,
                'fetched_at': datetime.utcnow().isoformat(),
            }

    except Exception as e:
        return None


async def scan_country_news_bangs(
    query: str,
    country: str,
    timeout: float = 4.0,
    max_concurrent: int = 30,
) -> List[Dict[str, Any]]:
    """Scan country-specific news bangs in parallel"""
    bangs = get_country_news_bangs(country)
    if not bangs:
        return []

    # Build keyword list - exact phrase
    clean = query.replace('"', '').replace("'", '')
    keywords = [clean]

    connector = aiohttp.TCPConnector(limit=max_concurrent, limit_per_host=3)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': f'{country},en;q=0.9',
    }

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        tasks = [
            check_country_bang(session, name, url_template, query, keywords, timeout, country)
            for name, url_template in bangs.items()
        ]
        results = await asyncio.gather(*tasks)

    return [r for r in results if r is not None]


async def country_news_burst(
    query: str,
    countries: List[str],
    timeout: float = 4.0,
    on_result: Optional[callable] = None,
) -> Dict[str, Any]:
    """
    Run country-specific news burst search across multiple countries.
    Called when dominant country detected or loc:/lang: search triggered.
    """
    start_time = time.time()

    results = {
        'query': query,
        'countries': countries,
        'timestamp': datetime.utcnow().isoformat(),
        'country_results': {},
        'total_matches': 0,
        'total_sources': 0,
        'elapsed_seconds': 0,
    }

    # Run searches for each country in parallel
    tasks = []
    for country in countries:
        bangs = get_country_news_bangs(country)
        if bangs:
            tasks.append((country, scan_country_news_bangs(query, country, timeout)))
            results['total_sources'] += len(bangs)

    if tasks:
        gathered = await asyncio.gather(*[t[1] for t in tasks])
        for i, (country, _) in enumerate(tasks):
            country_matches = gathered[i]
            results['country_results'][country] = country_matches
            results['total_matches'] += len(country_matches)

            # Call streaming callback if provided
            if on_result:
                for r in country_matches:
                    on_result(r)

    results['elapsed_seconds'] = round(time.time() - start_time, 2)
    return results


def normalize_country_result_to_search_result(result: Dict[str, Any], query: str) -> Dict[str, Any]:
    """Convert country news result to standard search result format"""
    return {
        'url': result['url'],
        'title': result.get('title', result['domain']),
        'snippet': result['snippets'][0] if result.get('snippets') else '',
        'snippets': result.get('snippets', []),
        'domain': result['domain'],
        'source': f"country_news:{result['country']}:{result['bang']}",
        'engine': f"NEWS_{result['country'].upper()}",
        'category': 'country_news',
        'country': result['country'],
        'bang_source': result['bang'],
        'matched_keywords': result.get('matched_keywords', []),
        'fetched_at': result.get('fetched_at'),
        'response_ms': result.get('response_ms'),
        'needs_scrape': True,
        'scrape_priority': 'high',
    }


# CLI interface
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Country News Bang Search')
    parser.add_argument('query', help='Search query')
    parser.add_argument('--countries', '-c', nargs='+', default=['de'], help='Country codes (de, fr, uk, etc.)')
    parser.add_argument('--timeout', '-t', type=float, default=4.0, help='Timeout per source')
    args = parser.parse_args()

    print(f"\n🌍 COUNTRY NEWS SEARCH: \"{args.query}\"")
    print(f"   Countries: {', '.join(args.countries)}")

    for c in args.countries:
        bangs = get_country_news_bangs(c)
        print(f"   {c.upper()}: {len(bangs)} sources")
    print()

    results = asyncio.run(country_news_burst(args.query, args.countries, args.timeout))

    print(f"⚡ Completed in {results['elapsed_seconds']}s")
    print(f"✅ {results['total_matches']} matches from {results['total_sources']} sources\n")

    for country, matches in results['country_results'].items():
        if matches:
            print(f"🗞️  {country.upper()} ({len(matches)} matches):")
            for r in matches[:5]:
                print(f"   {r['bang']:18} → {r['domain']} ({r['response_ms']}ms)")
            if len(matches) > 5:
                print(f"   ... and {len(matches) - 5} more")
            print()
