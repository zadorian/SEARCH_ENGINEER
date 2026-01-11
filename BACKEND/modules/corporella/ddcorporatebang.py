"""
company_bang_search.py  –  helper for corporate_search.py
Run a query through all major company‑registry DuckDuckGo bangs and
return a dict {bang: target_url}.  For quick manual follow‑up each
bang is expanded to its bang‑redirect URL (HTML not downloaded).

Usage
-----
from company_bang_search import run_company_bang_searches
urls = run_company_bang_searches("Acme Corp")
for bang, url in urls.items():
    print(bang, "→", url)
"""

import urllib.parse
import time
import logging

# Complete bang list focused on company registries & filings
COMPANY_BANGS = [
    # United States
    "sec", "edgar", "edgar10k", "nysecik",
    # Canada
    "sedar", "sedi", "icgc",
    # United Kingdom
    "companieshouse", "ch", "beta",
    # Australia & NZ
    "asic", "abn", "asicnz", "nzbn",
    # Western Europe
    "unternehmensregister", "handelsregister",  # Germany
    "kvk", "bkr",                               # Netherlands
    "cvr", "ahr",                               # Denmark
    "zefix",                                    # Switzerland
    "rcsl",                                     # Luxembourg
    "firmenbuch", "ainfo",                      # Austria
    "bbr",                                      # Belgium
    "ebr",                                      # EU gateway
    "info",                                     # Finland ytj.fi
    # Southern Europe
    "infogreffe", "borme",                      # France / Spain
    "grcomp",                                   # Greece GEMI
    # Central & Eastern Europe
    "crcr",                                     # Czech OR
    "dps",                                      # Slovakia ORSR
    "analiza", "krs",                           # Poland KRS
    # Nordics (additional)
    "brreg",                                    # Norway
    # Asia–Pacific
    "hkcr", "taiwancomp",                       # HK / Taiwan
    "singbiz",                                  # Singapore ACRA BizFile
    "mca", "indiamca",                          # India MCA21
    "taiwancomp",                               # Taiwan re‑listed for completeness
    # Latin America
    "cnpj", "brasilcnpj",                       # Brazil Receita
    # Africa
    "zacipc",                                   # South‑Africa CIPC
    # Offshore / Islands
    "asicisl",                                  # Isle of Man FSC
    # Middle East
    "sedin",                                    # Israel Registrar
    # Russia / CIS
    "rusprofile", "egrul",                      # Russia company DBs
    # Aggregators / paywall profiles
    "bvd", "orbis", "dnb",
    # Misc investigative helpers
    "whois", "dnstw",                           # domain WHOIS shortcuts
    ]

DDG_BANG_ENDPOINT = "https://duckduckgo.com/?q={}"

def _bang_url(bang: str, query: str) -> str:
    encoded = urllib.parse.quote_plus(f"!{bang} {query}")
    return DDG_BANG_ENDPOINT.format(encoded)

def run_company_bang_searches(query: str, delay: float = 0.0) -> dict[str, str]:
    """
    Build redirect URLs for all company‑registry bangs using *query*.

    Parameters
    ----------
    query : str
        The company name or keyword the user entered.
    delay : float, optional
        Seconds to sleep between URL generations.  Leave 0.0 for
        immediate; set >0 if you feed these into a real browser to
        avoid rate‑limiting.

    Returns
    -------
    dict
        Mapping of bang (str) → pre‑formed DuckDuckGo bang URL (str).
    """
    urls = {}
    for bang in COMPANY_BANGS:
        urls[bang] = _bang_url(bang, query)
        if delay:
            time.sleep(delay)
    return urls

if __name__ == "__main__":
    # quick CLI for ad‑hoc use
    import sys, json
    if len(sys.argv) < 2:
        print("Usage: python company_bang_search.py '<company name>'")
        sys.exit(1)
    print(json.dumps(run_company_bang_searches(" ".join(sys.argv[1:])), indent=2))
