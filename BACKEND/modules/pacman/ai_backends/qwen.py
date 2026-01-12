"""
PACMAN Qwen Backend
Entity extraction using Qwen via Ollama
"""

import json
import re
import requests
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen3:8b"

@dataclass
class ExtractedEntity:
    entity_type: str  # PERSON, COMPANY, LOCATION, PHONE, EMAIL, MONEY, DATE
    value: str
    context: str
    confidence: float = 0.9
    metadata: Dict = field(default_factory=dict)

EXTRACTION_PROMPT = '''Extract ALL entities from this text. Return valid JSON only, no other text.

Entity types to extract:
- PERSON: Full names of people
- COMPANY: Company/organization names (include legal suffix like Ltd, GmbH, AB, Inc)
- LOCATION: Countries, cities, jurisdictions mentioned
- PHONE: Phone numbers in any format
- EMAIL: Email addresses
- MONEY: Monetary amounts with currency
- DATE: Dates and time periods

For each entity include:
- type: entity type (PERSON, COMPANY, LOCATION, PHONE, EMAIL, MONEY, DATE)
- value: the extracted value exactly as it appears
- context: the surrounding 5-10 words showing how it appears in text

Return ONLY this JSON format, nothing else:
{"entities": [{"type": "PERSON", "value": "John Smith", "context": "CEO John Smith announced"}, {"type": "COMPANY", "value": "Acme Ltd", "context": "contract with Acme Ltd for"}]}

TEXT TO ANALYZE:
---
%s
---

JSON OUTPUT:'''


def extract_with_qwen(
    text: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096
) -> List[ExtractedEntity]:
    """
    Extract entities from text using Qwen.
    Returns list of ExtractedEntity objects.
    """
    if not text or len(text.strip()) < 10:
        return []

    # Truncate very long texts
    if len(text) > 15000:
        text = text[:15000] + "..."

    prompt = EXTRACTION_PROMPT % text

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.1,
                }
            },
            timeout=120
        )

        if response.status_code != 200:
            print(f"[Qwen] API error: {response.status_code}")
            return []

        result = response.json()
        raw_output = result.get("response", "")

        # Parse JSON from response
        entities = _parse_json_response(raw_output)
        return entities

    except requests.exceptions.Timeout:
        print("[Qwen] Request timeout")
        return []
    except Exception as e:
        print(f"[Qwen] Error: {e}")
        return []


def _parse_json_response(raw: str) -> List[ExtractedEntity]:
    """Parse JSON from Qwen response, handling various formats."""
    entities = []

    # Clean up the response
    raw = raw.strip()

    # Remove thinking tags if present (Qwen3 sometimes adds these)
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)
    raw = raw.strip()

    # Try to find JSON in response - handle ```json``` blocks
    json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1)

    # Try direct JSON parse
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "entities" in data:
            for ent in data["entities"]:
                entities.append(ExtractedEntity(
                    entity_type=ent.get("type", "UNKNOWN"),
                    value=ent.get("value", ""),
                    context=ent.get("context", ""),
                    confidence=ent.get("confidence", 0.85),
                    metadata=ent.get("metadata", {})
                ))
        return entities
    except json.JSONDecodeError:
        pass

    # Try to extract JSON object from mixed text
    brace_start = raw.find('{')
    brace_end = raw.rfind('}')
    if brace_start != -1 and brace_end > brace_start:
        try:
            json_str = raw[brace_start:brace_end+1]
            data = json.loads(json_str)
            if isinstance(data, dict) and "entities" in data:
                for ent in data["entities"]:
                    entities.append(ExtractedEntity(
                        entity_type=ent.get("type", "UNKNOWN"),
                        value=ent.get("value", ""),
                        context=ent.get("context", ""),
                        confidence=0.8
                    ))
                return entities
        except:
            pass

    # Fallback: try line-by-line extraction
    return _fallback_parse(raw)


def _fallback_parse(raw: str) -> List[ExtractedEntity]:
    """Fallback parser when JSON fails."""
    entities = []

    # Look for patterns in the raw output
    type_patterns = {
        'PERSON': r'(?:PERSON|Person|person)[:\s]+["\']?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)["\']?',
        'COMPANY': r'(?:COMPANY|Company|company)[:\s]+["\']?([A-Z][\w\s&.,]+?(?:Ltd|GmbH|Inc|AB|LLC|BV|NV|SA|AG|Kft|OY|AS)\.?)["\']?',
        'LOCATION': r'(?:LOCATION|Location|location)[:\s]+["\']?([A-Z][a-zA-Z\s]+)["\']?',
        'EMAIL': r'(?:EMAIL|Email|email)[:\s]+["\']?([\w.+-]+@[\w.-]+\.\w+)["\']?',
        'PHONE': r'(?:PHONE|Phone|phone)[:\s]+["\']?([+\d\s().-]{7,})["\']?',
        'MONEY': r'(?:MONEY|Money|money)[:\s]+["\']?([A-Z]{3}\s*[\d,.]+|[\d,.]+\s*[A-Z]{3}|[$€£¥]\s*[\d,.]+)["\']?',
    }

    for etype, pattern in type_patterns.items():
        for match in re.finditer(pattern, raw):
            entities.append(ExtractedEntity(
                entity_type=etype,
                value=match.group(1).strip(),
                context="",
                confidence=0.6
            ))

    return entities


def extract_batch(texts: List[str], model: str = DEFAULT_MODEL) -> List[List[ExtractedEntity]]:
    """Extract from multiple texts."""
    results = []
    for text in texts:
        entities = extract_with_qwen(text, model)
        results.append(entities)
    return results


def extract_all_entities(text: str, use_8b: bool = True) -> Dict[str, List[Dict]]:
    """
    Extract all entities and return as categorized dict.
    Compatible with email_exporter format.
    """
    model = "qwen3:8b" if use_8b else "qwen3:0.6b"
    entities = extract_with_qwen(text, model)

    result = {
        "persons": [],
        "companies": [],
        "locations": [],
        "phones": [],
        "emails": [],
        "money": [],
        "dates": []
    }

    type_map = {
        "PERSON": "persons",
        "COMPANY": "companies",
        "LOCATION": "locations",
        "PHONE": "phones",
        "EMAIL": "emails",
        "MONEY": "money",
        "DATE": "dates"
    }

    for ent in entities:
        category = type_map.get(ent.entity_type)
        if category:
            result[category].append({
                "value": ent.value,
                "context": ent.context,
                "confidence": ent.confidence
            })

    return result


# Test
if __name__ == "__main__":
    test_text = '''
    Dear Mr. John Smith,

    Following our meeting in Stockholm on 15 January 2024, I am pleased to confirm
    that Acme Holdings Ltd (registered in the Cayman Islands) has agreed to the
    terms proposed by Nordic Investments AB.

    The total amount of EUR 2,500,000 will be transferred to account held at
    Credit Suisse, Geneva. Please contact our office at +41 22 123 4567 or
    email finance@acmeholdings.com for wire details.

    Best regards,
    Maria Garcia
    CEO, Nordic Investments AB
    '''

    print("Testing Qwen entity extraction...")
    print("=" * 50)
    result = extract_all_entities(test_text)

    for category, items in result.items():
        if items:
            print(f"\n{category.upper()}:")
            for item in items:
                print(f"  - {item['value']}")
                if item['context']:
                    print(f"    Context: {item['context']}")
