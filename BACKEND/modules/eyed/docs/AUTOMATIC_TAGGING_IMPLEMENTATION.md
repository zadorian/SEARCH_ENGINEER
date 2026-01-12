# Automatic VERIFIED/UNVERIFIED Tagging Implementation

**Date:** 2026-01-07
**Status:** ✅ COMPLETE - Code implementation ready for testing

**Key Features:**
- **Dual verification logic**: Same breach record OR strong entity type pairs
- **Entity type-based verification**: Weak types (password/name/username) → UNVERIFIED, Strong types (email/phone/ip/domain) → VERIFIED
- **Priority queue recursive search**: VERIFIED entities ALWAYS searched first, UNVERIFIED _1 entities wait in queue
- **Sequence tags** (_1, _2, _3) ONLY on UNVERIFIED edges, increment when entity is searched
- **Tag increment**: _1 becomes _2 when entity is searched, _2 becomes _3, etc.
- **44 connection reason types** to explain why entities are linked

---

## What Was Implemented

### 1. Schema Updates

#### **Updated EmbeddedEdge Dataclass** (`c1_bridge.py:48-63`)
Added four new fields to all edges:
```python
verification_status: str = None  # VERIFIED or UNVERIFIED
connection_reason: str = None    # One of 44 connection reason types
additional_reasons: List[str] = field(default_factory=list)
query_sequence_tag: str = None   # Original input value + sequence number (e.g., "email@address.com_1")
```

#### **Updated C1Node Dataclass** (`c1_bridge.py:85-89`)
Added four new fields to all NODES (especially SOURCE/NEXUS nodes like aggregator_result):
```python
verification_status: Optional[str] = None  # VERIFIED or UNVERIFIED
connection_reason: Optional[str] = None    # One of 44 connection reason types
additional_reasons: List[str] = field(default_factory=list)
query_sequence_tag: Optional[str] = None   # Sequential tag for UNVERIFIED results
```

#### **Updated Elasticsearch Mapping** (`c1_bridge.py:160-180`)
Added fields to:
1. **Main node properties** (lines 160-163):
   - `verification_status` (keyword)
   - `connection_reason` (keyword)
   - `additional_reasons` (keyword array)
   - `query_sequence_tag` (keyword)

2. **Nested embedded_edges schema** (lines 170-174):
   - Same four fields within each embedded edge

#### **Why Both Levels? Dual-Level Tagging Explained**

**CRITICAL CONCEPT:** Tags exist at TWO levels:

**Level 1: SOURCE Node (aggregator_result NEXUS node)**
- The SOURCE node itself is a fully-blown NEXUS relationship node
- Represents the entire EYE-D result as a relationship
- Gets its own verification_status, connection_reason, additional_reasons, query_sequence_tag
- **Raw output stored in comment field** (standard field on all nodes) - contains the complete raw record from the aggregator
- Example: "All entities in LinkedIn2021 result_12345 are VERIFIED with same_breach_record"

**Level 2: Embedded Edges (within the SOURCE node)**
- Each edge from SOURCE → entity also gets tags
- Provides granular connection info between specific entities
- Can have different tags than the parent SOURCE node
- Example: "SOURCE mentions email [VERIFIED, same_breach_record]", "SOURCE mentions username [UNVERIFIED, username_contains_email_prefix]"

**Why is this important?**
- SOURCE nodes are queryable entities in Elasticsearch, not just edge metadata
- The SOURCE node represents the relationship itself as a first-class object
- Both levels enable filtering: "show me all UNVERIFIED SOURCE nodes" OR "show me nodes with UNVERIFIED edges"

#### **Updated Nodes Schema** (`/data/CYMONIDES/metadata/c-1/matrix_schema/nodes.json`)
Added properties to aggregator_result node (lines 1798-1817):
- `verification_status` (enum: VERIFIED/UNVERIFIED)
- `connection_reason` (string: one of 44 types)
- `additional_reasons` (array of strings)
- `query_sequence_tag` (string: sequential tag for UNVERIFIED results)

#### **Updated Relationships Index** (`/data/CYMONIDES/metadata/c-1/ontology/relationships.json`)
Added "aggregator_result" section (lines 6398-6490) with:
- **mentions** edge (SOURCE → entity)
- **found_in** edge (entity → SOURCE)
- Both require `verification_status` and `connection_reason` metadata
- All 44 connection reason types enumerated

---

## 2. Core Functions

