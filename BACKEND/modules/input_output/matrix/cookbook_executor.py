#!/usr/bin/env python3
"""
Cookbook Executor - Reactive Slot-Based Investigation Engine

This is the MISSING LINK between EDITH templates and IOExecutor.

Instead of hardcoded investigation pipelines, this:
1. Loads cookbook blueprints from compose_for_io_executor()
2. Tracks slot state (filled/empty/pending)
3. Executes sweep phase (initial actions)
4. Triggers cascades when slots fill (for_each patterns)
5. Runs gap fill phase if slots remain empty

The Reactive Loop:
    company_name filled
        → triggers COMPANY_OFFICERS action
        → fills director_name slots
        → for_each director_name triggers SANCTIONS_FROM_NAME
        → fills sanctions_match slots
        → ...continues until all slots filled or dead ends hit

Usage:
    executor = CookbookExecutor()
    result = await executor.execute_dd("UK", "company_dd", "Acme Corp Ltd")
    # Returns filled document with all sections populated

Author: Claude
Date: 2025-12-29
"""

import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Callable

logger = logging.getLogger(__name__)

# Add EDITH templates to path for compose imports
EDITH_SCRIPTS = Path.home() / ".claude" / "skills" / "edith-templates" / "scripts"
if str(EDITH_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(EDITH_SCRIPTS))

# Import compose functions
try:
    from compose import compose_for_io_executor, compose_for_writer
    COMPOSE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import compose: {e}")
    COMPOSE_AVAILABLE = False

# Import cookbook parser for trigger extraction
try:
    from cookbook_parser import CookbookParser
    PARSER_AVAILABLE = True
except ImportError:
    PARSER_AVAILABLE = False

# IOExecutor imported lazily to avoid circular imports
# See _get_executor() method for lazy loading
EXECUTOR_AVAILABLE = True  # Will be checked at runtime

# IOResult and IOStatus can be imported directly (no circular dep)
try:
    from io_result import IOResult, IOStatus
    IO_RESULT_AVAILABLE = True
except ImportError:
    IOResult = None
    IOStatus = None
    IO_RESULT_AVAILABLE = False

# Mined intelligence for dead-end filtering and arbitrage routing
try:
    from mined_intelligence import get_mined_intelligence, MinedIntelligence
    MINED_INTELLIGENCE_AVAILABLE = True
except ImportError:
    get_mined_intelligence = None
    MinedIntelligence = None
    MINED_INTELLIGENCE_AVAILABLE = False
    logger.info("Mined intelligence not available - proceeding without dead-end filtering")


# =============================================================================
# SLOT STATE MANAGEMENT
# =============================================================================

class SlotState(Enum):
    """State of a slot in the investigation."""
    EMPTY = "empty"           # No data yet
    PENDING = "pending"       # Action running to fill this
    FILLED = "filled"         # Has data
    DEAD_END = "dead_end"     # Attempted but no data available
    SKIPPED = "skipped"       # Intentionally skipped (jurisdiction doesn't have this)


@dataclass
class SlotValue:
    """A value in a slot (slots can hold multiple values)."""
    value: Any
    source_url: str = ""
    source_name: str = ""
    confidence: float = 1.0
    filled_at: datetime = field(default_factory=datetime.utcnow)
    filled_by_action: str = ""


@dataclass
class Slot:
    """A named slot that holds investigation data."""
    name: str
    io_field_code: int = 0
    state: SlotState = SlotState.EMPTY
    values: List[SlotValue] = field(default_factory=list)
    required: bool = True
    depends_on: List[str] = field(default_factory=list)  # Other slots this depends on
    triggers: List[str] = field(default_factory=list)     # Actions to trigger when filled

    def fill(self, value: Any, source_url: str = "", source_name: str = "", action: str = ""):
        """Fill this slot with a value."""
        if isinstance(value, list):
            for v in value:
                self.values.append(SlotValue(
                    value=v,
                    source_url=source_url,
                    source_name=source_name,
                    filled_by_action=action
                ))
        else:
            self.values.append(SlotValue(
                value=value,
                source_url=source_url,
                source_name=source_name,
                filled_by_action=action
            ))
        self.state = SlotState.FILLED

    def get_values(self) -> List[Any]:
        """Get all values in this slot."""
        return [sv.value for sv in self.values]

    def is_empty(self) -> bool:
        return self.state == SlotState.EMPTY

    def is_filled(self) -> bool:
        return self.state == SlotState.FILLED and len(self.values) > 0


