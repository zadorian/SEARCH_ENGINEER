#!/usr/bin/env python3
"""
ULTRATEST - Comprehensive verification of Cymonides Indexer Toolkit
Tests every component thoroughly
"""

import sys
import os
import asyncio
import json
import traceback
sys.path.insert(0, "/data/CYMONIDES")

from elasticsearch import AsyncElasticsearch

class UltraTest:
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
        
    def test(self, name, condition, details=""):
        if condition:
            self.results.append(f"  [PASS] {name}")
            self.passed += 1
        else:
            self.results.append(f"  [FAIL] {name}: {details}")
            self.failed += 1
        return condition

async def run_ultratest():
    ut = UltraTest()
    es = AsyncElasticsearch(["http://localhost:9200"])
    
    print("="*70)
    print("CYMONIDES INDEXER TOOLKIT - ULTRATEST VERIFICATION")
    print("="*70)
    
    try:
        # ============================================================
        # SECTION 1: CORE MODULE IMPORTS
        # ============================================================
        print("\n[SECTION 1] Core Module Imports")
        print("-"*50)
        
        try:
            from indexer.core.envelope import DocumentEnvelope, EnvelopeStatus, TransformRecord, EntityLink
            ut.test("DocumentEnvelope import", True)
        except Exception as e:
            ut.test("DocumentEnvelope import", False, str(e))
            
        try:
            from indexer.core.source import Source, SourceType, SourceConfig
            ut.test("Source import", True)
        except Exception as e:
            ut.test("Source import", False, str(e))
            
        try:
            from indexer.core.job import IndexingJob, JobProgress, JobCheckpoint, JobStatus
            ut.test("Job import", True)
        except Exception as e:
            ut.test("Job import", False, str(e))
        
        for r in ut.results[-3:]:
            print(r)
        
        # ============================================================
        # SECTION 2: SCHEMA REGISTRY
        # ============================================================
        print("\n[SECTION 2] Schema Registry")
        print("-"*50)
        ut.results.clear()
        
        try:
            from indexer.schemas.registry import SchemaRegistry, Tier, DataType, TierConfig
            ut.test("SchemaRegistry import", True)
            
            registry = SchemaRegistry(es)
            ut.test("SchemaRegistry instantiation", registry is not None)
            
            # Test all tiers exist
            for tier in [Tier.C1, Tier.C2, Tier.C3, Tier.CC_GRAPH]:
                cfg = registry.get_tier_config(tier)
                ut.test(f"Tier {tier.value} config", cfg is not None and cfg.alias != "")
            
            # Test data types
            ut.test("DataType count >= 10", len(list(DataType)) >= 10, f"Got {len(list(DataType))}")
            
            # Test schema retrieval
            schema = registry.get_schema(DataType.CONTENT)
            ut.test("CONTENT schema exists", schema is not None)
            
            schema = registry.get_schema(DataType.BREACH_RECORD)
            ut.test("BREACH_RECORD schema exists", schema is not None)
            
        except Exception as e:
            ut.test("SchemaRegistry tests", False, str(e))
        
        for r in ut.results:
            print(r)
        
        # ============================================================
        # SECTION 3: READERS
        # ============================================================
        print("\n[SECTION 3] Data Readers")
        print("-"*50)
        ut.results.clear()
        
        try:
            from indexer.readers.base import BaseReader, ReaderConfig, ReadResult
            ut.test("BaseReader import", True)
            
            from indexer.readers.jsonl_reader import JSONLReader
            ut.test("JSONLReader import", True)
            
            from indexer.readers.parquet_reader import ParquetReader
            ut.test("ParquetReader import", True)
            
            from indexer.readers.file_reader import FileReader
            ut.test("FileReader import", True)
            
            from indexer.readers.breach_reader import BreachReader
            ut.test("BreachReader import", True)
            
            # Test JSONL reader functionality
            reader = JSONLReader("/data/CYMONIDES/test_data.jsonl", ReaderConfig())
            reader.open()
            records = [r for r in reader if r.success]
            reader.close()
            ut.test("JSONLReader reads records", len(records) >= 1, f"Got {len(records)}")
            ut.test("ReadResult has data", records[0].data is not None if records else False)
            
        except Exception as e:
            ut.test("Readers tests", False, str(e))
            traceback.print_exc()
        
        for r in ut.results:
            print(r)
        
        # ============================================================
        # SECTION 4: PIPELINE STAGES
        # ============================================================
        print("\n[SECTION 4] Pipeline Stages")
        print("-"*50)
        ut.results.clear()
        
        try:
            from indexer.pipeline.stage import (
                PipelineStage, TransformStage, FilterStage, 
                EnrichStage, DedupeStage, StageResult, CommonTransforms
            )
            ut.test("Pipeline stages import", True)
            
            # Test TransformStage
            transform = TransformStage(
                name="test",
                add_fields={"test_field": lambda: "test_value"}
            )
            result = transform.process({"existing": "data"})
            ut.test("TransformStage adds fields", 
                    result.success and "test_field" in result.data)
            
            # Test FilterStage
            filter_stage = FilterStage(
                name="test",
                required_fields=["required"]
            )
            pass_result = filter_stage.process({"required": "value"})
            fail_result = filter_stage.process({"other": "value"})
            ut.test("FilterStage passes valid", pass_result.success)
            ut.test("FilterStage rejects invalid", fail_result.action == "skip")
            
            # Test DedupeStage
            dedupe = DedupeStage(name="test", key_fields=["id"])
            r1 = dedupe.process({"id": "123"})
            r2 = dedupe.process({"id": "123"})
            ut.test("DedupeStage first pass", r1.success)
            ut.test("DedupeStage second skip", r2.action == "skip")
            
            # Test CommonTransforms
            ut.test("CommonTransforms.lowercase", CommonTransforms.lowercase("TEST") == "test")
            ut.test("CommonTransforms.extract_domain", 
                    CommonTransforms.extract_domain("user@example.com") == "example.com")
            
        except Exception as e:
            ut.test("Pipeline stages tests", False, str(e))
            traceback.print_exc()
        
        for r in ut.results:
            print(r)
        
        # ============================================================
        # SECTION 5: PIPELINE ENGINE
        # ============================================================
        print("\n[SECTION 5] Pipeline Engine")
        print("-"*50)
        ut.results.clear()
        
        try:
            from indexer.pipeline.engine import PipelineEngine, PipelineStats
            from indexer.pipeline.config import PipelineConfig, OutputConfig, OutputMode, StageConfig
            ut.test("PipelineEngine import", True)
            
            # Test config creation
            config = PipelineConfig(
                name="ultratest",
                reader_type="jsonl",
                stages=[
                    StageConfig(type="filter", name="f", config={"min_field_count": 1}),
                ],
                output=OutputConfig(
                    index="cymonides-ultratest",
                    mode=OutputMode.INDEX,
                    batch_size=10
                ),
            )
            ut.test("PipelineConfig creation", config.name == "ultratest")
            
            # Create test index
            if await es.indices.exists(index="cymonides-ultratest"):
                await es.indices.delete(index="cymonides-ultratest")
            await es.indices.create(index="cymonides-ultratest", body={
                "settings": {"number_of_shards": 1, "number_of_replicas": 0}
            })
            
            # Run pipeline
            engine = PipelineEngine(es, config)
            stats = await engine.run("/data/CYMONIDES/test_data.jsonl")
            
            ut.test("Pipeline runs without error", True)
            ut.test("Pipeline reads records", stats.total_read >= 1, f"Read {stats.total_read}")
            ut.test("Pipeline indexes records", stats.total_indexed >= 1, f"Indexed {stats.total_indexed}")
            ut.test("Pipeline has stats", stats.duration_seconds >= 0)
            
            # Verify indexed
            await es.indices.refresh(index="cymonides-ultratest")
            cnt = await es.count(index="cymonides-ultratest")
            ut.test("Records in ES", doc_count >= 1, f'Count: {cnt[chr(99)+chr(111)+chr(117)+chr(110)+chr(116)]}')
            
            # Cleanup
            await es.indices.delete(index="cymonides-ultratest")
            
        except Exception as e:
            ut.test("PipelineEngine tests", False, str(e))
            traceback.print_exc()
        
        for r in ut.results:
            print(r)
        
        # ============================================================
        # SECTION 6: JOB MANAGER
        # ============================================================
        print("\n[SECTION 6] Job Manager")
        print("-"*50)
        ut.results.clear()
        
        try:
            from indexer.jobs.manager import JobManager
            ut.test("JobManager import", True)
            
            jm = JobManager(es)
            ut.test("JobManager instantiation", jm is not None)
            
            # Create job
            job = await jm.create_job({
                "source_type": "jsonl",
                "source_path": "/test/ultratest.jsonl",
                "target_index": "test-index",
                "pipeline": "test"
            })
            ut.test("Job creation", job is not None)
            ut.test("Job has ID", job.job_id is not None and len(job.job_id) > 0)
            ut.test("Job status pending", job.status == JobStatus.PENDING)
            
            # Get job
            retrieved = await jm.get_job(job.job_id)
            ut.test("Job retrieval", retrieved is not None)
            ut.test("Job ID matches", retrieved.job_id == job.job_id)
            
            # List jobs
            jobs = await jm.list_jobs(limit=10)
            ut.test("Job listing", len(jobs) >= 1)
            
        except Exception as e:
            ut.test("JobManager tests", False, str(e))
            traceback.print_exc()
        
        for r in ut.results:
            print(r)
        
        # ============================================================
        # SECTION 7: ENTITY LINKING
        # ============================================================
        print("\n[SECTION 7] Entity Linking")
        print("-"*50)
        ut.results.clear()
        
        try:
            from indexer.linking.linker import EntityLinker, LinkResult
            from indexer.linking.matchers import EmailMatcher, DomainMatcher
            ut.test("EntityLinker import", True)
            ut.test("Matchers import", True)
            
            linker = EntityLinker(es)
            ut.test("EntityLinker instantiation", linker is not None)
            
            # Test email linking (may not find match, but should not error)
            result = await linker.link_email("test@example.com")
            ut.test("Email link returns LinkResult", isinstance(result, LinkResult))
            ut.test("LinkResult has success attr", hasattr(result, "success"))
            
            # Test domain linking
            result = await linker.link_domain("example.com")
            ut.test("Domain link returns LinkResult", isinstance(result, LinkResult))
            
            # Test document linking
            doc = {"email": "user@test.com", "domain": "test.com", "content": "test"}
            results = await linker.link_document(doc)
            ut.test("Document linking returns list", isinstance(results, list))
            
        except Exception as e:
            ut.test("EntityLinker tests", False, str(e))
            traceback.print_exc()
        
        for r in ut.results:
            print(r)
        
        # ============================================================
        # SECTION 8: MCP TOOLS
        # ============================================================
        print("\n[SECTION 8] MCP Tools Integration")
        print("-"*50)
        ut.results.clear()
        
        try:
            from indexer.mcp_tools import INDEXER_TOOLS, IndexerMCPHandler, get_indexer_tools
            ut.test("MCP tools import", True)
            
            tools = get_indexer_tools()
            ut.test("get_indexer_tools returns list", isinstance(tools, list))
            ut.test("16 tools defined", len(tools) == 16, f"Got {len(tools)}")
            
            # Check tool structure
            tool_names = [t["name"] for t in tools]
            required_tools = [
                "indexer_job_create", "indexer_job_start", "indexer_job_status",
                "indexer_tier_info", "indexer_quick", "indexer_pipeline_list"
            ]
            for tool in required_tools:
                ut.test(f"Tool {tool} exists", tool in tool_names)
            
            # Test handler
            handler = IndexerMCPHandler(es)
            ut.test("IndexerMCPHandler instantiation", handler is not None)
            
            # Test tier_info handler
            result = handler._tier_info({"tier": "all"})
            ut.test("tier_info handler works", "tiers" in result)
            
            # Test pipeline_list handler
            result = handler._pipeline_list()
            ut.test("pipeline_list handler works", "pipelines" in result)
            
        except Exception as e:
            ut.test("MCP tools tests", False, str(e))
            traceback.print_exc()
        
        for r in ut.results:
            print(r)
        
        # ============================================================
        # SECTION 9: ES INDICES
        # ============================================================
        print("\n[SECTION 9] Elasticsearch Indices")
        print("-"*50)
        ut.results.clear()
        
        try:
            required_indices = ["cymonides-jobs", "cymonides-sources", "cymonides-dlq"]
            for idx in required_indices:
                exists = await es.indices.exists(index=idx)
                ut.test(f"Index {idx} exists", exists)
            
            # Test cymonides-test has data
            if await es.indices.exists(index="cymonides-test"):
                cnt = await es.count(index="cymonides-test")
                ut.test("cymonides-test has documents", doc_count >= 1, f'Count: {cnt[chr(99)+chr(111)+chr(117)+chr(110)+chr(116)]}')
            
        except Exception as e:
            ut.test("ES indices tests", False, str(e))
        
        for r in ut.results:
            print(r)
        
        # ============================================================
        # SECTION 10: FULL INTEGRATION TEST
        # ============================================================
        print("\n[SECTION 10] Full Integration Test")
        print("-"*50)
        ut.results.clear()
        
        try:
            # Create handler and run through MCP-style workflow
            handler = IndexerMCPHandler(es)
            
            # 1. Create job via handler
            job_result = await handler._job_create({
                "source_type": "jsonl",
                "source_path": "/data/CYMONIDES/test_data.jsonl",
                "target_index": "integration-test",
                "pipeline": "content"
            })
            ut.test("Integration: job created", "job_id" in job_result)
            
            # 2. Check tier info
            tier_result = handler._tier_info({"tier": "c3"})
            ut.test("Integration: tier info", "alias" in tier_result)
            
            # 3. List pipelines
            pipeline_result = handler._pipeline_list()
            ut.test("Integration: pipelines listed", len(pipeline_result.get("pipelines", [])) >= 1)
            
            ut.test("Full integration workflow", True)
            
        except Exception as e:
            ut.test("Integration tests", False, str(e))
            traceback.print_exc()
        
        for r in ut.results:
            print(r)
        
        # ============================================================
        # SUMMARY
        # ============================================================
        print("\n" + "="*70)
        print("ULTRATEST SUMMARY")
        print("="*70)
        print(f"  Total Tests: {ut.passed + ut.failed}")
        print(f"  Passed: {ut.passed}")
        print(f"  Failed: {ut.failed}")
        print(f"  Success Rate: {ut.passed/(ut.passed+ut.failed)*100:.1f}%")
        print("="*70)
        
        if ut.failed == 0:
            print("\n*** ALL TESTS PASSED - SYSTEM FULLY OPERATIONAL ***\n")
        else:
            print(f"\n*** {ut.failed} TESTS FAILED - REVIEW REQUIRED ***\n")
        
        return ut.failed
        
    finally:
        await es.close()

if __name__ == "__main__":
    sys.exit(asyncio.run(run_ultratest()))
