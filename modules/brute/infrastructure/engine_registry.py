#!/usr/bin/env python3
"""
Engine Registry - Central registry bridging routing and execution.

Provides:
1. EXTENDED_ENGINE_CONFIG - ENGINE_CONFIG from brute.py + routing metadata (tiers, tags)
2. get_engine_registry() - Returns dict mapping engine codes to runner classes
3. get_engine_tiers() - Returns dict mapping codes to tier names

This module bridges the routing system (query_router.py) with the execution
system (brute.py ENGINE_CONFIG) for the BruteSearchOptimal orchestrator.
"""
from __future__ import annotations

import logging
import importlib
import sys
import os
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Type

# Ensure module paths include brute roots
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

logger = logging.getLogger(__name__)

# Import ENGINE_TAGS from routing for tier/tag metadata
try:
    from brute.routing.query_router import QueryRouter
    ENGINE_TAGS = QueryRouter.ENGINE_TAGS
except ImportError:
    try:
        from .routing.query_router import QueryRouter
        ENGINE_TAGS = QueryRouter.ENGINE_TAGS
    except ImportError:
        # Fallback - define minimal tags
        logger.warning("Could not import ENGINE_TAGS from query_router")
        ENGINE_TAGS = {}


@dataclass
class EngineConfig:
    """Complete engine configuration with routing metadata."""
    code: str
    name: str
    module: str
    class_name: str

    # Routing metadata
    tier: str = 'fast'  # lightning, fast, standard, slow, very_slow
    tags: Set[str] = field(default_factory=set)
    reliability: float = 0.85

    # Execution config
    supports_streaming: bool = False
    disabled: bool = False
    status: str = 'active'  # active, deprecated, stub

    # Factory kwargs
    init_kwargs: Optional[Callable[[], Dict[str, Any]]] = None

    # Wrapper engine support (modern thin wrappers)
    wrapper_module: Optional[str] = None
    wrapper_class: Optional[str] = None


