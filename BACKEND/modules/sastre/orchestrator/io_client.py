"""
SASTRE IO Client - Direct Integration with IO Matrix

This module provides DIRECT integration with the IO Matrix system,
bypassing HTTP and calling the IOExecutor and IORouter directly.

Usage:
    from SASTRE.orchestrator.io_client import IOClient, parse_prefix_query

    client = IOClient()

    # Execute a prefix query
    result = await client.execute("p: John Smith")
    result = await client.execute("c: Acme Corp", jurisdiction="US")
    result = await client.execute("e: john@acme.com")

    # Or parse first, then execute
    entity_type, value = parse_prefix_query("p: John Smith")
    result = await client.execute_entity(entity_type, value)
"""

import os
import sys
import re
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# Path to IO Matrix (repo layout can vary; prefer /data/INPUT_OUTPUT/matrix)
_DATA_ROOT = Path(__file__).resolve().parents[2]
_MATRIX_CANDIDATES = [
    _DATA_ROOT / "INPUT_OUTPUT" / "matrix",
    _DATA_ROOT / "SEARCH_ENGINEER" / "input_output" / "matrix",
]
IO_MATRIX_DIR = next((p for p in _MATRIX_CANDIDATES if p.exists()), _MATRIX_CANDIDATES[0])

# Add to path if needed
if str(IO_MATRIX_DIR) not in sys.path:
    sys.path.insert(0, str(IO_MATRIX_DIR))


# =============================================================================
# QUERY PARSING
# =============================================================================

# Prefix patterns
PREFIX_PATTERNS = {
    'p:': 'person',
    'c:': 'company',
    'e:': 'email',
    't:': 'phone',
    'd:': 'domain',
    'a:': 'address',
    'u:': 'username',
    'li:': 'linkedin_url',
    'linkedin:': 'linkedin_url',
    'liu:': 'linkedin_username',
    'liuser:': 'linkedin_username',
}

# Jurisdiction pattern: :XX at end (e.g., "c: Acme Corp :US")
JURISDICTION_PATTERN = re.compile(r'\s+:([A-Z]{2})\s*$')


def parse_prefix_query(query: str) -> Tuple[str, str, Optional[str]]:
    """
    Parse a prefix query into entity type, value, and optional jurisdiction.

    Examples:
        "p: John Smith" -> ("person", "John Smith", None)
        "c: Acme Corp :US" -> ("company", "Acme Corp", "US")
        "e: john@acme.com" -> ("email", "john@acme.com", None)

    Returns:
        Tuple of (entity_type, value, jurisdiction)
    """
    query = query.strip()

    # Check for prefix
    entity_type = None
    value = query

    for prefix, etype in PREFIX_PATTERNS.items():
        if query.lower().startswith(prefix):
            entity_type = etype
            value = query[len(prefix):].strip()
            break

    if not entity_type:
        # No prefix - assume person if looks like name, company otherwise
        if any(c.isupper() for c in value) and ' ' in value:
            entity_type = 'person'
        else:
            entity_type = 'unknown'

    # Check for jurisdiction suffix
    jurisdiction = None
    match = JURISDICTION_PATTERN.search(value)
    if match:
        jurisdiction = match.group(1)
        value = value[:match.start()].strip()

    return entity_type, value, jurisdiction


# =============================================================================
# IO RESULT DATACLASS
# =============================================================================

@dataclass
class IOResult:
    """Result from an IO execution."""
    entity_type: str
    value: str
    jurisdiction: Optional[str] = None
    status: str = "pending"  # pending, success, error, partial
    modules_run: List[str] = field(default_factory=list)
    results: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    timestamp: str = ""

    # Extracted entities for graph population
    extracted_entities: List[Dict[str, Any]] = field(default_factory=list)

    # Reality check results
    reality_check: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "value": self.value,
            "jurisdiction": self.jurisdiction,
            "status": self.status,
            "modules_run": self.modules_run,
            "results": self.results,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp,
            "extracted_entities": self.extracted_entities,
            "reality_check": self.reality_check,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IOResult":
        return cls(
            entity_type=data.get("entity_type", "unknown"),
            value=data.get("value", ""),
            jurisdiction=data.get("jurisdiction"),
            status=data.get("status", "pending"),
            modules_run=data.get("modules_run", []),
            results=data.get("results", {}),
            errors=data.get("errors", []),
            duration_seconds=data.get("duration_seconds", 0.0),
            timestamp=data.get("timestamp", ""),
            extracted_entities=data.get("extracted_entities", []),
            reality_check=data.get("reality_check", {}),
        )

    @property
    def is_success(self) -> bool:
        return self.status in ("success", "partial") and not self.errors


# =============================================================================
# IO CLIENT - DIRECT INTEGRATION
# =============================================================================

