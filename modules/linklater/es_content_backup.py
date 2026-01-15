"""
ES Content Backup Manager
=========================
Auto-zips and uploads ALL content indexed to Elasticsearch to Google Drive.

Features:
- Intercepts ES bulk indexing operations
- Batches documents (configurable, default 50)
- Creates zip archives with descriptive naming
- Uploads to Google Drive via rclone
- Works for any ES index (onion-pages, graphs, clearnet, etc.)

Usage:
    from modules.linklater.es_content_backup import ESBackupManager

    # Create backup manager for an index
    backup_mgr = ESBackupManager(
        index_name="onion-pages",
        gdrive_path="es_backups/tor",
        batch_size=50
    )

    # Track documents as they're indexed
    backup_mgr.track_document(doc)

    # Or use the bulk indexing wrapper
    await backup_mgr.bulk_index_with_backup(es_client, documents)

Structure in GDrive:
    es_backups/
    └── {index_name}/
        └── {date}/
            └── batch_{start}-{end}_{timestamp}.zip
                ├── documents.ndjson
                └── manifest.json
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

# Local staging directory for content before zipping
STAGING_BASE = Path(__file__).parent / "es_backup_staging"
STAGING_BASE.mkdir(parents=True, exist_ok=True)

# Index file tracking what's been backed up
BACKUP_INDEX_FILE = STAGING_BASE / "backup_index.jsonl"

# Default GDrive path
DEFAULT_GDRIVE_PATH = "es_backups"

# rclone path
RCLONE_PATH = "/opt/homebrew/bin/rclone"


@dataclass
class ESBackupConfig:
    """Configuration for ES content backup."""

    # Index-specific settings
    index_name: str

    # Batching
    batch_size: int = 50  # Create zip after N documents

    # GDrive settings
    gdrive_enabled: bool = True
    gdrive_path: str = DEFAULT_GDRIVE_PATH
    gdrive_delete_local: bool = True  # Delete local zips after successful GDrive upload

    # Local settings
    keep_staging: bool = False  # Keep raw files after zipping
    staging_dir: Optional[Path] = None

    def __post_init__(self):
        # Set staging directory
        if self.staging_dir is None:
            self.staging_dir = STAGING_BASE / self.index_name
        self.staging_dir.mkdir(parents=True, exist_ok=True)


# =============================================================================
# ES Backup Manager
# =============================================================================

class ESBackupManager:
    """
    Manages backup of ES-indexed content to Google Drive.

    Tracks documents as they're indexed, batches them, zips, and uploads.
    """

    def __init__(
        self,
        index_name: str,
        gdrive_path: str = DEFAULT_GDRIVE_PATH,
        batch_size: int = 50,
        gdrive_enabled: bool = True,
    ):
        """Initialize backup manager for an ES index."""
        self.config = ESBackupConfig(
            index_name=index_name,
            gdrive_path=gdrive_path,
            batch_size=batch_size,
            gdrive_enabled=gdrive_enabled,
        )

        # Current batch state
        self._current_batch: List[Dict[str, Any]] = []
        self._batch_number: int = self._get_next_batch_number()
        self._total_backed_up: int = 0

        logger.info(
            f"[ESBackup] Initialized for index '{index_name}' "
            f"(batch_size={batch_size}, gdrive={gdrive_enabled})"
        )

    def _get_next_batch_number(self) -> int:
        """Get the next batch number by checking existing backups."""
        if not self.config.staging_dir.exists():
            return 0

        existing_batches = list(self.config.staging_dir.glob("batch_*.zip"))
        if not existing_batches:
            return 0

        # Extract batch numbers from filenames
        max_batch = 0
        for batch_file in existing_batches:
            match = re.search(r'batch_(\d+)-(\d+)', batch_file.name)
            if match:
                end_num = int(match.group(2))
                max_batch = max(max_batch, end_num)

        return (max_batch // self.config.batch_size) + 1

    def track_document(self, doc: Dict[str, Any], doc_id: Optional[str] = None):
        """
        Track a document that was indexed to ES.

        Automatically creates zip and uploads when batch is full.
        """
        # Add metadata
        tracked_doc = {
            "doc_id": doc_id or doc.get("_id") or doc.get("id") or f"doc_{len(self._current_batch)}",
            "indexed_at": datetime.utcnow().isoformat() + "Z",
            "index": self.config.index_name,
            "content": doc,
        }

        self._current_batch.append(tracked_doc)

        # Check if batch is full
        if len(self._current_batch) >= self.config.batch_size:
            # Run sync (can be made async if needed)
            asyncio.create_task(self._create_and_upload_batch())

    async def track_document_async(self, doc: Dict[str, Any], doc_id: Optional[str] = None):
        """Async version of track_document."""
        tracked_doc = {
            "doc_id": doc_id or doc.get("_id") or doc.get("id") or f"doc_{len(self._current_batch)}",
            "indexed_at": datetime.utcnow().isoformat() + "Z",
            "index": self.config.index_name,
            "content": doc,
        }

        self._current_batch.append(tracked_doc)

        if len(self._current_batch) >= self.config.batch_size:
            await self._create_and_upload_batch()

    async def flush(self):
        """Force flush any remaining documents in the current batch."""
        if self._current_batch:
            await self._create_and_upload_batch()

    async def _create_and_upload_batch(self):
        """Create zip archive and upload to GDrive."""
        if not self._current_batch:
            return

        batch_docs = self._current_batch.copy()
        self._current_batch = []

        # Calculate batch range
        batch_start = self._batch_number * self.config.batch_size + 1
        batch_end = batch_start + len(batch_docs) - 1

        # Create date-based subfolder
        date_folder = datetime.utcnow().strftime("%Y-%m-%d")
        batch_folder = self.config.staging_dir / date_folder
        batch_folder.mkdir(parents=True, exist_ok=True)

        # Create zip filename
        timestamp = datetime.utcnow().strftime("%H%M%S")
        zip_name = f"batch_{batch_start:06d}-{batch_end:06d}_{timestamp}.zip"
        zip_path = batch_folder / zip_name

        try:
            # Create NDJSON file with documents
            ndjson_path = batch_folder / f"batch_{batch_start:06d}-{batch_end:06d}.ndjson"
            with open(ndjson_path, 'w') as f:
                for doc in batch_docs:
                    f.write(json.dumps(doc, default=str) + "\n")

            # Create manifest
            manifest = {
                "index": self.config.index_name,
                "batch_start": batch_start,
                "batch_end": batch_end,
                "document_count": len(batch_docs),
                "created_at": datetime.utcnow().isoformat() + "Z",
                "doc_ids": [d["doc_id"] for d in batch_docs],
            }
            manifest_path = batch_folder / f"manifest_{batch_start:06d}-{batch_end:06d}.json"
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)

            # Create zip
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(ndjson_path, f"documents.ndjson")
                zf.write(manifest_path, "manifest.json")

            logger.info(
                f"[ESBackup] Created archive: {zip_path.name} "
                f"({len(batch_docs)} docs from {self.config.index_name})"
            )

            # Clean up staging files
            if not self.config.keep_staging:
                ndjson_path.unlink(missing_ok=True)
                manifest_path.unlink(missing_ok=True)

            # Update backup index
            self._update_backup_index(zip_name, batch_start, batch_end, len(batch_docs))

            # Upload to GDrive
            if self.config.gdrive_enabled:
                await self._upload_to_gdrive(zip_path, date_folder)

            # Update counters
            self._total_backed_up += len(batch_docs)
            self._batch_number += 1

            return zip_path

        except Exception as e:
            logger.error(f"[ESBackup] Failed to create batch archive: {e}")
            # Re-add documents to batch for retry
            self._current_batch = batch_docs + self._current_batch
            raise

    def _update_backup_index(self, zip_name: str, batch_start: int, batch_end: int, doc_count: int):
        """Update the backup index file."""
        entry = {
            "index": self.config.index_name,
            "zip_file": zip_name,
            "batch_start": batch_start,
            "batch_end": batch_end,
            "document_count": doc_count,
            "backed_up_at": datetime.utcnow().isoformat() + "Z",
        }

        with open(BACKUP_INDEX_FILE, 'a') as f:
            f.write(json.dumps(entry) + "\n")

    async def _upload_to_gdrive(self, zip_path: Path, date_folder: str = ""):
        """Upload zip file to Google Drive via rclone."""
        # Build destination path: es_backups/index_name/date/
        gdrive_folder = f"{self.config.gdrive_path}/{self.config.index_name}"
        if date_folder:
            gdrive_folder = f"{gdrive_folder}/{date_folder}"

        gdrive_dest = f"gdrive:{gdrive_folder}"

        try:
            # Ensure remote folder exists
            subprocess.run(
                [RCLONE_PATH, "mkdir", gdrive_dest],
                capture_output=True,
                timeout=60,
            )

            # Run rclone copy
            result = subprocess.run(
                [RCLONE_PATH, "copy", str(zip_path), gdrive_dest, "-v"],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode == 0:
                logger.info(f"[ESBackup] ✓ Uploaded to GDrive: {gdrive_dest}/{zip_path.name}")

                # Delete local zip if configured
                if self.config.gdrive_delete_local:
                    zip_path.unlink()
                    logger.info(f"[ESBackup] Deleted local zip after upload")
            else:
                logger.error(f"[ESBackup] GDrive upload failed: {result.stderr}")

        except subprocess.TimeoutExpired:
            logger.error(f"[ESBackup] GDrive upload timed out for {zip_path}")
        except FileNotFoundError:
            logger.error(f"[ESBackup] rclone not found at {RCLONE_PATH}")
        except Exception as e:
            logger.error(f"[ESBackup] GDrive upload error: {e}")

    async def bulk_index_with_backup(
        self,
        documents: List[Dict[str, Any]],
        es_url: str = "http://localhost:9200",
        es_user: str = "elastic",
        es_password: str = "",
    ) -> Dict[str, int]:
        """
        Bulk index documents to ES and backup to GDrive.

        This is a convenience wrapper that handles both ES indexing and backup.

        Returns:
            Dict with indexed count, failed count, and backed_up count
        """
        auth = aiohttp.BasicAuth(es_user, es_password) if es_password else None

        indexed = 0
        failed = 0

        async with aiohttp.ClientSession() as session:
            # Process in batches
            batch_size = 100  # ES bulk batch size

            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]

                # Build bulk body
                bulk_body = ""
                for doc in batch:
                    doc_id = doc.get("_id") or doc.get("id") or f"doc_{i}"
                    bulk_body += json.dumps({
                        "index": {"_index": self.config.index_name, "_id": doc_id}
                    }) + "\n"
                    bulk_body += json.dumps(doc, default=str) + "\n"

                try:
                    async with session.post(
                        f"{es_url}/_bulk",
                        data=bulk_body,
                        auth=auth,
                        headers={"Content-Type": "application/x-ndjson"},
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.json()

                            # Track successfully indexed documents for backup
                            for j, item in enumerate(result.get("items", [])):
                                if "index" in item and item["index"].get("result") in ["created", "updated"]:
                                    await self.track_document_async(batch[j], doc_id=item["index"].get("_id"))
                                    indexed += 1
                                else:
                                    failed += 1
                        else:
                            failed += len(batch)
                            logger.error(f"[ESBackup] Bulk index failed: {resp.status}")

                except Exception as e:
                    failed += len(batch)
                    logger.error(f"[ESBackup] Bulk index error: {e}")

        # Flush any remaining documents
        await self.flush()

        return {
            "indexed": indexed,
            "failed": failed,
            "backed_up": self._total_backed_up,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get backup statistics."""
        return {
            "index_name": self.config.index_name,
            "current_batch_size": len(self._current_batch),
            "batch_threshold": self.config.batch_size,
            "total_backed_up": self._total_backed_up,
            "current_batch_number": self._batch_number,
            "gdrive_enabled": self.config.gdrive_enabled,
            "gdrive_path": self.config.gdrive_path,
        }


