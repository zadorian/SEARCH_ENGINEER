from __future__ import annotations

import pytest


class _DummySonar:
    def __init__(self, *, query_type: str, domains: set[str]):
        self._query_type = query_type
        self._domains = set(domains)

    def _detect_query_type(self, query: str) -> str:
        return self._query_type

    async def scan_all(self, query: str, limit: int = 10000):
        from SUBMARINE.sonar.elastic_scanner import SonarResult

        return SonarResult(query=query, domains=set(self._domains))

    async def close(self):
        return None


class _DummyPeriscope:
    def __init__(self, *, records_by_domain=None, keyword_records=None):
        self.archive = "CC-MAIN-2025-51"
        self._records_by_domain = records_by_domain or {}
        self._keyword_records = keyword_records or []
        self.lookup_calls = []
        self.search_calls = []

    async def lookup_domain(self, domain: str, **kwargs):
        self.lookup_calls.append({"domain": domain, "kwargs": kwargs})
        return list(self._records_by_domain.get(domain, []))

    async def search(self, pattern: str, **kwargs):
        self.search_calls.append({"pattern": pattern, "kwargs": kwargs})
        return list(self._keyword_records)

    async def close(self):
        return None


def _cc_record(url: str):
    from SUBMARINE.periscope.cc_index import CCRecord
    import zlib

    return CCRecord(
        url=url,
        filename="crawl-data/CC-MAIN-2025-51/segments/x/warc/example.warc.gz",
        offset=int(zlib.crc32(url.encode("utf-8")) % 1_000_000),
        length=10,
        status=200,
        mime="text/html",
        timestamp="20250101000000",
        digest="ABC",
    )


@pytest.mark.asyncio
async def test_planner_domain_query_runs_without_sonar_domains():
    from SUBMARINE.dive_planner.planner import DivePlanner

    planner = DivePlanner()
    planner.sonar = _DummySonar(query_type="domain", domains=set())
    planner.periscope = _DummyPeriscope(records_by_domain={"example.com": [_cc_record("https://example.com/")]})

    plan = await planner.create_plan("example.com", max_domains=10, max_pages_per_domain=3)

    assert plan.total_domains == 1
    assert plan.targets[0].domain == "example.com"
    assert planner.periscope.lookup_calls and planner.periscope.lookup_calls[0]["domain"] == "example.com"

    await planner.close()


@pytest.mark.asyncio
async def test_planner_cc_keyword_fallback_buckets_domains_and_applies_tld_filter():
    from SUBMARINE.dive_planner.planner import DivePlanner

    records = [
        _cc_record("https://b.org/a"),
        _cc_record("https://b.org/b"),
        _cc_record("https://b.org/c"),
        _cc_record("https://a.com/a"),
        _cc_record("https://a.com/b"),
        _cc_record("https://c.com/a"),
    ]

    planner = DivePlanner()
    planner.sonar = _DummySonar(query_type="entity", domains=set())
    planner.periscope = _DummyPeriscope(keyword_records=records)

    plan = await planner.create_plan(
        "Acme Corp",
        max_domains=2,
        max_pages_per_domain=2,
        tld_include=["com"],
    )

    assert plan.query_type == "cc_keyword"
    assert {t.domain for t in plan.targets} == {"a.com", "c.com"}
    assert all(len(t.cc_records) <= 2 for t in plan.targets)

    assert planner.periscope.search_calls, "Expected CC keyword fallback search"
    assert planner.periscope.search_calls[0]["pattern"] == "*Acme*Corp*"

    await planner.close()


@pytest.mark.asyncio
async def test_planner_uses_domain_allowlist_when_sonar_empty():
    from SUBMARINE.dive_planner.planner import DivePlanner

    planner = DivePlanner()
    planner.sonar = _DummySonar(query_type="entity", domains=set())
    planner.periscope = _DummyPeriscope(
        records_by_domain={
            "a.com": [_cc_record("https://a.com/a")],
            "b.com": [_cc_record("https://b.com/a")],
        }
    )

    plan = await planner.create_plan(
        "Acme Corp",
        max_domains=10,
        max_pages_per_domain=1,
        domain_allowlist=["a.com", "b.com"],
        url_contains="acme",
    )

    assert plan.total_domains == 2
    assert [c["domain"] for c in planner.periscope.lookup_calls] == ["a.com", "b.com"]

    await planner.close()
