"""
Generative Watcher Creator
==========================

Uses LLM to automatically generate watchers from:
1. Hungry slots (empty mandatory fields)
2. Narrative goal (investigation questions)
3. Template sections (EDITH patterns)
4. Entity context (what we know so far)

ARCHITECTURE:
┌─────────────────────────────────────────────────────────────────────────────┐
│                    GENERATIVE WATCHER FLOW                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  INPUTS:                                                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ Hungry      │  │ Narrative   │  │ Template    │  │ Entity      │        │
│  │ Slots       │  │ Goal        │  │ Sections    │  │ Context     │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                │                │
│         └────────────────┼────────────────┼────────────────┘                │
│                          │                │                                 │
│                          ▼                ▼                                 │
│                    ┌─────────────────────────────┐                          │
│                    │      LLM GENERATOR          │                          │
│                    │  (Haiku / GPT-5-mini)       │                          │
│                    └──────────────┬──────────────┘                          │
│                                   │                                         │
│                                   ▼                                         │
│                    ┌─────────────────────────────┐                          │
│                    │    GENERATED WATCHERS       │                          │
│                    │  • Quote watchers           │                          │
│                    │  • Event watchers           │                          │
│                    │  • Topic watchers           │                          │
│                    │  • Entity watchers          │                          │
│                    └─────────────────────────────┘                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Literal
import json
import os
from datetime import datetime

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    import openai
except ImportError:
    openai = None


# =============================================================================
# CONSTANTS
# =============================================================================

# Event types (from ET3)
EVENT_TYPES = [
    "evt_ipo", "evt_acquisition", "evt_merger", "evt_bankruptcy",
    "evt_lawsuit", "evt_investigation", "evt_sanctions", "evt_arrest",
    "evt_resignation", "evt_appointment", "evt_regulatory_action",
    "evt_data_breach", "evt_layoffs", "evt_funding_round",
]

# Topic types (from ET3)
TOPIC_TYPES = [
    "top_sanctions", "top_corruption", "top_money_laundering",
    "top_fraud", "top_bribery", "top_tax_evasion", "top_offshore",
    "top_shell_company", "top_beneficial_ownership", "top_pep",
    "top_compliance", "top_regulatory", "top_litigation",
]

# Common slot types that suggest watcher patterns
SLOT_TO_WATCHER_HINTS = {
    "dob": "What is {entity}'s date of birth?",
    "date_of_birth": "What is {entity}'s date of birth?",
    "nationality": "What is {entity}'s nationality?",
    "address": "What is {entity}'s address?",
    "email": "What is {entity}'s email address?",
    "phone": "What is {entity}'s phone number?",
    "role": "What is {entity}'s role or position?",
    "title": "What is {entity}'s title?",
    "company": "What companies is {entity} associated with?",
    "employer": "Who is {entity}'s employer?",
    "director_of": "What companies is {entity} a director of?",
    "shareholder_of": "What companies does {entity} own shares in?",
    "beneficial_owner": "Who is the beneficial owner of {entity}?",
    "ubo": "Who is the ultimate beneficial owner of {entity}?",
    "registration_number": "What is {entity}'s registration number?",
    "jurisdiction": "In what jurisdiction is {entity} registered?",
    "incorporation_date": "When was {entity} incorporated?",
    "registered_agent": "Who is {entity}'s registered agent?",
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class GenerativeWatcherRequest:
    """Request for AI to generate watchers."""
    
    # Context for generation
    narrative_goal: str  # What are we trying to find out?
    known_subjects: List[str] = field(default_factory=list)  # Known entities
    known_locations: List[str] = field(default_factory=list)  # Known sources/jurisdictions
    
    # Hungry slots (slots without values)
    hungry_slots: List[Dict[str, str]] = field(default_factory=list)
    # Each: {"entity_id": "...", "entity_name": "...", "slot_name": "...", "slot_id": "..."}
    
    # Template guidance
    template_sections: Optional[List[str]] = None  # EDITH template sections
    
    # Generation constraints
    max_watchers: int = 10
    watcher_types: List[str] = field(default_factory=lambda: ["quote", "event", "topic", "entity"])


@dataclass
class GeneratedWatcher:
    """AI-generated watcher specification."""
    
    label: str
    watcher_type: Literal["quote", "event", "topic", "entity"]
    rationale: str  # Why this watcher was created
    
    # Type-specific config
    monitored_event: Optional[str] = None
    monitored_topic: Optional[str] = None
    monitored_types: Optional[List[str]] = None
    monitored_names: Optional[List[str]] = None
    
    # Slot binding (if generated from hungry slot)
    target_entity_id: Optional[str] = None
    target_slot_id: Optional[str] = None
    
    # Priority
    priority: int = 0


@dataclass
class GenerativeWatcherResult:
    """Result of generative watcher creation."""
    
    watchers: List[GeneratedWatcher] = field(default_factory=list)
    
    # Stats
    from_slots: int = 0
    from_narrative: int = 0
    from_template: int = 0
    
    # Metadata
    model_used: str = ""
    generation_time_ms: int = 0


# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

SYSTEM_PROMPT = """You are an investigative intelligence analyst. Your task is to generate watchers (extraction questions) for an investigation.

