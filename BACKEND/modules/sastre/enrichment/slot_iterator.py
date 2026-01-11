"""
Slot Iterator - Auto-iterate queries until slot is sufficient

Implements the "Loop Until Sufficient" pattern from the Abacus System.

ALIGNS WITH: Abacus System - "Auto-iterate queries until slot is sufficiently filled"
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set, Tuple

from .slot_sufficiency import SlotSufficiencyConfig, get_slot_config

logger = logging.getLogger(__name__)


class SlotState(Enum):
    """State of a slot."""

    EMPTY = "empty"
    PARTIAL = "partial"
    FILLED = "filled"
    VOID = "void"
    CONTESTED = "contested"
    DEFERRED = "deferred"     # Blocked with current tools, cannot formulate valid plan


@dataclass
class IterationAttempt:
    """Record of a single query attempt for a slot."""

    attempt_number: int
    query: str
    engine: str
    timestamp: datetime
    result_count: int
    confidence: float
    status: str  # "success", "no_results", "error", "rate_limited"
    error: Optional[str] = None


@dataclass
class SlotIterationState:
    """Tracks iteration history for a slot."""

    slot_id: str
    slot_type: str
    config: SlotSufficiencyConfig
    attempts: List[IterationAttempt] = field(default_factory=list)
    queries_tried: Set[str] = field(default_factory=set)
    engines_tried: Set[str] = field(default_factory=set)
    variations_used: List[str] = field(default_factory=list)
    current_status: SlotState = SlotState.EMPTY
    total_results: int = 0
    best_confidence: float = 0.0

    def is_sufficient(self) -> bool:
        """Check if slot has met sufficiency criteria."""
        if self.current_status == SlotState.FILLED:
            return True
        if self.current_status == SlotState.VOID and self.config.void_is_finding:
            return True
        if self.total_results >= self.config.min_results:
            if self.best_confidence >= self.config.min_confidence:
                return True
        return False

    def can_iterate(self) -> bool:
        """Check if more iterations are allowed."""
        return len(self.attempts) < self.config.max_attempts

    def record_attempt(self, attempt: IterationAttempt):
        self.attempts.append(attempt)
        self.queries_tried.add(attempt.query)
        self.engines_tried.add(attempt.engine)
        self.total_results += attempt.result_count
        if attempt.confidence > self.best_confidence:
            self.best_confidence = attempt.confidence

    def to_audit_log(self) -> Dict[str, Any]:
        """Generate audit log for methodology section."""
        return {
            "slot": self.slot_id,
            "total_attempts": len(self.attempts),
            "engines_consulted": list(self.engines_tried),
            "query_variations": len(self.queries_tried),
            "final_result": self.current_status.value,
            "total_results": self.total_results,
            "best_confidence": self.best_confidence,
        }


# ========== QUERY STRATEGIES ==========


class QueryStrategy:
    """Base class for query generation strategies."""

    name: str = "base"

    def can_generate(self, state: SlotIterationState, attempt: int) -> bool:
        return True

    def generate(
        self,
        slot_type: str,
        entity_context: Dict[str, Any],
        state: SlotIterationState,
        attempt: int,
    ) -> Optional[str]:
        raise NotImplementedError


class VariationStrategy(QueryStrategy):
    """Use name/company variations."""

    name = "variation"

    def generate(
        self,
        slot_type: str,
        entity_context: Dict[str, Any],
        state: SlotIterationState,
        attempt: int,
    ) -> Optional[str]:
        name = entity_context.get("name", "")
        if not state.variations_used:
            # Generate basic variations
            state.variations_used = self._generate_variations(
                name, entity_context.get("type", "unknown")
            )

        unused = [v for v in state.variations_used if v not in state.queries_tried]
        if unused:
            return f'"{unused[0]}" {slot_type}'
        return None

    def _generate_variations(self, name: str, entity_type: str) -> List[str]:
        variations = [name]
        parts = name.split()

        if entity_type == "person" and len(parts) >= 2:
            # Last name, First name
            variations.append(f"{parts[-1]}, {parts[0]}")
            # Initials
            if len(parts) == 2:
                variations.append(f"{parts[0][0]}. {parts[1]}")
            # Just last name
            variations.append(parts[-1])

        elif entity_type == "company":
            # Without common suffixes
            suffixes = ["Ltd", "Limited", "Inc", "LLC", "GmbH", "AG", "SA", "Kft"]
            for suffix in suffixes:
                if name.upper().endswith(suffix.upper()):
                    stripped = name[: -len(suffix)].strip(" .,")
                    if stripped not in variations:
                        variations.append(stripped)

        return variations


class BroadeningStrategy(QueryStrategy):
    """Broaden query when specific fails."""

    name = "broaden"

    def generate(
        self,
        slot_type: str,
        entity_context: Dict[str, Any],
        state: SlotIterationState,
        attempt: int,
    ) -> Optional[str]:
        name = entity_context.get("name", "")

        if attempt == 0:
            return f"{name} {slot_type}"  # Remove quotes
        elif attempt == 1:
            parts = name.split()
            if len(parts) >= 2:
                return f"{parts[-1]} {slot_type}"  # Last name only
        elif attempt == 2:
            return f'"{name}" OR "{slot_type}" related'

        return None


class FallbackEngineStrategy(QueryStrategy):
    """Try fallback engines."""

    name = "fallback"

    # Fallback chains per slot type
    FALLBACK_CHAINS = {
        "officers": ["companies_house_api", "opencorporates", "brute_search"],
        "shareholders": ["companies_house_api", "opencorporates", "brute_search"],
        "ubo": ["ubo_trace", "companies_house_api", "brute_search"],
        "litigation": ["bailii", "court_listener", "brute_search"],
        "_default": ["brute_search", "archive_search"],
    }

    def generate(
        self,
        slot_type: str,
        entity_context: Dict[str, Any],
        state: SlotIterationState,
        attempt: int,
    ) -> Optional[str]:
        chain = self.FALLBACK_CHAINS.get(slot_type, self.FALLBACK_CHAINS["_default"])
        unused_engines = [e for e in chain if e not in state.engines_tried]

        if unused_engines:
            # Return marker for which engine to use
            return f"__engine:{unused_engines[0]}__ {entity_context.get('name', '')}"

        return None


class ArchiveStrategy(QueryStrategy):
    """Search historical archives."""

    name = "archive"

    def generate(
        self,
        slot_type: str,
        entity_context: Dict[str, Any],
        state: SlotIterationState,
        attempt: int,
    ) -> Optional[str]:
        name = entity_context.get("name", "")
        return f'":{name}" ::{slot_type} #archive'


class JurisdictionPivotStrategy(QueryStrategy):
    """Try adjacent jurisdictions when primary fails."""

    name = "jurisdiction_pivot"

    ADJACENT_JURISDICTIONS = {
        "UK": ["IE", "JE", "GG", "IM"],
        "DE": ["AT", "CH", "LU"],
        "US": ["CA", "GB", "AU"],
        "HU": ["AT", "SK", "RO", "HR"],
        "CY": ["GR", "MT"],
    }

    def generate(
        self,
        slot_type: str,
        entity_context: Dict[str, Any],
        state: SlotIterationState,
        attempt: int,
    ) -> Optional[str]:
        primary_jur = entity_context.get("jurisdiction", "")
        adjacent = self.ADJACENT_JURISDICTIONS.get(primary_jur.upper(), [])

        if attempt < len(adjacent):
            alt_jur = adjacent[attempt]
            return f"reg{alt_jur.lower()}: {entity_context.get('name', '')}"

        return None


# Strategy registry
QUERY_STRATEGIES: Dict[str, QueryStrategy] = {
    "variation": VariationStrategy(),
    "broaden": BroadeningStrategy(),
    "fallback": FallbackEngineStrategy(),
    "archive": ArchiveStrategy(),
    "jurisdiction_pivot": JurisdictionPivotStrategy(),
}


# ========== SLOT ITERATOR ==========


class SlotIterator:
    """
    Auto-iterates queries for a slot until sufficient or exhausted.

    Strategy:
    1. Start with primary engine and base query
    2. If insufficient, try query variations (name inversions, etc.)
    3. If still insufficient, try fallback engines
    4. If still insufficient, try alternative query approaches (broader/narrower)
    5. Mark as VOID if all attempts exhausted with no results
    """

    def __init__(
        self,
        executor: Optional[Callable] = None,
        variation_generator: Optional[Callable] = None,
    ):
        self._executor = executor
        self._variation_generator = variation_generator
        self._iteration_states: Dict[str, SlotIterationState] = {}

    def _get_or_create_state(
        self, slot_id: str, slot_type: str
    ) -> SlotIterationState:
        if slot_id not in self._iteration_states:
            config = get_slot_config(slot_type)
            self._iteration_states[slot_id] = SlotIterationState(
                slot_id=slot_id,
                slot_type=slot_type,
                config=config,
            )
        return self._iteration_states[slot_id]

    async def fill_slot(
        self,
        slot_id: str,
        slot_type: str,
        entity_context: Dict[str, Any],
    ) -> AsyncGenerator[SlotIterationState, None]:
        """
        Iterate until slot is sufficient or max attempts reached.

        Yields state after each iteration for progress tracking.
        """
        state = self._get_or_create_state(slot_id, slot_type)
        strategies = state.config.strategies or ["variation", "fallback", "broaden"]

        while state.can_iterate() and not state.is_sufficient():
            # Generate next query attempt
            query, engine = self._generate_next_attempt(
                slot_type, entity_context, state, strategies
            )

            if not query:
                logger.info(f"[SlotIterator] No more queries to try for {slot_id}")
                break

            if query in state.queries_tried:
                continue

            # Execute query
            attempt = await self._execute_attempt(
                slot_id, slot_type, query, engine, entity_context, state
            )
            state.record_attempt(attempt)

            # Update slot state based on results
            self._update_slot_state(state, attempt)

            yield state

        # Mark as VOID if exhausted with no results
        if not state.is_sufficient() and not state.can_iterate():
            if state.total_results == 0:
                state.current_status = SlotState.VOID
                logger.info(f"[SlotIterator] Slot {slot_id} marked as VOID after {len(state.attempts)} attempts")

        yield state

    def _generate_next_attempt(
        self,
        slot_type: str,
        entity_context: Dict[str, Any],
        state: SlotIterationState,
        strategies: List[str],
    ) -> Tuple[Optional[str], str]:
        """Generate the next query/engine combination to try."""
        attempt_num = len(state.attempts)

        # Try each strategy in order
        for strategy_name in strategies:
            strategy = QUERY_STRATEGIES.get(strategy_name)
            if not strategy:
                continue

            query = strategy.generate(slot_type, entity_context, state, attempt_num)
            if query:
                # Extract engine from query if specified
                engine = "brute_search"
                if query.startswith("__engine:"):
                    parts = query.split("__", 3)
                    if len(parts) >= 3:
                        engine = parts[1].replace("engine:", "")
                        query = parts[2].strip()

                if query not in state.queries_tried:
                    return query, engine

        return None, "brute_search"

    async def _execute_attempt(
        self,
        slot_id: str,
        slot_type: str,
        query: str,
        engine: str,
        entity_context: Dict[str, Any],
        state: SlotIterationState,
    ) -> IterationAttempt:
        """Execute a single query attempt."""
        logger.info(f"[SlotIterator] Attempt {len(state.attempts) + 1} for {slot_id}: {query} via {engine}")

        attempt = IterationAttempt(
            attempt_number=len(state.attempts) + 1,
            query=query,
            engine=engine,
            timestamp=datetime.utcnow(),
            result_count=0,
            confidence=0.0,
            status="pending",
        )

        if self._executor:
            try:
                result = await self._executor(query, engine, entity_context)
                attempt.result_count = result.get("count", 0)
                attempt.confidence = result.get("confidence", 0.5)
                attempt.status = "success" if attempt.result_count > 0 else "no_results"
            except Exception as e:
                attempt.status = "error"
                attempt.error = str(e)
                logger.error(f"[SlotIterator] Attempt failed: {e}")
        else:
            # Mock execution for testing
            await asyncio.sleep(0.1)
            attempt.status = "no_results"

        return attempt

    def _update_slot_state(
        self, state: SlotIterationState, attempt: IterationAttempt
    ):
        """Update slot state based on attempt results."""
        if state.total_results >= state.config.min_results:
            if state.best_confidence >= state.config.min_confidence:
                state.current_status = SlotState.FILLED
            else:
                state.current_status = SlotState.PARTIAL
        elif state.total_results > 0:
            state.current_status = SlotState.PARTIAL

    def get_methodology_summary(self) -> str:
        """Generate methodology section for report."""
        lines = ["## Research Methodology", ""]

        for state in self._iteration_states.values():
            audit = state.to_audit_log()
            lines.append(f"### {state.slot_id}")
            lines.append(f"- Queries attempted: {audit['total_attempts']}")
            lines.append(f"- Sources consulted: {', '.join(audit['engines_consulted'])}")
            lines.append(f"- Results found: {audit['total_results']}")
            lines.append(f"- Result: {audit['final_result']}")
            lines.append("")

        return "\n".join(lines)
