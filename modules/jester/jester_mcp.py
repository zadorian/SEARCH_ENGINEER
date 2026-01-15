#!/usr/bin/env python3
"""
Jester MCP Server

Exposes the deterministic sorting pipeline to AI agents.
Usage: python3 jester_mcp.py
"""
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "python-backend"))

# Add local module path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("ERROR: mcp package not installed.", file=sys.stderr)
    sys.exit(1)

# Import modules
try:
    from modules.jester.ingester import Ingester
    from modules.jester.classifier import Classifier
    from modules.jester.reporter import Reporter
    from modules.jester.elastic_manager import ElasticManager
except ImportError:
    from ingester import Ingester
    from classifier import Classifier
    from reporter import Reporter
    from elastic_manager import ElasticManager

app = Server("jester")

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    # Common args
    project = arguments.get("project", "default")
    index_name = f"jester_atoms_{project}"

    if name == "sort_document":
        file_path = arguments.get("file_path")
        topics = arguments.get("topics") # Comma-separated string
        clear = arguments.get("clear", False) # Default to False for safety
        tier = arguments.get("tier", "smart")
        dry_run = arguments.get("dry_run", False)

        if not file_path or not topics:
            return [TextContent(type="text", text="Error: file_path and topics are required.")]

        # Normalize topics
        if isinstance(topics, str):
            topic_list = [t.strip() for t in topics.split(",")]
        else:
            topic_list = topics

        try:
            # 1. Setup
            elastic = ElasticManager(index_name=index_name)
            if clear and not dry_run:
                elastic.clear_index()
            
            # 2. Ingest
            atom_count = 0
            if not dry_run:
                ingester = Ingester(index_name=index_name)
                atom_count = ingester.ingest_file(file_path)
                if atom_count == 0:
                    return [TextContent(type="text", text=f"Error: No content extracted from {file_path}.")]
            else:
                return [TextContent(type="text", text="Dry-run: ingestion/classification/report skipped.")]

            # 3. Classify
            classifier = Classifier(topic_list, tier=tier, index_name=index_name)
            
            while True:
                processed = await classifier.run_batch(batch_size=50)
                if processed == 0:
                    break
            
            # 4. Report
            reporter = Reporter(topic_list, index_name=index_name)
            
            source_path = Path(file_path)
            report_path = f"{source_path.stem}_sorted_report.md"
            
            reporter.generate_report(report_path)
            
            if os.path.exists(report_path):
                with open(report_path, "r", encoding='utf-8') as f:
                    report_content = f.read()
                return [TextContent(type="text", text=report_content)]
            else:
                return [TextContent(type="text", text="Error: Report file was not generated.")]

        except Exception as e:
            return [TextContent(type="text", text=f"Error during processing: {str(e)}")]

    elif name == "get_entity_report":
        output_file = arguments.get("output_file", "entity_report.md")
        
        try:
            reporter = Reporter([], index_name=index_name)
            reporter.generate_entity_report(output_file)

            if os.path.exists(output_file):
                with open(output_file, "r", encoding='utf-8') as f:
                    report_content = f.read()
                return [TextContent(type="text", text=report_content)]
            else:
                return [TextContent(type="text", text="Error: Entity report file was not generated.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error generating entity report: {str(e)}")]

    elif name == "mine_document":
        file_path = arguments.get("file_path")
        tier = arguments.get("tier", "fast")
        verify = arguments.get("verify", True)
        
        if not file_path:
            return [TextContent(type="text", text="Error: file_path is required.")]

        try:
            # 1. Inspector
            from inspector_gadget import InspectorGadget
            inspector = InspectorGadget()
            
            topics_map = inspector.discover_topics(file_path)
            if not topics_map:
                return [TextContent(type="text", text="Error: Could not discover topics.")]
                
            alias_map = inspector.initial_sweep(file_path)
            
            # 2. Setup
            elastic = ElasticManager(index_name=index_name)
            elastic.clear_index()
            
            # 3. Ingest
            ingester = Ingester(index_name=index_name)
            ingester.ingest_file(file_path)
            
            # 4. Classify
            classifier = Classifier(topics_map, tier=tier, alias_map=alias_map, index_name=index_name)
            
            while True:
                processed = await classifier.run_batch(batch_size=50)
                if processed == 0:
                    break
            
            # 5. Report
            reporter = Reporter(list(topics_map.keys()), index_name=index_name)
            report_path = f"{Path(file_path).stem}_mined_report.md"
            reporter.generate_report(report_path)
            
            # 6. Verify
            verification_text = ""
            if verify:
                from auditor import Auditor
                auditor = Auditor()
                verification_text = auditor.verify_report(report_path, file_path)
                with open(report_path, "a", encoding="utf-8") as f:
                    f.write("\n\n---\n\n" + verification_text)
            
            with open(report_path, "r") as f:
                content = f.read()
                
            return [TextContent(type="text", text=f"MINING COMPLETE.\n\nTopics: {', '.join(topics_map.keys())}\n\n{content}")]

        except Exception as e:
            return [TextContent(type="text", text=f"Mining failed: {str(e)}")]

    elif name == "research_topic":
        query = arguments.get("query")
        
        if not query:
            return [TextContent(type="text", text="Error: query is required.")]
            
        try:
            # Use Harvester
            from harvester import Harvester
            harvester = Harvester()
            results = await harvester.harvest(query, limit=5)
            
            if not results:
                return [TextContent(type="text", text="No results found.")]
                
            # Format results
            output = f"RESEARCH RESULTS for '{query}':\n\n"
            for i, res in enumerate(results, 1):
                output += f"{i}. {res['title']} ({res['url']})\n"
                output += f"   {res.get('content', '')[:300]}...\n\n"
                
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return [TextContent(type="text", text=f"Research failed: {str(e)}")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]

# Define Tool schemas
@app.list_tools()
async def list_tools():
    """List available tools"""
    common_props = {
        "project": {"type": "string", "description": "Project identifier for isolation (default: default)"}
    }

    return [
        Tool(
            name="research_topic",
            description="Research a topic using Firecrawl (Live) and Linklater (Archive).",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Research query"}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="sort_document",
            description="Ingest and sort document into topics. Supports Smart/Fast tiers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to file"},
                    "topics": {"type": "string", "description": "Comma-separated topics"},
                    "clear": {"type": "boolean", "description": "Clear database before running (default: False)."},
                    "tier": {"type": "string", "enum": ["smart", "fast", "haiku"]},
                    "dry_run": {"type": "boolean", "description": "Skip ingest/classify/report (safety)"},
                    **common_props
                },
                "required": ["file_path", "topics"]
            }
        ),
        Tool(
            name="get_entity_report",
            description="Generate entity report from processed data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "output_file": {"type": "string"},
                    **common_props
                }
            }
        ),
        Tool(
            name="mine_document",
            description="Zero-config mining: Auto-discover topics + aliases, sort, and verify.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "tier": {"type": "string", "enum": ["smart", "fast", "haiku"]},
                    "verify": {"type": "boolean"},
                    **common_props
                },
                "required": ["file_path"]
            }
        )
    ]

async def main():
    """Run the MCP server"""
    print("✓ Jester MCP server started", file=sys.stderr)
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
