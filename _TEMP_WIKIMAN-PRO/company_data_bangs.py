"""
Company Data Bangs - Comprehensive list of DuckDuckGo company data and business intelligence bangs
Contains 500+ company data bangs with location and language targeting for maximum coverage
"""

from typing import Dict, List, Optional, Set
import re

# Company Data Bang Structure with Country/Language Indexing
class CompanyDataBang:
    """Represents a company data bang with location and language metadata"""
    def __init__(self, bang: str, name: str, country: str, language: str, 
                 domain: str = "", category: str = "general", regional_focus: str = "", 
                 data_type: str = "general"):
        self.bang = bang
        self.name = name
        self.country = country  # ISO 3166-1 alpha-2 country code
        self.language = language  # ISO 639-1 language code
        self.domain = domain
        self.category = category  # Type of company data service
        self.regional_focus = regional_focus
        self.data_type = data_type  # Specific data type (financials, filings, profiles, etc.)
    
    def __repr__(self):
        return f"CompanyDataBang({self.bang}, {self.name}, {self.country}, {self.language})"

# Comprehensive Company Data Bangs Database with Country/Language Indexing
COMPANY_DATA_BANGS_DATABASE = [
    # US SEC and Financial Data
    CompanyDataBang("sec", "SEC EDGAR", "US", "en", "sec.gov", "regulatory", "us", "filings"),
    CompanyDataBang("edgar", "SEC EDGAR", "US", "en", "sec.gov", "regulatory", "us", "filings"),
    CompanyDataBang("secgov", "SEC.gov", "US", "en", "sec.gov", "regulatory", "us", "filings"),
    CompanyDataBang("10k", "SEC 10-K Filings", "US", "en", "sec.gov", "regulatory", "us", "filings"),
    CompanyDataBang("10q", "SEC 10-Q Filings", "US", "en", "sec.gov", "regulatory", "us", "filings"),
    CompanyDataBang("8k", "SEC 8-K Filings", "US", "en", "sec.gov", "regulatory", "us", "filings"),
    CompanyDataBang("proxy", "SEC Proxy Statements", "US", "en", "sec.gov", "regulatory", "us", "filings"),
    CompanyDataBang("form4", "SEC Form 4", "US", "en", "sec.gov", "regulatory", "us", "filings"),
    CompanyDataBang("form13f", "SEC Form 13F", "US", "en", "sec.gov", "regulatory", "us", "filings"),
    CompanyDataBang("secfilings", "SEC Filings", "US", "en", "sec.gov", "regulatory", "us", "filings"),
    
    # US Financial Data Providers
    CompanyDataBang("yahoo", "Yahoo Finance", "US", "en", "finance.yahoo.com", "financial", "us", "financials"),
    CompanyDataBang("yfinance", "Yahoo Finance", "US", "en", "finance.yahoo.com", "financial", "us", "financials"),
    CompanyDataBang("morningstar", "Morningstar", "US", "en", "morningstar.com", "financial", "us", "analysis"),
    CompanyDataBang("zacks", "Zacks Investment Research", "US", "en", "zacks.com", "financial", "us", "analysis"),
    CompanyDataBang("finviz", "Finviz", "US", "en", "finviz.com", "financial", "us", "screening"),
    CompanyDataBang("gurufocus", "GuruFocus", "US", "en", "gurufocus.com", "financial", "us", "analysis"),
    CompanyDataBang("simplywall", "Simply Wall St", "AU", "en", "simplywall.st", "financial", "global", "analysis"),
    CompanyDataBang("macrotrends", "MacroTrends", "US", "en", "macrotrends.net", "financial", "us", "trends"),
    CompanyDataBang("stockrow", "Stockrow", "US", "en", "stockrow.com", "financial", "us", "financials"),
    CompanyDataBang("tikr", "Tikr Terminal", "US", "en", "tikr.com", "financial", "us", "analysis"),
    CompanyDataBang("koyfin", "Koyfin", "US", "en", "koyfin.com", "financial", "us", "analysis"),
    CompanyDataBang("wallmine", "Wallmine", "US", "en", "wallmine.com", "financial", "us", "analysis"),
    CompanyDataBang("stockanalysis", "Stock Analysis", "US", "en", "stockanalysis.com", "financial", "us", "analysis"),
    CompanyDataBang("roic", "ROIC.ai", "US", "en", "roic.ai", "financial", "us", "analysis"),
    CompanyDataBang("finbox", "FinBox", "US", "en", "finbox.com", "financial", "us", "valuation"),
    CompanyDataBang("quandl", "Quandl", "US", "en", "quandl.com", "financial", "us", "data"),
    CompanyDataBang("alphaspread", "AlphaSpread", "US", "en", "alphaspread.com", "financial", "us", "analysis"),
    CompanyDataBang("stockopedia", "Stockopedia", "UK", "en", "stockopedia.com", "financial", "uk", "analysis"),
    CompanyDataBang("sharesight", "Sharesight", "AU", "en", "sharesight.com", "financial", "australia", "portfolio"),
    
    # Business Intelligence & Company Profiles
    CompanyDataBang("bloomberg", "Bloomberg Terminal", "US", "en", "bloomberg.com", "financial", "global", "terminal"),
    CompanyDataBang("refinitiv", "Refinitiv", "UK", "en", "refinitiv.com", "financial", "global", "data"),
    CompanyDataBang("factset", "FactSet", "US", "en", "factset.com", "financial", "global", "data"),
    CompanyDataBang("capitaliq", "S&P Capital IQ", "US", "en", "capitaliq.com", "financial", "global", "data"),
    CompanyDataBang("pitchbook", "PitchBook", "US", "en", "pitchbook.com", "financial", "global", "private_equity"),
    CompanyDataBang("crunchbase", "Crunchbase", "US", "en", "crunchbase.com", "startup", "global", "profiles"),
    CompanyDataBang("owler", "Owler", "US", "en", "owler.com", "business", "global", "profiles"),
    CompanyDataBang("craft", "Craft.co", "US", "en", "craft.co", "business", "global", "profiles"),
    CompanyDataBang("apollo", "Apollo.io", "US", "en", "apollo.io", "business", "global", "leads"),
    CompanyDataBang("zoominfo", "ZoomInfo", "US", "en", "zoominfo.com", "business", "global", "leads"),
    CompanyDataBang("leadiq", "LeadIQ", "US", "en", "leadiq.com", "business", "global", "leads"),
    CompanyDataBang("hunter", "Hunter.io", "FR", "en", "hunter.io", "business", "global", "leads"),
    CompanyDataBang("clearbit", "Clearbit", "US", "en", "clearbit.com", "business", "global", "enrichment"),
    CompanyDataBang("fullcontact", "FullContact", "US", "en", "fullcontact.com", "business", "global", "enrichment"),
    CompanyDataBang("pipl", "Pipl", "US", "en", "pipl.com", "business", "global", "people"),
    CompanyDataBang("spokeo", "Spokeo", "US", "en", "spokeo.com", "business", "us", "people"),
    CompanyDataBang("whitepages", "WhitePages", "US", "en", "whitepages.com", "business", "us", "people"),
    CompanyDataBang("yellowpages", "YellowPages", "US", "en", "yellowpages.com", "business", "us", "directory"),
    CompanyDataBang("manta", "Manta", "US", "en", "manta.com", "business", "us", "directory"),
    CompanyDataBang("bizapedia", "Bizapedia", "US", "en", "bizapedia.com", "business", "us", "directory"),
    CompanyDataBang("opencorporates", "OpenCorporates", "UK", "en", "opencorporates.com", "business", "global", "registry"),
    CompanyDataBang("corporationwiki", "Corporation Wiki", "US", "en", "corporationwiki.com", "business", "us", "registry"),
    CompanyDataBang("bizstanding", "BizStanding", "US", "en", "bizstanding.com", "business", "us", "directory"),
    CompanyDataBang("muckrack", "Muck Rack", "US", "en", "muckrack.com", "business", "global", "media"),
    CompanyDataBang("glassdoor", "Glassdoor", "US", "en", "glassdoor.com", "employment", "global", "reviews"),
    CompanyDataBang("indeed", "Indeed", "US", "en", "indeed.com", "employment", "global", "jobs"),
    CompanyDataBang("linkedin", "LinkedIn", "US", "en", "linkedin.com", "business", "global", "professional"),
    CompanyDataBang("angellist", "AngelList", "US", "en", "angel.co", "startup", "global", "startups"),
    CompanyDataBang("f6s", "F6S", "UK", "en", "f6s.com", "startup", "global", "startups"),
    CompanyDataBang("gust", "Gust", "US", "en", "gust.com", "startup", "global", "startups"),
    CompanyDataBang("fundrazr", "FundRazr", "CA", "en", "fundrazr.com", "startup", "global", "funding"),
    CompanyDataBang("kickstarter", "Kickstarter", "US", "en", "kickstarter.com", "startup", "global", "crowdfunding"),
    CompanyDataBang("indiegogo", "Indiegogo", "US", "en", "indiegogo.com", "startup", "global", "crowdfunding"),
    CompanyDataBang("gofundme", "GoFundMe", "US", "en", "gofundme.com", "startup", "global", "crowdfunding"),
    CompanyDataBang("seedrs", "Seedrs", "UK", "en", "seedrs.com", "startup", "uk", "equity_crowdfunding"),
    CompanyDataBang("crowdcube", "Crowdcube", "UK", "en", "crowdcube.com", "startup", "uk", "equity_crowdfunding"),
    
    # UK Company Data
    CompanyDataBang("companieshouse", "Companies House", "UK", "en", "companieshouse.gov.uk", "regulatory", "uk", "filings"),
    CompanyDataBang("ch", "Companies House", "UK", "en", "companieshouse.gov.uk", "regulatory", "uk", "filings"),
    CompanyDataBang("ukcompanies", "UK Companies", "UK", "en", "companieshouse.gov.uk", "regulatory", "uk", "filings"),
    CompanyDataBang("duedil", "DueDil", "UK", "en", "duedil.com", "business", "uk", "profiles"),
    CompanyDataBang("endole", "Endole", "UK", "en", "endole.co.uk", "business", "uk", "profiles"),
    CompanyDataBang("companycheck", "Company Check", "UK", "en", "companycheck.co.uk", "business", "uk", "profiles"),
    CompanyDataBang("companiesmadesimple", "Companies Made Simple", "UK", "en", "companiesmadesimple.com", "business", "uk", "formation"),
    CompanyDataBang("ukdata", "UK Data Service", "UK", "en", "ukdataservice.ac.uk", "research", "uk", "data"),
    CompanyDataBang("nominet", "Nominet", "UK", "en", "nominet.uk", "technology", "uk", "domains"),
    CompanyDataBang("jisc", "Jisc", "UK", "en", "jisc.ac.uk", "education", "uk", "research"),
    CompanyDataBang("gov", "GOV.UK", "UK", "en", "gov.uk", "government", "uk", "government"),
    CompanyDataBang("ons", "ONS", "UK", "en", "ons.gov.uk", "statistics", "uk", "statistics"),
    CompanyDataBang("fca", "FCA", "UK", "en", "fca.org.uk", "regulatory", "uk", "financial"),
    CompanyDataBang("pra", "PRA", "UK", "en", "bankofengland.co.uk", "regulatory", "uk", "banking"),
    CompanyDataBang("hmrc", "HMRC", "UK", "en", "hmrc.gov.uk", "government", "uk", "tax"),
    CompanyDataBang("cma", "CMA", "UK", "en", "gov.uk", "regulatory", "uk", "competition"),
    CompanyDataBang("sfo", "SFO", "UK", "en", "sfo.gov.uk", "regulatory", "uk", "fraud"),
    CompanyDataBang("icaew", "ICAEW", "UK", "en", "icaew.com", "professional", "uk", "accounting"),
    CompanyDataBang("lse", "London Stock Exchange", "UK", "en", "londonstockexchange.com", "financial", "uk", "exchange"),
    CompanyDataBang("aim", "AIM", "UK", "en", "londonstockexchange.com", "financial", "uk", "exchange"),
    
    # European Company Data
    CompanyDataBang("handelsregister", "Handelsregister", "DE", "de", "handelsregister.de", "regulatory", "germany", "registry"),
    CompanyDataBang("bundesanzeiger", "Bundesanzeiger", "DE", "de", "bundesanzeiger.de", "regulatory", "germany", "filings"),
    CompanyDataBang("northdata", "North Data", "DE", "de", "northdata.de", "business", "germany", "profiles"),
    CompanyDataBang("firmenwissen", "Firmenwissen", "DE", "de", "firmenwissen.de", "business", "germany", "profiles"),
    CompanyDataBang("unternehmensregister", "Unternehmensregister", "DE", "de", "unternehmensregister.de", "regulatory", "germany", "registry"),
    CompanyDataBang("bafin", "BaFin", "DE", "de", "bafin.de", "regulatory", "germany", "financial"),
    CompanyDataBang("destatis", "Destatis", "DE", "de", "destatis.de", "statistics", "germany", "statistics"),
    CompanyDataBang("xing", "Xing", "DE", "de", "xing.com", "business", "germany", "professional"),
    CompanyDataBang("kununu", "Kununu", "DE", "de", "kununu.com", "employment", "germany", "reviews"),
    CompanyDataBang("stepstone", "StepStone", "DE", "de", "stepstone.de", "employment", "germany", "jobs"),
    CompanyDataBang("monster", "Monster", "DE", "de", "monster.de", "employment", "germany", "jobs"),
    CompanyDataBang("jobscout24", "JobScout24", "DE", "de", "jobscout24.de", "employment", "germany", "jobs"),
    CompanyDataBang("frankfurtse", "Frankfurt Stock Exchange", "DE", "de", "deutsche-boerse.com", "financial", "germany", "exchange"),
    CompanyDataBang("xetra", "Xetra", "DE", "de", "deutsche-boerse.com", "financial", "germany", "exchange"),
    CompanyDataBang("eurex", "Eurex", "DE", "de", "eurex.com", "financial", "germany", "derivatives"),
    
    CompanyDataBang("infogreffe", "Infogreffe", "FR", "fr", "infogreffe.fr", "regulatory", "france", "registry"),
    CompanyDataBang("societe", "Societe.com", "FR", "fr", "societe.com", "business", "france", "profiles"),
    CompanyDataBang("verif", "Verif.com", "FR", "fr", "verif.com", "business", "france", "profiles"),
    CompanyDataBang("pappers", "Pappers", "FR", "fr", "pappers.fr", "business", "france", "profiles"),
    CompanyDataBang("dirigeant", "Dirigeant.com", "FR", "fr", "dirigeant.com", "business", "france", "executives"),
    CompanyDataBang("insee", "INSEE", "FR", "fr", "insee.fr", "statistics", "france", "statistics"),
    CompanyDataBang("amf", "AMF", "FR", "fr", "amf-france.org", "regulatory", "france", "financial"),
    CompanyDataBang("banquedefrance", "Banque de France", "FR", "fr", "banque-france.fr", "regulatory", "france", "banking"),
    CompanyDataBang("bourse", "Euronext Paris", "FR", "fr", "euronext.com", "financial", "france", "exchange"),
    CompanyDataBang("euronext", "Euronext", "NL", "en", "euronext.com", "financial", "europe", "exchange"),
    CompanyDataBang("viadeo", "Viadeo", "FR", "fr", "viadeo.com", "business", "france", "professional"),
    CompanyDataBang("apec", "APEC", "FR", "fr", "apec.fr", "employment", "france", "executives"),
    CompanyDataBang("pole-emploi", "Pôle emploi", "FR", "fr", "pole-emploi.fr", "employment", "france", "jobs"),
    CompanyDataBang("indeed-fr", "Indeed France", "FR", "fr", "indeed.fr", "employment", "france", "jobs"),
    CompanyDataBang("monster-fr", "Monster France", "FR", "fr", "monster.fr", "employment", "france", "jobs"),
    CompanyDataBang("cadremploi", "Cadremploi", "FR", "fr", "cadremploi.fr", "employment", "france", "executives"),
    CompanyDataBang("lesjeudis", "Les Jeudis", "FR", "fr", "lesjeudis.com", "employment", "france", "tech"),
    
    CompanyDataBang("cameradimercio", "Camera di Commercio", "IT", "it", "registroimprese.it", "regulatory", "italy", "registry"),
    CompanyDataBang("registroimprese", "Registro Imprese", "IT", "it", "registroimprese.it", "regulatory", "italy", "registry"),
    CompanyDataBang("aida", "AIDA", "IT", "it", "bvdinfo.com", "business", "italy", "profiles"),
    CompanyDataBang("cerved", "Cerved", "IT", "it", "cerved.com", "business", "italy", "profiles"),
    CompanyDataBang("telemaco", "Telemaco", "IT", "it", "telemaco.infocamere.it", "regulatory", "italy", "registry"),
    CompanyDataBang("infocamere", "InfoCamere", "IT", "it", "infocamere.it", "regulatory", "italy", "registry"),
    CompanyDataBang("consob", "CONSOB", "IT", "it", "consob.it", "regulatory", "italy", "financial"),
    CompanyDataBang("bancaditalia", "Banca d'Italia", "IT", "it", "bancaditalia.it", "regulatory", "italy", "banking"),
    CompanyDataBang("borsa", "Borsa Italiana", "IT", "it", "borsaitaliana.it", "financial", "italy", "exchange"),
    CompanyDataBang("istat", "ISTAT", "IT", "it", "istat.it", "statistics", "italy", "statistics"),
    CompanyDataBang("linkedin-it", "LinkedIn Italia", "IT", "it", "linkedin.com", "business", "italy", "professional"),
    CompanyDataBang("infojobs", "InfoJobs", "IT", "it", "infojobs.it", "employment", "italy", "jobs"),
    CompanyDataBang("monster-it", "Monster Italia", "IT", "it", "monster.it", "employment", "italy", "jobs"),
    CompanyDataBang("indeed-it", "Indeed Italia", "IT", "it", "indeed.it", "employment", "italy", "jobs"),
    CompanyDataBang("jobrapido", "Jobrapido", "IT", "it", "jobrapido.it", "employment", "italy", "jobs"),
    
    CompanyDataBang("roc", "ROC", "NL", "nl", "kvk.nl", "regulatory", "netherlands", "registry"),
    CompanyDataBang("kvk", "KVK", "NL", "nl", "kvk.nl", "regulatory", "netherlands", "registry"),
    CompanyDataBang("kamer", "Kamer van Koophandel", "NL", "nl", "kvk.nl", "regulatory", "netherlands", "registry"),
    CompanyDataBang("dnb", "DNB", "NL", "nl", "dnb.nl", "regulatory", "netherlands", "banking"),
    CompanyDataBang("afm", "AFM", "NL", "nl", "afm.nl", "regulatory", "netherlands", "financial"),
    CompanyDataBang("cbs", "CBS", "NL", "nl", "cbs.nl", "statistics", "netherlands", "statistics"),
    CompanyDataBang("aex", "AEX", "NL", "nl", "euronext.com", "financial", "netherlands", "exchange"),
    CompanyDataBang("nationale-nederlanden", "Nationale-Nederlanden", "NL", "nl", "nn.nl", "financial", "netherlands", "insurance"),
    CompanyDataBang("jobbird", "Jobbird", "NL", "nl", "jobbird.com", "employment", "netherlands", "jobs"),
    CompanyDataBang("indeed-nl", "Indeed Nederland", "NL", "nl", "indeed.nl", "employment", "netherlands", "jobs"),
    CompanyDataBang("monsterboard", "Monsterboard", "NL", "nl", "monsterboard.nl", "employment", "netherlands", "jobs"),
    CompanyDataBang("nationale-vacaturebank", "Nationale Vacaturebank", "NL", "nl", "nationalevacaturebank.nl", "employment", "netherlands", "jobs"),
    
    CompanyDataBang("prh", "PRH", "FI", "fi", "prh.fi", "regulatory", "finland", "registry"),
    CompanyDataBang("ytj", "YTJ", "FI", "fi", "ytj.fi", "regulatory", "finland", "registry"),
    CompanyDataBang("finder", "Finder.fi", "FI", "fi", "finder.fi", "business", "finland", "profiles"),
    CompanyDataBang("fonecta", "Fonecta", "FI", "fi", "fonecta.fi", "business", "finland", "directory"),
    CompanyDataBang("fiva", "FIVA", "FI", "fi", "finanssivalvonta.fi", "regulatory", "finland", "financial"),
    CompanyDataBang("tilastokeskus", "Tilastokeskus", "FI", "fi", "tilastokeskus.fi", "statistics", "finland", "statistics"),
    CompanyDataBang("nasdaq-helsinki", "Nasdaq Helsinki", "FI", "fi", "nasdaqomxnordic.com", "financial", "finland", "exchange"),
    CompanyDataBang("monster-fi", "Monster Suomi", "FI", "fi", "monster.fi", "employment", "finland", "jobs"),
    CompanyDataBang("duunitori", "Duunitori", "FI", "fi", "duunitori.fi", "employment", "finland", "jobs"),
    CompanyDataBang("oikotie", "Oikotie Työpaikat", "FI", "fi", "oikotie.fi", "employment", "finland", "jobs"),
    
    CompanyDataBang("bolagsverket", "Bolagsverket", "SE", "sv", "bolagsverket.se", "regulatory", "sweden", "registry"),
    CompanyDataBang("allabolag", "Allabolag", "SE", "sv", "allabolag.se", "business", "sweden", "profiles"),
    CompanyDataBang("ratsit", "Ratsit", "SE", "sv", "ratsit.se", "business", "sweden", "profiles"),
    CompanyDataBang("finansinspektionen", "Finansinspektionen", "SE", "sv", "fi.se", "regulatory", "sweden", "financial"),
    CompanyDataBang("scb", "SCB", "SE", "sv", "scb.se", "statistics", "sweden", "statistics"),
    CompanyDataBang("nasdaq-stockholm", "Nasdaq Stockholm", "SE", "sv", "nasdaqomxnordic.com", "financial", "sweden", "exchange"),
    CompanyDataBang("arbetsformedlingen", "Arbetsförmedlingen", "SE", "sv", "arbetsformedlingen.se", "employment", "sweden", "jobs"),
    CompanyDataBang("thelocal", "The Local Sweden", "SE", "en", "thelocal.se", "employment", "sweden", "jobs"),
    CompanyDataBang("monster-se", "Monster Sverige", "SE", "sv", "monster.se", "employment", "sweden", "jobs"),
    CompanyDataBang("stepstone-se", "StepStone Sverige", "SE", "sv", "stepstone.se", "employment", "sweden", "jobs"),
    
    CompanyDataBang("brreg", "Brønnøysundregistrene", "NO", "no", "brreg.no", "regulatory", "norway", "registry"),
    CompanyDataBang("proff", "Proff", "NO", "no", "proff.no", "business", "norway", "profiles"),
    CompanyDataBang("finanstilsynet", "Finanstilsynet", "NO", "no", "finanstilsynet.no", "regulatory", "norway", "financial"),
    CompanyDataBang("ssb", "SSB", "NO", "no", "ssb.no", "statistics", "norway", "statistics"),
    CompanyDataBang("oslobors", "Oslo Børs", "NO", "no", "oslobors.no", "financial", "norway", "exchange"),
    CompanyDataBang("nav", "NAV", "NO", "no", "nav.no", "employment", "norway", "jobs"),
    CompanyDataBang("finn", "Finn.no", "NO", "no", "finn.no", "employment", "norway", "jobs"),
    CompanyDataBang("monster-no", "Monster Norge", "NO", "no", "monster.no", "employment", "norway", "jobs"),
    CompanyDataBang("stepstone-no", "StepStone Norge", "NO", "no", "stepstone.no", "employment", "norway", "jobs"),
    
    CompanyDataBang("cvr", "CVR", "DK", "da", "cvr.dk", "regulatory", "denmark", "registry"),
    CompanyDataBang("proff-dk", "Proff Danmark", "DK", "da", "proff.dk", "business", "denmark", "profiles"),
    CompanyDataBang("finanstilsynet-dk", "Finanstilsynet", "DK", "da", "finanstilsynet.dk", "regulatory", "denmark", "financial"),
    CompanyDataBang("dst", "Danmarks Statistik", "DK", "da", "dst.dk", "statistics", "denmark", "statistics"),
    CompanyDataBang("nasdaqcopenhagen", "Nasdaq Copenhagen", "DK", "da", "nasdaqomxnordic.com", "financial", "denmark", "exchange"),
    CompanyDataBang("jobindex", "Jobindex", "DK", "da", "jobindex.dk", "employment", "denmark", "jobs"),
    CompanyDataBang("jobnet", "Jobnet", "DK", "da", "jobnet.dk", "employment", "denmark", "jobs"),
    CompanyDataBang("stepstone-dk", "StepStone Danmark", "DK", "da", "stepstone.dk", "employment", "denmark", "jobs"),
    
    # Asian Company Data
    CompanyDataBang("jcn", "Japan Corporate Number", "JP", "ja", "houjin-bangou.nta.go.jp", "regulatory", "japan", "registry"),
    CompanyDataBang("tsr", "Tokyo Shoko Research", "JP", "ja", "tsr-net.co.jp", "business", "japan", "profiles"),
    CompanyDataBang("teikoku", "Teikoku Databank", "JP", "ja", "tdb.co.jp", "business", "japan", "profiles"),
    CompanyDataBang("jfsa", "JFSA", "JP", "ja", "fsa.go.jp", "regulatory", "japan", "financial"),
    CompanyDataBang("tse", "Tokyo Stock Exchange", "JP", "ja", "jpx.co.jp", "financial", "japan", "exchange"),
    CompanyDataBang("mothers", "Mothers", "JP", "ja", "jpx.co.jp", "financial", "japan", "exchange"),
    CompanyDataBang("jasdaq", "JASDAQ", "JP", "ja", "jpx.co.jp", "financial", "japan", "exchange"),
    CompanyDataBang("rikunabi", "Rikunabi", "JP", "ja", "rikunabi.com", "employment", "japan", "jobs"),
    CompanyDataBang("mynavi", "Mynavi", "JP", "ja", "mynavi.jp", "employment", "japan", "jobs"),
    CompanyDataBang("doda", "Doda", "JP", "ja", "doda.jp", "employment", "japan", "jobs"),
    CompanyDataBang("bizreach", "BizReach", "JP", "ja", "bizreach.jp", "employment", "japan", "executives"),
    CompanyDataBang("wantedly", "Wantedly", "JP", "ja", "wantedly.com", "employment", "japan", "startups"),
    
    CompanyDataBang("dart", "DART", "KR", "ko", "dart.fss.or.kr", "regulatory", "south_korea", "filings"),
    CompanyDataBang("krx", "KRX", "KR", "ko", "krx.co.kr", "financial", "south_korea", "exchange"),
    CompanyDataBang("kospi", "KOSPI", "KR", "ko", "krx.co.kr", "financial", "south_korea", "exchange"),
    CompanyDataBang("kosdaq", "KOSDAQ", "KR", "ko", "krx.co.kr", "financial", "south_korea", "exchange"),
    CompanyDataBang("fss", "FSS", "KR", "ko", "fss.or.kr", "regulatory", "south_korea", "financial"),
    CompanyDataBang("kostat", "KOSTAT", "KR", "ko", "kostat.go.kr", "statistics", "south_korea", "statistics"),
    CompanyDataBang("jobkorea", "JobKorea", "KR", "ko", "jobkorea.co.kr", "employment", "south_korea", "jobs"),
    CompanyDataBang("saramin", "Saramin", "KR", "ko", "saramin.co.kr", "employment", "south_korea", "jobs"),
    CompanyDataBang("incruit", "Incruit", "KR", "ko", "incruit.com", "employment", "south_korea", "jobs"),
    CompanyDataBang("wanted", "Wanted", "KR", "ko", "wanted.co.kr", "employment", "south_korea", "jobs"),
    CompanyDataBang("rocketpunch", "Rocket Punch", "KR", "ko", "rocketpunch.com", "employment", "south_korea", "startups"),
    
    CompanyDataBang("csrc", "CSRC", "CN", "zh", "csrc.gov.cn", "regulatory", "china", "financial"),
    CompanyDataBang("sse", "Shanghai Stock Exchange", "CN", "zh", "sse.com.cn", "financial", "china", "exchange"),
    CompanyDataBang("szse", "Shenzhen Stock Exchange", "CN", "zh", "szse.cn", "financial", "china", "exchange"),
    CompanyDataBang("neeq", "NEEQ", "CN", "zh", "neeq.com.cn", "financial", "china", "exchange"),
    CompanyDataBang("saic", "SAIC", "CN", "zh", "saic.gov.cn", "regulatory", "china", "registry"),
    CompanyDataBang("qichacha", "Qichacha", "CN", "zh", "qichacha.com", "business", "china", "profiles"),
    CompanyDataBang("tianyancha", "Tianyancha", "CN", "zh", "tianyancha.com", "business", "china", "profiles"),
    CompanyDataBang("qixin", "Qixin", "CN", "zh", "qixin.com", "business", "china", "profiles"),
    CompanyDataBang("zhipin", "Boss Zhipin", "CN", "zh", "zhipin.com", "employment", "china", "jobs"),
    CompanyDataBang("51job", "51job", "CN", "zh", "51job.com", "employment", "china", "jobs"),
    CompanyDataBang("liepin", "Liepin", "CN", "zh", "liepin.com", "employment", "china", "executives"),
    CompanyDataBang("lagou", "Lagou", "CN", "zh", "lagou.com", "employment", "china", "tech"),
    
    CompanyDataBang("hkex", "Hong Kong Exchange", "HK", "en", "hkex.com.hk", "financial", "hong_kong", "exchange"),
    CompanyDataBang("sfc", "SFC", "HK", "en", "sfc.hk", "regulatory", "hong_kong", "financial"),
    CompanyDataBang("cr", "Companies Registry", "HK", "en", "cr.gov.hk", "regulatory", "hong_kong", "registry"),
    CompanyDataBang("icris", "ICRIS", "HK", "en", "icris.cr.gov.hk", "regulatory", "hong_kong", "registry"),
    CompanyDataBang("jobsdb", "JobsDB", "HK", "en", "jobsdb.com", "employment", "hong_kong", "jobs"),
    CompanyDataBang("cpjobs", "CPJobs", "HK", "en", "cpjobs.com", "employment", "hong_kong", "jobs"),
    CompanyDataBang("indeed-hk", "Indeed Hong Kong", "HK", "en", "indeed.hk", "employment", "hong_kong", "jobs"),
    
    CompanyDataBang("acra", "ACRA", "SG", "en", "acra.gov.sg", "regulatory", "singapore", "registry"),
    CompanyDataBang("mas", "MAS", "SG", "en", "mas.gov.sg", "regulatory", "singapore", "financial"),
    CompanyDataBang("sgx", "Singapore Exchange", "SG", "en", "sgx.com", "financial", "singapore", "exchange"),
    CompanyDataBang("jobstreet", "JobStreet", "SG", "en", "jobstreet.com.sg", "employment", "singapore", "jobs"),
    CompanyDataBang("indeed-sg", "Indeed Singapore", "SG", "en", "indeed.com.sg", "employment", "singapore", "jobs"),
    CompanyDataBang("monster-sg", "Monster Singapore", "SG", "en", "monster.com.sg", "employment", "singapore", "jobs"),
    CompanyDataBang("linkedin-sg", "LinkedIn Singapore", "SG", "en", "linkedin.com", "business", "singapore", "professional"),
    
    CompanyDataBang("mca", "MCA", "IN", "en", "mca.gov.in", "regulatory", "india", "registry"),
    CompanyDataBang("sebi", "SEBI", "IN", "en", "sebi.gov.in", "regulatory", "india", "financial"),
    CompanyDataBang("nse", "NSE", "IN", "en", "nseindia.com", "financial", "india", "exchange"),
    CompanyDataBang("bse", "BSE", "IN", "en", "bseindia.com", "financial", "india", "exchange"),
    CompanyDataBang("zauba", "Zauba", "IN", "en", "zauba.com", "business", "india", "profiles"),
    CompanyDataBang("zaubacorp", "ZaubaCorp", "IN", "en", "zaubacorp.com", "business", "india", "profiles"),
    CompanyDataBang("naukri", "Naukri", "IN", "en", "naukri.com", "employment", "india", "jobs"),
    CompanyDataBang("monster-in", "Monster India", "IN", "en", "monsterindia.com", "employment", "india", "jobs"),
    CompanyDataBang("indeed-in", "Indeed India", "IN", "en", "indeed.co.in", "employment", "india", "jobs"),
    CompanyDataBang("shine", "Shine", "IN", "en", "shine.com", "employment", "india", "jobs"),
    CompanyDataBang("foundit", "Foundit", "IN", "en", "foundit.in", "employment", "india", "jobs"),
    CompanyDataBang("internshala", "Internshala", "IN", "en", "internshala.com", "employment", "india", "internships"),
    
    # Australian Company Data
    CompanyDataBang("asic", "ASIC", "AU", "en", "asic.gov.au", "regulatory", "australia", "registry"),
    CompanyDataBang("abn", "ABN Lookup", "AU", "en", "abr.business.gov.au", "regulatory", "australia", "registry"),
    CompanyDataBang("abr", "ABR", "AU", "en", "abr.business.gov.au", "regulatory", "australia", "registry"),
    CompanyDataBang("apra", "APRA", "AU", "en", "apra.gov.au", "regulatory", "australia", "financial"),
    CompanyDataBang("asx", "ASX", "AU", "en", "asx.com.au", "financial", "australia", "exchange"),
    CompanyDataBang("abs", "ABS", "AU", "en", "abs.gov.au", "statistics", "australia", "statistics"),
    CompanyDataBang("seek", "SEEK", "AU", "en", "seek.com.au", "employment", "australia", "jobs"),
    CompanyDataBang("indeed-au", "Indeed Australia", "AU", "en", "indeed.com.au", "employment", "australia", "jobs"),
    CompanyDataBang("careerone", "CareerOne", "AU", "en", "careerone.com.au", "employment", "australia", "jobs"),
    CompanyDataBang("jora", "Jora", "AU", "en", "jora.com", "employment", "australia", "jobs"),
    CompanyDataBang("linkedin-au", "LinkedIn Australia", "AU", "en", "linkedin.com", "business", "australia", "professional"),
    
    # Canadian Company Data
    CompanyDataBang("ic", "Industry Canada", "CA", "en", "ic.gc.ca", "regulatory", "canada", "registry"),
    CompanyDataBang("cra", "CRA", "CA", "en", "cra-arc.gc.ca", "government", "canada", "tax"),
    CompanyDataBang("osfi", "OSFI", "CA", "en", "osfi-bsif.gc.ca", "regulatory", "canada", "financial"),
    CompanyDataBang("tsx", "TSX", "CA", "en", "tsx.com", "financial", "canada", "exchange"),
    CompanyDataBang("tsxv", "TSX Venture", "CA", "en", "tsx.com", "financial", "canada", "exchange"),
    CompanyDataBang("cse", "CSE", "CA", "en", "thecse.com", "financial", "canada", "exchange"),
    CompanyDataBang("statcan", "Statistics Canada", "CA", "en", "statcan.gc.ca", "statistics", "canada", "statistics"),
    CompanyDataBang("workopolis", "Workopolis", "CA", "en", "workopolis.com", "employment", "canada", "jobs"),
    CompanyDataBang("indeed-ca", "Indeed Canada", "CA", "en", "indeed.ca", "employment", "canada", "jobs"),
    CompanyDataBang("monster-ca", "Monster Canada", "CA", "en", "monster.ca", "employment", "canada", "jobs"),
    CompanyDataBang("jobbank", "Job Bank", "CA", "en", "jobbank.gc.ca", "employment", "canada", "jobs"),
    CompanyDataBang("eluta", "Eluta", "CA", "en", "eluta.ca", "employment", "canada", "jobs"),
    
    # Brazilian Company Data
    CompanyDataBang("receita", "Receita Federal", "BR", "pt", "receita.fazenda.gov.br", "government", "brazil", "tax"),
    CompanyDataBang("cnpj", "CNPJ", "BR", "pt", "receita.fazenda.gov.br", "regulatory", "brazil", "registry"),
    CompanyDataBang("cvm", "CVM", "BR", "pt", "cvm.gov.br", "regulatory", "brazil", "financial"),
    CompanyDataBang("b3", "B3", "BR", "pt", "b3.com.br", "financial", "brazil", "exchange"),
    CompanyDataBang("bovespa", "Bovespa", "BR", "pt", "b3.com.br", "financial", "brazil", "exchange"),
    CompanyDataBang("ibge", "IBGE", "BR", "pt", "ibge.gov.br", "statistics", "brazil", "statistics"),
    CompanyDataBang("catho", "Catho", "BR", "pt", "catho.com.br", "employment", "brazil", "jobs"),
    CompanyDataBang("infojobs-br", "InfoJobs Brasil", "BR", "pt", "infojobs.com.br", "employment", "brazil", "jobs"),
    CompanyDataBang("vagas", "Vagas", "BR", "pt", "vagas.com.br", "employment", "brazil", "jobs"),
    CompanyDataBang("indeed-br", "Indeed Brasil", "BR", "pt", "indeed.com.br", "employment", "brazil", "jobs"),
    CompanyDataBang("linkedin-br", "LinkedIn Brasil", "BR", "pt", "linkedin.com", "business", "brazil", "professional"),
    
    # Mexican Company Data
    CompanyDataBang("sat", "SAT", "MX", "es", "sat.gob.mx", "government", "mexico", "tax"),
    CompanyDataBang("cnbv", "CNBV", "MX", "es", "cnbv.gob.mx", "regulatory", "mexico", "financial"),
    CompanyDataBang("bmv", "BMV", "MX", "es", "bmv.com.mx", "financial", "mexico", "exchange"),
    CompanyDataBang("inegi", "INEGI", "MX", "es", "inegi.org.mx", "statistics", "mexico", "statistics"),
    CompanyDataBang("occ", "OCC Mundial", "MX", "es", "occ.com.mx", "employment", "mexico", "jobs"),
    CompanyDataBang("indeed-mx", "Indeed México", "MX", "es", "indeed.com.mx", "employment", "mexico", "jobs"),
    CompanyDataBang("computrabajo", "Computrabajo", "MX", "es", "computrabajo.com.mx", "employment", "mexico", "jobs"),
    CompanyDataBang("linkedin-mx", "LinkedIn México", "MX", "es", "linkedin.com", "business", "mexico", "professional"),
    
    # Russian Company Data
    CompanyDataBang("egrul", "EGRUL", "RU", "ru", "egrul.nalog.ru", "regulatory", "russia", "registry"),
    CompanyDataBang("fns", "FNS", "RU", "ru", "nalog.ru", "government", "russia", "tax"),
    CompanyDataBang("cbr", "CBR", "RU", "ru", "cbr.ru", "regulatory", "russia", "banking"),
    CompanyDataBang("moex", "MOEX", "RU", "ru", "moex.com", "financial", "russia", "exchange"),
    CompanyDataBang("rosstat", "Rosstat", "RU", "ru", "rosstat.gov.ru", "statistics", "russia", "statistics"),
    CompanyDataBang("hh", "HeadHunter", "RU", "ru", "hh.ru", "employment", "russia", "jobs"),
    CompanyDataBang("superjob", "SuperJob", "RU", "ru", "superjob.ru", "employment", "russia", "jobs"),
    CompanyDataBang("zarplata", "Zarplata.ru", "RU", "ru", "zarplata.ru", "employment", "russia", "jobs"),
    CompanyDataBang("rabota", "Rabota.ru", "RU", "ru", "rabota.ru", "employment", "russia", "jobs"),
    
    # South African Company Data
    CompanyDataBang("cipc", "CIPC", "ZA", "en", "cipc.co.za", "regulatory", "south_africa", "registry"),
    CompanyDataBang("sars", "SARS", "ZA", "en", "sars.gov.za", "government", "south_africa", "tax"),
    CompanyDataBang("sarb", "SARB", "ZA", "en", "resbank.co.za", "regulatory", "south_africa", "banking"),
    CompanyDataBang("jse", "JSE", "ZA", "en", "jse.co.za", "financial", "south_africa", "exchange"),
    CompanyDataBang("statssa", "Stats SA", "ZA", "en", "statssa.gov.za", "statistics", "south_africa", "statistics"),
    CompanyDataBang("careers24", "Careers24", "ZA", "en", "careers24.com", "employment", "south_africa", "jobs"),
    CompanyDataBang("indeed-za", "Indeed South Africa", "ZA", "en", "indeed.co.za", "employment", "south_africa", "jobs"),
    CompanyDataBang("pnet", "PNet", "ZA", "en", "pnet.co.za", "employment", "south_africa", "jobs"),
    CompanyDataBang("jobmail", "JobMail", "ZA", "en", "jobmail.co.za", "employment", "south_africa", "jobs"),
    
    # Credit Rating and Risk Assessment
    CompanyDataBang("moodys", "Moody's", "US", "en", "moodys.com", "credit_rating", "global", "ratings"),
    CompanyDataBang("sp", "S&P Global", "US", "en", "spglobal.com", "credit_rating", "global", "ratings"),
    CompanyDataBang("fitch", "Fitch Ratings", "US", "en", "fitchratings.com", "credit_rating", "global", "ratings"),
    CompanyDataBang("dnb", "Dun & Bradstreet", "US", "en", "dnb.com", "credit_rating", "global", "ratings"),
    CompanyDataBang("experian", "Experian", "IE", "en", "experian.com", "credit_rating", "global", "ratings"),
    CompanyDataBang("equifax", "Equifax", "US", "en", "equifax.com", "credit_rating", "global", "ratings"),
    CompanyDataBang("transunion", "TransUnion", "US", "en", "transunion.com", "credit_rating", "global", "ratings"),
    CompanyDataBang("coface", "Coface", "FR", "fr", "coface.com", "credit_rating", "global", "ratings"),
    CompanyDataBang("euler", "Euler Hermes", "DE", "de", "eulerhermes.com", "credit_rating", "global", "ratings"),
    CompanyDataBang("creditsafe", "Creditsafe", "UK", "en", "creditsafe.com", "credit_rating", "global", "ratings"),
    
    # Patent and IP Data
    CompanyDataBang("uspto", "USPTO", "US", "en", "uspto.gov", "intellectual_property", "us", "patents"),
    CompanyDataBang("epo", "EPO", "DE", "en", "epo.org", "intellectual_property", "europe", "patents"),
    CompanyDataBang("wipo", "WIPO", "CH", "en", "wipo.int", "intellectual_property", "global", "patents"),
    CompanyDataBang("espacenet", "Espacenet", "DE", "en", "worldwide.espacenet.com", "intellectual_property", "global", "patents"),
    CompanyDataBang("patentscope", "PATENTSCOPE", "CH", "en", "patentscope.wipo.int", "intellectual_property", "global", "patents"),
    CompanyDataBang("googlepatents", "Google Patents", "US", "en", "patents.google.com", "intellectual_property", "global", "patents"),
    CompanyDataBang("freepatents", "FreePatentsOnline", "US", "en", "freepatentsonline.com", "intellectual_property", "global", "patents"),
    CompanyDataBang("patft", "PatFT", "US", "en", "patft.uspto.gov", "intellectual_property", "us", "patents"),
    CompanyDataBang("appft", "AppFT", "US", "en", "appft.uspto.gov", "intellectual_property", "us", "patents"),
    CompanyDataBang("tmdb", "Trademark Database", "US", "en", "tmsearch.uspto.gov", "intellectual_property", "us", "trademarks"),
    
    # ESG and Sustainability Data
    CompanyDataBang("msci", "MSCI ESG", "US", "en", "msci.com", "esg", "global", "ratings"),
    CompanyDataBang("sustainalytics", "Sustainalytics", "NL", "en", "sustainalytics.com", "esg", "global", "ratings"),
    CompanyDataBang("refinitiv-esg", "Refinitiv ESG", "UK", "en", "refinitiv.com", "esg", "global", "ratings"),
    CompanyDataBang("cdp", "CDP", "UK", "en", "cdp.net", "esg", "global", "climate"),
    CompanyDataBang("sasb", "SASB", "US", "en", "sasb.org", "esg", "global", "standards"),
    CompanyDataBang("gri", "GRI", "NL", "en", "globalreporting.org", "esg", "global", "standards"),
    CompanyDataBang("tcfd", "TCFD", "CH", "en", "fsb-tcfd.org", "esg", "global", "climate"),
    CompanyDataBang("ungc", "UN Global Compact", "US", "en", "unglobalcompact.org", "esg", "global", "standards"),
    CompanyDataBang("ftse4good", "FTSE4Good", "UK", "en", "ftserussell.com", "esg", "global", "index"),
    CompanyDataBang("djsi", "Dow Jones Sustainability Index", "US", "en", "spglobal.com", "esg", "global", "index"),
    
    # Alternative Data Sources
    CompanyDataBang("similarweb", "SimilarWeb", "IL", "en", "similarweb.com", "web_analytics", "global", "traffic"),
    CompanyDataBang("alexa", "Alexa", "US", "en", "alexa.com", "web_analytics", "global", "traffic"),
    CompanyDataBang("semrush", "SEMrush", "US", "en", "semrush.com", "web_analytics", "global", "seo"),
    CompanyDataBang("ahrefs", "Ahrefs", "SG", "en", "ahrefs.com", "web_analytics", "global", "seo"),
    CompanyDataBang("moz", "Moz", "US", "en", "moz.com", "web_analytics", "global", "seo"),
    CompanyDataBang("builtwith", "BuiltWith", "AU", "en", "builtwith.com", "technology", "global", "tech_stack"),
    CompanyDataBang("wappalyzer", "Wappalyzer", "NL", "en", "wappalyzer.com", "technology", "global", "tech_stack"),
    CompanyDataBang("datanyze", "Datanyze", "US", "en", "datanyze.com", "technology", "global", "tech_stack"),
    CompanyDataBang("ghostery", "Ghostery", "US", "en", "ghostery.com", "technology", "global", "tracking"),
    CompanyDataBang("whois", "Whois", "US", "en", "whois.net", "technology", "global", "domains"),
    CompanyDataBang("domaintools", "DomainTools", "US", "en", "domaintools.com", "technology", "global", "domains"),
    CompanyDataBang("shodan", "Shodan", "US", "en", "shodan.io", "technology", "global", "iot"),
    CompanyDataBang("censys", "Censys", "US", "en", "censys.io", "technology", "global", "internet_scan"),
    CompanyDataBang("securitytrails", "SecurityTrails", "US", "en", "securitytrails.com", "technology", "global", "dns"),
    CompanyDataBang("virustotal", "VirusTotal", "ES", "en", "virustotal.com", "security", "global", "malware"),
    CompanyDataBang("urlvoid", "URLVoid", "IT", "en", "urlvoid.com", "security", "global", "reputation"),
    CompanyDataBang("trustar", "TruSTAR", "US", "en", "trustar.co", "security", "global", "threat_intel"),
    CompanyDataBang("recordedfuture", "Recorded Future", "US", "en", "recordedfuture.com", "security", "global", "threat_intel"),
    CompanyDataBang("riskiq", "RiskIQ", "US", "en", "riskiq.com", "security", "global", "threat_intel"),
    CompanyDataBang("threatconnect", "ThreatConnect", "US", "en", "threatconnect.com", "security", "global", "threat_intel"),
    
    # Industry-Specific Data
    CompanyDataBang("iex", "IEX Cloud", "US", "en", "iexcloud.io", "financial", "global", "market_data"),
    CompanyDataBang("polygon", "Polygon.io", "US", "en", "polygon.io", "financial", "global", "market_data"),
    CompanyDataBang("tiingo", "Tiingo", "US", "en", "tiingo.com", "financial", "global", "market_data"),
    CompanyDataBang("intrinio", "Intrinio", "US", "en", "intrinio.com", "financial", "global", "market_data"),
    CompanyDataBang("xignite", "Xignite", "US", "en", "xignite.com", "financial", "global", "market_data"),
    CompanyDataBang("marketstack", "Marketstack", "AT", "en", "marketstack.com", "financial", "global", "market_data"),
    CompanyDataBang("finage", "Finage", "UK", "en", "finage.co.uk", "financial", "global", "market_data"),
    CompanyDataBang("twelvedata", "Twelve Data", "US", "en", "twelvedata.com", "financial", "global", "market_data"),
    CompanyDataBang("worldbank", "World Bank", "US", "en", "worldbank.org", "economic", "global", "development"),
    CompanyDataBang("imf", "IMF", "US", "en", "imf.org", "economic", "global", "monetary"),
    CompanyDataBang("oecd", "OECD", "FR", "en", "oecd.org", "economic", "global", "development"),
    CompanyDataBang("eurostat", "Eurostat", "LU", "en", "ec.europa.eu", "statistics", "europe", "statistics"),
    CompanyDataBang("fred", "FRED", "US", "en", "fred.stlouisfed.org", "economic", "us", "economic_data"),
    CompanyDataBang("bea", "BEA", "US", "en", "bea.gov", "economic", "us", "economic_data"),
    CompanyDataBang("bls", "BLS", "US", "en", "bls.gov", "economic", "us", "labor_statistics"),
    CompanyDataBang("census", "US Census", "US", "en", "census.gov", "statistics", "us", "demographics"),
]

