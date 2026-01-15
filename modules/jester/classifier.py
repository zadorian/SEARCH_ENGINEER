import json
import logging
import asyncio
import anthropic
import openai
from elastic_manager import ElasticManager
from dotenv import load_dotenv
import sys
import os

# Model Constants
GPT_5_NANO = "gpt-5-nano"
CLAUDE_HAIKU_4_5 = "claude-4.5-haiku"

def get_claude_model():
    return "claude-4.5-sonnet"

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Classifier")

class Classifier:
    def __init__(self, topics, tier="smart", alias_map=None, index_name="jester_atoms"):
        self.elastic = ElasticManager(index_name=index_name)
        self.topics = topics
        self.tier = tier
        self.alias_map = alias_map or {}
        self.client = None
        self.smart_client = None
        self.smart_model = None
        
        # --- Primary Client Setup ---
        if self.tier == "fast":
            self.model_name = GPT_5_NANO
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                self.client = openai.AsyncOpenAI(api_key=api_key)
                logger.info(f"Initialized FAST mode with {self.model_name}")
            else:
                logger.error("No OpenAI API Key found! Fast mode will not function.")

            # Smart fallback setup
            try:
                self.smart_model = get_claude_model()
                anthropic_key = os.getenv('ANTHROPIC_API_KEY')
                if anthropic_key:
                    self.smart_client = anthropic.AsyncAnthropic(api_key=anthropic_key)
            except Exception as e:

                print(f"[Classifier] Error: {e}")

                pass

        elif self.tier == "haiku":
            self.model_name = CLAUDE_HAIKU_4_5
            api_key = os.getenv('ANTHROPIC_API_KEY')
            if api_key:
                self.client = anthropic.AsyncAnthropic(api_key=api_key)
                logger.info(f"Initialized HAIKU mode with {self.model_name}")
            else:
                logger.error("No Anthropic API Key found! Haiku mode will not function.")

        else: # Default: smart
            try:
                self.model_name = get_claude_model()
                logger.info(f"Using centralized model constant: {self.model_name}")
            except Exception as e:
                logger.warning(f"Could not load constants: {e}")
                self.model_name = "claude-3-5-sonnet-20241022" # Safer fallback

            api_key = os.getenv('ANTHROPIC_API_KEY')
            if api_key:
                self.client = anthropic.AsyncAnthropic(api_key=api_key)
                logger.info(f"Initialized SMART mode with {self.model_name}")
            else:
                logger.error("No Anthropic API Key found! Smart mode will not function.")
        
        # Create the mapping Prompt
        if isinstance(topics, dict):
            self.topic_keys = list(topics.keys())
            self.topic_map_str = "\n".join([f"{i+1}. {k}: {v}" for i, (k, v) in enumerate(topics.items())])
        else:
            self.topic_keys = topics
            self.topic_map_str = "\n".join([f"{i+1}. {t}" for i, t in enumerate(topics)])

    async def _call_model(self, client, model_name, system_prompt, user_message, is_openai=False):
        """Helper to call appropriate API"""
        if not client:
            raise ValueError("Client not initialized (missing API Key)")

        if is_openai:
            response = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                response_format={"type": "json_object"},
                reasoning_effort="low",
                verbosity="low" 
            )
            return response.choices[0].message.content.strip()
        else:
            # Anthropic Call with Prompt Caching
            message = await client.messages.create(
                model=model_name,
                max_tokens=1024,
                temperature=0,
                system=[
                    {
                        "type": "text", 
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"}
                    }
                ],
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )
            return message.content[0].text.strip()

    async def classify_atom(self, atom):
        if not self.client:
            logger.error(f"Skipping classification for atom {atom['atom_id']}: Client not ready")
            return {}, "error"

        # Move static context (Topics + Aliases) to System Prompt
        static_context = f'''
TOPIC DEFINITIONS:
{self.topic_map_str}

ALIAS MAP (Known Entity Aliases):
"""
{json.dumps(self.alias_map, indent=2) if self.alias_map else "None provided."} 
"""
'''
        system_prompt = f"You are a strict classification and extraction engine. Your ONLY output must be a valid JSON object.\n\n{static_context}"
        
        user_message = f'''
PREVIOUS CONTEXT:
"""
{atom.get('previous_context', '')}
"""

CURRENT TEXT:
"""
{atom['content']}
"""

INSTRUCTIONS:
- Return a JSON object with keys: "topics" (int array) and "entities" (object array).
- "entities" format: {{"text": "String", "label": "TYPE"}}.
- Resolve pronouns using PREVIOUS CONTEXT.
- Match topics based on DEFINITIONS.
- If no match, topics is [].
'''
        try:
            # Primary Call
            is_openai = (self.tier == "fast")
            text = await self._call_model(self.client, self.model_name, system_prompt, user_message, is_openai)
            
            # Parse
            data = self._parse_json(text)
            
            # SMART ESCALATION
            if self.tier == "fast" and not data.get("topics") and self.smart_client:
                if len(atom['content']) > 50:
                    logger.info(f"Atom {atom['atom_id']} unassigned. Escalating to Smart tier...")
                    try:
                        text_smart = await self._call_model(self.smart_client, self.smart_model, system_prompt, user_message, is_openai=False)
                        data_smart = self._parse_json(text_smart)
                        if data_smart.get("topics"):
                            logger.info(f"Atom {atom['atom_id']} rescued by Smart tier!")
                            data = data_smart
                    except Exception as e:
                        logger.warning(f"Smart escalation failed: {e}")
            
            topic_indexes = data.get("topics", [])
            entities = data.get("entities", [])

            assigned_topics = []
            for i in topic_indexes:
                if isinstance(i, int) and 0 < i <= len(self.topic_keys):
                    assigned_topics.append(self.topic_keys[i-1])
            
            status = "classified" if assigned_topics else "unassigned"
            
            logger.info(f"Atom {atom['atom_id']} -> {assigned_topics} | {len(entities)} entities")
            return {"topics": assigned_topics, "entities": entities}, status

        except Exception as e:
            logger.error(f"Error classifying atom {atom['atom_id']}: {e}")
            await asyncio.sleep(1)
            return {}, "error"

    def _parse_json(self, text):
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1].replace("json", "").strip()
            else:
                    text = text.replace("```", "")
        try:
            return json.loads(text)
        except Exception as e:
            return {}

    async def run_batch(self, batch_size=20):
        atoms = self.elastic.get_pending_atoms(limit=batch_size)
        if not atoms:
            logger.info("No pending atoms.")
            return 0

        logger.info(f"Processing batch of {len(atoms)} atoms...")
        tasks = []
        for atom in atoms:
            tasks.append(self.process_atom(atom))
        
        await asyncio.gather(*tasks)
        return len(atoms)

    async def process_atom(self, atom):
        result, status = await self.classify_atom(atom)
        topics = result.get("topics", [])
        entities = result.get("entities", [])

        self.elastic.update_atom_status(
            atom_id=atom['atom_id'],
            topics=topics,
            entities=entities,
            status=status
        )


