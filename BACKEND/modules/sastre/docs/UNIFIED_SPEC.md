# SASTRE UNIFIED SPECIFICATION

-----

# PART 0: THE UNIFIED SYNTAX

One syntax for everything. Target determines scope.

## THE PRINCIPLE

**The agent is a translator, not a programmer.**

The agent doesn't need to understand module internals. It speaks a **search programming language** at the macro level:

- Understands operators and their meaning
- Knows which operators to chain for which intent
- Translates user narrative into syntax
- Triggers execution without understanding execution

```
USER: "Find offshore companies connected to John Smith"
         ↓
AGENT: Translates intent to syntax (doesn't know how registry? works internally)
         ↓
SYNTAX: "John Smith" AND #OFFSHORE => ent? => registry?
         ↓
MODULES: Execute (agent doesn't see this)
         ↓
USER: Sees findings
```

The agent is **fluent in the language** but **ignorant of the machinery**. Like a translator who speaks French perfectly but doesn't know how the printing press works.

**Why this matters:**

- Agent doesn't need retraining when modules change
- New modules just need new operator names
- Agent reasons at intent level, not implementation level
- Syntax is the stable interface between agent and system

-----

## THE SYNTAX

```
OPERATOR :TARGET [TARGET...] [=> #tag]
```

### Target Type Determines Scope

|Target      |Scope        |
|------------|-------------|
|`domain.com`|External web |
|`#nodename` |Internal grid|

### Position of `!` Determines Expansion

|Position  |Web                    |Grid              |
|----------|-----------------------|------------------|
|`!` prefix|Root domain (all pages)|Node + all related|
|`!` suffix|Specific page only     |That node only    |

### Examples: Web vs Grid

```
# Web - domain vs page
"keyword" :!domain.com        # search entire domain
"keyword" :domain.com/page!   # search that page only

ent? :!domain.com             # extract from domain (all pages)
ent? :domain.com/page!        # extract from that page only

bl? :!domain.com              # backlinks to domain
ol? :!domain.com              # outlinks from domain

# Grid - expanded vs contracted
"keyword" :!#tag3             # search all nodes linked to #tag3
"keyword" :#tag3!             # search only #tag3's content

ent? :!#querynode             # extract from node + related
ent? :#querynode!             # extract from that node only

p? :!#sourcenode              # persons from source + related
c? :#sourcenode!              # companies from that source only

# Multiple targets
ent? :!#query1 !#query2 !#source => #EXTRACTED

# Chain
ent? :!#querynode => #NEW => enrich? => #ENRICHED
```

### Universal Rule

- `!` prefix = scope **expands** (domain / node + edges)
- `!` suffix = scope **contracts** (page / single node)

Same operators, same positional logic. Target determines external vs internal.

-----

## OPERATORS REFERENCE

### Extraction Operators

|Operator|Extracts    |Example               |
|--------|------------|----------------------|
|`ent?`  |All entities|`ent? :!domain.com`   |
|`p?`    |Persons     |`p? :!#source`        |
|`c?`    |Companies   |`c? :domain.com/page!`|
|`e?`    |Emails      |`e? :!#querynode`     |
|`t?`    |Telephones  |`t? :!domain.com`     |
|`a?`    |Addresses   |`a? :#source!`        |

### Link Operators

|Operator|Returns         |Example                |
|--------|----------------|-----------------------|
|`bl?`   |Backlink pages  |`bl? :!domain.com`     |
|`?bl`   |Backlink domains|`?bl :!domain.com`     |
|`ol?`   |Outlink pages   |`ol? :domain.com/page!`|
|`?ol`   |Outlink domains |`?ol :!domain.com`     |

### Enrichment Operators

|Operator    |Does                      |Example               |
|------------|--------------------------|----------------------|
|`enrich?`   |Fill entity slots         |`enrich? :!#company`  |
|`sanctions?`|Check sanctions lists     |`sanctions? :!#person`|
|`registry?` |Check corporate registries|`registry? :#company!`|
|`whois?`    |Domain registration       |`whois? :domain.com`  |

### Result Type (? position)

|Position    |Returns       |
|------------|--------------|
|`?op` prefix|Domains/unique|
|`op?` suffix|Pages/all     |

-----

## ACTION SCOPE ON GRID

When targeting grid nodes, actions apply to target + related nodes (with `!` prefix), filtered by applicability.

```
ent? :!#querynode
```

1. Target: `#querynode`
1. `!` prefix: Expand to related nodes
1. Related: All SourceResults connected to query
1. `ent?` applies to: Sources (not queries)
1. Execute: Extract entities from each source

```
#querynode
    │
    ├── source_1 → ent?
    ├── source_2 → ent?
    └── source_3 → ent?
```

If `ent? :#querynode!` — only that node, no expansion.

### Applicability Filter

Actions auto-filter to applicable node types:

|Operator          |Applies To        |
|------------------|------------------|
|`ent?`, `p?`, `c?`|@SOURCE, @DOCUMENT|
|`enrich?`         |@PERSON, @COMPANY |
|`sanctions?`      |@PERSON, @COMPANY |
|`registry?`       |@COMPANY          |
|`bl?`, `ol?`      |@SOURCE, @DOMAIN  |

-----

# PART 1: QUERY DIMENSIONS

## INTENT: THE 2x2

|            |SUBJECT                         |LOCATION                              |
|------------|--------------------------------|--------------------------------------|
|**ENRICH**  |Fill slots on known entity/topic|Check known jurisdiction/source/time  |
|**DISCOVER**|Find new entities/topics        |Find new jurisdictions/sources/periods|

-----

## THE TWO DIMENSIONS

### SUBJECT Dimension (WHO/WHAT)

**Entity** - The person, company, asset

- Known: `#john_smith`
- Unknown: `"John Smith"`
- Class: `@PERSON`, `@COMPANY`, `@ASSET`

**Topic/Theme** - The subject matter

- `#FRAUD`, `#SANCTIONS`, `#CORRUPTION`
- `"money laundering"`, `"shell company"`

**Industry/Sector** - The business domain

- `#FINTECH`, `#REAL_ESTATE`, `#OIL_GAS`, `#CRYPTO`
- `"pharmaceutical"`, `"defense contractor"`

**Event** - The occurrence

- `#IPO`, `#BANKRUPTCY`, `#MERGER`, `#INVESTIGATION`
- `"acquisition"`, `"delisting"`, `"indictment"`

All are SUBJECT. You're asking "what am I looking for?"

### LOCATION Dimension (WHERE/WHEN)

**Jurisdiction** - Legal geography

- `##jurisdiction:CY`, `##jurisdiction:PA`
- `#OFFSHORE` (tag group)

**Source** - Information geography

- `site:companies.gov.cy`
- `##source:registry`, `##source:court`, `##source:news`

**Time** - Temporal geography

- `##2020`, `##2019-2023`
- `##before:2020`, `##after:2015`

All are LOCATION. You're asking "where/when am I looking?"

-----

## THE INTERSECTIONS ARE EVERYTHING

Every AND creates an intersection. Intelligence lives at intersections.

```
#john_smith AND #FINTECH AND ##jurisdiction:CY AND ##2020
     │              │              │                │
   Entity       Industry      Jurisdiction        Time
```

**NEXUS must consider ALL dimension combinations:**

|Intersection                           |Question                          |
|---------------------------------------|----------------------------------|
|Entity + Entity                        |Are these people connected?       |
|Entity + Topic                         |Is this person linked to fraud?   |
|Entity + Industry                      |Does he work in fintech?          |
|Entity + Event                         |Was he involved in the IPO?       |
|Entity + Jurisdiction                  |Does he appear in Cyprus?         |
|Entity + Time                          |When was he active?               |
|Topic + Industry                       |Is there fraud in this sector?    |
|Topic + Jurisdiction                   |Where is this crime happening?    |
|Industry + Jurisdiction                |Which sectors are active here?    |
|Event + Time                           |When did this happen?             |
|Entity + Entity + Topic                |Are these two connected via fraud?|
|Entity + Industry + Jurisdiction + Time|Full intersection                 |

-----

## THE K-U QUADRANT

|Quadrant|Subject             |Location                      |You're Doing                      |
|--------|--------------------|------------------------------|----------------------------------|
|**K-K** |Known entity/topic  |Known jurisdiction/source/time|ENRICH both                       |
|**K-U** |Known entity/topic  |Unknown location/time         |ENRICH SUBJECT + DISCOVER LOCATION|
|**U-K** |Unknown entity/topic|Known location/time           |DISCOVER SUBJECT + ENRICH LOCATION|
|**U-U** |Unknown             |Unknown                       |DISCOVER both                     |

-----

## DIMENSION FILTERS (##)

|Dimension   |Filter            |Example            |
|------------|------------------|-------------------|
|Jurisdiction|`##jurisdiction:X`|`##jurisdiction:CY`|
|Source Type |`##source:X`      |`##source:registry`|
|Year        |`##YYYY`          |`##2020`           |
|Year Range  |`##YYYY-YYYY`     |`##2019-2023`      |
|Before      |`##before:YYYY`   |`##before:2020`    |
|After       |`##after:YYYY`    |`##after:2015`     |
|Filetype    |`##filetype:X`    |`##pdf`            |
|State       |`##state:X`       |`##unchecked`      |

-----

## GRID SYNTAX CONTROL

Same syntax queries the Grid. Target with `#` = internal.

### Core Syntax

|Syntax    |Meaning                |Example                               |
|----------|-----------------------|--------------------------------------|
|`@CLASS`  |Select by type         |`@SUBJECT`, `@SOURCE`, `@QUERY`       |
|`#name`   |Specific node          |`#john_smith`, `#acme_holdings`       |
|`!#name`  |Node + related (expand)|`!#query` = query + its sources       |
|`#name!`  |Node only (contract)   |`#source!` = just that source         |
|`##filter`|Dimension filter       |`##pdf`, `##jurisdiction:CY`, `##2020`|
|`=> #tag` |Tag the results        |`=> #OFFSHORE`, `=> #SUSPECT`         |

### The Pattern

```
OPERATOR :TARGETS ##filters => #tag
```

### Classes (@)

```
@SUBJECT     - All subject entities (people, companies)
@PERSON      - Person entities only
@COMPANY     - Company entities only
@SOURCE      - Sources in the investigation
@QUERY       - Queries that have run
@NARRATIVE   - Narrative items/questions
@LOCATION    - Location/jurisdiction nodes
```

### Examples

**Extract from query and related sources, tag results:**

```
ent? :!#query1 !#query2 => #EXTRACTED
```

**All Cyprus companies get tagged offshore:**

```
@COMPANY ##jurisdiction:CY => #OFFSHORE
```

**Search content of nodes linked to tag:**