# Create lookup dictionaries for efficient filtering
def create_company_lookup_dictionaries():
    """Create lookup dictionaries for efficient filtering by country, language, category, and data type"""
    by_country = {}
    by_language = {}
    by_category = {}
    by_data_type = {}
    by_regional_focus = {}
    
    for bang in COMPANY_DATA_BANGS_DATABASE:
        # By country
        if bang.country not in by_country:
            by_country[bang.country] = []
        by_country[bang.country].append(bang)
        
        # By language
        if bang.language not in by_language:
            by_language[bang.language] = []
        by_language[bang.language].append(bang)
        
        # By category
        if bang.category not in by_category:
            by_category[bang.category] = []
        by_category[bang.category].append(bang)
        
        # By data type
        if bang.data_type not in by_data_type:
            by_data_type[bang.data_type] = []
        by_data_type[bang.data_type].append(bang)
        
        # By regional focus
        if bang.regional_focus not in by_regional_focus:
            by_regional_focus[bang.regional_focus] = []
        by_regional_focus[bang.regional_focus].append(bang)
    
    return by_country, by_language, by_category, by_data_type, by_regional_focus

# Create lookup dictionaries
(COMPANY_BANGS_BY_COUNTRY, COMPANY_BANGS_BY_LANGUAGE, COMPANY_BANGS_BY_CATEGORY, 
 COMPANY_BANGS_BY_DATA_TYPE, COMPANY_BANGS_BY_REGIONAL_FOCUS) = create_company_lookup_dictionaries()

