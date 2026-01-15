#!/usr/bin/env python3
"""
Cymonides AI Agent - Main Orchestrator

An intelligent agent for Cymonides indexing operations that:
1. Routes tasks to appropriate subagents (C-1 Bridge Builder, C-3 Dataset Indexer)
2. Maintains persistent memory of all indexing operations
3. Implements completion hooks and polling for async operations
4. Provides status visibility at any point

Two Main Tasks:
1. Hook up modules to C-1 indexing (C1BridgeBuilder)
2. Index datasets to C-3 unified indices (C3DatasetIndexer)

THE HOLY RULE (for C-3): Preserve ABSOLUTELY EVERYTHING from each dataset.

Usage:
    # CLI mode
    python3 main.py status                           # Get overall status
    python3 main.py hookup /path/to/module           # Hook up module to C-1
    python3 main.py index /path/to/dataset           # Index dataset to C-3
    python3 main.py poll                             # Check for completed tasks

    # Programmatic mode
    from cymonides_agent import CymonicesAgent

    agent = CymonicesAgent(project_id="my-project")
    agent.hookup_module("/path/to/module")
    agent.index_dataset("/path/to/dataset")
    agent.get_status()
"""

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

# Local imports
from subagents import C1BridgeBuilder, C3DatasetIndexer
from memory import StatusTracker, get_tracker, list_projects
from config import (
    INDEX_TIERS,
    NODE_CLASSES,
    CANONICAL_PATHS,
    C3_TEST_PROTOCOL,
)

logger = logging.getLogger(__name__)


# ============================================================================
# COMPLETION HOOKS
# ============================================================================

@dataclass
class CompletionHook:
    """Hook to execute when a task completes."""
    task_id: str
    callback: Optional[Callable] = None
    notify_channel: Optional[str] = None  # webhook URL, email, etc.
    metadata: Dict = field(default_factory=dict)


class CompletionMonitor:
    """
    Monitors indexing tasks for completion and triggers hooks.

    Can run in polling mode or be triggered by external events.
    """

    def __init__(self, tracker: StatusTracker):
        self.tracker = tracker
        self.hooks: Dict[str, CompletionHook] = {}
        self._running = False

    def register_hook(self, hook: CompletionHook):
        """Register a completion hook for a task."""
        self.hooks[hook.task_id] = hook
        logger.info(f"Registered completion hook for task: {hook.task_id}")

    def unregister_hook(self, task_id: str):
        """Remove a completion hook."""
        self.hooks.pop(task_id, None)

    def check_completions(self) -> List[Dict]:
        """
        Check for completed tasks and trigger hooks.

        Returns:
            List of completed tasks that were processed
        """
        completed = []

        # Get tasks that might have completed
        tasks = self.tracker.get_tasks_for_poll()

        for task in tasks:
            task_id = task.get("task_id")
            status = task.get("status")

            # Check if task is now complete
            if status in ("complete", "failed"):
                completed.append(task)

                # Trigger hook if registered
                if task_id in self.hooks:
                    hook = self.hooks[task_id]
                    self._trigger_hook(hook, task)

                # Mark as acknowledged
                if not task.get("completion_acknowledged"):
                    self.tracker.mark_completion_acknowledged(task_id)

        return completed

    def _trigger_hook(self, hook: CompletionHook, task: Dict):
        """Execute a completion hook."""
        logger.info(f"Triggering completion hook for task: {hook.task_id}")

        # Execute callback if provided
        if hook.callback:
            try:
                hook.callback(task)
            except Exception as e:
                logger.error(f"Hook callback error: {e}")

        # Send notification if channel configured
        if hook.notify_channel:
            self._send_notification(hook.notify_channel, task)

        # Remove hook after triggering
        self.unregister_hook(hook.task_id)

    def _send_notification(self, channel: str, task: Dict):
        """Send notification to a channel (webhook, etc.)."""
        # Placeholder for notification logic
        # Could be expanded to support webhooks, email, Slack, etc.
        logger.info(f"Would notify {channel} about task: {task.get('task_id')}")

    def start_polling(self, interval_seconds: int = 60):
        """Start polling for completions in background."""
        self._running = True
        logger.info(f"Starting completion polling (interval: {interval_seconds}s)")

        while self._running:
            try:
                completed = self.check_completions()
                if completed:
                    logger.info(f"Processed {len(completed)} completed tasks")
            except Exception as e:
                logger.error(f"Polling error: {e}")

            time.sleep(interval_seconds)

    def stop_polling(self):
        """Stop the polling loop."""
        self._running = False