class SlotManager:
    """
    Manages all slots for an investigation.

    Tracks:
    - Slot states (empty/pending/filled/dead_end)
    - Dependencies between slots
    - Triggers to fire when slots fill
    """

    def __init__(self):
        self.slots: Dict[str, Slot] = {}
        self._watchers: Dict[str, List[Callable]] = {}  # slot_name -> callbacks
        self._trigger_queue: List[tuple] = []  # (action_id, trigger_slot, trigger_values)

    def register_slot(
        self,
        name: str,
        io_field_code: int = 0,
        required: bool = True,
        depends_on: List[str] = None,
        triggers: List[str] = None
    ) -> Slot:
        """Register a new slot."""
        slot = Slot(
            name=name,
            io_field_code=io_field_code,
            required=required,
            depends_on=depends_on or [],
            triggers=triggers or []
        )
        self.slots[name] = slot
        return slot

    def fill_slot(
        self,
        name: str,
        value: Any,
        source_url: str = "",
        source_name: str = "",
        action: str = ""
    ) -> List[str]:
        """
        Fill a slot and return list of triggered actions.

        Returns:
            List of action IDs that should be triggered
        """
        if name not in self.slots:
            self.register_slot(name)

        slot = self.slots[name]
        was_empty = slot.is_empty()
        slot.fill(value, source_url, source_name, action)

        triggered_actions = []

        # If slot was empty and now filled, check triggers
        if was_empty and slot.is_filled():
            # Direct triggers from slot definition
            triggered_actions.extend(slot.triggers)

            # Fire watchers
            if name in self._watchers:
                for callback in self._watchers[name]:
                    try:
                        callback(name, slot.get_values())
                    except Exception as e:
                        logger.error(f"Watcher error for slot {name}: {e}")

            logger.info(f"Slot '{name}' filled with {len(slot.values)} values, triggers: {triggered_actions}")

        return triggered_actions

    def mark_dead_end(self, name: str, reason: str = ""):
        """Mark a slot as a dead end (tried but no data available)."""
        if name not in self.slots:
            self.register_slot(name)
        self.slots[name].state = SlotState.DEAD_END
        logger.info(f"Slot '{name}' marked as dead end: {reason}")

    def mark_pending(self, name: str):
        """Mark a slot as pending (action running)."""
        if name not in self.slots:
            self.register_slot(name)
        self.slots[name].state = SlotState.PENDING

    def get_slot(self, name: str) -> Optional[Slot]:
        """Get a slot by name."""
        return self.slots.get(name)

    def get_slot_values(self, name: str) -> List[Any]:
        """Get all values from a slot."""
        slot = self.slots.get(name)
        return slot.get_values() if slot else []

    def get_empty_required_slots(self) -> List[str]:
        """Get list of required slots that are still empty."""
        return [
            name for name, slot in self.slots.items()
            if slot.required and slot.is_empty()
        ]

    def get_filled_slots(self) -> Dict[str, List[Any]]:
        """Get all filled slots and their values."""
        return {
            name: slot.get_values()
            for name, slot in self.slots.items()
            if slot.is_filled()
        }

    def add_watcher(self, slot_name: str, callback: Callable):
        """Add a callback to be fired when a slot is filled."""
        if slot_name not in self._watchers:
            self._watchers[slot_name] = []
        self._watchers[slot_name].append(callback)

    def get_completion_status(self) -> Dict[str, Any]:
        """Get overall completion status."""
        total = len(self.slots)
        filled = sum(1 for s in self.slots.values() if s.is_filled())
        dead_ends = sum(1 for s in self.slots.values() if s.state == SlotState.DEAD_END)
        empty = sum(1 for s in self.slots.values() if s.is_empty())

        return {
            "total_slots": total,
            "filled": filled,
            "dead_ends": dead_ends,
            "empty": empty,
            "completion_rate": filled / total if total > 0 else 0,
            "empty_required": self.get_empty_required_slots()
        }


