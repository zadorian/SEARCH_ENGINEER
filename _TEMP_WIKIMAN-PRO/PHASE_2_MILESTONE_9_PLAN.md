# Phase 2 – Milestone 9: UK Companies House API Enhancements

**Goal:** Expand the UK handler’s API layer beyond basic company lookup so deterministic routing returns richer results (PSC, officers, filings, advanced search filters) with robust caching, telemetry, and error handling.

---

## 1. Scope

### In-Scope Endpoints
- Company Profile (`/company/{company_number}`)
- Officers (`/company/{company_number}/officers`)
- Filing History (`/company/{company_number}/filing-history`)
- Persons with Significant Control (PSC) (`/company/{company_number}/persons-with-significant-control`)
- Search refinements (`/search/companies` with filters like `q`, `items_per_page`, `start_index`)

### Out-of-Scope
- Streaming/doc download endpoints
- Document API (PDF retrieval)
- Insolvency history (phase 2+)

---

## 2. Architecture Tasks

1. **HTTP Client Layer**
   - Add `countries/http_utils.py` methods for authenticated GET with exponential backoff and rate-limit awareness.
   - Support query parameters for pagination; capture `X-RateLimit-Remain` headers when present.

2. **Handler Updates (`countries/uk/handler.py`)**
   - `_fetch_company_profile`, `_fetch_officers`, `_fetch_filing_history`, `_fetch_psc` helper functions using the shared HTTP client.
   - Enhanced `_search_api` to stitch together the aggregated response (profile + officers + PSC + filings excerpt).
   - Layer caching keyed by company number + digest of included subresources.

3. **Normalization (`countries/result_normalizer.py`)**
   - Extend optional fields to include PSC, filing summaries, officer appointment dates.
   - Ensure trail-layer merging preserves API fields (priority = API).

4. **Deterministic Output (`mcp_server.py`)**
   - Update handler summary branch with new UK sections (PSC summary, recent filings, officer count, company status).

5. **Configuration**
   - Update `countries/countries_config.json`: add rate-limit metadata (`items_per_page`, default backoff) if known.
   - Document env vars (`COMPANIES_HOUSE_API_KEY`) in README.

---

## 3. Testing

### Unit Tests
- Mocked HTTP responses for each endpoint (success + error + empty).
- Caching behaviour (second call hits cache, not network).
- Error propagation (HTTPError → fallback to wiki/trail).

### Integration Tests
- Extend deterministic routing tests: `execute_direct_search` returns enriched UK summary.
- Handler tests verifying aggregated fields (PSC list truncated to top N with indicator).

---

## 4. Observability

- Structured logs in handler for each endpoint call (status, duration, returned counts).
- Emit metrics:
  - `uk_api_call` (endpoint tag)
  - `uk_api_error` with status code
  - `uk_api_latency_ms`
  - `uk_api_cache_hit`
- Update `docs/observability.md` with new metrics and example queries.

---

## 5. Rollout Plan

1. Implement enhancements behind feature flag (e.g., `UK_API_ENHANCED=true`).
2. Manual validation:
   - Company with PSC (e.g., “Tesco Stores Limited”)
   - Company with officer turnover
   - Company with recent filings
3. Remove flag after validation; regenerate config/tests.

---

## 6. Deliverables

- Updated `countries/uk/handler.py` + helper utilities.
- New/extended tests in `tests/test_uk_handler.py` and deterministic routing tests.
- Regenerated config if needed.
- Documentation updates: `countries/uk/README.md`, `COUNTRY_HANDLERS_GUIDE.md`.

