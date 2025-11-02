# Phase 2 Validation Checklist

**Status**: Ready for validation  
**Date**: October 15, 2025  
**Phase 2 Completion**: Milestone 7 - Quality Gate

---

## Overview

This document provides comprehensive validation criteria for Phase 2 of the WIKIMAN-PRO country handler architecture. All checks must pass before declaring Phase 2 stable and ready for production rollout.

---

## 1. Environment Configuration

### 1.1 Required Environment Variables

Verify all required credentials are configured:

```bash
# Required for UK handler
echo $COMPANIES_HOUSE_API_KEY

# Required for TrailBlazer flows (if used)
echo $TRAILBLAZER_ENABLED

# Required for Gemini fallback (if enabled)
echo $GEMINI_API_KEY

# Optional: Country-specific feature flags
echo $COUNTRY_HANDLERS_ENABLED
echo $COUNTRY_HANDLER_UK
echo $COUNTRY_HANDLER_SG
```

**Expected Results**:
- [ ] All required environment variables are set
- [ ] API keys are valid (not expired or revoked)
- [ ] Feature flags default to appropriate values

**Validation Script**: `scripts/validate_phase2.py --check=environment`

---

## 2. Country Registry

### 2.1 Registry Initialization

```python
from countries.registry import get_handler, list_countries, list_enabled

# Verify registry loads
countries = list_countries()
enabled = list_enabled()
```

**Expected Results**:
- [ ] `list_countries()` returns ≥10 countries
- [ ] `list_enabled()` returns ≥5 countries (UK, SG, HK, AU, JP)
- [ ] No import errors or exceptions
- [ ] Registry cache works correctly

**Validation Script**: `scripts/validate_phase2.py --check=registry`

### 2.2 Handler Loading

```python
# Test handler retrieval for all enabled countries
for country_code in ['uk', 'sg', 'hk', 'au', 'jp']:
    handler = get_handler(country_code)
    assert handler is not None
    assert handler.country_code == country_code
```

**Expected Results**:
- [ ] All enabled handlers load successfully
- [ ] Handlers have correct country_code attribute
- [ ] Lazy loading works (no import until needed)
- [ ] Handler caching prevents duplicate instances

**Validation Script**: `scripts/validate_phase2.py --check=handlers`

---

## 3. Country Handler Functionality

### 3.1 UK Handler (Reference Implementation)

```python
from countries.uk.handler import UKHandler

handler = UKHandler()

# Test basic search
result = handler.search_company("BP plc")
assert result["ok"] == True
assert result["source"] == "companies_house_uk"
assert "company" in result["data"]

# Test with enhanced options
result = handler.search_company(
    "BP plc",
    include_officers=True,
    include_psc=True,
    include_filings=True
)
assert "officers" in result["data"]
assert "psc" in result["data"]
assert "filings" in result["data"]
```

**Expected Results**:
- [ ] Basic search returns valid company data
- [ ] Enhanced options return officers/PSC/filings
- [ ] API layer executes successfully
- [ ] Rate limiting is enforced
- [ ] Caching reduces duplicate API calls
- [ ] Fallback to WIKIMAN works on API failure

**Validation Script**: `scripts/validate_phase2.py --check=uk-handler`

### 3.2 APAC Handlers

Test each APAC handler:

```python
test_cases = {
    'sg': 'Temasek Holdings',
    'hk': 'Cathay Pacific',
    'au': 'Commonwealth Bank',
    'jp': 'Toyota Motor Corporation'
}

for country_code, company_name in test_cases.items():
    handler = get_handler(country_code)
    result = handler.search_company(company_name)
    assert result["ok"] == True
    assert result["source"].startswith(country_code)
```

**Expected Results**:
- [ ] All APAC handlers execute successfully
- [ ] Results contain company data or context
- [ ] API layer attempts before fallback (where available)
- [ ] WIKIMAN layer provides fallback context
- [ ] Cache keys are country-specific

**Validation Script**: `scripts/validate_phase2.py --check=apac-handlers`

### 3.3 European Handlers (Stub Validation)

