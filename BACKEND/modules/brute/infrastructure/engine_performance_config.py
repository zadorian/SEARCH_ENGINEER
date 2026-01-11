#!/usr/bin/env python3
"""
Engine Performance Configuration
=================================
Optimized engine configurations based on performance benchmarks.
Auto-generated from benchmark results on 2025-11-18.
"""

# Engine initialization times from benchmarks (in milliseconds)
ENGINE_INIT_TIMES = {
    'DD': 0.006,      # DuckDuckGo - Fastest
    'BR': 0.163,      # Brave
    'BI': 0.180,      # Bing
    'PW': 0.334,      # PublicWWW
    'SP': 0.637,      # Startpage
    'NA': 0.823,      # NewsAPI
    'YO': 0.848,      # You.com
    'W': 1.132,       # WikiLeaks
    'BS': 1.244,      # BareSearch
    'AR': 1.281,      # Archive.org
    'BA': 2.017,      # Baidu
    'QW': 3.447,      # Qwant
    'SG': 4.300,      # SAGEJournals
    'MU': 4.361,      # ProjectMUSE
    'NT': 4.748,      # Nature
    'JS': 4.750,      # JSTOR
    'GU': 4.777,      # Gutenberg
    'OL': 4.944,      # OpenLibrary
    'BK': 5.114,      # Books
    'YA': 5.062,      # Yandex
    'SE': 5.316,      # SemanticScholar
    'OA': 5.330,      # OpenAlex
    'CR': 5.382,      # Crossref
    'AA': 6.169,      # AnnasArchive
    'GR': 7.364,      # Grok
    'BO': 8.983,      # BoardReader
    'SS': 9.321,      # SocialSearcher
    'GD': 10.034,     # GDELT
    'AX': 11.015,     # arXiv
    'WP': 11.492,     # Wikipedia
    'EX': 13.042,     # Exa
    'PM': 15.680,     # PubMed
    'GO': 43.321,     # Google
    'YE': 171.185,    # Yep - Slow
    'LG': 384.033,    # LibGen - Very Slow
    'AL': 493.404,    # Aleph - Very Slow
    'HF': 2845.512,   # HuggingFace - Extremely Slow
}

# Engine tiers based on performance
PERFORMANCE_TIERS = {
    'lightning': [    # < 1ms - Ultra Fast
        'DD', 'BR', 'BI', 'PW', 'SP', 'NA', 'YO'
    ],
    'fast': [         # 1-10ms - Fast
        'W', 'BS', 'AR', 'BA', 'QW', 'SG', 'MU', 'NT',
        'JS', 'GU', 'OL', 'BK', 'YA', 'SE', 'OA', 'CR',
        'AA', 'GR', 'BO', 'SS'
    ],
    'standard': [     # 10-50ms - Standard
        'GD', 'AX', 'WP', 'EX', 'PM', 'GO'
    ],
    'slow': [         # 50-200ms - Slow but usable
        'YE'
    ],
    'very_slow': [    # > 200ms - Use only when needed
        'LG', 'AL', 'HF'
    ]
}

# Optimized default engine sets for different use cases
OPTIMIZED_ENGINE_SETS = {
    # Maximum speed - only the fastest engines
    'speed': ['DD', 'BR', 'BI', 'SP', 'YO'],

    # Balanced - fast engines with good coverage
    'balanced': ['DD', 'BR', 'BI', 'GO', 'YA', 'QW', 'AR', 'EX'],

    # Comprehensive - all engines except the slowest
    'comprehensive': [e for e in ENGINE_INIT_TIMES.keys() if e not in ['HF', 'AL', 'LG']],

    # Academic - fast academic engines
    'academic': ['OA', 'CR', 'SE', 'AX', 'PM', 'WP', 'GU', 'JS'],

    # News - fast news engines
    'news': ['NA', 'GR', 'GD'],

    # Social - social media engines
    'social': ['SS', 'BO'],

    # Archives - archive engines (excluding slow ones)
    'archives': ['AR', 'AA'],
}

# Engine health scores (based on typical success rates)
ENGINE_RELIABILITY = {
    'GO': 0.98,  # Google - Very Reliable
    'BI': 0.97,  # Bing - Very Reliable
    'DD': 0.96,  # DuckDuckGo - Very Reliable
    'BR': 0.95,  # Brave - Reliable
    'YA': 0.94,  # Yandex - Reliable
    'AR': 0.92,  # Archive.org - Reliable
    'EX': 0.91,  # Exa - Reliable
    'QW': 0.90,  # Qwant - Reliable
    'WP': 0.95,  # Wikipedia - Very Reliable
    'SE': 0.93,  # SemanticScholar - Reliable
    'CR': 0.92,  # Crossref - Reliable
    'OA': 0.91,  # OpenAlex - Reliable
    'PM': 0.94,  # PubMed - Reliable
    'AX': 0.93,  # arXiv - Reliable
    # Others default to 0.85
}

