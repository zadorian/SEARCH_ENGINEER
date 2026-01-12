import os

import pytest


class _DummyIndices:
    def __init__(self, exists_map):
        self._exists_map = exists_map

    async def exists(self, index: str) -> bool:
        return bool(self._exists_map.get(index, False))


class _DummyAsyncES:
    def __init__(self, exists_map, search_results_by_index):
        self.indices = _DummyIndices(exists_map)
        self._search_results_by_index = search_results_by_index
        self.calls = []

    async def search(self, index: str, query: dict, size: int, _source: bool = True, **kwargs):
        self.calls.append({"index": index, "query": query, "size": size, "kwargs": kwargs})
        return self._search_results_by_index.get(index, {"hits": {"hits": []}})


@pytest.mark.asyncio
async def test_graph_backlinks_uses_source_target_fields():
    from SUBMARINE.sonar.elastic_scanner import Sonar, SonarResult

    es = _DummyAsyncES(
        exists_map={"cc_web_graph_host_edges": True},
        search_results_by_index={
            "cc_web_graph_host_edges": {
                "hits": {
                    "hits": [
                        {"_id": "1", "_score": 1.0, "_source": {"source": "a.example", "target": "b.example"}}
                    ]
                }
            }
        },
    )

    sonar = Sonar()
    sonar.es = es
    result = SonarResult(query="b.example")

    await sonar._scan_graph_backlinks("b.example", result, limit=10)

    assert "cc_web_graph_host_edges" in result.indices_scanned
    assert "a.example" in result.domains
    assert "b.example" in result.domains

    assert es.calls, "Expected an Elasticsearch search call"
    q = es.calls[0]["query"]
    should = q["bool"]["should"]
    assert {"term": {"target": "b.example"}} in should
    assert {"term": {"source": "b.example"}} in should
    # Regression guard: older field names must not be used
    assert "target_host" not in str(q)
    assert "source_host" not in str(q)


@pytest.mark.asyncio
async def test_corpus_scan_prefers_home_then_raw_and_extracts_domains_urls(monkeypatch):
    from SUBMARINE.sonar.elastic_scanner import Sonar, SonarResult

    monkeypatch.setenv("SUBMARINE_CORPUS_INDICES", "cymonides-3,cymonides-2")

    es = _DummyAsyncES(
        exists_map={"cymonides-3": False, "cymonides-2": True},
        search_results_by_index={
            "cymonides-2": {
                "hits": {
                    "hits": [
                        {
                            "_id": "doc1",
                            "_score": 2.0,
                            "_source": {
                                "source_domain": "example.com",
                                "source_url": "https://example.com/page",
                                "extracted_entities": {"domains": ["sub.example.com"], "urls": ["https://sub.example.com/a"]},
                            },
                        }
                    ]
                }
            }
        },
    )

    sonar = Sonar()
    sonar.es = es
    result = SonarResult(query="example.com")

    await sonar._scan_corpus_indices("example.com", "domain", result, limit=10)

    assert "cymonides-2" in result.indices_scanned
    assert "cymonides-3" not in result.indices_scanned

    assert "example.com" in result.domains
    assert "sub.example.com" in result.domains
    assert "https://example.com/page" in result.urls
    assert "https://sub.example.com/a" in result.urls

