import json
import os
import sys
import asyncio
from pathlib import Path
from typing import Dict, Any, List

# Add project paths to import ElasticService
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "python-backend"))
# sys.path.insert(0, str(project_root / "server/services/cymonides")) # Deprecated path

from brute.services.elastic_service import ElasticService

# Configuration
SCHEMA_INDEX = "search_schema"
NODES_JSON_PATH = project_root / "BACKEND/modules/CYMONIDES/metadata/c-1/matrix_schema/nodes.json"
LEGEND_JSON_PATH = project_root / "input_output/matrix/legend.json"

async def index_schema():
    print(f"🚀 Indexing Schema and Codes into {SCHEMA_INDEX}...")
    
    es = ElasticService(index_name=SCHEMA_INDEX)
    await es.initialize()
    
    # 1. Load Legend (Flat Codes)
    print(f"   📂 Loading Legend: {LEGEND_JSON_PATH}")
    with open(LEGEND_JSON_PATH, 'r') as f:
        legend = json.load(f)
        
    # 2. Load Nodes (Rich Structure)
    print(f"   📂 Loading Node Schema: {NODES_JSON_PATH}")
    with open(NODES_JSON_PATH, 'r') as f:
        nodes_schema = json.load(f)
    
    docs_to_index = []
    
    # 3. Process Legend Codes
    print("   🔄 Processing Codes...")
    for code_id, label in legend.items():
        doc = {
            "id": f"code_{code_id}",
            "type": "code",
            "code": int(code_id),
            "label": label,
            "content": f"Code {code_id}: {label}", # For full-text search
            "metadata": {
                "source": "legend.json"
            }
        }
        docs_to_index.append(doc)

    # 4. Process Node Classes & Types (Structure)
    print("   🔄 Processing Node Types...")
    classes = nodes_schema.get("classes", {})
    for class_name, class_def in classes.items():
        # Index the Class itself
        docs_to_index.append({
            "id": f"class_{class_name}",
            "type": "class",
            "label": class_name,
            "content": f"{class_name}: {class_def.get('description', '')}",
            "metadata": {
                "description": class_def.get("description"),
                "source": "nodes.json"
            }
        })
        
        # Index the Types within the Class
        types = class_def.get("types", {})
        for type_name, type_def in types.items():
            # Combine description and properties for rich context
            props = ", ".join(type_def.get("properties", {}).keys())
            content = f"Type: {type_def.get('label')} ({type_name}). {type_def.get('description')}. Properties: {props}"
            
            docs_to_index.append({
                "id": f"type_{type_name}",
                "type": "node_type",
                "label": type_def.get("label"),
                "node_class": class_name,
                "node_type": type_name,
                "codes": type_def.get("codes", []),
                "content": content,
                "metadata": {
                    "handled_by": type_def.get("handled_by"),
                    "ftm_schema": type_def.get("ftm_schema")
                }
            })

    # 5. Bulk Index
    print(f"   💾 Indexing {len(docs_to_index)} schema documents...")
    # We use index_batch but we need to make sure the index supports the fields
    # The ElasticService defaults to 'search_nodes' mapping, so we might need to force a generic mapping or separate index
    # For now, we'll rely on dynamic mapping or the service's flexibility.
    # Ideally, we'd define a schema mapping here too.
    
    success = await es.index_batch(docs_to_index)
    
    if success:
        print(f"   ✅ Successfully indexed schema.")
    else:
        print(f"   ❌ Failed to index schema.")
        
    await es.close()

if __name__ == "__main__":
    asyncio.run(index_schema())