A watcher is a question that will be run against search results to extract specific information.

WATCHER TYPES:
1. QUOTE watchers: Plain text questions (e.g., "What is John Smith's date of birth?")
2. EVENT watchers: Monitor for specific event types (e.g., IPO, lawsuit, sanctions)
3. TOPIC watchers: Monitor for topic associations (e.g., corruption, money laundering)
4. ENTITY watchers: Monitor for entity types/names (e.g., persons, companies)

EVENT TYPES: {event_types}

TOPIC TYPES: {topic_types}

OUTPUT FORMAT:
Return a JSON array of watchers, each with:
{{
  "label": "The watcher question/description",
  "watcher_type": "quote" | "event" | "topic" | "entity",
  "rationale": "Why this watcher is relevant",
  "monitored_event": "evt_xxx (for event watchers)",
  "monitored_topic": "top_xxx (for topic watchers)",
  "monitored_types": ["person", "company"] (for entity watchers),
  "monitored_names": ["specific names"] (for entity watchers),
  "target_entity_id": "entity ID if slot-bound",
  "target_slot_id": "slot ID if slot-bound",
  "priority": 0-10 (higher = more important)
}}

Generate watchers that will help answer the investigation goal."""

USER_PROMPT_TEMPLATE = """INVESTIGATION GOAL:
{narrative_goal}

KNOWN ENTITIES:
{known_subjects}

KNOWN SOURCES/JURISDICTIONS:
{known_locations}

HUNGRY SLOTS (empty fields that need values):
{hungry_slots}

TEMPLATE SECTIONS (if applicable):
{template_sections}

Generate up to {max_watchers} watchers to help fill these gaps.
Focus on {watcher_types} watchers.