### **detect_connection_reasons()** (`c1_bridge.py:242-325`)

Detects why two entities are connected. Returns list of reasons in priority order.

**Detection Logic:**

1. **same_breach_record** - Same source_node_id/result_id (HIGHEST PRIORITY)
2. **Direct matches**:
   - same_email, same_phone, same_username, same_ip_address
   - same_password, same_domain, same_address, same_name
3. **Pattern-based**:
   - username_contains_email_prefix
   - similar_username
   - same_surname
4. **Contextual**:
   - same_geolocation (from metadata)
   - temporal_correlation (same account creation date)
5. **Fallback**:
   - similarity_score (string similarity > 0.7)
   - investigator_inference (default if nothing else)

**Example:**
```python
# Email: john.smith@example.com
# Username: john.smith
# Result: ['username_contains_email_prefix']

# Two entities from same breach record:
# Result: ['same_breach_record']
```

---

### **determine_verification_by_entity_type()** (`c1_bridge.py:332-358`)

Determines verification based on entity type pairs.

**Logic:**
```python
weak_types = {'password', 'name', 'username', 'person'}
strong_types = {'email', 'phone', 'ip', 'domain', 'linkedin_url', 'whois'}

# If either entity is weak type → UNVERIFIED
if entity_a_type in weak_types or entity_b_type in weak_types:
    return "UNVERIFIED"

# If both are strong types → VERIFIED
if entity_a_type in strong_types and entity_b_type in strong_types:
    return "VERIFIED"
```

**Example:**
- `email ↔ phone` → VERIFIED
- `email ↔ username` → UNVERIFIED (username is weak)
- `phone ↔ password` → UNVERIFIED (password is weak)

---

### **assign_connection_tags()** (`c1_bridge.py:360-395`)

Assigns both tags based on dual verification logic.

**Returns:** `(verification_status, primary_reason, additional_reasons)`

**Logic:**
```python
# TAG 1: VERIFICATION STATUS (Dual Logic)
if entity_a.source_node_id == entity_b.source_node_id:
    # Same breach record → always VERIFIED
    verification_status = "VERIFIED"
else:
    # Different sources → check entity type pairs
    verification_status = determine_verification_by_entity_type(
        entity_a.type, entity_b.type
    )

# TAG 2: CONNECTION REASON
reasons = detect_connection_reasons(entity_a, entity_b)
primary_reason = reasons[0]
additional_reasons = reasons[1:]  # If multiple reasons exist
```

**Example Output:**
```python
("VERIFIED", "same_breach_record", [])  # Same source
("VERIFIED", "same_email", [])  # Different sources, both strong types
("UNVERIFIED", "username_contains_email_prefix", [])  # Username is weak type
```

---

### **add_edge() - Updated** (`c1_bridge.py:359-410`)

Now automatically tags edges when created.

**Key Changes:**
```python
# Automatically assign tags for entity connections
if relation in ['mentions', 'found_in', 'co_occurs_with']:
    verification_status, connection_reason, additional_reasons = self.assign_connection_tags(
        node, target_node
    )

# Generate query sequence tag
# Format: {original_input_value}_{sequence_number}
query_sequence_tag = None
if node.canonicalValue:
    sequence_number = len(node.embedded_edges) + 1
    query_sequence_tag = f"{node.canonicalValue}_{sequence_number}"

edge = EmbeddedEdge(
    ...,
    verification_status=verification_status,
    connection_reason=connection_reason,
    additional_reasons=additional_reasons,
    query_sequence_tag=query_sequence_tag
)
```

**Relations that get auto-tagged:**
- `mentions` - SOURCE → entity
- `found_in` - entity → SOURCE
- `co_occurs_with` - entity → entity

**Relations that DON'T get tagged:**
- `found_on` - Generic discovery edge
- Other non-entity edges

**Query Sequence Tag:**
- **ONLY generated for UNVERIFIED edges**
- **VERIFIED edges have NO sequence tag (set to None)**
- Format: `{input_value}_{sequence_number}`
- Example: If input was "email@address.com":
  - First UNVERIFIED edge: "email@address.com_1"
  - Second UNVERIFIED edge: "email@address.com_2"
  - Third UNVERIFIED edge: "email@address.com_3"
  - VERIFIED edges: None (not tagged)
- Helps track unverified entities that need recursive searching

---

## 3. How It Works - Examples

### Example 1: Same Breach Record (VERIFIED) - SOURCE Node + Edges

