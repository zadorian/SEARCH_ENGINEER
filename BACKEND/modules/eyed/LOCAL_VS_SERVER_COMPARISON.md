# EYE-D Local vs Server Implementation Comparison

## Executive Summary

**CRITICAL FINDING:** The local version has a sophisticated node ID generation system and graph structure that is **MISSING or INCOMPLETE** on the server. This system ensures deterministic node creation across multiple data sources using SHA-256 hashing.

---

## 1. Node ID Generation (LOCAL HAS, SERVER NEEDS)

### Local Implementation (output.py lines 1076-1133)

```python
# DETERMINISTIC ID GENERATION SYSTEM
_global_id_map = {}  # (scope, normalized_value) -> ID

# ID Scopes for cross-field linkage
ID_SCOPES = {
    'registered_domains': 'domain',
    'breach_domains': 'domain',
    'linkedin_urls': 'url',
    'account_urls': 'url',
    'websites': 'url',
    'picture_urls': 'url',
    'banner_urls': 'url',
    'phones': 'phone',
    'emails': 'email',
    'usernames': 'username'
}

def normalize_value(value):
    """Normalize value for comparison"""
    # Lowercase, strip whitespace
    # Collapse internal whitespace
    # Clean URLs (remove http://, www.)
    # Clean phones (digits only)
    # Return normalized string for consistent matching

def get_or_create_id(field_type, value) -> str:
    """Get existing ID or create new one using SHA-256"""
    normalized = normalize_value(value)
    scope = ID_SCOPES.get(field_type, field_type)
    key = (scope, normalized)
    
    if key not in _global_id_map:
        hash_input = f"{scope}:{normalized}"
        _global_id_map[key] = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
    return _global_id_map[key]
```

**KEY FEATURES:**
- Same value across multiple sources = SAME ID
- Domain from email extraction gets SAME ID as registered domain lookup
- Enables automatic deduplication and merging
- SHA-256 hash ensures deterministic IDs (same value always produces same ID)

### Server Implementation (PARTIAL)

```python
def _c1_generate_id(value: str, node_type: str) -> str:
    key = f"{node_type}:{(value or '').lower().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

**MISSING:**
- No global ID map for tracking created IDs
- No ID scopes for cross-field linkage
- No normalize_value function (URL cleaning, phone normalization)
- No merge system for nodes across sources

---

## 2. Node Type Mapping

### Local Implementation (output.py lines 1262-1277)

```python
field_mappings = {
    'emails': ('email', 'has_email'),
    'phones': ('phone', 'has_phone'),
    'usernames': ('username', 'has_username'),
    'names': ('alias', 'has_alias'),  # ← Note: Names become ALIASES
    'linkedin_urls': ('social_url', 'has_social'),
    'account_urls': ('social_url', 'has_social'),
    'registered_domains': ('domain', 'associated_domain'),
    'breach_domains': ('domain', 'breached_on_domain'),  # ← Different edge type
    'ip_addresses': ('ip', 'associated_ip'),
    'addresses': ('address', 'has_address'),
    'companies': ('company', 'worked_at'),
    'job_titles': ('job_title', 'has_title'),
    'schools': ('school', 'attended'),
    'passwords': ('password', 'exposed_password')
}
```

### Server Implementation (lines 314-364)

```python
def _c1_ui_type_to_c1(ui_type: str, node_data: Optional[Dict] = None):
    """Map EYE-D UI node type -> (node_class, c1_type, original_type)"""
    original = (ui_type or "unknown").strip().lower()
    if original in ("url", "webpage"):
        return ("source", "webpage", original)
    if original in ("ip", "ip_address"):
        return ("entity", "ip", original)
    if original in ("name", "person"):
        return ("entity", "person", original)
    if original in ("company", "organization", "org"):
        return ("entity", "company", original)
    # ... etc