Return ONLY valid JSON array, no other text."""


# =============================================================================
# GENERATOR CLASS
# =============================================================================

class GenerativeWatcherCreator:
    """
    Creates watchers using LLM.
    
    Supports:
    - Claude Haiku 4.5 (Anthropic)
    - GPT-5-mini (OpenAI)
    """
    
    def __init__(
        self,
        anthropic_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        preferred_model: str = "haiku",  # "haiku" or "gpt"
    ):
        self.anthropic_api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        self.preferred_model = preferred_model
        
        # Initialize clients
        self._anthropic_client = None
        self._openai_client = None
        
        if anthropic and self.anthropic_api_key:
            self._anthropic_client = anthropic.Anthropic(api_key=self.anthropic_api_key)
        
        if openai and self.openai_api_key:
            self._openai_client = openai.OpenAI(api_key=self.openai_api_key)
    
    async def generate(self, request: GenerativeWatcherRequest) -> GenerativeWatcherResult:
        """
        Generate watchers from request.
        
        First tries rule-based generation for hungry slots,
        then uses LLM for narrative-driven and template-driven watchers.
        """
        start_time = datetime.now()
        result = GenerativeWatcherResult()
        
        # 1. Rule-based generation from hungry slots
        slot_watchers = self._generate_from_slots(request.hungry_slots)
        result.watchers.extend(slot_watchers)
        result.from_slots = len(slot_watchers)
        
        # 2. LLM generation for remaining watchers
        remaining = request.max_watchers - len(result.watchers)
        if remaining > 0:
            llm_watchers = await self._generate_with_llm(request, remaining)
            result.watchers.extend(llm_watchers)
            result.from_narrative = len([w for w in llm_watchers if not w.target_slot_id])
            result.from_template = len([w for w in llm_watchers if w.target_slot_id])
        
        # Record timing
        result.generation_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return result
    
    def _generate_from_slots(self, hungry_slots: List[Dict[str, str]]) -> List[GeneratedWatcher]:
        """
        Rule-based generation from hungry slots.
        
        Uses SLOT_TO_WATCHER_HINTS to create appropriate questions.
        """
        watchers = []
        
        for slot in hungry_slots:
            slot_name = slot.get("slot_name", "").lower()
            entity_name = slot.get("entity_name", "unknown entity")
            entity_id = slot.get("entity_id", "")
            slot_id = slot.get("slot_id", "")
            
            # Check for hint
            hint_template = None
            for key, template in SLOT_TO_WATCHER_HINTS.items():
                if key in slot_name:
                    hint_template = template
                    break
            
            if hint_template:
                label = hint_template.format(entity=entity_name)
            else:
                # Generic question
                label = f"What is {entity_name}'s {slot_name.replace('_', ' ')}?"
            
            watcher = GeneratedWatcher(
                label=label,
                watcher_type="quote",
                rationale=f"Generated from hungry slot: {slot_name}",
                target_entity_id=entity_id,
                target_slot_id=slot_id,
                priority=5,  # Medium priority for slot-derived
            )
            watchers.append(watcher)
        
        return watchers
    
    async def _generate_with_llm(
        self,
        request: GenerativeWatcherRequest,
        max_count: int,
    ) -> List[GeneratedWatcher]:
        """Generate watchers using LLM."""
        
        # Build prompts
        system = SYSTEM_PROMPT.format(
            event_types=", ".join(EVENT_TYPES),
            topic_types=", ".join(TOPIC_TYPES),
        )
        
        user = USER_PROMPT_TEMPLATE.format(
            narrative_goal=request.narrative_goal,
            known_subjects="\n".join(f"- {s}" for s in request.known_subjects) or "None",
            known_locations="\n".join(f"- {l}" for l in request.known_locations) or "None",
            hungry_slots="\n".join(
                f"- {s['entity_name']}.{s['slot_name']}" for s in request.hungry_slots
            ) or "None",
            template_sections="\n".join(f"- {t}" for t in (request.template_sections or [])) or "None",
            max_watchers=max_count,
            watcher_types=", ".join(request.watcher_types),
        )
        
        # Call LLM
        response_text = await self._call_llm(system, user)
        
        # Parse response
        return self._parse_llm_response(response_text)
    
    async def _call_llm(self, system: str, user: str) -> str:
        """Call preferred LLM."""
        
        if self.preferred_model == "haiku" and self._anthropic_client:
            return await self._call_anthropic(system, user)
        elif self.preferred_model == "gpt" and self._openai_client:
            return await self._call_openai(system, user)
        elif self._anthropic_client:
            return await self._call_anthropic(system, user)
        elif self._openai_client:
            return await self._call_openai(system, user)
        else:
            raise RuntimeError("No LLM client available")
    
    async def _call_anthropic(self, system: str, user: str) -> str:
        """Call Claude Haiku."""
        import asyncio
        
        # Run sync client in executor
        def call():
            response = self._anthropic_client.messages.create(
                model="claude-haiku-4-5-20241022",
                max_tokens=2048,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, call)
    
    async def _call_openai(self, system: str, user: str) -> str:
        """Call GPT-5-mini."""
        import asyncio
        
        # Run sync client in executor
        def call():
            response = self._openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Using gpt-4o-mini as stand-in
                max_tokens=2048,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return response.choices[0].message.content
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, call)
    
    def _parse_llm_response(self, response: str) -> List[GeneratedWatcher]:
        """Parse LLM JSON response into GeneratedWatcher objects."""
        watchers = []
        
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            
            data = json.loads(json_str.strip())
            
            if not isinstance(data, list):
                data = [data]
            
            for item in data:
                watcher = GeneratedWatcher(
                    label=item.get("label", ""),
                    watcher_type=item.get("watcher_type", "quote"),
                    rationale=item.get("rationale", ""),
                    monitored_event=item.get("monitored_event"),
                    monitored_topic=item.get("monitored_topic"),
                    monitored_types=item.get("monitored_types"),
                    monitored_names=item.get("monitored_names"),
                    target_entity_id=item.get("target_entity_id"),
                    target_slot_id=item.get("target_slot_id"),
                    priority=item.get("priority", 0),
                )
                watchers.append(watcher)
        
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            # Log error but don't fail
            print(f"Failed to parse LLM response: {e}")
        
        return watchers


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def generate_watchers_from_slots(
    hungry_slots: List[Dict[str, str]],
    narrative_goal: str = "",
    max_watchers: int = 10,
) -> List[GeneratedWatcher]:
    """
    Generate watchers from hungry slots.
    
    Convenience function for common use case.
    """
    request = GenerativeWatcherRequest(
        narrative_goal=narrative_goal,
        hungry_slots=hungry_slots,
        max_watchers=max_watchers,
        watcher_types=["quote"],  # Slots → quote watchers
    )
    
    creator = GenerativeWatcherCreator()
    result = await creator.generate(request)
    
    return result.watchers


async def generate_watchers_from_narrative(
    narrative_goal: str,
    known_subjects: List[str],
    known_locations: List[str],
    max_watchers: int = 10,
    watcher_types: Optional[List[str]] = None,
) -> List[GeneratedWatcher]:
    """
    Generate watchers from narrative goal.
    
    Uses LLM to suggest relevant watchers.
    """
    request = GenerativeWatcherRequest(
        narrative_goal=narrative_goal,
        known_subjects=known_subjects,
        known_locations=known_locations,
        max_watchers=max_watchers,
        watcher_types=watcher_types or ["quote", "event", "topic", "entity"],
    )
    
    creator = GenerativeWatcherCreator()
    result = await creator.generate(request)
    
    return result.watchers


def generate_watchers_from_slots_sync(
    hungry_slots: List[Dict[str, str]],
) -> List[GeneratedWatcher]:
    """
    Synchronous, rule-based generation from slots only.
    
    No LLM call - uses SLOT_TO_WATCHER_HINTS.
    """
    creator = GenerativeWatcherCreator()
    return creator._generate_from_slots(hungry_slots)
