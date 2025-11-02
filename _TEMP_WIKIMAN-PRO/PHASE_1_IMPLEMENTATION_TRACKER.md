# Phase 1 Implementation Tracker

**Status:** In Progress
**Goal:** Deterministic routing with fallbacks, clean formatting, no duplicates
**Approach:** Atomic commits with explicit file changes

---

## Current State Audit

### File: mcp_server.py

**Current Issues:**
- Line 2515-2643: `execute_direct_search()` exists but NO fallback logic
- Line 2703-2706: Returns raw JSON dump in TextContent
- Line 2824+: Legacy handlers (`handle_company_intelligence`, `handle_opensanctions_search`, etc.) still exist and are REACHABLE
- No execution time tracking
- No standardized result format

**Current Code Inspection:**

```python
# mcp_server.py:2547-2560 (Current - NO FALLBACK)
if country_code == "uk" and router in ("intelligence", "opencorporates"):
    from companies_house_unified import search_uk_company
    ch_result = search_uk_company(search_query, include_psc=True, include_officers=True)
    result["ok"] = ch_result.get("ok", False)
    result["data"] = ch_result
    result["router"] = "companies_house_uk"
    return result  # ❌ Returns immediately, no fallback

# mcp_server.py:2703-2706 (Current - RAW JSON)
json_output = json.dumps(direct_result, indent=2, default=str)
return [types.TextContent(
    type="text",
    text=f"# Search Results (Deterministic)\n\n```json\n{json_output}\n```"
)]

# mcp_server.py:2824+ (Current - STILL EXISTS)
elif router == "intelligence":
    return await handle_company_intelligence(search_query)  # ❌ Duplicate path
```

---

## Commit Structure

### Commit 1: Add Cascading Fallback Logic
**Files:** `mcp_server.py`
**Lines:** 2547-2643 (execute_direct_search function)
**Changes:**
- Add `attempted_sources` tracking
- Add `execution_time_ms` tracking
- UK routing: Try Companies House → fall back to parallel search
- All routers: Record what was attempted
- Consistent error handling

**Diff Preview:**
```python
# BEFORE (mcp_server.py:2547-2560)
if country_code == "uk" and router in ("intelligence", "opencorporates"):
    from companies_house_unified import search_uk_company
    ch_result = search_uk_company(search_query, include_psc=True, include_officers=True)
    result["ok"] = ch_result.get("ok", False)
    result["data"] = ch_result
    result["router"] = "companies_house_uk"
    return result

# AFTER
if country_code == "uk" and router in ("intelligence", "opencorporates"):
    result["attempted_sources"].append("companies_house")
    try:
        from companies_house_unified import search_uk_company
        ch_result = search_uk_company(search_query, include_psc=True, include_officers=True)

        if ch_result.get("ok"):
            result["ok"] = True
            result["data"] = ch_result
            result["router"] = "companies_house_uk"
            result["execution_time_ms"] = int((time.time() - start) * 1000)
            return result
        else:
            logger.warning("Companies House failed, falling back to parallel")
            result["attempted_sources"].append("fallback_to_parallel")
    except Exception as e:
        logger.error(f"Companies House error: {e}, falling back")
        result["attempted_sources"].append("companies_house_error")

    # FALLBACK: Parallel search
    if tool_parallel_search:
        parallel_result = tool_parallel_search(search_query)
        result["ok"] = parallel_result.get("ok", False)
        result["data"] = parallel_result
        result["router"] = "parallel_fallback"
        result["execution_time_ms"] = int((time.time() - start) * 1000)
        return result
```

**Testing:**
- Test Companies House success → returns CH data
- Test Companies House failure → falls back to parallel
- Test Companies House exception → falls back to parallel
- Verify `attempted_sources` tracked correctly

---

### Commit 2: Create format_search_summary() Helper
**Files:** `mcp_server.py`
**Lines:** New function after line 2643
**Changes:**
- Add `format_search_summary()` function
- Format UK Companies House results as structured markdown
- Format parallel search results
- Format OpenSanctions results
- No raw JSON dumps

