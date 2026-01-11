## 2026-01-05 - GPT-5 - Entity Harvester Fix
**Duration:** 1 hour
**Tasks:** Unblock CZ company extraction in the EU news harvester.
**Completed:**
- Added designator-based company candidate extraction from snippets.
- Filtered GLiNER company outputs by designator presence to reduce noise.
**Blockers:** None.
**Next:** Run a small CZ harvest and confirm companies like "Farma Skupec, s.r.o." appear.

## 2026-01-05 - GPT-5 - Entity URL Capture
**Duration:** 15 minutes
**Tasks:** Ensure entities include URLs where they were mentioned.
**Completed:**
- Added `source_urls` list per entity alongside `sources`.
**Blockers:** None.
**Next:** Verify `news_entities.json` includes `source_urls` after a test harvest.

## 2026-01-05 - GPT-5 - Single News Source File
**Duration:** 20 minutes
**Tasks:** Remove news source file duplication for TORPEDO.
**Completed:**
- NewsSearcher and NewsProcessor now read only `input_output/matrix/sources/news.json`.
- Dropped fallbacks to `sources_news.json` and `sources.json`.
**Blockers:** None.
**Next:** Confirm `sources/news.json` exists and is jurisdiction-keyed before running harvests.
