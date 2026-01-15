#!/usr/bin/env python3
"""
PACMAN Launcher for CC-PDF-2025 Dataset
========================================

Usage:
    python run_pacman.py                    # Process all parquet files
    python run_pacman.py --dry-run          # Test without indexing
    python run_pacman.py --reset            # Clear checkpoint, start fresh
"""

import asyncio
import argparse
from pathlib import Path
from typing import AsyncIterator, Dict, Any

import pyarrow.parquet as pq
from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from sources.Pacman import PacmanRunner, Tier, TARGET_INDEX

# Data source
PARQUET_DIR = Path(__file__).parent.parent.parent.parent.parent / "output" / "finepdfs_corporate"
PARQUET_PATTERN = "corporate_pdfs_*.parquet"

# Elasticsearch
ES_HOST = "http://localhost:9200"


async def parquet_document_iterator(parquet_dir: Path) -> AsyncIterator[Dict[str, Any]]:
    """
    Async iterator over all parquet files in directory.
    Yields documents with url, domain, content fields.
    """
    parquet_files = sorted(parquet_dir.glob(PARQUET_PATTERN))

    for pf_path in parquet_files:
        print(f"\n📄 Reading {pf_path.name}...")
        table = pq.read_table(pf_path)
        df = table.to_pandas()

        for _, row in df.iterrows():
            yield {
                "url": row.get("url", ""),
                "domain": row.get("domain", ""),
                "content": row.get("text", ""),
                # Pass through other metadata
                "language": row.get("language"),
                "token_count": row.get("token_count"),
                "priority_score": row.get("priority_score"),
                "jurisdiction": row.get("jurisdiction"),
                "is_regulatory": row.get("is_regulatory"),
                "has_financial_tables": row.get("has_financial_tables"),
                "detected_sectors": row.get("detected_sectors"),
            }


def count_total_documents(parquet_dir: Path) -> int:
    """Count total documents across all parquet files."""
    total = 0
    parquet_files = sorted(parquet_dir.glob(PARQUET_PATTERN))

    for pf_path in parquet_files:
        pf = pq.ParquetFile(pf_path)
        total += pf.metadata.num_rows

    return total


async def create_index_callback(es: AsyncElasticsearch, dry_run: bool = False):
    """Create the indexing callback function."""

    # Buffer for bulk indexing
    buffer = []
    buffer_size = 500

    async def flush_buffer():
        if buffer:
            if not dry_run:
                await async_bulk(es, buffer, raise_on_error=False)
            buffer.clear()

    async def index_callback(doc: Dict, tier: Tier) -> bool:
        """Index document to Elasticsearch."""
        try:
            action = {
                "_index": TARGET_INDEX,
                "_source": doc,
            }
            buffer.append(action)

            if len(buffer) >= buffer_size:
                await flush_buffer()

            return True
        except Exception as e:
            print(f"\n❌ Index error: {e}")
            return False

    # Attach flush function for final cleanup
    index_callback.flush = flush_buffer

    return index_callback


async def main():
    parser = argparse.ArgumentParser(description="Run PACMAN ingestion on CC-PDF-2025")
    parser.add_argument("--dry-run", action="store_true", help="Test without indexing")
    parser.add_argument("--reset", action="store_true", help="Clear checkpoint, start fresh")
    args = parser.parse_args()

    # Check parquet directory
    if not PARQUET_DIR.exists():
        print(f"❌ Parquet directory not found: {PARQUET_DIR}")
        sys.exit(1)

    # Count documents
    print("📊 Counting documents...")
    total_docs = count_total_documents(PARQUET_DIR)
    print(f"   Found {total_docs:,} documents in {PARQUET_DIR}")

    # Initialize runner
    runner = PacmanRunner()

    # Handle reset
    if args.reset:
        runner.checkpoint_manager.clear()
        print("🗑️  Checkpoint cleared")

    # Initialize Elasticsearch
    es = AsyncElasticsearch([ES_HOST])

    try:
        # Check connection
        if not await es.ping():
            print("❌ Cannot connect to Elasticsearch")
            sys.exit(1)

        # Create index callback
        index_callback = await create_index_callback(es, dry_run=args.dry_run)

        if args.dry_run:
            print("🧪 DRY RUN MODE - no documents will be indexed")

        # Run ingestion
        await runner.run(
            documents=parquet_document_iterator(PARQUET_DIR),
            total_count=total_docs,
            index_callback=index_callback,
        )

        # Flush remaining buffer
        await index_callback.flush()

    finally:
        await es.close()


if __name__ == "__main__":
    asyncio.run(main())