**New Function:**
```python
def format_search_summary(data: dict, metadata: dict) -> str:
    """
    Format search results as structured markdown.

    Returns key highlights, not raw JSON dumps.
    Claude can then enhance presentation further.
    """
    router = metadata.get("router")
    query = metadata.get("query")
    time_ms = metadata.get("execution_time_ms")
    attempted = metadata.get("attempted_sources", [])

    lines = [
        f"# Search Results: {query}",
        f"**Source:** {router}",
        f"**Execution Time:** {time_ms}ms",
        ""
    ]

    if attempted:
        lines.append(f"**Sources Attempted:** {' → '.join(attempted)}")
        lines.append("")

    # Format based on router type
    if router == "companies_house_uk":
        top_match = data.get("top_match", {})
        lines.extend([
            f"## Top Match: {top_match.get('title')}",
            f"- **Company Number:** {top_match.get('company_number')}",
            f"- **Status:** {top_match.get('company_status')}",
            ""
        ])

        # PSC data
        psc_data = data.get("psc", [])
        if psc_data:
            lines.append(f"## Persons with Significant Control ({len(psc_data)})")
            for psc in psc_data[:5]:
                name = psc.get('name')
                control = psc.get('natures_of_control', ['Unknown'])[0] if psc.get('natures_of_control') else 'Unknown'
                lines.append(f"- **{name}** — {control}")
            lines.append("")

        # Officers
        officers = data.get("officers", [])
        if officers:
            lines.append(f"## Officers ({len(officers)})")
            for officer in officers[:5]:
                lines.append(f"- **{officer.get('name')}** — {officer.get('officer_role')}")
            lines.append("")

    elif router in ("intelligence", "parallel_fallback"):
        # Parallel search
        oc_data = data.get("opencorporates", {})
        aleph_data = data.get("aleph", {})
        edgar_data = data.get("edgar", {})

        if oc_data.get("ok"):
            companies = oc_data.get("results", {}).get("companies", [])
            lines.append(f"## OpenCorporates: {len(companies)} results")
            if companies:
                top = companies[0]
                lines.append(f"- **{top.get('name')}** ({top.get('jurisdiction_code')})")
            lines.append("")

        if aleph_data.get("ok"):
            entities = aleph_data.get("results", [])
            lines.append(f"## OCCRP Aleph: {len(entities)} entities")
            lines.append("")

        if edgar_data.get("ok"):
            filings = edgar_data.get("filings_by_type", {})
            total_filings = sum(len(v) for v in filings.values())
            lines.append(f"## EDGAR SEC: {total_filings} filings")
            for filing_type, filing_list in filings.items():
                lines.append(f"- **{filing_type}:** {len(filing_list)}")
            lines.append("")

    elif router == "opensanctions":
        sanctions = data.get("sanctions", [])
        peps = data.get("peps", [])
        other = data.get("other", [])

        lines.append(f"## Summary")
        lines.append(f"- 🚨 **Sanctions:** {len(sanctions)}")
        lines.append(f"- 👤 **PEPs:** {len(peps)}")
        lines.append(f"- 📋 **Other:** {len(other)}")
        lines.append("")

        if sanctions:
            lines.append("## Sanctions Matches")
            for entity in sanctions[:5]:
                lines.append(f"- **{entity.get('caption')}** — {', '.join(entity.get('datasets', []))}")

    return "\n".join(lines)
```

**Testing:**
- Test UK result formatting
- Test parallel result formatting
- Test OpenSanctions formatting
- Verify no raw JSON in output

---

### Commit 3: Use format_search_summary() in handle_router_search()
**Files:** `mcp_server.py`
**Lines:** 2695-2713 (deterministic execution block)
**Changes:**
- Replace raw JSON dump with `format_search_summary()` call
- Return structured markdown
- Include metadata in summary

**Diff Preview:**
```python
# BEFORE (mcp_server.py:2703-2706)
json_output = json.dumps(direct_result, indent=2, default=str)
return [types.TextContent(
    type="text",
    text=f"# Search Results (Deterministic)\n\n```json\n{json_output}\n```"
)]

# AFTER
if direct_result.get("ok"):
    data = direct_result.get("data", {})
    metadata = {
        "router": direct_result.get("router"),
        "query": direct_result.get("query"),
        "country": direct_result.get("country_code"),
        "execution_time_ms": direct_result.get("execution_time_ms"),
        "attempted_sources": direct_result.get("attempted_sources")
    }

    summary = format_search_summary(data, metadata)

    return [types.TextContent(type="text", text=summary)]
else:
    # Error case
    error_msg = direct_result.get("error", "Unknown error")
    attempted = ", ".join(direct_result.get("attempted_sources", []))

    return [types.TextContent(
        type="text",
        text=f"❌ Search failed after trying: {attempted}\n\nError: {error_msg}"
    )]
```

**Testing:**
- Test successful search formatting
- Test error case formatting
- Verify no raw JSON dumps

---

### Commit 4: Remove Duplicate Legacy Handlers
**Files:** `mcp_server.py`
**Lines:** 2824+ (legacy handler functions)
**Changes:**
- Delete `handle_company_intelligence()` function
- Delete `handle_person_intelligence()` function
- Delete `handle_opensanctions_search()` function
- Delete routing to these functions (already unreachable)
- Add comment explaining why they were removed

**Diff Preview:**
```python
# BEFORE (mcp_server.py:2809-2824)
elif router == "intelligence":
    return await handle_company_intelligence(search_query)

elif router == "person_intelligence":
    return await handle_person_intelligence(search_query)

# ... more legacy handlers ...

# AFTER
# Legacy handlers removed - now covered by deterministic execution path
# If you reach this point, router was NOT in deterministic_routers set
# Only non-deterministic routers (wiki sections, etc.) continue here
```