```
"keyword" :!#tag3
```

**Search only that tag's content:**

```
"keyword" :#tag3!
```

**Persons from sources, but only unchecked:**

```
p? :!#query ##unchecked => #NEW_PERSONS
```

**Unchecked Panama sources get tagged for priority:**

```
@SOURCE ##jurisdiction:PA ##unchecked => #PRIORITY_CHECK
```

**High confidence entities get tagged confirmed:**

```
@SUBJECT ##confidence:>0.8 => #CONFIRMED
```

**Multiple jurisdiction filter, tag result:**

```
@COMPANY ##jurisdiction:BVI ##jurisdiction:Cayman ##jurisdiction:Panama => #OFFSHORE_WRAPPER
```

### Tag Becomes Variable

Once tagged, the tag works as a variable in chains:

```
# Step 1: Filter and tag
@COMPANY ##jurisdiction:CY => #CYPRUS_TARGETS

# Step 2: Use tag in automation chain
#CYPRUS_TARGETS => {X} => !registry_lookup({X})
```

The `=>` is consistent: "here's what you do with the result"

- **Grid:** result => tag it
- **Chain:** result => run action on it

-----

# PART 2: THE COMPARE & SIMILARITY OPERATOR `=?`

The `=?` operator is the most powerful in the system. It computes **multi-dimensional similarity** between nodes.

## BASIC FORM: IDENTITY COMPARISON

```
=? :#node_a #node_b [#node_c...]
```

Compares specific nodes across all dimensions and relationships.

### What It Compares

**Subject Dimensions:**

- Entity: Name variants, type, attributes (Core/Shell/Halo)
- Topic: Associated themes, tags
- Industry: Sector involvement
- Event: Connected events (IPO, bankruptcy, etc.)

**Location Dimensions:**

- Jurisdiction: Where each appears
- Source: Which sources mention each
- Time: Temporal overlap, activity periods

**Relationships:**

- Shared edges: Common connections
- Shared addresses: Same locations
- Shared officers: Overlapping people
- Shared companies: Corporate overlap

### Output Example

```
=? :#john_smith #john_j_smith

COMPARISON RESULT:
├── ENTITY
│   ├── Name similarity: 0.85 (FUSE signal)
│   ├── Type: Both @PERSON (match)
│   └── DOB: Unknown vs 1965-03-12 (inconclusive)
│
├── LOCATION
│   ├── Jurisdictions: Both CY, PA (overlap)
│   ├── Sources: 3 shared sources
│   └── Time: 2018-2023 overlap
│
├── RELATIONSHIPS
│   ├── Shared companies: Acme Holdings, Beta Ltd
│   ├── Shared addresses: 123 Main St, Nicosia
│   └── Shared associates: Jane Doe
│
└── VERDICT: FUSE (high confidence same entity)
```

### Identity Verdicts

|Verdict       |Meaning                                        |
|--------------|-----------------------------------------------|
|`FUSE`        |High confidence same entity - merge recommended|
|`REPEL`       |Confirmed different entities - keep separate   |
|`BINARY_STAR` |Related but distinct (father/son, shell/parent)|
|`INCONCLUSIVE`|Need more data - wedge queries suggested       |

-----

## EXTENDED FORM: SIMILARITY SEARCH

The real power of `=?` is **finding similar nodes you haven't explicitly connected yet**.

### Similarity to Target

```
=? :#target :@CLASS [##filters] [=> #tag]
```

Finds nodes of a class most similar to target.

**Examples:**

```
# Find companies most similar to this one
=? :#acme_holdings :@COMPANY

# Find people similar to this person
=? :#john_smith :@PERSON

# Find entities similar to target, limited to Cyprus
=? :#suspicious_company :@SUBJECT ##jurisdiction:CY

# Find and tag the top 10 most similar
=? :#target :@COMPANY ##limit:10 => #SIMILAR_TO_TARGET
```

### Similarity Output

```
=? :#acme_holdings :@COMPANY ##limit:5

SIMILARITY RANKING:
┌──────┬─────────────────────┬───────────┬─────────────────────────────────┐
│ Rank │ Entity              │ Score     │ Why Similar                     │
├──────┼─────────────────────┼───────────┼─────────────────────────────────┤
│ 1    │ #beta_holdings      │ 0.92      │ Same officers, same address     │
│ 2    │ #gamma_ltd          │ 0.78      │ Same jurisdiction, same sector  │
│ 3    │ #delta_corp         │ 0.65      │ Shared officer, temporal overlap│
│ 4    │ #epsilon_sa         │ 0.54      │ Same formation agent            │
│ 5    │ #zeta_inc           │ 0.41      │ Same jurisdiction only          │
└──────┴─────────────────────┴───────────┴─────────────────────────────────┘
```

### Nearest Neighbors (Even Unlinked)

The critical insight: **similarity doesn't require an existing edge**.

```
=? :#target :@COMPANY ##unlinked
```

This finds companies similar to target **that have no direct relationship yet**. These are:

- Potential connections not yet discovered
- Entities that *should* be investigated together
- Structural similarities without explicit links

**Use Case:** "What other companies look like this shell company, even if we haven't found a connection?"

-----

## SIMILARITY DIMENSIONS

### The Similarity Vector

Every node has a position in multi-dimensional space:

```python
@dataclass
class SimilarityVector:
    """Multi-dimensional position for similarity computation."""

    # Subject dimensions
    entity_type: EntityType           # @PERSON, @COMPANY, @ASSET
    name_embedding: np.array          # Semantic embedding of name
    attributes: Dict[str, Any]        # Core/Shell/Halo attributes
    topics: Set[str]                  # Associated tags/themes
    industries: Set[str]              # Sector involvement
    events: Set[str]                  # Connected events

    # Location dimensions
    jurisdictions: Set[str]           # Where entity appears
    sources: Set[str]                 # Which sources mention
    time_range: Tuple[date, date]     # Active period

    # Relationship dimensions
    connected_entities: Set[str]      # Direct connections
    shared_addresses: Set[str]        # Location overlap
    shared_officers: Set[str]         # People overlap (for companies)
    shared_companies: Set[str]        # Company overlap (for people)

    # Structural dimensions
    formation_agent: Optional[str]    # Who formed the company
    registered_agent: Optional[str]   # Current agent
    corporate_structure: str          # Holding/subsidiary/standalone
```

### Similarity Computation

```python
class SimilarityEngine:
    """Compute multi-dimensional similarity between nodes."""

    # Dimension weights (configurable)
    WEIGHTS = {
        "entity_type": 0.1,
        "name": 0.15,
        "attributes": 0.15,
        "topics": 0.1,
        "jurisdictions": 0.15,
        "sources": 0.05,
        "time_overlap": 0.1,
        "shared_connections": 0.2,  # Highest weight - structural similarity
    }

    def compute_similarity(self, a: SimilarityVector, b: SimilarityVector) -> SimilarityScore:
        """
        Compute weighted similarity across all dimensions.
        Returns score 0.0 - 1.0 plus breakdown.
        """
        scores = {}

        # Entity type match
        scores["entity_type"] = 1.0 if a.entity_type == b.entity_type else 0.0

        # Name similarity (cosine on embeddings)
        scores["name"] = cosine_similarity(a.name_embedding, b.name_embedding)

        # Attribute overlap (Jaccard on filled slots)
        scores["attributes"] = self.jaccard(
            set(a.attributes.keys()),
            set(b.attributes.keys())
        )

        # Topic overlap
        scores["topics"] = self.jaccard(a.topics, b.topics)

        # Jurisdiction overlap
        scores["jurisdictions"] = self.jaccard(a.jurisdictions, b.jurisdictions)

        # Source overlap
        scores["sources"] = self.jaccard(a.sources, b.sources)

        # Temporal overlap
        scores["time_overlap"] = self.temporal_overlap(a.time_range, b.time_range)

        # Shared connections (structural similarity)
        all_shared = (
            len(a.connected_entities & b.connected_entities) +
            len(a.shared_addresses & b.shared_addresses) +
            len(a.shared_officers & b.shared_officers) +
            len(a.shared_companies & b.shared_companies)
        )
        max_possible = max(
            len(a.connected_entities) + len(b.connected_entities),
            1
        )
        scores["shared_connections"] = all_shared / max_possible

        # Weighted total
        total = sum(
            scores[dim] * self.WEIGHTS[dim]
            for dim in scores
        )

        return SimilarityScore(
            total=total,
            breakdown=scores,
            explanation=self.explain_similarity(scores)
        )

    def jaccard(self, a: Set, b: Set) -> float:
        """Jaccard similarity for sets."""
        if not a and not b:
            return 0.0
        return len(a & b) / len(a | b)

    def temporal_overlap(self, a: Tuple[date, date], b: Tuple[date, date]) -> float:
        """How much do time ranges overlap?"""
        if not a or not b:
            return 0.0
        overlap_start = max(a[0], b[0])
        overlap_end = min(a[1], b[1])
        if overlap_start > overlap_end:
            return 0.0
        overlap_days = (overlap_end - overlap_start).days
        total_days = max((a[1] - a[0]).days, (b[1] - b[0]).days, 1)
        return overlap_days / total_days

    def explain_similarity(self, scores: Dict[str, float]) -> str:
        """Generate human-readable explanation."""
        high_dims = [dim for dim, score in scores.items() if score > 0.7]
        if not high_dims:
            return "Low similarity across all dimensions"
        return f"High similarity in: {', '.join(high_dims)}"
```

-----

## SIMILARITY QUERY PATTERNS

### Pattern 1: Find Similar Entities

```
# Most similar companies to target
=? :#target_company :@COMPANY

# Most similar people
=? :#target_person :@PERSON

# Most similar assets
=? :#target_asset :@ASSET
```

**Use:** "What else looks like this?"

### Pattern 2: Find Structurally Similar (Unlinked)

```
# Companies that look like target but aren't connected
=? :#shell_company :@COMPANY ##unlinked

# People with similar profiles, no known connection
=? :#suspect :@PERSON ##unlinked
```

**Use:** "What should we investigate that we haven't connected yet?"

### Pattern 3: Find Similar Within Constraint

```
# Similar companies in same jurisdiction
=? :#target :@COMPANY ##jurisdiction:CY

# Similar people in same time period
=? :#target :@PERSON ##2018-2020

# Similar entities from same source
=? :#target :@SUBJECT ##source:offshore_leaks
```

**Use:** "What's similar within this scope?"

### Pattern 4: Cluster by Similarity

```
# Find natural clusters among suspects
=? :@SUBJECT ##suspect ##cluster

# Cluster all Cyprus companies by similarity
=? :@COMPANY ##jurisdiction:CY ##cluster
```

**Use:** "Group similar things together"

### Pattern 5: Find Bridge Entities