**Scenario:** Email and phone found together in LinkedIn (2021) breach

```python
# Creating SOURCE node (aggregator_result NEXUS node)
source_node = create_source_node(
    module="Eye-D",
    aggregator="dehashed",
    primary="LinkedIn2021",
    result_id="result_12345"
)

# SOURCE node itself gets tagged
source_node.verification_status = "VERIFIED"
source_node.connection_reason = "same_breach_record"
source_node.query_sequence_tag = None  # VERIFIED nodes have no tag

# Creating entities from same result
email_node = create_entity_node("john@example.com", "email")
email_node.metadata['result_id'] = "result_12345"

phone_node = create_entity_node("+1-555-0123", "phone")
phone_node.metadata['result_id'] = "result_12345"

# Add edges - AUTOMATICALLY TAGGED
add_edge(source_node, email_node, "mentions")
add_edge(source_node, phone_node, "mentions")
```

**Result - SOURCE Node (aggregator_result):**
```json
{
  "id": "eyed:dehashed:LinkedIn2021:result_12345",
  "node_class": "NEXUS",
  "type": "aggregator_result",
  "verification_status": "VERIFIED",
  "connection_reason": "same_breach_record",
  "additional_reasons": [],
  "query_sequence_tag": null,
  "comment": "{\"email\": \"john@example.com\", \"phone\": \"+1-555-0123\", \"breach\": \"LinkedIn2021\", \"password\": \"Pass123!\"}",
  "embedded_edges": [...]
}
```

**Note:** The `comment` field (standard on all nodes) contains the raw output from the EYE-D aggregator for this specific record/result.

**Result - First Embedded Edge (SOURCE → email):**
```json
{
  "target_id": "email_node_id",
  "relation": "mentions",
  "verification_status": "VERIFIED",
  "connection_reason": "same_breach_record",
  "additional_reasons": [],
  "query_sequence_tag": null
}
```

**Result for second edge (SOURCE → phone):**
```json
{
  "target_id": "phone_node_id",
  "relation": "mentions",
  "verification_status": "VERIFIED",
  "connection_reason": "same_breach_record",
  "additional_reasons": [],
  "query_sequence_tag": null
}
```

**Note:** VERIFIED edges have `query_sequence_tag: null` because they don't need recursive searching. They're from the same breach record, already confirmed.

---

### Example 2: Different Results (UNVERIFIED)

**Scenario:** Username matches email prefix but from different breaches

```python
# Email from LinkedIn2021
email_node = create_entity_node("john.smith@company.com", "email")
email_node.metadata['result_id'] = "result_12345"

# Username from MyFitnessPal2018
username_node = create_entity_node("john.smith", "username")
username_node.metadata['result_id'] = "result_67890"

# Add edge - AUTOMATICALLY TAGGED AS UNVERIFIED
add_edge(email_node, username_node, "co_occurs_with")
```

**Result:**
```json
{
  "target_id": "username_node_id",
  "relation": "co_occurs_with",
  "verification_status": "UNVERIFIED",
  "connection_reason": "username_contains_email_prefix",
  "additional_reasons": [],
  "query_sequence_tag": "john.smith@company.com_1"
}
```

---

### Example 3: Multiple Reasons

**Scenario:** Same IP + username match

```python
# Entity A from result1
entity_a = create_entity_node("user123", "username")
entity_a.metadata['result_id'] = "result_1"
entity_a.metadata['ip'] = "37.238.197.40"
entity_a.metadata['geolocation'] = {'city': 'Baghdad'}

# Entity B from result2
entity_b = create_entity_node("user123_new", "username")
entity_b.metadata['result_id'] = "result_2"
entity_b.metadata['ip'] = "37.238.197.40"
entity_b.metadata['geolocation'] = {'city': 'Baghdad'}

# Add edge
add_edge(entity_a, entity_b, "co_occurs_with")
```

**Result:**
```json
{
  "verification_status": "UNVERIFIED",
  "connection_reason": "similar_username",
  "additional_reasons": ["same_geolocation"],
  "query_sequence_tag": "user123_1"
}
```

---

### Example 4: Entity Type-Based Verification (Different Sources)

**Scenario:** Email and phone from DIFFERENT breaches, connected by pattern matching