```python
european_countries = ['de', 'hu', 'fr', 'es', 'it', 'nl']

for country_code in european_countries:
    handler = get_handler(country_code)
    result = handler.search_company("Test Company")
    # Should return WIKIMAN context even if API is stubbed
    assert result["ok"] == True or result["metadata"]["layers_attempted"]
```

**Expected Results**:
- [ ] European handlers return WIKIMAN context
- [ ] API stubs return appropriate "not_implemented" status
- [ ] Fallback chain works correctly

**Validation Script**: `scripts/validate_phase2.py --check=european-handlers`

---

## 4. Routing Integration

### 4.1 Deterministic Routing

```python
from mcp_server import execute_direct_search

# Test country-specific routing
result = execute_direct_search("cuk:BP plc")
assert "country" in result
assert result["country"] == "uk"

result = execute_direct_search("csg:Temasek")
assert result["country"] == "sg"
```

**Expected Results**:
- [ ] Country prefix routing works (`cuk:`, `csg:`, etc.)
- [ ] Handler delegation occurs correctly
- [ ] Metadata includes layer information
- [ ] Global fallback still available

**Validation Script**: `scripts/validate_phase2.py --check=routing`

### 4.2 MCP Tool Integration

```python
# Test MCP tool interface
result = tool_country_search(
    country="uk",
    entity_type="company",
    query="BP plc"
)
assert result["status"] == "success"
assert "company" in result["data"]
```

**Expected Results**:
- [ ] MCP tools call country handlers
- [ ] Tool results include metadata
- [ ] Error handling works correctly

**Validation Script**: `scripts/validate_phase2.py --check=mcp-tools`

---

## 5. Caching Strategy

### 5.1 Cache Configuration

```python
from countries.cache import CountryCache

cache = CountryCache(country="uk")

# Test cache operations
cache.set("api", "test_key", {"data": "value"}, ttl=300)
cached = cache.get("api", "test_key")
assert cached == {"data": "value"}

# Test cache clearing
cache.clear("api")
assert cache.get("api", "test_key") is None
```

**Expected Results**:
- [ ] Cache stores data correctly per layer
- [ ] TTL expiration works
- [ ] Cache keys are unique per country/layer
- [ ] Cache clearing works per layer
- [ ] Cache stats are accurate

**Validation Script**: `scripts/validate_phase2.py --check=caching`

### 5.2 Cache Performance

```python
import time

handler = get_handler("uk")

# First call (uncached)
start = time.time()
result1 = handler.search_company("BP plc")
uncached_time = time.time() - start

# Second call (cached)
start = time.time()
result2 = handler.search_company("BP plc")
cached_time = time.time() - start

assert cached_time < uncached_time * 0.2  # Cached should be 5x faster
```

**Expected Results**:
- [ ] Cached calls are significantly faster (>5x)
- [ ] Cache hit rate > 50% in typical usage
- [ ] Cache invalidation works correctly

**Validation Script**: `scripts/validate_phase2.py --check=cache-performance`

---

## 6. Rate Limiting

### 6.1 Rate Limit Configuration

```python
from countries.rate_limit import RateLimiter

# Test rate limiter
limiter = RateLimiter(max_calls=10, window_seconds=60)

for i in range(10):
    assert limiter.acquire() == True

# 11th call should be rate limited
assert limiter.acquire() == False
```

**Expected Results**:
- [ ] Rate limiters enforce call limits
- [ ] Window-based rate limiting works
- [ ] Stats tracking is accurate
- [ ] Rate limit decorator works correctly

**Validation Script**: `scripts/validate_phase2.py --check=rate-limiting`

### 6.2 Per-Country Rate Limits

```python
# Verify each handler has appropriate rate limits
rate_limit_config = {
    'uk': 60,      # Companies House: 600/5min = 120/min, use conservative 60
    'sg': 30,      # ACRA: assumed conservative
    'hk': 30,      # ICRIS: assumed conservative
    'au': 30,      # ASIC: assumed conservative
    'jp': 30       # Corporate Number: assumed conservative
}

for country_code, expected_limit in rate_limit_config.items():
    handler = get_handler(country_code)
    assert handler.rate_limiter.max_calls <= expected_limit
```

