# BIOGRAPHER Agent

**Person Profile Aggregator** - Agent SDK Implementation

BIOGRAPHER is a specialized aggregator agent that coordinates multiple OSINT specialists to build comprehensive person profiles. It demonstrates the Agent SDK best practice of **specialist immersion with delegation**.

---

## Architecture

```
BIOGRAPHER (Orchestrator)
├── System Prompt: Person profile aggregation workflow
├── Tools: NONE (delegation only)
├── Model: Claude Sonnet 4
└── Subagents:
    ├── EYE-D (OSINT Specialist)
    │   ├── Tools: 9 MCP tools (email, phone, username, LinkedIn, WHOIS, IP, people search)
    │   └── Model: Claude Sonnet 4
    ├── CORPORELLA (Corporate Intelligence Specialist)
    │   ├── Tools: 11 MCP tools (company search, officers, shareholders, filings)
    │   └── Model: Claude Sonnet 4
    └── SOCIALITE (Social Media Specialist) [Optional]
        ├── Tools: Social platform search tools
        └── Model: Claude Sonnet 4
```

---

## Key Features

✅ **Pure Delegation Architecture**: BIOGRAPHER has NO direct tool access
✅ **Specialist Immersion**: Each subagent has full access to its domain tools
✅ **Intelligent Disambiguation**: Resolves conflicts between multiple person matches
✅ **Structured Output**: Returns PersonProfile dataclass with confidence scores
✅ **Agent SDK Compliant**: Uses official Claude Agent SDK patterns
✅ **Continuous Conversations**: Uses ClaudeSDKClient for multi-turn investigations

---

## Installation

### Prerequisites

```bash
# Install Claude Agent SDK
pip install claude-agent-sdk

# Set API key
export ANTHROPIC_API_KEY=your_key_here
```

### Verify MCP Servers

BIOGRAPHER requires these MCP servers to be functional:

```bash
# Test EYE-D MCP
python3 -m EYE-D.mcp_server --help

# Test CORPORELLA MCP
python3 -m CORPORELLA.mcp_server --help

# Optional: Test SOCIALITE MCP
python3 -m SOCIALITE.mcp_server --help
```

---

## Usage

### CLI Interface

```bash
# Basic investigation
python3 /data/BIOGRAPHER/agent.py "John Smith"

# With email identifier
python3 /data/BIOGRAPHER/agent.py "john@acme.com"

# With phone identifier
python3 /data/BIOGRAPHER/agent.py "+1-555-0123"

# Save results to file
python3 /data/BIOGRAPHER/agent.py "john@acme.com" --output profile.json

# Verbose logging
python3 /data/BIOGRAPHER/agent.py "john@acme.com" --verbose
```

### Python API

```python
import asyncio
from BIOGRAPHER.agent import BiographerAgent, investigate_person

# Quick investigation (convenience function)
async def quick_example():
    profile = await investigate_person("john@acme.com")
    print(f"Name: {profile.name}")
    print(f"Employment: {profile.employment}")
    print(f"Confidence: {profile.confidence_score}")

# Full agent control
async def advanced_example():
    agent = BiographerAgent()

    # Investigate person
    profile = await agent.investigate("john@acme.com")

    # Access structured data
    print(f"Identifiers: {profile.identifiers}")
    print(f"Social Profiles: {profile.social_profiles}")
    print(f"Breach Exposure: {profile.breach_exposure}")
    print(f"Sources Used: {profile.sources}")

    # Disambiguation
    if len(profile.disambiguation_notes) > 0:
        print("Disambiguation needed:")
        for note in profile.disambiguation_notes:
            print(f"  - {note}")

    # Save to JSON
    import json
    with open('profile.json', 'w') as f:
        json.dump(profile.to_dict(), f, indent=2)

# Run
asyncio.run(quick_example())
```

---

## Output Structure

### PersonProfile Dataclass

```python
@dataclass
class PersonProfile:
    name: str                                    # Full name
    identifiers: Dict[str, Any]                  # email, phone, linkedin, etc.
    employment: List[Dict[str, Any]]             # Companies, positions, dates
    social_profiles: List[Dict[str, Any]]        # Platform, handle, URL
    relationships: List[Dict[str, Any]]          # Connections, type, context
    breach_exposure: List[Dict[str, Any]]        # Breaches, data exposed, dates
    disambiguation_notes: List[str]              # Clarifications, conflicts
    confidence_score: float                      # 0.0 to 1.0
    sources: List[str]                           # "EYE-D", "CORPORELLA", etc.
```

### Example Output

```json
{
  "name": "John Smith",
  "identifiers": {
    "email": "john@acme.com",
    "phone": "+1-555-0123",
    "linkedin": "https://linkedin.com/in/johnsmith"
  },
  "employment": [
    {
      "company": "Acme Corporation",
      "position": "CEO",
      "dates": "2020-present",
      "source": "CORPORELLA"
    }
  ],
  "social_profiles": [
    {
      "platform": "LinkedIn",
      "handle": "johnsmith",
      "url": "https://linkedin.com/in/johnsmith",
      "source": "EYE-D"
    }
  ],
  "breach_exposure": [
    {
      "breach": "Collection #1",
      "data_exposed": ["email", "password"],
      "date": "2019-01",
      "source": "EYE-D"
    }
  ],
  "disambiguation_notes": [
    "Multiple John Smiths found, selected based on email match"
  ],
  "confidence_score": 0.85,
  "sources": ["EYE-D", "CORPORELLA"]
}
```