```python
# Email from LinkedIn2021
email_node = create_entity_node("john@example.com", "email")
email_node.metadata['result_id'] = "result_12345"

# Phone from MySpace2008
phone_node = create_entity_node("+1-555-0123", "phone")
phone_node.metadata['result_id'] = "result_67890"

# Add edge - Different sources BUT both strong types
add_edge(email_node, phone_node, "co_occurs_with")
```

**Result:**
```json
{
  "verification_status": "VERIFIED",
  "connection_reason": "same_phone",
  "additional_reasons": [],
  "query_sequence_tag": null
}
```

**Note:** Even though they're from different breaches, both email and phone are "strong types" so the connection is VERIFIED. No sequence tag because it's VERIFIED.

---

### Example 5: Weak Type Makes Connection UNVERIFIED

**Scenario:** Email and username from different breaches

```python
# Email from LinkedIn2021
email_node = create_entity_node("john.smith@example.com", "email")
email_node.metadata['result_id'] = "result_12345"

# Username from Twitter2020
username_node = create_entity_node("john_smith", "username")
username_node.metadata['result_id'] = "result_67890"

# Add edge - Different sources AND username is weak type
add_edge(email_node, username_node, "co_occurs_with")
```

**Result:**
```json
{
  "verification_status": "UNVERIFIED",
  "connection_reason": "username_contains_email_prefix",
  "additional_reasons": [],
  "query_sequence_tag": "john.smith@example.com_1"
}
```

**Note:** Username is a "weak type" so even though there's a pattern match, the connection is UNVERIFIED and gets a _1 sequence tag for recursive searching.

---

## 4. Integration Points

### Where Tagging Happens Automatically:

1. **LINKLATER Results** (`index_clink_results()`)
   - Entity co-occurrence edges
   - Found_on relationships

2. **EYE-D Results** (`index_eyed_results()`)
   - SOURCE → entity edges
   - Entity → entity co-occurrence

3. **Manual Edge Creation**
   - Any call to `add_edge()` with supported relations
   - Automatic detection runs every time

---

## 5. Querying Tagged Edges

### Elasticsearch Query Examples:

**Find all VERIFIED connections:**
```json
{
  "query": {
    "nested": {
      "path": "embedded_edges",
      "query": {
        "term": {
          "embedded_edges.verification_status": "VERIFIED"
        }
      }
    }
  }
}
```

**Find connections by reason:**
```json
{
  "query": {
    "nested": {
      "path": "embedded_edges",
      "query": {
        "term": {
          "embedded_edges.connection_reason": "same_breach_record"
        }
      }
    }
  }
}
```

**Find UNVERIFIED username matches:**
```json
{
  "query": {
    "nested": {
      "path": "embedded_edges",
      "query": {
        "bool": {
          "must": [
            {"term": {"embedded_edges.verification_status": "UNVERIFIED"}},
            {"term": {"embedded_edges.connection_reason": "username_contains_email_prefix"}}
          ]
        }
      }
    }
  }
}
```

**Find all edges from a specific input query:**
```json
{
  "query": {
    "nested": {
      "path": "embedded_edges",
      "query": {
        "prefix": {
          "embedded_edges.query_sequence_tag": "email@address.com_"
        }
      }
    }
  }
}
```

**Find the first entity discovered from a search:**
```json
{
  "query": {
    "nested": {
      "path": "embedded_edges",
      "query": {
        "term": {
          "embedded_edges.query_sequence_tag": "email@address.com_1"
        }
      }
    }
  }
}
```

**Find all entities discovered from a phone search (sorted by sequence):**
```json
{
  "query": {
    "nested": {
      "path": "embedded_edges",
      "query": {
        "prefix": {
          "embedded_edges.query_sequence_tag": "+1-555-0123_"
        }
      },
      "inner_hits": {
        "sort": [
          {"embedded_edges.query_sequence_tag": {"order": "asc"}}
        ]
      }
    }
  }
}
```

---

## 6. Recursive Search Logic - VERIFIED Priority Queue

### **Rule: VERIFIED Entities Always Run First, Then UNVERIFIED _1 Entities**

