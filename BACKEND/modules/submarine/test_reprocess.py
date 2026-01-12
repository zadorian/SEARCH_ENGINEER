from __future__ import annotations

import os

import pytest
import requests


pytestmark = pytest.mark.integration


def test_reprocessor_components_smoke():
    if os.getenv("RUN_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to run SUBMARINE integration tests")

    es_host = os.getenv("SUBMARINE_ES_HOST", "http://localhost:9200")
    es_index = os.getenv("SUBMARINE_ES_INDEX", "submarine-scrapes")

    try:
        resp = requests.get(f"{es_host}/{es_index}/_count", timeout=2)
    except requests.RequestException:
        pytest.skip("Elasticsearch not reachable")

    if resp.status_code == 404:
        pytest.skip(f"Elasticsearch index not found: {es_index}")

    assert resp.status_code == 200
    data = resp.json()
    assert "count" in data

    from SUBJECT.detector import classify_text

    subject = classify_text("John Smith is the CEO of Finance Corp.")
    assert isinstance(subject, dict)