# Extended engine config combining brute.py ENGINE_CONFIG with routing metadata
EXTENDED_ENGINE_CONFIG: Dict[str, EngineConfig] = {
    # ─────────────────────────────────────────────────────────────
    # LIGHTNING TIER - Sub-second response, highest reliability
    # ─────────────────────────────────────────────────────────────
    'BI': EngineConfig(
        code='BI', name='Bing',
        module='engines.exact_phrase_recall_runner_bing',
        class_name='ExactPhraseRecallRunnerBing',
        tier='lightning', tags={'general', 'web', 'news', 'corporate'},
        reliability=0.97, supports_streaming=True
    ),
    'DD': EngineConfig(
        code='DD', name='DuckDuckGo',
        module='engines.exact_phrase_recall_runner_duckduck',
        class_name='MaxExactDuckDuckGo',
        tier='lightning', tags={'general', 'web', 'privacy'},
        reliability=0.96, supports_streaming=False
    ),
    'BR': EngineConfig(
        code='BR', name='Brave',
        module='engines.exact_phrase_recall_runner_brave',
        class_name='ExactPhraseRecallRunnerBrave',
        tier='lightning', tags={'general', 'web', 'privacy'},
        reliability=0.95, supports_streaming=True
    ),
    'NA': EngineConfig(
        code='NA', name='NewsAPI',
        module='engines.exact_phrase_recall_runner_newsapi',
        class_name='ExactPhraseRecallRunnerNewsAPI',
        tier='lightning', tags={'news', 'current_events', 'media'},
        reliability=0.90, supports_streaming=False
    ),
    'PW': EngineConfig(
        code='PW', name='PublicWWW',
        module='engines.exact_phrase_recall_runner_publicwww',
        class_name='PublicWWWSearch',
        tier='lightning', tags={'code', 'html', 'source'},
        reliability=0.82, supports_streaming=False
    ),
    'SP': EngineConfig(
        code='SP', name='Startpage',
        module='engines.exact_phrase_recall_runner_startpage',
        class_name='ExactPhraseRecallRunnerStartpage',
        tier='lightning', tags={'general', 'privacy'},
        reliability=0.88, supports_streaming=False
    ),
    'YO': EngineConfig(
        code='YO', name='You.com',
        module='engines.exact_phrase_recall_runner_you',
        class_name='ExactPhraseRecallRunnerYou',
        tier='lightning', tags={'general', 'ai'},
        reliability=0.85, supports_streaming=True
    ),

    # ─────────────────────────────────────────────────────────────
    # FAST TIER - 1-5 second response, high reliability
    # ─────────────────────────────────────────────────────────────
    'YA': EngineConfig(
        code='YA', name='Yandex',
        module='engines.exact_phrase_recall_runner_yandex',
        class_name='ExactPhraseRecallRunnerYandex',
        tier='fast', tags={'general', 'web', 'regional_ru'},
        reliability=0.94, supports_streaming=True
    ),
    'QW': EngineConfig(
        code='QW', name='Qwant',
        module='engines.exact_phrase_recall_runner_qwant',
        class_name='ExactPhraseRecallRunnerQwant',
        tier='fast', tags={'general', 'web', 'regional_eu', 'privacy'},
        reliability=0.90, supports_streaming=True
    ),
    'SE': EngineConfig(
        code='SE', name='SemanticScholar',
        module='engines.exact_phrase_recall_runner_semantic_scholar',
        class_name='ExactPhraseRecallRunnerSemanticScholar',
        tier='fast', tags={'academic', 'research', 'papers'},
        reliability=0.93, supports_streaming=True
    ),
    'OA': EngineConfig(
        code='OA', name='OpenAlex',
        module='engines.exact_phrase_recall_runner_openalex',
        class_name='ExactPhraseRecallRunnerOpenAlex',
        tier='fast', tags={'academic', 'research', 'papers'},
        reliability=0.91, supports_streaming=True
    ),
    'CR': EngineConfig(
        code='CR', name='Crossref',
        module='engines.exact_phrase_recall_runner_crossref',
        class_name='ExactPhraseRecallRunnerCrossref',
        tier='fast', tags={'academic', 'research', 'papers', 'doi'},
        reliability=0.92, supports_streaming=True
    ),
    'JS': EngineConfig(
        code='JS', name='JSTOR',
        module='engines.exact_phrase_recall_runner_jstor',
        class_name='ExactPhraseRecallRunnerJSTOR',
        tier='fast', tags={'academic', 'research', 'papers', 'books'},
        reliability=0.88, supports_streaming=False
    ),
    'SG': EngineConfig(
        code='SG', name='SAGEJournals',
        module='engines.exact_phrase_recall_runner_sage',
        class_name='ExactPhraseRecallRunnerSAGE',
        tier='fast', tags={'academic', 'research', 'papers'},
        reliability=0.87, supports_streaming=False
    ),
    'MU': EngineConfig(
        code='MU', name='ProjectMUSE',
        module='engines.exact_phrase_recall_runner_muse',
        class_name='ExactPhraseRecallRunnerMUSE',
        tier='fast', tags={'academic', 'research', 'papers'},
        reliability=0.87, supports_streaming=False
    ),
    'NT': EngineConfig(
        code='NT', name='Nature',
        module='engines.exact_phrase_recall_runner_nature',
        class_name='ExactPhraseRecallRunnerNature',
        tier='fast', tags={'academic', 'research', 'papers', 'science'},
        reliability=0.89, supports_streaming=False
    ),
    'GR': EngineConfig(
        code='GR', name='Grok',
        module='engines.exact_phrase_recall_runner_grok_http',
        class_name='ExactPhraseRecallRunnerGrok',
        tier='fast', tags={'news', 'social', 'realtime'},
        reliability=0.88, supports_streaming=False
    ),
    'GU': EngineConfig(
        code='GU', name='Gutenberg',
        module='engines.exact_phrase_recall_runner_gutenberg',
        class_name='ExactPhraseRecallRunnerGutenberg',
        tier='fast', tags={'books', 'literature', 'free'},
        reliability=0.90, supports_streaming=False
    ),
    'OL': EngineConfig(
        code='OL', name='OpenLibrary',
        module='engines.exact_phrase_recall_runner_openlibrary',
        class_name='ExactPhraseRecallRunnerOpenLibrary',
        tier='fast', tags={'books', 'library'},
        reliability=0.88, supports_streaming=True
    ),
    'BK': EngineConfig(
        code='BK', name='Books',
        module='brute.targeted_searches.special.book',
        class_name='BookSearchRunner',
        tier='fast', tags={'books', 'literature'},
        reliability=0.85, supports_streaming=True
    ),
    'AA': EngineConfig(
        code='AA', name='AnnasArchive',
        module='engines.exact_phrase_recall_runner_annas_archive',
        class_name='ExactPhraseRecallRunnerAnnasArchive',
        tier='fast', tags={'books', 'archives', 'shadow'},
        reliability=0.80, supports_streaming=True
    ),
    'AR': EngineConfig(
        code='AR', name='Archive.org',
        module='engines.exact_phrase_recall_runner_archiveorg',
        class_name='ExactPhraseRecallRunnerArchiveOrg',
        tier='fast', tags={'archives', 'historical', 'wayback'},
        reliability=0.92, supports_streaming=False
    ),
    'W': EngineConfig(
        code='W', name='WikiLeaks',
        module='engines.exact_phrase_recall_runner_wikileaks',
        class_name='ExactPhraseRecallRunnerWikiLeaks',
        tier='fast', tags={'archives', 'leaks', 'investigative'},
        reliability=0.82, supports_streaming=True
    ),
    'SS': EngineConfig(
        code='SS', name='SocialSearcher',
        module='engines.exact_phrase_recall_runner_socialsearcher',
        class_name='ExactPhraseRecallRunnerSocialSearcher',
        tier='fast', tags={'social', 'social_media'},
        reliability=0.80, supports_streaming=True
    ),
    'BS': EngineConfig(
        code='BS', name='BareSearch',
        module='engines.exact_phrase_recall_runner_baresearch',
        class_name='ExactPhraseRecallRunnerBareSearch',
        tier='fast', tags={'general', 'web'},
        reliability=0.80, supports_streaming=False
    ),
    'BA': EngineConfig(
        code='BA', name='Baidu',
        module='engines.exact_phrase_recall_runner_baidu',
        class_name='ExactPhraseRecallRunnerBaidu',
        tier='fast', tags={'general', 'regional_cn'},
        reliability=0.85, supports_streaming=True
    ),

    # ─────────────────────────────────────────────────────────────
    # STANDARD TIER - 5-15 second response, good reliability
    # ─────────────────────────────────────────────────────────────
    'GO': EngineConfig(
        code='GO', name='Google',
        module='engines.exact_phrase_recall_runner_google',
        class_name='ExactPhraseRecallRunner',
        tier='standard', tags={'general', 'web', 'news', 'local'},
        reliability=0.98, supports_streaming=True
    ),
    'AX': EngineConfig(
        code='AX', name='arXiv',
        module='engines.exact_phrase_recall_runner_arxiv',
        class_name='ExactPhraseRecallRunnerArxiv',
        tier='standard', tags={'academic', 'research', 'papers', 'preprints'},
        reliability=0.93, supports_streaming=True
    ),
    'PM': EngineConfig(
        code='PM', name='PubMed',
        module='engines.exact_phrase_recall_runner_pubmed',
        class_name='ExactPhraseRecallRunnerPubMed',
        tier='standard', tags={'academic', 'medical', 'research', 'papers'},
        reliability=0.94, supports_streaming=True
    ),
    'GD': EngineConfig(
        code='GD', name='GDELT',
        module='engines.exact_phrase_recall_runner_gdelt',
        class_name='ExactPhraseRecallRunnerGDELT',
        tier='standard', tags={'news', 'global', 'events'},
        reliability=0.85, supports_streaming=False
    ),
    'WP': EngineConfig(
        code='WP', name='Wikipedia',
        module='engines.exact_phrase_recall_runner_wikipedia',
        class_name='ExactPhraseRecallRunnerWikipedia',
        tier='standard', tags={'reference', 'facts', 'historical'},
        reliability=0.95, supports_streaming=True
    ),
    'EX': EngineConfig(
        code='EX', name='Exa',
        module='engines.exact_phrase_recall_runner_exa',
        class_name='ExactPhraseRecallRunnerExa',
        tier='standard', tags={'general', 'semantic', 'ai'},
        reliability=0.91, supports_streaming=True
    ),

    # ─────────────────────────────────────────────────────────────
    # SLOW TIER - 15-30 second response
    # ─────────────────────────────────────────────────────────────
    'YE': EngineConfig(
        code='YE', name='Yep',
        module='engines.exact_phrase_recall_runner_yep',
        class_name='YepExactPhraseRecallRunner',
        tier='slow', tags={'general', 'web'},
        reliability=0.78, supports_streaming=True
    ),

    # ─────────────────────────────────────────────────────────────
    # VERY SLOW TIER - 30+ second response
    # ─────────────────────────────────────────────────────────────
    'LG': EngineConfig(
        code='LG', name='LibGen',
        module='engines.exact_phrase_recall_runner_libgen',
        class_name='ExactPhraseRecallRunnerLibGen',
        tier='very_slow', tags={'books', 'shadow', 'academic'},
        reliability=0.75, supports_streaming=True
    ),
    'HF': EngineConfig(
        code='HF', name='HuggingFace',
        module='engines.exact_phrase_recall_runner_huggingface_fixed',
        class_name='MaxExactHuggingFace',
        tier='very_slow', tags={'code', 'ml', 'ai', 'models'},
        reliability=0.85, supports_streaming=True
    ),
    'AL': EngineConfig(
        code='AL', name='Aleph',
        module='engines.exact_phrase_recall_runner_aleph',
        class_name='ExactPhraseRecallRunnerAleph',
        tier='very_slow', tags={'corporate', 'osint', 'leaks', 'documents'},
        reliability=0.80, supports_streaming=False
    ),

    # ─────────────────────────────────────────────────────────────
    # DISABLED / STUB ENGINES
    # ─────────────────────────────────────────────────────────────
    'BO': EngineConfig(
        code='BO', name='BoardReader',
        module='engines.exact_phrase_recall_runner_boardreader',
        class_name='ExactPhraseRecallRunnerBoardreaderV2',
        tier='fast', tags={'social', 'forums', 'discussions'},
        reliability=0.75, supports_streaming=False,
        disabled=False, status='active'
    ),
}