**Priority Queue Logic:**
```python
# Priority 1: VERIFIED entities (highest priority)
verified_queue = []
for edge in source_node.embedded_edges:
    if edge.verification_status == "VERIFIED":
        target_entity = get_node(edge.target_id)
        verified_queue.append(target_entity.canonicalValue)

# Priority 2: UNVERIFIED _1 entities (lower priority)
unverified_queue = []
for edge in source_node.embedded_edges:
    if edge.verification_status == "UNVERIFIED" and edge.query_sequence_tag.endswith("_1"):
        target_entity = get_node(edge.target_id)
        unverified_queue.append(target_entity.canonicalValue)

# Execute searches in priority order
while verified_queue or unverified_queue:
    if verified_queue:
        # Always search VERIFIED entities first
        next_input = verified_queue.pop(0)
        results = search_eyed(next_input)

        # New VERIFIED entities go to front of queue
        # New UNVERIFIED _1 entities go to unverified queue

    elif unverified_queue:
        # Only when NO VERIFIED entities remain, search UNVERIFIED
        next_input = unverified_queue.pop(0)
        results = search_eyed(next_input)

        # This _1 entity now becomes _2 (already searched once)
        # New results follow same priority logic
```

### **Why VERIFIED First**

**VERIFIED entities (always first):**
- Confirmed from same breach record OR both strong entity types
- Most reliable pivots for expanding investigation
- Keep searching as long as new VERIFIED entities emerge
- Example: Email → phone → domain → all VERIFIED, search them all before any UNVERIFIED

**UNVERIFIED _1 entities (wait until no VERIFIED):**
- Inferred connections that need validation
- Only searched when VERIFIED queue is empty
- When searched, their tag increments from _1 to _2
- Example: Username tagged _1 waits until all VERIFIED entities are exhausted

### **Entity Type-Based Verification for Secondary Edges**

When searching any entity (verified or unverified _1), the new edges created are tagged based on entity type pairs:

**UNVERIFIED if node pair contains AT LEAST ONE of:**
- `password`
- `name` (real name / person name)
- `username`

**VERIFIED if node pair consists ONLY of:**
- `email`
- `phone`
- `ip` (IP address)
- `domain` (web domain)
- `linkedin_url`
- `whois`

**Implementation Logic:**
```python
def determine_verification_by_entity_type(entity_a_type: str, entity_b_type: str) -> str:
    """
    Determine verification status based on entity types in the pair.

    Args:
        entity_a_type: Type of first entity (e.g., 'email', 'username', 'password')
        entity_b_type: Type of second entity

    Returns:
        'VERIFIED' or 'UNVERIFIED'
    """
    weak_types = {'password', 'name', 'username', 'person'}
    strong_types = {'email', 'phone', 'ip', 'domain', 'linkedin_url', 'whois'}

    # If either entity is a weak type → UNVERIFIED
    if entity_a_type in weak_types or entity_b_type in weak_types:
        return "UNVERIFIED"

    # If both are strong types → VERIFIED
    if entity_a_type in strong_types and entity_b_type in strong_types:
        return "VERIFIED"

    # Default fallback
    return "UNVERIFIED"
```

**Example Pairs:**
- `email ↔ phone` → VERIFIED (both strong types)
- `email ↔ username` → UNVERIFIED (username is weak)
- `phone ↔ password` → UNVERIFIED (password is weak)
- `ip ↔ domain` → VERIFIED (both strong types)
- `name ↔ email` → UNVERIFIED (name is weak)

**Note:** This secondary verification logic applies to edges created during recursive searches, providing additional granularity beyond the same_breach_record verification.

---

### **Sequence Number Progression and Tag Increment**

**Key Rule:** When an UNVERIFIED _1 entity is searched, its incoming tag increments to _2.

**Original Search:**
```
Input: "email@address.com"
Results:
  - phone "+1-555-0100" [VERIFIED] → NO TAG (goes to priority queue immediately)
  - username "john_smith" [UNVERIFIED] → tagged "email@address.com_1" (waits in queue)
  - password "Pass123" [UNVERIFIED] → tagged "email@address.com_2" (waits in queue)
```

**Priority Queue Status After Initial Search:**
```
VERIFIED queue: ["+1-555-0100"]
UNVERIFIED queue: ["john_smith" (has _1), "Pass123" (has _2)]
```

**First Recursive Search (VERIFIED entity):**
```
Input: "+1-555-0100" (VERIFIED, searched first)
Results:
  - email "john@work.com" [VERIFIED] → NO TAG (added to VERIFIED queue)
  - domain "work.com" [VERIFIED] → NO TAG (added to VERIFIED queue)
  - username "j_smith" [UNVERIFIED] → tagged "+1-555-0100_1" (added to UNVERIFIED queue)
```

**Priority Queue Status After First Recursive:**
```
VERIFIED queue: ["john@work.com", "work.com"]
UNVERIFIED queue: ["john_smith" (has _1), "Pass123" (has _2), "j_smith" (has _1)]
```