# Standalone Entity Confidence Scorer
class EntityConfidenceScorer:
    """
    Lightweight entity validation using AI models.
    Used by Linklater to validate regex-extracted entities.
    """

    def __init__(self, tier: str = "fast"):
        self.tier = tier
        self.client = None
        self.model_name = None

        if tier == "fast":
            self.model_name = GPT_5_NANO
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                self.client = openai.AsyncOpenAI(api_key=api_key)
        else:
            try:
                self.model_name = get_claude_model()
            except Exception as e:
                self.model_name = "claude-3-5-sonnet-20241022"
            api_key = os.getenv('ANTHROPIC_API_KEY')
            if api_key:
                self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def score_entities(
        self,
        entities: list,
        context: str = "",
        batch_size: int = 20
    ) -> list:
        """
        Score confidence for a batch of entities.

        Args:
            entities: List of dicts with {type, text, confidence}
            context: Surrounding text context (optional)
            batch_size: Max entities per API call

        Returns:
            List of dicts with updated confidence scores
        """
        if not self.client or not entities:
            return entities

        # Process in batches
        scored_entities = []
        for i in range(0, len(entities), batch_size):
            batch = entities[i:i + batch_size]
            batch_scored = await self._score_batch(batch, context)
            scored_entities.extend(batch_scored)

        return scored_entities

    async def _score_batch(self, entities: list, context: str) -> list:
        """Score a single batch of entities."""
        entity_list = "\n".join([
            f"- {e.get('type', 'unknown')}: \"{e.get('text', '')}\" (current: {e.get('confidence', 0.5):.2f})"
            for e in entities
        ])

        system_prompt = """You are an entity validation engine. Your task is to assess whether extracted entities are valid.

For each entity, return a confidence score between 0.0 and 1.0:
- 0.9-1.0: Definitely valid (exact match, well-formed)
- 0.7-0.89: Likely valid (reasonable format, contextually appropriate)
- 0.5-0.69: Uncertain (partial match, ambiguous)
- 0.3-0.49: Likely invalid (format issues, out of context)
- 0.0-0.29: Definitely invalid (garbage, extraction error)

Consider:
1. Format correctness (valid email format, phone number pattern, etc.)
2. Contextual appropriateness (does it make sense in the text?)
3. Completeness (full name vs partial, full address vs fragment)

Return ONLY a JSON array with updated confidence scores."""

        user_message = f"""Entities to validate:
{entity_list}

Context (if available):
"{context[:1000] if context else 'No context provided'}"

Return JSON array: [{{"type": "...", "text": "...", "confidence": 0.XX}}, ...]"""

        try:
            if self.tier == "fast":
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    response_format={"type": "json_object"},
                    reasoning_effort="low"
                )
                text = response.choices[0].message.content.strip()
            else:
                message = await self.client.messages.create(
                    model=self.model_name,
                    max_tokens=1024,
                    temperature=0,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}]
                )
                text = message.content[0].text.strip()

            # Parse response
            scored = self._parse_scored_entities(text, entities)
            return scored

        except Exception as e:
            logger.warning(f"Entity scoring failed: {e}")
            return entities  # Return original on failure

    def _parse_scored_entities(self, text: str, original: list) -> list:
        """Parse AI response and merge with original entities."""
        # Clean up JSON
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1].replace("json", "").strip()

        try:
            data = json.loads(text)
            # Handle wrapped response ({"entities": [...]} vs [...])
            if isinstance(data, dict):
                data = data.get("entities", data.get("results", []))

            if not isinstance(data, list):
                return original

            # Merge with original (preserve fields not in response)
            result = []
            for i, orig in enumerate(original):
                updated = orig.copy()
                if i < len(data):
                    scored = data[i]
                    if isinstance(scored, dict) and "confidence" in scored:
                        updated["confidence"] = float(scored["confidence"])
                        updated["ai_validated"] = True
                result.append(updated)

            return result

        except Exception as e:
            logger.warning(f"Failed to parse scored entities: {e}")
            return original


async def score_entity_confidence(
    entities: list,
    context: str = "",
    tier: str = "fast"
) -> list:
    """
    Convenience function for entity confidence scoring.

    Args:
        entities: List of {type, text, confidence} dicts
        context: Surrounding text context
        tier: Model tier ('fast' for GPT-5-nano, 'smart' for Claude)

    Returns:
        List of entities with updated confidence scores
    """
    scorer = EntityConfidenceScorer(tier=tier)
    return await scorer.score_entities(entities, context)
