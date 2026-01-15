#!/usr/bin/env python3
"""
Engine wrapper to provide consistent initialization interface for all search engines.
This allows engines to be initialized without parameters and have the phrase set later.
"""

import importlib
import asyncio
from typing import Optional, List, Dict, Any


class EngineWrapper:
    """Wrapper to provide consistent interface for all search engines."""
    
    def __init__(self, module_name: str, class_name: str, engine_code: str):
        self.module_name = module_name
        self.class_name = class_name
        self.engine_code = engine_code
        self.phrase = None
        self.runner = None
        self._module = None
        self._runner_class = None
        self._initialized = False
    
    def set_phrase(self, phrase: str):
        """Set the search phrase."""
        self.phrase = phrase
    
    def _initialize_runner(self):
        """Initialize the actual runner with the phrase."""
        if not self.phrase:
            raise ValueError("Phrase must be set before running")
        
        # Import module if not already imported
        if not self._module:
            self._module = importlib.import_module(self.module_name)
            self._runner_class = getattr(self._module, self.class_name)
        
        # Initialize based on engine type
        if self.engine_code == 'DD':
            # DuckDuckGo doesn't need phrase in init
            self.runner = self._runner_class()
        elif self.engine_code == 'W':
            # WikiLeaks doesn't need phrase in init
            self.runner = self._runner_class()
        elif self.engine_code == 'PW':
            # PublicWWW doesn't need phrase in init
            self.runner = self._runner_class()
        elif self.engine_code in ['GO', 'YA', 'BI', 'BR', 'YE']:
            # These need phrase and engine instance
            # Create a mock engine instance for now
            if self.engine_code == 'GO':
                from brute.engines.google import GoogleSearch
                engine = GoogleSearch()
                self.runner = self._runner_class(phrase=self.phrase, google=engine)
            elif self.engine_code == 'YA':
                from brute.engines.yandex import YandexSearch
                engine = YandexSearch()
                self.runner = self._runner_class(phrase=self.phrase, yandex=engine)
            elif self.engine_code == 'BI':
                from brute.engines.bing import BingSearch
                engine = BingSearch()
                self.runner = self._runner_class(phrase=self.phrase, bing=engine)
            elif self.engine_code == 'BR':
                from brute.engines.brave import BraveSearch
                engine = BraveSearch()
                self.runner = self._runner_class(phrase=self.phrase, brave=engine)
            elif self.engine_code == 'YE':
                from brute.engines.yep import YepSearchScraper
                scraper = YepSearchScraper()
                self.runner = self._runner_class(phrase=self.phrase, scraper=scraper)
        elif self.engine_code == 'AR':
            # Archive.org needs archiveorg_client
            from brute.engines.archiveorg import ArchiveOrgSearch
            client = ArchiveOrgSearch()
            self.runner = self._runner_class(phrase=self.phrase, archiveorg_client=client)
        elif self.engine_code == 'NA':
            # NewsAPI just needs phrase
            self.runner = self._runner_class(phrase=self.phrase)
        else:
            # Default: just pass phrase (SS, EX, GD, GR, AL, BO, HF)
            self.runner = self._runner_class(phrase=self.phrase)
    
    def run(self) -> List[Dict[str, Any]]:
        """Run the search."""
        if not self.runner:
            self._initialize_runner()
        
        # Handle different run methods
        if self.engine_code == 'DD':
            # DuckDuckGo uses search() method
            clean_phrase = self.phrase.strip('"')
            return self.runner.search(clean_phrase, max_results=100)
        elif self.engine_code == 'BO':
            # BoardReader has async interface
            return self.runner.run_sync()
        elif self.engine_code == 'W':
            # WikiLeaks uses search() method
            return self.runner.search(self.phrase)
        elif self.engine_code == 'PW':
            # PublicWWW uses search() method
            return self.runner.search(self.phrase)
        else:
            # Most engines use run() method
            return self.runner.run()
    
    def search(self, *args, **kwargs):
        """Alias for run() to support engines that expect search()."""
        return self.run()