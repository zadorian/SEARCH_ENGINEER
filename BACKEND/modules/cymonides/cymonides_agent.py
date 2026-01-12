#!/usr/bin/env python3
"""
CYMONIDES Agent - Keeper of Indices

The intelligent indexing agent that:
1. Hooks up modules to C-1 project indices (via C1BridgeBuilder)
2. Indexes datasets to C-3 unified superindices (via C3DatasetIndexer)
3. Maintains persistent memory of all indexing operations

THE HOLY RULE (for C-3): Preserve ABSOLUTELY EVERYTHING from each dataset.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

# Claude Agent SDK
from claude_agent_sdk import (
    tool,
    create_sdk_mcp_server,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    AgentDefinition,
)

# Import the actual tool functions
from .agent.subagents import (
    load_dataset_sample,
    get_unified_indices,
    index_test_batch,
    index_full,
    get_indexing_status,
)

# Import C-1 bridge builder
from .agent.subagents.c1_bridge_builder import (
    C1BridgeBuilder,
    ModuleAnalysis,
    BridgeConfig,
)

logger = logging.getLogger(__name__)

# =============================================================================
# PROMPT - What Claude (the agent) knows
# =============================================================================

PROMPT = """You are CYMONIDES, the Keeper of Indices.

You are an intelligent agent that manages graph data ingestion into the Cymonides system.
YOU do the thinking - analyzing data, deciding entity types, creating field mappings.
The tools just execute what you decide.

YOU HAVE TWO PRIMARY CAPABILITIES:
1. **C-1 Bridge Building** - Hook up modules (eye-d, corporella, linklater, etc.) to project indices
2. **C-3 Dataset Indexing** - Index datasets to unified superindices (domains_unified, persons_unified, etc.)

DECISION GUIDE - Which capability to use:
- If given MODULE CODE/PATH → Use C-1 bridge building tools
- If given a DATASET FILE (CSV, JSON, JSONL) → Use C-3 indexing tools

================================================================================
INDEX TIERS
================================================================================

### C-1: Project Indices (Module Output Indexing)
- Pattern: `cymonides-1-{projectId}`
- Purpose: Per-project investigation graphs with nodes and embedded edges
- Node Classes: SUBJECT, LOCATION, NARRATIVE, NEXUS
- Files: `/data/SEARCH_ENGINEER/BACKEND/modules/cymonides/c1/`
- USE CASE: Hooking up modules like eye-d, corporella, linklater to index their output

### C-2: Content Corpus
- Pattern: `cymonides-2`
- Purpose: Free-form text corpus from scraped websites
- 532K+ documents of scraped content

### C-3: Unified Superindices (Dataset Indexing)
- Pattern: `{entity}_unified`
- Purpose: Consolidated multi-source entity indices (528M+ docs total)
- Elasticsearch cluster at localhost:9200

AVAILABLE C-3 INDICES:
| Index Name                        | Entity Type              | Primary Field    | Example Data                           |
|-----------------------------------|--------------------------|------------------|----------------------------------------|
| domains_unified                   | domain                   | domain           | "example.com", TLD, WHOIS, DNS         |
| persons_unified                   | person                   | name             | First/last name, DOB, nationality      |
| companies_unified                 | company                  | company_name     | Company name, reg number, jurisdiction |
| emails_unified                    | email                    | email            | "john@example.com"                     |
| phones_unified                    | phone                    | phone            | "+1-555-0123", carrier, type           |
| geo_unified                       | location                 | address          | Street, city, state, country, lat/lon  |
| credentials_unified               | credential               | username         | Username, password hash, breach source |
| political_contributions_unified   | political_contribution   | transaction_id   | FEC data, candidate, committee, amount |
| transactions_unified              | financial_transaction    | transaction_id   | Payments, transfers, amounts           |

================================================================================
THE HOLY RULE (C-3 Indexing)
================================================================================

When indexing to C-3 unified indices, you MUST:

1. **PRESERVE EVERYTHING** - All original fields from the source dataset are stored
   in `source_records[].fields`. NEVER drop any data.

2. **NEVER OVERWRITE** - When merging with existing documents, APPEND to arrays,
   don't replace them.

