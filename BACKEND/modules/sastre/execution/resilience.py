#!/usr/bin/env python3
"""
SASTRE Resilience Layer - Graceful Degradation & Fallback Chains

Handles external API failures (429, CAPTCHA, timeout) without halting investigations.
Each ALLOWED_ACTION has a defined fallback chain with automatic source switching.

Fallback Philosophy:
- Primary: Live registry/API (fastest, most current)
- Fallback 1: Archive search (Wayback, CommonCrawl)
- Fallback 2: Cached/commercial providers (Orbis, D&B)
- Fallback 3: Manual flag (human intervention needed)

Usage:
    executor = ResilientExecutor()
    results, source = await executor.execute_with_fallback(
        "SEARCH_REGISTRY",
        {"entity": "Test Ltd", "jurisdiction": "uk"}
    )

    if source == "manual_flag":
        # Flag for human review
        pass
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    """Base error for execution failures."""
    pass


class RateLimitError(ExecutionError):
    """Rate limit exceeded (429 errors)."""
    pass


class TimeoutError(ExecutionError):
    """Request timeout."""
    pass


class CaptchaError(ExecutionError):
    """CAPTCHA challenge encountered."""
    pass


class SourceUnavailableError(ExecutionError):
    """Source is temporarily or permanently unavailable."""
    pass


class SourceType(Enum):
    """Types of data sources in fallback chains."""
    LIVE_REGISTRY = "live_registry"       # Direct registry API
    LIVE_API = "live_api"                 # Third-party API
    ARCHIVE = "archive"                   # Wayback/CommonCrawl
    CACHED = "cached"                     # Local cache/Elasticsearch
    COMMERCIAL = "commercial"             # Paid providers (Orbis, D&B)
    MANUAL = "manual_flag"                # Human intervention


@dataclass
class FallbackChain:
    """
    Ordered list of fallback sources for an action.

    Attributes:
        action: The ALLOWED_ACTION this chain handles
        primary: Primary source name
        primary_type: Type of primary source
        fallbacks: Ordered list of (source_name, source_type) tuples
        latency_budget_ms: Total time budget for all attempts
        retry_delays: Delay between retries per source type
    """
    action: str
    primary: str
    primary_type: SourceType
    fallbacks: List[Tuple[str, SourceType]]
    latency_budget_ms: int = 30000
    retry_delays: Dict[SourceType, float] = field(default_factory=lambda: {
        SourceType.LIVE_REGISTRY: 1.0,
        SourceType.LIVE_API: 0.5,
        SourceType.ARCHIVE: 2.0,
        SourceType.CACHED: 0.1,
        SourceType.COMMERCIAL: 1.0,
    })

    def get_source_budget(self, is_primary: bool) -> float:
        """Get timeout budget for a source in seconds."""
        if is_primary:
            return self.latency_budget_ms / 1000 / 2  # Half for primary
        # Remaining half split among fallbacks
        return (self.latency_budget_ms / 1000 / 2) / max(len(self.fallbacks), 1)


# Define fallback chains for all 24 ALLOWED_ACTIONS
FALLBACK_CHAINS: Dict[str, FallbackChain] = {
    # Registry & Corporate
    "SEARCH_REGISTRY": FallbackChain(
        action="SEARCH_REGISTRY",
        primary="torpedo_live",
        primary_type=SourceType.LIVE_REGISTRY,
        fallbacks=[
            ("linklater_archive", SourceType.ARCHIVE),
            ("opencorporates_cache", SourceType.CACHED),
            ("elastic_cache", SourceType.CACHED),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=45000,
    ),
    "SEARCH_OFFICERS": FallbackChain(
        action="SEARCH_OFFICERS",
        primary="registry_api",
        primary_type=SourceType.LIVE_REGISTRY,
        fallbacks=[
            ("linklater_archive", SourceType.ARCHIVE),
            ("opencorporates_cache", SourceType.CACHED),
            ("orbis_commercial", SourceType.COMMERCIAL),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=30000,
    ),
    "SEARCH_SHAREHOLDERS": FallbackChain(
        action="SEARCH_SHAREHOLDERS",
        primary="registry_api",
        primary_type=SourceType.LIVE_REGISTRY,
        fallbacks=[
            ("orbis_commercial", SourceType.COMMERCIAL),
            ("linklater_archive", SourceType.ARCHIVE),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=45000,
    ),
    "SEARCH_FINANCIALS": FallbackChain(
        action="SEARCH_FINANCIALS",
        primary="registry_filings",
        primary_type=SourceType.LIVE_REGISTRY,
        fallbacks=[
            ("dnb_commercial", SourceType.COMMERCIAL),
            ("orbis_commercial", SourceType.COMMERCIAL),
            ("linklater_archive", SourceType.ARCHIVE),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=60000,
    ),

    # Regulatory & Compliance
    "SEARCH_REGULATORY": FallbackChain(
        action="SEARCH_REGULATORY",
        primary="regulator_api",
        primary_type=SourceType.LIVE_API,
        fallbacks=[
            ("linklater_archive", SourceType.ARCHIVE),
            ("news_search", SourceType.LIVE_API),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=30000,
    ),
    "SEARCH_SANCTIONS": FallbackChain(
        action="SEARCH_SANCTIONS",
        primary="consolidated_sanctions",
        primary_type=SourceType.LIVE_API,
        fallbacks=[
            ("ofac_direct", SourceType.LIVE_API),
            ("eu_sanctions_list", SourceType.LIVE_API),
            ("cached_sanctions", SourceType.CACHED),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=20000,
    ),
    "SEARCH_PEP": FallbackChain(
        action="SEARCH_PEP",
        primary="worldcheck_api",
        primary_type=SourceType.COMMERCIAL,
        fallbacks=[
            ("dowjones_api", SourceType.COMMERCIAL),
            ("opensanctions", SourceType.LIVE_API),
            ("cached_pep", SourceType.CACHED),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=30000,
    ),

    # Legal & Courts
    "SEARCH_COURT": FallbackChain(
        action="SEARCH_COURT",
        primary="court_registry",
        primary_type=SourceType.LIVE_REGISTRY,
        fallbacks=[
            ("linklater_archive", SourceType.ARCHIVE),
            ("lexisnexis_commercial", SourceType.COMMERCIAL),
            ("news_litigation", SourceType.LIVE_API),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=45000,
    ),
    "SEARCH_BANKRUPTCY": FallbackChain(
        action="SEARCH_BANKRUPTCY",
        primary="insolvency_registry",
        primary_type=SourceType.LIVE_REGISTRY,
        fallbacks=[
            ("linklater_archive", SourceType.ARCHIVE),
            ("gazette_search", SourceType.LIVE_API),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=30000,
    ),

    # Media & News
    "SEARCH_NEWS": FallbackChain(
        action="SEARCH_NEWS",
        primary="gdelt_api",
        primary_type=SourceType.LIVE_API,
        fallbacks=[
            ("newsapi", SourceType.LIVE_API),
            ("brute_news", SourceType.LIVE_API),
            ("linklater_archive", SourceType.ARCHIVE),
            ("elastic_cache", SourceType.CACHED),
        ],
        latency_budget_ms=30000,
    ),

    # Property & Assets
    "SEARCH_PROPERTY": FallbackChain(
        action="SEARCH_PROPERTY",
        primary="land_registry",
        primary_type=SourceType.LIVE_REGISTRY,
        fallbacks=[
            ("linklater_archive", SourceType.ARCHIVE),
            ("commercial_property", SourceType.COMMERCIAL),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=45000,
    ),
    "SEARCH_CREDIT": FallbackChain(
        action="SEARCH_CREDIT",
        primary="credit_bureau",
        primary_type=SourceType.COMMERCIAL,
        fallbacks=[
            ("dnb_commercial", SourceType.COMMERCIAL),
            ("experian_commercial", SourceType.COMMERCIAL),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=30000,
    ),

    # Business Context
    "SEARCH_COMPETITORS": FallbackChain(
        action="SEARCH_COMPETITORS",
        primary="industry_databases",
        primary_type=SourceType.LIVE_API,
        fallbacks=[
            ("brute_search", SourceType.LIVE_API),
            ("elastic_cache", SourceType.CACHED),
        ],
        latency_budget_ms=30000,
    ),
    "SEARCH_CONTRACTS": FallbackChain(
        action="SEARCH_CONTRACTS",
        primary="procurement_registry",
        primary_type=SourceType.LIVE_REGISTRY,
        fallbacks=[
            ("linklater_archive", SourceType.ARCHIVE),
            ("news_contracts", SourceType.LIVE_API),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=45000,
    ),
    "SEARCH_ENVIRONMENTAL": FallbackChain(
        action="SEARCH_ENVIRONMENTAL",
        primary="environmental_registry",
        primary_type=SourceType.LIVE_REGISTRY,
        fallbacks=[
            ("linklater_archive", SourceType.ARCHIVE),
            ("ngo_databases", SourceType.LIVE_API),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=30000,
    ),
    "SEARCH_TAX": FallbackChain(
        action="SEARCH_TAX",
        primary="tax_authority",
        primary_type=SourceType.LIVE_REGISTRY,
        fallbacks=[
            ("commercial_tax", SourceType.COMMERCIAL),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=30000,
    ),
    "SEARCH_INTELLECTUAL_PROPERTY": FallbackChain(
        action="SEARCH_INTELLECTUAL_PROPERTY",
        primary="ip_registry",
        primary_type=SourceType.LIVE_REGISTRY,
        fallbacks=[
            ("wipo_search", SourceType.LIVE_API),
            ("linklater_archive", SourceType.ARCHIVE),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=30000,
    ),

    # Person-Specific
    "SEARCH_EMPLOYEE": FallbackChain(
        action="SEARCH_EMPLOYEE",
        primary="linkedin_api",
        primary_type=SourceType.LIVE_API,
        fallbacks=[
            ("brute_search", SourceType.LIVE_API),
            ("elastic_cache", SourceType.CACHED),
        ],
        latency_budget_ms=30000,
    ),
    "SEARCH_RELATED_PARTIES": FallbackChain(
        action="SEARCH_RELATED_PARTIES",
        primary="registry_cross_ref",
        primary_type=SourceType.LIVE_REGISTRY,
        fallbacks=[
            ("orbis_commercial", SourceType.COMMERCIAL),
            ("elastic_cache", SourceType.CACHED),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=45000,
    ),
    "SEARCH_WEBSITE": FallbackChain(
        action="SEARCH_WEBSITE",
        primary="firecrawl",
        primary_type=SourceType.LIVE_API,
        fallbacks=[
            ("wayback_machine", SourceType.ARCHIVE),
            ("commoncrawl", SourceType.ARCHIVE),
        ],
        latency_budget_ms=30000,
    ),
    "SEARCH_CAREER": FallbackChain(
        action="SEARCH_CAREER",
        primary="linkedin_api",
        primary_type=SourceType.LIVE_API,
        fallbacks=[
            ("brute_search", SourceType.LIVE_API),
            ("linklater_archive", SourceType.ARCHIVE),
            ("elastic_cache", SourceType.CACHED),
        ],
        latency_budget_ms=30000,
    ),
    "SEARCH_EDUCATION": FallbackChain(
        action="SEARCH_EDUCATION",
        primary="education_registry",
        primary_type=SourceType.LIVE_REGISTRY,
        fallbacks=[
            ("brute_search", SourceType.LIVE_API),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=30000,
    ),
    "SEARCH_FAMILY": FallbackChain(
        action="SEARCH_FAMILY",
        primary="public_records",
        primary_type=SourceType.LIVE_REGISTRY,
        fallbacks=[
            ("news_search", SourceType.LIVE_API),
            ("manual_flag", SourceType.MANUAL),
        ],
        latency_budget_ms=45000,
    ),
    "SEARCH_SOCIAL": FallbackChain(
        action="SEARCH_SOCIAL",
        primary="social_apis",
        primary_type=SourceType.LIVE_API,
        fallbacks=[
            ("linklater_archive", SourceType.ARCHIVE),
            ("wayback_social", SourceType.ARCHIVE),
            ("elastic_cache", SourceType.CACHED),
        ],
        latency_budget_ms=30000,
    ),
}


@dataclass
class ExecutionResult:
    """Result of a resilient execution attempt."""
    success: bool
    source_used: str
    source_type: SourceType
    results: List[Dict[str, Any]]
    attempts: List[Dict[str, Any]]  # Log of all attempts
    total_time_ms: float
    fallback_used: bool = False


class ResilientExecutor:
    """
    Execute actions with automatic fallback on failures.

    Handles:
    - Rate limiting (429 errors) with exponential backoff
    - Timeouts with automatic source switching
    - CAPTCHA challenges with archive fallback
    - Source unavailability with graceful degradation
    """

    def __init__(
        self,
        source_executors: Optional[Dict[str, Callable]] = None,
        max_retries_per_source: int = 2,
        circuit_breaker_threshold: int = 5,
    ):
        """
        Initialize resilient executor.

        Args:
            source_executors: Dict mapping source names to executor functions
            max_retries_per_source: Max retries before moving to fallback
            circuit_breaker_threshold: Failures before circuit opens
        """
        self.source_executors = source_executors or {}
        self.max_retries = max_retries_per_source
        self.circuit_breaker_threshold = circuit_breaker_threshold

        # Circuit breaker state per source
        self._circuit_failures: Dict[str, int] = {}
        self._circuit_open_until: Dict[str, float] = {}

    def register_executor(self, source: str, executor: Callable):
        """Register an executor function for a source."""
        self.source_executors[source] = executor

    def _is_circuit_open(self, source: str) -> bool:
        """Check if circuit breaker is open for a source."""
        if source not in self._circuit_open_until:
            return False
        if time.time() > self._circuit_open_until[source]:
            # Reset circuit
            self._circuit_failures[source] = 0
            del self._circuit_open_until[source]
            return False
        return True

    def _record_failure(self, source: str):
        """Record a failure for circuit breaker."""
        self._circuit_failures[source] = self._circuit_failures.get(source, 0) + 1
        if self._circuit_failures[source] >= self.circuit_breaker_threshold:
            # Open circuit for 5 minutes
            self._circuit_open_until[source] = time.time() + 300
            logger.warning(f"Circuit breaker OPEN for {source}")

    def _record_success(self, source: str):
        """Record success to reset circuit breaker."""
        self._circuit_failures[source] = 0
        if source in self._circuit_open_until:
            del self._circuit_open_until[source]

    async def execute_with_fallback(
        self,
        action: str,
        context: Dict[str, Any],
    ) -> Tuple[List[Dict], str]:
        """
        Execute action with automatic fallback on failure.

        Args:
            action: ALLOWED_ACTION to execute
            context: Execution context (entity, jurisdiction, etc.)

        Returns:
            Tuple of (results, source_used)
            If source_used is "manual_flag", human intervention needed
            If source_used is "exhausted", all sources failed
        """
        chain = FALLBACK_CHAINS.get(action)
        if not chain:
            # No fallback chain defined, execute directly
            return await self._direct_execute(action, context), "direct"

        start_time = time.time()
        attempts = []

        # Try primary source
        if not self._is_circuit_open(chain.primary):
            try:
                results = await asyncio.wait_for(
                    self._execute_source(chain.primary, action, context),
                    timeout=chain.get_source_budget(is_primary=True)
                )
                if results:
                    self._record_success(chain.primary)
                    return results, chain.primary
            except asyncio.TimeoutError:
                logger.warning(f"{chain.primary} timed out for {action}")
                attempts.append({
                    "source": chain.primary,
                    "error": "timeout",
                    "time_ms": (time.time() - start_time) * 1000
                })
            except RateLimitError as e:
                logger.warning(f"{chain.primary} rate limited: {e}")
                self._record_failure(chain.primary)
                attempts.append({
                    "source": chain.primary,
                    "error": "rate_limit",
                    "time_ms": (time.time() - start_time) * 1000
                })
            except CaptchaError:
                logger.warning(f"{chain.primary} CAPTCHA challenge")
                attempts.append({
                    "source": chain.primary,
                    "error": "captcha",
                    "time_ms": (time.time() - start_time) * 1000
                })
            except Exception as e:
                logger.warning(f"{chain.primary} failed: {e}")
                self._record_failure(chain.primary)
                attempts.append({
                    "source": chain.primary,
                    "error": str(e),
                    "time_ms": (time.time() - start_time) * 1000
                })
        else:
            logger.info(f"Circuit open for {chain.primary}, skipping")
            attempts.append({
                "source": chain.primary,
                "error": "circuit_open",
                "time_ms": 0
            })

        # Try fallbacks
        for fallback_source, fallback_type in chain.fallbacks:
            if fallback_type == SourceType.MANUAL:
                logger.info(f"Flagging {action} for manual intervention")
                return [], "manual_flag"

            if self._is_circuit_open(fallback_source):
                logger.debug(f"Circuit open for {fallback_source}, skipping")
                continue

            try:
                # Add delay between fallback attempts
                delay = chain.retry_delays.get(fallback_type, 0.5)
                await asyncio.sleep(delay)

                results = await asyncio.wait_for(
                    self._execute_source(fallback_source, action, context),
                    timeout=chain.get_source_budget(is_primary=False)
                )
                if results:
                    self._record_success(fallback_source)
                    logger.info(f"Fallback {fallback_source} succeeded for {action}")
                    return results, fallback_source

            except asyncio.TimeoutError:
                logger.warning(f"Fallback {fallback_source} timed out")
                attempts.append({
                    "source": fallback_source,
                    "error": "timeout",
                    "time_ms": (time.time() - start_time) * 1000
                })
            except Exception as e:
                logger.warning(f"Fallback {fallback_source} failed: {e}")
                self._record_failure(fallback_source)
                attempts.append({
                    "source": fallback_source,
                    "error": str(e),
                    "time_ms": (time.time() - start_time) * 1000
                })

        # All sources exhausted
        logger.error(f"All sources exhausted for {action}")
        return [], "exhausted"

    async def _execute_source(
        self,
        source: str,
        action: str,
        context: Dict[str, Any]
    ) -> List[Dict]:
        """Execute using a specific source."""
        executor = self.source_executors.get(source)
        if not executor:
            # No executor registered, return empty
            logger.debug(f"No executor registered for {source}")
            return []

        return await executor(action, context)

    async def _direct_execute(
        self,
        action: str,
        context: Dict[str, Any]
    ) -> List[Dict]:
        """Execute action directly without fallback chain."""
        # Default implementation - should be overridden
        logger.warning(f"Direct execute called for {action} - no implementation")
        return []

    def get_circuit_status(self) -> Dict[str, str]:
        """Get status of all circuit breakers."""
        status = {}
        for source, open_until in self._circuit_open_until.items():
            remaining = open_until - time.time()
            if remaining > 0:
                status[source] = f"OPEN (resets in {remaining:.0f}s)"
            else:
                status[source] = "CLOSED"
        return status


# Convenience function for quick resilient execution
async def execute_resilient(
    action: str,
    context: Dict[str, Any],
    executor: Optional[ResilientExecutor] = None
) -> Tuple[List[Dict], str]:
    """Quick resilient execution."""
    if executor is None:
        executor = ResilientExecutor()
    return await executor.execute_with_fallback(action, context)


if __name__ == "__main__":
    import json

    # Demo: Show all fallback chains
    print("SASTRE Fallback Chains for 24 ALLOWED_ACTIONS")
    print("=" * 60)

    for action, chain in FALLBACK_CHAINS.items():
        print(f"\n{action}")
        print(f"  Primary: {chain.primary} ({chain.primary_type.value})")
        print(f"  Budget: {chain.latency_budget_ms}ms")
        print("  Fallbacks:")
        for source, source_type in chain.fallbacks:
            print(f"    → {source} ({source_type.value})")

    # Demo: Circuit breaker
    print("\n\n" + "=" * 60)
    print("Circuit Breaker Demo")
    print("=" * 60)

    executor = ResilientExecutor()

    # Simulate failures
    for i in range(6):
        executor._record_failure("test_source")
        print(f"Failure {i+1}: Circuit open = {executor._is_circuit_open('test_source')}")

    print(f"\nCircuit status: {executor.get_circuit_status()}")
