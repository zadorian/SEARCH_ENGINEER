# SWITCHBOARD - Axis Interaction Management System

## Overview

The Switchboard is a sophisticated logic system that manages interactions between all axes of the Search-Engineer.02 architecture. It controls how different components limit and increase possibilities through combinatorial interactions.

## Core Components

### 1. **axis_orchestrator.py**

Central orchestration system that:

- Manages state of all axes (NARRATIVE, SUBJECT, OBJECT, LOCATION)
- Applies interaction rules based on active components
- Optimizes execution order
- Provides compatibility matrix

### 2. **combinatorial_analyzer.py**

Advanced analysis system that:

- Computes pairwise and higher-order interactions
- Calculates search space modifications
- Generates execution strategies
- Provides optimization recommendations

### 3. **interaction_rules.json**

Comprehensive ruleset defining:

- Axis interactions and effects
- Constraint rules and exclusions
- Performance optimizations
- Capability matrices

## Interaction Types

### Enhancement Effects

When axes work together to expand possibilities:

- **Person + Country** → Enables local sources, language variants
- **Document + Sources** → Prioritizes by credibility
- **Entity + Proximity** → Enables relationship extraction

### Limitation Effects

When axes constrain the search space:

- **Company + Jurisdiction** → Restricts to business registries
- **Historical Date** → Limits to archive sources
- **Future Date** → Restricts to prediction/planning sources

### Transformation Effects

When axes fundamentally change the search approach:

- **Historical Location** → Adjusts for boundary changes
- **Non-English Country** → Adds translation/transliteration
- **Topic + NOT** → Requires semantic understanding

### Conflict Resolution

When axes have conflicting requirements:

- Archive-only vs Real-time
- Exact match vs Fuzzy search
- Single source vs Consensus required

## Usage Examples

### Simple Query

```python
from SWITCHBOARD.axis_orchestrator import process_search_query

components = {
    "entities": [{"type": "person", "value": "John Smith"}],
    "location": {"country": "Japan"}
}

result = process_search_query("John Smith Japan", components)
# Result: Enhances with Japanese sources, name transliteration
```

### Complex Multi-Axis Query

```python
from SWITCHBOARD.combinatorial_analyzer import analyze_search_query

components = {
    "entities": [
        {"type": "person", "value": "Jane Doe"},
        {"type": "company", "value": "TechCorp"}
    ],
    "location": {
        "country": "Germany",
        "city": "Berlin",
        "address": "Alexanderplatz 1"
    },
    "temporal": {"date_range": "2020-2023"},
    "operators": ["proximity", "NOT"]
}

analysis = analyze_search_query(components)
# Returns: Staged execution plan with optimized order
```

## Interaction Matrix

```
        NARRATIVE   SUBJECT   OBJECT   LOCATION
NARRATIVE    self    enhance   enhance    neutral
SUBJECT    enhance     self    limit     enhance
OBJECT     require   complex    self      limit
LOCATION   prioritize enhance   limit      self
```

## Key Interaction Patterns

### 1. Geographic Enhancement

- **Country** → Enables regional sources
- **City/Region** → Adds local directories
- **Address** → Enables street-level precision

### 2. Entity-Location Synergy

- **Person + Country** → Name variations, local formats
- **Organisation + Address** → Business registries, licenses
- **Company + Jurisdiction** → Corporate filings, registrations

### 3. Temporal Modulation

- **Past + Location** → Historical boundaries
- **Present + Real-time** → Social media, news
- **Future + Planning** → Events, forecasts

### 4. Operator Cascades

- **Proximity** → Requires snippet extraction
- **NOT** → Requires semantic expansion
- **Wildcard** → Requires pattern matching

## Execution Strategies

### Parallel Execution

Used when interactions are strongly positive:

- Multiple independent entities
- Complementary location/time constraints
- High interaction strength (>0.7)

### Staged Execution

Used for complex queries:

1. Entity identification
2. Location resolution
3. Temporal filtering
4. Operator application
5. Result assembly

### Sequential Execution

Default for simple queries:

- Single axis dominant
- Low interaction complexity
- Limited resources

## Performance Optimization

### Search Space Modifiers

- **Enhancement**: 1.3-1.5x expansion
- **Limitation**: 0.5-0.7x reduction
- **Precision**: 0.7x space, higher relevance
- **Comprehensive**: 1.3x space, full coverage

### Resource Estimation

- Base time: 10 seconds
- Interaction factor: +10% per interaction
- Parallelization: Up to 5x speedup
- API calls: 5-50 depending on complexity

## Configuration

### Adding New Rules

Edit `interaction_rules.json`:

```json
{
  "axis_interactions": {
    "NEW_INTERACTION": {
      "effect": "enhance|limit|transform",
      "description": "What this does",
      "enables": ["capabilities"],
      "restricts_to": ["constraints"]
    }
  }
}
```

### Custom Analyzers

Extend `CombinatorialAnalyzer`:

```python
class CustomAnalyzer(CombinatorialAnalyzer):
    def _evaluate_custom_interaction(self, axes, components):
        # Custom logic here
        pass
```

## Integration Points

### With ROUTER

- Receives parsed query components
- Returns execution plan
- Provides optimization hints

### With NARRATIVE

- Document assembly respects source priorities
- Gap filling follows temporal sequences
- Entity extraction triggers subject axis

### With SUBJECT

- Entity types determine location constraints
- Variations adapt to geographic context
- Relationships enable proximity searches

### With OBJECT

- Operators modify execution strategy
- Filters apply based on axis states
- Ranking considers interaction strength

### With LOCATION

- Geographic context enables sources
- Temporal filters limit archives
- Domain relationships affect crawling

## Monitoring & Debugging

### Interaction Logs

```python
orchestrator.get_axis_compatibility_matrix()
# Shows current interaction states

analyzer.analyze_combination(components)
# Detailed interaction analysis
```

### Performance Metrics

- Interaction strength scores
- Search space modifications
- Execution time estimates
- API call predictions

## Best Practices

1. **Start Simple**: Begin with 2-3 axes, add more as needed
2. **Check Conflicts**: Review mutual exclusions before execution
3. **Stage Complex Queries**: Break down 4+ axis queries
4. **Monitor Resources**: Watch API limits with broad searches
5. **Cache Interactions**: Reuse analysis for similar queries

## Future Enhancements

- Machine learning for interaction strength prediction
- Dynamic rule generation from search patterns
- Real-time optimization based on result quality
- Automatic conflict resolution strategies
- Visual interaction graph interface
