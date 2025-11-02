#!/usr/bin/env python3
"""
Entity Extraction Service for EDITh
Integrates FactAssembler's entity extraction logic with GPT-4.1-nano
"""

import json
import sys
import os
import time
from datetime import datetime
from typing import Dict, List, Any
from collections import defaultdict
import openai

# Initialize OpenAI client
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    # Try to load from .env if exists
    try:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv('OPENAI_API_KEY')
    except:
        pass

if api_key:
    openai.api_key = api_key
    client = openai.OpenAI(api_key=api_key)
else:
    client = None

# GPT-4.1-nano for fast entity extraction
GPT_NANO_MODEL = "gpt-4.1-nano"

def extract_entities_with_gpt(content: str, chunk_name: str = "document") -> Dict[str, List[Dict]]:
    """Extract entities from content using GPT-4.1-nano - based on FactAssembler logic"""
    
    if not content or len(content) < 10:
        return {}
    
    if not client:
        print("Error: OpenAI client not initialized", file=sys.stderr)
        return {}
    
    try:
        prompt = f"""Extract ALL entities from the document content below. DO NOT make up example entities. Extract ONLY the actual entities mentioned in the document text.

Return a JSON object with these categories:

companies: Array of company/organization names with context
people: Array of person names with their roles/titles if mentioned
emails: Array of email addresses with associated person/company if mentioned
phones: Array of phone numbers with associated person/company if mentioned
addresses: Array of COMPLETE physical addresses with associated entity if mentioned

For physical addresses, ALWAYS extract:
- The FULL address including street number, street name, suite/apt, city, state/province, postal code, country
- Do NOT truncate or abbreviate
- Include office numbers, floor numbers, building names

For each entity, include:
- "name" or "value": The entity itself (COMPLETE address for physical addresses)
- "context": Brief context about the entity from the document (1-2 sentences)
- "mentions": Number of times mentioned in the document
- "type": The entity type (person, organization, phone, email, address)
- "confidence": Confidence score (0.0-1.0)

IMPORTANT: Extract ONLY entities that actually appear in the document below. Do NOT create example entities.

Document content:
{content[:15000]}"""  # Limit to avoid token issues

        response = client.chat.completions.create(
            model=GPT_NANO_MODEL,
            messages=[
                {"role": "system", "content": "You are an entity extraction expert. Extract all entities accurately."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=4000
        )
        
        entities = json.loads(response.choices[0].message.content)
        
        # Add metadata to each entity
        for entity_type, entity_list in entities.items():
            for entity in entity_list:
                if 'type' not in entity:
                    entity['type'] = entity_type.rstrip('s')  # Remove plural 's'
                if 'confidence' not in entity:
                    entity['confidence'] = 0.9  # Default high confidence for GPT extractions
                if 'mentions' not in entity:
                    entity['mentions'] = 1
        
        return entities
        
    except Exception as e:
        print(f"Entity extraction error: {str(e)}", file=sys.stderr)
        return {}

def analyze_entity_similarity(entity1: Dict, entity2: Dict, entity_type: str) -> Dict:
    """Enhanced similarity detection for better entity merging - from FactAssembler"""
    val1 = entity1.get('name', entity1.get('value', '')).strip()
    val2 = entity2.get('name', entity2.get('value', '')).strip()
    
    # Quick exact match (case insensitive)
    if val1.lower() == val2.lower():
        return {'should_merge': True, 'confidence': 1.0}
    
    # Remove common variations and check again
    clean1 = val1.lower().replace('ltd', '').replace('limited', '').replace('inc', '').replace('corporation', '').replace('.', '').replace(',', '').strip()
    clean2 = val2.lower().replace('ltd', '').replace('limited', '').replace('inc', '').replace('corporation', '').replace('.', '').replace(',', '').strip()
    
    if clean1 == clean2:
        return {'should_merge': True, 'confidence': 0.9}
    
    # Check if one is contained in the other
    if clean1 in clean2 or clean2 in clean1:
        return {'should_merge': True, 'confidence': 0.8}
    
    # Basic check - if completely different lengths, probably not the same
    if abs(len(val1) - len(val2)) > 50:
        return {'should_merge': False, 'confidence': 0.0}
    
    # Otherwise, might be similar
    return {'should_merge': True, 'confidence': 0.5}

def merge_similar_entities(all_entities: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """Merge similar entities locally without Claude - simplified version"""
    
    merged_entities = {k: list(v) for k, v in all_entities.items()}  # Deep copy
    
    for entity_type in ['companies', 'people', 'addresses']:
        if entity_type not in merged_entities:
            continue
            
        entities = merged_entities[entity_type]
        i = 0
        while i < len(entities):
            j = i + 1
            while j < len(entities):
                similarity = analyze_entity_similarity(entities[i], entities[j], entity_type)
                
                if similarity['should_merge'] and similarity['confidence'] > 0.7:
                    # Merge j into i
                    entity1 = entities[i]
                    entity2 = entities[j]
                    
                    # Merge mentions
                    entity1['mentions'] = entity1.get('mentions', 1) + entity2.get('mentions', 1)
                    
                    # Merge contexts
                    if entity2.get('context'):
                        if entity1.get('context'):
                            entity1['context'] = entity1['context'] + ' | ' + entity2['context']
                        else:
                            entity1['context'] = entity2['context']
                    
                    # Use the longer/more complete name
                    val1 = entity1.get('name', entity1.get('value', ''))
                    val2 = entity2.get('name', entity2.get('value', ''))
                    if len(val2) > len(val1):
                        entity1['name'] = val2
                        entity1['value'] = val2
                    
                    # Track merge
                    if 'merged_from' not in entity1:
                        entity1['merged_from'] = []
                    entity1['merged_from'].append(val2)
                    
                    # Remove the merged entity
                    entities.pop(j)
                else:
                    j += 1
            i += 1
    
    return merged_entities

def find_entity_positions(text: str, entity_name: str) -> List[int]:
    """Find all positions where an entity appears in text"""
    positions = []
    name_lower = entity_name.lower()
    text_lower = text.lower()
    
    start = 0
    while True:
        pos = text_lower.find(name_lower, start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1
    
    return positions

def process_request(request_data: Dict) -> Dict:
    """Process entity extraction request"""
    
    content = request_data.get('content', '')
    command = request_data.get('command', 'extract')
    
    if command == 'extract':
        # Extract entities
        entities = extract_entities_with_gpt(content, "document")
        
        # Merge similar entities
        merged_entities = merge_similar_entities(entities)
        
        # Find positions for each entity
        all_entities = []
        for entity_type, entity_list in merged_entities.items():
            for entity in entity_list:
                entity_name = entity.get('name', entity.get('value', ''))
                positions = find_entity_positions(content, entity_name)
                
                entity_data = {
                    'id': f"{entity_type}_{hash(entity_name)}",
                    'name': entity_name,
                    'type': entity.get('type', entity_type.rstrip('s')),
                    'mentions': len(positions),
                    'positions': positions,
                    'context': entity.get('context', ''),
                    'confidence': entity.get('confidence', 0.9),
                    'metadata': {
                        'merged_from': entity.get('merged_from', [])
                    }
                }
                all_entities.append(entity_data)
        
        # Sort by mention count
        all_entities.sort(key=lambda x: x['mentions'], reverse=True)
        
        return {
            'success': True,
            'entities': all_entities,
            'summary': {
                'total': len(all_entities),
                'by_type': {k: len(v) for k, v in merged_entities.items()}
            }
        }
    
    else:
        return {
            'success': False,
            'error': f'Unknown command: {command}'
        }

def main():
    """Main entry point for service"""
    
    # Read input from stdin
    input_data = sys.stdin.read()
    
    try:
        request = json.loads(input_data)
        result = process_request(request)
        print(json.dumps(result))
    except json.JSONDecodeError as e:
        error_response = {
            'success': False,
            'error': f'Invalid JSON input: {str(e)}'
        }
        print(json.dumps(error_response))
    except Exception as e:
        error_response = {
            'success': False,
            'error': f'Processing error: {str(e)}'
        }
        print(json.dumps(error_response))

if __name__ == "__main__":
    main()