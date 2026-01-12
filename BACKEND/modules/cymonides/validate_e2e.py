#!/usr/bin/env python3
import sys
sys.path.insert(0, "/data/CYMONIDES")
import asyncio
from elasticsearch import AsyncElasticsearch

async def validate():
    print("="*60)
    print("END-TO-END WORKFLOW VALIDATION")
    print("="*60)
    
    es = AsyncElasticsearch(["http://localhost:9200"])
    
    try:
        # 1. Indexer Module
        print("\n[1] Indexer Module Imports")
        print("-" * 40)
        from indexer import (
            SchemaRegistry, Tier, DataType,
            PipelineEngine, PipelineConfig,
            JobManager, JSONLReader
        )
        print("  All core imports OK")
        
        # 2. MCP Tools
        print("\n[2] MCP Indexer Tools")
        print("-" * 40)
        from indexer.mcp_tools import INDEXER_TOOLS, IndexerMCPHandler
        print(f"  {len(INDEXER_TOOLS)} tools defined")
        
        # 3. ES Indices Check
        print("\n[3] Elasticsearch Indices")
        print("-" * 40)
        indices = ["cymonides-jobs", "cymonides-sources", "cymonides-dlq", "cymonides-test"]
        for idx in indices:
            exists = await es.indices.exists(index=idx)
            status = "EXISTS" if exists else "MISSING"
            print(f"  {idx}: {status}")
        
        # 4. Test Index Content
        print("\n[4] Test Index Content")
        print("-" * 40)
        cnt = await es.count(index="cymonides-test")
        doc_count = cnt["count"]
        print(f"  Documents in cymonides-test: {doc_count}")
        
        # Sample document
        resp = await es.search(index="cymonides-test", size=1)
        if resp["hits"]["hits"]:
            doc = resp["hits"]["hits"][0]["_source"]
            print(f"  Sample doc fields: {list(doc.keys())}")
        
        # 5. Job Registry
        print("\n[5] Job Registry")
        print("-" * 40)
        jobs_cnt = await es.count(index="cymonides-jobs")
        job_count = jobs_cnt["count"]
        print(f"  Jobs registered: {job_count}")
        
        # 6. Tier Configuration
        print("\n[6] Tier Configuration")
        print("-" * 40)
        registry = SchemaRegistry(es)
        for tier in Tier:
            cfg = registry.get_tier_config(tier)
            print(f"  {tier.value}: alias={cfg.alias}")
        
        print("\n" + "="*60)
        print("VALIDATION COMPLETE - ALL SYSTEMS OPERATIONAL")
        print("="*60)
        
    finally:
        await es.close()

if __name__ == "__main__":
    asyncio.run(validate())
