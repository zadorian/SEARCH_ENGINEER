# Torpedo Country Scrapers

This directory contains country-specific scraping modules moved from `JURISDICTIONAL/` because they rely on web scraping rather than formal APIs.

## Modules

- **AT (Austria):** `at_cli.py`, `at_cr.py` (FirmenABC)
- **BE (Belgium):** `be_cli.py` (KBO Public Search)
- **DK (Denmark):** `dk_cli.py`, `virk_api.py` (Virk Scraper)
- **SE (Sweden):** `se_cli.py`, `verksamt_api.py` (Verksamt Scraper)
- **SK (Slovakia):** `sk_cli.py`, `orsr_api.py` (ORSR Scraper)
- **US (USA):** `us_cli.py`, `us_cr.py`, `us_sources.py` (OpenCorporates + State Links)

## Integration Plan

These modules should be refactored to inherit from a common `TorpedoCountryScraper` base class and integrated into the main `TORPEDO` dispatch logic.

### Required Refactoring

1.  **Imports:** Update relative imports to absolute imports or local sibling imports.
2.  **Base Class:** Inherit from `TorpedoScraper`.
3.  **Output:** Ensure output format matches Torpedo's standard `SearchResult` schema.
4.  **Error Handling:** Use Torpedo's error reporting mechanisms.

## Status

These files were moved on 2026-01-11. They are functional but require integration.
