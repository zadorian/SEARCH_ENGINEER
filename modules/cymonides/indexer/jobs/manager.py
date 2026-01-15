"""
JobManager - Central registry for all indexing jobs.

Persists jobs to Elasticsearch for durability and queryability.
Supports checkpointing, resume, and lifecycle management.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from elasticsearch import Elasticsearch, NotFoundError
from elasticsearch.helpers import bulk

from ..core.job import IndexingJob, JobStatus, JobProgress, JobCheckpoint

logger = logging.getLogger("cymonides.indexer.jobs")


class JobManager:
    """
    Central registry for all indexing jobs.
    
    Features:
    - ES-backed persistence
    - Checkpointing for resume
    - Progress tracking
    - Job lifecycle management
    """
    
    JOBS_INDEX = "cymonides-jobs"
    JOBS_DIR = Path("/data/CYMONIDES/jobs")
    
    # Index mapping for jobs
    JOBS_MAPPING = {
        "properties": {
            "job_id": {"type": "keyword"},
            "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "status": {"type": "keyword"},
            "source_id": {"type": "keyword"},
            "source_type": {"type": "keyword"},
            "source_path": {"type": "keyword"},
            "target_index": {"type": "keyword"},
            "target_tier": {"type": "keyword"},
            "pipeline": {"type": "keyword"},
            "pipeline_version": {"type": "keyword"},
            "progress": {"type": "object"},
            "checkpoint": {"type": "object"},
            "created_at": {"type": "date"},
            "started_at": {"type": "date"},
            "completed_at": {"type": "date"},
            "duration_seconds": {"type": "float"},
            "error_count": {"type": "integer"},
            "last_error": {"type": "text"},
            "dlq_count": {"type": "integer"},
            "created_by": {"type": "keyword"},
            "tags": {"type": "keyword"},
        }
    }
    
    def __init__(self, es: Elasticsearch):
        self.es = es
        self._active_jobs: Dict[str, IndexingJob] = {}
        self._index_ensured = False
        self.JOBS_DIR.mkdir(parents=True, exist_ok=True)
        
    async def _ensure_index(self):
        """Ensure jobs index exists."""
        if self._index_ensured:
            return
        if not await self.es.indices.exists(index=self.JOBS_INDEX):
            await self.es.indices.create(
                index=self.JOBS_INDEX,
                mappings=self.JOBS_MAPPING,
                settings={
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                }
            )
            self._index_ensured = True
            logger.info(f"Created jobs index: {self.JOBS_INDEX}")
            
    async def create_job(self, config: Dict[str, Any]) -> IndexingJob:
        """Create and register a new indexing job."""
        await self._ensure_index()
        options = config.get("options", {})
        
        job = IndexingJob(
            name=config.get("name"),
            source_id=config.get("source_id"),
            source_type=config.get("source_type", "file"),
            source_path=config.get("source_path", ""),
            source_config=config.get("source_config", {}),
            target_index=config.get("target_index", ""),
            target_tier=config.get("target_tier", "c2"),
            pipeline=config.get("pipeline", "content"),
            pipeline_config=config.get("pipeline_config", {}),
            batch_size=options.get("batch_size", 100),
            checkpoint_every=options.get("checkpoint_every", 1000),
            dedup_enabled=options.get("dedup_enabled", True),
            dedup_field=options.get("dedup_field", "content_hash"),
            extract_entities=options.get("extract_entities", False),
            link_entities=options.get("link_entities", False),
            run_async=options.get("run_async", True),
            created_by=config.get("created_by", "system"),
            tags=config.get("tags", []),
            metadata=config.get("metadata", {}),
        )
        
        # Determine target tier from index name if not specified
        if not job.target_tier:
            if job.target_index.startswith("cymonides-1-"):
                job.target_tier = "c1"
            elif job.target_index == "cymonides-2":
                job.target_tier = "c2"
            elif job.target_index in ["cymonides-3", "atlas", "domains_unified", "companies_unified", "persons_unified"]:
                job.target_tier = "c3"
                
        # Save to ES
        await self._save_job(job)
        
        logger.info(f"Created job {job.job_id}: {job.source_type} -> {job.target_index}")
        return job
    
    async def start_job(self, job_id: str) -> IndexingJob:
        """
        Start executing a job.
        
        Args:
            job_id: Job ID to start
            
        Returns:
            Updated job
        """
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
            
        if job.status not in [JobStatus.PENDING, JobStatus.PAUSED]:
            raise ValueError(f"Cannot start job in status: {job.status.value}")
            
        job.start()
        self._active_jobs[job_id] = job
        await self._save_job(job)
        
        logger.info(f"Started job {job_id}")
        return job
    
    async def pause_job(self, job_id: str) -> IndexingJob:
        """
        Pause a running job with checkpoint.
        
        Args:
            job_id: Job ID to pause
            
        Returns:
            Updated job
        """
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
            
        if job.status != JobStatus.RUNNING:
            raise ValueError(f"Cannot pause job in status: {job.status.value}")
            
        job.pause()
        await self._save_job(job)
        await self._save_checkpoint_file(job)
        
        # Remove from active
        self._active_jobs.pop(job_id, None)
        
        logger.info(f"Paused job {job_id} at offset {job.checkpoint.last_offset if job.checkpoint else 0}")
        return job
    
    async def resume_job(self, job_id: str, from_checkpoint: bool = True) -> IndexingJob:
        """
        Resume a paused or failed job.
        
        Args:
            job_id: Job ID to resume
            from_checkpoint: If True, resume from checkpoint. If False, restart.
            
        Returns:
            Updated job
        """
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
            
        if job.status not in [JobStatus.PAUSED, JobStatus.FAILED]:
            raise ValueError(f"Cannot resume job in status: {job.status.value}")
            
        if not from_checkpoint:
            # Reset progress
            job.progress = JobProgress()
            job.checkpoint = None
            job.errors = []
        else:
            # Load checkpoint from file if exists
            checkpoint = await self._load_checkpoint_file(job_id)
            if checkpoint:
                job.checkpoint = checkpoint
                
        job.resume()
        self._active_jobs[job_id] = job
        await self._save_job(job)
        
        offset = job.checkpoint.last_offset if job.checkpoint else 0
        logger.info(f"Resumed job {job_id} from offset {offset}")
        return job
    
    async def cancel_job(self, job_id: str, rollback: bool = False, reason: str = "") -> IndexingJob:
        """
        Cancel an indexing job.
        
        Args:
            job_id: Job ID to cancel
            rollback: If True, delete documents indexed by this job
            reason: Cancellation reason
            
        Returns:
            Updated job
        """
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
            
        if job.is_finished:
            raise ValueError(f"Cannot cancel finished job: {job.status.value}")
            
        job.cancel(reason)
        await self._save_job(job)
        
        # Remove from active
        self._active_jobs.pop(job_id, None)
        
        if rollback and job.progress.indexed > 0:
            # Delete documents indexed by this job
            await self._rollback_job(job)
            
        logger.info(f"Cancelled job {job_id}" + (f" with rollback" if rollback else ""))
        return job
    
    async def complete_job(self, job_id: str, summary: Dict[str, Any] = None) -> IndexingJob:
        """Mark job as completed."""
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
            
        job.complete(summary)
        await self._save_job(job)
        
        # Remove from active
        self._active_jobs.pop(job_id, None)
        
        # Clean up checkpoint file
        checkpoint_file = self.JOBS_DIR / f"{job_id}.checkpoint"
        if checkpoint_file.exists():
            checkpoint_file.unlink()
            
        logger.info(f"Completed job {job_id}: {job.progress.indexed} indexed, {job.progress.failed} failed")
        return job
    
    async def fail_job(self, job_id: str, error: str) -> IndexingJob:
        """Mark job as failed."""
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
            
        job.fail(error)
        await self._save_job(job)
        
        # Save checkpoint for potential resume
        await self._save_checkpoint_file(job)
        
        # Remove from active
        self._active_jobs.pop(job_id, None)
        
        logger.error(f"Failed job {job_id}: {error}")
        return job
    
    async def update_progress(
        self,
        job_id: str,
        indexed: int = 0,
        failed: int = 0,
        deduped: int = 0,
        skipped: int = 0,
        total: int = None
    ) -> IndexingJob:
        """Update job progress."""
        job = self._active_jobs.get(job_id)
        if not job:
            job = await self.get_job(job_id)
            if job:
                self._active_jobs[job_id] = job
                
        if not job:
            raise ValueError(f"Job not found: {job_id}")
            
        if total is not None:
            job.progress.total = total
            
        job.progress.update(indexed=indexed, failed=failed, deduped=deduped, skipped=skipped)
        
        # Save checkpoint periodically
        if job.progress.processed % job.checkpoint_every == 0:
            job.save_checkpoint(
                offset=job.progress.processed,
                doc_id=None,
                cursor={}
            )
            await self._save_checkpoint_file(job)
            
        # Persist progress periodically (every 10 batches)
        if job.progress.processed % (job.batch_size * 10) == 0:
            await self._save_job(job)
            
        return job
    
    async def get_job(self, job_id: str) -> Optional[IndexingJob]:
        """Get job by ID."""
        # Check active jobs first
        if job_id in self._active_jobs:
            return self._active_jobs[job_id]
            
        # Load from ES
        try:
            resp = await self.es.get(index=self.JOBS_INDEX, id=job_id)
            return IndexingJob.from_dict(resp["_source"])
        except NotFoundError:
            return None
    
    async def list_jobs(
        self,
        status: str = "all",
        target_index: str = None,
        pipeline: str = None,
        limit: int = 50,
        include_completed: bool = False
    ) -> List[IndexingJob]:
        """
        List jobs with optional filtering.
        
        Args:
            status: Filter by status (all, pending, running, paused, completed, failed)
            target_index: Filter by target index
            pipeline: Filter by pipeline
            limit: Max results
            include_completed: Include completed jobs
            
        Returns:
            List of jobs
        """
        query = {"bool": {"must": []}}
        
        if status != "all":
            query["bool"]["must"].append({"term": {"status": status}})
        elif not include_completed:
            query["bool"]["must_not"] = [
                {"terms": {"status": ["completed", "cancelled"]}}
            ]
            
        if target_index:
            query["bool"]["must"].append({"term": {"target_index": target_index}})
            
        if pipeline:
            query["bool"]["must"].append({"term": {"pipeline": pipeline}})
            
        if not query["bool"]["must"]:
            query = {"match_all": {}}
            
        resp = await self.es.search(
            index=self.JOBS_INDEX,
            query=query,
            sort=[{"created_at": "desc"}],
            size=limit
        )
        
        return [IndexingJob.from_dict(hit["_source"]) for hit in resp["hits"]["hits"]]
    
    async def get_active_jobs(self) -> List[IndexingJob]:
        """Get all currently running jobs."""
        return list(self._active_jobs.values())
    
    async def get_job_stats(self) -> Dict[str, Any]:
        """Get aggregate job statistics."""
        resp = await self.es.search(
            index=self.JOBS_INDEX,
            size=0,
            aggs={
                "by_status": {"terms": {"field": "status"}},
                "by_pipeline": {"terms": {"field": "pipeline"}},
                "by_target": {"terms": {"field": "target_index", "size": 20}},
                "total_indexed": {"sum": {"field": "progress.indexed"}},
                "total_failed": {"sum": {"field": "progress.failed"}},
                "avg_duration": {"avg": {"field": "duration_seconds"}},
            }
        )
        
        aggs = resp.get("aggregations", {})
        return {
            "total_jobs": resp["hits"]["total"]["value"],
            "by_status": {b["key"]: b["doc_count"] for b in aggs.get("by_status", {}).get("buckets", [])},
            "by_pipeline": {b["key"]: b["doc_count"] for b in aggs.get("by_pipeline", {}).get("buckets", [])},
            "by_target": {b["key"]: b["doc_count"] for b in aggs.get("by_target", {}).get("buckets", [])},
            "total_docs_indexed": int(aggs.get("total_indexed", {}).get("value", 0)),
            "total_docs_failed": int(aggs.get("total_failed", {}).get("value", 0)),
            "avg_duration_seconds": aggs.get("avg_duration", {}).get("value"),
            "active_jobs": len(self._active_jobs),
        }
    
    async def _save_job(self, job: IndexingJob):
        """Save job to ES."""
        await self.es.index(
            index=self.JOBS_INDEX,
            id=job.job_id,
            document=job.to_dict(),
            refresh=True
        )
        
    async def _save_checkpoint_file(self, job: IndexingJob):
        """Save checkpoint to file for crash recovery."""
        if not job.checkpoint:
            return
            
        checkpoint_file = self.JOBS_DIR / f"{job.job_id}.checkpoint"
        with open(checkpoint_file, "w") as f:
            json.dump({
                "job_id": job.job_id,
                "checkpoint": job.checkpoint.to_dict(),
                "progress": job.progress.to_dict(),
            }, f, indent=2)
            
    async def _load_checkpoint_file(self, job_id: str) -> Optional[JobCheckpoint]:
        """Load checkpoint from file."""
        checkpoint_file = self.JOBS_DIR / f"{job_id}.checkpoint"
        if not checkpoint_file.exists():
            return None
            
        with open(checkpoint_file) as f:
            data = json.load(f)
            return JobCheckpoint.from_dict(data.get("checkpoint", {}))
            
    async def _rollback_job(self, job: IndexingJob):
        """Delete documents indexed by this job."""
        try:
            # Delete by job_id metadata field
            self.es.delete_by_query(
                index=job.target_index,
                query={"term": {"_meta.job_id": job.job_id}},
                refresh=True
            )
            logger.info(f"Rolled back {job.progress.indexed} docs from {job.target_index}")
        except Exception as e:
            logger.error(f"Rollback failed for job {job.job_id}: {e}")