def get_engine_tiers() -> Dict[str, str]:
    """
    Return dict mapping engine codes to tier names.

    Used by CascadeExecutor to group engines into waves.
    """
    return {code: cfg.tier for code, cfg in EXTENDED_ENGINE_CONFIG.items()}


def get_engine_tags() -> Dict[str, Set[str]]:
    """
    Return dict mapping engine codes to tag sets.

    Used by QueryRouter for capability-based selection.
    """
    return {code: cfg.tags for code, cfg in EXTENDED_ENGINE_CONFIG.items()}


def get_active_engines() -> List[str]:
    """Return list of active engine codes (ignore disabled flag to force max recall)."""
    return list(EXTENDED_ENGINE_CONFIG.keys())


def get_engines_by_tier(tier: str) -> List[str]:
    """Return engine codes for a specific tier."""
    return [
        code for code, cfg in EXTENDED_ENGINE_CONFIG.items()
        if cfg.tier == tier and not cfg.disabled
    ]


def get_engines_by_tag(tag: str) -> List[str]:
    """Return engine codes that have a specific tag."""
    return [
        code for code, cfg in EXTENDED_ENGINE_CONFIG.items()
        if tag in cfg.tags and not cfg.disabled
    ]


def load_engine_class(code: str) -> Optional[Type]:
    """
    Dynamically load engine runner class for a given code.

    Returns the class or None if loading fails.
    """
    if code not in EXTENDED_ENGINE_CONFIG:
        logger.warning("Unknown engine code: %s", code)
        return None

    cfg = EXTENDED_ENGINE_CONFIG[code]

    if cfg.disabled:
        logger.debug("Engine %s is disabled", code)
        return None

    module_paths = [cfg.module]
    # Fallbacks for legacy paths
    module_paths.append(f"modules.brute.{cfg.module}")
    if cfg.module.startswith("engines."):
        base = cfg.module.split(".")[-1]
        module_paths.append(f"modules.brute.engines.{base}")
        module_paths.append(f"brute.engines.{base}")
        # Heuristic: many files are named without the exact_phrase_recall_runner_ prefix
        if base.startswith("exact_phrase_recall_runner_"):
            stripped = base.replace("exact_phrase_recall_runner_", "")
            module_paths.append(f"modules.brute.engines.{stripped}")
            module_paths.append(f"brute.engines.{stripped}")
            module_paths.append(f"engines.{stripped}")

    # Heuristic based on engine human name (e.g., "Bing" -> bing)
    guessed = cfg.name.lower().replace(" ", "_")
    module_paths.append(f"modules.brute.engines.{guessed}")
    module_paths.append(f"brute.engines.{guessed}")
    module_paths.append(f"engines.{guessed}")

    last_exc: Optional[Exception] = None
    for mp in module_paths:
        try:
            module = importlib.import_module(mp)
            runner_class = getattr(module, cfg.class_name)
            return runner_class
        except Exception as exc:  # noqa: E722
            last_exc = exc
            continue

    # Final fallback: scan engines directory for matching class name
    engines_dir = os.path.join(BASE_DIR, 'engines')
    if os.path.isdir(engines_dir):
        for file in os.listdir(engines_dir):
            if not file.endswith(".py") or file.startswith("__"):
                continue
            module_name = f"brute.engines.{file[:-3]}"
            try:
                module = importlib.import_module(module_name)
                if hasattr(module, cfg.class_name):
                    return getattr(module, cfg.class_name)
                # Fallback: pick any class in module with matching engine code attribute
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if getattr(obj, "code", None) == code:
                        return obj
            except Exception:
                continue

    logger.warning("Failed to load engine %s (%s.%s): %s",
                  code, cfg.module, cfg.class_name, last_exc)
    return None