```

**KEY DIFFERENCE:**
- Local uses **node_type** + **edge_type** pattern (tuple)
- Server uses **node_class** + **c1_type** pattern
- Local has more specific edge types ("breached_on_domain" vs "associated_domain")

---

## 3. Graph Structure Generation

### Local Implementation (output.py lines 1205-1303)

```python
def generate_graph_export(data, primary_email):
    """Generate nodes and edges from extracted data"""
    nodes = []
    edges = []
    created_node_ids = set()
    
    # 1. Create Subject/Root Node
    subject_id = add_node('person', primary_email, {'is_root': True})
    
    # 2. Process all fields and link to Subject
    for field_name, field_data in data.items():
        if field_name in field_mappings:
            node_type, relation = field_mappings[field_name]
            for item in field_data:
                attr_id = add_node(node_type, item['value'])
                add_edge(subject_id, attr_id, relation)
                
                # 3. Special Case: Email -> Domain extraction
                if node_type == 'email' and '@' in val:
                    domain_id = add_node('domain', domain_part, {'inferred': True})
                    add_edge(attr_id, domain_id, 'at_domain')
    
    return {'nodes': nodes, 'edges': edges}
```

**CRITICAL FEATURES:**
- **Root/Subject node** as anchor point
- **Automatic edge creation** from subject to all attributes
- **Automatic email → domain extraction** with 'inferred' flag
- **Metadata tracking** (sources, validation data)

### Server Implementation

**INCOMPLETE** - Server has C1Node creation but:
- No automatic graph generation from data
- No root node concept
- No automatic edge creation
- Manual edge creation required

---

## 4. Data Source Tracking

### Local Implementation (output.py lines 102-149)

```python
def add_with_source(data_list, value, source, validation=None, 
                    extract_domain=False, domain_list=None):
    """Add value with source tracking, avoiding duplicates"""
    
    # Check if value exists
    for item in data_list:
        if item['value'] == value_str:
            # Merge sources
            if source not in item['sources']:
                item['sources'].append(source)
            # Merge validation data
            if validation:
                item['validation'].update(validation)
            return
    
    # New value
    new_item = {'value': value_str, 'sources': [source]}
    if validation:
        new_item['validation'] = validation
    data_list.append(new_item)
```

**KEY FEATURES:**
- Every extracted value tracks **ALL sources** that found it
- Validation data (SMTP valid, phone type) attached to values
- Automatic domain extraction from emails
- Automatic deduplication

### Server Implementation

**PARTIAL** - Server tracks some metadata but:
- No systematic source tracking
- No validation data preservation
- No automatic merging across sources

---

## 5. Data Merging Across Sources

### Local Implementation (output.py lines 1140-1203)

```python
def merge_extracted_data(data1, data2):
    """Merge two data dicts, combining sources and maintaining IDs"""
    merged = {}
    
    for field_name in all_fields:
        value_map = {}  # normalized_value -> item
        
        # Process both sources
        for item in items1 + items2:
            normalized = normalize_value(item['value'])
            item_id = get_or_create_id(field_name, item['value'])
            
            if normalized in value_map:
                # Merge sources
                value_map[normalized]['sources'] += item['sources']
                # Merge validation
                value_map[normalized]['validation'].update(item['validation'])
            else:
                value_map[normalized] = item
            
            # Ensure same ID
            value_map[normalized]['id'] = item_id
        
        merged[field_name] = list(value_map.values())
    return merged
```

**CRITICAL FEATURE:**
- Can merge results from multiple API calls (DeHashed + OSINT Industries + RocketReach)
- Preserves all sources for each value
- Maintains consistent IDs across merges

### Server Implementation

**MISSING** - No merge system exists

---

## 6. Relationship Edge Types (Local vs Server)

### Local Relationship Types (output.py)

```python
# Direct relationships
'has_email', 'has_phone', 'has_username', 'has_alias'
'has_social', 'has_address', 'has_title'

# Contextual relationships  
'associated_domain', 'breached_on_domain', 'at_domain'
'associated_ip', 'worked_at', 'attended'