# =============================================================================
# Global Backup Managers
# =============================================================================

# Pre-configured backup managers for common indices
_backup_managers: Dict[str, ESBackupManager] = {}


def get_backup_manager(index_name: str, **kwargs) -> ESBackupManager:
    """Get or create a backup manager for an index."""
    if index_name not in _backup_managers:
        _backup_managers[index_name] = ESBackupManager(index_name, **kwargs)
    return _backup_managers[index_name]


# Pre-configured managers for common indices
def get_onion_pages_backup() -> ESBackupManager:
    """Get backup manager for onion-pages index."""
    return get_backup_manager(
        "onion-pages",
        gdrive_path="es_backups/tor",
        batch_size=25,  # Smaller batches for potentially large page content
    )


def get_onion_graph_nodes_backup() -> ESBackupManager:
    """Get backup manager for onion graph nodes.

    CYMONIDES MANDATE: Onion graph data is now in cymonides-2 with doc_type="onion_node".
    This backs up from cymonides-2 (filtering by doc_type happens at query time).
    """
    return get_backup_manager(
        "cymonides-2",  # CYMONIDES MANDATE: Onion data migrated to C2
        gdrive_path="es_backups/tor/nodes",
        batch_size=100,
    )


def get_onion_graph_edges_backup() -> ESBackupManager:
    """Get backup manager for onion graph edges.

    CYMONIDES MANDATE: Onion graph data is now in cymonides-2 with doc_type="onion_edge".
    This backs up from cymonides-2 (filtering by doc_type happens at query time).
    """
    return get_backup_manager(
        "cymonides-2",  # CYMONIDES MANDATE: Onion data migrated to C2
        gdrive_path="es_backups/tor/edges",
        batch_size=500,
    )


