# Field Codes Migration: Hardcoded → Dynamic Schema Loading

## Summary

Successfully migrated hardcoded field code mappings in `contracts.py` to dynamic loading from the CYMONIDES matrix schema.

## Changes Made

### 1. contracts.py - Core Implementation

**Before:**
```python
# Hardcoded field codes
PERSON_CODES = {
    "name": 7,
    "national_id": 8,
    "tax_id": 9,
    # ... 15 fields hardcoded
}

COMPANY_CODES = {
    "name": 13,
    "reg_id": 14,
    # ... 13 fields hardcoded
}
```

**After:**
```python
def _load_field_codes_from_schema(entity_type: str) -> Dict[str, int]:
    """Load field codes dynamically from CYMONIDES schema."""
    reader = get_schema_reader()
    type_def = reader.get_entity_type(entity_type)
    
    field_codes = {}
    for prop_name, prop_def in type_def.properties.items():
        if prop_def.codes:
            field_codes[prop_name] = prop_def.codes[0]
    
    return field_codes

# Cached dynamic loading
def get_field_codes(entity_type: str) -> Dict[str, int]:
    if entity_type not in _FIELD_CODES_CACHE:
        _FIELD_CODES_CACHE[entity_type] = _load_field_codes_from_schema(entity_type)
    return _FIELD_CODES_CACHE[entity_type]
```

**Backwards Compatibility:**
```python
class _FieldCodesProxy:
    """Lazy-loading proxy maintains backwards compatibility."""
    # Implements dict-like interface (__getitem__, get, items, etc.)
    # Loads from schema on first access

PERSON_CODES = _FieldCodesProxy("person")
COMPANY_CODES = _FieldCodesProxy("company")
DOMAIN_CODES = _FieldCodesProxy("domain")
```

### 2. get_completeness() - Updated to Use Schema

**Before:**
```python
def get_completeness(node_data, entity_type):
    # Used hardcoded SUBJECT_FIELD_CODES["person"]["core"]
    core_codes = SUBJECT_FIELD_CODES[entity_type]["core"]
    shell_codes = SUBJECT_FIELD_CODES[entity_type]["shell"]
    # ...
```

**After:**
```python
def get_completeness(node_data, entity_type):
    """Now uses REAL schema from CYMONIDES."""
    reader = get_schema_reader()
    type_def = reader.get_entity_type(entity_type)
    
    required_props = type_def.required_properties
    optional_props = type_def.optional_properties
    # Calculate completeness from actual schema
```

### 3. dispatcher.py - Updated Import and Usage

**Before:**
```python
from .contracts import SUBJECT_FIELD_CODES

field_codes = SUBJECT_FIELD_CODES.get(entity_type, {})
all_fields = {
    **field_codes.get("core", {}),
    **field_codes.get("shell", {}),
    **field_codes.get("enrichment", {}),
}
```

**After:**
```python
from .contracts import get_field_codes

all_fields = get_field_codes(entity_type)
```

### 4. report_writer.py - Cleaned Up Unused Imports

Removed unused imports of `PERSON_CODES`, `COMPANY_CODES`, `DOMAIN_CODES`.

## Benefits

1. **Single Source of Truth**: Field codes now come from `CYMONIDES/metadata/c-1/matrix_schema/nodes.json`
2. **No Duplication**: Eliminates hardcoded mappings that could drift from schema
3. **Automatic Updates**: Adding fields to schema automatically makes them available
4. **Type Safety**: Schema reader provides validation and type information
5. **Backwards Compatible**: Existing code using `PERSON_CODES["name"]` still works via proxy

## Test Results

All tests pass:
- ✓ Dynamic loading: Person (23 fields), Company (38 fields)
- ✓ Backwards compatibility: `PERSON_CODES['name']` returns `7`
- ✓ Completeness function uses dynamic schema
- ✓ Dispatcher integration works correctly

## Schema Source

Authoritative schema location:
```
/Users/attic/01. DRILL_SEARCH/drill-search-app/BACKEND/modules/CYMONIDES/metadata/c-1/matrix_schema/nodes.json
```

Schema reader: `SASTRE/core/schema_reader.py`

## Migration Notes

- Old `SUBJECT_FIELD_CODES` structure (core/shell/enrichment) is deprecated
- Use `get_field_codes(entity_type)` for new code
- Legacy constants (`PERSON_CODES`, etc.) still work via lazy-loading proxy
- Schema is loaded once and cached for performance

## Files Modified

1. `BACKEND/modules/SASTRE/contracts.py` - Core implementation
2. `BACKEND/modules/SASTRE/dispatcher.py` - Updated to use `get_field_codes()`
3. `BACKEND/modules/SASTRE/report_writer.py` - Cleaned up unused imports