# ============================================================================
# MAIN AGENT
# ============================================================================

class CymonicesAgent:
    """
    Main Cymonices AI Agent.

    Routes tasks to appropriate subagents and maintains project memory.

    Index Tiers:
    - C-1: cymonides-1-{projectId} - Project graphs with nodes and embedded edges
    - C-2: cymonides-2 - Content corpus from scraped websites
    - C-3: {entity}_unified - Consolidated multi-source entity indices

    Subagents:
    - C1BridgeBuilder: Hooks up modules to C-1 indexing
    - C3DatasetIndexer: Indexes datasets to C-3 unified indices
    """

    def __init__(
        self,
        project_id: str = "default",
        es_host: str = "http://localhost:9200"
    ):
        self.project_id = project_id
        self.es_host = es_host

        # Initialize components
        self.tracker = StatusTracker(project_id)
        self.completion_monitor = CompletionMonitor(self.tracker)

        # Initialize subagents (lazy)
        self._c1_builder = None
        self._c3_indexer = None

    @property
    def c1_builder(self) -> C1BridgeBuilder:
        """Lazy load C1 Bridge Builder."""
        if self._c1_builder is None:
            self._c1_builder = C1BridgeBuilder(self.project_id)
        return self._c1_builder

    @property
    def c3_indexer(self) -> C3DatasetIndexer:
        """Lazy load C3 Dataset Indexer."""
        if self._c3_indexer is None:
            self._c3_indexer = C3DatasetIndexer(self.project_id, self.es_host)
        return self._c3_indexer

    # =========================================================================
    # TASK 1: Hook up modules to C-1
    # =========================================================================

    def hookup_module(
        self,
        module_path: str,
        output_path: Optional[str] = None,
        auto_generate: bool = True
    ) -> Dict[str, Any]:
        """
        Hook up a module with node creation to C-1 indexing.

        This analyzes the module to discover its output types and generates
        a C1 bridge file that formats and indexes the module's output.

        Args:
            module_path: Path to the module to hook up
            output_path: Where to save generated bridge (optional)
            auto_generate: Generate bridge code automatically

        Returns:
            Dict with analysis and generation results
        """
        logger.info(f"Hooking up module: {module_path}")

        # Analyze the module
        analysis = self.c1_builder.analyze_module(module_path)

        result = {
            "status": "analyzed",
            "module": analysis.module_name,
            "output_types": analysis.output_types,
            "edge_types": analysis.edge_types,
            "has_existing_bridge": analysis.has_existing_bridge,
            "recommended_mappings": analysis.recommended_mappings,
            "warnings": analysis.warnings,
        }

        if analysis.has_existing_bridge:
            result["existing_bridge"] = analysis.existing_bridge_path
            result["message"] = "Module already has a C1 bridge. Review or regenerate."

        if auto_generate:
            # Generate bridge code
            bridge_code = self.c1_builder.generate_bridge(analysis)

            # Validate
            validation = self.c1_builder.validate_bridge(bridge_code)
            result["validation"] = validation

            if validation["valid"]:
                # Save if output path provided
                if output_path:
                    saved_path = self.c1_builder.save_bridge(bridge_code, output_path)
                    result["bridge_saved"] = saved_path
                    result["status"] = "generated"
                else:
                    result["bridge_code_preview"] = bridge_code[:2000]
                    result["status"] = "generated_not_saved"
                    result["message"] = "Bridge code generated. Provide output_path to save."
            else:
                result["status"] = "validation_failed"
                result["errors"] = validation["errors"]

        return result

    # =========================================================================
    # TASK 2: Index datasets to C-3
    # =========================================================================

    def index_dataset(
        self,
        dataset_path: str,
        source_name: Optional[str] = None,
        test_only: bool = False,
        test_size: int = 1000,
        auto_proceed: bool = False,
        on_complete: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Index a dataset to the appropriate C-3 unified index.

        THE HOLY RULE: Preserve ABSOLUTELY EVERYTHING from the dataset.

        Test Protocol:
        1. Analyze dataset structure
        2. Test batch (100-1000 records)
        3. Review results (success rate, mappings)
        4. Full indexing if approved

        Args:
            dataset_path: Path to dataset file or ES index
            source_name: Name for source attribution
            test_only: Only run test batch, don't proceed to full
            test_size: Number of records for test batch
            auto_proceed: Automatically proceed to full if test passes
            on_complete: Callback when indexing completes

        Returns:
            Dict with analysis, test results, and indexing status
        """
        logger.info(f"Indexing dataset: {dataset_path}")

        result = {"status": "analyzing"}

        # Phase 1: Analyze
        analysis = self.c3_indexer.analyze_dataset(
            dataset_path,
            source_name=source_name
        )

        result.update({
            "dataset": analysis.dataset_name,
            "format": analysis.format,
            "total_records": analysis.total_records,
            "entity_type": analysis.detected_entity_type,
            "target_index": analysis.target_index,
            "confidence": analysis.confidence,
            "field_mappings": analysis.field_mappings,
            "unmapped_fields_preserved": len(analysis.unmapped_fields),
            "recommendations": analysis.recommendations,
            "warnings": analysis.warnings,
        })

        if analysis.confidence < 0.3:
            result["status"] = "low_confidence"
            result["message"] = "Low confidence in entity detection. Manual review required."
            return result

        # Phase 2: Test batch
        logger.info(f"Running test batch ({test_size} records)...")
        test_result = self.c3_indexer.index_test_batch(analysis, batch_size=test_size)

        result["test_result"] = {
            "success_rate": test_result.success_rate,
            "success_count": test_result.success_count,
            "error_count": test_result.error_count,
            "issues": test_result.issues,
            "sample_doc": test_result.sample_docs[0] if test_result.sample_docs else None,
        }

        if test_result.success_rate < 0.95:
            result["status"] = "test_issues"
            result["message"] = f"Test success rate {test_result.success_rate:.0%} below 95%. Review issues."
            result["adjustments_needed"] = test_result.adjustments_needed
            return result

        result["status"] = "test_passed"

        if test_only:
            result["message"] = "Test passed. Run with auto_proceed=True for full indexing."
            return result

        if not auto_proceed:
            result["message"] = "Test passed. Awaiting approval for full indexing."
            return result

        # Phase 4: Full indexing
        logger.info("Test passed. Proceeding with full indexing...")

        # Register completion hook if callback provided
        if on_complete:
            task = self.tracker.get_indexing_tasks(tier="c-3")
            for t in task:
                if t.get("source") == analysis.dataset_path:
                    hook = CompletionHook(
                        task_id=t["task_id"],
                        callback=on_complete
                    )
                    self.completion_monitor.register_hook(hook)
                    break

        indexing_result = self.c3_indexer.index_full(analysis)

        result["status"] = "complete" if indexing_result.success_rate > 0.95 else "completed_with_errors"
        result["indexing_result"] = {
            "indexed": indexing_result.indexed_docs,
            "failed": indexing_result.failed_docs,
            "success_rate": indexing_result.success_rate,
            "duration_seconds": indexing_result.duration_seconds,
            "unique_entities": indexing_result.unique_entities,
        }

        return result

    # =========================================================================
    # STATUS & MONITORING
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive status of all indexing operations.

        Returns project status including:
        - Pending tasks
        - In-progress tasks
        - Recently completed tasks
        - Index statistics
        """
        return self.tracker.get_project_status()

    def get_pending_work(self) -> Dict[str, Any]:
        """Get all pending work that needs attention."""
        return self.tracker.get_pending_work()

    def poll_completions(self) -> List[Dict]:
        """
        Check for completed tasks and process hooks.

        Call this periodically if not running continuous polling.
        """
        return self.completion_monitor.check_completions()

    def start_background_monitoring(self, interval_seconds: int = 60):
        """Start background polling for task completions."""
        import threading
        thread = threading.Thread(
            target=self.completion_monitor.start_polling,
            args=(interval_seconds,),
            daemon=True
        )
        thread.start()
        logger.info("Background monitoring started")

    def stop_background_monitoring(self):
        """Stop background polling."""
        self.completion_monitor.stop_polling()

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    def list_unified_indices(self) -> List[str]:
        """List all C-3 unified indices."""
        return INDEX_TIERS["c-3"]["unified_indices"]

    def list_node_classes(self) -> Dict:
        """List all node classes and their types."""
        return NODE_CLASSES

    def get_canonical_paths(self) -> Dict:
        """Get paths to canonical data files."""
        return CANONICAL_PATHS

    def switch_project(self, project_id: str):
        """Switch to a different project context."""
        self.project_id = project_id
        self.tracker = StatusTracker(project_id)
        self.completion_monitor = CompletionMonitor(self.tracker)
        self._c1_builder = None
        self._c3_indexer = None
        logger.info(f"Switched to project: {project_id}")

    @staticmethod
    def list_all_projects() -> List[str]:
        """List all projects with memory files."""
        return list_projects()


# ============================================================================
# CLI
# ============================================================================

def main():
    """CLI entry point."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(
        description="Cymonices AI Agent - Intelligent Indexing Operations"
    )
    parser.add_argument("--project", "-p", default="default", help="Project ID")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Status command
    status_parser = subparsers.add_parser("status", help="Get project status")
    status_parser.add_argument("--pending", action="store_true", help="Show only pending work")

    # Hookup command
    hookup_parser = subparsers.add_parser("hookup", help="Hook up module to C-1")
    hookup_parser.add_argument("module_path", help="Path to module")
    hookup_parser.add_argument("--output", "-o", help="Output path for bridge")
    hookup_parser.add_argument("--no-generate", action="store_true", help="Analyze only")

    # Index command
    index_parser = subparsers.add_parser("index", help="Index dataset to C-3")
    index_parser.add_argument("dataset_path", help="Path to dataset")
    index_parser.add_argument("--source", "-s", help="Source name")
    index_parser.add_argument("--test-only", action="store_true", help="Test batch only")
    index_parser.add_argument("--test-size", type=int, default=1000, help="Test batch size")
    index_parser.add_argument("--auto", action="store_true", help="Auto-proceed if test passes")

    # Poll command
    poll_parser = subparsers.add_parser("poll", help="Check for completed tasks")
    poll_parser.add_argument("--continuous", action="store_true", help="Continuous polling")
    poll_parser.add_argument("--interval", type=int, default=60, help="Polling interval (seconds)")

    # Projects command
    projects_parser = subparsers.add_parser("projects", help="List all projects")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    agent = CymonicesAgent(project_id=args.project)

    if args.command == "status":
        if args.pending:
            status = agent.get_pending_work()
        else:
            status = agent.get_status()
        print(json.dumps(status, indent=2, default=str))

    elif args.command == "hookup":
        result = agent.hookup_module(
            args.module_path,
            output_path=args.output,
            auto_generate=not args.no_generate
        )
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "index":
        result = agent.index_dataset(
            args.dataset_path,
            source_name=args.source,
            test_only=args.test_only,
            test_size=args.test_size,
            auto_proceed=args.auto
        )
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "poll":
        if args.continuous:
            print(f"Starting continuous polling (interval: {args.interval}s)")
            print("Press Ctrl+C to stop")
            agent.completion_monitor.start_polling(args.interval)
        else:
            completed = agent.poll_completions()
            if completed:
                print(f"Processed {len(completed)} completed tasks:")
                for task in completed:
                    print(f"  - {task.get('task_id')}: {task.get('status')}")
            else:
                print("No completed tasks to process")

    elif args.command == "projects":
        projects = CymonicesAgent.list_all_projects()
        print("Projects:")
        for p in projects:
            print(f"  - {p}")


if __name__ == "__main__":
    main()