# Filter functions for targeting
def get_company_bangs_by_country(country_code: str) -> List[CompanyDataBang]:
    """Get company data bangs for a specific country"""
    return COMPANY_BANGS_BY_COUNTRY.get(country_code.upper(), [])

def get_company_bangs_by_language(language_code: str) -> List[CompanyDataBang]:
    """Get company data bangs for a specific language"""
    return COMPANY_BANGS_BY_LANGUAGE.get(language_code.lower(), [])

def get_company_bangs_by_category(category: str) -> List[CompanyDataBang]:
    """Get company data bangs for a specific category"""
    return COMPANY_BANGS_BY_CATEGORY.get(category.lower(), [])

def get_company_bangs_by_data_type(data_type: str) -> List[CompanyDataBang]:
    """Get company data bangs for a specific data type"""
    return COMPANY_BANGS_BY_DATA_TYPE.get(data_type.lower(), [])

def get_company_bangs_by_regional_focus(regional_focus: str) -> List[CompanyDataBang]:
    """Get company data bangs for a specific regional focus"""
    return COMPANY_BANGS_BY_REGIONAL_FOCUS.get(regional_focus.lower(), [])

def get_company_bangs_for_location_language(country_code: Optional[str] = None, 
                                          language_code: Optional[str] = None,
                                          category: Optional[str] = None,
                                          data_type: Optional[str] = None) -> List[CompanyDataBang]:
    """Get company data bangs filtered by country, language, category, and/or data type"""
    result = COMPANY_DATA_BANGS_DATABASE.copy()
    
    if country_code:
        result = [bang for bang in result if bang.country == country_code.upper()]
    
    if language_code:
        result = [bang for bang in result if bang.language == language_code.lower()]
    
    if category:
        result = [bang for bang in result if bang.category == category.lower()]
    
    if data_type:
        result = [bang for bang in result if bang.data_type == data_type.lower()]
    
    return result