```
# Entities similar to BOTH targets (potential bridges)
=? :#cluster_a :#cluster_b :@SUBJECT ##bridge
```

**Use:** "What connects these two groups?"

### Pattern 6: Anomaly Detection

```
# Find entities that DON'T fit the pattern
=? :#typical_shell :@COMPANY ##anomaly

# What's different about this one?
=? :#outlier :@SUBJECT ##explain_difference
```

**Use:** "What doesn't belong?"

-----

## SIMILARITY-BASED AUTOMATION

### Auto-Expand Investigation

When a new entity is found, automatically find similar entities:

```
# New entity found → find similar → tag for review
ent? :!#source => #NEW => =? :{X} :@SUBJECT ##limit:5 => #REVIEW_SIMILAR
```

### Cluster-Based Enrichment

Enrich one entity, apply findings to similar:

```
# Enrich target, find similar, apply same enrichment
enrich? :#target => =? :#target :@COMPANY ##similarity:>0.8 => enrich?
```

### Similarity-Triggered Alerts

```python
class SimilarityWatcher:
    """Watch for new entities similar to targets of interest."""

    def __init__(self, state: InvestigationState):
        self.state = state
        self.watch_targets: List[str] = []
        self.similarity_threshold: float = 0.7

    def on_new_entity(self, entity: Entity):
        """Check if new entity is similar to any watch target."""
        for target_id in self.watch_targets:
            target = self.state.entities[target_id]
            score = self.compute_similarity(entity, target)

            if score.total > self.similarity_threshold:
                self.alert(
                    f"New entity {entity.name} is {score.total:.0%} similar to "
                    f"watched target {target.name}: {score.explanation}"
                )
```

-----

## IMPLEMENTATION

```python
class CompareOperator:
    """
    The =? operator: compare and similarity search.

    Forms:
    - =? :#a #b              Compare specific nodes
    - =? :#target :@CLASS    Find similar in class
    - =? :#target :@CLASS ##unlinked    Find similar but unconnected
    """

    def __init__(self, state: InvestigationState):
        self.state = state
        self.similarity_engine = SimilarityEngine()

    def execute(self, query: str) -> CompareResult:
        """Parse and execute compare/similarity query."""
        parsed = self.parse(query)

        if parsed.mode == "compare":
            # Direct comparison: =? :#a #b #c
            return self.compare_specific(parsed.targets)

        elif parsed.mode == "similarity":
            # Similarity search: =? :#target :@CLASS
            return self.similarity_search(
                target=parsed.target,
                search_class=parsed.search_class,
                filters=parsed.filters,
                limit=parsed.limit
            )

        elif parsed.mode == "cluster":
            # Cluster: =? :@CLASS ##cluster
            return self.cluster(
                search_class=parsed.search_class,
                filters=parsed.filters
            )

        elif parsed.mode == "bridge":
            # Bridge: =? :#a :#b :@CLASS ##bridge
            return self.find_bridges(
                targets=parsed.targets,
                search_class=parsed.search_class
            )

    def compare_specific(self, target_ids: List[str]) -> CompareResult:
        """Compare specific nodes for identity resolution."""
        nodes = [self.state.get_node(id) for id in target_ids]
        vectors = [self.to_vector(n) for n in nodes]

        # Pairwise comparison
        comparisons = []
        for i, a in enumerate(vectors):
            for j, b in enumerate(vectors[i+1:], i+1):
                score = self.similarity_engine.compute_similarity(a, b)
                verdict = self.determine_verdict(score, nodes[i], nodes[j])
                comparisons.append(PairComparison(
                    node_a=nodes[i],
                    node_b=nodes[j],
                    score=score,
                    verdict=verdict
                ))

        return CompareResult(
            mode="compare",
            comparisons=comparisons,
            overall_verdict=self.aggregate_verdict(comparisons)
        )

    def similarity_search(
        self,
        target: str,
        search_class: str,
        filters: List[str],
        limit: int = 10
    ) -> CompareResult:
        """Find entities most similar to target."""
        target_node = self.state.get_node(target)
        target_vector = self.to_vector(target_node)

        # Get candidate nodes
        candidates = self.state.get_nodes_by_class(search_class)

        # Apply filters
        for f in filters:
            candidates = self.apply_filter(candidates, f)

        # Handle ##unlinked filter specially
        if "##unlinked" in filters:
            linked = self.state.get_connected_nodes(target)
            candidates = [c for c in candidates if c.id not in linked and c.id != target]

        # Compute similarities
        scored = []
        for candidate in candidates:
            if candidate.id == target:
                continue
            candidate_vector = self.to_vector(candidate)
            score = self.similarity_engine.compute_similarity(target_vector, candidate_vector)
            scored.append((candidate, score))

        # Sort by score, take top N
        scored.sort(key=lambda x: x[1].total, reverse=True)
        top_n = scored[:limit]

        return CompareResult(
            mode="similarity",
            target=target_node,
            similar=[
                SimilarEntity(
                    entity=entity,
                    score=score,
                    is_linked=self.state.has_edge(target, entity.id)
                )
                for entity, score in top_n
            ]
        )

    def cluster(self, search_class: str, filters: List[str]) -> CompareResult:
        """Cluster entities by similarity."""
        candidates = self.state.get_nodes_by_class(search_class)
        for f in filters:
            candidates = self.apply_filter(candidates, f)

        # Build similarity matrix
        n = len(candidates)
        similarity_matrix = np.zeros((n, n))
        vectors = [self.to_vector(c) for c in candidates]

        for i in range(n):
            for j in range(i+1, n):
                score = self.similarity_engine.compute_similarity(vectors[i], vectors[j])
                similarity_matrix[i][j] = score.total
                similarity_matrix[j][i] = score.total

        # Cluster (simple agglomerative)
        clusters = self.agglomerative_cluster(candidates, similarity_matrix)

        return CompareResult(
            mode="cluster",
            clusters=clusters
        )

    def find_bridges(self, targets: List[str], search_class: str) -> CompareResult:
        """Find entities similar to multiple targets (potential bridges)."""
        target_nodes = [self.state.get_node(t) for t in targets]
        target_vectors = [self.to_vector(n) for n in target_nodes]

        candidates = self.state.get_nodes_by_class(search_class)

        # Score by minimum similarity to ALL targets
        # (must be similar to all to be a bridge)
        bridges = []
        for candidate in candidates:
            if candidate.id in targets:
                continue
            candidate_vector = self.to_vector(candidate)

            scores = [
                self.similarity_engine.compute_similarity(candidate_vector, tv)
                for tv in target_vectors
            ]

            min_score = min(s.total for s in scores)
            avg_score = sum(s.total for s in scores) / len(scores)

            if min_score > 0.3:  # Must be at least somewhat similar to all
                bridges.append(BridgeEntity(
                    entity=candidate,
                    min_similarity=min_score,
                    avg_similarity=avg_score,
                    target_scores={t: s for t, s in zip(targets, scores)}
                ))

        bridges.sort(key=lambda b: b.min_similarity, reverse=True)

        return CompareResult(
            mode="bridge",
            targets=target_nodes,
            bridges=bridges[:10]
        )

    def determine_verdict(
        self,
        score: SimilarityScore,
        a: Node,
        b: Node
    ) -> IdentityVerdict:
        """Determine FUSE/REPEL/BINARY_STAR/INCONCLUSIVE."""

        # Check for automatic REPEL (temporal impossibility, etc.)
        if self.check_repel_constraints(a, b):
            return IdentityVerdict.REPEL

        # Check for automatic FUSE (same identifier)
        if self.check_fuse_constraints(a, b):
            return IdentityVerdict.FUSE

        # Score-based determination
        if score.total > 0.85:
            # Check if BINARY_STAR (related but distinct)
            if self.appears_related_not_same(a, b, score):
                return IdentityVerdict.BINARY_STAR
            return IdentityVerdict.FUSE

        elif score.total < 0.3:
            return IdentityVerdict.REPEL

        else:
            return IdentityVerdict.INCONCLUSIVE

    def check_repel_constraints(self, a: Node, b: Node) -> bool:
        """Check for automatic REPEL signals."""
        # Different entity types
        if a.entity_type != b.entity_type:
            return True

        # Temporal impossibility (active in non-overlapping periods with death/dissolution)
        # ... implementation

        # Exclusive geography (two places at once)
        # ... implementation

        return False

    def check_fuse_constraints(self, a: Node, b: Node) -> bool:
        """Check for automatic FUSE signals."""
        # Same unique identifier (SSN, company reg number, etc.)
        if a.get_identifier() and a.get_identifier() == b.get_identifier():
            return True

        return False

    def appears_related_not_same(
        self,
        a: Node,
        b: Node,
        score: SimilarityScore
    ) -> bool:
        """Check if entities are related but distinct (father/son, shell/parent)."""
        # High shared connections but different names
        if score.breakdown["shared_connections"] > 0.8 and score.breakdown["name"] < 0.5:
            return True

        # Same address, different company types (holding + operating)
        # ... implementation

        return False
```

-----

## AGENT TRANSLATION FOR `=?`

|User Says                              |Agent Writes                                               |
|---------------------------------------|-----------------------------------------------------------|
|"Are these the same person?"           |`=? :#john_smith #john_j_smith`                            |
|"What companies are similar to this?"  |`=? :#acme :@COMPANY`                                      |
|"Find similar but unconnected entities"|`=? :#target :@SUBJECT ##unlinked`                         |
|"What's closest to this shell company?"|`=? :#shell :@COMPANY ##limit:10`                          |
|"Group these by similarity"            |`=? :@COMPANY ##jurisdiction:CY ##cluster`                 |
|"What connects these two groups?"      |`=? :#group_a :#group_b :@SUBJECT ##bridge`                |
|"What doesn't fit the pattern?"        |`=? :#typical :@COMPANY ##anomaly`                         |
|"Compare all suspects"                 |`=? :#suspect_1 #suspect_2 #suspect_3`                     |
|"Find people like him in Cyprus"       |`=? :#john_smith :@PERSON ##jurisdiction:CY`               |
|"What should we investigate next?"     |`=? :#key_entity :@SUBJECT ##unlinked ##limit:5 => #REVIEW`|

-----

# PART 3: NEXUS INTERSECTION INTELLIGENCE

NEXUS mode evaluates three states for every potential intersection:

## 1. Expected AND Found

*Confirms hypothesis*

```
#john_smith AND #acme_holdings  →  RESULT
```

They're connected. Expected, confirmed.

## 2. Expected AND NOT Found

*Suspicious absence*

```
#ceo AND #company_filings AND ##2020  →  NO RESULT
```

CEO should appear in filings. Why doesn't he?

## 3. Unexpected AND Found