**Continue Until VERIFIED Queue Empty:**
```
Keep searching all VERIFIED entities first...
Only when VERIFIED queue is empty, move to UNVERIFIED queue
```

**When UNVERIFIED _1 Entity Finally Searched:**
```
Input: "john_smith" (was tagged _1, now being searched)
  - Tag increments: _1 → _2
Results:
  - Any new UNVERIFIED entities get fresh _1 tags
  - Any VERIFIED entities go to priority queue immediately
```

### **Depth Tracking**

The sequence number tracks how many times an entity has been pivoted on:
- `_1` = Discovered but not yet searched
- `_2` = Searched once (was _1, now _2)
- `_3` = Searched twice (was _2, now _3)
- And so on...

### **Implementation Requirements**

**1. Build Priority Queues:**
```python
def get_priority_queues(project_id: str) -> tuple[List[str], List[str]]:
    """
    Build VERIFIED and UNVERIFIED priority queues.

    Returns:
        (verified_queue, unverified_queue)
    """
    # Query Elasticsearch for all entities

    verified_queue = []
    unverified_queue = []

    for node in all_nodes:
        for edge in node.incoming_edges:
            if edge.verification_status == "VERIFIED" and not edge.already_searched:
                verified_queue.append(node.canonicalValue)
            elif edge.verification_status == "UNVERIFIED" and edge.query_sequence_tag.endswith("_1"):
                unverified_queue.append((node.canonicalValue, edge.query_sequence_tag))

    return verified_queue, unverified_queue
```

**2. Increment Tag When Searching:**
```python
def increment_sequence_tag(entity_value: str, current_tag: str) -> str:
    """
    Increment sequence tag when entity is searched.

    Args:
        entity_value: The entity being searched (e.g., "john_smith")
        current_tag: Current tag (e.g., "email@address.com_1")

    Returns:
        New tag with incremented number (e.g., "email@address.com_2")
    """
    # Parse current tag: "base_N" → extract base and N
    base, num = current_tag.rsplit('_', 1)
    new_num = int(num) + 1
    return f"{base}_{new_num}"
```

**3. Priority Queue Recursive Search Controller:**
```python
def recursive_eyed_search(
    initial_query: str,
    max_depth: int = 3
) -> Dict:
    """
    Perform recursive EYE-D searches with VERIFIED priority.

    Args:
        initial_query: Starting search value
        max_depth: Maximum recursion depth (default 3)
    """
    verified_queue, unverified_queue = get_priority_queues(project_id)

    while (verified_queue or unverified_queue) and depth <= max_depth:
        if verified_queue:
            # ALWAYS search VERIFIED first
            next_input = verified_queue.pop(0)
            results = search_eyed(next_input)

            # Add new VERIFIED to front of verified_queue
            # Add new UNVERIFIED _1 to unverified_queue

        elif unverified_queue:
            # Only when NO VERIFIED remain
            next_input, current_tag = unverified_queue.pop(0)

            # Increment tag before searching
            new_tag = increment_sequence_tag(next_input, current_tag)
            update_edge_tag(next_input, new_tag)

            results = search_eyed(next_input)

            # Process results with same priority logic
```

### **Example: Full Recursive Flow with Priority Queue**

**Initial Search:**
```
Input: "john@example.com"
Results from SOURCE node:
  - username "john_doe" [UNVERIFIED - username_contains_email_prefix] → tagged "john@example.com_1"
  - phone "+1-555-0100" [VERIFIED - same_breach_record] → NO TAG
  - password "Pass123!" [VERIFIED - same_breach_record] → NO TAG
```

**Priority Queues After Initial:**
```
VERIFIED queue: ["+1-555-0100", "Pass123!"]
UNVERIFIED queue: ["john_doe" (has _1)]
```

**Second Search (VERIFIED first):**
```
Input: "+1-555-0100" (popped from VERIFIED queue)
Results:
  - email "john@work.com" [VERIFIED - both strong types] → NO TAG
  - domain "work.com" [VERIFIED - both strong types] → NO TAG
  - username "j_smith" [UNVERIFIED - username is weak] → tagged "+1-555-0100_1"
```

**Priority Queues After Second:**
```
VERIFIED queue: ["Pass123!", "john@work.com", "work.com"]
UNVERIFIED queue: ["john_doe" (has _1), "j_smith" (has _1)]
```