class IOClient:
    """
    Direct client for IO Matrix execution.

    Unlike the HTTP-based IOClient, this directly imports and calls
    the IOExecutor and IORouter from the IO Matrix.
    """

    def __init__(
        self,
        project_id: str = "default",
        dry_run: bool = False,
        rules_limit: Optional[int] = None,
    ):
        self.project_id = project_id
        self.dry_run = dry_run
        self.rules_limit = rules_limit

        # Lazy-loaded executor
        self._executor = None
        self._router = None
        self._available = None

    def _lazy_load(self) -> bool:
        """Lazy load IO Matrix components."""
        if self._available is not None:
            return self._available

        try:
            # Import IO Matrix components
            from io_cli import IORouter, IOExecutor

            self._router = IORouter()
            self._executor = IOExecutor(
                router=self._router,
                dry_run=self.dry_run,
                project_id=self.project_id,
                rules_limit=self.rules_limit,
            )
            self._available = True
            logger.info("IO Matrix loaded successfully")
            return True

        except ImportError as e:
            logger.warning(f"IO Matrix not available: {e}")
            self._available = False
            return False
        except Exception as e:
            logger.error(f"Failed to load IO Matrix: {e}")
            self._available = False
            return False

    @property
    def is_available(self) -> bool:
        """Check if IO Matrix is available."""
        return self._lazy_load()

    async def execute(
        self,
        query: str,
        jurisdiction: Optional[str] = None,
        **kwargs
    ) -> IOResult:
        """
        Execute a prefix query.

        Args:
            query: Query with prefix (e.g., "p: John Smith", "c: Acme Corp :US")
            jurisdiction: Optional jurisdiction override
            **kwargs: Additional options passed to executor

        Returns:
            IOResult with execution results
        """
        # Parse the query
        entity_type, value, parsed_jurisdiction = parse_prefix_query(query)

        # Use parsed jurisdiction if not overridden
        jurisdiction = jurisdiction or parsed_jurisdiction

        return await self.execute_entity(
            entity_type=entity_type,
            value=value,
            jurisdiction=jurisdiction,
            **kwargs
        )

    async def execute_entity(
        self,
        entity_type: str,
        value: str,
        jurisdiction: Optional[str] = None,
        **kwargs
    ) -> IOResult:
        """
        Execute investigation for a specific entity type.

        Args:
            entity_type: Type (person, company, email, phone, domain)
            value: The entity value to investigate
            jurisdiction: Optional jurisdiction filter
            **kwargs: Additional options

        Returns:
            IOResult with execution results
        """
        start_time = datetime.now()

        # Create result object
        result = IOResult(
            entity_type=entity_type,
            value=value,
            jurisdiction=jurisdiction,
            timestamp=start_time.isoformat(),
        )

        # Check availability
        if not self._lazy_load():
            result.status = "error"
            result.errors.append("IO Matrix not available")
            return result

        try:
            # Execute via IO Matrix
            raw_result = await self._executor.execute(
                entity_type=entity_type,
                value=value,
                jurisdiction=jurisdiction,
            )

            # Map raw result to IOResult
            result.status = "success" if not raw_result.get("errors") else "partial"
            result.modules_run = raw_result.get("modules_run", [])
            result.results = raw_result.get("results", {})
            result.errors = raw_result.get("errors", [])
            result.reality_check = raw_result.get("reality_check", {})
            result.duration_seconds = raw_result.get("duration_seconds", 0.0)

            # Extract entities from results for graph population
            result.extracted_entities = self._extract_entities(raw_result)

        except Exception as e:
            result.status = "error"
            result.errors.append(f"Execution error: {str(e)}")
            logger.exception(f"IO execution failed: {e}")

        result.duration_seconds = (datetime.now() - start_time).total_seconds()
        return result

    async def execute_matching_rules(
        self,
        entity_type: str,
        value: str,
        jurisdiction: Optional[str] = None,
    ) -> IOResult:
        """
        Execute only rules matching entity type and jurisdiction.

        This uses the rule-based execution path for more targeted results.
        """
        if not self._lazy_load():
            return IOResult(
                entity_type=entity_type,
                value=value,
                status="error",
                errors=["IO Matrix not available"],
            )

        try:
            raw_result = await self._executor.execute_matching_rules(
                entity_type=entity_type,
                value=value,
                jurisdiction=jurisdiction,
            )

            return IOResult(
                entity_type=entity_type,
                value=value,
                jurisdiction=jurisdiction,
                status="success" if raw_result.get("status") == "success" else "partial",
                results=raw_result.get("results", {}),
                modules_run=raw_result.get("rules_executed", []),
                errors=raw_result.get("errors", []),
            )

        except Exception as e:
            return IOResult(
                entity_type=entity_type,
                value=value,
                status="error",
                errors=[str(e)],
            )

    async def get_available_routes(
        self,
        entity_type: str,
        jurisdiction: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get available routes for an entity type.

        This is useful for planning what investigations are possible.
        Uses IORouter.find_capabilities() to discover what outputs are possible.
        """
        if not self._lazy_load():
            return []

        try:
            # Map entity type to field code
            entity_field_map = {
                "person": "person_name",
                "company": "company_name",
                "email": "email",
                "phone": "phone",
                "domain": "domain_url",
            }

            field_name = entity_field_map.get(entity_type, entity_type)

            # Use find_capabilities to get available routes
            capabilities = self._router.find_capabilities(field_name)

            if "error" in capabilities:
                logger.warning(f"No capabilities for {entity_type}: {capabilities['error']}")
                return []

            # Combine rules and playbooks info
            routes = []

            for rule in capabilities.get("via_rules", []):
                routes.append({
                    "source_id": rule.get("rule_id"),
                    "source_label": rule.get("label"),
                    "input_type": field_name,
                    "output_columns": rule.get("outputs", []),
                    "reliability": rule.get("reliability", "medium"),
                    "friction": rule.get("friction", "open"),
                    "type": "rule",
                })

            for playbook in capabilities.get("via_playbooks", []):
                routes.append({
                    "source_id": playbook.get("rule_id"),
                    "source_label": playbook.get("label"),
                    "input_type": field_name,
                    "output_columns": playbook.get("outputs", []),
                    "reliability": playbook.get("reliability", "medium"),
                    "friction": playbook.get("friction", "open"),
                    "type": "playbook",
                })

            return routes

        except Exception as e:
            logger.error(f"Failed to get routes: {e}")
            return []

    async def dry_run_plan(
        self,
        entity_type: str,
        value: str,
        jurisdiction: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get a dry run plan without executing.

        Shows what would be executed.
        """
        if not self._lazy_load():
            return {"error": "IO Matrix not available"}

        try:
            # Create executor in dry run mode
            dry_executor = type(self._executor)(
                router=self._router,
                dry_run=True,
                project_id=self.project_id,
            )

            result = await dry_executor.execute(
                entity_type=entity_type,
                value=value,
                jurisdiction=jurisdiction,
            )

            return result

        except Exception as e:
            return {"error": str(e)}

    def _extract_entities(self, raw_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract entities from raw IO result for graph population.

        Looks through all result modules and extracts:
        - Names (person, company)
        - Emails
        - Phones
        - Addresses
        - URLs/domains
        """
        entities = []
        results = raw_result.get("results", {})

        # WDC entities
        for entity in results.get("schema_org_entities", []):
            if isinstance(entity, dict):
                entities.append({
                    "type": entity.get("@type", "Thing"),
                    "name": entity.get("name", "Unknown"),
                    "source": "wdc",
                })

        # EYE-D results
        eyed = results.get("eye_d", {})
        if isinstance(eyed, dict):
            for email in eyed.get("emails", []):
                entities.append({"type": "email", "value": email, "source": "eye_d"})
            for phone in eyed.get("phones", []):
                entities.append({"type": "phone", "value": phone, "source": "eye_d"})

        # Corporella results
        corp = results.get("corporella", {})
        if isinstance(corp, dict):
            if corp.get("company_name"):
                entities.append({
                    "type": "company",
                    "name": corp.get("company_name"),
                    "registration_number": corp.get("registration_number"),
                    "jurisdiction": corp.get("jurisdiction"),
                    "source": "corporella",
                })
            for officer in corp.get("officers", []):
                entities.append({
                    "type": "person",
                    "name": officer.get("name"),
                    "role": officer.get("role"),
                    "source": "corporella",
                })

        # Torpedo results (registry data)
        torpedo = results.get("torpedo", {})
        if isinstance(torpedo, dict) and torpedo.get("profile"):
            profile = torpedo["profile"]
            entities.append({
                "type": "company",
                "name": profile.get("company_name"),
                "registration_number": profile.get("registration_number") or profile.get("oib"),
                "status": profile.get("status"),
                "address": profile.get("address"),
                "source": "torpedo",
            })

        return entities


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

# Global client instance
_default_client: Optional[IOClient] = None


def get_io_client(project_id: str = "default") -> IOClient:
    """Get or create the default IO client."""
    global _default_client
    if _default_client is None or _default_client.project_id != project_id:
        _default_client = IOClient(project_id=project_id)
    return _default_client


async def execute_io(query: str, jurisdiction: str = None, **kwargs) -> IOResult:
    """
    Convenience function to execute an IO query.

    Args:
        query: Prefix query (e.g., "p: John Smith")
        jurisdiction: Optional jurisdiction
        **kwargs: Additional options

    Returns:
        IOResult with execution results
    """
    client = get_io_client()
    return await client.execute(query, jurisdiction=jurisdiction, **kwargs)


async def investigate(
    query: str,
    project_id: str = "default",
    dry_run: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """
    Main entry point for SASTRE investigation via IO Matrix.

    This is the function that io_tools.py calls.

    Args:
        query: Investigation query with prefix
        project_id: Project ID for tracking
        dry_run: If True, show plan without executing
        **kwargs: Additional options

    Returns:
        Dict with investigation results
    """
    client = IOClient(project_id=project_id, dry_run=dry_run)
    result = await client.execute(query, **kwargs)
    return result.to_dict()