*The Surprising AND - real intelligence*

```
#respected_banker AND #sanctioned_oligarch AND ##2019  →  RESULT
```

Shouldn't be connected. But they are. Flag it.

-----

## NEXUS DIMENSION MATRIX

NEXUS keeps all dimensions loaded to evaluate relevance:

```python
class NexusDimensions:
    """All dimensions NEXUS must consider."""

    SUBJECT = {
        "entity": ["@PERSON", "@COMPANY", "@ASSET"],
        "topic": ["#FRAUD", "#SANCTIONS", "#CORRUPTION", "#AML"],
        "industry": ["#FINTECH", "#REAL_ESTATE", "#OIL_GAS", "#CRYPTO", "#DEFENSE"],
        "event": ["#IPO", "#BANKRUPTCY", "#MERGER", "#INVESTIGATION", "#INDICTMENT"],
    }

    LOCATION = {
        "jurisdiction": ["##jurisdiction:*"],
        "source": ["##source:registry", "##source:court", "##source:news", "##source:leak"],
        "time": ["##YYYY", "##YYYY-YYYY"],
    }

    def generate_intersection_queries(self, known_entities: List[Entity]) -> List[Query]:
        """Generate all relevant intersection queries for NEXUS assessment."""
        queries = []

        for entity in known_entities:
            # Entity + Topic intersections
            for topic in self.SUBJECT["topic"]:
                queries.append(f"#{entity.name} AND {topic}")

            # Entity + Industry intersections
            for industry in self.SUBJECT["industry"]:
                queries.append(f"#{entity.name} AND {industry}")

            # Entity + Event intersections
            for event in self.SUBJECT["event"]:
                queries.append(f"#{entity.name} AND {event}")

            # Entity + Entity intersections (other entities)
            for other in known_entities:
                if other.id != entity.id:
                    queries.append(f"#{entity.name} AND #{other.name}")

        return queries

    def evaluate_intersection(
        self,
        query: str,
        result: bool,
        expected: bool
    ) -> IntersectionType:
        """Classify the intersection."""
        if result and expected:
            return IntersectionType.CONFIRMED
        elif not result and expected:
            return IntersectionType.SUSPICIOUS_ABSENCE
        elif result and not expected:
            return IntersectionType.SURPRISING_AND  # The gold
        else:
            return IntersectionType.EXPECTED_NEGATIVE
```

-----

## NEXUS + SIMILARITY: THE INTEGRATION

The `=?` operator powers NEXUS in two ways:

### 1. Expectation Model

Similarity tells NEXUS what connections to expect:

```python
class NexusExpectationModel:
    """Use similarity to predict expected connections."""

    def __init__(self, similarity_engine: SimilarityEngine):
        self.similarity_engine = similarity_engine

    def predict_connection(self, a: Node, b: Node) -> ExpectedConnection:
        """Should these nodes be connected?"""
        score = self.similarity_engine.compute_similarity(
            self.to_vector(a),
            self.to_vector(b)
        )

        # High structural similarity → expect connection
        if score.breakdown["shared_connections"] > 0.5:
            return ExpectedConnection(
                expected=True,
                confidence=score.breakdown["shared_connections"],
                reason="High structural similarity"
            )

        # Same jurisdiction + industry → might be connected
        if (score.breakdown["jurisdictions"] > 0.8 and
            score.breakdown["topics"] > 0.5):
            return ExpectedConnection(
                expected=True,
                confidence=0.4,
                reason="Same jurisdiction and industry"
            )

        # Very different → don't expect connection
        if score.total < 0.2:
            return ExpectedConnection(
                expected=False,
                confidence=0.8,
                reason="Low similarity across dimensions"
            )

        return ExpectedConnection(
            expected=None,  # Uncertain
            confidence=0.0,
            reason="Insufficient signal"
        )
```

### 2. Surprising AND Detection

When a connection is found, check if it violates expectations:

```python
class SurprisingANDDetector:
    """Detect connections that violate similarity-based expectations."""

    def __init__(self, expectation_model: NexusExpectationModel):
        self.expectation_model = expectation_model

    def evaluate_connection(
        self,
        a: Node,
        b: Node,
        connection_found: bool
    ) -> Optional[SurprisingAND]:
        """Is this connection surprising?"""
        expectation = self.expectation_model.predict_connection(a, b)

        if connection_found and expectation.expected == False:
            # CONNECTION WHERE NONE EXPECTED - SURPRISING AND
            return SurprisingAND(
                entity_a=a,
                entity_b=b,
                surprise_score=expectation.confidence,  # Higher = more surprising
                reason=f"Connection found despite: {expectation.reason}",
                implications=self.infer_implications(a, b)
            )

        if not connection_found and expectation.expected == True:
            # NO CONNECTION WHERE ONE EXPECTED - SUSPICIOUS ABSENCE
            return SuspiciousAbsence(
                entity_a=a,
                entity_b=b,
                surprise_score=expectation.confidence,
                reason=f"No connection despite: {expectation.reason}",
                suggested_queries=self.suggest_investigation(a, b)
            )

        return None  # Not surprising

    def infer_implications(self, a: Node, b: Node) -> List[str]:
        """What does this surprising connection imply?"""
        implications = []

        # Different jurisdictions connected → cross-border activity
        a_jurisdictions = a.get_jurisdictions()
        b_jurisdictions = b.get_jurisdictions()
        if a_jurisdictions and b_jurisdictions and not (a_jurisdictions & b_jurisdictions):
            implications.append(
                f"Cross-border connection: {a_jurisdictions} ↔ {b_jurisdictions}"
            )

        # Different industries connected → diversification or front
        if a.industry != b.industry:
            implications.append(
                f"Cross-industry connection: {a.industry} ↔ {b.industry}"
            )

        # Reputable + questionable connected → reputational risk
        if self.is_reputable(a) and self.is_questionable(b):
            implications.append(
                f"Reputational risk: {a.name} connected to questionable {b.name}"
            )

        return implications
```

-----

# PART 4: THE ALGEBRA OF INVESTIGATION

## Foundational Theory

Before implementation, understand the mathematics. The system is not a passive map—it is an active computer. The formula that makes it compute:

```
Query Group () = Narrative Tag # = Automation Variable {X}
```

When a user groups terms `(A OR B)` and names them, they are not just saving a search. They are defining a **Type Class** for the automation engine. They are saying:

> "Anything caught by this net shall be known as X, and X shall be processed according to the laws of this Tag."

-----

## THE TRINITY OF DEFINITION (The Axiom)

**From Text to Logic.**

To automate, we must transmute "Strings" into "Variables." The Narrative Tag is the Alchemist.

|Layer           |Name             |Example                                                               |
|----------------|-----------------|----------------------------------------------------------------------|
|**The Net**     |Query Group      |`( "LLC" OR "Ltd" OR "Inc" OR "GmbH" )`                               |
|**The Tag**     |Narrative Class  |`#LEGAL_WRAPPER`                                                      |
|**The Variable**|Automation Handle|Any text hit by "The Net" becomes node `{X}` of type `[LEGAL_WRAPPER]`|

**The Automation Consequence:**

The system does not need to know what "GmbH" means. It only needs to know:

```
IF result is #LEGAL_WRAPPER → THEN run !registry_lookup
```

-----

## INTENT-BASED INHERITANCE (The Biology of X)

**"The Tag dictates the Future of the Result."**

The Narrative Tag tells the system what kind of thing X is, which determines which Slots (needs) are auto-generated.

|Scenario|Query     |Tag       |Inherited Slots                                |
|--------|----------|----------|-----------------------------------------------|
|A       |"John Doe"|`#SUSPECT`|`[Criminal_Record]`, `[Aliases]`, `[Sanctions]`|
|B       |"John Doe"|`#WITNESS`|`[Phone]`, `[Email]`, `[Location]`             |

**The Insight:** The same entity gets different future automation paths based solely on the Narrative Tag used to find it.

```python
class NarrativeTag:
    """The Tag dictates inheritance."""

    SLOT_INHERITANCE = {
        "#SUSPECT": ["criminal_record", "aliases", "sanctions", "associates"],
        "#WITNESS": ["phone", "email", "location", "employer"],
        "#LEGAL_WRAPPER": ["registry", "officers", "shareholders", "filings"],
        "#OFFSHORE_JURISDICTION": ["registry_url", "formation_agents", "nominee_services"],
        "#ASSET": ["ownership", "valuation", "encumbrances", "history"],
    }

    @classmethod
    def get_slots_for_tag(cls, tag: str) -> List[str]:
        """What slots does this tag generate?"""
        return cls.SLOT_INHERITANCE.get(tag, [])

    @classmethod
    def apply_inheritance(cls, entity: Entity, tag: str):
        """Apply tag-based slot inheritance to entity."""
        slots = cls.get_slots_for_tag(tag)
        for slot in slots:
            if slot not in entity.shell:
                entity.shell[slot] = Attribute(
                    key=slot,
                    value=None,  # Empty slot - needs filling
                    source_id=None,
                    confidence=0.0,
                    verified=False,
                    found_at=None
                )
```

-----

## THE CHAIN REACTION (Result → X → Query)

**"Whatever results becomes X."**

A dynamic feedback loop. The system executes without human intervention.

**Chain Definition:**

```
[Subject] + [#OFFSHORE_JURISDICTION] => {X} => [#REGISTRY_SEARCH]
```

**Execution Flow:**

1. **Subject:** Acme Holdings
1. **Group (Tag):** `#OFFSHORE_JURISDICTION` = `(BVI OR Cayman OR Panama)`
1. **Search:** `"Acme Holdings" AND (BVI OR Cayman OR Panama)`
1. **Result:** Hit found on "Panama"
1. **Variable {X}:** "Panama" becomes `{X}`
1. **Injection:** Next link is `[#REGISTRY_SEARCH]`
- System looks up definition for Registry Search
- Injects `{X}` (Panama) into logic
- **Computed Command:** `site:registro-publico.gob.pa "Acme Holdings"`

**The Power:** User never typed "Panama Registry." They typed a Narrative Chain. The system used Result `{X}` to define Destination.

```python
@dataclass
class ChainLink:
    """A link in an automation chain."""
    input_tag: str              # What tag triggers this link
    output_tag: str             # What tag to apply to results
    action: str                 # What action to run
    injection_template: str     # How to inject {X}

class AutomationChain:
    """Executes chain reactions."""

    def __init__(self, links: List[ChainLink]):
        self.links = links

    async def execute(self, initial_subject: str, initial_tag: str) -> List[Entity]:
        """Run the chain reaction."""
        current_results = [initial_subject]
        current_tag = initial_tag
        all_entities = []

        for link in self.links:
            if link.input_tag != current_tag:
                continue

            next_results = []
            for x in current_results:
                # Inject {X} into template
                command = link.injection_template.replace("{X}", x)

                # Execute
                results = await self.execute_command(command)

                # Apply output tag inheritance
                for result in results:
                    entity = self.create_entity(result)
                    NarrativeTag.apply_inheritance(entity, link.output_tag)
                    all_entities.append(entity)
                    next_results.append(result)

            current_results = next_results
            current_tag = link.output_tag

        return all_entities
```

