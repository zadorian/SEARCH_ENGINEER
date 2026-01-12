"""
MCP Tools for Cymonides Indexer
Provides tool definitions and handlers for the indexer toolkit
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger("cymonides-indexer")

# Import indexer components
from .core.job import IndexingJob, JobStatus
from .jobs.manager import JobManager
from .schemas.registry import SchemaRegistry, Tier, DataType
from .pipeline.config import PipelineConfig, BREACH_PIPELINE, CONTENT_PIPELINE, ENTITY_PIPELINE
from .pipeline.engine import PipelineEngine

# Tool definitions for MCP registration
INDEXER_TOOLS = [
    # === JOB MANAGEMENT ===
    {
        "name": "indexer_job_create",
        "description": "Create a new indexing job. Returns job_id for tracking.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_path": {"type": "string", "description": "Path to source file/directory"},
                "source_type": {"type": "string", "enum": ["jsonl", "parquet", "csv", "breach"], "description": "Source format"},
                "target_index": {"type": "string", "description": "Target ES index"},
                "pipeline": {"type": "string", "default": "default", "description": "Pipeline name (breach, content, entity, or custom)"},
                "batch_size": {"type": "integer", "default": 1000, "description": "Batch size for indexing"},
            },
            "required": ["source_path", "source_type", "target_index"]
        }
    },
    {
        "name": "indexer_job_start",
        "description": "Start a pending indexing job.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID to start"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "indexer_job_status",
        "description": "Get status of an indexing job.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "indexer_job_list",
        "description": "List all indexing jobs with optional filtering.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending", "running", "completed", "failed", "cancelled"], "description": "Filter by status"},
                "limit": {"type": "integer", "default": 20, "description": "Max jobs to return"}
            }
        }
    },
    {
        "name": "indexer_job_pause",
        "description": "Pause a running indexing job.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID to pause"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "indexer_job_resume",
        "description": "Resume a paused indexing job from checkpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID to resume"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "indexer_job_cancel",
        "description": "Cancel an indexing job.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID to cancel"}
            },
            "required": ["job_id"]
        }
    },
    
    # === SCHEMA & TIER INFO ===
    {
        "name": "indexer_tier_info",
        "description": "Get information about Cymonides tier structure (C-1, C-2, C-3, CC Graph).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tier": {"type": "string", "enum": ["c1", "c2", "c3", "cc_graph", "all"], "default": "all", "description": "Tier to get info for"}
            }
        }
    },
    {
        "name": "indexer_schema_info",
        "description": "Get schema information for a data type.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data_type": {"type": "string", "description": "Data type (person, company, domain, breach_record, content, etc.)"}
            },
            "required": ["data_type"]
        }
    },
    
    # === QUICK INDEXING ===
    {
        "name": "indexer_quick",
        "description": "Quick one-shot indexing of a file. Creates job, runs it, returns results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_path": {"type": "string", "description": "Path to source file"},
                "target_tier": {"type": "string", "enum": ["c2", "c3"], "description": "Target tier (c2=content, c3=entities)"},
                "data_type": {"type": "string", "description": "Data type hint (breach, content, entity)"},
            },
            "required": ["source_path"]
        }
    },
    
    # === PIPELINE MANAGEMENT ===
    {
        "name": "indexer_pipeline_list",
        "description": "List available indexing pipelines.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "indexer_pipeline_info",
        "description": "Get details of a specific pipeline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pipeline_name": {"type": "string", "description": "Pipeline name"}
            },
            "required": ["pipeline_name"]
        }
    },
    
    # === SOURCE MANAGEMENT ===
    {
        "name": "indexer_source_register",
        "description": "Register a data source for recurring indexing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Source name"},
                "type": {"type": "string", "enum": ["file", "directory", "api", "stream"], "description": "Source type"},
                "path": {"type": "string", "description": "Path or URL"},
                "pipeline": {"type": "string", "description": "Default pipeline"},
                "target_tier": {"type": "string", "enum": ["c1", "c2", "c3"], "description": "Target tier"}
            },
            "required": ["name", "type", "path"]
        }
    },
    {
        "name": "indexer_source_list",
        "description": "List registered data sources.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    
    # === DLQ (Dead Letter Queue) ===
    {
        "name": "indexer_dlq_list",
        "description": "List records in the dead letter queue.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Filter by job ID"},
                "limit": {"type": "integer", "default": 50, "description": "Max records"}
            }
        }
    },
    {
        "name": "indexer_dlq_retry",
        "description": "Retry failed records from DLQ.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID to retry DLQ records for"}
            },
            "required": ["job_id"]
        }
    },
]


class IndexerMCPHandler:
    """Handler for indexer MCP tools"""
    
    # Built-in pipelines
    PIPELINES = {
        "breach": BREACH_PIPELINE,
        "content": CONTENT_PIPELINE,
        "entity": ENTITY_PIPELINE,
    }
    
    def __init__(self, es_client):
        self.es = es_client
        self.job_manager = JobManager(es_client)
        self.schema_registry = SchemaRegistry(es_client)
        self._running_jobs: Dict[str, PipelineEngine] = {}
    
    async def handle(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle an indexer tool call"""
        
        # === JOB MANAGEMENT ===
        if name == "indexer_job_create":
            return await self._job_create(args)
        elif name == "indexer_job_start":
            return await self._job_start(args)
        elif name == "indexer_job_status":
            return await self._job_status(args)
        elif name == "indexer_job_list":
            return await self._job_list(args)
        elif name == "indexer_job_pause":
            return await self._job_pause(args)
        elif name == "indexer_job_resume":
            return await self._job_resume(args)
        elif name == "indexer_job_cancel":
            return await self._job_cancel(args)
        
        # === SCHEMA & TIER INFO ===
        elif name == "indexer_tier_info":
            return self._tier_info(args)
        elif name == "indexer_schema_info":
            return self._schema_info(args)
        
        # === QUICK INDEXING ===
        elif name == "indexer_quick":
            return await self._quick_index(args)
        
        # === PIPELINE MANAGEMENT ===
        elif name == "indexer_pipeline_list":
            return self._pipeline_list()
        elif name == "indexer_pipeline_info":
            return self._pipeline_info(args)
        
        # === SOURCE MANAGEMENT ===
        elif name == "indexer_source_register":
            return await self._source_register(args)
        elif name == "indexer_source_list":
            return await self._source_list()
        
        # === DLQ ===
        elif name == "indexer_dlq_list":
            return await self._dlq_list(args)
        elif name == "indexer_dlq_retry":
            return await self._dlq_retry(args)
        
        return {"error": f"Unknown indexer tool: {name}"}
    
    # === JOB HANDLERS ===
    
    async def _job_create(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new indexing job"""
        job = await self.job_manager.create_job({
            "source_type": args["source_type"],
            "source_path": args["source_path"],
            "target_index": args["target_index"],
            "pipeline": args.get("pipeline", "default"),
            "options": {"batch_size": args.get("batch_size", 1000)},
        })
        return {
            "job_id": job.job_id,
            "status": job.status.value,
            "source_path": job.source_path,
            "target_index": job.target_index,
            "created_at": job.created_at.isoformat(),
        }
    
    async def _job_start(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Start an indexing job"""
        job_id = args["job_id"]
        job = await self.job_manager.get_job(job_id)
        
        if not job:
            return {"error": f"Job not found: {job_id}"}
        
        # Get pipeline config
        pipeline_name = job.pipeline or "default"
        pipeline_config = self.PIPELINES.get(pipeline_name)
        
        if not pipeline_config:
            # Create default pipeline
            from .pipeline.config import PipelineConfig, OutputConfig, OutputMode
            pipeline_config = PipelineConfig(
                name=pipeline_name,
                reader_type=job.source_type,
                output=OutputConfig(
                    index=job.target_index,
                    mode=OutputMode.INDEX,
                    batch_size=job.config.get("batch_size", 1000),
                ),
            )
        else:
            # Update output index
            pipeline_config.output.index = job.target_index
        
        # Create engine and start in background
        engine = PipelineEngine(self.es, pipeline_config, job)
        self._running_jobs[job_id] = engine
        
        # Update job status
        await self.job_manager.start_job(job_id)
        
        # Run async
        asyncio.create_task(self._run_job(job_id, engine, job.source_path))
        
        return {
            "job_id": job_id,
            "status": "running",
            "message": "Job started in background",
        }
    
    async def _run_job(self, job_id: str, engine: PipelineEngine, source_path: str):
        """Run job in background"""
        try:
            stats = await engine.run(source_path)
            await self.job_manager.complete_job(
                job_id,
                stats.total_indexed,
                stats.total_errors,
            )
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            await self.job_manager.fail_job(job_id, str(e))
        finally:
            self._running_jobs.pop(job_id, None)
    
    async def _job_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get job status"""
        job = await self.job_manager.get_job(args["job_id"])
        if not job:
            return {"error": "Job not found"}
        return job.to_dict()
    
    async def _job_list(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """List jobs"""
        status = args.get("status")
        limit = args.get("limit", 20)
        
        jobs = await self.job_manager.list_jobs(
            status=JobStatus(status) if status else None,
            limit=limit,
        )
        
        return {
            "count": len(jobs),
            "jobs": [j.to_dict() for j in jobs],
        }
    
    async def _job_pause(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Pause a job"""
        job_id = args["job_id"]
        engine = self._running_jobs.get(job_id)
        
        if engine:
            engine.stop()
        
        await self.job_manager.pause_job(job_id)
        return {"job_id": job_id, "status": "paused"}
    
    async def _job_resume(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Resume a paused job"""
        job_id = args["job_id"]
        job = await self.job_manager.get_job(job_id)
        
        if not job or job.status != JobStatus.PAUSED:
            return {"error": "Job not found or not paused"}
        
        # Get checkpoint
        checkpoint = await self.job_manager.get_checkpoint(job_id)
        resume_offset = checkpoint.get("records_processed", 0) if checkpoint else 0
        
        # Restart with resume
        await self.job_manager.resume_job(job_id)
        
        # Similar to start but with offset
        pipeline_config = self.PIPELINES.get(job.pipeline) or PipelineConfig(
            name=job.pipeline or "default",
            reader_type=job.source_type,
        )
        pipeline_config.output.index = job.target_index
        
        engine = PipelineEngine(self.es, pipeline_config, job)
        self._running_jobs[job_id] = engine
        
        asyncio.create_task(self._run_job_with_resume(job_id, engine, job.source_path, resume_offset))
        
        return {
            "job_id": job_id,
            "status": "running",
            "resumed_from": resume_offset,
        }
    
    async def _run_job_with_resume(self, job_id: str, engine: PipelineEngine, source_path: str, offset: int):
        """Run job with resume from offset"""
        try:
            stats = await engine.run(source_path, resume_from=offset)
            await self.job_manager.complete_job(job_id, stats.total_indexed, stats.total_errors)
        except Exception as e:
            await self.job_manager.fail_job(job_id, str(e))
        finally:
            self._running_jobs.pop(job_id, None)
    
    async def _job_cancel(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel a job"""
        job_id = args["job_id"]
        engine = self._running_jobs.get(job_id)
        
        if engine:
            engine.stop()
        
        await self.job_manager.cancel_job(job_id)
        return {"job_id": job_id, "status": "cancelled"}
    
    # === TIER & SCHEMA INFO ===
    
    def _tier_info(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get tier information"""
        tier = args.get("tier", "all")
        
        if tier == "all":
            return self.schema_registry.to_dict()
        
        try:
            tier_enum = Tier(tier)
            config = self.schema_registry.get_tier_config(tier_enum)
            return {
                "tier": tier,
                "alias": config.alias,
                "underlying_indices": config.underlying_indices,
                "description": config.description,
                "data_types": [dt.value for dt in config.data_types],
            }
        except ValueError:
            return {"error": f"Unknown tier: {tier}"}
    
    def _schema_info(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get schema information"""
        try:
            data_type = DataType(args["data_type"])
            schema = self.schema_registry.get_schema(data_type)
            if schema:
                return {
                    "data_type": data_type.value,
                    "tier": schema.tier.value,
                    "index_pattern": schema.index_pattern,
                    "doc_id_field": schema.doc_id_field,
                    "mapping": schema.mapping,
                }
            return {"error": "Schema not found"}
        except ValueError:
            return {"error": f"Unknown data type: {args.get('data_type')}"}
    
    # === QUICK INDEXING ===
    
    async def _quick_index(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Quick one-shot indexing"""
        source_path = args["source_path"]
        target_tier = args.get("target_tier", "c2")
        data_type = args.get("data_type", "content")
        
        # Determine target index based on tier and type
        if target_tier == "c2":
            target_index = "cymonides-2"
            pipeline_name = "content"
        elif target_tier == "c3":
            if data_type == "breach":
                target_index = "breach_compilation"
                pipeline_name = "breach"
            else:
                # Route to correct {entity}_unified index
                entity_index_map = {
                    "person": "persons_unified",
                    "company": "companies_unified",
                    "domain": "domains_unified",
                    "email": "emails_unified",
                    "phone": "phones_unified",
                    "location": "locations_unified",
                }
                target_index = entity_index_map.get(data_type, "persons_unified")
                pipeline_name = "entity"
        else:
            target_index = args.get("target_index", "cymonides-2")
            pipeline_name = "content"
        
        # Auto-detect source type from extension
        source_type = "jsonl"
        if source_path.endswith('.parquet'):
            source_type = "parquet"
        elif source_path.endswith('.csv'):
            source_type = "csv"
        elif 'breach' in source_path.lower() or 'combo' in source_path.lower():
            source_type = "breach"
            pipeline_name = "breach"
        
        # Create and run job
        job = await self.job_manager.create_job(
            source_type=source_type,
            source_path=source_path,
            target_index=target_index,
            pipeline=pipeline_name,
        )
        
        # Run synchronously for quick index
        pipeline_config = self.PIPELINES.get(pipeline_name, CONTENT_PIPELINE)
        pipeline_config.output.index = target_index
        
        engine = PipelineEngine(self.es, pipeline_config, job)
        
        await self.job_manager.start_job(job.job_id)
        
        try:
            stats = await engine.run(source_path)
            await self.job_manager.complete_job(job.job_id, stats.total_indexed, stats.total_errors)
            
            return {
                "job_id": job.job_id,
                "status": "completed",
                "target_index": target_index,
                "stats": stats.to_dict(),
            }
        except Exception as e:
            await self.job_manager.fail_job(job.job_id, str(e))
            return {"job_id": job.job_id, "status": "failed", "error": str(e)}
    
    # === PIPELINE MANAGEMENT ===
    
    def _pipeline_list(self) -> Dict[str, Any]:
        """List available pipelines"""
        return {
            "pipelines": [
                {
                    "name": name,
                    "description": config.description,
                    "reader_type": config.reader_type,
                    "stages": len(config.stages),
                }
                for name, config in self.PIPELINES.items()
            ]
        }
    
    def _pipeline_info(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get pipeline details"""
        name = args["pipeline_name"]
        config = self.PIPELINES.get(name)
        
        if not config:
            return {"error": f"Pipeline not found: {name}"}
        
        return config.to_dict()
    
    # === SOURCE MANAGEMENT ===
    
    async def _source_register(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Register a data source"""
        # Store in ES
        source_doc = {
            "name": args["name"],
            "type": args["type"],
            "path": args["path"],
            "pipeline": args.get("pipeline", "default"),
            "target_tier": args.get("target_tier", "c2"),
            "registered_at": datetime.utcnow().isoformat(),
            "last_sync": None,
            "sync_cursor": {},
        }
        
        await self.es.index(
            index="cymonides-sources",
            id=args["name"],
            document=source_doc,
        )
        
        return {"source_id": args["name"], "registered": True}
    
    async def _source_list(self) -> Dict[str, Any]:
        """List registered sources"""
        try:
            resp = await self.es.search(
                index="cymonides-sources",
                query={"match_all": {}},
                size=100,
            )
            sources = [h["_source"] for h in resp["hits"]["hits"]]
            return {"count": len(sources), "sources": sources}
        except Exception:
            return {"count": 0, "sources": []}
    
    # === DLQ ===
    
    async def _dlq_list(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """List DLQ records"""
        query = {"match_all": {}}
        if args.get("job_id"):
            query = {"term": {"job_id": args["job_id"]}}
        
        try:
            resp = await self.es.search(
                index="cymonides-dlq",
                query=query,
                size=args.get("limit", 50),
            )
            records = [h["_source"] for h in resp["hits"]["hits"]]
            return {"count": len(records), "records": records}
        except Exception:
            return {"count": 0, "records": []}
    
    async def _dlq_retry(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Retry DLQ records"""
        # This would re-queue DLQ records for processing
        return {"message": "DLQ retry not yet implemented", "job_id": args["job_id"]}


def get_indexer_tools() -> List[Dict[str, Any]]:
    """Get tool definitions for MCP registration"""
    return INDEXER_TOOLS


def create_indexer_handler(es_client) -> IndexerMCPHandler:
    """Create indexer handler instance"""
    return IndexerMCPHandler(es_client)