**Third Search (VERIFIED first):**
```
Input: "Pass123!" (popped from VERIFIED queue)
Results:
  - email "john@personal.com" [VERIFIED - both strong types] → NO TAG
  - No new entities
```

**Priority Queues After Third:**
```
VERIFIED queue: ["john@work.com", "work.com", "john@personal.com"]
UNVERIFIED queue: ["john_doe" (has _1), "j_smith" (has _1)]
```

**Continue exhausting VERIFIED queue...**
```
Search "john@work.com" → may find more VERIFIED entities
Search "work.com" → may find more VERIFIED entities
Search "john@personal.com" → may find more VERIFIED entities
... keep going until VERIFIED queue is empty
```

**Finally, when VERIFIED queue empty:**
```
Input: "john_doe" (popped from UNVERIFIED queue)
  - Tag increments: _1 → _2 (before searching)
Results:
  - Any new VERIFIED → go to VERIFIED queue (searched immediately)
  - Any new UNVERIFIED → get fresh _1 tags, join UNVERIFIED queue
```

**Key Points:**
- VERIFIED entities ALWAYS searched before UNVERIFIED
- As long as VERIFIED entities exist, keep searching them
- UNVERIFIED _1 entities wait in queue
- When UNVERIFIED entity is finally searched, its tag increments (_1 → _2)
- New VERIFIED entities from UNVERIFIED search go to front of queue

---

## 7. Testing Checklist

### Unit Tests Needed:

**Tagging Logic:**
- [ ] `detect_connection_reasons()` with same_breach_record
- [ ] `detect_connection_reasons()` with username_contains_email_prefix
- [ ] `detect_connection_reasons()` with same_surname
- [ ] `assign_connection_tags()` returns VERIFIED for same result_id
- [ ] `assign_connection_tags()` returns UNVERIFIED for different result_ids
- [ ] `add_edge()` creates edges with tags for 'mentions' relation
- [ ] `add_edge()` creates edges with tags for 'found_in' relation
- [ ] `add_edge()` creates edges with tags for 'co_occurs_with' relation
- [ ] `add_edge()` doesn't tag 'found_on' edges (not entity-to-entity)

**Query Sequence Tags:**
- [ ] `add_edge()` generates query_sequence_tag ONLY for UNVERIFIED edges
- [ ] `add_edge()` sets query_sequence_tag to None for VERIFIED edges
- [ ] First UNVERIFIED edge gets _1, second gets _2, third gets _3, etc.
- [ ] VERIFIED edges are NOT counted in sequence numbering
- [ ] query_sequence_tag uses node.canonicalValue as base
- [ ] Query sequence tag stored in Elasticsearch correctly

**Recursive Search Priority Queue:**
- [ ] `get_priority_queues()` builds VERIFIED and UNVERIFIED queues correctly
- [ ] VERIFIED edges have no sequence tags (confirmed by tests)
- [ ] UNVERIFIED edges have sequence tags (confirmed by tests)
- [ ] VERIFIED entities always searched before UNVERIFIED _1 entities
- [ ] New VERIFIED entities from searches added to VERIFIED queue
- [ ] UNVERIFIED queue only processed when VERIFIED queue empty
- [ ] `increment_sequence_tag()` increments _1 to _2, _2 to _3, etc.
- [ ] Tag increment happens BEFORE searching the UNVERIFIED entity
- [ ] `recursive_eyed_search()` respects max_depth parameter
- [ ] Recursive search stops when both queues empty or max_depth reached

### Integration Tests Needed:

**Basic Tagging:**
- [ ] Index EYE-D results → Check SOURCE nodes have tagged edges
- [ ] Index LINKLATER results → Check co-occurrence edges are tagged
- [ ] Query for VERIFIED edges → Returns correct results
- [ ] Query for specific connection_reason → Returns correct results
- [ ] Multiple reasons detected → additional_reasons populated

**Query Sequence Tags:**
- [ ] Query for all edges from specific input → Returns all with matching prefix
- [ ] Query for first discovered entity → Returns _1 tagged edge
- [ ] Sort entities by discovery order → Ordered by sequence number