-----

## THE GHOST CHAIN (Pre-emptive Logic)

**"Programming with Empty Containers."**

Build complex Automation Chains using only Narrative Tags, before any data exists. This is **Abstract Investigation**.

**Construction:**

```
[{#COMPANY}] → [Find: {#OFFICERS}] → [Check: {#OFFICERS} + "Fraud"]
```

**State:** Ghost Variables. Instructions but no mass.

**Trigger:** Drag a real entity (e.g., "Acme Ltd") into `[{#COMPANY}]` slot.

**Ignition:** Ghost chain solidifies. `{#COMPANY}` becomes "Acme Ltd". Search for `{#OFFICERS}` fires. Results populate next variable. Chain reacts down the line.

**Value:** "Investigative Recipes" (Macros) that are totally reusable because they rely on Tags (Variables), not specific data.

-----

## THE CONDITIONAL ROUTER (Tag as Switch)

**"If X came from Group A, go Left."**

When a Group contains diverse logic `(A OR B)`, the resulting Variable X remembers which part caught it. This allows conditional automation.

**The Group:** `#ASSET = ( "Real Estate" OR "Vessel" OR "Crypto" )`

**The Logic Chain:**

1. Find `{#ASSET}` for "John Smith"
1. Result = `{X}`

**The Router:**

```
IF {X} matched "Real Estate" → Run !land_registry_lookup({X})
IF {X} matched "Vessel"      → Run !marine_traffic_track({X})
IF {X} matched "Crypto"      → Run !blockchain_explorer({X})
```

**The Mechanism:** Tag `#ASSET` is parent class; search terms are subclasses. Automation Engine reads subclass of result to choose correct tool.

```python
@dataclass
class TaggedResult:
    """A result that remembers which subclass caught it."""
    value: str
    parent_tag: str           # #ASSET
    matched_term: str         # "Real Estate" | "Vessel" | "Crypto"

class ConditionalRouter:
    """Routes results based on which subclass matched."""

    ROUTES = {
        ("#ASSET", "Real Estate"): "!land_registry_lookup",
        ("#ASSET", "Vessel"): "!marine_traffic_track",
        ("#ASSET", "Crypto"): "!blockchain_explorer",
        ("#LEGAL_WRAPPER", "LLC"): "!us_state_registry",
        ("#LEGAL_WRAPPER", "Ltd"): "!uk_companies_house",
        ("#LEGAL_WRAPPER", "GmbH"): "!german_handelsregister",
    }

    @classmethod
    def route(cls, result: TaggedResult) -> str:
        """Determine which action to run."""
        key = (result.parent_tag, result.matched_term)
        return cls.ROUTES.get(key, "!generic_lookup")
```

-----

## THE UNIFIED FIELD THEORY OF LOGIC

**AND = COMPARE. The operator is the Tool; the Intent is the Job.**

We stop treating "Comparison" as a separate module. It is Set Theory applied to Identity.

|Logic Gate|The Math            |INTERNAL (Knowns)                                                     |EXTERNAL (Unknowns)                                                   |
|----------|--------------------|----------------------------------------------------------------------|----------------------------------------------------------------------|
|**AND**   |Intersection (A ∩ B)|**COMPARE**: Do Known A and Known B overlap? (Verifying the Link)     |**SPECULATE**: Does A intersect with hypothetical B? (The Wedge Query)|
|**NOT**   |Exclusion (A \ B)   |**CONTRAST**: What does Known A have that B lacks? (Finding the Delta)|**DISCRIMINATE**: Find matches for A that are not B. (Filtering Noise)|
|**OR**    |Union (A ∪ B)       |**GROUP**: Treat Known A and B as single cluster. (Fusion)            |**EXPAND**: Find unknowns that look like A or B. (Netfishing)         |

### The Speculated Alignment (The Probe)

- **Speculation:** "I bet these two clusters are linked."
- **Logic:** AND
- **Query:** `"Cluster A" AND "Cluster B"`
- **Result:**
  - 0 Results → Speculation Failed (No intersection)
  - 1+ Results → Speculation becomes Fact. The AND has materialized a Bridge Node.

### Coordinate Matching vs String Matching

**String Matching (Weak - Google):**

```
Node A: "Director"
Node B: "Director"
Result: Match. (Meaningless)
```

**Coordinate Matching (Strong - The System):**

```
We match Position in the Lattice, not text.

Subject Coordinate:   Role: Officer (Code 58)
Location Coordinate:  Jurisdiction: Cyprus (Code CY)
Temporal Coordinate:  Active: 2020

Comparison: Overlay the 3D shape of Node A onto Node B.
Result: If they snap together = Physical Collision in logic, not linguistic similarity.
```

### The Verdict

The machine does not know "Compare" or "Contrast." It only knows:

- **Alignment (AND):** Distance = 0
- **Repulsion (NOT):** Distance > 0

You are simply directing where to point the logic:

- **At the Table:** Knowns (Internal)
- **At the Sea:** Unknowns (External)

-----

# PART 5: RELATIONSHIP HIERARCHY

## The Four Levels

The investigation tracks state at four hierarchical levels:

```
NARRATIVE LEVEL (what questions to answer)
    │
    │ 1:many
    ▼
QUERY LEVEL (what searches to run)
    │
    │ 1:many
    ▼
SOURCE LEVEL (what sources to check)
    │
    │ 1:many
    ▼
ENTITY LEVEL (what we found)
```

### Level 1: Narrative (Investigation Questions)

```python
@dataclass
class NarrativeItem:
    """A question or goal from the investigation."""
    id: str
    question: str                      # "Find John Smith's offshore connections"
    intent: Intent                     # DISCOVER_SUBJECT, ENRICH_SUBJECT, etc.
    priority: Priority                 # HIGH, MEDIUM, LOW
    state: NarrativeState              # UNANSWERED, PARTIAL, ANSWERED, PARKED

    # Relationships
    queries: List[Query]               # Many queries per narrative item
    header_id: str                     # Links to document section

    # Tracking
    created_at: datetime
    last_activity: datetime
    answer_confidence: float           # 0.0 - 1.0

class NarrativeState(Enum):
    UNANSWERED = "unanswered"          # No queries run yet
    PARTIAL = "partial"                # Some queries run, incomplete
    ANSWERED = "answered"              # Sufficient to answer question
    PARKED = "parked"                  # Explicitly set aside
    BLOCKED = "blocked"                # Depends on unresolved disambiguation
```

### Level 2: Query (Searches Run)

```python
@dataclass
class Query:
    """A search query attached to a narrative item."""
    id: str
    macro: str                         # "John Smith" => !cyprus_registry
    narrative_id: str                  # Parent narrative item
    k_u_quadrant: KUQuadrant           # VERIFY, TRACE, EXTRACT, DISCOVER
    intent: Intent
    state: QueryState

    # Relationships
    sources: List[SourceResult]        # Many sources per query

    # Tracking
    created_at: datetime
    executed_at: Optional[datetime]
    execution_count: int               # How many times run
    last_result_count: int

class QueryState(Enum):
    PENDING = "pending"                # Not yet executed
    RUNNING = "running"                # Currently executing
    PARTIAL = "partial"                # Some sources checked
    EXHAUSTED = "exhausted"            # All known sources checked
    FAILED = "failed"                  # Execution error
```

### Level 3: Source (Sources Checked)

```python
@dataclass
class SourceResult:
    """A source checked for a query."""
    id: str
    source_id: str                     # From IO Matrix
    source_name: str                   # "companies.gov.cy"
    jurisdiction: str                  # "CY"
    query_id: str                      # Parent query
    state: SourceState

    # Results
    raw_results: int                   # How many results returned
    entities_extracted: int            # How many entities from this source

    # Tracking
    checked_at: datetime
    extraction_complete: bool

class SourceState(Enum):
    UNCHECKED = "unchecked"            # Not yet scraped
    CHECKING = "checking"              # Currently scraping
    CHECKED = "checked"                # Scraped, results available
    EMPTY = "empty"                    # Scraped, no results
    FAILED = "failed"                  # Scrape error
    BLOCKED = "blocked"                # Access denied/paywall
```

### Level 4: Entity (What We Found)

```python
@dataclass
class Entity:
    """An entity extracted from sources."""
    id: str
    name: str
    entity_type: EntityType            # PERSON, COMPANY, ADDRESS, etc.

    # Core/Shell/Halo organization
    core: Dict[str, Attribute]         # Always present: name, type
    shell: Dict[str, Attribute]        # Usually present: DOB, jurisdiction
    halo: Dict[str, Attribute]         # Sometimes present: associates, aliases

    # Disambiguation
    cluster_id: Optional[str]          # Which entity cluster (if disambiguated)
    collision_flags: List[str]         # Potential false friends

    # Provenance
    source_ids: List[str]              # Which sources produced this entity
    confidence: float                  # 0.0 - 1.0

    # Completeness tracking
    core_complete: bool
    shell_complete: bool
    halo_started: bool

@dataclass
class Attribute:
    """A single attribute with provenance."""
    key: str
    value: Any
    source_id: str
    confidence: float
    verified: bool
    found_at: datetime
```

-----

## Relationship Flow Example

```
NARRATIVE NOTE: "Find John Smith's offshore connections"
    │
    ├── QUERY: "John Smith" site:cyprus_registry
    │   ├── SOURCE: companies.gov.cy (checked, 3 entities)
    │   ├── SOURCE: opencorporates.cy (checked, 0 entities)
    │   └── SOURCE: offshore_leaks (unchecked)
    │
    ├── QUERY: "John Smith" site:bvi_registry
    │   └── SOURCE: bvifsc.vg (unchecked)
    │
    └── QUERY: "John Smith" + "shell company"
        └── (not yet run)
```

-----

# PART 6: GRID ASSESSMENT

The Grid assesses completeness by rotating through four cognitive modes:

```
NARRATIVE LEVEL
├── "What questions should we answer?"
├── Many queries attach to each question
└── Track: answered / partially answered / unanswered

QUERY LEVEL
├── "What searches have we run?"
├── Many sources to each query
└── Track: exhausted / partial / untried

SOURCE LEVEL
├── "What sources have we checked?"
├── Many entities extracted from each source
└── Track: scraped / indexed / extracted / empty

ENTITY LEVEL
├── "What do we know about each entity?"
├── Core/Shell/Halo completeness
└── Track: complete / partial / stub
```