def get_fast_engines(max_init_time_ms=10.0):
    """Get engines that initialize faster than specified time.

    Args:
        max_init_time_ms: Maximum initialization time in milliseconds

    Returns:
        List of engine codes sorted by speed
    """
    return [
        engine for engine, time in sorted(ENGINE_INIT_TIMES.items(), key=lambda x: x[1])
        if time <= max_init_time_ms
    ]

def get_engines_for_tier(tier_name='balanced'):
    """Get optimized engine set for a specific use case.

    Args:
        tier_name: One of 'speed', 'balanced', 'comprehensive', 'academic', 'news', 'social', 'archives'

    Returns:
        List of engine codes optimized for the use case
    """
    return OPTIMIZED_ENGINE_SETS.get(tier_name, OPTIMIZED_ENGINE_SETS['balanced'])

def get_engine_performance_score(engine_code):
    """Calculate overall performance score for an engine.

    Score factors:
    - Speed: 70% weight (inverted init time)
    - Reliability: 30% weight

    Args:
        engine_code: Engine code

    Returns:
        Performance score (0-100)
    """
    if engine_code not in ENGINE_INIT_TIMES:
        return 0

    # Speed score (0-100, inversely proportional to init time)
    # Normalize: 0.006ms = 100, 2845ms = 0
    max_time = max(ENGINE_INIT_TIMES.values())
    init_time = ENGINE_INIT_TIMES[engine_code]
    speed_score = 100 * (1 - (init_time / max_time))

    # Reliability score (0-100)
    reliability = ENGINE_RELIABILITY.get(engine_code, 0.85)
    reliability_score = reliability * 100

    # Combined score
    return 0.7 * speed_score + 0.3 * reliability_score

def recommend_engines_for_query(query_type='general', max_engines=8):
    """Recommend engines based on query type and performance.

    Args:
        query_type: Type of query ('general', 'academic', 'news', 'technical', 'historical')
        max_engines: Maximum number of engines to recommend

    Returns:
        List of recommended engine codes
    """
    if query_type == 'academic':
        base_set = OPTIMIZED_ENGINE_SETS['academic']
    elif query_type == 'news':
        base_set = OPTIMIZED_ENGINE_SETS['news']
    elif query_type == 'historical':
        base_set = ['AR', 'AA', 'WP', 'GO', 'BI']
    elif query_type == 'technical':
        base_set = ['GO', 'DD', 'HF', 'GR', 'SE']
    else:
        base_set = OPTIMIZED_ENGINE_SETS['balanced']

    # Filter out very slow engines unless specifically needed
    if query_type != 'technical':
        base_set = [e for e in base_set if e not in PERFORMANCE_TIERS['very_slow']]

    # Sort by performance score and return top N
    scored = [(e, get_engine_performance_score(e)) for e in base_set]
    scored.sort(key=lambda x: x[1], reverse=True)

    return [e[0] for e in scored[:max_engines]]

# Configuration for adaptive engine selection
ADAPTIVE_CONFIG = {
    'timeout_multipliers': {
        'lightning': 1.0,   # Normal timeout
        'fast': 1.2,        # 20% more time
        'standard': 1.5,    # 50% more time
        'slow': 2.0,        # Double timeout
        'very_slow': 3.0    # Triple timeout
    },
    'retry_limits': {
        'lightning': 3,     # More retries for fast engines
        'fast': 2,
        'standard': 2,
        'slow': 1,
        'very_slow': 1      # Single attempt for slow engines
    },
    'parallel_limits': {
        'lightning': 10,    # Can run many in parallel
        'fast': 8,
        'standard': 5,
        'slow': 3,
        'very_slow': 1      # Run sequentially
    }
}

if __name__ == '__main__':
    # Demo the configuration
    print("Engine Performance Configuration")
    print("="*50)

    print("\n🚀 Lightning Fast Engines (<1ms):")
    for engine in PERFORMANCE_TIERS['lightning']:
        print(f"  {engine}: {ENGINE_INIT_TIMES[engine]:.3f}ms")

    print("\n🎯 Recommended Engines by Use Case:")
    for use_case in ['speed', 'balanced', 'academic', 'news']:
        engines = get_engines_for_tier(use_case)[:5]
        print(f"  {use_case.title()}: {', '.join(engines)}")

    print("\n📊 Top 5 Engines by Performance Score:")
    all_engines = list(ENGINE_INIT_TIMES.keys())
    scores = [(e, get_engine_performance_score(e)) for e in all_engines]
    scores.sort(key=lambda x: x[1], reverse=True)
    for engine, score in scores[:5]:
        print(f"  {engine}: {score:.1f}/100")