---

## Investigation Workflow

BIOGRAPHER follows this autonomous workflow:

```
1. RECEIVE identifier (name/email/phone/username)
   ↓
2. DELEGATE to EYE-D for broad OSINT discovery
   ↓
3. EXTRACT company affiliations from results
   ↓
4. DELEGATE to CORPORELLA for corporate intelligence
   ↓
5. EXTRACT social handles from results
   ↓
6. DELEGATE to SOCIALITE for social media profiles (if available)
   ↓
7. DISAMBIGUATE conflicts (multiple matches)
   ├─ Compare identifiers
   ├─ Check employment overlaps
   ├─ Assess consistency
   └─ Calculate confidence score
   ↓
8. SYNTHESIZE complete PersonProfile
   ↓
9. RETURN structured results
```

---

## Disambiguation Logic

BIOGRAPHER uses intelligent disambiguation when multiple people match:

### Confidence Scoring

| Score Range | Meaning | Criteria |
|-------------|---------|----------|
| **0.8 - 1.0** | HIGH confidence | All identifiers match, consistent employment history, clear linkage |
| **0.5 - 0.8** | MEDIUM confidence | Some identifiers match, possible conflicts, reasonable linkage |
| **0.0 - 0.5** | LOW confidence | Multiple potential matches, ambiguous data, unclear linkage |

### Disambiguation Factors

1. **Identifier Overlap**: Email, phone, LinkedIn, location matches
2. **Employment Consistency**: Company affiliations align across sources
3. **Social Connections**: Shared network indicates same person
4. **Temporal Consistency**: Timeline of events makes sense
5. **Geographic Consistency**: Locations align with employment/social data

---

## Integration with SASTRE

BIOGRAPHER is designed to be used as a subagent of SASTRE AI:

```python
# In SASTRE AI configuration
sastre_options = ClaudeAgentOptions(
    agents={
        "biographer": AgentDefinition(
            description="Build complete person profiles",
            prompt="Delegate all person investigations to BIOGRAPHER...",
            # BIOGRAPHER handles its own subagents
        ),
        # ... other agents
    }
)
```

SASTRE delegates person investigations to BIOGRAPHER, which then coordinates the specialist MCPs.

---

## Agent SDK Compliance

✅ **Follows Best Practices**:
- Separation of concerns (orchestrator vs specialists)
- No cognitive overload (BIOGRAPHER has 0 tools, specialists have ≤11)
- Delegation over omniscience
- Specialist immersion (each subagent focused on domain)
- Clear task boundaries

✅ **Uses Official SDK**:
- ClaudeSDKClient for continuous conversations
- AgentDefinition for subagent configuration
- McpServerConfig for MCP integration
- Structured system prompts
- Proper tool exposure via allowed_tools

---

## Extending BIOGRAPHER

### Adding New Data Sources

To add new subagents (e.g., CRIMINAL_RECORDS, FINANCIAL_DATA):

```python
# In _build_options()
criminal_agent = AgentDefinition(
    description="Criminal records specialist",
    prompt="You search criminal databases...",
    tools=["mcp__criminal__search_records"],
    model="sonnet"
)

self.options.agents["criminal"] = criminal_agent
self.options.mcp_servers["criminal"] = {
    "type": "stdio",
    "command": "python3",
    "args": ["-m", "CRIMINAL.mcp_server"],
    "env": mcp_env,
}
```

### Custom Disambiguation Logic

Override `disambiguate()` method for specialized disambiguation:

```python
class CustomBiographerAgent(BiographerAgent):
    async def disambiguate(self, candidates: List[Dict]) -> Dict:
        # Custom logic here
        # E.g., industry-specific disambiguation
        # E.g., geographic-focused selection
        return selected_candidate
```

---

## Testing

### Unit Test

```bash
python3 /data/BIOGRAPHER/test_agent.py
```

### Integration Test with SASTRE

```bash
# Test BIOGRAPHER as SASTRE subagent
python3 /data/SASTRE/test_biographer_integration.py
```

---

## Performance

| Operation | Duration | Cost (est.) |
|-----------|----------|-------------|
| Basic person search | 10-20s | $0.05-0.10 |
| Full profile (3 specialists) | 30-60s | $0.15-0.30 |
| Disambiguation (5 candidates) | 5-10s | $0.02-0.05 |

*Costs vary based on data volume and number of subagent calls*

---

## Troubleshooting

### "MCP server not found"

```bash
# Verify MCP servers are executable
ls -la /data/EYE-D/mcp_server.py
ls -la /data/CORPORELLA/mcp_server.py

# Check PYTHONPATH
echo $PYTHONPATH
```

### "No tools available"

Check that MCP servers expose expected tools:

```bash
# List EYE-D tools
python3 -c "from EYE_D.mcp_server import *; print(list_tools())"
```

### "Low confidence score"

- Provide more specific identifiers (email > name)
- Check for common names (disambiguation may be needed)
- Verify data sources are returning results

---

## Roadmap

- [ ] Add CRIMINAL_RECORDS subagent
- [ ] Add FINANCIAL_DATA subagent
- [ ] Implement caching for repeated lookups
- [ ] Add streaming progress updates
- [ ] Support batch investigations
- [ ] Export to multiple formats (PDF, DOCX, HTML)

---

## License

Part of the SASTRE AI system.

## Support

For issues or questions, see `/data/AGENT_SDK_COMPLIANCE_AUDIT.md`
