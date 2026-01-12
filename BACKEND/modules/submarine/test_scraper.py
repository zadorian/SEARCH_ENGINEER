from __future__ import annotations

import os

import pytest


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_extract_full_smoke():
    if os.getenv("RUN_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to run SUBMARINE integration tests")

    from SUBMARINE.distributed_scraper import SubmarineScraper

    scraper = SubmarineScraper(es_host="localhost")

    html = """
    <html><body>
    <a href="https://google.com">Google</a>
    <a href="https://facebook.com/page">FB</a>
    <a href="/about">About</a>
    <a href="https://linkedin.com/company/test">LinkedIn</a>
    John Smith is the CEO of Acme Ltd.
    Dr. Sarah Johnson works at Global Finance GmbH.
    </body></html>
    """

    result = await scraper._extract_full(html, "test content", "https://example.com")
    assert isinstance(result, dict)
    assert "outlinks" in result
    assert isinstance(result.get("outlinks"), list)
    assert isinstance(result.get("outlinks_external"), list)

    await scraper.close()
