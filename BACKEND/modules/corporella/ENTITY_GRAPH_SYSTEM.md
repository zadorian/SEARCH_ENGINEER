# Entity Graph System - Implementation Complete

## Date: 2025-11-02
## Status: ✅ Core System Built - Ready for Integration

---

## OVERVIEW

Corporella Claude now has a complete entity graph system that:
- Creates nodes for ALL extracted entities (companies, people, addresses, emails, phones)
- Establishes bidirectional relationships between entities
- Maintains semantic relationship types based on field context
- Provides inverse relationships (if X owns Y, then Y is owned by X)

---

## IMPLEMENTATION

### 1. Database Schema

#### Entity Nodes Table (`entity_nodes`)
```sql
- id: TEXT PRIMARY KEY (MD5 hash)
- entity_type: company|person|address|email|phone|url|litigation|regulator|document|other
- name: TEXT (original name)
- normalized_name: TEXT (lowercase, trimmed)
- properties: JSON (entity-specific data)
- sources: JSON array (data sources)
- first_seen: TIMESTAMP
- last_updated: TIMESTAMP
```

#### Entity Edges Table (`entity_edges`)
```sql
- id: INTEGER PRIMARY KEY
- source_id: TEXT (node ID)
- target_id: TEXT (node ID)
- relationship_type: TEXT (e.g., SUBSIDIARY_OF, HAS_CEO)
- relationship_label: TEXT (human-readable)
- properties: JSON (edge-specific data like ownership %)
- field_context: TEXT (which field created this relationship)
- confidence: REAL (0-1)
- source: TEXT (data source)
- created_at: TIMESTAMP
```

### 2. Relationship Mapping System

#### Bidirectional Relationships
Each relationship has a forward and inverse form:

| Field Context | Forward Relationship | Inverse Relationship |
|--------------|---------------------|---------------------|
| subsidiary | X SUBSIDIARY_OF Y | Y PARENT_OF X |
| parent_company | X PARENT_OF Y | Y SUBSIDIARY_OF X |
| beneficial_owner | X OWNS Y | Y OWNED_BY X |
| officer | X OFFICER_OF Y | Y HAS_OFFICER X |
| director | X DIRECTOR_OF Y | Y HAS_DIRECTOR X |
| ceo | X CEO_OF Y | Y HAS_CEO X |
| registered_address | X REGISTERED_AT Y | Y REGISTRATION_ADDRESS_FOR X |
| email | X HAS_EMAIL Y | Y EMAIL_FOR X |
| phone | X HAS_PHONE Y | Y PHONE_FOR X |
| litigation | X INVOLVED_IN_LITIGATION Y | Y LITIGATION_INVOLVES X |
| regulator | X REGULATED_BY Y | Y REGULATES X |

### 3. Key Features

#### Automatic Entity Extraction
```python
# From company data, extracts and creates nodes for:
- Officers → person nodes
- Beneficial owners → person or company nodes
- Subsidiaries → company nodes
- Addresses → address nodes
- Emails → email nodes
- Phones → phone nodes
```

#### Bidirectional Edge Creation
```python
# When creating a relationship, automatically creates both directions:
graph.create_bidirectional_edge(
    person_id, company_id,
    field_context='ceo'
)
# Creates:
# 1. person CEO_OF company
# 2. company HAS_CEO person
```

#### Entity Deduplication
- Uses MD5 hash of (entity_type + normalized_name) as ID
- Merges properties and sources when same entity found again
- Maintains first_seen and last_updated timestamps

---

## USAGE EXAMPLES

### Creating Entities and Relationships
```python
from storage.entity_graph import EntityGraph

graph = EntityGraph()

# Create company node
company_id = graph.create_node(
    'company',
    'Apple Inc',
    properties={'jurisdiction': 'us_ca'},
    sources=['opencorporates']
)

# Create person node
person_id = graph.create_node(
    'person',
    'Tim Cook',
    properties={'position': 'CEO'},
    sources=['opencorporates']
)

# Create bidirectional relationship
graph.create_bidirectional_edge(
    person_id, company_id,
    field_context='ceo',
    source='opencorporates'
)
```

### Querying Relationships
```python
# Get all relationships for a company
relationships = graph.get_node_relationships(company_id)

# Result includes both directions:
# - Incoming: Tim Cook CEO_OF Apple Inc
# - Outgoing: Apple Inc HAS_CEO Tim Cook
```

### Automatic Extraction from Company Data
```python
# Extract all entities from populated company data
entities = graph.extract_and_create_entities(
    company_data,  # The merged entity from Haiku
    company_id,    # The company's node ID
    source='opencorporates'
)

# Returns:
{
    'companies': ['sub_id1', 'parent_id1'],
    'people': ['officer_id1', 'owner_id1'],
    'addresses': ['addr_id1'],
    'emails': ['email_id1'],
    'phones': ['phone_id1']
}
```

---

## INTEGRATION POINTS

### 1. With Company Storage (`company_storage.py`)
- When saving a company, also extract entities to graph
- When loading a company, include related entities

### 2. With Populator (`populator.py`)
- After Haiku merges entity, extract all entities
- Create nodes and edges for all extracted entities

### 3. With WebSocket Server (`websocket_server.py`)
- After auto-save, trigger entity extraction
- Include relationship data in responses

### 4. With Frontend (`entity_recognition.js`)
- When entity badges are clicked, query relationships
- Show bidirectional relationships in UI

---

## NEXT STEPS

### Required Integration:
1. **Modify `company_storage.py`**
   - Add entity graph integration to save_company()
   - Include relationship data in load_company()

2. **Update `websocket_server.py`**
   - Call entity extraction after saving
   - Add endpoint for querying entity relationships

3. **Create Entity Templates**
   - Person profile template
   - Address profile template
   - Generic entity profile template

### Optional Enhancements:
1. **Graph Visualization**
   - D3.js network graph
   - Interactive exploration
   - Relationship filtering

2. **Advanced Queries**
   - Find all companies owned by person
   - Find all people at same address
   - Network analysis (degrees of separation)

3. **Entity Resolution**
   - Fuzzy matching for similar names
   - Merge duplicate entities
   - Confidence scoring

---

## DATABASE STATISTICS

Current state after test:
- Entity nodes: 2 (Apple Inc, Tim Cook)
- Edges: 2 (bidirectional CEO relationship)
- Tables: 5 total (3 original + 2 graph tables)
- Indexes: 5 (for performance)

---

## BENEFITS

1. **Knowledge Graph**: Every entity becomes queryable
2. **Bidirectional Navigation**: Navigate relationships both ways
3. **Context Preservation**: Field context determines relationship type
4. **Deduplication**: Same entities merged across sources
5. **Audit Trail**: Track when entities first seen and updated
6. **Flexible Schema**: Easy to add new entity types and relationships

---

**Status**: ✅ Core system complete and tested
**Next**: Integration with existing components
**Location**: `/storage/entity_graph.py`