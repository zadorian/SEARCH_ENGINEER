## [2025-12-29] - GPT-5 - Work Session
**Duration:** 2 hours
**Tasks:** Consolidate search_types into targeted_searches, unify news search, align taxonomy with grid filters.
**Completed:**
- Moved unified NewsSearcher (global + national/Torpedo modes) into `BACKEND/modules/BRUTE/targeted_searches/news/news.py` with CLI support.
- Replaced definitional searcher under `targeted_searches/special` with the orchestrator-backed parser and added `subject_link_ops`.
- Updated core API, CLI, engine registry, streaming search imports, and corp profile OpenCorporates import to target `targeted_searches`.
- Added `targeted_searches/taxonomy.py` mapping search types to Location/Subject/Nexus.
- Removed `BACKEND/search_types` folder.
- Fixed indentation errors in `BACKEND/modules/BRUTE/infrastructure/streaming_search.py` so it compiles when wired into core routes.
**Blockers:** None.
**Next:** Validate news CLI/API, confirm definitional parsing in unified_search, and decide whether to wire taxonomy into router/operator mapping.