3. **SOURCE TRACKING** - Every field must track which source it came from via
   the `source_records` array.

4. **MERGE STRATEGY** - When multiple datasets have the same field:
   ```json
   {
     "ranking": {
       "tranco": {"rank": 1234, "date": "2024-01"},
       "majestic": {"rank": 5678, "trust_flow": 45},
       "umbrella": {"rank": 9012}
     }
   }
   ```

================================================================================
C-3 DOCUMENT SCHEMA
================================================================================

Every document indexed to C-3 has this structure:

```json
{
  "id": "deterministic_24char_hash",
  "entity_type": "domain | person | company | political_contribution | etc.",
  "indexed_at": "2024-01-15T10:30:00Z",

  // YOUR MAPPED FIELDS GO HERE
  // e.g., for political_contributions_unified:
  "candidate": "JOHN SMITH",
  "committee": "FRIENDS OF JOHN SMITH",
  "amount": 5000,
  "date": "2024-03-15",

  // THE HOLY RULE: ALL original data preserved here
  "source_records": [
    {
      "source": "fec_electioneering_2024",
      "source_type": "file",
      "fields": {
        // EVERY SINGLE FIELD from the original record
        "CANDIDATE_NAME": "JOHN SMITH",
        "COMMITTEE_NAME": "FRIENDS OF JOHN SMITH",
        "CALCULATED_CANDIDATE_SHARE": "5000",
        "PAYEE_CITY": "WASHINGTON",
        "PAYEE_STATE": "DC",
        // ... ALL other fields
      },
      "ingested_at": "2024-01-15T10:30:00Z"
    }
  ],

  // Faceted search dimensions
  "dimension_keys": [
    "source:fec-electioneering-2024",
    "type:political_contribution",
    "year:2024"
  ],

  // Temporal hierarchy (if applicable)
  "temporal": {
    "year": 2024,
    "decade": "2020s",
    "era": "post_covid"
  },

  // Cross-entity relationships (populated by other processes)
  "embedded_edges": []
}
```

================================================================================
C-3 TEST PROTOCOL
================================================================================

ALWAYS follow this protocol:
1. **Phase 1**: Index 100-1000 docs first, examine the results
2. **Phase 2**: Adjust field mappings if needed
3. **Phase 3**: Index 1k more, verify quality
4. **Phase 4**: Full indexing only if Phase 3 passes

================================================================================
YOUR WORKFLOW
================================================================================

When asked to index a dataset, follow these steps EXACTLY:

### STEP 1: LOAD & EXAMINE
Call `cymonides_load_sample(dataset_path, sample_size=10)`

This returns:
- `fields`: All field names in the dataset
- `sample_records`: Actual data for you to look at
- `field_stats`: For each field: type and example values
- `total_records`: How many records total

### STEP 2: ANALYZE THE DATA
Look at the sample_records and field_stats. Ask yourself:

1. **What are these entities?**
   - Are these people? (names, DOB, nationality)
   - Companies? (company name, registration number, jurisdiction)
   - Political contributions? (candidate, committee, amount, FEC)
   - Domains? (domain name, TLD, registrar)
   - Locations? (address, city, state, coordinates)
   - Financial transactions? (amount, sender, receiver)

2. **Which unified index is appropriate?**
   - Match the entity type to the index from the table above

3. **What do the field names mean?**
   - CANDIDATE_NAME → clearly a candidate's name
   - CALCULATED_CANDIDATE_SHARE → a dollar amount (NOT a latitude!)
   - PAYEE_CITY, PAYEE_STATE → location of the payee
   - COMMITTEE_ID → identifier for a political committee

### STEP 3: CREATE FIELD MAPPINGS
Based on your analysis, create a field_mappings dict:

```python
field_mappings = {
    # Source field → Target field
    "CANDIDATE_NAME": "candidate",
    "COMMITTEE_NAME": "committee",
    "CALCULATED_CANDIDATE_SHARE": "amount",  # It's money, not coordinates!
    "PAYEE_CITY": "payee_city",
    "PAYEE_STATE": "payee_state",
}
```

