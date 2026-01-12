from __future__ import annotations

import json

import pytest


class _DummyResponse:
    def __init__(self, *, status: int, text: str):
        self.status = status
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self) -> str:
        return self._text


class _DummySession:
    def __init__(self):
        self.calls = []

    def get(self, url: str, *, params=None):
        self.calls.append({"url": url, "params": params})
        payload = {
            "url": "https://www.example.com/",
            "filename": "crawl-data/CC-MAIN-2025-51/segments/x/warc/example.warc.gz",
            "offset": "0",
            "length": "10",
            "status": "200",
            "mime": "text/html",
            "timestamp": "20250101000000",
            "digest": "ABC",
            "languages": "eng",
        }
        return _DummyResponse(status=200, text=json.dumps(payload) + "\n")


@pytest.mark.asyncio
async def test_periscope_preserves_multiple_filters(monkeypatch):
    from SUBMARINE.periscope.cc_index import Periscope

    periscope = Periscope(archive="CC-MAIN-2025-51")
    periscope.cache_ttl_seconds = 0
    dummy = _DummySession()

    async def _get_session():
        return dummy

    monkeypatch.setattr(periscope, "_get_session", _get_session)

    await periscope.lookup_domain(
        "example.com",
        limit=1,
        filter_status=200,
        filter_mime="text/html",
        filter_languages="eng",
        from_ts="20250101000000",
        to_ts="20250102000000",
    )

    assert dummy.calls, "Expected a CC Index request"
    params = dummy.calls[0]["params"]

    assert ("url", "*.example.com/*") in params
    assert ("from", "20250101000000") in params
    assert ("to", "20250102000000") in params

    filters = [p for p in params if p[0] == "filter"]
    assert ("filter", "status:200") in filters
    assert ("filter", "mime:text/html") in filters
    assert ("filter", "languages:eng") in filters


@pytest.mark.asyncio
async def test_periscope_url_contains_is_embedded_in_pattern(monkeypatch):
    from SUBMARINE.periscope.cc_index import Periscope

    periscope = Periscope(archive="CC-MAIN-2025-51")
    periscope.cache_ttl_seconds = 0
    dummy = _DummySession()

    async def _get_session():
        return dummy

    monkeypatch.setattr(periscope, "_get_session", _get_session)

    await periscope.lookup_domain("example.com", limit=1, url_contains="acme corp")

    assert dummy.calls, "Expected a CC Index request"
    params = dummy.calls[0]["params"]
    assert ("url", "*.example.com/*acme*corp*") in params
