"""
Query Variation Generator using GPT-5 Nano

Generates search variations for names/entities:
- First/last name switched
- Nickname versions
- Middle name with/without initial
- Other alphabet transliterations (Cyrillic, Arabic, etc.)

Returns grouped variations for OR queries (max 4 per group for Firecrawl).
"""

import os
import json
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# GPT-5 Nano config
GPT5_NANO_MODEL = "gpt-5-nano"
MAX_VARIATIONS_PER_GROUP = 4  # Safe limit for Firecrawl OR queries


@dataclass
class QueryVariations:
    """Container for query variations grouped for OR searches."""
    original: str
    groups: List[List[str]] = field(default_factory=list)  # Each group = one OR search
    all_variations: List[str] = field(default_factory=list)

    @property
    def total_variations(self) -> int:
        return len(self.all_variations)

    def as_or_queries(self) -> List[str]:
        """Return variations formatted as OR query strings."""
        or_queries = []
        for group in self.groups:
            # Each variation wrapped in quotes for exact phrase
            phrases = [f'"{v}"' for v in group]
            or_queries.append(" OR ".join(phrases))
        return or_queries


VARIATION_PROMPT = '''Generate search query variations for: "{query}"

Rules:
1. For PERSON NAMES generate:
   - Original order: "John Smith"
   - Reversed order: "Smith John"
   - Common nicknames: "Johnny Smith", "Jack Smith" (if John)
   - With/without middle initial: "John A Smith", "John Smith"
   - Formal versions: "Jonathan Smith" (if John)
   - Transliterations if applicable:
     - Cyrillic: "Джон Смит" (if English name)
     - For Slavic names: both Latin and Cyrillic
     - For Arabic names: Arabic script + common Latin spellings
     - For Chinese names: Pinyin + characters if known

2. For COMPANY NAMES generate:
   - With/without legal suffix: "Acme Corp", "Acme Corporation", "Acme"
   - Common abbreviations: "ACME"
   - Local language versions if international

3. For OTHER QUERIES:
   - Synonym variations
   - Common misspellings
   - Alternative phrasings

Return ONLY a JSON array of variations (strings). Include the original.
Keep total under 20 variations. Most important variations first.

Example for "Viktor Orban":
["Viktor Orban", "Orban Viktor", "Viktor Orbán", "Виктор Орбан", "Orbán Viktor", "V. Orban", "Viktor O."]
'''


async def generate_variations_gpt5nano(query: str) -> QueryVariations:
    """
    Use GPT-5 Nano to generate smart query variations.
    Groups them into chunks of 4 for OR queries.
    """
    try:
        import openai

        client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        response = await client.chat.completions.create(
            model=GPT5_NANO_MODEL,
            messages=[
                {"role": "user", "content": VARIATION_PROMPT.format(query=query)}
            ],
            # GPT-5 uses reasoning_effort instead of temperature
            extra_body={"reasoning_effort": "low"},
            max_tokens=500
        )

        content = response.choices[0].message.content.strip()

        # Parse JSON array from response
        # Handle markdown code blocks if present
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        variations = json.loads(content)

        if not isinstance(variations, list):
            variations = [query]

        # Ensure original is included
        if query not in variations:
            variations.insert(0, query)

        # Deduplicate while preserving order
        seen = set()
        unique_vars = []
        for v in variations:
            v_lower = v.lower().strip()
            if v_lower not in seen:
                seen.add(v_lower)
                unique_vars.append(v.strip())

        # Group into chunks of MAX_VARIATIONS_PER_GROUP
        groups = []
        for i in range(0, len(unique_vars), MAX_VARIATIONS_PER_GROUP):
            groups.append(unique_vars[i:i + MAX_VARIATIONS_PER_GROUP])

        logger.info(f"Generated {len(unique_vars)} variations in {len(groups)} groups for '{query}'")

        return QueryVariations(
            original=query,
            groups=groups,
            all_variations=unique_vars
        )

    except Exception as e:
        logger.warning(f"GPT-5 Nano variation generation failed: {e}, using fallback")
        return _fallback_variations(query)


