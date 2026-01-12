#!/usr/bin/env python3
"""
EYE-D -> Cymonides-1 (C-1) End-to-End Smoke Test

Validates that EYE-D-style results can be indexed into the Cymonides-1 Elasticsearch
graph (nodes + embedded_edges) using the shared C1Bridge implementation.

Runs locally against `http://localhost:9200` only (no external APIs).
"""

from __future__ import annotations

if __name__ != "__main__":
    import pytest

    pytest.skip("EYE-D smoke tests are manual; run directly", allow_module_level=True)

import sys
import time
from pathlib import Path


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from LINKLATER.c1_bridge import C1Bridge

    project_id = f"project-eyed-smoke-{int(time.time())}"
    bridge = C1Bridge(project_id=project_id)
    index_name = bridge._get_index_name()

    eyed_results = {
        "query": "alice@example.com",
        "subtype": "email",
        "timestamp": time.time(),
        "results": [
            {"source": "DeHashed", "data": {"url": None}},
            {"source": "OSINT Industries", "data": {"url": None}},
        ],
        "entities": [
            {"type": "domain", "value": "example.com"},
            {"type": "username", "value": "alice"},
            {"type": "phone", "value": "+1 (555) 010-9999"},
        ],
    }

    stats = bridge.index_eyed_results(eyed_results)
    if stats.get("errors"):
        return _fail(f"indexing returned errors: {stats}")

    try:
        count = bridge.es.count(index=index_name)["count"]
    except Exception as e:
        return _fail(f"failed to count docs in {index_name}: {e}")

    if count < 3:
        return _fail(f"expected at least 3 nodes in {index_name}, got {count}")

    main_id = bridge._generate_id("alice@example.com", "email")
    main_node = bridge.get_node(main_id)
    if not main_node:
        return _fail("main entity node missing after indexing")

    embedded = main_node.get("embedded_edges") or []
    relations = {e.get("relation") for e in embedded if isinstance(e, dict)}
    if "found_on" not in relations:
        return _fail(f"main node missing found_on edge(s): {relations}")
    if "co_occurs_with" not in relations:
        return _fail(f"main node missing co_occurs_with edge(s): {relations}")

    source_url = "eyed://DeHashed/email/alice@example.com"
    source_id = bridge._generate_id(source_url, "webpage")
    source_node = bridge.get_node(source_id)
    if not source_node:
        return _fail("source node missing after indexing")

    source_embedded = source_node.get("embedded_edges") or []
    source_relations = {e.get("relation") for e in source_embedded if isinstance(e, dict)}
    if "mentions" not in source_relations:
        return _fail(f"source node missing mentions edge(s): {source_relations}")

    # Cleanup: remove only the smoke-test index we created.
    try:
        bridge.es.indices.delete(index=index_name)
    except Exception:
        pass

    print("PASS: EYE-D C-1 indexing smoke test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