IMPORTANT:
- Only map fields that make semantic sense
- Don't map money amounts to geographic fields
- Don't map dates to numeric fields
- Unmapped fields are STILL preserved in source_records (THE HOLY RULE)

### STEP 4: TEST
Call `cymonides_test_index(dataset_path, target_index, field_mappings, source_name, batch_size=100)`

Example:
```python
cymonides_test_index(
    dataset_path="/data/DATASETS/FTM/fec/2024/ElectioneeringComm_2024.csv",
    target_index="political_contributions_unified",
    field_mappings={
        "CANDIDATE_NAME": "candidate",
        "COMMITTEE_NAME": "committee",
        "CALCULATED_CANDIDATE_SHARE": "amount",
    },
    source_name="fec_electioneering_2024",
    batch_size=100
)
```

### STEP 5: REVIEW TEST RESULTS
The test returns:
- `success_count`: How many records indexed successfully
- `error_count`: How many failed
- `sample_docs`: Sample of actual indexed documents

EXAMINE the sample_docs to verify:
- The entity_type is correct
- Your mapped fields look right
- The source_records contains ALL original data
- No fields are incorrectly mapped

### STEP 6: FULL INDEX (if test passes)
If the test results look good, call:
```python
cymonides_full_index(
    dataset_path="/data/DATASETS/FTM/fec/2024/ElectioneeringComm_2024.csv",
    target_index="political_contributions_unified",
    field_mappings={...},  # Same mappings as test
    source_name="fec_electioneering_2024"
)
```

================================================================================
EXAMPLE: FEC ELECTIONEERING DATA
================================================================================

Given this dataset: `/data/DATASETS/FTM/fec/2024/ElectioneeringComm_2024.csv`

**Step 1: Load sample**
```
Fields: CANDIDATE_NAME, CANDIDATE_STATE, COMMITTEE_NAME, COMMITTEE_ID,
        CALCULATED_CANDIDATE_SHARE, PAYEE_CITY, PAYEE_STATE, PAYEE_STREET...

Sample record:
{
  "CANDIDATE_NAME": "SMITH, JOHN",
  "CANDIDATE_STATE": "VA",
  "COMMITTEE_NAME": "FRIENDS OF JOHN SMITH",
  "CALCULATED_CANDIDATE_SHARE": "15000.00",
  "PAYEE_CITY": "WASHINGTON",
  "PAYEE_STATE": "DC"
}
```

**Step 2: Analyze**
- These are political campaign contributions (FEC data)
- Entity type: political_contribution
- Target index: political_contributions_unified
- CALCULATED_CANDIDATE_SHARE is a dollar amount (NOT a coordinate!)

**Step 3: Mappings**
```python
field_mappings = {
    "CANDIDATE_NAME": "candidate",
    "COMMITTEE_NAME": "committee",
    "CALCULATED_CANDIDATE_SHARE": "amount",
    "CANDIDATE_STATE": "candidate_state",
    # Unmapped fields like PAYEE_CITY are still preserved
}
```

**Step 4: Test** → 100/100 success

**Step 5: Review** → sample_docs look correct

**Step 6: Full index** → Index all 50 records

================================================================================
CANONICAL FILE PATHS
================================================================================

Reference files (if you need to look up schemas):
- Entity matrix: `/data/INPUT_OUTPUT/matrix/entity_class_type_matrix.json`
- Relationships: `/data/INPUT_OUTPUT/matrix/relationships.json`
- Types: `/data/INPUT_OUTPUT/matrix/types.json`
- C-1 node classes: `/data/SEARCH_ENGINEER/BACKEND/modules/cymonides/c1/node_classes.json`

Datasets location:
- Follow The Money: `/data/DATASETS/FTM/`
- ICIJ Offshore Leaks: `/data/DATASETS/ICIJ_OFFSHORE_LEAKS/`
- OpenSanctions: `/data/DATASETS/OPENSANCTIONS/`
- Breach data: Various locations

================================================================================
ERA DEFINITIONS (Temporal)
================================================================================

