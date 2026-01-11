#!/usr/bin/env python3
"""
Engine Status - Simple engine availability checker
"""

import sys
import importlib
from pathlib import Path
from typing import Dict, Tuple, List

# Add paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'engines'))


def check_engine_availability() -> Dict[str, bool]:
    """Check which engines are available"""
    engines = {
        'google': ('exact_phrase_recall_runner_google', 'GoogleSearch'),
        'bing': ('exact_phrase_recall_runner_bing', 'BingSearch'),
        'yandex': ('exact_phrase_recall_runner_yandex', 'YandexSearch'),
        'duckduckgo': ('exact_phrase_recall_runner_duckduck', 'MaxExactDuckDuckGo'),
        'yep': ('exact_phrase_recall_runner_yep', 'YepScraper'),
        'brave': ('exact_phrase_recall_runner_brave', 'BraveSearch'),
        'boardreader': ('exact_phrase_recall_runner_boardreader', 'BoardReaderSearch'),
        'exa': ('exact_phrase_recall_runner_exa', 'ExaSearch'),
        'gdelt': ('exact_phrase_recall_runner_gdelt', 'GDELTSearch'),
        'grok': ('exact_phrase_recall_runner_grok', 'GrokSearch'),
        'publicwww': ('exact_phrase_recall_runner_publicwww', 'PublicWWWSearch'),
        'socialsearcher': ('exact_phrase_recall_runner_socialsearcher', 'SocialSearcherSearch'),
        'aleph': ('exact_phrase_recall_runner_aleph', 'AlephSearch'),
        'archiveorg': ('exact_phrase_recall_runner_archiveorg', 'ArchiveOrgSearch'),
        'huggingface': ('exact_phrase_recall_runner_huggingface', 'HuggingFaceSearch'),
        'newsapi': ('exact_phrase_recall_runner_newsapi', 'NewsAPISearch'),
    }
    
    availability = {}
    for engine_name, (module_name, class_name) in engines.items():
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, class_name):
                availability[engine_name] = True
            else:
                availability[engine_name] = False
        except ImportError:
            availability[engine_name] = False
    
    return availability


def show_engine_status():
    """Display detailed engine status"""
    print("🔍 Search Engineer - Engine Status Report")
    print("=" * 60)
    
    # Define engine info
    engine_info = {
        'google': ('Google', 'No Auth', 'Fast', ['exact_phrase', 'filetype', 'date', 'proximity']),
        'bing': ('Bing', 'No Auth', 'Fast', ['exact_phrase', 'filetype', 'proximity']),
        'yandex': ('Yandex', 'No Auth/IP Restricted', 'Fast', ['exact_phrase', 'proximity']),
        'duckduckgo': ('DuckDuckGo', 'No Auth', 'Medium', ['exact_phrase']),
        'brave': ('Brave', 'API Key', 'Fast', ['exact_phrase', 'language']),
        'yep': ('Yep', 'No Auth', 'Medium', ['exact_phrase']),
        'boardreader': ('BoardReader', 'No Auth', 'Slow', ['forums']),
        'exa': ('Exa', 'API Key', 'Fast', ['semantic']),
        'gdelt': ('GDELT', 'No Auth', 'Medium', ['news', 'events']),
        'grok': ('Grok', 'API Key', 'Fast', ['AI-powered']),
        'publicwww': ('PublicWWW', 'API Key', 'Slow', ['code_search']),
        'socialsearcher': ('SocialSearcher', 'API Key', 'Medium', ['social_media']),
        'aleph': ('Aleph', 'No Auth', 'Medium', ['documents']),
        'archiveorg': ('Archive.org', 'No Auth', 'Slow', ['historical']),
        'huggingface': ('HuggingFace', 'API Key', 'Medium', ['datasets', 'models']),
        'newsapi': ('NewsAPI', 'API Key', 'Fast', ['news']),
    }
    
    # Check availability
    availability = check_engine_availability()
    available_count = sum(1 for v in availability.values() if v)
    unavailable_count = len(availability) - available_count
    
    print("\n📊 Engine Availability:\n")
    print(f"{'Engine':<15} {'Status':<12} {'Auth':<20} {'Speed':<10} {'Features'}")
    print("-" * 80)
    
    for engine_key, (name, auth, speed, features) in engine_info.items():
        available = availability.get(engine_key, False)
        if available:
            status = "✅ Available"
        else:
            status = "❌ Not Found"
        
        features_str = ", ".join(features)
        print(f"{name:<15} {status:<12} {auth:<20} {speed:<10} {features_str}")
    
    print("\n📈 Summary:")
    print(f"  • Available Engines: {available_count}")
    print(f"  • Unavailable Engines: {unavailable_count}")
    print(f"  • Total Engines: {len(availability)}")
    
    # Check for common issues
    print("\n⚠️  Common Issues:")
    if not availability.get('yandex', False):
        print("  • Yandex: May be blocked due to IP restrictions (this is normal)")
    if not availability.get('brave', False):
        print("  • Brave: Requires BRAVE_API_KEY environment variable")
    if not availability.get('exa', False):
        print("  • Exa: Requires EXA_API_KEY environment variable")
    if not availability.get('newsapi', False):
        print("  • NewsAPI: Requires NEWS_API_KEY environment variable")
    
    # Show search type support
    print("\n🔧 Search Type Support:")
    print("  • Exact Phrase: All engines")
    print("  • Proximity (~N, N<, <N): Google, Bing, Yandex")
    print("  • Date (2024!): Google, Bing")
    print("  • Filetype (pdf!): Google, Bing")
    print("  • Language (lang:de): Google, Bing, Brave")
    print("  • Definitional [term]: Uses AI for query expansion")
    print("  • Corporate (c:): OpenCorporates, Companies House, EDGAR, OCCRP")
    
    print("\n💡 Tips:")
    print("  • Use --list-engines to see engine codes")
    print("  • Use -e GO BI to select specific engines")
    print("  • Parallel execution is already enabled")


if __name__ == "__main__":
    show_engine_status()