**Expected Results**:
- [ ] All handlers have rate limiters configured
- [ ] Rate limits match API provider specifications
- [ ] Rate limit violations trigger backoff

**Validation Script**: `scripts/validate_phase2.py --check=rate-limit-config`

---

## 7. Observability

### 7.1 Metrics Emission

```python
from countries.observability import get_metrics, clear_metrics

# Clear previous metrics
clear_metrics()

# Execute handler call
handler = get_handler("uk")
result = handler.search_company("BP plc")

# Check metrics were emitted
metrics = get_metrics()
assert len(metrics) > 0

# Verify metric types
api_metrics = [m for m in metrics if m["name"] == "api_call"]
layer_metrics = [m for m in metrics if m["name"] == "layer_attempt"]

assert len(api_metrics) > 0
assert len(layer_metrics) > 0
```

**Expected Results**:
- [ ] Metrics emitted for every handler call
- [ ] API metrics include country/endpoint/status
- [ ] Layer metrics include success/failure
- [ ] Cache metrics track hit/miss
- [ ] Latency metrics calculated correctly

**Validation Script**: `scripts/validate_phase2.py --check=metrics`

### 7.2 Prometheus Endpoint

```bash
# Start test metrics server
python3 test_metrics_server.py &

# Generate test metrics
curl http://localhost:5055/test

# Verify Prometheus format
curl http://localhost:5055/metrics | head -50
```

**Expected Results**:
- [ ] Metrics endpoint returns Prometheus format
- [ ] All metric families present (requests, latency, cache, layer)
- [ ] Quantile calculations correct (p50, p95, p99)
- [ ] All 5 countries appear in metrics

**Validation Script**: `scripts/validate_phase2.py --check=prometheus`

### 7.3 Structured Logging

```python
from countries.observability import get_logger

logger = get_logger("uk.api", country="uk", layer="api")

# Verify log output includes context
logger.info("Test message", extra={"company": "BP plc"})

# Check logs contain structured context
# (Manual verification of log output)
```

**Expected Results**:
- [ ] Logs include country/layer context
- [ ] Extra fields appear in log output
- [ ] Log levels work correctly
- [ ] Error logs include stack traces when requested

**Validation Script**: `scripts/validate_phase2.py --check=logging`

---

## 8. Error Handling

### 8.1 API Failures

```python
# Simulate API failure
handler = get_handler("uk")

# Mock API to fail
def mock_api_failure(*args, **kwargs):
    raise HTTPError("503 Service Unavailable")

import countries.uk.handler as uk_module
uk_module.UKHandler._search_companies = mock_api_failure

# Handler should fallback gracefully
result = handler.search_company("BP plc")

# Should get WIKIMAN fallback
assert result["metadata"]["layers_attempted"] == ["api", "wikiman"]
assert result["metadata"]["layer_errors"]["api"]
```

**Expected Results**:
- [ ] API failures trigger fallback to WIKIMAN
- [ ] Error metadata captured in response
- [ ] Partial successes handled correctly
- [ ] No unhandled exceptions

**Validation Script**: `scripts/validate_phase2.py --check=error-handling`

### 8.2 Rate Limit Errors

```python
# Simulate rate limit error
handler = get_handler("uk")

# Exhaust rate limit
for i in range(handler.rate_limiter.max_calls + 1):
    result = handler.search_company(f"Company {i}")

# Last call should indicate rate limiting
assert result["metadata"]["rate_limited"] == True
```

**Expected Results**:
- [ ] Rate limit errors handled gracefully
- [ ] Metadata indicates rate_limited status
- [ ] Backoff occurs automatically

**Validation Script**: `scripts/validate_phase2.py --check=rate-limit-errors`

---

## 9. Gemini Budget Guard

### 9.1 Budget Configuration

```python
from countries.gemini_budget import check_budget, reset_budget

# Verify budget tracking
assert check_budget() == True

# Simulate token usage
for i in range(100):
    use_tokens(100)  # Use 10k tokens total

# Check budget status
budget_status = get_budget_status()
assert budget_status["tokens_used"] >= 10000
```