def get_engine_registry() -> Dict[str, Type]:
    """
    Build registry mapping engine codes to runner classes.

    Loads all active engines and returns a dict for use by
    CascadeExecutor and BruteSearchOptimal.
    """
    registry: Dict[str, Type] = {}

    for code in get_active_engines():
        runner_class = load_engine_class(code)
        if runner_class:
            registry[code] = runner_class

    logger.info("Loaded %d engines into registry", len(registry))
    return registry


# Tier timeout configurations (ms)
TIER_TIMEOUTS = {
    'lightning': 15000,   # 15s
    'fast': 30000,        # 30s
    'standard': 60000,    # 60s
    'slow': 90000,        # 90s
    'very_slow': 120000,  # 120s
}


if __name__ == '__main__':
    # Demo the registry
    print("Engine Registry - Demo")
    print("=" * 60)

    # Show tier breakdown
    print("\nEngines by Tier:")
    for tier in ['lightning', 'fast', 'standard', 'slow', 'very_slow']:
        engines = get_engines_by_tier(tier)
        print(f"  {tier}: {len(engines)} engines - {', '.join(engines)}")

    # Show tag examples
    print("\nEngines by Tag (examples):")
    for tag in ['academic', 'news', 'books', 'code', 'regional_eu']:
        engines = get_engines_by_tag(tag)
        print(f"  {tag}: {', '.join(engines[:5])}{'...' if len(engines) > 5 else ''}")

    # Show active engines
    active = get_active_engines()
    print(f"\nActive engines: {len(active)}")

    # Show disabled engines
    disabled = [code for code, cfg in EXTENDED_ENGINE_CONFIG.items() if cfg.disabled]
    print(f"Disabled engines: {len(disabled)} - {', '.join(disabled)}")

    # Test loading a few engines
    print("\nTesting engine loading:")
    for code in ['GO', 'BI', 'SE', 'NA', 'BO']:
        runner = load_engine_class(code)
        status = 'loaded' if runner else 'failed/disabled'
        print(f"  {code}: {status}")