# =============================================================================
# TRIGGER ENGINE - Handles for_each cascades
# =============================================================================

@dataclass
class TriggerRule:
    """A rule that triggers when a slot is filled."""
    action_id: str
    watch_slot: str
    for_each: bool = False  # If True, fire once per value in slot
    condition: str = ""      # Optional condition expression
    priority: int = 0        # Higher = run first


class TriggerEngine:
    """
    Manages trigger rules and fires actions when slots fill.

    Handles:
    - Simple triggers (slot filled → run action)
    - for_each triggers (slot filled → run action for EACH value)
    - Conditional triggers (only if condition met)
    """

    def __init__(self, slot_manager: SlotManager):
        self.slot_manager = slot_manager
        self.rules: List[TriggerRule] = []
        self._executed_triggers: Set[str] = set()  # Track what we've already fired

    def add_rule(
        self,
        action_id: str,
        watch_slot: str,
        for_each: bool = False,
        condition: str = "",
        priority: int = 0
    ):
        """Add a trigger rule."""
        rule = TriggerRule(
            action_id=action_id,
            watch_slot=watch_slot,
            for_each=for_each,
            condition=condition,
            priority=priority
        )
        self.rules.append(rule)
        self.rules.sort(key=lambda r: -r.priority)  # Higher priority first

    def get_triggered_actions(self, filled_slot: str) -> List[Dict[str, Any]]:
        """
        Get actions to trigger based on a slot being filled.

        Returns list of dicts with:
        - action_id: Action to run
        - input_values: Values to use as input (for for_each)
        """
        triggered = []
        slot = self.slot_manager.get_slot(filled_slot)
        if not slot or not slot.is_filled():
            return triggered

        for rule in self.rules:
            if rule.watch_slot != filled_slot:
                continue

            # Check condition
            if rule.condition:
                if not self._evaluate_condition(rule.condition):
                    continue

            if rule.for_each:
                # Fire once per value in slot
                for value in slot.get_values():
                    trigger_key = f"{rule.action_id}:{value}"
                    if trigger_key not in self._executed_triggers:
                        triggered.append({
                            "action_id": rule.action_id,
                            "input_value": value,
                            "source_slot": filled_slot
                        })
                        self._executed_triggers.add(trigger_key)
            else:
                # Fire once for whole slot
                trigger_key = f"{rule.action_id}:{filled_slot}"
                if trigger_key not in self._executed_triggers:
                    triggered.append({
                        "action_id": rule.action_id,
                        "input_values": slot.get_values(),
                        "source_slot": filled_slot
                    })
                    self._executed_triggers.add(trigger_key)

        return triggered

    def _evaluate_condition(self, condition: str) -> bool:
        """Evaluate a condition expression."""
        # Simple conditions for now
        if "==" in condition:
            parts = condition.split("==")
            if len(parts) == 2:
                slot_name = parts[0].strip()
                expected = parts[1].strip()
                slot = self.slot_manager.get_slot(slot_name)
                if slot:
                    return str(len(slot.values)) == expected or expected in [str(v) for v in slot.get_values()]
        return True  # Default to true if can't parse


# =============================================================================
# COOKBOOK EXECUTOR - The Main Reactive Engine
# =============================================================================