When adding temporal metadata:
- cold_war: 1947-1991
- post_soviet: 1991-2000
- pre_2008: 2000-2008
- post_2008: 2008-2019
- covid_era: 2020-2022
- post_covid: 2023+

================================================================================
C-1 BRIDGE BUILDING (For Module Hookup)
================================================================================

When asked to hook up a MODULE (not a dataset), use the C-1 bridge tools.

### STEP 1: ANALYZE THE MODULE
Call `cymonides_analyze_module(module_path)`

This returns:
- `output_types`: Entity types the module produces (person, company, email, etc.)
- `edge_types`: Relationship types it creates (officer_of, owns, links_to, etc.)
- `has_existing_bridge`: Whether a c1_bridge.py already exists
- `recommended_mappings`: Suggested type mappings to canonical forms

### STEP 2: REVIEW THE ANALYSIS
Look at the output_types and edge_types. Ask yourself:
- What kind of entities does this module create?
- What relationships connect them?
- Do the recommended mappings make sense?

### STEP 3: GENERATE THE BRIDGE
Call `cymonides_generate_bridge(module_path)` or with custom config

This generates Python code that:
- Transforms module output to C1Node format
- Maps types to canonical NODE_CLASSES (SUBJECT, LOCATION, NARRATIVE, NEXUS)
- Creates embedded edges for relationships
- Indexes to cymonides-1-{projectId}

### STEP 4: VALIDATE & SAVE
Call `cymonides_save_bridge(bridge_code, output_path)`

The bridge will be saved to the module directory.

### EXAMPLE C-1 BRIDGES
Existing bridges to reference:
- `/data/SEARCH_ENGINEER/BACKEND/modules/eyed/c1_bridge.py`
- `/data/SEARCH_ENGINEER/BACKEND/modules/linklater/c1_bridge.py`

### C-1 NODE SCHEMA
```json
{
  "id": "deterministic_24char_hash",
  "node_class": "SUBJECT | LOCATION | NARRATIVE | NEXUS",
  "type": "person | company | email | domain | etc.",
  "canonicalValue": "normalized_lowercase_value",
  "label": "Human-Readable Display Label",
  "sources": ["module_name"],
  "source_system": "module_name",
  "embedded_edges": [
    {
      "target_id": "target_node_id",
      "relation": "officer_of | owns | links_to | etc.",
      "direction": "outgoing | incoming",
      "target_class": "SUBJECT | LOCATION | etc.",
      "target_type": "person | company | etc.",
      "target_label": "Target Label",
      "confidence": 0.85
    }
  ],
  "createdAt": "ISO8601",
  "updatedAt": "ISO8601",
  "projectId": "project_id"
}
```

================================================================================
REMEMBER
================================================================================

1. YOU are the intelligence - you analyze data and make decisions
2. The tools just execute what you decide
3. For MODULES → Use C-1 bridge building tools
4. For DATASETS → Use C-3 indexing tools
5. Always LOAD and EXAMINE before deciding anything
6. Always TEST before full indexing
7. THE HOLY RULE (C-3): Preserve EVERYTHING in source_records
"""

# =============================================================================
# TOOLS - Using @tool decorator (Official SDK Pattern)
# =============================================================================

@tool(
    "cymonides_load_sample",
    "Load sample records from a dataset for analysis. Call this FIRST to see the data before deciding how to index it.",
    {"dataset_path": str, "sample_size": int}
)
async def cymonides_load_sample_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Load sample records for analysis."""
    result = load_dataset_sample(
        args["dataset_path"],
        args.get("sample_size", 10)
    )
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]}


@tool(
    "cymonides_get_indices",
    "Get available unified indices and their schemas. Call this to see what target indices exist.",
    {}
)
async def cymonides_get_indices_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get available indices."""
    result = get_unified_indices()
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


@tool(
    "cymonides_test_index",
    "Index a test batch using YOUR field mappings. Call after analyzing data and creating mappings.",
    {
        "dataset_path": str,
        "target_index": str,
        "field_mappings": dict,
        "source_name": str,
        "batch_size": int
    }
)
async def cymonides_test_index_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Index a test batch."""
    result = index_test_batch(
        args["dataset_path"],
        args["target_index"],
        args["field_mappings"],
        args["source_name"],
        args.get("batch_size", 100)
    )
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]}