def get_clearnet_pages_backup() -> ESBackupManager:
    """Get backup manager for clearnet scraped pages."""
    return get_backup_manager(
        "scraped-pages",
        gdrive_path="es_backups/clearnet",
        batch_size=25,
    )


# =============================================================================
# Utility Functions
# =============================================================================

async def backup_existing_index(
    index_name: str,
    es_url: str = "http://localhost:9200",
    es_user: str = "elastic",
    es_password: str = "",
    batch_size: int = 50,
    max_docs: Optional[int] = None,
) -> Dict[str, int]:
    """
    Backup an existing ES index to GDrive.

    Useful for backing up indices that were created before this system was in place.
    """
    auth = aiohttp.BasicAuth(es_user, es_password) if es_password else None

    backup_mgr = ESBackupManager(index_name, batch_size=batch_size)

    backed_up = 0

    async with aiohttp.ClientSession() as session:
        # Use scroll API for large indices
        scroll_id = None

        try:
            # Initial search
            async with session.post(
                f"{es_url}/{index_name}/_search?scroll=2m",
                json={"size": 100, "query": {"match_all": {}}},
                auth=auth,
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"Search failed: {resp.status}")

                result = await resp.json()
                scroll_id = result.get("_scroll_id")
                hits = result.get("hits", {}).get("hits", [])

            # Process initial batch
            for hit in hits:
                if max_docs and backed_up >= max_docs:
                    break
                await backup_mgr.track_document_async(hit["_source"], doc_id=hit["_id"])
                backed_up += 1

            # Continue scrolling
            while hits and (not max_docs or backed_up < max_docs):
                async with session.post(
                    f"{es_url}/_search/scroll",
                    json={"scroll": "2m", "scroll_id": scroll_id},
                    auth=auth,
                ) as resp:
                    if resp.status != 200:
                        break

                    result = await resp.json()
                    scroll_id = result.get("_scroll_id")
                    hits = result.get("hits", {}).get("hits", [])

                for hit in hits:
                    if max_docs and backed_up >= max_docs:
                        break
                    await backup_mgr.track_document_async(hit["_source"], doc_id=hit["_id"])
                    backed_up += 1

                logger.info(f"[ESBackup] Backed up {backed_up} documents from {index_name}")

        finally:
            # Clear scroll
            if scroll_id:
                await session.delete(
                    f"{es_url}/_search/scroll",
                    json={"scroll_id": scroll_id},
                    auth=auth,
                )

    # Flush remaining
    await backup_mgr.flush()

    return {
        "index": index_name,
        "backed_up": backed_up,
        "total_batches": backup_mgr._batch_number,
    }


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ES Content Backup Manager")
    parser.add_argument("command", choices=["backup", "stats"], help="Command to run")
    parser.add_argument("--index", required=True, help="ES index name")
    parser.add_argument("--es-url", default="http://localhost:9200", help="ES URL")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size")
    parser.add_argument("--max-docs", type=int, help="Max documents to backup")

    args = parser.parse_args()

    if args.command == "backup":
        result = asyncio.run(backup_existing_index(
            args.index,
            es_url=args.es_url,
            batch_size=args.batch_size,
            max_docs=args.max_docs,
        ))
        print(f"Backup complete: {result}")

    elif args.command == "stats":
        mgr = get_backup_manager(args.index)
        print(f"Stats: {mgr.get_stats()}")
