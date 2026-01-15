# CYMONIDES Agent - Keeper of Indices

An intelligent indexing agent built with the Claude Agent SDK that manages graph data ingestion into the Cymonides system.

## Overview

CYMONIDES is an AI-powered agent that:
1. **C-1 Bridge Building** - Hooks up modules (eye-d, corporella, linklater, etc.) to project indices
2. **C-3 Dataset Indexing** - Indexes datasets to unified superindices with intelligent field mapping

## Installation

```bash
cd /data/SEARCH_ENGINEER/BACKEND/modules/cymonides
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY
```

## Quick Start

### Python API

```python
from modules.cymonides.cymonides_agent import CymonicesAgent, index_dataset_sync

# Option 1: Direct function
result = index_dataset_sync("/path/to/data.csv", source_name="my_dataset")

# Option 2: Agent instance
agent = CymonicesAgent(model="claude-sonnet-4-20250514")
result = await agent.run("Index /path/to/data.csv")
```

### CLI

```bash
python -m modules.cymonides.cymonides_agent /path/to/data.csv [source_name]
```

## Index Tiers

| Tier | Pattern | Purpose |
|------|---------|---------|
| **C-1** | `cymonides-1-{projectId}` | Per-project graphs with nodes/edges |
| **C-2** | `cymonides-2` | Text corpus (532K+ docs) |
| **C-3** | `{entity}_unified` | Consolidated multi-source indices |

### C-3 Unified Indices

| Index | Entity Type | Primary Field |
|-------|-------------|---------------|
| `domains_unified` | domain | domain |
| `persons_unified` | person | name |
| `companies_unified` | company | company_name |
| `emails_unified` | email | email |
| `phones_unified` | phone | phone |
| `geo_unified` | location | address |
| `credentials_unified` | credential | username |
| `political_contributions_unified` | political_contribution | transaction_id |
| `transactions_unified` | financial_transaction | transaction_id |

## Agent Tools (8 Total)

### C-3 Indexing Tools
- `cymonides_load_sample` - Load sample records for analysis
- `cymonides_get_indices` - Get available unified indices
- `cymonides_test_index` - Index test batch with mappings
- `cymonides_full_index` - Full indexing after approval
- `cymonides_status` - Check indexing status

### C-1 Bridge Building Tools
- `cymonides_analyze_module` - Analyze module output types
- `cymonides_generate_bridge` - Generate C-1 bridge code
- `cymonides_save_bridge` - Save bridge to file

## THE HOLY RULE (C-3)

When indexing to C-3, **preserve ABSOLUTELY EVERYTHING** from each dataset:
- All original fields stored in `source_records[].fields`
- Never overwrite, always append
- Track source for every field

```json
{
  "id": "abc123...",
  "entity_type": "political_contribution",
  "candidate": "JOHN SMITH",
  "amount": 5000,
  "source_records": [
    {
      "source": "fec_electioneering_2024",
      "fields": {
        "CANDIDATE_NAME": "JOHN SMITH",
        "CALCULATED_CANDIDATE_SHARE": "5000.00",
        "PAYEE_CITY": "WASHINGTON"
      }
    }
  ]
}
```

## Test Protocol (C-3)

Always follow this 4-phase protocol:
1. **Phase 1**: Index 100-1000 docs, examine results
2. **Phase 2**: Adjust field mappings if needed
3. **Phase 3**: Index 1k more, verify quality
4. **Phase 4**: Full indexing only if Phase 3 passes

## Architecture

```
cymonides_agent.py              # Main agent (CymonicesAgent class)
├── agent/
│   ├── subagents/
│   │   ├── c3_dataset_indexer.py   # C-3 tool implementations
│   │   └── c1_bridge_builder.py    # C-1 tool implementations
│   ├── memory/
│   │   └── status_tracker.py       # Persistent task tracking
│   └── config/
│       └── canonical_standards.py  # Index schemas, node classes
├── c1/                             # C-1 node indexer
├── indexer/                        # Low-level indexing
└── bridges/                        # Existing C-1 bridges
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `ELASTICSEARCH_HOST` | No | ES host (default: localhost) |
| `ELASTICSEARCH_PORT` | No | ES port (default: 9200) |
| `CYMONIDES_MODEL` | No | Model to use (default: claude-sonnet-4-20250514) |

## Example: Index FEC Data

```python
from modules.cymonides.cymonides_agent import CymonicesAgent
import asyncio

async def main():
    agent = CymonicesAgent()

    result = await agent.run("""
        Index this FEC electioneering dataset:
        /data/DATASETS/FTM/fec/2024/ElectioneeringComm_2024.csv

        Source name: fec_electioneering_2024
    """)

    print(result["output"])

asyncio.run(main())
```

The agent will:
1. Load a sample to examine fields
2. Identify entity type (political_contribution)
3. Create field mappings (CANDIDATE_NAME → candidate, etc.)
4. Run test batch
5. If successful, complete full indexing

## Example: Hook Up Module to C-1

```python
result = await agent.run("""
    Hook up the LINKLATER module to C-1:
    /data/SEARCH_ENGINEER/BACKEND/modules/linklater

    Project ID: my_investigation
""")
```

The agent will:
1. Analyze module output types
2. Map to canonical node classes (SUBJECT, LOCATION, etc.)
3. Generate c1_bridge.py code
4. Save to module directory

## SDK Implementation Details

The agent uses the official Claude Agent SDK patterns:

```python
from claude_agent_sdk import (
    tool,                    # @tool decorator
    create_sdk_mcp_server,   # MCP server for tools
    ClaudeAgentOptions,      # Agent configuration
    ClaudeSDKClient,         # Async client
)

@tool("tool_name", "description", {"param": str})
async def my_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    result = do_something(args["param"])
    return {"content": [{"type": "text", "text": json.dumps(result)}]}

TOOLS = [my_tool]
MCP_SERVER = create_sdk_mcp_server(name="name", version="1.0", tools=TOOLS)
```

## Files

| File | Description |
|------|-------------|
| `cymonides_agent.py` | Main agent class and tool definitions |
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment variable template |
| `AGENT_README.md` | This documentation |

## Verification

Agent verified with `agent-sdk-verifier-py`:
- **Grade**: A- (92/100)
- **SDK Implementation**: 100/100
- **All critical checks passed**

## License

Internal use - OSINT Platform Component