**Expected Results**:
- [ ] Budget tracking is accurate
- [ ] Budget limits enforced
- [ ] Alerts trigger at 80% usage
- [ ] Budget resets daily/hourly as configured

**Validation Script**: `scripts/validate_phase2.py --check=gemini-budget`

### 9.2 Budget Exhaustion

```python
# Simulate budget exhaustion
exhaust_budget()

# Gemini layer should be disabled
handler = get_handler("uk")
result = handler.search_company("Obscure Company")

# Should skip Gemini layer
assert "gemini" not in result["metadata"]["layers_attempted"]
```

**Expected Results**:
- [ ] Gemini layer skipped when budget exhausted
- [ ] Other layers still function
- [ ] Budget exhaustion logged

**Validation Script**: `scripts/validate_phase2.py --check=budget-exhaustion`

---

## 10. Performance Benchmarks

### 10.1 Latency Targets

```python
import time
from statistics import mean

handler = get_handler("uk")
latencies = []

for i in range(100):
    start = time.time()
    result = handler.search_company("BP plc")
    latencies.append((time.time() - start) * 1000)

# Calculate percentiles
latencies.sort()
p50 = latencies[50]
p95 = latencies[95]
p99 = latencies[99]

print(f"P50: {p50:.2f}ms")
print(f"P95: {p95:.2f}ms")
print(f"P99: {p99:.2f}ms")
```

**Expected Results**:
- [ ] P50 latency < 500ms
- [ ] P95 latency < 2000ms
- [ ] P99 latency < 5000ms
- [ ] Cached calls < 100ms

**Validation Script**: `scripts/validate_phase2.py --check=performance`

### 10.2 Token Reduction

```python
# Compare token usage: Phase 1 vs Phase 2
phase1_tokens = measure_phase1_query("Tell me about BP plc in UK")
phase2_tokens = measure_phase2_query("cuk:BP plc")

reduction_pct = ((phase1_tokens - phase2_tokens) / phase1_tokens) * 100

print(f"Token reduction: {reduction_pct:.1f}%")
```

**Expected Results**:
- [ ] Token reduction ≥ 50% for country queries
- [ ] Simple lookups use < 1k tokens
- [ ] Enhanced lookups use < 2k tokens

**Validation Script**: `scripts/validate_phase2.py --check=token-reduction`

---

## 11. Test Suite

### 11.1 Test Coverage

```bash
# Run full test suite
python3 -m pytest tests/ --ignore=tests/test_mcp_trailblazer_handlers.py -v --cov=countries --cov-report=html
```

**Expected Results**:
- [ ] All 176+ tests passing
- [ ] Handler tests: 65+ passing
- [ ] Observability tests passing
- [ ] Coverage > 80% for countries module
- [ ] No skipped tests (except pre-existing webapp issues)

**Validation Script**: `scripts/validate_phase2.py --check=tests`

### 11.2 Handler-Specific Tests

```bash
# UK handler tests
python3 -m pytest tests/test_uk_handler.py -v
# Expected: 27/27 passing

# APAC handler tests
python3 -m pytest tests/test_apac_handlers.py -v
# Expected: 32/32 passing

# European handler tests
python3 -m pytest tests/test_european_handlers.py -v
# Expected: 6/6 passing
```

**Expected Results**:
- [ ] All handler-specific tests pass
- [ ] No flaky tests
- [ ] Tests run in < 10 seconds

**Validation Script**: `scripts/validate_phase2.py --check=handler-tests`

---

## 12. Documentation

### 12.1 Required Documentation Present

```bash
# Check all required docs exist
docs=(
    "PHASE_2_PLAN.md"
    "PHASE_2_VALIDATION.md"
    "PHASE_2_MONITORING.md"
    "PHASE_2_RELEASE_NOTES.md"
    "countries/README.md"
    "countries/uk/README.md"
    "PROMETHEUS_SETUP.md"
    "OBSERVABILITY_INTEGRATION_COMPLETE.md"
)

for doc in "${docs[@]}"; do
    [ -f "$doc" ] && echo "✅ $doc" || echo "❌ $doc MISSING"
done
```