## GridAssessor Class

```python
class GridAssessor:
    """
    Assesses investigation completeness from four perspectives.
    Each perspective reveals different gaps and actions.
    """

    def __init__(self, state: InvestigationState):
        self.state = state

    def full_assessment(self) -> GridAssessment:
        """Run all four assessment modes plus cross-pollination."""
        return GridAssessment(
            narrative=self.narrative_mode(),
            subject=self.subject_mode(),
            location=self.location_mode(),
            nexus=self.nexus_mode(),
            cross_pollinated=self.cross_pollinate()
        )

    # ─────────────────────────────────────────────────────────────
    # MODE 1: NARRATIVE-CENTRIC
    # "What story are we building? What gaps prevent coherence?"
    # ─────────────────────────────────────────────────────────────

    def narrative_mode(self) -> NarrativeAssessment:
        """
        Assess from narrative perspective.
        Questions: Which investigation questions are answered/unanswered?
        """
        assessment = NarrativeAssessment()

        for item in self.state.narrative_items:
            if item.state == NarrativeState.UNANSWERED:
                assessment.unanswered.append(item)
                assessment.gaps.append(Gap(
                    type="NARRATIVE_UNANSWERED",
                    target=item.id,
                    description=f"Question not yet investigated: {item.question}",
                    priority=item.priority,
                    suggested_action=f"Run initial queries for: {item.question}"
                ))
            elif item.state == NarrativeState.PARTIAL:
                assessment.partial.append(item)
                run_queries = len([q for q in item.queries if q.state != QueryState.PENDING])
                total_queries = len(item.queries)
                assessment.gaps.append(Gap(
                    type="NARRATIVE_PARTIAL",
                    target=item.id,
                    description=f"Question partially answered: {run_queries}/{total_queries} queries run",
                    priority=Priority.MEDIUM,
                    suggested_action=f"Run remaining {total_queries - run_queries} queries"
                ))
            else:
                assessment.answered.append(item)

        return assessment

    # ─────────────────────────────────────────────────────────────
    # MODE 2: SUBJECT-CENTRIC
    # "What entities do we have? What slots are empty?"
    # ─────────────────────────────────────────────────────────────

    def subject_mode(self) -> SubjectAssessment:
        """
        Assess from entity perspective.
        Questions: Which entities are complete/incomplete? What enrichment needed?
        """
        assessment = SubjectAssessment()

        for entity in self.state.entities.values():
            # Check Core completeness
            if not entity.core_complete:
                assessment.incomplete_core.append(entity)
                assessment.gaps.append(Gap(
                    type="ENTITY_CORE_INCOMPLETE",
                    target=entity.id,
                    description=f"Entity {entity.name} missing core attributes",
                    priority=Priority.HIGH,
                    suggested_action=f"Enrich core for {entity.name}"
                ))

            # Check Shell completeness
            elif not entity.shell_complete:
                assessment.incomplete_shell.append(entity)
                routes = self.get_enrichment_routes(entity)
                assessment.gaps.append(Gap(
                    type="ENTITY_SHELL_INCOMPLETE",
                    target=entity.id,
                    description=f"Entity {entity.name} has Core but no Shell",
                    priority=Priority.MEDIUM,
                    suggested_action=f"Enrichment routes: {', '.join(routes)}"
                ))

            # Check for disambiguation needs
            if entity.collision_flags:
                assessment.needs_disambiguation.append(entity)
                assessment.gaps.append(Gap(
                    type="ENTITY_COLLISION",
                    target=entity.id,
                    description=f"Entity {entity.name} may be confused with others",
                    priority=Priority.HIGH,
                    suggested_action="Run wedge queries for disambiguation"
                ))

        return assessment

    # ─────────────────────────────────────────────────────────────
    # MODE 3: LOCATION-CENTRIC
    # "What terrain have we defined? What sources unchecked?"
    # ─────────────────────────────────────────────────────────────

    def location_mode(self) -> LocationAssessment:
        """
        Assess from source/location perspective.
        Questions: What jurisdictions implied? What sources not yet checked?
        """
        assessment = LocationAssessment()

        by_jurisdiction = defaultdict(list)
        for source in self.state.sources.values():
            by_jurisdiction[source.jurisdiction].append(source)

        for jurisdiction, sources in by_jurisdiction.items():
            checked = [s for s in sources if s.state == SourceState.CHECKED]
            unchecked = [s for s in sources if s.state == SourceState.UNCHECKED]

            if unchecked:
                assessment.unchecked_sources.extend(unchecked)
                assessment.gaps.append(Gap(
                    type="LOCATION_UNCHECKED",
                    target=jurisdiction,
                    description=f"{jurisdiction}: {len(checked)}/{len(sources)} sources checked",
                    priority=Priority.MEDIUM,
                    suggested_action=f"Check {len(unchecked)} remaining sources in {jurisdiction}"
                ))

        implied = self.get_implied_jurisdictions()
        for jurisdiction in implied:
            if jurisdiction not in by_jurisdiction:
                assessment.gaps.append(Gap(
                    type="LOCATION_IMPLIED",
                    target=jurisdiction,
                    description=f"Findings imply jurisdiction {jurisdiction} but no sources checked",
                    priority=Priority.HIGH,
                    suggested_action=f"Expand investigation to {jurisdiction}"
                ))

        return assessment

    # ─────────────────────────────────────────────────────────────
    # MODE 4: NEXUS-CENTRIC
    # "What connections exist? What's suspiciously unconnected?"
    # ─────────────────────────────────────────────────────────────

    def nexus_mode(self) -> NexusAssessment:
        """
        Assess from connection/relationship perspective.
        Questions: What connections confirmed/unconfirmed? What's suspiciously missing?
        """
        assessment = NexusAssessment()

        for edge in self.state.graph.edges:
            if edge.confirmed:
                assessment.confirmed_connections.append(edge)
            else:
                assessment.unconfirmed_connections.append(edge)
                assessment.gaps.append(Gap(
                    type="NEXUS_UNCONFIRMED",
                    target=(edge.entity_a, edge.entity_b),
                    description=f"Connection {edge.entity_a} → {edge.entity_b} unconfirmed",
                    priority=Priority.MEDIUM,
                    suggested_action=f"Verify connection with: {edge.evidence}"
                ))

        expected = self.get_expected_connections()
        for (entity_a, entity_b, reason) in expected:
            if not self.state.graph.has_edge(entity_a, entity_b):
                assessment.gaps.append(Gap(
                    type="NEXUS_EXPECTED_NOT_FOUND",
                    target=(entity_a, entity_b),
                    description=f"Expected connection {entity_a} → {entity_b} not found",
                    priority=Priority.HIGH,
                    suggested_action=f"Investigate: {reason}"
                ))

        return assessment

    # ─────────────────────────────────────────────────────────────
    # CROSS-POLLINATION
    # Each mode reveals actions for other modes
    # ─────────────────────────────────────────────────────────────

    def cross_pollinate(self) -> List[CrossPollinatedAction]:
        """Insights from one mode that reveal actions in another."""
        actions = []

        # Subject → Location: Entity implies jurisdiction to check
        for entity in self.state.entities.values():
            if "jurisdiction" in entity.shell:
                jurisdiction = entity.shell["jurisdiction"]["value"]
                unchecked = self.get_unchecked_sources_for_jurisdiction(jurisdiction)
                if unchecked:
                    actions.append(CrossPollinatedAction(
                        from_mode="SUBJECT",
                        to_mode="LOCATION",
                        insight=f"Entity implies jurisdiction {jurisdiction}",
                        action=f"Check {len(unchecked)} unchecked sources in {jurisdiction}",
                        priority=Priority.HIGH
                    ))

        # Location → Subject: Source checked but entities not extracted
        for source in self.state.sources.values():
            if source.state == SourceState.CHECKED:
                entity_count = len(self.state.source_to_entities.get(source.id, []))
                if source.raw_results > 0 and entity_count == 0:
                    actions.append(CrossPollinatedAction(
                        from_mode="LOCATION",
                        to_mode="SUBJECT",
                        insight=f"Source {source.source_name} has results but no extracted entities",
                        action=f"Run entity extraction on {source.source_name}",
                        priority=Priority.MEDIUM
                    ))

        # Nexus → Narrative: Connection found that answers question
        for item in self.state.narrative_items:
            if item.state == NarrativeState.PARTIAL:
                relevant_edges = self.get_edges_relevant_to(item)
                if relevant_edges:
                    actions.append(CrossPollinatedAction(
                        from_mode="NEXUS",
                        to_mode="NARRATIVE",
                        insight=f"Connection found that may answer: {item.question}",
                        action=f"Update narrative with {len(relevant_edges)} confirmed connections",
                        priority=Priority.HIGH
                    ))

        return actions
```

-----

# PART 7: CROSS-LEVEL QUERYING

## Query → Narrative Progress Tracking

Track which queries actually contribute to answering which narrative questions.

```python
class QueryNarrativeTracker:
    """
    Query nodes against Narrative nodes to track progress.
    Not just "query ran" but "query contributed to answer".
    """

    def __init__(self, state: InvestigationState):
        self.state = state
        self.contribution_matrix: Dict[str, Dict[str, ContributionStatus]] = {}

    def assess_contribution(self, query: Query, narrative: NarrativeItem) -> ContributionStatus:
        """Did this query actually help answer this narrative question?"""
        if query.state == QueryState.PENDING:
            return ContributionStatus.NOT_RUN

        if query.state == QueryState.FAILED:
            return ContributionStatus.FAILED

        entities_found = self.get_entities_from_query(query)

        if not entities_found:
            return ContributionStatus.RAN_NO_RESULTS

        relevant = self.entities_relevant_to_narrative(entities_found, narrative)

        if not relevant:
            return ContributionStatus.RAN_IRRELEVANT

        if self.entities_answer_question(relevant, narrative):
            return ContributionStatus.CONTRIBUTED
        else:
            return ContributionStatus.RAN_PARTIAL

    def get_narrative_progress(self, narrative: NarrativeItem) -> NarrativeProgress:
        """For a narrative question, what's the real progress?"""
        queries = self.state.narrative_to_queries.get(narrative.id, [])

        progress = NarrativeProgress(
            narrative_id=narrative.id,
            total_queries=len(queries),
            not_run=0,
            ran_no_results=0,
            ran_irrelevant=0,
            ran_partial=0,
            contributed=0,
            failed=0
        )

        for query_id in queries:
            query = self.state.queries[query_id]
            status = self.assess_contribution(query, narrative)

            if status == ContributionStatus.NOT_RUN:
                progress.not_run += 1
            elif status == ContributionStatus.RAN_NO_RESULTS:
                progress.ran_no_results += 1
            elif status == ContributionStatus.RAN_IRRELEVANT:
                progress.ran_irrelevant += 1
            elif status == ContributionStatus.RAN_PARTIAL:
                progress.ran_partial += 1
            elif status == ContributionStatus.CONTRIBUTED:
                progress.contributed += 1
            elif status == ContributionStatus.FAILED:
                progress.failed += 1

        progress.effective_progress = progress.contributed / max(1, progress.total_queries)
        progress.coverage = (progress.contributed + progress.ran_partial) / max(1, progress.total_queries)

        return progress

class ContributionStatus(Enum):
    NOT_RUN = "not_run"
    FAILED = "failed"
    RAN_NO_RESULTS = "ran_no_results"
    RAN_IRRELEVANT = "ran_irrelevant"
    RAN_PARTIAL = "ran_partial"
    CONTRIBUTED = "contributed"
```