def _fallback_variations(query: str) -> QueryVariations:
    """
    Fallback variation generator when GPT-5 Nano unavailable.
    Uses simple heuristics for name variations.
    """
    variations = [query]

    parts = query.strip().split()

    if len(parts) == 2:
        # Simple first/last name - generate basic variations
        first, last = parts

        # Reversed order
        variations.append(f"{last} {first}")

        # Initial version
        if len(first) > 1:
            variations.append(f"{first[0]}. {last}")

        # Common nickname mappings
        nickname_map = {
            "william": ["bill", "will", "billy"],
            "robert": ["bob", "rob", "bobby"],
            "richard": ["dick", "rick", "ricky"],
            "michael": ["mike", "mick", "mickey"],
            "james": ["jim", "jimmy", "jamie"],
            "john": ["jack", "johnny", "jon"],
            "joseph": ["joe", "joey"],
            "thomas": ["tom", "tommy"],
            "charles": ["charlie", "chuck"],
            "daniel": ["dan", "danny"],
            "david": ["dave", "davey"],
            "alexander": ["alex", "sandy"],
            "elizabeth": ["liz", "beth", "betty", "eliza"],
            "margaret": ["maggie", "peggy", "meg"],
            "catherine": ["kate", "cathy", "katie"],
            "jennifer": ["jen", "jenny"],
            "christopher": ["chris"],
            "nicholas": ["nick", "nicky"],
            "anthony": ["tony"],
            "edward": ["ed", "eddie", "ted"],
            "viktor": ["victor"],
            "vladimir": ["vlad"],
            "dmitry": ["dmitri", "dima"],
            "sergei": ["sergey"],
            "andrei": ["andrey", "andrew"],
            "nikolai": ["nikolay", "nick"],
        }

        first_lower = first.lower()
        if first_lower in nickname_map:
            for nick in nickname_map[first_lower][:2]:  # Max 2 nicknames
                variations.append(f"{nick.capitalize()} {last}")

        # Check if first name IS a nickname, add formal version
        for formal, nicks in nickname_map.items():
            if first_lower in nicks:
                variations.append(f"{formal.capitalize()} {last}")
                break

    elif len(parts) == 3:
        # First Middle Last
        first, middle, last = parts

        # Without middle
        variations.append(f"{first} {last}")

        # Reversed
        variations.append(f"{last} {first} {middle}")
        variations.append(f"{last} {first}")

        # Middle initial
        if len(middle) > 1:
            variations.append(f"{first} {middle[0]}. {last}")

    # Deduplicate
    seen = set()
    unique = []
    for v in variations:
        v_lower = v.lower()
        if v_lower not in seen:
            seen.add(v_lower)
            unique.append(v)

    # Group into chunks
    groups = []
    for i in range(0, len(unique), MAX_VARIATIONS_PER_GROUP):
        groups.append(unique[i:i + MAX_VARIATIONS_PER_GROUP])

    return QueryVariations(
        original=query,
        groups=groups,
        all_variations=unique
    )


async def generate_variations(query: str, use_llm: bool = True) -> QueryVariations:
    """
    Generate query variations.

    Args:
        query: Original search query
        use_llm: Whether to use GPT-5 Nano (True) or fallback heuristics (False)

    Returns:
        QueryVariations with grouped variations for OR searches
    """
    if use_llm and os.getenv("OPENAI_API_KEY"):
        return await generate_variations_gpt5nano(query)
    else:
        return _fallback_variations(query)


# Synchronous wrapper for non-async contexts
def generate_variations_sync(query: str, use_llm: bool = True) -> QueryVariations:
    """Synchronous wrapper for generate_variations."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're in an async context, create new loop
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    generate_variations(query, use_llm)
                )
                return future.result()
        else:
            return loop.run_until_complete(generate_variations(query, use_llm))
    except RuntimeError:
        return asyncio.run(generate_variations(query, use_llm))


if __name__ == "__main__":
    import asyncio

    async def test():
        # Test with various names
        test_queries = [
            "Viktor Orban",
            "John Smith",
            "Vladimir Putin",
            "Xi Jinping",
            "Mohammed bin Salman",
            "Acme Corporation",
        ]

        for query in test_queries:
            print(f"\n{'='*60}")
            print(f"Query: {query}")
            print(f"{'='*60}")

            result = await generate_variations(query)

            print(f"Total variations: {result.total_variations}")
            print(f"Groups: {len(result.groups)}")

            for i, group in enumerate(result.groups):
                print(f"\nGroup {i+1}:")
                for v in group:
                    print(f"  - {v}")

            print(f"\nOR queries:")
            for q in result.as_or_queries():
                print(f"  {q}")

    asyncio.run(test())
