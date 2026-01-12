#!/usr/bin/env python3
"""
Cymonides Project Status Memory System

Tracks the state of all indexing operations:
- What is to be indexed (pending)
- What is being mapped (mapping)
- What is currently indexing (indexing)
- What is complete (complete)

JSON-based memory for persistence across sessions.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)

# Memory file location
MEMORY_DIR = Path("/data/SEARCH_ENGINEER/BACKEND/modules/cymonides/agent/memory/projects")
MEMORY_DIR.mkdir(parents=True, exist_ok=True)


class IndexTier(Enum):
    """Index tier types."""
    C1 = "c-1"  # Project indices: cymonides-1-{projectId}
    C2 = "c-2"  # Content corpus: cymonides-2
    C3 = "c-3"  # Unified indices: {entity}_unified


class TaskStatus(Enum):
    """Task status values."""
    PENDING = "pending"          # Queued but not started
    MAPPING = "mapping"          # Schema/field mapping in progress
    TESTING = "testing"          # Test indexing (100-1000 docs)
    ADJUSTING = "adjusting"      # Adjusting strategy based on test
    INDEXING = "indexing"        # Full indexing in progress
    COMPLETE = "complete"        # Successfully completed
    FAILED = "failed"            # Failed with error
    PAUSED = "paused"            # Manually paused


@dataclass
class FieldMapping:
    """Field mapping from source to target."""
    source_field: str
    target_field: str
    transform: Optional[str] = None  # Transformation to apply
    merge_strategy: str = "append"   # append, overwrite, nested
    notes: str = ""


@dataclass
class IndexingTask:
    """A single indexing task."""
    task_id: str
    tier: str                        # c-1, c-2, c-3
    source: str                      # Source file/index
    target_index: str                # Target index name
    status: str = "pending"          # TaskStatus value

    # Progress tracking
    total_docs: int = 0
    indexed_docs: int = 0
    failed_docs: int = 0

    # Field mappings (for C-3)
    field_mappings: List[Dict] = field(default_factory=list)

    # Test results
    test_batch_size: int = 1000
    test_results: Dict = field(default_factory=dict)

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Error tracking
    last_error: Optional[str] = None
    error_count: int = 0

    # Metadata
    metadata: Dict = field(default_factory=dict)


@dataclass
class C1BridgeTask:
    """Task for hooking up a module to C-1 indexing."""
    task_id: str
    module_name: str                 # e.g., "eye-d", "corporella", "alldom"
    module_path: str                 # Path to module
    output_types: List[str]          # Node types the module produces
    status: str = "pending"

    # Bridge configuration
    bridge_file: Optional[str] = None  # Path to generated bridge
    node_mappings: List[Dict] = field(default_factory=list)
    edge_mappings: List[Dict] = field(default_factory=list)

    # Validation results
    validation_passed: bool = False
    validation_errors: List[str] = field(default_factory=list)

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None


@dataclass
class ProjectMemory:
    """Memory for a single project/indexing session."""
    project_id: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Tasks by type
    c1_bridge_tasks: List[Dict] = field(default_factory=list)
    indexing_tasks: List[Dict] = field(default_factory=list)

    # Index status cache
    index_status: Dict = field(default_factory=dict)

    # Global settings
    settings: Dict = field(default_factory=dict)


class StatusTracker:
    """
    Tracks and persists indexing operation status.

    Usage:
        tracker = StatusTracker("my-project")

        # Add a new indexing task
        task = tracker.add_indexing_task(
            tier="c-3",
            source="/path/to/data.json",
            target_index="domains_unified"
        )

        # Update status
        tracker.update_task_status(task.task_id, "mapping")

        # Get current status
        status = tracker.get_project_status()
    """

    def __init__(self, project_id: str = "default"):
        self.project_id = project_id
        self.memory_file = MEMORY_DIR / f"{project_id}.json"
        self.memory = self._load_memory()

    def _load_memory(self) -> ProjectMemory:
        """Load memory from disk or create new."""
        if self.memory_file.exists():
            try:
                with open(self.memory_file) as f:
                    data = json.load(f)
                return ProjectMemory(**data)
            except Exception as e:
                logger.error(f"Failed to load memory: {e}")

        return ProjectMemory(project_id=self.project_id)

    def _save_memory(self):
        """Save memory to disk."""
        self.memory.updated_at = datetime.utcnow().isoformat()
        with open(self.memory_file, 'w') as f:
            json.dump(asdict(self.memory), f, indent=2)

    # =========================================================================
    # C-1 BRIDGE TASKS
    # =========================================================================

    def add_c1_bridge_task(
        self,
        module_name: str,
        module_path: str,
        output_types: List[str]
    ) -> C1BridgeTask:
        """Add a new C-1 bridge hookup task."""
        task = C1BridgeTask(
            task_id=f"c1-bridge-{module_name}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            module_name=module_name,
            module_path=module_path,
            output_types=output_types
        )
        self.memory.c1_bridge_tasks.append(asdict(task))
        self._save_memory()
        return task

    def get_c1_bridge_tasks(self, status: Optional[str] = None) -> List[Dict]:
        """Get C-1 bridge tasks, optionally filtered by status."""
        tasks = self.memory.c1_bridge_tasks
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        return tasks

    def update_c1_bridge_task(self, task_id: str, updates: Dict):
        """Update a C-1 bridge task."""
        for i, task in enumerate(self.memory.c1_bridge_tasks):
            if task.get("task_id") == task_id:
                self.memory.c1_bridge_tasks[i].update(updates)
                self._save_memory()
                return
        raise ValueError(f"Task not found: {task_id}")

    # =========================================================================
    # INDEXING TASKS
    # =========================================================================

    def add_indexing_task(
        self,
        tier: str,
        source: str,
        target_index: str,
        total_docs: int = 0,
        metadata: Dict = None
    ) -> IndexingTask:
        """Add a new indexing task."""
        task = IndexingTask(
            task_id=f"idx-{tier}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            tier=tier,
            source=source,
            target_index=target_index,
            total_docs=total_docs,
            metadata=metadata or {}
        )
        self.memory.indexing_tasks.append(asdict(task))
        self._save_memory()
        return task

    def get_indexing_tasks(
        self,
        tier: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict]:
        """Get indexing tasks, optionally filtered."""
        tasks = self.memory.indexing_tasks
        if tier:
            tasks = [t for t in tasks if t.get("tier") == tier]
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        return tasks

    def update_indexing_task(self, task_id: str, updates: Dict):
        """Update an indexing task."""
        for i, task in enumerate(self.memory.indexing_tasks):
            if task.get("task_id") == task_id:
                self.memory.indexing_tasks[i].update(updates)
                self._save_memory()
                return
        raise ValueError(f"Task not found: {task_id}")

    def update_task_progress(
        self,
        task_id: str,
        indexed_docs: int,
        failed_docs: int = 0
    ):
        """Update task progress counts."""
        self.update_indexing_task(task_id, {
            "indexed_docs": indexed_docs,
            "failed_docs": failed_docs
        })

    def set_task_status(
        self,
        task_id: str,
        status: str,
        error: Optional[str] = None
    ):
        """Set task status with optional error."""
        updates = {"status": status}

        if status == "indexing" and not self._get_task(task_id).get("started_at"):
            updates["started_at"] = datetime.utcnow().isoformat()
        elif status in ("complete", "failed"):
            updates["completed_at"] = datetime.utcnow().isoformat()

        if error:
            updates["last_error"] = error
            task = self._get_task(task_id)
            updates["error_count"] = task.get("error_count", 0) + 1

        self.update_indexing_task(task_id, updates)

    def _get_task(self, task_id: str) -> Optional[Dict]:
        """Get a task by ID."""
        for task in self.memory.indexing_tasks:
            if task.get("task_id") == task_id:
                return task
        for task in self.memory.c1_bridge_tasks:
            if task.get("task_id") == task_id:
                return task
        return None

    # =========================================================================
    # FIELD MAPPINGS (C-3)
    # =========================================================================

    def add_field_mapping(
        self,
        task_id: str,
        source_field: str,
        target_field: str,
        transform: Optional[str] = None,
        merge_strategy: str = "append"
    ):
        """Add a field mapping to a task."""
        mapping = FieldMapping(
            source_field=source_field,
            target_field=target_field,
            transform=transform,
            merge_strategy=merge_strategy
        )

        for i, task in enumerate(self.memory.indexing_tasks):
            if task.get("task_id") == task_id:
                if "field_mappings" not in task:
                    task["field_mappings"] = []
                task["field_mappings"].append(asdict(mapping))
                self._save_memory()
                return
        raise ValueError(f"Task not found: {task_id}")

    # =========================================================================
    # TEST RESULTS
    # =========================================================================

    def record_test_results(
        self,
        task_id: str,
        batch_size: int,
        success_count: int,
        error_count: int,
        sample_docs: List[Dict] = None,
        issues: List[str] = None
    ):
        """Record test batch results."""
        test_results = {
            "batch_size": batch_size,
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": success_count / batch_size if batch_size > 0 else 0,
            "tested_at": datetime.utcnow().isoformat(),
            "sample_docs": sample_docs or [],
            "issues": issues or []
        }

        self.update_indexing_task(task_id, {"test_results": test_results})

    # =========================================================================
    # INDEX STATUS
    # =========================================================================

    def cache_index_status(self, index_name: str, status: Dict):
        """Cache current status of an index."""
        self.memory.index_status[index_name] = {
            **status,
            "cached_at": datetime.utcnow().isoformat()
        }
        self._save_memory()

    def get_cached_index_status(self, index_name: str) -> Optional[Dict]:
        """Get cached index status."""
        return self.memory.index_status.get(index_name)

    # =========================================================================
    # PROJECT STATUS SUMMARY
    # =========================================================================

    def get_project_status(self) -> Dict:
        """Get comprehensive project status summary."""
        indexing_tasks = self.memory.indexing_tasks
        bridge_tasks = self.memory.c1_bridge_tasks

        # Count by status
        indexing_by_status = {}
        for task in indexing_tasks:
            status = task.get("status", "unknown")
            indexing_by_status[status] = indexing_by_status.get(status, 0) + 1

        bridge_by_status = {}
        for task in bridge_tasks:
            status = task.get("status", "unknown")
            bridge_by_status[status] = bridge_by_status.get(status, 0) + 1

        # Count by tier
        indexing_by_tier = {}
        for task in indexing_tasks:
            tier = task.get("tier", "unknown")
            indexing_by_tier[tier] = indexing_by_tier.get(tier, 0) + 1

        return {
            "project_id": self.project_id,
            "updated_at": self.memory.updated_at,
            "indexing_tasks": {
                "total": len(indexing_tasks),
                "by_status": indexing_by_status,
                "by_tier": indexing_by_tier,
                "in_progress": [t for t in indexing_tasks if t.get("status") in ("mapping", "testing", "indexing")],
                "recent_complete": [t for t in indexing_tasks if t.get("status") == "complete"][-5:]
            },
            "c1_bridge_tasks": {
                "total": len(bridge_tasks),
                "by_status": bridge_by_status,
                "pending": [t for t in bridge_tasks if t.get("status") == "pending"]
            },
            "index_cache": list(self.memory.index_status.keys())
        }

    def get_pending_work(self) -> Dict:
        """Get all pending work that needs attention."""
        return {
            "pending_indexing": self.get_indexing_tasks(status="pending"),
            "pending_bridges": self.get_c1_bridge_tasks(status="pending"),
            "testing_indexing": self.get_indexing_tasks(status="testing"),
            "adjusting_indexing": self.get_indexing_tasks(status="adjusting"),
            "failed_tasks": [
                *self.get_indexing_tasks(status="failed"),
                *self.get_c1_bridge_tasks(status="failed")
            ]
        }

    # =========================================================================
    # POLLING / HOOKS
    # =========================================================================

    def get_tasks_for_poll(self) -> List[Dict]:
        """Get tasks that should be polled for completion."""
        return [
            t for t in self.memory.indexing_tasks
            if t.get("status") in ("indexing", "testing")
        ]

    def mark_completion_acknowledged(self, task_id: str):
        """Mark that a completion has been acknowledged/processed."""
        self.update_indexing_task(task_id, {
            "completion_acknowledged": True,
            "acknowledged_at": datetime.utcnow().isoformat()
        })


# Convenience functions
def get_tracker(project_id: str = "default") -> StatusTracker:
    """Get a status tracker for a project."""
    return StatusTracker(project_id)


def list_projects() -> List[str]:
    """List all projects with memory files."""
    return [p.stem for p in MEMORY_DIR.glob("*.json")]
