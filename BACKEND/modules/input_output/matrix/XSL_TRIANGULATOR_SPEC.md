# XSL_Triangulator Specification

**Cross-Subject-Location Source Discovery**

---

## Purpose

Pure lookup utility that cross-references **Subject** (entity type), **Location** (jurisdiction), and available **Sources** to discover obtainable outputs.

**No AI. No decisions. Just data structure traversal.**

---

## Naming: XSL

- **X** = Cross/Intersection
- **S** = Subject axis (entity type, identifier)
- **L** = Location axis (jurisdiction, domain, source)

**XSL_Triangulator** finds the intersection of these three dimensions.

---

## Location

```
/data/INPUT_OUTPUT/matrix/xsl_triangulator.py
```

**Why INPUT_OUTPUT?**
- Only reads INPUT_OUTPUT matrix files
- Pure lookup utility with zero business logic
- Multiple agents use it (NEXUS, WIKIMAN, BIOGRAPHER)
- Conceptually part of "reading the matrix"

---

## Data Sources

XSL_Triangulator reads these static files:

```
INPUT_OUTPUT/matrix/
├── sources.json      # 2,521 sources, 70 jurisdictions
├── rules.json        # 1,147 Have→Get transformation rules
├── codes.json        # Field definitions
├── legend.json       # Entity type mappings
└── xsl_triangulator.py  # This utility
```

---

## API

### Core Method

```python
from INPUT_OUTPUT.matrix.xsl_triangulator import XSL_Triangulator

xsl = XSL_Triangulator()

result = xsl.triangulate(
    input_code: int,           # Subject: Entity identifier type (1=email, 13=company_name, etc.)
    jurisdiction: str,          # Location: Country code (UK, DE, CY, US, etc.)
    include_chains: bool = True # Include chain reaction possibilities
) -> TriangulationResult
```

### Result Structure

```python
@dataclass
class TriangulationResult:
    input_code: int                      # What we started with
    input_name: str                      # Human-readable name
    jurisdiction: str                    # Where we're looking
    outputs: List[OutputMapping]         # What we can get
    sources_queried: List[str]           # Which sources we checked
    chains_available: List[Dict]         # Chain possibilities

@dataclass
class OutputMapping:
    code: int                            # Output field code
    name: str                            # Human-readable name
    sources: List[str]                   # Sources that provide this
    nexus_edge: Optional[Dict]           # NEXUS relationship edge
    node_type: Optional[str]             # Entity type created
    creates: str                         # "attribute" or "entity"
```

### Helper Methods

```python
# High-level query
result = xsl.what_can_i_get(
    entity_type: str,      # "company", "person", "email", etc.
    identifier: str,       # The actual value
    jurisdiction: str      # Country code
) -> Dict[str, Any]

# Get specific code info
code_info = xsl.get_code_info(code=14)
# Returns: {"name": "company_reg_id", "type": "identifier"}

# Get NEXUS relationship edge
nexus_edge = xsl.get_nexus_edge(output_code=59)
# Returns: {"nexus_code": 600, "nexus_name": "officer_of", "direction": "person→company"}
```

---

## Examples

### Example 1: Email → Possible Outputs

```python
xsl = XSL_Triangulator()

# Cross-reference: email (Subject) + UK (Location)
result = xsl.triangulate(input_code=1, jurisdiction="UK")

# Returns:
# TriangulationResult(
#   input_code=1,
#   input_name="email",
#   jurisdiction="UK",
#   outputs=[
#     OutputMapping(
#       code=2,
#       name="phone",
#       sources=["DeHashed", "OSINT.industries"],
#       nexus_edge={"nexus_code": 608, "nexus_name": "has_phone"}
#     ),
#     OutputMapping(
#       code=187,
#       name="breach_exposure",
#       sources=["DeHashed", "Have I Been Pwned"],
#       nexus_edge={"nexus_code": 607, "nexus_name": "has_email"}
#     ),
#     OutputMapping(
#       code=188,
#       name="social_profiles",
#       sources=["RocketReach", "OSINT.industries"]
#     )
#   ],
#   sources_queried=["DeHashed", "OSINT.industries", "RocketReach"],
#   chains_available=[...]
# )
```

### Example 2: UK Company Registration Number → Officers

```python
# Cross-reference: company_reg_id (Subject) + UK (Location)
result = xsl.triangulate(input_code=14, jurisdiction="UK")

# Returns:
# TriangulationResult(
#   outputs=[
#     OutputMapping(
#       code=13,
#       name="company_name",
#       sources=["Companies House API"]
#     ),
#     OutputMapping(
#       code=59,
#       name="company_officer_name",
#       sources=["Companies House API"],
#       nexus_edge={
#         "nexus_code": 600,
#         "nexus_name": "officer_of",
#         "direction": "person→company"
#       }
#     ),
#     OutputMapping(
#       code=67,
#       name="company_beneficial_owner_name",
#       sources=["Companies House PSC API"],
#       nexus_edge={
#         "nexus_code": 601,
#         "nexus_name": "beneficial_owner_of"
#       }
#     )
#   ]
# )
```

