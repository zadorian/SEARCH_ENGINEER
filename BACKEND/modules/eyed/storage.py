#!/usr/bin/env python3
"""
EYE-D Result Storage
"""

import uuid
import json
import logging
from datetime import datetime
from typing import Dict, Any

try:
    from cymonides.indexer.result_storage import ResultStorage
except ImportError:
    print("Warning: Could not import ResultStorage")
    ResultStorage = None

class EyeDStorage:
    def __init__(self):
        self.storage = ResultStorage() if ResultStorage else None

    def store_results(self, results: Dict[str, Any]) -> None:
        """Store results in the database using the proper schema"""
        if not self.storage:
            return
        
        try:
            # Generate a unique search_id for this EYE-D query
            search_id = f"eye-d_{results['subtype']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # First store the target entity itself (the query)
            target_entity_id = self.storage.create_entity_record(
                project_id=search_id,
                query=search_id,
                entity_value=results['query'],
                entity_type=results['subtype'].upper(),  # email -> EMAIL, phone -> PHONE, etc.
                url_id=search_id,  # Self-reference for the target entity
                source_url=f"eye-d://query/{results['subtype']}",
                notes=f"Target {results['subtype']} for EYE-D search",
                ai_model='EYE-D',
                ai_confidence=1.0,
                ai_tokens_used=0
            )
            
            print(f"💾 Stored target entity: {results['query']} (ID: {target_entity_id})")
            
            # Store each result as a search result record
            for i, result in enumerate(results.get('results', [])):
                # Create a record for the result
                result_data = result.get('data', {})
                
                # Create a meaningful snippet from the data
                snippet_parts = []
                if isinstance(result_data, dict):
                    for key, value in list(result_data.items())[:5]:  # First 5 fields
                        if value and str(value).strip():
                            snippet_parts.append(f"{key}: {str(value)[:100]}")
                snippet = ' | '.join(snippet_parts) if snippet_parts else str(result_data)[:500]
                
                # Store result record using the standard result storage
                result_record = {
                    'id': str(uuid.uuid4()),
                    'project_id': search_id,
                    'value': f"eye-d://{result['source']}/{result['entity_value']}",
                    'aliases': None,
                    'variations': None,
                    'type': 'result',
                    'subtype': result['source'],  # Source as subtype (rocketreach, dehashed, etc.)
                    'notes': snippet,
                    'meta': json.dumps({
                        'entity_type': result['entity_type'],
                        'entity_value': result['entity_value'],
                        'full_data': str(result['data']),  # Convert to string to avoid serialization issues
                        'source': result['source']
                    }),
                    'created_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat(),
                    'query': search_id,
                    'engine': f"EYE-D/{result['source']}",
                    'scraped_content': str(result['data']),  # Convert to string to avoid serialization issues
                    'scraped_at': datetime.utcnow().isoformat()
                }
                
                # Insert the result record with proper duplicate handling
                try:
                    self.storage.conn.execute('''
                        INSERT OR IGNORE INTO search_results (
                            id, project_id, value, aliases, variations, type, subtype,
                            notes, meta, created_at, updated_at, query, engine,
                            scraped_content, scraped_at
                        ) VALUES (
                            :id, :project_id, :value, :aliases, :variations, :type, :subtype,
                            :notes, :meta, :created_at, :updated_at, :query, :engine,
                            :scraped_content, :scraped_at
                        )
                    ''', result_record)
                except Exception as e:
                    print(f"Note: Result already exists in database: {result['source']} - {e}")
            
            # Store extracted entities using the proper entity record method
            unique_entities = {}  # Deduplicate entities
            for entity in results.get('entities', []):
                entity_key = f"{entity['type']}:{entity['value']}"
                if entity_key not in unique_entities:
                    unique_entities[entity_key] = entity
            
            for entity in unique_entities.values():
                # Handle list values properly by converting to string
                entity_value = entity['value']
                if isinstance(entity_value, list):
                    entity_value = ', '.join(str(item) for item in entity_value)
                elif not isinstance(entity_value, str):
                    entity_value = str(entity_value)
                
                try:
                    entity_id = self.storage.create_entity_record(
                        project_id=search_id,
                        query=search_id,
                        entity_value=entity_value,
                        entity_type=entity['type'].upper(),  # Use consistent entity types
                        url_id=target_entity_id,  # Link to the target entity
                        source_url=f"eye-d://extracted/{results['subtype']}",
                        notes=f"Extracted from {results['query']} via EYE-D {results['subtype']} search",
                        ai_model='EYE-D',
                        ai_confidence=0.9,  # High confidence for direct extraction
                        ai_tokens_used=0
                    )
                except Exception as e:
                    print(f"Note: Entity already exists in database: {entity_value} ({entity['type']}) - {e}")
            
            # Commit all changes
            self.storage.conn.commit()
            
            print(f"✅ Stored {len(results.get('results', []))} results and {len(unique_entities)} unique entities")
            print(f"📊 Search ID: {search_id}")
            
        except Exception as e:
            print(f"❌ Error storing results: {e}")
            import traceback
            traceback.print_exc()
