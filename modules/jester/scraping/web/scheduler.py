"""
LinkLater DRILL Scheduler - Alert-Triggered Crawl Jobs

Provides a simple job queue that can be triggered by alerts for automatic re-crawling.

When an alert detects significant changes (entity removal, content changes, etc.),
it can trigger a re-crawl to capture fresh content.

Usage:
    scheduler = DrillScheduler()

    # Queue a crawl job
    job_id = await scheduler.queue_crawl(
        domain="example.com",
        trigger_source="alert",
        trigger_id="abc123",
        priority=2,  # Higher = more urgent
    )

    # Process pending jobs
    await scheduler.process_pending_jobs(max_jobs=5)

    # Check job status
    job = await scheduler.get_job(job_id)
"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum
from elasticsearch import Elasticsearch


class JobStatus(Enum):
    """Crawl job status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(Enum):
    """Job priority levels."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class CrawlJob:
    """Represents a scheduled crawl job."""
    job_id: str
    domain: str
    seed_urls: List[str] = field(default_factory=list)

    # Job metadata
    status: str = JobStatus.PENDING.value
    priority: int = JobPriority.NORMAL.value

    # Trigger info (what caused this job)
    trigger_source: str = "manual"  # manual, alert, discovery, scheduled
    trigger_id: Optional[str] = None  # Alert ID or other trigger reference
    trigger_details: Dict[str, Any] = field(default_factory=dict)

    # Timing
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Results
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    # Crawl config overrides
    max_pages: int = 100
    max_concurrent: int = 10

    def __post_init__(self):
        if not self.job_id:
            import hashlib
            self.job_id = hashlib.md5(
                f"{self.domain}:{self.trigger_source}:{self.created_at}".encode()
            ).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "domain": self.domain,
            "seed_urls": self.seed_urls,
            "status": self.status,
            "priority": self.priority,
            "trigger_source": self.trigger_source,
            "trigger_id": self.trigger_id,
            "trigger_details": self.trigger_details,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "max_pages": self.max_pages,
            "max_concurrent": self.max_concurrent,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrawlJob":
        return cls(
            job_id=data.get("job_id", ""),
            domain=data.get("domain", ""),
            seed_urls=data.get("seed_urls", []),
            status=data.get("status", JobStatus.PENDING.value),
            priority=data.get("priority", JobPriority.NORMAL.value),
            trigger_source=data.get("trigger_source", "manual"),
            trigger_id=data.get("trigger_id"),
            trigger_details=data.get("trigger_details", {}),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            result=data.get("result"),
            error=data.get("error"),
            max_pages=data.get("max_pages", 100),
            max_concurrent=data.get("max_concurrent", 10),
        )


class DrillScheduler:
    """
    Simple job scheduler for DRILL crawler.

    Stores jobs in Elasticsearch and processes them on-demand or via background worker.
    """

    INDEX_NAME = "drill_crawl_jobs"

    INDEX_MAPPING = {
        "mappings": {
            "properties": {
                "job_id": {"type": "keyword"},
                "domain": {"type": "keyword"},
                "seed_urls": {"type": "keyword"},
                "status": {"type": "keyword"},
                "priority": {"type": "integer"},
                "trigger_source": {"type": "keyword"},
                "trigger_id": {"type": "keyword"},
                "trigger_details": {"type": "object", "enabled": False},
                "created_at": {"type": "date"},
                "started_at": {"type": "date"},
                "completed_at": {"type": "date"},
                "result": {"type": "object", "enabled": False},
                "error": {"type": "text"},
                "max_pages": {"type": "integer"},
                "max_concurrent": {"type": "integer"},
            }
        },
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
    }

    def __init__(self, elasticsearch_url: Optional[str] = None):
        self.es_url = elasticsearch_url or os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
        self.es = Elasticsearch([self.es_url])
        self._crawler = None

    @property
    def crawler(self):
        """Lazy load DRILL crawler."""
        if self._crawler is None:
            try:
                from .crawler import Drill, DrillConfig
                self._crawler = (Drill, DrillConfig)
            except ImportError as e:
                print(f"[DrillScheduler] Could not import crawler: {e}")
        return self._crawler

    def ensure_index(self):
        """Create jobs index if it doesn't exist."""
        if not self.es.indices.exists(index=self.INDEX_NAME):
            self.es.indices.create(index=self.INDEX_NAME, body=self.INDEX_MAPPING)
            print(f"[DrillScheduler] Created index: {self.INDEX_NAME}")

    async def queue_crawl(
        self,
        domain: str,
        seed_urls: Optional[List[str]] = None,
        trigger_source: str = "manual",
        trigger_id: Optional[str] = None,
        trigger_details: Optional[Dict[str, Any]] = None,
        priority: int = JobPriority.NORMAL.value,
        max_pages: int = 100,
        max_concurrent: int = 10,
    ) -> str:
        """
        Queue a crawl job.

        Args:
            domain: Target domain to crawl
            seed_urls: Optional seed URLs (if not provided, discovery runs)
            trigger_source: What triggered this job (manual, alert, discovery, scheduled)
            trigger_id: Reference to triggering alert/event
            trigger_details: Additional context about the trigger
            priority: Job priority (0=low, 3=urgent)
            max_pages: Max pages to crawl
            max_concurrent: Concurrent requests

        Returns:
            Job ID
        """
        self.ensure_index()

        job = CrawlJob(
            job_id="",  # Will be generated
            domain=domain,
            seed_urls=seed_urls or [],
            trigger_source=trigger_source,
            trigger_id=trigger_id,
            trigger_details=trigger_details or {},
            priority=priority,
            max_pages=max_pages,
            max_concurrent=max_concurrent,
        )

        # Store to Elasticsearch
        self.es.index(
            index=self.INDEX_NAME,
            id=job.job_id,
            document=job.to_dict(),
            refresh=True,
        )

        print(f"[DrillScheduler] Queued job {job.job_id} for {domain} (source={trigger_source}, priority={priority})")
        return job.job_id

    async def queue_from_alert(
        self,
        alert_id: str,
        alert_type: str,
        source_domain: str,
        target_domain: Optional[str] = None,
        alert_details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Queue a re-crawl triggered by an alert.

        This is called by LinkAlertService when significant alerts are triggered.

        Args:
            alert_id: ID of the triggering alert
            alert_type: Type of alert (archive_entity_removed, etc.)
            source_domain: Domain from the alert (what to crawl)
            target_domain: Optional target domain from alert
            alert_details: Full alert details

        Returns:
            Job ID
        """
        # Determine priority based on alert type
        priority = JobPriority.NORMAL.value

        high_priority_alerts = [
            "archive_entity_removed",  # Entity scrubbing - investigate quickly
            "velocity_spike",  # Unusual activity
        ]

        if alert_type in high_priority_alerts:
            priority = JobPriority.HIGH.value

        # Determine what to crawl
        domain_to_crawl = source_domain
        seed_urls = []

        # If we have a specific URL from the alert, use it
        if alert_details:
            url = alert_details.get("url")
            if url:
                seed_urls = [url]

        return await self.queue_crawl(
            domain=domain_to_crawl,
            seed_urls=seed_urls,
            trigger_source="alert",
            trigger_id=alert_id,
            trigger_details={
                "alert_type": alert_type,
                "source_domain": source_domain,
                "target_domain": target_domain,
                **(alert_details or {}),
            },
            priority=priority,
            max_pages=50,  # Focused re-crawl
            max_concurrent=5,
        )

    async def get_job(self, job_id: str) -> Optional[CrawlJob]:
        """Get a job by ID."""
        try:
            result = self.es.get(index=self.INDEX_NAME, id=job_id)
            return CrawlJob.from_dict(result["_source"])
        except Exception:
            return None

    async def get_pending_jobs(
        self,
        limit: int = 10,
        min_priority: int = 0,
    ) -> List[CrawlJob]:
        """
        Get pending jobs ordered by priority (highest first), then age (oldest first).
        """
        try:
            result = self.es.search(
                index=self.INDEX_NAME,
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"status": JobStatus.PENDING.value}},
                                {"range": {"priority": {"gte": min_priority}}},
                            ]
                        }
                    },
                    "sort": [
                        {"priority": {"order": "desc"}},
                        {"created_at": {"order": "asc"}},
                    ],
                    "size": limit,
                }
            )

            return [
                CrawlJob.from_dict(hit["_source"])
                for hit in result["hits"]["hits"]
            ]
        except Exception as e:
            print(f"[DrillScheduler] Error getting pending jobs: {e}")
            return []

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        """Update job status."""
        update_body = {
            "status": status.value,
        }

        if status == JobStatus.RUNNING:
            update_body["started_at"] = datetime.utcnow().isoformat()
        elif status in (JobStatus.COMPLETED, JobStatus.FAILED):
            update_body["completed_at"] = datetime.utcnow().isoformat()
            if result:
                update_body["result"] = result
            if error:
                update_body["error"] = error

        try:
            self.es.update(
                index=self.INDEX_NAME,
                id=job_id,
                body={"doc": update_body},
                refresh=True,
            )
        except Exception as e:
            print(f"[DrillScheduler] Error updating job {job_id}: {e}")

    async def run_job(self, job: CrawlJob) -> Dict[str, Any]:
        """
        Execute a single crawl job.

        Returns:
            CrawlStats as dict
        """
        if not self.crawler:
            raise RuntimeError("DRILL crawler not available")

        Drill, DrillConfig = self.crawler

        # Mark as running
        await self.update_job_status(job.job_id, JobStatus.RUNNING)

        try:
            # Create crawler with job config
            config = DrillConfig(
                max_pages=job.max_pages,
                max_concurrent=job.max_concurrent,
                index_to_elasticsearch=True,
                extract_entities=True,
            )

            crawler = Drill(config)

            # Run crawl
            if job.seed_urls:
                stats = await crawler.crawl(job.domain, seed_urls=job.seed_urls)
            else:
                stats = await crawler.crawl(job.domain)

            result = stats.to_dict()

            # Mark completed
            await self.update_job_status(
                job.job_id,
                JobStatus.COMPLETED,
                result=result,
            )

            print(f"[DrillScheduler] Job {job.job_id} completed: {stats.pages_crawled} pages")
            return result

        except Exception as e:
            # Mark failed
            await self.update_job_status(
                job.job_id,
                JobStatus.FAILED,
                error=str(e),
            )
            print(f"[DrillScheduler] Job {job.job_id} failed: {e}")
            raise

    async def process_pending_jobs(
        self,
        max_jobs: int = 5,
        min_priority: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Process pending jobs from the queue.

        Args:
            max_jobs: Maximum jobs to process in this batch
            min_priority: Only process jobs with priority >= this value

        Returns:
            List of job results
        """
        jobs = await self.get_pending_jobs(limit=max_jobs, min_priority=min_priority)

        if not jobs:
            print("[DrillScheduler] No pending jobs")
            return []

        print(f"[DrillScheduler] Processing {len(jobs)} pending jobs")

        results = []
        for job in jobs:
            try:
                result = await self.run_job(job)
                results.append({
                    "job_id": job.job_id,
                    "status": "completed",
                    "result": result,
                })
            except Exception as e:
                results.append({
                    "job_id": job.job_id,
                    "status": "failed",
                    "error": str(e),
                })

        return results

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job."""
        job = await self.get_job(job_id)
        if not job:
            return False

        if job.status != JobStatus.PENDING.value:
            print(f"[DrillScheduler] Cannot cancel job {job_id} in status {job.status}")
            return False

        await self.update_job_status(job_id, JobStatus.CANCELLED)
        return True

    async def get_job_history(
        self,
        domain: Optional[str] = None,
        trigger_source: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[CrawlJob]:
        """Get job history with filters."""
        filters = []

        if domain:
            filters.append({"term": {"domain": domain}})
        if trigger_source:
            filters.append({"term": {"trigger_source": trigger_source}})
        if status:
            filters.append({"term": {"status": status}})

        query = {"match_all": {}} if not filters else {"bool": {"filter": filters}}

        try:
            result = self.es.search(
                index=self.INDEX_NAME,
                body={
                    "query": query,
                    "sort": [{"created_at": {"order": "desc"}}],
                    "size": limit,
                }
            )

            return [
                CrawlJob.from_dict(hit["_source"])
                for hit in result["hits"]["hits"]
            ]
        except Exception as e:
            print(f"[DrillScheduler] Error getting job history: {e}")
            return []


# Convenience functions

async def trigger_recrawl_from_alert(
    alert_id: str,
    alert_type: str,
    source_domain: str,
    target_domain: Optional[str] = None,
    alert_details: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Trigger a re-crawl from an alert.

    This is the main integration point between alerts and the scheduler.
    """
    scheduler = DrillScheduler()
    return await scheduler.queue_from_alert(
        alert_id=alert_id,
        alert_type=alert_type,
        source_domain=source_domain,
        target_domain=target_domain,
        alert_details=alert_details,
    )


async def process_crawl_queue(max_jobs: int = 5) -> List[Dict[str, Any]]:
    """Process pending crawl jobs."""
    scheduler = DrillScheduler()
    return await scheduler.process_pending_jobs(max_jobs=max_jobs)


async def get_crawl_queue_status() -> Dict[str, Any]:
    """Get current queue status."""
    scheduler = DrillScheduler()
    pending = await scheduler.get_pending_jobs(limit=100)

    return {
        "pending_count": len(pending),
        "pending_by_priority": {
            "urgent": len([j for j in pending if j.priority == JobPriority.URGENT.value]),
            "high": len([j for j in pending if j.priority == JobPriority.HIGH.value]),
            "normal": len([j for j in pending if j.priority == JobPriority.NORMAL.value]),
            "low": len([j for j in pending if j.priority == JobPriority.LOW.value]),
        },
        "pending_jobs": [j.to_dict() for j in pending[:10]],  # Show first 10
    }