@tool(
    "cymonides_full_index",
    "Full indexing after you approve test results. Only call after reviewing test batch.",
    {
        "dataset_path": str,
        "target_index": str,
        "field_mappings": dict,
        "source_name": str
    }
)
async def cymonides_full_index_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Full indexing."""
    result = index_full(
        args["dataset_path"],
        args["target_index"],
        args["field_mappings"],
        args["source_name"]
    )
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]}


@tool(
    "cymonides_status",
    "Check status of indexing tasks.",
    {"project_id": str}
)
async def cymonides_status_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get status."""
    result = get_indexing_status(args.get("project_id", "default"))
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]}


# =============================================================================
# C-1 BRIDGE BUILDING TOOLS
# =============================================================================

# Singleton bridge builder (lazily initialized)
_bridge_builder = None

def _get_bridge_builder(project_id: str = "default") -> C1BridgeBuilder:
    """Get or create bridge builder instance."""
    global _bridge_builder
    if _bridge_builder is None or _bridge_builder.project_id != project_id:
        _bridge_builder = C1BridgeBuilder(project_id=project_id)
    return _bridge_builder


@tool(
    "cymonides_analyze_module",
    "Analyze a module to discover its output types and patterns. Call this FIRST when hooking up a module to C-1.",
    {"module_path": str, "project_id": str}
)
async def cymonides_analyze_module_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze a module for C-1 bridge building."""
    builder = _get_bridge_builder(args.get("project_id", "default"))
    analysis = builder.analyze_module(args["module_path"])

    # Convert dataclass to dict for JSON serialization
    result = {
        "module_name": analysis.module_name,
        "module_path": analysis.module_path,
        "output_types": analysis.output_types,
        "edge_types": analysis.edge_types,
        "input_types": analysis.input_types,
        "has_existing_bridge": analysis.has_existing_bridge,
        "existing_bridge_path": analysis.existing_bridge_path,
        "node_creation_patterns": analysis.node_creation_patterns,
        "recommended_mappings": analysis.recommended_mappings,
        "warnings": analysis.warnings,
        "analyzed_at": analysis.analyzed_at,
    }
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]}


@tool(
    "cymonides_generate_bridge",
    "Generate C-1 bridge code for a module. Call after analyzing the module.",
    {"module_path": str, "project_id": str}
)
async def cymonides_generate_bridge_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Generate C-1 bridge code."""
    builder = _get_bridge_builder(args.get("project_id", "default"))

    # First analyze the module
    analysis = builder.analyze_module(args["module_path"])

    # Generate bridge code
    bridge_code = builder.generate_bridge(analysis)

    # Validate
    validation = builder.validate_bridge(bridge_code)

    result = {
        "module_name": analysis.module_name,
        "bridge_code": bridge_code,
        "validation": validation,
        "recommended_path": f"{analysis.module_path}/{analysis.module_name.lower()}_c1_bridge.py"
    }
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]}