**Find and delete these functions:**
```bash
grep -n "async def handle_company_intelligence" mcp_server.py
grep -n "async def handle_person_intelligence" mcp_server.py
grep -n "async def handle_opensanctions_search" mcp_server.py
```

**Testing:**
- Verify deterministic routers don't call legacy functions
- Verify no duplicate execution
- Verify all tests still pass

---

### Commit 5: Add Execution Time Tracking
**Files:** `mcp_server.py`
**Lines:** 2515-2643 (execute_direct_search function)
**Changes:**
- Import `time` module
- Record start time at function entry
- Calculate execution_time_ms before each return
- Include in result dict

**Already shown in Commit 1, ensuring it's in all code paths**

---

### Commit 6: Write Phase 1 Unit Tests
**Files:** NEW `tests/test_phase1_deterministic_routing.py`
**Changes:**
- Create test file
- Test UK fallback logic
- Test response formatting
- Test no duplicate execution
- Test execution time tracking
- Test error cases

**New File:**
```python
"""
Phase 1 Unit Tests: Deterministic Routing

Tests:
1. UK Companies House fallback on failure
2. Clean response formatting (no raw JSON)
3. No duplicate execution paths
4. Execution time tracking
5. Error handling
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import mcp_server


class TestUKFallback:
    """Test UK Companies House fallback logic."""

    @patch('mcp_server.tool_parallel_search')
    @patch('companies_house_unified.search_uk_company')
    def test_companies_house_success(self, mock_ch, mock_parallel):
        """UK search succeeds with Companies House."""
        mock_ch.return_value = {
            "ok": True,
            "top_match": {"title": "BP plc", "company_number": "00102498"},
            "psc": [{"name": "Test PSC"}],
            "officers": [{"name": "Test Officer"}]
        }

        result = mcp_server.execute_direct_search({
            "router": "intelligence",
            "country_code": "uk",
            "query": "BP plc"
        })

        assert result["ok"] == True
        assert result["router"] == "companies_house_uk"
        assert "psc" in result["data"]
        assert "companies_house" in result["attempted_sources"]
        assert result["execution_time_ms"] > 0

        # Parallel search should NOT be called
        mock_parallel.assert_not_called()

    @patch('mcp_server.tool_parallel_search')
    @patch('companies_house_unified.search_uk_company')
    def test_companies_house_fallback_on_failure(self, mock_ch, mock_parallel):
        """UK search falls back to parallel when Companies House fails."""
        mock_ch.return_value = {
            "ok": False,
            "error": "API key invalid"
        }

        mock_parallel.return_value = {
            "ok": True,
            "opencorporates": {"ok": True, "results": {"companies": []}},
            "aleph": {"ok": True, "results": []},
            "edgar": {"ok": True}
        }

        result = mcp_server.execute_direct_search({
            "router": "intelligence",
            "country_code": "uk",
            "query": "BP plc"
        })

        assert result["ok"] == True
        assert result["router"] == "parallel_fallback"
        assert "companies_house" in result["attempted_sources"]
        assert "fallback_to_parallel" in result["attempted_sources"]

        # Parallel search SHOULD be called
        mock_parallel.assert_called_once()

    @patch('mcp_server.tool_parallel_search')
    @patch('companies_house_unified.search_uk_company')
    def test_companies_house_fallback_on_exception(self, mock_ch, mock_parallel):
        """UK search falls back to parallel when Companies House raises exception."""
        mock_ch.side_effect = Exception("API connection error")

        mock_parallel.return_value = {
            "ok": True,
            "opencorporates": {"ok": True}
        }

        result = mcp_server.execute_direct_search({
            "router": "intelligence",
            "country_code": "uk",
            "query": "BP plc"
        })

        assert result["ok"] == True
        assert result["router"] == "parallel_fallback"
        assert "companies_house_error" in result["attempted_sources"]


class TestResponseFormatting:
    """Test clean response formatting."""

    def test_no_raw_json_dumps(self):
        """Response should be structured markdown, not raw JSON."""
        data = {
            "top_match": {
                "title": "BP plc",
                "company_number": "00102498",
                "company_status": "active"
            },
            "psc": [
                {"name": "Test PSC", "natures_of_control": ["ownership-of-shares-75-to-100-percent"]}
            ],
            "officers": [
                {"name": "Test Officer", "officer_role": "director"}
            ]
        }

        metadata = {
            "router": "companies_house_uk",
            "query": "BP plc",
            "execution_time_ms": 1500,
            "attempted_sources": ["companies_house"]
        }

        summary = mcp_server.format_search_summary(data, metadata)

        # Should NOT contain raw JSON
        assert "```json" not in summary
        assert '{"ok":' not in summary

        # Should contain structured markdown
        assert "# Search Results:" in summary
        assert "## Top Match:" in summary
        assert "## Persons with Significant Control" in summary
        assert "BP plc" in summary

    def test_uk_formatting(self):
        """UK results formatted correctly."""
        data = {
            "top_match": {"title": "Test Company", "company_number": "12345"},
            "psc": [{"name": "PSC 1"}],
            "officers": [{"name": "Officer 1", "officer_role": "director"}]
        }

        summary = mcp_server.format_search_summary(data, {"router": "companies_house_uk"})

        assert "Test Company" in summary
        assert "12345" in summary
        assert "PSC 1" in summary
        assert "Officer 1" in summary