# Special relationships
'exposed_password', 'inferred' (metadata flag)
```

### Server Relationship Types (Would need to check ontology)

Server uses C1Bridge embedded_edges format. Need to verify if these relationship types exist in:
`input_output/ontology/relationships.json`

---

## 7. Node Templates

### Local Template Structure

```python
{
    'id': '<deterministic_hash>',
    'type': '<node_type>',
    'label': '<display_value>',
    'metadata': {
        'sources': ['RocketReach', 'OSINT Industries'],
        'validation': {'smtp_valid': True, 'type': 'work'},
        'is_root': False,
        'inferred': False  # For auto-extracted domains
    }
}
```

### Server Template (C1Node)

```python
C1Node(
    id=node_id,
    node_class="entity",  # or "source"
    type=c1_type,
    label=label,
    canonicalValue=canonical,
    metadata=metadata,
    source_system="eyed",
    embedded_edges=[],
    projectId=project_id
)
```

**KEY DIFFERENCES:**
- Local stores sources as list in metadata
- Local has validation data attached
- Local has 'inferred' flag for auto-generated nodes
- Server uses embedded_edges for relationships

---

## 8. Special Features in Local (NOT in Server)

### A. Email Domain Extraction (lines 86-101, 1292-1301)

```python
def extract_domain_from_email(email):
    """Extract domain from email address"""
    if '@' not in email:
        return None
    domain = email.split('@')[-1].strip().lower()
    # Basic validation
    if domain and '.' in domain and len(domain) > 3:
        return domain
    return None

# In graph generation:
if node_type == 'email' and '@' in val:
    domain_part = val.split('@')[1]
    domain_id = add_node('domain', domain_part, {'inferred': True})
    add_edge(email_id, domain_id, 'at_domain')
```

### B. Phone Normalization (server.py lines 322-399)

Both have phone normalization! Server version is actually MORE comprehensive:
- Handles US (+1), UK (+44), international formats
- Generates multiple variants to try
- Removes non-digit characters

**This is GOOD in server, should KEEP**

### C. Claude Text Cleaning (server.py lines 273-320)

Server has this, local doesn't:
```python
def should_clean_with_claude(text):
    """Check if text has malformed patterns"""
    # Checks for }, ], key-value patterns

def clean_with_claude(malformed_text):
    """Use Claude Haiku to clean corrupted data"""
    # Uses Haiku 4.5 to parse malformed addresses
```

**This is UNIQUE to server, should KEEP**

---

## 9. RECOMMENDATIONS: What to Port from Local to Server

### HIGH PRIORITY (Core Functionality)

1. **Global ID Map System**
   - Port normalize_value() function
   - Port ID_SCOPES dictionary
   - Port get_or_create_id() function
   - Integrate with existing _c1_generate_id()

2. **Email Domain Auto-Extraction**
   - Add extract_domain_from_email()
   - Automatically create domain nodes from email nodes
   - Add 'at_domain' edge type to ontology

3. **Data Source Tracking**
   - Add add_with_source() pattern
   - Store sources list in metadata
   - Merge sources when same value found multiple times

### MEDIUM PRIORITY (Enhanced Features)

4. **Graph Auto-Generation**
   - Port generate_graph_export() concept
   - Create subject/root node automatically
   - Auto-create edges from root to all entities

5. **Data Merge System**
   - Port merge_extracted_data() function
   - Enable combining multiple API results
   - Preserve all sources and validation data

6. **Validation Data Preservation**
   - Store SMTP validation for emails
   - Store phone type/validity
   - Attach to node metadata

### LOW PRIORITY (Nice to Have)

7. **Field Mappings Dictionary**
   - Create unified field_mappings dict
   - Standardize node types and edge types
   - Make edge types configurable

---

## 10. Implementation Plan

### Step 1: Core ID System (Do First)
```python
# Add to server.py after imports

_global_id_map = {}

ID_SCOPES = {
    'email': 'email',
    'phone': 'phone', 
    'username': 'username',
    'domain': 'domain',  # For registered_domains AND breach_domains
    'url': 'url',  # For linkedin_urls AND account_urls
}

def normalize_value(value: str) -> str:
    """Port from local output.py lines 1080-1106"""
    # Implement URL cleaning
    # Implement phone digit extraction
    # Implement whitespace collapsing
    pass

