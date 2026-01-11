#!/usr/bin/env python3
"""
EDITH Bridge for SASTRE

Async bridge to the EDITH skills pipeline. Uses subprocess execution
to call route.py, compose.py, and validate.py.

CRITICAL: All calls are async using asyncio.create_subprocess_exec.
The ThinOrchestrator is async; blocking calls would freeze the orchestrator.

Usage:
    from SASTRE.bridges.edith_bridge import EdithBridge

    bridge = EdithBridge()

    # Route a query
    routing = await bridge.route_investigation("DD on UK company Test Ltd")

    # Compose templates
    context = await bridge.compose_context("uk", "company_dd", "Test Ltd")

    # Validate output
    result = await bridge.validate_output(content, "uk")
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Optional, List, Any

logger = logging.getLogger(__name__)

# EDITH scripts location (try repo-local first, then user-installed)
_REPO_ROOT = Path(__file__).resolve().parents[2]
# Try standard location
_REPO_SCRIPTS = _REPO_ROOT / "EDITH" / "templates" / "scripts"
if not _REPO_SCRIPTS.exists():
    # Try new NARRATIVE location
    _REPO_SCRIPTS = Path("/data/CLASSES/NARRATIVE/EDITH/templates/scripts")

_ENV_ROOTS = [
    os.getenv("EDITH_TEMPLATES_DIR"),
    os.getenv("EDITH_TEMPLATES_ROOT"),
    os.getenv("SASTRE_TEMPLATES_DIR"),
]


def _find_edith_scripts_dir() -> Path:
    candidates: List[Path] = []

    for root in (p for p in _ENV_ROOTS if p):
        root_path = Path(root).expanduser()
        candidates.append(root_path)
        candidates.append(root_path / "scripts")

    candidates.extend([
        _REPO_SCRIPTS,
        Path.home() / ".claude" / "skills" / "edith-templates" / "scripts",
        Path("/Users/attic/01. DRILL_SEARCH/drill-search-app/.claude/skills/edith-templates/scripts"),
    ])

    for candidate in candidates:
        try:
            if (candidate / "route.py").exists() and (candidate / "compose.py").exists():
                return candidate
        except Exception:
            continue

    # Last resort: return the repo path even if missing, to make warnings informative
    return _REPO_SCRIPTS


EDITH_SCRIPTS = _find_edith_scripts_dir()


class EdithBridgeError(Exception):
    """Error from EDITH bridge operations."""
    pass


class EdithBridge:
    """
    Async bridge to EDITH skills pipeline.

    Provides non-blocking access to:
    - route.py: Deterministic query routing
    - compose.py: Template compilation
    - validate.py: QC guardrails
    """

    def __init__(self, timeout_seconds: int = 30):
        """
        Initialize EDITH bridge.

        Args:
            timeout_seconds: Max time for subprocess execution
        """
        self.timeout = timeout_seconds
        self.scripts_dir = EDITH_SCRIPTS

        # Verify scripts exist
        if not self.scripts_dir.exists():
            logger.warning(f"EDITH scripts directory not found: {self.scripts_dir}")

    async def _run_script(
        self,
        script: str,
        *args,
        stdin: Optional[str] = None
    ) -> Dict:
        """
        Run EDITH script asynchronously (non-blocking).

        Args:
            script: Script name (e.g., "route.py")
            *args: Command line arguments
            stdin: Optional stdin input

        Returns:
            Parsed JSON output from script

        Raises:
            EdithBridgeError: If script fails or times out
        """
        script_path = self.scripts_dir / script

        if not script_path.exists():
            raise EdithBridgeError(f"EDITH script not found: {script_path}")

        cmd = [sys.executable, str(script_path)] + list(args)

        logger.debug(f"Running EDITH script: {' '.join(cmd)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.scripts_dir)  # Run from scripts dir
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin.encode() if stdin else None),
                timeout=self.timeout
            )

            if proc.returncode != 0:
                error_msg = stderr.decode().strip() if stderr else "Unknown error"
                raise EdithBridgeError(f"EDITH {script} failed (exit {proc.returncode}): {error_msg}")

            # Parse JSON output
            output = stdout.decode().strip()
            if not output:
                return {}

            try:
                return json.loads(output)
            except json.JSONDecodeError as e:
                # Return raw output if not JSON
                return {"raw_output": output, "parse_error": str(e)}

        except asyncio.TimeoutError:
            raise EdithBridgeError(f"EDITH {script} timed out after {self.timeout}s")
        except Exception as e:
            raise EdithBridgeError(f"EDITH {script} error: {e}")

    async def route_investigation(self, query: str) -> Dict:
        """
        Route an investigation query to jurisdiction/genre/section.

        Args:
            query: Natural language query (e.g., "DD on UK company Test Ltd")

        Returns:
            Dict with routing result:
            {
                "status": "exact" | "ambiguous" | "missing",
                "jurisdiction_id": "uk",
                "genre_id": "company_dd",
                "entity_detected": true,
                "entity_name": "Test Ltd",
                "dead_end_warnings": [...],  # If any
                "confidence_reason": "..."
            }
        """
        result = await self._run_script("route.py", query)

        # Log dead-end warnings if present
        warnings = result.get("dead_end_warnings", [])
        for warning in warnings:
            logger.warning(
                f"Dead-end: {warning.get('action')} - {warning.get('reason')}"
            )

        return result

    async def compose_context(
        self,
        jurisdiction: str,
        genre: str,
        entity: str,
        section: Optional[str] = None,
        strict_mode: bool = False
    ) -> Dict:
        """
        Compose template context for an investigation.

        Stacks jurisdiction + genre + sections into compiled context
        with ALLOWED_ACTIONS and arbitrage routes.

        Args:
            jurisdiction: Jurisdiction code (e.g., "uk")
            genre: Genre ID (e.g., "company_dd")
            entity: Entity name
            section: Optional single section (default: full DD)
            strict_mode: If True, remove dead-end actions

        Returns:
            Dict with compiled context:
            {
                "status": "success",
                "mode": "FULL_DD" | "SINGLE_SECTION",
                "jurisdiction": "uk",
                "genre": "company_dd",
                "entity": "Test Ltd",
                "allowed_actions": ["SEARCH_REGISTRY", ...],
                "dd_sections": [...],
                "compiled_context": "...",
                "arbitrage_routes": [...]  # If available
            }
        """
        args = [
            "--jurisdiction", jurisdiction,
            "--genre", genre,
            "--entity", entity,
            "--json"
        ]

        if section:
            args.extend(["--section", section])

        if strict_mode:
            args.append("--strict")

        return await self._run_script("compose.py", *args)

    async def validate_output(
        self,
        content: str,
        jurisdiction: str,
        strict: bool = False
    ) -> Dict:
        """
        Validate generated content against QC rules.

        Runs 14 validation checks including:
        - No invented registries
        - Footnote format compliance
        - Certainty calibration
        - Dead-end citation detection
        - Arbitrage opportunity suggestions

        Args:
            content: Generated content to validate
            jurisdiction: Jurisdiction code
            strict: If True, warnings also cause failure

        Returns:
            Dict with validation result:
            {
                "status": "PASS" | "FAIL",
                "jurisdiction": "UK",
                "checks_run": 14,
                "checks_passed": 14,
                "checks_failed": 0,
                "failures": [...],
                "manifest_hash": "..."
            }
        """
        args = ["--jurisdiction", jurisdiction, "--json"]
        if strict:
            args.append("--strict")

        return await self._run_script("validate.py", *args, stdin=content)

    async def get_dead_ends(self, jurisdiction: str) -> Dict:
        """
        Get dead-end patterns for a jurisdiction.

        Args:
            jurisdiction: Jurisdiction code

        Returns:
            Dict mapping action to dead-end info
        """
        # Use Python import directly for this
        try:
            sys.path.insert(0, str(self.scripts_dir))
            from dead_ends_loader import get_dead_ends_for_jurisdiction
            return get_dead_ends_for_jurisdiction(jurisdiction)
        except ImportError:
            return {}
        finally:
            if str(self.scripts_dir) in sys.path:
                sys.path.remove(str(self.scripts_dir))

    async def get_arbitrage_routes(
        self,
        jurisdiction: str,
        direction: str = "both"
    ) -> Dict:
        """
        Get arbitrage routes for a jurisdiction.

        Args:
            jurisdiction: Jurisdiction code
            direction: "outbound", "inbound", or "both"

        Returns:
            Dict with arbitrage routes
        """
        try:
            sys.path.insert(0, str(self.scripts_dir))
            from arbitrage_loader import (
                get_arbitrage_for_jurisdiction,
                get_arbitrage_to_target
            )

            result = {}
            if direction in ("outbound", "both"):
                result["outbound"] = get_arbitrage_for_jurisdiction(jurisdiction)
            if direction in ("inbound", "both"):
                result["inbound"] = get_arbitrage_to_target(jurisdiction)

            return result
        except ImportError:
            return {}
        finally:
            if str(self.scripts_dir) in sys.path:
                sys.path.remove(str(self.scripts_dir))

    async def full_pipeline(
        self,
        query: str,
        content_generator: Optional[Any] = None
    ) -> Dict:
        """
        Run full EDITH pipeline: route → compose → [generate] → validate.

        Args:
            query: Natural language query
            content_generator: Optional async callable to generate content
                              If None, returns context without validation

        Returns:
            Dict with full pipeline result
        """
        # Phase 1: Route
        routing = await self.route_investigation(query)

        if routing.get("status") == "missing":
            return {
                "status": "error",
                "phase": "routing",
                "error": "No template coverage for query",
                "routing": routing
            }

        if routing.get("status") == "ambiguous":
            return {
                "status": "ambiguous",
                "phase": "routing",
                "message": "Jurisdiction ambiguous - clarification needed",
                "routing": routing
            }

        # Phase 2: Compose
        context = await self.compose_context(
            jurisdiction=routing["jurisdiction_id"],
            genre=routing["genre_id"],
            entity=routing.get("entity_name", "Unknown")
        )

        if context.get("status") != "success":
            return {
                "status": "error",
                "phase": "compose",
                "error": "Template compilation failed",
                "routing": routing,
                "context": context
            }

        # Phase 3: Generate (if generator provided)
        if content_generator:
            try:
                content = await content_generator(context)
            except Exception as e:
                return {
                    "status": "error",
                    "phase": "generation",
                    "error": str(e),
                    "routing": routing,
                    "context": context
                }

            # Phase 4: Validate
            validation = await self.validate_output(
                content,
                routing["jurisdiction_id"]
            )

            return {
                "status": "success" if validation["status"] == "PASS" else "validation_failed",
                "routing": routing,
                "context": context,
                "content": content,
                "validation": validation
            }

        # No generator - return context only
        return {
            "status": "context_ready",
            "routing": routing,
            "context": context
        }


# Convenience functions for direct import
async def route_query(query: str) -> Dict:
    """Quick route function."""
    bridge = EdithBridge()
    return await bridge.route_investigation(query)


async def compose_template(
    jurisdiction: str,
    genre: str,
    entity: str
) -> Dict:
    """Quick compose function."""
    bridge = EdithBridge()
    return await bridge.compose_context(jurisdiction, genre, entity)


async def validate_content(content: str, jurisdiction: str) -> Dict:
    """Quick validate function."""
    bridge = EdithBridge()
    return await bridge.validate_output(content, jurisdiction)


# CLI for testing
if __name__ == "__main__":
    import argparse

    async def main():
        parser = argparse.ArgumentParser(description="EDITH Bridge CLI")
        parser.add_argument("--route", help="Route a query")
        parser.add_argument("--compose", nargs=3, metavar=("JUR", "GENRE", "ENTITY"),
                          help="Compose template")
        parser.add_argument("--validate", help="Validate content file")
        parser.add_argument("--jurisdiction", "-j", help="Jurisdiction for validation")

        args = parser.parse_args()
        bridge = EdithBridge()

        if args.route:
            result = await bridge.route_investigation(args.route)
            print(json.dumps(result, indent=2))

        elif args.compose:
            jur, genre, entity = args.compose
            result = await bridge.compose_context(jur, genre, entity)
            print(json.dumps(result, indent=2))

        elif args.validate and args.jurisdiction:
            content = Path(args.validate).read_text()
            result = await bridge.validate_output(content, args.jurisdiction)
            print(json.dumps(result, indent=2))

        else:
            parser.print_help()

    asyncio.run(main())