### Example 3: Generic Person Name → Multiple Jurisdictions

```python
# No jurisdiction specified → returns global options
result = xsl.triangulate(input_code=7, jurisdiction="GLOBAL")

# Returns sources from multiple jurisdictions:
# - OpenCorporates (global)
# - OCCRP Aleph (75+ jurisdictions)
# - LinkedIn (global)
# - Facebook/Twitter (global)
```

---

## Usage by Agents

### BIOGRAPHER (Task Orchestrator)

```python
class BiographerAgent:
    def __init__(self):
        self.xsl = XSL_Triangulator()

    async def investigate(self, identifier: str) -> PersonProfile:
        # Get initial data
        profile = await self._gather_initial_data(identifier)

        # Query XSL_Triangulator for opportunities
        opportunities = self.xsl.what_can_i_get(
            entity_type="email",
            identifier=identifier,
            jurisdiction=self._detect_jurisdiction(profile)
        )

        # BIOGRAPHER makes decision: which slot to fill next?
        for category in ["relationships", "contact", "basic_info"]:
            for opp in opportunities["obtainable_data"][category]:
                # Decide and delegate
                ...
```

### WIKIMAN (Routing Advisor)

```python
class WikimanAgent:
    def __init__(self):
        self.xsl = XSL_Triangulator()

    def recommend_source(self, entity_type: str, jurisdiction: str, context: str):
        # Get all possibilities from XSL_Triangulator
        options = self.xsl.triangulate(...)

        # WIKIMAN makes decision based on context
        if context == "due_diligence":
            # Prefer official registries
            return self._filter_official_sources(options)
        elif context == "investigative":
            # Prefer comprehensive aggregators
            return self._filter_aggregators(options)
```

### NEXUS (Query Constructor)

```python
class NexusAgent:
    def __init__(self):
        self.xsl = XSL_Triangulator()
        self.query_lab = QueryLab()

    def assess_opportunities(self, gap: Gap):
        # Use XSL_Triangulator to get possibilities
        opportunities = self.xsl.triangulate(
            input_code=gap.input_code,
            jurisdiction=gap.jurisdiction
        )

        # NEXUS makes strategic decision: how to search?
        query = self.query_lab.construct(gap, opportunities)
        results = self.brute_search.execute(query)
        return results
```

---

## Not Responsibilities

XSL_Triangulator does **NOT**:
- ❌ Make decisions about which source to use
- ❌ Execute searches
- ❌ Prioritize outputs
- ❌ Handle ambiguity
- ❌ Construct queries
- ❌ Assess quality or confidence

Those are responsibilities of:
- **BIOGRAPHER**: Prioritizes which slot to fill
- **WIKIMAN**: Decides which source when ambiguous
- **NEXUS**: Constructs strategic queries, executes searches

---

## Implementation Status

**Current**: Located at `/data/NEXUS/io_triangulator.py`
**Should be**: `/data/INPUT_OUTPUT/matrix/xsl_triangulator.py`

**Migration needed**:
1. Move file from NEXUS to INPUT_OUTPUT
2. Rename class from `IOTriangulator` to `XSL_Triangulator`
3. Update all imports across codebase
4. Update documentation

---

## Testing

```python
# Test basic triangulation
xsl = XSL_Triangulator()
result = xsl.triangulate(input_code=1, jurisdiction="UK")
assert len(result.outputs) > 0
assert "email" in result.input_name

# Test NEXUS edge mapping
edge = xsl.get_nexus_edge(output_code=59)
assert edge["nexus_name"] == "officer_of"

# Test high-level query
result = xsl.what_can_i_get(
    entity_type="person",
    identifier="john@acme.com",
    jurisdiction="UK"
)
assert "contact" in result["obtainable_data"]
assert "relationships" in result["obtainable_data"]
```

---

## Summary

**XSL_Triangulator** = Pure lookup utility for Cross-Subject-Location source discovery

**Lives in**: INPUT_OUTPUT/matrix/
**Used by**: NEXUS, WIKIMAN, BIOGRAPHER, ALLDOM, SUBMARINE
**Purpose**: Answer "What can I get from X in jurisdiction Y?"
**Decisions**: ZERO (pure data structure traversal)

---

**Related Files**:
- `/data/AGENT_SDK_COMPLIANCE_AUDIT_UPDATED.md` - Architecture overview
- `/data/NEXUS_WIKIMAN_BIOGRAPHER_INTEGRATION.md` - Integration patterns
- `/data/INPUT_OUTPUT/README.md` - Matrix documentation
