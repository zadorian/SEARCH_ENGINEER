#!/usr/bin/env python3
"""
Quick test for SeekLeech.

Usage:
    python test_seekleech.py
    python test_seekleech.py --domain cégközlöny.hu
"""

import asyncio
import logging
from seekleech import SeekLeech

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger()


async def test_single(domain: str = "e-cegjegyzek.hu"):
    """Test mining a single registry."""

    registry = {
        "id": f"{domain}_test",
        "domain": domain,
        "jurisdiction": "HU",
        "url": f"https://{domain}",
        "type": "corporate_registry"
    }

    p = SeekLeech()
    try:
        result = await p.mine(registry)

        print("\n" + "="*50)
        print(f"Domain: {result.domain}")
        print(f"Status: {result.status}")
        print(f"Method: {result.method}")
        print(f"Requires Browser: {result.requires_browser}")
        print(f"Validated: {result.validated}")

        if result.templates:
            print("\nTemplates found:")
            for ttype, tdata in result.templates.items():
                print(f"  {ttype}:")
                for k, v in tdata.items():
                    print(f"    {k}: {v}")

        if result.notes:
            print(f"\nNotes: {result.notes}")

    finally:
        await p.close()


async def test_batch():
    """Test batch processing with a few registries."""
    from pathlib import Path

    registries = [
        {"id": "test_hu_1", "domain": "e-cegjegyzek.hu", "jurisdiction": "HU", "url": "https://e-cegjegyzek.hu", "type": "corporate_registry"},
        {"id": "test_uk_1", "domain": "find-and-update.company-information.service.gov.uk", "jurisdiction": "GB", "url": "https://find-and-update.company-information.service.gov.uk", "type": "corporate_registry"},
        {"id": "test_de_1", "domain": "handelsregister.de", "jurisdiction": "DE", "url": "https://www.handelsregister.de", "type": "corporate_registry"},
    ]

    p = SeekLeech()
    try:
        results = await p.run(
            registries,
            output=Path("test_results.json"),
            concurrent=2,
            resume=False,
            validate=True
        )

        print("\n" + "="*50)
        print("SUMMARY:")
        for r in results:
            status = "✓" if r.get("status") == "found" else "✗"
            print(f"  {status} {r.get('domain')}: {r.get('status')}")

    finally:
        await p.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", help="Test single domain")
    parser.add_argument("--batch", action="store_true", help="Test batch mode")
    args = parser.parse_args()

    if args.domain:
        asyncio.run(test_single(args.domain))
    elif args.batch:
        asyncio.run(test_batch())
    else:
        # Default: test Hungarian registry
        asyncio.run(test_single())