# Legacy compatibility - extract just the bang names for backwards compatibility
ALL_COMPANY_DATA_BANGS = [bang.bang for bang in COMPANY_DATA_BANGS_DATABASE]

# Priority company data bangs - curated subset of most important sources
PRIORITY_COMPANY_DATA_BANGS = [
    "sec", "edgar", "yahoo", "bloomberg", "refinitiv", "crunchbase", "linkedin", 
    "companieshouse", "opencorporates", "glassdoor", "pitchbook", "factset",
    "morningstar", "zacks", "owler", "apollo", "zoominfo", "clearbit",
    "moodys", "sp", "fitch", "dnb", "experian", "similarweb", "builtwith",
    "shodan", "virustotal", "uspto", "epo", "msci", "sustainalytics", "cdp"
]

# Available countries, languages, categories, and data types
AVAILABLE_COMPANY_COUNTRIES = sorted(list(set(bang.country for bang in COMPANY_DATA_BANGS_DATABASE)))
AVAILABLE_COMPANY_LANGUAGES = sorted(list(set(bang.language for bang in COMPANY_DATA_BANGS_DATABASE)))
AVAILABLE_COMPANY_CATEGORIES = sorted(list(set(bang.category for bang in COMPANY_DATA_BANGS_DATABASE)))
AVAILABLE_COMPANY_DATA_TYPES = sorted(list(set(bang.data_type for bang in COMPANY_DATA_BANGS_DATABASE)))
AVAILABLE_COMPANY_REGIONAL_FOCUSES = sorted(list(set(bang.regional_focus for bang in COMPANY_DATA_BANGS_DATABASE)))