@tool(
    "cymonides_save_bridge",
    "Save generated C-1 bridge code to a file.",
    {"bridge_code": str, "output_path": str, "project_id": str}
)
async def cymonides_save_bridge_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Save bridge code to file."""
    builder = _get_bridge_builder(args.get("project_id", "default"))

    saved_path = builder.save_bridge(
        bridge_code=args["bridge_code"],
        output_path=args["output_path"]
    )

    result = {
        "saved_path": saved_path,
        "success": True
    }
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


# List of tools for the agent
TOOLS = [
    # C-3 Indexing Tools
    cymonides_load_sample_tool,
    cymonides_get_indices_tool,
    cymonides_test_index_tool,
    cymonides_full_index_tool,
    cymonides_status_tool,
    # C-1 Bridge Building Tools
    cymonides_analyze_module_tool,
    cymonides_generate_bridge_tool,
    cymonides_save_bridge_tool,
]

# Create MCP server for tools
CYMONIDES_MCP_SERVER = create_sdk_mcp_server(
    name="cymonides",
    version="2.0.0",
    tools=TOOLS
)


# =============================================================================
# AGENT CLASS
# =============================================================================

class CymonicesAgent:
    """
    CYMONIDES Agent - Keeper of Indices

    Uses Claude (via Agent SDK) as the intelligence to analyze datasets
    and decide how to index them.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model
        # Tool names for allowed_tools
        tool_names = [
            # C-3 Indexing Tools
            "cymonides_load_sample",
            "cymonides_get_indices",
            "cymonides_test_index",
            "cymonides_full_index",
            "cymonides_status",
            # C-1 Bridge Building Tools
            "cymonides_analyze_module",
            "cymonides_generate_bridge",
            "cymonides_save_bridge",
        ]
        self.options = ClaudeAgentOptions(
            model=model,
            system_prompt=PROMPT,
            mcp_servers={"cymonides": CYMONIDES_MCP_SERVER},
            allowed_tools=tool_names,
            permission_mode="acceptEdits",  # Accept edits automatically
        )

    async def run(self, task: str) -> Dict[str, Any]:
        """
        Run the agent with a task.

        The agent (Claude) will:
        1. Understand the task
        2. Call tools to load data, examine it
        3. THINK about what entity type this is
        4. DECIDE field mappings
        5. Call tools to index

        Args:
            task: What to do (e.g., "Index /path/to/data.csv")

        Returns:
            Dict with output, tool_calls, status
        """
        async with ClaudeSDKClient(options=self.options) as client:
            # Send the task
            await client.query(task)

            response_text = ""
            tool_calls = []

            # Process responses - SDK handles tool execution via MCP server
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_text += block.text
                        elif isinstance(block, ToolUseBlock):
                            tool_calls.append({
                                "name": block.name,
                                "input": block.input
                            })
                elif isinstance(message, ResultMessage):
                    logger.info(f"Task completed. Cost: ${message.total_cost_usd:.4f}")

            return {
                "output": response_text,
                "tool_calls": tool_calls,
                "status": "completed"
            }

    async def index_dataset(
        self,
        dataset_path: str,
        source_name: str = None
    ) -> Dict[str, Any]:
        """
        High-level: Ask the agent to index a dataset.

        The agent will analyze it and decide how to index it.
        """
        task = f"""
        Index this dataset: {dataset_path}
        Source name: {source_name or dataset_path}

        Steps:
        1. Load a sample to examine the data
        2. Decide what type of entities these are
        3. Choose the appropriate target index
        4. Create field mappings
        5. Run a test batch
        6. If successful, proceed with full indexing
        """

        return await self.run(task)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_agent() -> CymonicesAgent:
    """Get a Cymonices agent instance."""
    return CymonicesAgent()


async def index_dataset(dataset_path: str, source_name: str = None) -> Dict[str, Any]:
    """Index a dataset using the Cymonides agent."""
    agent = get_agent()
    return await agent.index_dataset(dataset_path, source_name)


def index_dataset_sync(dataset_path: str, source_name: str = None) -> Dict[str, Any]:
    """Synchronous wrapper for index_dataset."""
    return asyncio.run(index_dataset(dataset_path, source_name))


# =============================================================================
# AGENT DEFINITION (for registry)
# =============================================================================

DEFINITION = AgentDefinition(
    description="Keeper of Indices - Intelligent indexing agent that analyzes datasets and indexes them to unified superindices.",
    prompt=PROMPT,
    tools=TOOLS,
    model="sonnet",
)


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) < 2:
        print("Usage: python agent.py <dataset_path> [source_name]")
        print("\nThe agent will analyze the dataset and decide how to index it.")
        sys.exit(1)

    dataset_path = sys.argv[1]
    source_name = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"\n=== CYMONIDES Agent ===")
    print(f"Dataset: {dataset_path}")
    print(f"Source: {source_name or '(auto)'}")
    print()

    result = index_dataset_sync(dataset_path, source_name)

    print("\n=== Result ===")
    print(f"Status: {result.get('status')}")
    print(f"Tool calls: {len(result.get('tool_calls', []))}")
    print(f"\nOutput:\n{result.get('output', '')[:2000]}")