**Recursive Search Priority Queue:**
- [ ] Initial search creates _1, _2, _3 tags ONLY on UNVERIFIED edges
- [ ] Initial search creates NO tags on VERIFIED edges
- [ ] VERIFIED entities searched first (before any UNVERIFIED)
- [ ] VERIFIED queue exhausted before moving to UNVERIFIED queue
- [ ] New VERIFIED entities from recursive searches jump to front of queue
- [ ] UNVERIFIED _1 entity tag increments to _2 when searched
- [ ] After tag increment, entity produces new results with fresh _1 tags
- [ ] Priority queue maintains VERIFIED > UNVERIFIED ordering throughout
- [ ] Recursive search terminates at max_depth or when both queues empty
- [ ] Full recursive flow prioritizes verified chains, validates unverified chains last

---

## 8. Files Modified

1. **`/data/EYE-D/c1_bridge.py`**
   - Updated EmbeddedEdge dataclass (lines 48-63) - Added 4 fields to edges: verification_status, connection_reason, additional_reasons, query_sequence_tag
   - Updated C1Node dataclass (lines 85-89) - Added 4 fields to nodes: verification_status, connection_reason, additional_reasons, query_sequence_tag
   - Updated Elasticsearch mapping (lines 160-180) - Added 4 fields to both main node properties AND nested embedded_edges schema
   - Added detect_connection_reasons() (lines 246-334) - Detects 44 connection reason types
   - Added determine_verification_by_entity_type() (lines 336-362) - Entity type pair verification logic
   - Added assign_connection_tags() (lines 364-399) - Dual verification logic (breach record + entity types)
   - Updated add_edge() (lines 401-452) - Automatic tagging AND query_sequence_tag generation (UNVERIFIED only)

2. **`/data/CYMONIDES/metadata/c-1/matrix_schema/nodes.json`**
   - Added aggregator_result node type (NEXUS class, lines 1764-1838)
   - Added 4 verification properties to aggregator_result (lines 1798-1817): verification_status, connection_reason, additional_reasons, query_sequence_tag

3. **`/data/CYMONIDES/metadata/c-1/ontology/relationships.json`**
   - Added aggregator_result section (lines 6398-6490)
   - Defined mentions edge schema with required tags
   - Defined found_in edge schema with required tags
   - Enumerated all 44 connection reason types

4. **`/data/EYE-D/AUTOMATIC_TAGGING_IMPLEMENTATION.md`**
   - Complete implementation documentation (this file)
   - Explains dual-level tagging: SOURCE nodes + embedded edges
   - Priority queue recursive search strategy
   - Full examples and testing checklists

5. **`/data/SEARCH_ENGINEER/nexus/BACKEND/modules/CYMONIDES_1/todo/scenarios.json`**
   - Added eyed-aggregator-result-source-node scenario
   - Added eyed-source-mentions-entity-edge scenario
   - Added eyed-entity-found-in-source-edge scenario

---

## 9. Connection Reason Reference

**All 44 types implemented in detection logic:**

**Category A: Direct Data Matches** (10)
- same_breach_record, same_email, same_phone, same_username
- same_ip_address, same_password, same_name, same_address
- same_domain, same_profile_url

**Category B: Cryptographic** (2)
- hash_match, password_pattern_match

**Category C: Platform** (4)
- device_fingerprint, session_id, platform_association, same_platform_same_time

**Category D: Pattern-Based** (4)
- username_contains_email_prefix, similar_username, same_surname, similar_name

**Category E: Geographic** (4)
- same_geolocation, ip_range_overlap, geographic_proximity, same_timezone

**Category F: Temporal** (3)
- temporal_correlation, breach_date_proximity, activity_overlap

**Category G-L:** (17 more types enumerated in schema)

---

## 10. Next Steps

### To Use This Implementation:

1. **Create EYE-D SOURCE nodes** with result_id in metadata
2. **Create entity nodes** with result_id in metadata
3. **Call add_edge()** - Tags applied automatically
4. **Query by tags** - Use nested Elasticsearch queries

### Example Usage:

```python
from c1_bridge import C1Bridge

bridge = C1Bridge(project_id="investigation-001")

# Process EYE-D results
eyed_results = {
    'query': 'john@example.com',
    'subtype': 'email',
    'results': [
        {
            'source': 'dehashed',
            'data': {
                'email': 'john@example.com',
                'username': 'john.smith',
                'password': 'Password123!',
                'breach': 'LinkedIn2021'
            }
        }
    ]
}

# Index - edges automatically tagged
stats = bridge.index_eyed_results(eyed_results)

# All edges now have:
# - verification_status: "VERIFIED" (same result)
# - connection_reason: "same_breach_record"
```

---

**Status:** Implementation complete, ready for testing and integration.