## Source → Query Overlap Detection

Find where multiple queries hit the same sources.

```python
class SourceQueryOverlapDetector:
    """
    Source nodes against Query nodes to find overlaps.
    Multiple queries hitting same source = pattern worth investigating.
    """

    def __init__(self, state: InvestigationState):
        self.state = state
        self.source_to_queries: Dict[str, List[str]] = self.build_index()

    def find_hot_spots(self, min_queries: int = 2) -> List[HotSpot]:
        """
        Sources hit by multiple queries = hot spots.
        - Convergence: different angles arriving at same evidence (GOOD)
        - Redundancy: same ground covered multiple times (WASTE)
        - Central node: this source is key to investigation (IMPORTANT)
        """
        hot_spots = []

        for source_id, query_ids in self.source_to_queries.items():
            if len(query_ids) >= min_queries:
                source = self.state.sources[source_id]
                queries = [self.state.queries[qid] for qid in query_ids]
                overlap_type = self.classify_overlap(source, queries)

                hot_spots.append(HotSpot(
                    source=source,
                    queries=queries,
                    query_count=len(queries),
                    overlap_type=overlap_type,
                    significance=self.calculate_significance(source, queries, overlap_type)
                ))

        return sorted(hot_spots, key=lambda h: h.significance, reverse=True)

    def classify_overlap(self, source: SourceResult, queries: List[Query]) -> OverlapType:
        """Classify why multiple queries hit this source."""
        narratives = set()
        for query in queries:
            narratives.add(query.narrative_id)

        if len(narratives) == 1:
            return OverlapType.REFINEMENT

        entities = self.state.source_to_entities.get(source.id, [])
        if entities:
            return OverlapType.CONVERGENCE

        if source.state == SourceState.EMPTY:
            return OverlapType.DEAD_END

        return OverlapType.REDUNDANCY

class OverlapType(Enum):
    CONVERGENCE = "convergence"
    REFINEMENT = "refinement"
    REDUNDANCY = "redundancy"
    DEAD_END = "dead_end"
```

-----

# PART 8: AGENT ARCHITECTURE

## Agent Definitions

```python
from anthropic_agents import Agent, Tool, Task, Session

# ─────────────────────────────────────────────────────────────
# ORCHESTRATOR AGENT (Opus 4.5)
# ─────────────────────────────────────────────────────────────

orchestrator_agent = Agent(
    name="sastre_orchestrator",
    model="claude-opus-4-5-20251101",
    system_prompt="""You are the SASTRE investigation orchestrator.

Your job is to coordinate an autonomous investigation loop:

1. ASSESS: Use the Grid to assess current state from four perspectives
   - NARRATIVE: What questions answered/unanswered?
   - SUBJECT: What entities complete/incomplete?
   - LOCATION: What sources checked/unchecked?
   - NEXUS: What connections confirmed/unconfirmed?

2. PRIORITIZE: Compile priority actions from assessment

3. DELEGATE: Assign actions to appropriate subagents
   - IO actions → io_executor
   - Disambiguation → disambiguator
   - Similarity search → similarity_engine
   - Writing → writer
   - Gap analysis → grid_assessor

4. UPDATE: Update state with results

5. CHECK SUFFICIENCY: Can we answer the question?
   - YES → Delegate final report to writer
   - NO → Loop back to step 1

You have access to the full investigation state.
You see the hierarchy: Narrative → Query → Source → Entity.
You track what's known vs unknown at each level.

SYNTAX: You speak the unified query language.
- =? for comparison and similarity
- ent?, p?, c? for extraction
- enrich?, sanctions?, registry? for enrichment
- ! prefix = expand scope, ! suffix = contract scope

NEVER duplicate existing infrastructure. Call existing tools.""",

    tools=[
        Tool(name="assess_grid", handler=grid_assessment_handler),
        Tool(name="delegate_task", handler=delegate_task_handler),
        Tool(name="update_state", handler=update_state_handler),
        Tool(name="check_sufficiency", handler=check_sufficiency_handler),
        Tool(name="execute_query", handler=execute_query_handler),  # Unified syntax
    ],

    subagents=["io_executor", "disambiguator", "similarity_engine", "writer", "grid_assessor"]
)

# ─────────────────────────────────────────────────────────────
# SIMILARITY ENGINE AGENT (Opus 4.5)
# ─────────────────────────────────────────────────────────────

similarity_agent = Agent(
    name="similarity_engine",
    model="claude-opus-4-5-20251101",
    system_prompt="""You are the Similarity Engine. You execute =? operations.

You handle:
- Identity comparison: =? :#node_a #node_b
- Similarity search: =? :#target :@CLASS
- Unlinked similarity: =? :#target :@CLASS ##unlinked
- Clustering: =? :@CLASS ##cluster
- Bridge finding: =? :#a :#b :@CLASS ##bridge

You compute multi-dimensional similarity across:
- Subject dimensions: entity type, name, attributes, topics, industries, events
- Location dimensions: jurisdictions, sources, time ranges
- Relationship dimensions: shared connections, addresses, officers, companies

You return:
- For identity: FUSE / REPEL / BINARY_STAR / INCONCLUSIVE verdicts
- For similarity: Ranked list with scores and explanations
- For clusters: Grouped entities with cohesion scores
- For bridges: Entities similar to multiple targets

You power NEXUS expectation models - predicting which connections should exist.""",

    tools=[
        Tool(name="compare_specific", handler=compare_specific_handler),
        Tool(name="similarity_search", handler=similarity_search_handler),
        Tool(name="find_bridges", handler=find_bridges_handler),
        Tool(name="cluster_entities", handler=cluster_entities_handler),
        Tool(name="compute_expectations", handler=compute_expectations_handler),
    ]
)

# ─────────────────────────────────────────────────────────────
# IO EXECUTOR AGENT (Opus 4.5)
# ─────────────────────────────────────────────────────────────

io_executor_agent = Agent(
    name="io_executor",
    model="claude-opus-4-5-20251101",
    system_prompt="""You are the IO Executor. You run investigations using existing infrastructure.

You receive tasks like:
- "Run query X against sources Y, Z"
- "Enrich entity X using routes Y, Z"
- "Check sources X in jurisdiction Y"

You use the IO Matrix (5,620 rules, 3,087 sources, 130 jurisdictions).
You auto-expand variations (Free ORs).
You extract entities from results using Jasper.

For each query:
1. Expand entity variations
2. Select appropriate sources
3. Execute via IO Matrix
4. Extract entities from results
5. Detect potential collisions (same name from multiple sources)
6. Return structured results with collision flags

IMPORTANT: You detect collisions but do NOT resolve them.
Disambiguation is a separate agent's job.""",

    tools=[
        Tool(name="execute_macro", handler=execute_macro_handler),
        Tool(name="expand_variations", handler=expand_variations_handler),
        Tool(name="extract_entities", handler=extract_entities_handler),
        Tool(name="check_source", handler=check_source_handler),
    ]
)

# ─────────────────────────────────────────────────────────────
# DISAMBIGUATOR AGENT (Opus 4.5)
# ─────────────────────────────────────────────────────────────

disambiguator_agent = Agent(
    name="disambiguator",
    model="claude-opus-4-5-20251101",
    system_prompt="""You are the Disambiguator. You resolve entity collisions.

When the same name appears in multiple sources, you determine:
- FUSE: Same entity, merge attributes
- REPEL: Different entities, keep separate
- BINARY_STAR: Related but distinct (father/son, shell/parent)

Your process:
1. PASSIVE checks (automatic):
   - Temporal impossibility → AUTO_REPEL
   - Identifier collision (same SSN, reg number) → AUTO_FUSE
   - Exclusive geography (Budapest AND Dublin same day) → AUTO_REPEL

2. USE SIMILARITY ENGINE:
   - Delegate to similarity_engine for =? comparison
   - Use similarity scores to inform decision

3. ACTIVE checks (wedge queries):
   - Generate discriminating queries that will SPLIT or CONFIRM
   - "John Smith" + "lawyer" vs "John Smith" + "plumber"
   - Delegate execution to io_executor

4. RESOLUTION:
   - Apply FUSE/REPEL/BINARY_STAR
   - Update entity clusters
   - Return resolution status

NEVER skip disambiguation. Entity collisions corrupt the entire investigation.""",

    tools=[
        Tool(name="check_passive_constraints", handler=passive_constraints_handler),
        Tool(name="generate_wedge_queries", handler=wedge_queries_handler),
        Tool(name="apply_resolution", handler=apply_resolution_handler),
        Tool(name="request_similarity", handler=request_similarity_handler),
    ]
)

# ─────────────────────────────────────────────────────────────
# WRITER AGENT (Sonnet 4)
# ─────────────────────────────────────────────────────────────

writer_agent = Agent(
    name="writer",
    model="claude-sonnet-4-20250514",
    system_prompt="""You are the Writer. You produce Nardello-style investigative reports.

Your style:
- Core facts first, then supporting details
- Footnotes for provenance
- Surprising ANDs flagged explicitly
- Core/Shell/Halo organization for entity profiles
- Clear attribution for all claims

You write:
- Section content based on findings
- Entity profiles (Core → Shell → Halo)
- Footnotes with source provenance
- Surprising AND flags when findings contradict expectations

NEVER invent facts. Every claim must have provenance.""",

    tools=[
        Tool(name="write_section", handler=write_section_handler),
        Tool(name="write_entity_profile", handler=write_entity_profile_handler),
        Tool(name="add_footnote", handler=add_footnote_handler),
        Tool(name="flag_surprising_and", handler=flag_surprising_and_handler),
    ]
)

# ─────────────────────────────────────────────────────────────
# GRID ASSESSOR AGENT (Haiku 4.5)
# ─────────────────────────────────────────────────────────────

grid_assessor_agent = Agent(
    name="grid_assessor",
    model="claude-haiku-4-5-20251001",
    system_prompt="""You are the Grid Assessor. You analyze investigation state from four perspectives.

When asked to assess, you rotate through:
1. NARRATIVE-CENTRIC: What questions answered/unanswered?
2. SUBJECT-CENTRIC: What entities complete/incomplete?
3. LOCATION-CENTRIC: What sources checked/unchecked?
4. NEXUS-CENTRIC: What connections confirmed/unconfirmed?

You also run:
- Cross-pollination: Insights from one mode that reveal actions in another
- Similarity-based expectations: Use =? to predict expected connections
- Cross-level querying: Query→Narrative progress, Source→Query overlap

Output: Prioritized list of gaps and suggested actions.""",

    tools=[
        Tool(name="narrative_assessment", handler=narrative_assessment_handler),
        Tool(name="subject_assessment", handler=subject_assessment_handler),
        Tool(name="location_assessment", handler=location_assessment_handler),
        Tool(name="nexus_assessment", handler=nexus_assessment_handler),
        Tool(name="cross_pollinate", handler=cross_pollinate_handler),
    ]
)
```