**Expected Results**:
- [ ] All required documentation files exist
- [ ] Documentation is up-to-date
- [ ] Examples are accurate and runnable
- [ ] API references are complete

**Validation Script**: `scripts/validate_phase2.py --check=documentation`

---

## 13. Rollback Plan

### 13.1 Feature Flag Disable

```bash
# Verify feature flags can disable handlers
export COUNTRY_HANDLERS_ENABLED=false

# Verify handlers are disabled
python3 -c "from countries.registry import list_enabled; assert len(list_enabled()) == 0"
```

**Expected Results**:
- [ ] Feature flag disables all handlers
- [ ] System falls back to global search
- [ ] No errors or exceptions

**Validation Script**: `scripts/validate_phase2.py --check=feature-flags`

### 13.2 Per-Country Disable

```bash
# Disable specific country
export COUNTRY_HANDLER_UK=false

# Verify UK handler disabled
python3 -c "from countries.registry import list_enabled; assert 'uk' not in list_enabled()"
```

**Expected Results**:
- [ ] Per-country flags work correctly
- [ ] Other handlers remain enabled
- [ ] Graceful fallback for disabled countries

**Validation Script**: `scripts/validate_phase2.py --check=country-flags`

---

## 14. Security

### 14.1 Credential Masking

```python
from countries.credentials import CredentialManager

creds = CredentialManager()

# Verify credentials are masked in logs
api_key = creds.get_credential("COMPANIES_HOUSE_API_KEY")
assert len(api_key) > 0

# Check logs don't expose credentials
# (Manual verification)
```

**Expected Results**:
- [ ] API keys masked in logs (show only last 4 chars)
- [ ] No credentials in error messages
- [ ] Credential health checks work

**Validation Script**: `scripts/validate_phase2.py --check=security`

---

## 15. Production Readiness

### 15.1 Environment Checklist

- [ ] All required environment variables set
- [ ] API credentials valid and not expired
- [ ] Rate limits configured correctly
- [ ] Feature flags set appropriately
- [ ] Logging level configured (INFO or WARNING for prod)
- [ ] Metrics endpoint accessible
- [ ] Prometheus scraping configured

### 15.2 Deployment Checklist

- [ ] All tests passing (176+)
- [ ] Documentation complete and reviewed
- [ ] Rollback plan tested
- [ ] Monitoring dashboards created
- [ ] Alert rules configured
- [ ] Team trained on new features
- [ ] Staged rollout plan approved

### 15.3 Post-Deployment Checklist

- [ ] Verify metrics collection working
- [ ] Check handler success rates
- [ ] Monitor latency percentiles
- [ ] Track cache hit rates
- [ ] Verify no credential leaks in logs
- [ ] Confirm rate limiting working
- [ ] Collect baseline metrics for comparison

---

## Validation Summary

### Automated Validation

Run the comprehensive validation script:

```bash
cd /path/to/wikiman-pro
python3 scripts/validate_phase2.py --all

# Or run specific checks
python3 scripts/validate_phase2.py --check=handlers,routing,performance
```

### Manual Validation

Some checks require manual verification:

1. **Log Output Review**: Check logs for credential exposure
2. **Dashboard Verification**: Verify Grafana dashboards display correctly
3. **Alert Testing**: Trigger test alerts to verify notifications
4. **Documentation Review**: Read all docs for accuracy and completeness

### Success Criteria

**Phase 2 is considered validated when**:
- ✅ All automated validation checks pass
- ✅ All manual verification complete
- ✅ 176+ tests passing
- ✅ Performance targets met (P95 < 2s)
- ✅ Token reduction ≥ 50%
- ✅ Documentation complete
- ✅ Rollback plan tested
- ✅ Monitoring operational

---

## Validation Sign-Off

**Validator**: _________________  
**Date**: _________________  
**Status**: ☐ PASSED  ☐ FAILED  
**Notes**: 

---

**Next Step**: Once validation passes, proceed to PHASE_2_RELEASE_NOTES.md for rollout plan.