class TestNoDuplicateExecution:
    """Test that deterministic path doesn't fall through to legacy."""

    @pytest.mark.asyncio
    async def test_no_legacy_handler_called(self):
        """Deterministic routers should not call legacy handlers."""
        with patch('mcp_server.execute_direct_search') as mock_direct:
            with patch('mcp_server.handle_company_intelligence') as mock_legacy:
                mock_direct.return_value = {
                    "ok": True,
                    "router": "intelligence",
                    "data": {},
                    "execution_time_ms": 100
                }

                # This should hit deterministic path only
                result = await mcp_server.handle_router_search("c:Tesla")

                # Verify direct execution called
                assert mock_direct.called

                # Verify legacy handler NOT called
                assert not mock_legacy.called


class TestExecutionTiming:
    """Test execution time tracking."""

    def test_execution_time_recorded(self):
        """Execution time should be tracked."""
        result = mcp_server.execute_direct_search({
            "router": "opensanctions",
            "query": "test"
        })

        # Should have execution_time_ms key
        assert "execution_time_ms" in result
        assert isinstance(result["execution_time_ms"], int)
        assert result["execution_time_ms"] >= 0


class TestErrorHandling:
    """Test error case handling."""

    def test_error_message_includes_attempted_sources(self):
        """Error messages should include what was attempted."""
        result = mcp_server.execute_direct_search({
            "router": "invalid_router",
            "query": "test"
        })

        assert result["ok"] == False
        assert "error" in result
        assert "attempted_sources" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Run Tests:**
```bash
cd "/Users/brain/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/0. WIKIMAN-PRO"
python -m pytest tests/test_phase1_deterministic_routing.py -v
```

---

## Commit Order and Dependencies

1. ✅ **Commit 1: Fallback logic** - Must be first (enables graceful degradation)
2. ✅ **Commit 2: Format helper** - Independent, can be parallel with Commit 1
3. ✅ **Commit 3: Use format helper** - Depends on Commit 2
4. ✅ **Commit 4: Remove duplicates** - After Commits 1-3 proven working
5. ✅ **Commit 5: Already in Commit 1** - No separate commit needed
6. ✅ **Commit 6: Tests** - After all code changes, validates everything

**Actual Commit Sequence:**
```bash
git add mcp_server.py
git commit -m "Phase 1.1: Add cascading fallback logic to execute_direct_search()"

git add mcp_server.py
git commit -m "Phase 1.2: Create format_search_summary() helper for clean markdown output"

git add mcp_server.py
git commit -m "Phase 1.3: Use format_search_summary() in handle_router_search()"

git add mcp_server.py
git commit -m "Phase 1.4: Remove duplicate legacy handlers (covered by deterministic path)"

git add tests/test_phase1_deterministic_routing.py
git commit -m "Phase 1.5: Add comprehensive unit tests for Phase 1"
```

---

## Validation Checklist

Before marking Phase 1 complete:

- [ ] Commit 1: Fallback logic added and tested
- [ ] Commit 2: Format helper created
- [ ] Commit 3: Format helper integrated
- [ ] Commit 4: Legacy handlers removed
- [ ] Commit 5: Execution time tracking verified
- [ ] Commit 6: All tests passing
- [ ] Manual test: `cuk:BP plc` returns PSC data
- [ ] Manual test: Mock Companies House failure, verify fallback
- [ ] Manual test: `c:Tesla` returns parallel search
- [ ] Manual test: No raw JSON in output
- [ ] Manual test: Response is structured markdown
- [ ] Code review: All diffs reviewed
- [ ] Documentation: PHASE_1_COMPLETION_REPORT.md created

---

## Next Steps After Phase 1

Once Phase 1 validated:
1. Create PHASE_1_COMPLETION_REPORT.md
2. Measure token savings (before/after)
3. Measure latency improvements (before/after)
4. Deploy to staging
5. User approval for Phase 2

---

## Notes

- Each commit should be atomic and testable
- Tests run after each commit
- No commit should break existing functionality
- All changes tracked in this document
- User can review diffs before approval
