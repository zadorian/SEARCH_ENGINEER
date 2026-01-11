# EYE-D - TODO

> **Auto-updated by AI agents.** See `AGENT.md` for protocols.

---

## High Priority

- [ ] Fix Google API credential configuration
  - Priority: High
  - Added: 2025-12-04 by Claude
  - Notes: Currently using mock results when API not configured

- [ ] Complete legend-aligned module wrapper
  - Priority: High
  - Added: 2025-12-04 by Claude
  - Notes: `legend/module.py` needs production hardening

- [ ] Ensure all API keys are backend-only
  - Priority: High
  - Added: 2025-12-04 by Claude
  - Notes: Security audit for frontend code

## Medium Priority

- [ ] Add retry logic for failed OSINT requests
  - Priority: Medium
  - Added: 2025-12-04 by Claude
  - Notes: Currently no request queuing or retry

- [ ] Implement health checks for external APIs
  - Priority: Medium
  - Added: 2025-12-04 by Claude
  - Notes: Frontend should verify service availability

- [ ] Add rate limit handling for all resources
  - Priority: Medium
  - Added: 2025-12-04 by Claude
  - Notes: Exponential backoff patterns needed

- [ ] Complete SQL graph persistence testing
  - Priority: Medium
  - Added: 2025-12-04 by Claude
  - Notes: `graph-sql-integration.js` needs verification

## Low Priority

- [ ] Add batch entity extraction from multiple URLs
  - Priority: Low
  - Added: 2025-12-04 by Claude
  - Notes: Claude API batch processing

- [ ] Implement graph export to various formats
  - Priority: Low
  - Added: 2025-12-04 by Claude
  - Notes: JSON, CSV, GraphML exports

- [ ] Add keyboard shortcuts for common actions
  - Priority: Low
  - Added: 2025-12-04 by Claude
  - Notes: ESC, Enter, arrow navigation

---

## Completed

- [x] Mirror Linklater WHOIS discovery into EYE-D
  - Completed: 2025-12-31 by GPT-5
  - Notes: Copied `BACKEND/modules/LINKLATER/discovery/whois_discovery.py` into `BACKEND/modules/EYE-D/whois_discovery.py` and aligned `BACKEND/modules/EYE-D/whois.py` to use the same history/reverse helpers.

- [x] Return structured WHOIS history in EYE-D API
  - Completed: 2025-12-31 by GPT-5
  - Notes: `/api/whois` now includes `structured_history` (Linklater-format records + distinct registrants) alongside raw records.

- [x] Unify WHOIS lookups under shared whoisxmlapi helper
  - Completed: 2025-12-31 by GPT-5
  - Notes: Centralized WhoisXML API calls + deterministic extraction in `BACKEND/modules/eyed/whoisxmlapi.py`, with EYE-D and Linklater using the shared helper.

- [x] URL node screenshot capture via Firecrawl
  - Completed: 2025-07-04 by Claude
  - Notes: Auto-trigger on URL paste working

- [x] Entity extraction from URLs via Claude
  - Completed: 2025-07-04 by Claude
  - Notes: Semi-circle pattern display

- [x] MD file upload for entity extraction
  - Completed: 2025-07-04 by Claude
  - Notes: Document node creation working

- [x] Backlinks display as list node
  - Completed: 2025-07-02 by Claude
  - Notes: Rich display with metadata

- [x] Connection types standardization (5 types)
  - Completed: 2025-07-02 by Claude
  - Notes: Gray/White/Blue/Green/Red system

- [x] Google search progress indication
  - Completed: 2025-07-02 by Claude
  - Notes: Live (0/7)...(7/7) updates

- [x] Duplicate node prevention (case-insensitive)
  - Completed: 2025-07-02 by Claude
  - Notes: valueToNodeMap normalization

- [x] Search provider selection modal
  - Completed: 2025-07-02 by Claude
  - Notes: Two-tab interface (APIs/Categories)
