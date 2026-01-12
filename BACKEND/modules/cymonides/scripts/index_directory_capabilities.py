import json
import sys
import asyncio
from pathlib import Path
from typing import Dict, Any, List

# Add project paths
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "python-backend"))

from brute.adapter.drill_search_adapter import DrillSearchAdapter

# Configuration
MATRIX_DIR = project_root / "input_output/matrix"
SOURCES_PATH = MATRIX_DIR / "sources.json"
REGISTRIES_PATH = MATRIX_DIR / "registries.json"
CAPABILITIES_PATH = MATRIX_DIR / "nexus_database_capabilities.json"
RULES_PATH = MATRIX_DIR / "rules.json"

async def index_directory():
    print("🚀 Indexing Directory & Capabilities for Arbitrage Analysis...")
    
    adapter = DrillSearchAdapter()
    
    # 1. Index Nexus Capabilities
    if CAPABILITIES_PATH.exists():
        print(f"   📂 Loading Capabilities: {CAPABILITIES_PATH}")
        with open(CAPABILITIES_PATH, 'r') as f:
            capabilities = json.load(f)
            
        count = 0
        # Capability file is a Dict where keys are DB names
        if isinstance(capabilities, dict):
            items = capabilities.items()
        else:
            # Fallback if it is a list
            items = [(c.get("name", "Unknown"), c) for c in capabilities]

        for name, cap in items:
            # Print progress
            if count % 5 == 0:
                print(f"   ⏳ Processing capability {count}...", end="\r", flush=True)

            # Build rich content string for vectorization
            content_parts = [
                f"Database: {name}",
                f"Description: {cap.get('description', '')}",
                f"Jurisdictions: {', '.join(cap.get('countries', []))}", # Changed from jurisdictions to countries based on file read
                f"Inputs: {', '.join(cap.get('inputs', []))}",
                f"Outputs: {', '.join(cap.get('outputs', []))}",
                f"Sources: {', '.join(cap.get('sources', []))}"
            ]
            
            # Arbitrage keywords
            desc_lower = str(cap).lower()
            if "subsidiaries" in desc_lower:
                content_parts.append("Arbitrage Opportunity: Discloses subsidiary relationships.")
            if "shareholders" in desc_lower:
                content_parts.append("Arbitrage Opportunity: Discloses shareholder information.")
            if "beneficial" in desc_lower:
                content_parts.append("Arbitrage Opportunity: Discloses beneficial ownership.")
                
            adapter.index_node(
                id=f"cap_{name.lower().replace(' ', '_').replace('.', '_')}",
                label=name,
                content="\n".join(content_parts),
                className="resource",
                typeName="database_capability",
                metadata={
                    "source_file": "nexus_database_capabilities.json",
                    "capabilities": cap,
                    "suite": "directory"
                }
            )
            count += 1
        print(f"   ✅ Indexed {count} capability records.")

    # 2. Index Registries
    if REGISTRIES_PATH.exists():
        print(f"   📂 Loading Registries: {REGISTRIES_PATH}")
        with open(REGISTRIES_PATH, 'r') as f:
            registries = json.load(f)
            
        count = 0
        # Handle list or dict structure
        # If it's a list, iterate. If dict with "registries" key, use that.
        if isinstance(registries, list):
            items = registries
        else:
            items = registries.get("registries", [])
        
        for reg in items:
            # Print progress
            if count % 10 == 0:
                print(f"   ⏳ Processing registry {count}...", end="\r", flush=True)

            jurisdiction = reg.get("jurisdiction") or reg.get("country", "Unknown")
            name = reg.get("name") or f"{jurisdiction} Registry"
            
            content = f"Registry: {name}. Jurisdiction: {jurisdiction}. "
            content += f"URL: {reg.get('url', '')}. "
            content += f"Data: {reg.get('description', '')}"
            
            adapter.index_node(
                id=f"reg_{count}_{name.lower().replace(' ', '_')[:30]}",
                label=name,
                content=content,
                className="resource",
                typeName="registry",
                metadata={
                    "source_file": "registries.json",
                    "jurisdiction": jurisdiction,
                    "registry_data": reg,
                    "suite": "directory"
                }
            )
            count += 1
        print(f"   ✅ Indexed {count} registries.")

    # 3. Index Rules
    if RULES_PATH.exists():
        print(f"   📂 Loading Rules: {RULES_PATH}")
        with open(RULES_PATH, 'r') as f:
            rules = json.load(f)
            
        count = 0
        # Rules file is a list of rule objects at the top level or under "rules" key?
        # Based on file read, it's a list [ {id: ...}, ... ]
        if isinstance(rules, list):
            items = rules
        else:
            items = rules.get("rules", [])
        
        for rule in items:
            # Print progress
            if count % 10 == 0:
                print(f"   ⏳ Processing rule {count}...", end="\r", flush=True)

            # Use 'id' as name if 'name' is missing, or 'label'
            name = rule.get("label") or rule.get("id") or f"Rule {count}"
            
            # Build content description
            content = f"Rule: {name}. "
            content += f"Description: {rule.get('notes', '')}. "
            
            # Add friction info
            if rule.get("friction"):
                content += f"Friction: {rule.get('friction')}. "
                
            # Add jurisdiction info
            if rule.get("jurisdiction"):
                content += f"Jurisdiction: {rule.get('jurisdiction')}. "

            # Add arbitrage hints
            if "Open" in str(rule.get("friction", "")):
                content += "Arbitrage Opportunity: Low friction data access. "
            
            adapter.index_node(
                id=f"rule_{rule.get('id', count)}",
                label=name,
                content=content,
                className="logic",
                typeName="rule",
                metadata={
                    "rule_data": rule,
                    "suite": "system"
                }
            )
            count += 1
        print(f"   ✅ Indexed {count} rules.")

    print("\n✅ Directory Capabilities Indexed. You can now query for arbitrage opportunities.")

if __name__ == "__main__":
    asyncio.run(index_directory())
