#!/usr/bin/env python3
"""
Template Validation and Auto-Population for CyMonides

Integrates enhanced JSON Schema templates with auto-population and validation
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from copy import deepcopy


class TemplateValidator:
    """
    Validates and auto-populates node data according to enhanced templates
    """

    def __init__(self):
        """Load templates from input_output/matrix/entity_schema_templates/"""
        self.templates_dir = Path(__file__).parent.parent.parent.parent / "input_output" / "matrix" / "entity_schema_templates"
        self.provenance_schema = self._load_provenance_schema()
        self.source_template = self._load_source_template()
        print(f"✅ Loaded enhanced templates from {self.templates_dir}")

    def _load_provenance_schema(self) -> Dict[str, Any]:
        """Load the provenance schema"""
        try:
            path = self.templates_dir / "provenance_schema.json"
            with open(path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Failed to load provenance_schema.json: {e}")
            return {}

    def _load_source_template(self) -> Dict[str, Any]:
        """Load enhanced source template v2"""
        try:
            path = self.templates_dir / "source_template_v2.json"
            with open(path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Failed to load source_template_v2.json: {e}")
            return {}

    def auto_populate(self, node_data: Dict[str, Any], node_type: str, mode: str = 'discovery') -> Dict[str, Any]:
        """
        Auto-populate fields based on template annotations

        Args:
            node_data: Original node data
            node_type: Type of node (e.g., 'webdomain', 'document')
            mode: 'discovery' or 'enrichment'

        Returns:
            Node data with auto-populated fields
        """
        populated = deepcopy(node_data)

        # Initialize metadata if not present
        if 'metadata' not in populated:
            populated['metadata'] = {}

        # Auto-populate base metadata
        populated['metadata']['node_id'] = populated['metadata'].get('node_id', str(uuid.uuid4()))
        populated['metadata']['created_at'] = populated['metadata'].get('created_at', datetime.utcnow().isoformat() + 'Z')
        populated['metadata']['updated_at'] = datetime.utcnow().isoformat() + 'Z'
        populated['metadata']['class'] = 'SOURCE'  # For source template

        # Auto-populate type
        if 'type' not in populated:
            populated['type'] = node_type

        # Add provenance if missing
        if 'provenance' not in populated:
            populated['provenance'] = self._create_default_provenance()

        # Type-specific auto-population
        if node_type == 'webdomain':
            populated = self._auto_populate_webdomain(populated)
        elif node_type == 'document':
            populated = self._auto_populate_document(populated)

        return populated

    def _create_default_provenance(self) -> Dict[str, Any]:
        """Create default provenance object"""
        return {
            "source": "cymonides",
            "confidence": 0.8,
            "verified_at": datetime.utcnow().isoformat() + 'Z',
            "verification_method": "automated"
        }

    def _auto_populate_webdomain(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-populate webdomain-specific fields"""
        # Extract domain from URL if not present
        if 'url' in data and 'domain' not in data:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(data['url'])
                data['domain'] = parsed.netloc
            except Exception as e:

                print(f"[BRUTE] Error: {e}")

                pass

        # Generate content hash if content is present
        if 'content' in data and 'content_hash' not in data:
            import hashlib
            content = str(data.get('content', ''))
            data['content_hash'] = hashlib.sha256(content.encode()).hexdigest()

        # Set last_crawled
        if 'last_crawled' not in data:
            data['last_crawled'] = datetime.utcnow().isoformat() + 'Z'

        return data

    def _auto_populate_document(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-populate document-specific fields"""
        # Generate file hash if file content is available
        if 'file_content' in data and 'file_hash' not in data:
            import hashlib
            content = data['file_content'].encode() if isinstance(data['file_content'], str) else data['file_content']
            data['file_hash'] = hashlib.sha256(content).hexdigest()

        # Set file_size if available
        if 'file_content' in data and 'file_size' not in data:
            content = data['file_content'].encode() if isinstance(data['file_content'], str) else data['file_content']
            data['file_size'] = len(content)

        return data

    def validate_schema(self, node_data: Dict[str, Any], node_type: str) -> tuple[bool, List[str]]:
        """
        Validate node data against template schema

        Args:
            node_data: Node data to validate
            node_type: Type of node

        Returns:
            (is_valid, error_messages)
        """
        errors = []

        # Get type schema from template
        if not self.source_template or 'types' not in self.source_template:
            return True, []  # Skip validation if template not loaded

        type_schema = self.source_template.get('types', {}).get(node_type)
        if not type_schema:
            errors.append(f"Unknown node type: {node_type}")
            return False, errors

        # Check required fields
        required = type_schema.get('required', [])
        for field in required:
            if field not in node_data:
                errors.append(f"Missing required field: {field}")

        # Validate field types and patterns (simplified validation)
        properties = type_schema.get('properties', {})
        for field, value in node_data.items():
            if field in properties:
                field_schema = properties[field]
                errors.extend(self._validate_field(field, value, field_schema))

        return len(errors) == 0, errors

    def _validate_field(self, field_name: str, value: Any, schema: Dict[str, Any]) -> List[str]:
        """Validate a single field against its schema"""
        errors = []

        # Type validation
        expected_type = schema.get('type')
        if expected_type == 'string' and not isinstance(value, str):
            errors.append(f"{field_name}: expected string, got {type(value).__name__}")
        elif expected_type == 'integer' and not isinstance(value, int):
            errors.append(f"{field_name}: expected integer, got {type(value).__name__}")
        elif expected_type == 'number' and not isinstance(value, (int, float)):
            errors.append(f"{field_name}: expected number, got {type(value).__name__}")
        elif expected_type == 'array' and not isinstance(value, list):
            errors.append(f"{field_name}: expected array, got {type(value).__name__}")
        elif expected_type == 'object' and not isinstance(value, dict):
            errors.append(f"{field_name}: expected object, got {type(value).__name__}")

        # Pattern validation for strings
        if expected_type == 'string' and isinstance(value, str):
            if 'pattern' in schema:
                import re
                pattern = schema['pattern']
                if not re.match(pattern, value):
                    errors.append(f"{field_name}: does not match pattern {pattern}")

            if 'minLength' in schema and len(value) < schema['minLength']:
                errors.append(f"{field_name}: length {len(value)} is less than minimum {schema['minLength']}")

            if 'maxLength' in schema and len(value) > schema['maxLength']:
                errors.append(f"{field_name}: length {len(value)} exceeds maximum {schema['maxLength']}")

        # Enum validation
        if 'enum' in schema and value not in schema['enum']:
            errors.append(f"{field_name}: value '{value}' not in allowed values {schema['enum']}")

        # Range validation for numbers
        if expected_type in ('integer', 'number') and isinstance(value, (int, float)):
            if 'minimum' in schema and value < schema['minimum']:
                errors.append(f"{field_name}: value {value} is less than minimum {schema['minimum']}")
            if 'maximum' in schema and value > schema['maximum']:
                errors.append(f"{field_name}: value {value} exceeds maximum {schema['maximum']}")

        return errors

    def validate_provenance(self, provenance: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate provenance object against provenance schema"""
        if not provenance:
            return False, ["Provenance is required"]

        errors = []

        # Check required fields
        required = self.provenance_schema.get('required', [])
        for field in required:
            if field not in provenance:
                errors.append(f"Provenance missing required field: {field}")

        # Validate confidence score
        if 'confidence' in provenance:
            conf = provenance['confidence']
            if not isinstance(conf, (int, float)) or conf < 0.0 or conf > 1.0:
                errors.append("Provenance confidence must be between 0.0 and 1.0")

        # Validate verification_method enum
        if 'verification_method' in provenance:
            allowed = ['manual', 'automated', 'ai_extracted', 'crowdsourced', 'api_verified']
            if provenance['verification_method'] not in allowed:
                errors.append(f"Invalid verification_method: {provenance['verification_method']}")

        return len(errors) == 0, errors


# Convenience function for quick validation
def validate_and_populate(node_data: Dict[str, Any], node_type: str, mode: str = 'discovery') -> tuple[Dict[str, Any], bool, List[str]]:
    """
    Validate and auto-populate node data in one call

    Returns:
        (populated_data, is_valid, error_messages)
    """
    validator = TemplateValidator()
    populated = validator.auto_populate(node_data, node_type, mode)
    is_valid, errors = validator.validate_schema(populated, node_type)

    # Also validate provenance
    if 'provenance' in populated:
        prov_valid, prov_errors = validator.validate_provenance(populated['provenance'])
        if not prov_valid:
            is_valid = False
            errors.extend(prov_errors)

    return populated, is_valid, errors


if __name__ == "__main__":
    # Test the validator
    print("Testing Template Validator...")

    test_data = {
        "url": "https://example.com/page",
        "title": "Example Page"
    }

    populated, valid, errors = validate_and_populate(test_data, "webdomain")

    print(f"\nOriginal data: {json.dumps(test_data, indent=2)}")
    print(f"\nPopulated data: {json.dumps(populated, indent=2)}")
    print(f"\nValid: {valid}")
    if errors:
        print(f"Errors: {errors}")
    else:
        print("✅ No validation errors")
