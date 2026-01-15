import sys
import os
import asyncio
import argparse
import logging
import json

# Add current directory to path so we can import local modules directly
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from ingester import Ingester
from classifier import Classifier
from reporter import Reporter
from inspector_gadget import InspectorGadget
from auditor import Auditor
from gliner_extractor import GlinerExtractor
from harvester import Harvester

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Jester")

async def main():
    parser = argparse.ArgumentParser(description="Jester (The Truth-Teller) - Deterministic Information Sorter")
    parser.add_argument("--mode", help="Execution mode: sort_document (default), fill_section, mine_document", default="sort_document")
    parser.add_argument("--input", help="Input file path (text)", required=False)
    parser.add_argument("--topics", help="Comma-separated list of topics", required=False)
    parser.add_argument("--topics-file", help="Path to JSON file containing topic definitions (Label -> Description)", required=False)
    parser.add_argument("--output", help="Output report path", default="sorted_report.md")
    parser.add_argument("--clear", help="Clear database before running (default: False)", action="store_true")
    parser.add_argument("--tier", help="Classification model tier: 'smart' (Claude Sonnet 4.5), 'haiku' (Claude 4.5 Haiku), or 'fast' (GPT-5-nano)", default="smart")
    parser.add_argument("--entity-report", help="Generate an entity-centric report instead of a topic-centric one.", action="store_true")
    parser.add_argument("--inspector", help="Enable Inspector Gadget (Gemini 3 Pro) for initial document sweep (Ultra Mode).", action="store_true")
    parser.add_argument("--gliner", help="Enable GLiNER local extraction pre-processor (Free/Fast).", action="store_true")
    parser.add_argument("--langextract", help="Enable Gemini LangExtract (Gemini 2.0 Flash) for structured extraction (Fast/Cheap).", action="store_true")
    parser.add_argument("--verify", help="Run Auditor (Gemini 3 Pro) to verify report against source.", action="store_true")
    parser.add_argument("--project", help="Project name/ID for isolation (default: default)", default="default")
    parser.add_argument("--style", help="Report style: default, template", default="default")
    
    # Smart Fill / Harvester Arguments
    parser.add_argument("--query", help="Search query for fill_section mode", required=False)
    parser.add_argument("--context", help="Target section header/topic for fill_section mode", required=False)

    args = parser.parse_args()
    
    # Construct Index Name
    index_name = f"jester_atoms_{args.project}"

    # --- MODE: FILL SECTION (Smart Fill) ---
    if args.mode == "fill_section":
        if not args.context:
            logger.error("Error: --context (Topic Header) is required for fill_section mode.")
            sys.exit(1)
            
        logger.info(f"=== JESTER SMART FILL: '{args.context}' ===")
        
        # 1. Setup
        ingester = Ingester(index_name=index_name)
        if args.clear:
            ingester.elastic.clear_index()

        # 2. Ingest Explicit Context (if provided via --input file)
        if args.input and os.path.exists(args.input):
            logger.info(f"Ingesting background context from {args.input}")
            ingester.ingest_file(args.input)
        
        # 3. Harvest (Search & Download) - Only if query is provided
        if args.query:
            logger.info(f"Searching for: {args.query}")
            harvester = Harvester()
            results = await harvester.harvest(args.query, limit=8, project_id=args.project)
            if results:
                ingester.ingest_search_results(results)
            elif not args.input:
                # No input file AND no search results
                logger.warning("No info found.")
                with open(args.output, "w") as f:
                    f.write(f"No information found for '{args.query}'.")
                return

        # 4. Classify (Target Topic Only)
        topics_data = [args.context]
        classifier = Classifier(topics_data, tier=args.tier, index_name=index_name)
        
        while True:
            processed = await classifier.run_batch(batch_size=50)
            if processed == 0:
                break
                
        # 5. Report (Section Fragment)
        reporter = Reporter(topics_data, index_name=index_name)
        reporter.generate_section(args.output)
        
        # 6. Audit (Optional)
        if args.verify:
            # For verification, we need a source reference.
            # If we searched, use search results. If we just used input file, use that.
            temp_source = args.output + ".source.txt"
            
            with open(temp_source, "w", encoding="utf-8") as f:
                if args.input and os.path.exists(args.input):
                    f.write(f"--- BACKGROUND CONTEXT ---\n{open(args.input, 'r', encoding='utf-8', errors='ignore').read()}\n\n")
                if 'results' in locals() and results:
                    for r in results:
                        f.write(f"--- SEARCH: {r['title']} ---\n{r['content']}\n\n")
            
            logger.info("--- PHASE 4: AUDITOR VERIFICATION ---")
            auditor = Auditor()
            verification = auditor.verify_report(args.output, temp_source)
            
            with open(args.output, "a") as f:
                f.write(f"\n\n<!-- Verification: {verification} -->")
                
            if os.path.exists(temp_source):
                os.remove(temp_source)

        logger.info(f"Section filled. Output: {args.output}")
        return

    # --- STANDARD MODES ---
    
    # Load topics
    topics_data = []
    if args.topics_file:
        try:
            with open(args.topics_file, 'r') as f:
                topics_data = json.load(f)
                logger.info(f"Loaded topic definitions from {args.topics_file}")
        except Exception as e:
            logger.error(f"Failed to load topics file: {e}")
            sys.exit(1)
    elif args.topics:
        topics_data = [t.strip() for t in args.topics.split(",")]
    
    # Validate arguments based on report type
    if not args.entity_report and not topics_data:
        logger.error("Error: --topics or --topics-file is required for topic-centric report generation.")
        sys.exit(1)
    
    if args.entity_report and (args.topics or args.topics_file):
        logger.warning("Warning: Topics are ignored when --entity-report is used.")
        if not topics_data:
             topics_data = [] 
    
    # 0. Pre-processing
    alias_map = {}
    
    # Run GLiNER (Local)
    if args.gliner and args.input:
        logger.info("--- PHASE 0A: GLiNER EXTRACTION (Local) ---")
        try:
            with open(args.input, 'r', encoding='utf-8', errors='ignore') as f:
                text_content = f.read()
            gliner = GlinerExtractor()
            gliner_map = gliner.extract(text_content)
            if gliner_map:
                alias_map.update(gliner_map)
            else:
                logger.warning("GLiNER returned no results (model loaded?)")
        except Exception as e:
            logger.warning(f"GLiNER extraction failed: {e}")

    # Run Inspector (Gemini 3 Pro)
    if args.inspector and args.input:
        logger.info("--- PHASE 0B: INSPECTOR SWEEP (Gemini 3 Pro) ---")
        inspector = InspectorGadget()
        inspector_map = inspector.initial_sweep(args.input)
        
        if inspector_map and "entities" in inspector_map:
            for ent in inspector_map["entities"]:
                name = ent.get("name")
                aliases = ent.get("aliases", [])
                if name:
                    if name in alias_map:
                        alias_map[name].extend(aliases)
                    else:
                        alias_map[name] = aliases

    # Run LangExtract (Gemini 2.0)
    if args.langextract and args.input:
        logger.info("--- PHASE 0C: LANGEXTRACT (Gemini 2.0) ---")
        inspector = InspectorGadget()
        lang_map = await inspector.run_langextract(args.input)
        # Merge
        for name, info in lang_map.items():
            if name in alias_map:
                alias_map[name].extend(info)
            else:
                alias_map[name] = info

    # 1. Ingest
    ingester = Ingester(index_name=index_name)
    if args.clear:
        logger.warning(f"Clearing existing index {index_name}...")
        ingester.elastic.clear_index()
        
    if args.input: 
        logger.info("--- PHASE 1: INGESTION ---")
        atom_count = ingester.ingest_file(args.input)
        if atom_count == 0:
            logger.error(f"Error: No content extracted from {args.input}.")
            sys.exit(1)
    else:
        logger.info("--- PHASE 1: INGESTION SKIPPED (No input file provided) ---")
    
    # 2. Classify
    if args.input: 
        logger.info(f"--- PHASE 2: CLASSIFICATION ({args.tier}) ---")
        classifier = Classifier(topics_data, tier=args.tier, alias_map=alias_map, index_name=index_name)
        
        while True:
            processed = await classifier.run_batch(batch_size=50)
            if processed == 0:
                break
    else:
        logger.info("--- PHASE 2: CLASSIFICATION SKIPPED ---")
            
    # 3. Report
    logger.info("--- PHASE 3: REPORTING ---")
    
    report_topics = list(topics_data.keys()) if isinstance(topics_data, dict) else topics_data
    reporter = Reporter(report_topics, index_name=index_name)

    if args.entity_report:
        report_output_path = args.output.replace(".md", "_entities.md") if args.output == "sorted_report.md" else args.output
        reporter.generate_entity_report(report_output_path)
    elif args.style == "template":
        report_output_path = args.output
        reporter.generate_template_report(report_output_path)
    else:
        report_output_path = args.output
        reporter.generate_report(report_output_path)
    
    logger.info(f"Done! Report saved to {report_output_path}")

    # 4. Verification (Optional)
    if args.verify and args.input:
        logger.info("--- PHASE 4: AUDITOR VERIFICATION (Gemini 3 Pro) ---")
        auditor = Auditor()
        verification_result = auditor.verify_report(report_output_path, args.input)
        
        with open(report_output_path, "a", encoding="utf-8") as f:
            f.write("\n\n---\n\n" + verification_result)
            
        logger.info("✅ Verification complete.")

if __name__ == "__main__":
    asyncio.run(main())