class CookbookExecutor:
    """
    Executes DD investigations using cookbook blueprints reactively.

    This replaces the hardcoded _company_investigation() with:
    1. Load cookbook blueprint from compose_for_io_executor()
    2. Register all slots from cookbooks
    3. Set up triggers from cookbook flows
    4. Execute sweep phase (initial actions)
    5. Process trigger queue (cascades)
    6. Run gap fill phase if needed
    """

    def __init__(self, project_id: str = None):
        self.project_id = project_id
        self.slot_manager = SlotManager()
        self.trigger_engine = TriggerEngine(self.slot_manager)
        self._io_executor = None  # Lazy loaded to avoid circular imports
        self._blueprint: Optional[Dict] = None
        self._execution_log: List[Dict] = []

    def _get_executor(self):
        """Lazy load IOExecutor to avoid circular imports."""
        if self._io_executor is None:
            try:
                from io_executor import IOExecutor
                self._io_executor = IOExecutor(project_id=self.project_id)
            except ImportError as e:
                raise RuntimeError(f"IOExecutor not available: {e}")
        return self._io_executor

    async def execute_dd(
        self,
        jurisdiction: str,
        genre: str,
        entity: str,
        initial_slots: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Execute a full DD investigation using cookbook blueprints.

        Args:
            jurisdiction: Jurisdiction code (e.g., "UK")
            genre: Genre ID (e.g., "company_dd")
            entity: Entity name (e.g., "Acme Corp Ltd")
            initial_slots: Pre-filled slots (e.g., {"company_name": "Acme Corp"})

        Returns:
            Dict with:
            - sections: Filled section data
            - slots: Final slot state
            - completion: Completion status
            - execution_log: What actions ran
        """
        start_time = datetime.utcnow()

        # 1. Load blueprint
        if not COMPOSE_AVAILABLE:
            return {"error": "compose module not available"}

        self._blueprint = compose_for_io_executor(jurisdiction, genre, entity)
        if "error" in self._blueprint:
            return self._blueprint

        logger.info(f"Loaded blueprint for {genre} in {jurisdiction}: {len(self._blueprint.get('cookbooks', []))} sections")

        # 2. Register slots and triggers from cookbooks
        self._register_from_blueprint()

        # 3. Fill initial slots
        if initial_slots:
            for slot_name, value in initial_slots.items():
                self.slot_manager.fill_slot(slot_name, value, action="initial")

        # Always fill entity slot
        entity_slot = "company_name" if "company" in genre else "person_name"
        self.slot_manager.fill_slot(entity_slot, entity, action="initial_entity")
        self.slot_manager.fill_slot("jurisdiction", jurisdiction, action="initial_jurisdiction")

        # 4. Execute sweep phase
        await self._execute_sweep_phase()

        # 5. Process trigger queue until empty
        await self._process_triggers()

        # 6. Gap fill phase
        await self._execute_gap_fill_phase()

        # 7. Build result
        end_time = datetime.utcnow()

        return {
            "jurisdiction": jurisdiction,
            "genre": genre,
            "entity": entity,
            "sections": self._build_section_results(),
            "slots": self.slot_manager.get_filled_slots(),
            "completion": self.slot_manager.get_completion_status(),
            "execution_log": self._execution_log,
            "execution_time_ms": int((end_time - start_time).total_seconds() * 1000)
        }

    def _register_from_blueprint(self):
        """Register slots and triggers from cookbook blueprint."""
        if not self._blueprint:
            return

        for cookbook in self._blueprint.get("cookbooks", []):
            section_id = cookbook.get("section_id", "")

            # Register slots from slot_extraction_rules
            for rule in cookbook.get("slot_extraction_rules", []):
                slot_name = rule.get("slot_name") or rule.get("name", "")
                if slot_name:
                    self.slot_manager.register_slot(
                        name=slot_name,
                        io_field_code=rule.get("io_field", 0),
                        required=rule.get("required", True)
                    )

            # Register triggers from flows
            for flow in cookbook.get("flows", []):
                # Check for for_each triggers
                triggers = flow.get("triggers", [])
                if isinstance(triggers, list):
                    for trigger in triggers:
                        if isinstance(trigger, dict) and "for_each" in trigger:
                            watch_slot = trigger["for_each"]
                            action_id = flow.get("action") or flow.get("rule_id", "")
                            if action_id and watch_slot:
                                self.trigger_engine.add_rule(
                                    action_id=action_id,
                                    watch_slot=watch_slot,
                                    for_each=True
                                )
                                logger.debug(f"Registered for_each trigger: {watch_slot} -> {action_id}")

            # Register required_actions as sweep actions
            for action in cookbook.get("required_actions", []):
                # These will be executed in sweep phase
                pass

    async def _execute_sweep_phase(self):
        """Execute initial sweep actions from all cookbooks."""
        if not self._blueprint:
            return

        executor = self._get_executor()
        entity = self._blueprint.get("entity", "")
        jurisdiction = self._blueprint.get("jurisdiction", "")

        logger.info(f"Starting sweep phase for {entity} in {jurisdiction}")

        for cookbook in self._blueprint.get("cookbooks", []):
            section_id = cookbook.get("section_id", "")
            required_actions = cookbook.get("required_actions", [])

            for action_id in required_actions:
                if not action_id:
                    continue

                # Dead-end filtering: skip known-failing actions
                if MINED_INTELLIGENCE_AVAILABLE:
                    mi = get_mined_intelligence()
                    is_dead, reason = mi.is_dead_end(action_id, jurisdiction)
                    if is_dead:
                        logger.info(f"Skipping dead-end action {action_id} in {jurisdiction}: {reason}")
                        self._log_execution(action_id, "skipped_dead_end", section_id, reason)

                        # Try arbitrage alternatives
                        alternatives = mi.suggest_arbitrage(jurisdiction, action_id)
                        if alternatives:
                            logger.info(f"Found {len(alternatives)} arbitrage alternatives for {action_id}")
                            for alt in alternatives[:2]:  # Try top 2 alternatives
                                alt_jurisdiction = alt.get("source_jurisdiction", "")
                                if alt_jurisdiction and alt_jurisdiction != jurisdiction:
                                    logger.info(f"Trying arbitrage via {alt_jurisdiction}: {alt.get('source_registry')}")
                                    try:
                                        result = await executor.execute(action_id, entity, alt_jurisdiction)
                                        if result and hasattr(result, 'success') and result.success:
                                            self._extract_slots_from_result(result, cookbook)
                                            self._log_execution(action_id, "arbitrage_success", section_id,
                                                              f"via {alt_jurisdiction}")
                                            break
                                    except Exception as arb_e:
                                        logger.debug(f"Arbitrage attempt failed: {arb_e}")
                        continue  # Skip direct execution of dead-end action

                self._log_execution(action_id, "sweep", section_id)

                try:
                    # Mark relevant slots as pending
                    # Execute action
                    result = await executor.execute(action_id, entity, jurisdiction)

                    # Extract slots from result
                    self._extract_slots_from_result(result, cookbook)

                except Exception as e:
                    logger.error(f"Sweep action {action_id} failed: {e}")
                    self._log_execution(action_id, "error", section_id, str(e))

    async def _process_triggers(self, max_iterations: int = 100):
        """Process trigger queue until empty or max iterations."""
        executor = self._get_executor()
        jurisdiction = self._blueprint.get("jurisdiction", "") if self._blueprint else ""

        iterations = 0
        while iterations < max_iterations:
            iterations += 1

            # Get all newly triggered actions
            all_triggered = []
            for slot_name, slot in self.slot_manager.slots.items():
                if slot.is_filled():
                    triggered = self.trigger_engine.get_triggered_actions(slot_name)
                    all_triggered.extend(triggered)

            if not all_triggered:
                break  # No more triggers

            logger.info(f"Processing {len(all_triggered)} triggered actions (iteration {iterations})")

            for trigger in all_triggered:
                action_id = trigger.get("action_id")
                input_value = trigger.get("input_value")
                source_slot = trigger.get("source_slot", "")

                if not action_id:
                    continue

                self._log_execution(action_id, "trigger", source_slot, f"from {source_slot}")

                try:
                    # Execute with the triggered input value
                    entity = input_value if input_value else self._blueprint.get("entity", "")
                    result = await executor.execute(action_id, str(entity), jurisdiction)

                    # Extract slots from result
                    self._extract_slots_from_result(result, None)

                except Exception as e:
                    logger.error(f"Triggered action {action_id} failed: {e}")

        if iterations >= max_iterations:
            logger.warning(f"Trigger processing hit max iterations ({max_iterations})")

    async def _execute_gap_fill_phase(self):
        """Execute gap fill actions for empty required slots."""
        empty_slots = self.slot_manager.get_empty_required_slots()
        if not empty_slots:
            logger.info("No empty required slots, skipping gap fill")
            return

        logger.info(f"Gap fill phase: {len(empty_slots)} empty required slots")

        if not self._blueprint:
            return

        executor = self._get_executor()
        entity = self._blueprint.get("entity", "")
        jurisdiction = self._blueprint.get("jurisdiction", "")

        # Find gap fill actions from cookbooks
        for cookbook in self._blueprint.get("cookbooks", []):
            for flow in cookbook.get("flows", []):
                # Check if this is a gap fill flow
                condition = flow.get("condition") or ""
                description = flow.get("description") or ""
                if "== 0" in condition or "gap" in description.lower():
                    action_id = flow.get("action") or flow.get("rule_id", "")
                    if action_id:
                        self._log_execution(action_id, "gap_fill", cookbook.get("section_id", ""))

                        try:
                            result = await executor.execute(action_id, entity, jurisdiction)
                            self._extract_slots_from_result(result, cookbook)
                        except Exception as e:
                            logger.error(f"Gap fill action {action_id} failed: {e}")

    def _extract_slots_from_result(self, result, cookbook: Optional[Dict]):
        """Extract slot values from an IOResult or dict.

        Handles both:
        - IOResult objects (from io_executor)
        - Plain dicts (fallback)
        """
        if not result:
            return

        # Handle both IOResult and dict
        if IO_RESULT_AVAILABLE and hasattr(result, 'status'):
            # It's an IOResult
            if result.status != IOStatus.SUCCESS:
                return
            data = result.data or {}
            source_url = result.source_url or ""
            source_name = result.source_name or ""
            action = result.route_id or ""
        elif isinstance(result, dict):
            # Plain dict result
            if result.get('status') not in ('success', 'SUCCESS', None):
                if result.get('error'):
                    return  # Error result
            data = result.get('data', result)  # Data might be nested or at root
            source_url = result.get('source_url', '')
            source_name = result.get('source_name', '')
            action = result.get('route_id', '')
        else:
            return

        # Extract based on cookbook slot_extraction_rules if provided
        if cookbook:
            for rule in cookbook.get("slot_extraction_rules", []):
                slot_name = rule.get("slot_name") or rule.get("name", "")
                data_field = rule.get("extract_from") or slot_name

                if slot_name and data_field in data:
                    triggered = self.slot_manager.fill_slot(
                        slot_name,
                        data[data_field],
                        source_url=source_url,
                        source_name=source_name,
                        action=action
                    )

        # Also extract any data that matches known slot names
        for key, value in data.items():
            if value and key not in self.slot_manager.slots:
                self.slot_manager.register_slot(key, required=False)
            if value:
                self.slot_manager.fill_slot(
                    key,
                    value,
                    source_url=source_url,
                    source_name=source_name,
                    action=action
                )

    def _build_section_results(self) -> Dict[str, Dict]:
        """Build section results from filled slots."""
        sections = {}

        if not self._blueprint:
            return sections

        for cookbook in self._blueprint.get("cookbooks", []):
            section_id = cookbook.get("section_id", "")
            title = cookbook.get("title", section_id)

            # Gather slots relevant to this section
            section_slots = {}
            for rule in cookbook.get("slot_extraction_rules", []):
                slot_name = rule.get("slot_name") or rule.get("name", "")
                if slot_name:
                    slot = self.slot_manager.get_slot(slot_name)
                    if slot and slot.is_filled():
                        section_slots[slot_name] = {
                            "values": slot.get_values(),
                            "sources": [
                                {"url": sv.source_url, "name": sv.source_name}
                                for sv in slot.values
                            ]
                        }

            sections[section_id] = {
                "title": title,
                "slots": section_slots,
                "status": "complete" if section_slots else "empty"
            }

        return sections

    def _log_execution(self, action_id: str, phase: str, section: str, note: str = ""):
        """Log an execution event."""
        self._execution_log.append({
            "action_id": action_id,
            "phase": phase,
            "section": section,
            "note": note,
            "timestamp": datetime.utcnow().isoformat()
        })


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def execute_company_dd(
    jurisdiction: str,
    company_name: str,
    project_id: str = None
) -> Dict[str, Any]:
    """
    Execute a company DD investigation.

    This is the replacement for the hardcoded _company_investigation().
    """
    executor = CookbookExecutor(project_id=project_id)
    return await executor.execute_dd(
        jurisdiction=jurisdiction,
        genre="company_dd",
        entity=company_name,
        initial_slots={"company_name": company_name}
    )


async def execute_person_dd(
    jurisdiction: str,
    person_name: str,
    project_id: str = None
) -> Dict[str, Any]:
    """Execute a person DD investigation."""
    executor = CookbookExecutor(project_id=project_id)
    return await executor.execute_dd(
        jurisdiction=jurisdiction,
        genre="person_dd",
        entity=person_name,
        initial_slots={"person_name": person_name}
    )


# =============================================================================
# CLI
# =============================================================================

async def main():
    """CLI for testing CookbookExecutor."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Cookbook Executor - Reactive DD Investigation Engine"
    )
    parser.add_argument("entity", help="Entity name (company or person)")
    parser.add_argument("-j", "--jurisdiction", required=True, help="Jurisdiction code (e.g., UK)")
    parser.add_argument("-g", "--genre", default="company_dd", help="Genre (company_dd, person_dd)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")

    args = parser.parse_args()

    if args.dry_run:
        # Just show the blueprint
        if COMPOSE_AVAILABLE:
            blueprint = compose_for_io_executor(args.jurisdiction, args.genre, args.entity)
            print(json.dumps(blueprint, indent=2))
        else:
            print("compose module not available")
        return

    executor = CookbookExecutor()
    result = await executor.execute_dd(
        jurisdiction=args.jurisdiction,
        genre=args.genre,
        entity=args.entity
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"\n{'='*60}")
        print(f"DD Investigation: {args.entity} ({args.jurisdiction})")
        print(f"{'='*60}\n")

        completion = result.get("completion", {})
        print(f"Completion: {completion.get('filled', 0)}/{completion.get('total_slots', 0)} slots filled")
        print(f"Dead ends: {completion.get('dead_ends', 0)}")
        print(f"Execution time: {result.get('execution_time_ms', 0)}ms")

        print(f"\n{'='*60}")
        print("SECTIONS:")
        print(f"{'='*60}\n")

        for section_id, section in result.get("sections", {}).items():
            status = section.get("status", "unknown")
            slot_count = len(section.get("slots", {}))
            print(f"  [{status.upper()}] {section.get('title', section_id)} ({slot_count} slots)")

        print(f"\n{'='*60}")
        print("EXECUTION LOG:")
        print(f"{'='*60}\n")

        for log in result.get("execution_log", [])[-20:]:
            print(f"  [{log.get('phase')}] {log.get('action_id')} - {log.get('section')} {log.get('note', '')}")


if __name__ == "__main__":
    asyncio.run(main())
