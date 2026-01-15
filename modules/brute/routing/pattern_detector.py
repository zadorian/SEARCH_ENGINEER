#!/usr/bin/env python3
"""
Unified Pattern Detection Module for Search_Engineer

This module centralizes all search pattern detection logic, providing a single
source of truth for operator patterns and their detection priority.

Pattern Categories:
1. Pre-processors (handled before search): translation, handshake, variations
2. Search type patterns: scraper, archive, domain, filetype, etc.
3. Operator patterns: NOT, OR, proximity, language, etc.
"""

import re
from typing import Tuple, List, Dict, Optional, Any


class PatternDetector:
    """Centralized pattern detection for all search operators and types."""
    
    def __init__(self):
        """Initialize all pattern definitions and priority order."""
        
        # All pattern definitions organized by category
        self.patterns = {
            # Highest priority - special handlers
            'scraper': r'^\?\?',  # ?? prefix for ScrapeR
            
            # Memory search patterns
            'keyword_memory': r'^"[^"]+"$',        # "exact phrase" for keyword memory
            'vector_memory': r'^(?!.*:<-).*\?$',             # questions ending with ? for vector memory
            
            # Archive patterns (high priority)
            'archived_date': [
                r'\d{4}!\s*:\s*[^?\s]+',      # 2016!:domain.com
                r'\d{4}-\d{4}!\s*:\s*[^?\s]+', # 2016-2020!:domain.com
                r'<-\s*\d{4}!\s*:\s*[^?\s]+',  # <- 2016!:domain.com
                r'\d{4}\s*->!\s*:\s*[^?\s]+',  # 2016 ->!:domain.com
            ],
            'backlink': [
                r'bl!\s*:\s*\?\s*[^?\s]+',  # bl! :? domain.com (referring pages, domain)
                r'bl!\s*:\s*[^?\s]+\s*\?',  # bl! : domain.com/path ? (referring pages, url)
                r'!bl\s*:\s*\?\s*[^?\s]+',  # !bl :? domain.com (referring domains, domain)
                r'!bl\s*:\s*[^?\s]+\s*\?',  # !bl : domain.com/path ? (referring domains, url)
            ],
            'similar': [
                r'similar\s*:\s*https?://[^\s]+',  # similar:https://example.com
                r'sim\s*:\s*https?://[^\s]+',      # sim:https://example.com
            ],
            'related': [
                r'related\s*:\s*https?://[^\s]+',  # related:https://example.com
                r'related\s*:\s*[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # related:domain.com
            ],
            'historic': [
                r'"[^"]+"\s*:\s*<-[^?]*\?',   # "keyword" :<- url? (allow any chars before ?)
                r'ol!\s*:\s*<-[^?]*\?',        # ol! :<- url? (outlinks from historic page)
            ],
            
            # Historic entity extraction patterns
            'historic_entity_extraction': {
                'person': r'p!\s*:\s*<-[^?]*\?',      # p! :<- url?
                'company': r'c!\s*:\s*<-[^?]*\?',     # c! :<- url?
                'email': r'e!\s*:\s*<-[^?]*\?',       # e! :<- url?
                'phone': r't!\s*:\s*<-[^?]*\?',       # t! :<- url?
                'location': r'a!\s*:\s*<-[^?]*\?',    # a! :<- url?
            },
            
            # Domain operations (high priority)
            'domain_search': r'^(ol|ga|age)!\s*:([?]?)(.+?)([?]?)$',  # ol!, ga!, age! operations
            'keyword_domain_search': [
                r'^"([^"]+)"\s*:\s*\?\s*([^?\s]+)$',  # "keyword" :? domain (allow space after ?)
                r'^"([^"]+)"\s*:\s*([^?\s]+)$',        # "keyword" : domain
            ],
            'alldom': r'^alldom\s*:\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})$',  # alldom:domain.com
            
            # Google operators (HIGH PRIORITY - before country patterns)
            'cache': r'^cache\s*:\s*(.+)$',           # cache:url
            'link': r'^link\s*:\s*(.+)$',             # link:url (pages linking to URL)
            'info': r'^info\s*:\s*(.+)$',             # info:url (info about URL)
            'define': r'^define\s*:\s*(.+)$',         # define:term (dictionary definition)
            
            # Entity extraction patterns (new)
            'entity_extraction': {
                'person': r'p!\s*:([?]?)(.+)',      # p!:?domain.com or p!:url
                'company': r'c!\s*:([?]?)(.+)',     # c!:?domain.com or c!:url
                'email': r'e!\s*:([?]?)(.+)',       # e!:?domain.com or e!:url
                'phone': r't!\s*:([?]?)(.+)',       # t!:?domain.com or t!:url
                'location': r'a!\s*:([?]?)(.+)',    # a!:?domain.com or a!:url
            },
            
            # Country-specific anchor text search patterns (HIGH PRIORITY)
            'country_anchor': [
                r'^([cp])([a-z]{2})\s*:\s*(.+)$',           # cuk:company, puk:person
                r'^(corp|person)([a-z]{2})\s*:\s*(.+)$',    # corpuk:company, personuk:person
            ],
            
            # Person search patterns (NOT entity extraction - this is for finding people by name)
            'country_person': r'^p([A-Za-z]{2,3})\s*:\s*(.+)',  # pUK:, pHU:, pNO:, etc. for country-specific person search (case-insensitive)
            'person': r'^p:\s*(.+)',  # p: operator for global person name search
            
            # Corporate search patterns (order matters - country_corporate must be checked first)
            'country_corporate': r'^c(uk|us|no|nz|au|ca|de|fr|es|it|nl|se|dk|fi|at|ch|be|lu|ie|pt|gr|pl|cz|hu|ro|bg|hr|si|sk|ee|lv|lt|mt|cy|is|li|mc|sm|va|ad|md|ua|by|ru|ge|am|az|kz|uz|tm|kg|tj|tr|il|sa|ae|qa|kw|bh|om|ye|eg|lb|sy|jo|iq|ir|af|pk|in|bd|lk|np|bt|mm|th|vn|la|kh|my|sg|id|ph|bn|tl|cn|jp|kr|tw|hk|mo|mn|kp|mx|gt|hn|sv|ni|cr|pa|co|ve|ec|pe|br|cl|ar|uy|py|bo|gy|sr|gf|fk|za|na|bw|zw|zm|mw|mz|ao|tz|ke|ug|rw|bi|et|er|dj|so|sd|ss|ly|tn|dz|ma|eh|mr|ml|bf|ne|td|sn|gm|gn|sl|lr|ci|gh|tg|bj|ng|cm|cf|cg|cd|ga|gq|st|cv|gw):\s*(.+)',  # Country-specific corporate search with valid ISO country codes (lowercase for case-insensitive matching)
            'corporate': r'^(c|corp|corporate):\s*(.+)',  # c:, corp: or corporate: for company search
            
            # Tor/Onion search pattern
            'tor': r'^tor:\s*(.+)',  # tor: operator for dark web searches
            
            # IP Address search pattern
            'ip_address': r'^ip:\s*(.+)',  # ip: operator for IP address intelligence
            
            # Cryptocurrency search pattern
            'crypto': r'^crypto:\s*(.+)',  # crypto: operator for cryptocurrency wallet search
            
            # Wiki search patterns
            'wiki_search': [
                r'^cr([a-z]{2})\?$',      # Corporate Registry: crde?
                r'^lit([a-z]{2})\?$',     # Litigation: lituk?
                r'^reg([a-z]{2})\?$',     # Regulatory: regfr?
                r'^ass([a-z]{2})\?$',     # Asset registries: assus?
                r'^misc([a-z]{2})\?$',    # Miscellaneous: miscca?
                r'^wiki([a-z]{2})\?$',    # Full wiki: wikisk?
            ],
            
            # Boolean/logic operators
            'not_search': [
                r'\bNOT\s+',           # NOT term
                r'\s+-["\']?\w+',      # -term or -"term"
                r'^-["\']?\w+',        # -term at start
            ],
            'or_search': [
                r'\s/\s',              # term / term
                r'\sOR\s',             # term OR term
            ],
            
            # Search modifiers
            'definitional': r'\[([^\]]+)\]',  # [bracketed content]
            
            # Date patterns
            'date': [
                r'\d{4}\s*-\s*\d{4}!?',  # yyyy-yyyy! (year range)
                r'<-\s*\d{4}!?',          # <- yyyy! (before year)
                r'\d{4}\s*->!?',          # yyyy ->! (after year)
                r'(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})\s*-\s*(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})!?',  # dd month yyyy - dd month yyyy!
                r'<-\s*(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})!?',  # <- dd month yyyy!
                r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}!?',  # month yyyy!
                r'\d{1,2}\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}!?',  # dd month yyyy!
                r'\b\d{4}!',              # yyyy! (year only with !)
            ],
            
            # Proximity/wildcard patterns
            'proximity': [
                r'\s\d+<\s',               # N< (at least N words)
                r'\s<\d+\s',               # <N (fewer than N words)
                r'\s~\d+\s',               # ~N (exactly N words)
                r'\s\d+~\s',               # N~ (exactly N words, alternative)
                r'\s\*{1,3}\s',            # *, **, *** (wildcards between words)
                r'\s\*\d+\s',              # *N (exactly N words between)
            ],
            
            # Language patterns
            'language': [
                r'lang\s*:\s*[a-z]{2}',          # lang:en or lang : en
                r'language\s*:\s*[a-z]{2}',      # language:en or language : en
                r':[a-z]{2}:',             # :en:
            ],
            
            # Location patterns
            'location': [
                r'\bloc\s*:\s*[a-zA-Z]{2}\b',      # loc:UK or loc : UK, etc.
                r'\bnear\s*:\s*[a-zA-Z]{2}\b',     # near:UK or near : UK, etc.
                r'\blocation\s*:\s*[a-zA-Z]{2}\b', # location:UK or location : UK, etc.
            ],
            
            # File type patterns
            'filetype': [
                r'filetype\s*:\s*\w+',           # filetype:pdf or filetype : pdf (legacy)
                r'ext\s*:\s*\w+',                # ext:pdf or ext : pdf (legacy)
                # Strict macro ("!" suffix) forms, including torrent aliases
                r'(?:^|\s)(pdf|doc|docx|xls|xlsx|ppt|pptx|txt|csv|json|xml|html|htm|zip|tar|gz|jpg|jpeg|png|gif|mp3|mp4|avi|mov|document|spreadsheet|presentation|text|code|archive|image|audio|video|media|file|torrent|to)!',
            ],
            
            # PDF search pattern
            'pdf': [
                r'pdf\s*:\s*.+',                 # pdf:query or pdf : query
            ],
            
            # Academic search patterns
            'academic': [
                r'\bacademic!',                   # academic! operator
                r'\bscholar!',                    # scholar! operator
                r'^academic\s*:',                 # academic: prefix
                r'^scholar\s*:',                  # scholar: prefix
            ],
            
            # Author search patterns
            'author': [
                r'\bauthor\s*:',                  # author: or author :
                r'\bauth\s*:',                    # auth: or auth :
                r'\bby\s*:',                      # by: or by :
                r'\bwritten\s+by\s+',             # written by
                r'\bauthored\s+by\s+',            # authored by
                r'\bwriter\s*:',                  # writer:
                r'\bcreator\s*:',                 # creator:
            ],
            
            # Corporate patterns
            'corporate': [
                r'^c\s*:',                    # starts with c: or c :
                r'\bc\s*:',                   # c: or c : anywhere
                r'^corp\s*:',                 # starts with corp: or corp :
                r'\bcorp\s*:',                # corp: or corp : anywhere
                r'^corporate\s*:',            # starts with corporate: or corporate :
                r'\bcorporate\s*:',          # corporate: or corporate : anywhere
            ],
            'country_corporate': [
                r'^c[A-Z]{2}\s*:',            # cUK:, cNO:, cNZ: etc.
                r'^c[A-Z]{3,}\s*:',           # cGREAT_BRITAIN:, cENGLAND: etc.
            ],
            
            # Site/URL patterns
            'site': r'site\s*:\s*[^\s]+',        # site:domain.com or site : domain.com
            'inurl': [                     # New pattern
                r'inurl\s*:\s*[^\s]+',           # inurl:keyword or inurl : keyword
                r'allinurl\s*:\s*[^\s]+',        # allinurl:keywords or allinurl : keywords
            ],
            'indom': r'indom\s*:\s*.+',      # indom:keyword or indom : keyword
            
            # EYE-D OSINT patterns
            'eye_d_email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\?$',
            'eye_d_phone': r'^(\+?\d{1,4}[\s.-]?)?\(?\d{1,4}\)?[\s.-]?\d{1,4}[\s.-]?\d{1,4}[\s.-]?\d{1,9}\?$',
            'eye_d_linkedin': r'^https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9-]+/?\?$',
            'eye_d_whois': r'^whois!\s*:\s*[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
            'eye_d_username': r'^(u|user|username):\s*(.+)$',  # u:username, user:username, username:username
            'eye_d_ip': r'^((25[0-5]|(2[0-4]|1\d|[1-9]|)\d)\.?\b){4}$|^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$',  # IPv4 and IPv6
            
            # Anchor search patterns
            'anchor': [
                r'anchor\s*:\s*"[^"]+"',        # anchor:"text"
                r'anchortext\s*:\s*"[^"]+"',    # anchortext:"phrase"
                r'anchor\s*:\s*[^\s]+',         # anchor:keyword
            ],
            
            # Address search patterns
            'address': [
                r'address\s*:\s*.+',             # address:123 Main St
                r'addr\s*:\s*.+',                # addr:123 Main St
                r'street\s*:\s*.+',              # street:Main Street
                r'physical\s*:\s*.+',            # physical:location
            ],
            
            # Media search patterns
            'image_search': [
                r'img![^\s]*',             # img! or img!query
                r'image![^\s]*',           # image! or image!query
                r'img\s*:\s*[^\s]+',       # img:keyword
                r'image\s*:\s*[^\s]+',     # image:keyword
            ],
            'video': [
                r'vid![^\s]*',             # vid! or vid!query
                r'video![^\s]*',           # video! or video!query
                r'video\s*:\s*[^\s]+',     # video:keyword
                r'vid\s*:\s*[^\s]+',       # vid:keyword
            ],
            'reverse_image': r'reverse!\s*:\s*[^\s]+',  # reverse!:url or reverse! : url
            
            # Title search patterns
            'title': [
                r'intitle\s*:\s*.+',              # intitle:keyword
                r'allintitle\s*:\s*.+',           # allintitle:keywords
                r'title\s*:\s*.+',                # title:keyword
            ],
            
            # Wildcards patterns
            'wildcards': [
                r'\*\w+',                         # *word (prefix wildcard)
                r'\w+\*',                         # word* (suffix wildcard)
                r'\w+\*\w+',                      # wo*rd (infix wildcard)
            ],
            
            # Author search
            'author_search': [
                r'author\s*:\s*[^\s]+',          # author:name or author : name
                r'by\s*:\s*[^\s]+',              # by:name or by : name
            ],
            'isbn': [
                r'isbn\s*:\s*[0-9Xx\-\s]+'      # isbn:978... or isbn: 0-321-14653-0
            ],
            
            # Book search
            'book': [
                r'book\s*:\s*.+',                # book:query or book : query
                r'books\s*:\s*.+',               # books:query or books : query
                r'(?:^|\s)book!',                 # book! macro
                r'(?:^|\s)books!',                # books! macro
            ],
            'academic': [
                r'(?:^|\s)academic!',            # academic! macro
                r'(?:^|\s)scholar!',             # scholar! macro
            ],
            'patent': [
                r'(?:^|\s)patent!',              # patent! macro
                r'(?:^|\s)patents!',             # patents! macro
                r'(?:^|\s)ip!',                  # ip! macro
            ],
            'code': [
                r'(?:^|\s)code!',                # code! macro (full-query aggregator)
                r'code\s*:\s*.+',               # code:query with optional helpers (legacy; normalized to code!)
            ],
            'social': [
                r'(?:^|\s)social!',              # social! macro
                r'social\s*:\s*.+',              # social: legacy
            ],
            'username': [
                r'username\s*:\s*[^\s]+',
                r'user\s*:\s*[^\s]+',
                r'handle\s*:\s*[^\s]+',    # handle:query
                r'@\w+',                    # @username
            ],
            
            # Forum patterns (contextual)
            'forum': [
                r'forum:',                 # forum:query
                r'discussion:',            # discussion:query
                r'discussions:',           # discussions:query
            ],
            
            # Social data collection (BrightData API - HIGH PRIORITY, must come before social_media)
            'social_data': [
                r'^fb:\s*',                # fb:username or fb:url (Facebook auto-detect)
                r'^facebook:\s*',          # facebook:username (Facebook auto-detect)
                r'^fbp:\s*',               # fbp:username (Facebook person/profile)
                r'^fbc:\s*',               # fbc:pagename (Facebook company/page)
                r'^insta:\s*',             # insta:username (Instagram profile)
                r'^instagram:\s*',         # instagram:username (Instagram profile)
                r'^ig:\s*',                # ig:username (Instagram profile)
                r'^li:\s*',                # li:username (LinkedIn auto-detect)
                r'^linkedin:\s*',          # linkedin:username (LinkedIn auto-detect)
                r'^lip:\s*',               # lip:username (LinkedIn person)
                r'^lic:\s*',               # lic:company (LinkedIn company)
            ],

            # NEWLY INTEGRATED PATTERNS (18 search types)
            'audio': [
                r'audio:',                 # audio:query
                r'sound:',                 # sound:query
                r'music:',                 # music:query
                r'podcast:',               # podcast:query
            ],
            'social_media': [
                r'social:',                # social:query
                r'sm:',                    # sm:query (social media)
                r'twitter:',               # twitter:query
                # Note: facebook:, instagram:, linkedin: are handled by social_data for BrightData collection
            ],
            'medical': [
                r'medical:',               # medical:query
                r'health:',                # health:query
                r'medicine:',              # medicine:query
                r'disease:',               # disease:query
            ],
            'edu': [
                r'edu:',                   # edu:query
                r'education:',             # education:query
                r'course:',                # course:query
                r'tutorial:',              # tutorial:query
            ],
            'product': [
                r'product:',               # product:query
                r'shop:',                  # shop:query
                r'buy:',                   # buy:query
                r'price:',                 # price:query
            ],
            # legal/public_records patterns intentionally deferred for now
            'recruitment': [
                r'(?:^|\s)jobs!',                # jobs! macro
                r'(?:^|\s)job!',                 # job! macro
                r'job:',                   # job:query (legacy)
                r'jobs:',                  # jobs:query (legacy)
                r'career:',                # career:query
                r'hire:',                  # hire:query
                r'hiring:',                # hiring:query
            ],
            'review': [
                r'review:',                # review:query
                r'reviews:',               # reviews:query
                r'rating:',                # rating:query
                r'feedback:',              # feedback:query
            ],
            'about': [
                r'\babout\s*:\s*(\"[^\"]+\"|\'[^\']+\'|\S+)',
                r'\btopic\s*:\s*(\"[^\"]+\"|\'[^\']+\'|\S+)'
            ],
            'blog': [
                r'blog:',                  # blog:query
                r'blogs:',                 # blogs:query
                r'article:',               # article:query
                r'post:',                  # post:query
            ],
            'email': [
                r'email:',                 # email:query (search, not OSINT)
                r'mail:',                  # mail:query
                r'gmail:',                 # gmail:query
                r'outlook:',               # outlook:query
            ],
            'event': [
                r'event:',                 # event:query
                r'events:',                # events:query
                r'conference:',            # conference:query
                r'meetup:',                # meetup:query
            ],
            'age': [
                r'age:',                   # age:query
                r'old:',                   # old:query
                r'new:',                   # new:query
                r'recent:',                # recent:query
            ],
            'dataset': [
                r'dataset:',               # dataset:query
                r'data:',                  # data:query
                r'csv:',                   # csv:query
                r'database:'              # database:query
            ],
        }
        
        # Define search type detection priority order
        # This matches the exact order in main.py's analyze_query()
        self.priority_order = [
            'scraper',           # ?? prefix (highest priority)
            'keyword_memory',    # "exact phrase" for keyword memory
            'wiki_search',       # Wiki operators (cr, lit, reg, ass, misc, wiki) - HIGH PRIORITY
            # EYE-D patterns MUST come before vector_memory to avoid conflicts
            'eye_d_email',       # EYE-D email pattern
            'eye_d_phone',       # EYE-D phone pattern
            'eye_d_linkedin',    # EYE-D LinkedIn pattern
            'eye_d_whois',       # EYE-D WHOIS pattern
            'eye_d_username',    # EYE-D username pattern (u:, user:, username:)
            'eye_d_ip',          # EYE-D IP geolocation pattern
            'vector_memory',     # questions ending with ? for vector memory
            'archived_date',     # Date-specific archive search
            'backlink',          # Backlink patterns
            'similar',           # Similar content patterns
            'related',           # Unified relationship discovery patterns
            # Google operators (must come before country patterns)
            'cache',             # cache: Google cached pages
            'link',              # link: pages linking to URL
            'info',              # info: information about URL
            'define',            # define: dictionary definitions
            'historic_entity_extraction', # Historic entity extraction (must come before historic)
            'historic',          # Historic archive patterns
            'country_anchor',    # Country-specific anchor text search (cuk:, puk:, etc.) - HIGH PRIORITY
            'anchor',            # Anchor text search patterns (NEW)
            'address',           # Address/location search patterns (address:, addr:, street:)
            'country_person',    # pUK:, pHU:, pNO: country-specific person search (HIGHER PRIORITY)
            'person',            # p: person name search (NOT p!: entity extraction)
            'corporate',         # c:, corp:, corporate: company search (CHECK BEFORE country_corporate)
            'country_corporate', # cUK:, cNO:, cNZ: country-specific corporate search
            'tor',               # tor: dark web/onion search
            'ip_address',        # ip: IP address intelligence search
            'crypto',            # crypto: cryptocurrency wallet search
            'entity_extraction', # Entity extraction patterns (moved up high priority)
            'domain_search',     # ol!, ga!, age! operations
            'keyword_domain_search',  # "keyword" :target
            'alldom',            # alldom:domain.com - find ALL URLs from domain
            # Specific media/content patterns MUST come before generic patterns
            'video',             # Video search patterns (MOVED UP for priority)
            'image_search',      # Image search patterns (MOVED UP for priority)
            'blog',              # Blog search (MOVED UP to come before news)
            'filetype',          # File type patterns
            'book',              # Book search patterns (book:, books:)
            'code',              # Code repos (code:)
            'about',            # About/subject search patterns
            'isbn',              # ISBN lookups
            'pdf',               # PDF search with Anna's Archive download links
            'academic',          # Academic search patterns (academic!, scholar!)
            'author',            # Author search patterns (author:, by:, etc.)
            'title',             # Title search patterns (intitle:, allintitle:)
            'wildcards',         # Wildcard patterns (*, word*, *word)
            'not_search',        # NOT and exclusion patterns
            'or_search',         # OR operator patterns
            'definitional',      # [bracketed] patterns
            # NEWLY INTEGRATED (18 search types)
            'social_data',       # BrightData social data collection (fb:, insta:, li:, etc.) - HIGH PRIORITY
            'audio',             # Audio search
            'medical',           # Medical/health search
            'edu',               # Educational content
            'product',           # Product/shopping search
            'recruitment',       # Job/career search
            'review',            # Reviews and ratings
            'email',             # Email search (not OSINT)
            'event',             # Event search
            'age',               # Age/recency search
            'dataset',           # Dataset search
            'username',          # Username search
            'language',          # Language patterns
            'location',          # Location patterns (loc:, near:, location:)
            'date',              # Date patterns
            'proximity',         # Proximity/wildcard patterns
            'forum',             # Forum search patterns
            'reverse_image',     # Reverse image search
            'site',              # Site-specific search
            'inurl',             # InURL search
            'indom',             # InDom search
        ]
        
        # Pre-processor patterns (handled before main search routing)
        self.preprocessor_patterns = {
            'translation': r'tr([a-z]{2})!(.+)',      # trXX!text (e.g., trde!, trfr!, tres!)
            'handshake': r'handshake\{([^}]+)\}',     # handshake{A,B,C}
            'variations': r"'([^']+)'",                # 'single quoted terms'
        }
        
        # Compile regex patterns for efficiency
        self._compiled_patterns = {}
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Pre-compile all regex patterns for better performance."""
        for pattern_type, patterns in self.patterns.items():
            if pattern_type in ['entity_extraction', 'historic_entity_extraction']:
                # Handle nested entity patterns
                self._compiled_patterns[pattern_type] = {}
                for entity_type, pattern in patterns.items():
                    self._compiled_patterns[pattern_type][entity_type] = re.compile(pattern, re.IGNORECASE)
            elif isinstance(patterns, list):
                self._compiled_patterns[pattern_type] = [re.compile(p, re.IGNORECASE) for p in patterns]
            elif isinstance(patterns, str):
                self._compiled_patterns[pattern_type] = re.compile(patterns, re.IGNORECASE)
    
    def detect_pattern(self, query: str) -> Tuple[str, List[str]]:
        """
        Detect the search pattern type and extract parameters.
        
        Args:
            query: The search query string
            
        Returns:
            Tuple of (pattern_type, parameters)
        """
        # First check for preprocessors (they should not be main patterns)
        preprocessor = self.check_preprocessor(query)
        if preprocessor and preprocessor[0] in ['translation', 'handshake', 'variations']:
            # These are handled by preprocessors, not main search
            # Return as exact_phrase for now
            return 'exact_phrase', [query]
        
        # Check NOT patterns before news detection
        if self._check_pattern(query, 'not_search'):
            return 'not_search', [query]
        
        # Check for news keywords early (before other patterns)
        if any(word in query.lower() for word in ['news', 'latest', 'breaking']):
            # But still check for higher priority patterns first
            for pattern_type in self.priority_order[:10]:  # Check first 10 high-priority patterns
                result = self._check_pattern(query, pattern_type)
                if result:
                    return result
            return 'news', [query]
        
        # Check patterns in priority order
        for pattern_type in self.priority_order:
            result = self._check_pattern(query, pattern_type)
            if result:
                return result
        
        # Default fallback
        if self._is_exact_phrase_search(query):
            return 'exact_phrase', [query]
        
        # Multi-word or single word - use exact phrase
        return 'exact_phrase', [query]
    
    def _check_pattern(self, query: str, pattern_type: str) -> Optional[Tuple[str, List[str]]]:
        """Check if query matches a specific pattern type."""
        
        if pattern_type == 'scraper':
            if query.startswith('??'):
                return 'scraper', [query[2:].strip()]
        
        elif pattern_type == 'or_search':
            if self._has_or_operator(query):
                return 'or_search', self._split_or_query(query)
        
        elif pattern_type in ['entity_extraction', 'historic_entity_extraction']:
            # Check each entity type
            for entity_type, compiled_re in self._compiled_patterns[pattern_type].items():
                match = compiled_re.match(query)
                if match:
                    return pattern_type, [query, entity_type]
        
        elif pattern_type == 'country_anchor':
            # Check country anchor patterns
            patterns = self._compiled_patterns.get(pattern_type)
            if patterns and isinstance(patterns, list):
                for pattern in patterns:
                    match = pattern.match(query.lower())  # Case insensitive
                    if match:
                        return 'country_anchor', [query]
        
        elif pattern_type == 'forum':
            if self._has_forum_pattern(query):
                return 'forum', [query]
        
        elif pattern_type == 'indom':
            # Use the compiled regex pattern instead of hardcoded logic
            patterns = self._compiled_patterns.get(pattern_type)
            if patterns and patterns.search(query):
                return pattern_type, [query]
        
        elif pattern_type == 'alldom':
            match = self._compiled_patterns.get('alldom')
            if match and match.match(query):
                # Extract just the domain from alldom:domain.com
                domain = query.split(':', 1)[1].strip()
                return 'alldom', [domain]
        
        elif pattern_type == 'keyword_domain_search':
            # Check keyword domain patterns
            patterns = self._compiled_patterns.get(pattern_type)
            if patterns and isinstance(patterns, list):
                for pattern in patterns:
                    match = pattern.match(query)
                    if match:
                        return 'keyword_domain_search', [query]
        
        else:
            # Generic pattern checking
            patterns = self._compiled_patterns.get(pattern_type)
            if patterns:
                if isinstance(patterns, list):
                    for pattern in patterns:
                        if pattern.search(query):
                            return pattern_type, [query]
                else:
                    if patterns.search(query):
                        return pattern_type, [query]
        
        return None
    
    def _has_or_operator(self, query: str) -> bool:
        """Check if query contains OR operator."""
        # Check for surrounded by spaces to avoid matching URLs
        return ' / ' in query or ' OR ' in query
    
    def _split_or_query(self, query: str) -> List[str]:
        """Split query by OR operator."""
        # Only replace / when surrounded by spaces
        query = query.replace(' / ', ' OR ').replace(' OR OR ', ' OR ')
        return [q.strip() for q in query.split(' OR ') if q.strip()]
    
    def _has_forum_pattern(self, query: str) -> bool:
        """Check for forum-related patterns."""
        query_lower = query.lower()
        
        # Direct operators
        if any(op in query_lower for op in ['forum:', 'discussion:', 'discussions:']):
            return True
        
        # Contextual patterns
        forum_patterns = [
            r'\breddit\b.*\b(discussion|post|comment|thread)\b',
            r'\b(discussion|thread|post)\b.*\b(forum|reddit|board)\b',
            r'\b(forum|community)\b.*\b(discussion|thread|post)\b',
            r'\bforum\b',
            r'\breddit\b',
        ]
        
        for pattern in forum_patterns:
            if re.search(pattern, query_lower):
                return True
        
        return False
    
    def _is_exact_phrase_search(self, query: str) -> bool:
        """Check if query is an exact phrase search."""
        # Quoted strings
        if (query.startswith('"') and query.endswith('"')) or \
           (query.startswith("'") and query.endswith("'")):
            return True
        
        # Multi-word phrases
        if ' ' in query.strip():
            return True
        
        return False
    
    def check_preprocessor(self, query: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Check for pre-processor patterns (translation, handshake, variations).
        
        Returns:
            Tuple of (preprocessor_type, extracted_data) or None
        """
        # Check translation
        trans_match = re.match(self.preprocessor_patterns['translation'], query, re.IGNORECASE)
        if trans_match:
            return 'translation', {
                'language': trans_match.group(1),
                'text': trans_match.group(2)
            }
        
        # Check handshake
        handshake_match = re.search(self.preprocessor_patterns['handshake'], query)
        if handshake_match:
            items = [item.strip() for item in handshake_match.group(1).split(',')]
            return 'handshake', {'items': items, 'full_match': handshake_match.group(0)}
        
        # Check variations (single quotes)
        variations = re.findall(self.preprocessor_patterns['variations'], query)
        if variations:
            return 'variations', {'terms': variations}
        
        return None
    
    def get_pattern_info(self, pattern_type: str) -> Dict[str, Any]:
        """Get information about a specific pattern type."""
        return {
            'type': pattern_type,
            'patterns': self.patterns.get(pattern_type, []),
            'priority': self.priority_order.index(pattern_type) if pattern_type in self.priority_order else -1,
            'is_preprocessor': pattern_type in self.preprocessor_patterns
        }
    
    def export_patterns_for_frontend(self) -> Dict[str, Any]:
        """Export pattern information that could be used by frontend."""
        return {
            'search_patterns': {
                ptype: self.patterns[ptype] 
                for ptype in self.patterns 
                if isinstance(self.patterns[ptype], (str, list))
            },
            'preprocessor_patterns': self.preprocessor_patterns,
            'priority_order': self.priority_order
        }