-----

# PART 9: AGENT TRANSLATION LAYER

**The user speaks intent. The agent writes syntax. The machine executes.**

```
USER: "Find his offshore connections"
           ↓
AGENT: Translates to syntax
           ↓
SYNTAX: "John Smith" AND (#OFFSHORE_JURISDICTION) => ent? => enrich?
           ↓
EXECUTION: Chain fires, results return
           ↓
USER: Sees findings, not machinery
```

## Translation Patterns

|User Says                              |Agent Writes                                 |
|---------------------------------------|---------------------------------------------|
|"Find connections"                     |`ent? :!{subject}`                           |
|"Extract from those results"           |`ent? :!#query1 !#query2`                    |
|"Just this one"                        |`ent? :#target!`                             |
|"Who links to this"                    |`bl? :!{target}`                             |
|"Check sanctions"                      |`sanctions? :!{entity}`                      |
|"Dig deeper"                           |`enrich? :!{entity}`                         |
|"Are these the same?"                  |`=? :#{entity_a} #{entity_b}`                |
|"What do they have in common?"         |`=? :#{targets}`                             |
|"Find similar companies"               |`=? :#target :@COMPANY`                      |
|"What's similar but unconnected?"      |`=? :#target :@SUBJECT ##unlinked`           |
|"Group by similarity"                  |`=? :@COMPANY ##jurisdiction:CY ##cluster`   |
|"What connects these groups?"          |`=? :#group_a :#group_b :@SUBJECT ##bridge`  |
|"Is he connected to the fintech fraud?"|`#john_smith AND #FRAUD AND #FINTECH`        |
|"Find offshore companies"              |`ent? :!{subject} AND #OFFSHORE => registry?`|
|"Check all the directors"              |`p? :!#company => enrich?`                   |
|"Not the one in London"                |`#entity NOT "London"`                       |

## Translation Rules

```python
class IntentTranslator:
    """
    Agent's syntax knowledge - translates user intent to operations.
    """

    PATTERNS = {
        # Discovery
        r"who is (connected|linked|associated) to": "DISCOVER_CONNECTIONS",
        r"find (connections|links|relationships)": "DISCOVER_CONNECTIONS",
        r"extract entities": "EXTRACT_ENTITIES",

        # Verification
        r"is .* (linked|connected|associated) to": "VERIFY_CONNECTION",
        r"(confirm|verify|check) (the )?(link|connection)": "VERIFY_CONNECTION",

        # Compare / Identity
        r"are .* the same": "COMPARE_IDENTITY",
        r"same (person|company|entity)": "COMPARE_IDENTITY",
        r"what.* in common": "COMPARE_OVERLAP",
        r"compare": "COMPARE_OVERLAP",

        # Similarity
        r"(find|what).* similar": "SIMILARITY_SEARCH",
        r"closest to": "SIMILARITY_SEARCH",
        r"like this": "SIMILARITY_SEARCH",
        r"unconnected.* similar": "SIMILARITY_UNLINKED",
        r"group.* by similarity": "CLUSTER",
        r"what connects.* groups": "BRIDGE_SEARCH",

        # Enrichment
        r"find (out )?more about": "ENRICH_ENTITY",
        r"dig deeper": "ENRICH_ENTITY",

        # Exclusion
        r"but not": "DISCRIMINATE",
        r"exclude": "DISCRIMINATE",

        # Expansion
        r"check all": "EXPAND_SEARCH",

        # Scope
        r"just (this|that) one": "CONTRACT_SCOPE",
        r"and (related|connected)": "EXPAND_SCOPE",

        # Link Analysis
        r"who links to": "BACKLINKS",
        r"what does .* link to": "OUTLINKS",
    }

    SYNTAX_TEMPLATES = {
        "DISCOVER_CONNECTIONS": "ent? :!{subject} => #CONNECTIONS",
        "EXTRACT_ENTITIES": "ent? :!{targets}",
        "VERIFY_CONNECTION": "{subject_a} AND {subject_b} :!#SOURCES",
        "COMPARE_IDENTITY": "=? :#{entity_a} #{entity_b}",
        "COMPARE_OVERLAP": "=? :#{targets}",
        "SIMILARITY_SEARCH": "=? :#{target} :@{class}",
        "SIMILARITY_UNLINKED": "=? :#{target} :@{class} ##unlinked",
        "CLUSTER": "=? :@{class} {filters} ##cluster",
        "BRIDGE_SEARCH": "=? :#{target_a} #{target_b} :@{class} ##bridge",
        "ENRICH_ENTITY": "enrich? :!{entity}",
        "DISCRIMINATE": "{subject} NOT ({exclusion})",
        "EXPAND_SEARCH": "ent? :!{subject} AND ({group})",
        "CONTRACT_SCOPE": "{operator} :#{target}!",
        "EXPAND_SCOPE": "{operator} :!#{target}",
        "BACKLINKS": "bl? :!{target}",
        "OUTLINKS": "ol? :!{target}",
    }
```

-----

# PART 10: FILE STRUCTURE

```
BACKEND/modules/SASTRE/
├── __init__.py
│
├── core/
│   ├── __init__.py
│   ├── state.py                # InvestigationState, all dataclasses
│   ├── relationships.py        # Narrative/Query/Source/Entity hierarchy
│   ├── phases.py               # InvestigationPhase, transitions
│   └── sufficiency.py          # SufficiencyCheck
│
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py         # Main orchestrator agent
│   ├── io_executor.py          # IO Executor agent
│   ├── disambiguator.py        # Disambiguator agent
│   ├── similarity_engine.py    # Similarity Engine agent (NEW)
│   ├── writer.py               # Writer agent
│   └── grid_assessor.py        # Grid Assessor agent
│
├── syntax/
│   ├── __init__.py
│   ├── parser.py               # Unified syntax parser
│   ├── translator.py           # Intent → Syntax translator
│   └── operators.py            # Operator definitions
│
├── similarity/
│   ├── __init__.py
│   ├── engine.py               # SimilarityEngine class
│   ├── vectors.py              # SimilarityVector computation
│   ├── compare.py              # CompareOperator (=?) implementation
│   └── expectations.py         # NEXUS expectation model
│
├── grid/
│   ├── __init__.py
│   ├── assessor.py             # GridAssessor class
│   ├── narrative_mode.py       # Narrative-centric assessment
│   ├── subject_mode.py         # Subject-centric assessment
│   ├── location_mode.py        # Location-centric assessment
│   ├── nexus_mode.py           # Nexus-centric assessment
│   └── cross_pollinate.py      # Cross-pollination logic
│
├── disambiguation/
│   ├── __init__.py
│   ├── passive.py              # Passive disambiguation checks
│   ├── wedge.py                # Wedge query generation
│   ├── resolution.py           # Resolution logic
│   └── clusters.py             # Core/Shell/Halo management
│
├── narrative/
│   ├── __init__.py
│   ├── engine.py               # NarrativeEngine class
│   ├── relevance.py            # Relevance judgment
│   ├── surprising.py           # Surprising AND detection
│   └── tags.py                 # Tag inheritance
│
├── document/
│   ├── __init__.py
│   ├── interface.py            # Document class
│   ├── sections.py             # Section management
│   ├── streaming.py            # Streaming updates
│   └── export.py               # Export to markdown/docx
│
├── tools/
│   ├── __init__.py
│   ├── io_tools.py             # IO Executor tools
│   ├── disambig_tools.py       # Disambiguator tools
│   ├── similarity_tools.py     # Similarity Engine tools (NEW)
│   ├── writer_tools.py         # Writer tools
│   └── grid_tools.py           # Grid Assessor tools
│
├── bridge/
│   ├── __init__.py
│   ├── cymonides.py            # Cymonides integration
│   ├── io_matrix.py            # IO Matrix integration
│   ├── watchers.py             # Watcher bridge
│   └── linklater.py            # Linklater integration
│
├── cli.py                      # CLI entry point
├── mcp.py                      # MCP server
└── orchestrator.py             # Main SastreOrchestrator class
```

-----

# SUMMARY

## The Unified Syntax

One syntax for everything:

- **Target determines scope**: `domain.com` = web, `#node` = grid
- **`!` position determines expansion**: prefix = expand, suffix = contract
- **Same operators everywhere**: `ent?`, `bl?`, `enrich?`, `=?`
- **Agent as translator**: Speaks the language, doesn't know the machinery

## The Query Dimensions

- **Subject** (WHO/WHAT): Entity, Topic, Industry, Event
- **Location** (WHERE/WHEN): Jurisdiction, Source, Time
- **Intelligence lives at intersections**: Every AND creates meaningful overlap

## The `=?` Operator

Three modes:

1. **Identity comparison**: `=? :#a #b` → FUSE/REPEL/BINARY_STAR
1. **Similarity search**: `=? :#target :@CLASS` → Ranked similar entities
1. **Advanced patterns**: `##unlinked`, `##cluster`, `##bridge`, `##anomaly`

Powers:

- Find similar entities even without existing connections
- Cluster entities by multi-dimensional similarity
- Find bridge entities connecting separate groups
- Detect anomalies that don't fit patterns
- Build expectation models for NEXUS (what connections should exist)

## The Hierarchy

Narrative → Query → Source → Entity with full state tracking at each level

## The Grid

Four cognitive modes that assess completeness:

- NARRATIVE: Questions answered?
- SUBJECT: Entities complete?
- LOCATION: Sources checked?
- NEXUS: Connections confirmed?

Plus cross-pollination and similarity-based expectations.

## The Key Insight

**Similarity without edges is the frontier.** The `=?` operator finds structurally similar entities that have no direct relationship yet—these are the investigation leads that pure graph traversal would miss.