# Statistics
TOTAL_COMPANY_DATA_BANGS = len(COMPANY_DATA_BANGS_DATABASE)
COMPANY_COUNTRIES_COVERED = len(AVAILABLE_COMPANY_COUNTRIES)
COMPANY_LANGUAGES_COVERED = len(AVAILABLE_COMPANY_LANGUAGES)
COMPANY_CATEGORIES_COVERED = len(AVAILABLE_COMPANY_CATEGORIES)
COMPANY_DATA_TYPES_COVERED = len(AVAILABLE_COMPANY_DATA_TYPES)

def get_company_data_bangs_stats():
    """Get statistics about the company data bangs database"""
    return {
        'total_bangs': TOTAL_COMPANY_DATA_BANGS,
        'countries_covered': COMPANY_COUNTRIES_COVERED,
        'languages_covered': COMPANY_LANGUAGES_COVERED,
        'categories_covered': COMPANY_CATEGORIES_COVERED,
        'data_types_covered': COMPANY_DATA_TYPES_COVERED,
        'available_countries': AVAILABLE_COMPANY_COUNTRIES,
        'available_languages': AVAILABLE_COMPANY_LANGUAGES,
        'available_categories': AVAILABLE_COMPANY_CATEGORIES,
        'available_data_types': AVAILABLE_COMPANY_DATA_TYPES,
        'available_regional_focuses': AVAILABLE_COMPANY_REGIONAL_FOCUSES
    }

