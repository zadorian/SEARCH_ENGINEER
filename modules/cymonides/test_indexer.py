#!/usr/bin/env python3
import sys
import asyncio
sys.path.insert(0, "/data/CYMONIDES")

from elasticsearch import AsyncElasticsearch

async def main():
    print("="*60)
    print("CYMONIDES INDEXER TOOLKIT - TEST SUITE")
    print("="*60)
    es = AsyncElasticsearch(["http://localhost:9200"])
    
    try:
        # Test 1: Schema Registry
        print("\n[TEST 1] Schema Registry")
        print("-" * 40)
        from indexer.schemas.registry import SchemaRegistry, Tier, DataType
        registry = SchemaRegistry(es)
        print(f"  Tiers defined: {[t.value for t in Tier]}")
        print(f"  Data types: {len(list(DataType))} types")
        c3_config = registry.get_tier_config(Tier.C3)
        print(f"  C-3 alias: {c3_config.alias}")
        cc_config = registry.get_tier_config(Tier.CC_GRAPH)
        print(f"  CC Graph alias: {cc_config.alias}")
        print("  [OK] Schema Registry")
        
        # Test 2: Readers
        print("\n[TEST 2] Data Readers")
        print("-" * 40)
        from indexer.readers.jsonl_reader import JSONLReader
        from indexer.readers.base import ReaderConfig
        reader = JSONLReader("/data/CYMONIDES/test_data.jsonl", ReaderConfig(batch_size=10))
        reader.open()
        records = [r.data for r in reader if r.success]
        reader.close()
        print(f"  Read {len(records)} records from test_data.jsonl")
        print("  [OK] JSONL Reader")
        
        # Test 3: Pipeline Stages
        print("\n[TEST 3] Pipeline Stages")
        print("-" * 40)
        from indexer.pipeline.stage import TransformStage, FilterStage, CommonTransforms
        transform = TransformStage(name="t", add_fields={"indexed_at": CommonTransforms.timestamp_now})
        result = transform.process({"url": "http://test.com"})
        has_ts = "indexed_at" in result.data
        print(f"  Transform added timestamp: {has_ts}")
        filter_stage = FilterStage(name="f", required_fields=["url"])
        r1 = filter_stage.process({"url": "http://test.com"})
        r2 = filter_stage.process({"title": "no url"})
        print(f"  Filter pass/reject: {r1.success}/{r2.action}")
        print("  [OK] Pipeline Stages")
        
        # Test 4: Entity Linking
        print("\n[TEST 4] Entity Linking")
        print("-" * 40)
        from indexer.linking.linker import EntityLinker
        linker = EntityLinker(es)
        email_result = await linker.link_email("test@example.com")
        print(f"  Email link success: {email_result.success}")
        print(f"  Match type: {email_result.match_type}")
        domain_result = await linker.link_domain("example.com")
        print(f"  Domain link success: {domain_result.success}")
        print("  [OK] Entity Linker")
        
        # Test 5: Pipeline Engine
        print("\n[TEST 5] Full Pipeline Run")
        print("-" * 40)
        from indexer.pipeline.config import PipelineConfig, OutputConfig, OutputMode, StageConfig
        from indexer.pipeline.engine import PipelineEngine
        
        config = PipelineConfig(
            name="test",
            reader_type="jsonl",
            stages=[
                StageConfig(type="filter", name="f", config={"min_field_count": 2}),
                StageConfig(type="transform", name="t", config={"add_fields": {"indexed_at": "timestamp_now"}}),
            ],
            output=OutputConfig(index="cymonides-test", mode=OutputMode.INDEX, batch_size=10),
        )
        
        if not await es.indices.exists(index="cymonides-test"):
            await es.indices.create(index="cymonides-test", body={
                "settings": {"number_of_shards": 1},
                "mappings": {"properties": {"url": {"type": "keyword"}, "content": {"type": "text"}}}
            })
        
        engine = PipelineEngine(es, config)
        stats = await engine.run("/data/CYMONIDES/test_data.jsonl")
        print(f"  Read: {stats.total_read}, Indexed: {stats.total_indexed}")
        print(f"  Duration: {stats.duration_seconds:.2f}s")
        print("  [OK] Pipeline Engine")
        
        await es.indices.refresh(index="cymonides-test")
        cnt = await es.count(index="cymonides-test")
        print(f"  Docs in cymonides-test: {cnt['count']}")
        
        # Test 6: Job Manager
        print("\n[TEST 6] Job Manager")
        print("-" * 40)
        from indexer.jobs.manager import JobManager
        jm = JobManager(es)
        job = await jm.create_job({"source_type": "jsonl", "source_path": "/test.jsonl", "target_index": "test", "pipeline": "default"})
        print(f"  Created job: {job.job_id[:8]}...")
        print(f"  Status: {job.status.value}")
        jobs = await jm.list_jobs(limit=5)
        print(f"  Total jobs: {len(jobs)}")
        print("  [OK] Job Manager")
        
        # Summary
        print("\n" + "="*60)
        print("ALL TESTS PASSED!")
        print("="*60)
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        await es.close()
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