def get_or_create_id(field_type: str, value: str, project_id: str = None) -> str:
    """Enhanced version with project isolation"""
    normalized = normalize_value(value)
    scope = ID_SCOPES.get(field_type, field_type)
    
    # Project-scoped key
    key = (project_id or 'global', scope, normalized)
    
    if key not in _global_id_map:
        hash_input = f"{scope}:{normalized}"
        _global_id_map[key] = hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    return _global_id_map[key]
```

### Step 2: Email Domain Extraction
```python
def extract_domain_from_email(email: str) -> Optional[str]:
    """Port from local output.py lines 86-100"""
    # Add implementation
    pass

def auto_create_domain_node(email_node: C1Node, project_id: str):
    """Automatically create domain node from email"""
    if '@' in email_node.canonicalValue:
        domain = extract_domain_from_email(email_node.canonicalValue)
        if domain:
            domain_id = get_or_create_id('domain', domain, project_id)
            domain_node = C1Node(
                id=domain_id,
                node_class="entity",
                type="domain",
                label=domain,
                canonicalValue=domain,
                metadata={'inferred': True, 'source': 'email_extraction'},
                source_system="eyed",
                embedded_edges=[],
                projectId=project_id
            )
            # Add edge: email -> domain
            email_node.embedded_edges.append({
                'target_id': domain_id,
                'relation': 'at_domain'
            })
            return domain_node
    return None
```

### Step 3: Source Tracking in Metadata
```python
def add_source_to_node(node: C1Node, source: str, validation: Dict = None):
    """Add source tracking to node metadata"""
    if 'sources' not in node.metadata:
        node.metadata['sources'] = []
    if source not in node.metadata['sources']:
        node.metadata['sources'].append(source)
    
    if validation:
        if 'validation' not in node.metadata:
            node.metadata['validation'] = {}
        node.metadata['validation'].update(validation)
```

---

## 11. Testing Plan

1. **Test ID Consistency**
   - Same email from DeHashed and OSINT Industries should get same ID
   - Domain extracted from email should match domain from Whoxy

2. **Test Email Domain Extraction**
   - Create email node
   - Verify domain node created automatically
   - Verify 'at_domain' edge exists

3. **Test Source Tracking**
   - Run multiple searches for same entity
   - Verify sources list accumulates
   - Verify validation data merges

4. **Test Data Merging**
   - Merge results from DeHashed + OSINT Industries
   - Verify no duplicate nodes
   - Verify all sources preserved

---

## 12. Edge Types to Add to Ontology

These edge types from local need to be added to `input_output/ontology/relationships.json`:

```json
{
  "at_domain": {
    "label": "at domain",
    "description": "Email address is at this domain",
    "source_types": ["email"],
    "target_types": ["domain"]
  },
  "has_alias": {
    "label": "has alias",
    "description": "Person has this alternative name",
    "source_types": ["person"],
    "target_types": ["alias"]
  },
  "breached_on_domain": {
    "label": "breached on domain",
    "description": "Data was breached on this domain",
    "source_types": ["person", "email"],
    "target_types": ["domain"]
  },
  "exposed_password": {
    "label": "exposed password",
    "description": "Password exposed in breach",
    "source_types": ["person"],
    "target_types": ["password"]
  },
  "associated_ip": {
    "label": "associated IP",
    "description": "Associated with this IP address",
    "source_types": ["person", "email"],
    "target_types": ["ip"]
  },
  "worked_at": {
    "label": "worked at",
    "description": "Person worked at this company",
    "source_types": ["person"],
    "target_types": ["company"]
  },
  "attended": {
    "label": "attended",
    "description": "Person attended this school",
    "source_types": ["person"],
    "target_types": ["school"]
  }
}
```

---

## CONCLUSION

The local version has a **sophisticated deterministic node creation system** that ensures:
1. Same entity from multiple sources = same node (deduplication)
2. Automatic relationship discovery (email → domain)
3. Complete provenance tracking (all sources preserved)
4. Consistent IDs across project lifecycle

**The server is missing these core features.** Porting them would significantly improve data quality and reduce duplicate nodes.

**PRIORITY: Implement the ID generation system FIRST, then email domain extraction.**