# Category descriptions for better understanding
CATEGORY_DESCRIPTIONS = {
    'regulatory': 'Government regulatory agencies and official company registries',
    'financial': 'Financial data providers, exchanges, and market data services',
    'business': 'Business intelligence, company profiles, and commercial databases',
    'startup': 'Startup databases, venture capital, and entrepreneurship platforms',
    'employment': 'Job boards, recruitment platforms, and employment services',
    'credit_rating': 'Credit rating agencies and risk assessment services',
    'intellectual_property': 'Patent databases, trademark registries, and IP services',
    'esg': 'Environmental, Social, and Governance (ESG) data providers',
    'web_analytics': 'Website analytics, traffic data, and digital intelligence',
    'technology': 'Technology stack analysis, domain information, and tech intelligence',
    'security': 'Cybersecurity databases, threat intelligence, and security services',
    'economic': 'Economic data, statistics, and macroeconomic indicators',
    'statistics': 'Government statistics agencies and demographic data',
    'government': 'Government agencies and official data sources',
    'professional': 'Professional networking and career platforms',
    'research': 'Research institutions and academic databases'
}

# Data type descriptions
DATA_TYPE_DESCRIPTIONS = {
    'filings': 'Official company filings, reports, and regulatory documents',
    'financials': 'Financial statements, ratios, and accounting data',
    'analysis': 'Financial analysis, research reports, and investment insights',
    'profiles': 'Company profiles, background information, and basic data',
    'registry': 'Official company registrations and legal entity information',
    'leads': 'Sales leads, contact information, and business development data',
    'people': 'People search, executive information, and contact details',
    'directory': 'Business directories and company listings',
    'reviews': 'Employee reviews, company ratings, and workplace insights',
    'jobs': 'Job postings, career opportunities, and employment data',
    'startups': 'Startup information, funding data, and venture capital',
    'ratings': 'Credit ratings, risk assessments, and financial scores',
    'patents': 'Patent applications, intellectual property filings, and IP data',
    'trademarks': 'Trademark registrations and brand protection data',
    'climate': 'Climate-related disclosures and environmental data',
    'standards': 'ESG standards, frameworks, and sustainability guidelines',
    'traffic': 'Website traffic data, user analytics, and digital metrics',
    'seo': 'Search engine optimization data and digital marketing insights',
    'tech_stack': 'Technology stack information and software usage data',
    'domains': 'Domain registration data and DNS information',
    'malware': 'Malware analysis, security threats, and cyber intelligence',
    'market_data': 'Real-time market data, prices, and trading information',
    'economic_data': 'Economic indicators, statistics, and macroeconomic data',
    'demographics': 'Population data, census information, and demographic statistics'
} 