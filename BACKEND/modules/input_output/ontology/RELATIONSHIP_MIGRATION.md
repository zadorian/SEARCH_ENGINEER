# Relationship Type Standardization Migration

## Overview
This document describes the standardization of relationship types in the Abacus System ontology.

## Changes Required to relationships.json

### 1. Rename `owns` → `owner_of`
- Line ~806 (company section): `"relationship_type": "owns"` → `"relationship_type": "owner_of"`
- Line ~3239 (person section): `"relationship_type": "owns"` → `"relationship_type": "owner_of"`
- Update inverse references: `"inverse": "owns"` → `"inverse": "owner_of"` (lines 93, 6043)

### 2. Add `parent_type` field to child relationships

**Ownership hierarchy:**
```json
"beneficial_owner_of": {
  ...
  "parent_type": "owner_of",
  "aliases": ["ubo_of"]
}

"shareholder_of": {
  ...
  "parent_type": "owner_of"
}
```

**Officer hierarchy:**
```json
"director_of": {
  ...
  "parent_type": "officer_of"
}

"secretary_of": {
  ...
  "parent_type": "officer_of"
}
```

**URL hierarchy:**
```json
"subdomain_of": {
  ...
  "parent_type": "url_of"
}
```

### 3. Add missing relationship: `path_of`
```json
{
  "relationship_type": "path_of",
  "direction": "outgoing",
  "source_types": ["url"],
  "target_types": ["domain"],
  "parent_type": "url_of",
  "category": "web",
  "description": "URL path belongs to domain",
  "confidence_default": 1.0
}
```

### 4. Add parent relationship: `url_of`
```json
{
  "relationship_type": "url_of",
  "direction": "outgoing",
  "source_types": ["url"],
  "target_types": ["domain"],
  "category": "web",
  "description": "URL belongs to domain (parent type for subdomain_of and path_of)",
  "children": ["subdomain_of", "path_of"],
  "confidence_default": 1.0
}
```

## Hierarchy Summary

```
owner_of (parent)
├── beneficial_owner_of (alias: ubo_of)
└── shareholder_of

officer_of (parent)
├── director_of
└── secretary_of

url_of (parent)
├── subdomain_of
└── path_of
```

## Extraction Syntax

| Syntax | Extracts |
|--------|----------|
| `@owner_of?` | All ownership (beneficial_owner_of + shareholder_of) |
| `@beneficial_owner_of?` | UBO only |
| `@ubo_of?` | Alias for @beneficial_owner_of? |
| `@shareholder_of?` | Shareholders only |
| `@officer_of?` | All officers (director_of + secretary_of) |
| `@director_of?` | Directors only |
| `@secretary_of?` | Secretaries only |
| `@url_of?` | All URL relationships |
| `@subdomain_of?` | Subdomains only |
| `@path_of?` | Paths only |

## Backward Compatibility

- `owns` should be treated as alias for `owner_of` during transition
- Old data using `owns` should be migrated to `owner_of`
- Parser should accept both during transition period

## Files Affected

1. `/input_output/ontology/relationships.json` - Main relationship definitions
2. `/input_output/ontology/relationship_hierarchy.json` - Hierarchy and aliases (NEW)
3. Parser code that resolves relationship types
4. Extraction operators that use parent types
