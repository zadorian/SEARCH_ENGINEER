"""
LinkLater Link Alerts - Category-Based Alerting

Feature 6: Alert when suspicious link patterns appear.

This module enables:
- Detection of new links to offshore jurisdictions
- Detection of new links to Russia/CIS domains
- Velocity spike alerts (unusual link acquisition rate)
- Automated alert storage and retrieval

Usage:
    service = LinkAlertService()

    # Check for new alerts
    alerts = await service.check_for_alerts("example.com", since_hours=24)

    # Get stored alerts
    all_alerts = await service.get_alerts(severity="high")
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

# Scheduler integration for re-crawl triggering
try:
    from ..scraping.web.scheduler import DrillScheduler, trigger_recrawl_from_alert
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False
    DrillScheduler = None


@dataclass
class LinkAlert:
    """Represents an alert triggered by suspicious link patterns."""
    alert_type: str  # new_offshore, new_russia_cis, velocity_spike, new_entity
    severity: str  # low, medium, high, critical
    source_domain: str
    target_domain: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    alert_id: Optional[str] = None

    def __post_init__(self):
        if not self.alert_id:
            import hashlib
            self.alert_id = hashlib.md5(
                f"{self.alert_type}:{self.source_domain}:{self.target_domain}:{self.created_at}".encode()
            ).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "source_domain": self.source_domain,
            "target_domain": self.target_domain,
            "details": self.details,
            "created_at": self.created_at,
        }


class LinkAlertService:
    """Monitor for suspicious link patterns."""

    INDEX_NAME = "drill_link_alerts"

    INDEX_MAPPING = {
        "mappings": {
            "properties": {
                "alert_id": {"type": "keyword"},
                "alert_type": {"type": "keyword"},
                "severity": {"type": "keyword"},
                "source_domain": {"type": "keyword"},
                "target_domain": {"type": "keyword"},
                "details": {"type": "object", "enabled": False},  # Don't index internals
                "created_at": {"type": "date"},
            }
        },
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
    }

    # Alert rule definitions
    ALERT_RULES = {
        "new_offshore": {
            "categories": ["offshore"],
            "severity": "high",
            "description": "New link to offshore jurisdiction",
        },
        "new_russia_cis": {
            "categories": ["russia_cis"],
            "severity": "medium",
            "description": "New link to Russia/CIS region",
        },
        "new_government": {
            "categories": ["government"],
            "severity": "low",
            "description": "New link to government domain",
        },
        "velocity_spike": {
            "threshold_multiplier": 3.0,
            "severity": "medium",
            "description": "Link velocity 3x above baseline",
        },
        # Archive change alerts (triggered by snapshot_differ)
        "archive_content_change": {
            "min_lines_changed": 10,
            "severity": "low",
            "description": "Significant content change detected in archive",
        },
        "archive_entity_added": {
            "severity": "medium",
            "description": "New entity appeared in archived page",
        },
        "archive_entity_removed": {
            "severity": "high",
            "description": "Entity removed from archived page",
        },
        "archive_links_changed": {
            "min_links_changed": 5,
            "severity": "medium",
            "description": "Significant link changes in archived page",
        },
    }

    def __init__(self, elasticsearch_url: Optional[str] = None):
        self.es_url = elasticsearch_url or os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
        self.es = Elasticsearch([self.es_url])
        self._pipeline = None

    @property
    def pipeline(self):
        """Lazy load link pipeline."""
        if self._pipeline is None:
            try:
                from ..scraping.web.linkpipeline import DrillLinkPipeline
                self._pipeline = DrillLinkPipeline()
            except ImportError:
                pass
        return self._pipeline

    def ensure_index(self):
        """Create alerts index if it doesn't exist."""
        if not self.es.indices.exists(index=self.INDEX_NAME):
            self.es.indices.create(index=self.INDEX_NAME, body=self.INDEX_MAPPING)
            print(f"[LinkAlerts] Created index: {self.INDEX_NAME}")

    async def check_for_alerts(
        self,
        source_domain: str,
        since_hours: int = 24,
    ) -> List[LinkAlert]:
        """
        Check for alert conditions since last check.

        Scans for:
        - New links to offshore domains
        - New links to Russia/CIS domains
        - Velocity spikes

        Args:
            source_domain: Domain to check
            since_hours: Hours to look back

        Returns:
            List of triggered alerts
        """
        self.ensure_index()
        alerts = []

        since_date = (datetime.utcnow() - timedelta(hours=since_hours)).isoformat()

        # Check category-based rules
        for rule_name, rule in self.ALERT_RULES.items():
            if "categories" in rule:
                for category in rule["categories"]:
                    category_alerts = await self._check_category_rule(
                        source_domain=source_domain,
                        category=category,
                        rule_name=rule_name,
                        rule=rule,
                        since_date=since_date,
                    )
                    alerts.extend(category_alerts)

        # Check velocity spike
        velocity_alerts = await self._check_velocity_spike(
            source_domain=source_domain,
            rule=self.ALERT_RULES["velocity_spike"],
            since_hours=since_hours,
        )
        alerts.extend(velocity_alerts)

        # Store alerts
        if alerts:
            await self._store_alerts(alerts)

        return alerts

    async def _check_category_rule(
        self,
        source_domain: str,
        category: str,
        rule_name: str,
        rule: Dict[str, Any],
        since_date: str,
    ) -> List[LinkAlert]:
        """Check for new links in a specific category."""
        alerts = []

        if not self.pipeline:
            return alerts

        try:
            # Query for links in this category with first_seen after since_date
            links = await self.pipeline.query_links_by_age(
                source_domain=source_domain,
                target_category=category,
                first_seen_after=since_date,
                size=100,
            )

            for link in links:
                # Check if we already alerted on this link
                if await self._alert_exists(source_domain, link.get("target_domain"), rule_name):
                    continue

                alerts.append(LinkAlert(
                    alert_type=rule_name,
                    severity=rule["severity"],
                    source_domain=source_domain,
                    target_domain=link.get("target_domain"),
                    details={
                        "link": link,
                        "rule": rule["description"],
                        "category": category,
                    },
                ))

        except Exception as e:
            print(f"[LinkAlerts] Category check failed: {e}")

        return alerts

    async def _check_velocity_spike(
        self,
        source_domain: str,
        rule: Dict[str, Any],
        since_hours: int,
    ) -> List[LinkAlert]:
        """Check for velocity spikes."""
        alerts = []

        if not self.pipeline:
            return alerts

        try:
            # Get current velocity (last N hours)
            current_velocity = await self.pipeline.calculate_link_velocity(
                source_domain=source_domain,
                period_days=max(1, since_hours // 24),
            )

            # Get baseline velocity (previous 30 days)
            baseline_velocity = await self.pipeline.calculate_link_velocity(
                source_domain=source_domain,
                period_days=30,
            )

            current_rate = current_velocity.get("avg_links_per_day", 0)
            baseline_rate = baseline_velocity.get("avg_links_per_day", 0)

            # Check for spike
            threshold = rule.get("threshold_multiplier", 3.0)
            if baseline_rate > 0 and current_rate > baseline_rate * threshold:
                alerts.append(LinkAlert(
                    alert_type="velocity_spike",
                    severity=rule["severity"],
                    source_domain=source_domain,
                    details={
                        "current_rate": current_rate,
                        "baseline_rate": baseline_rate,
                        "spike_multiplier": round(current_rate / baseline_rate, 2),
                        "threshold_multiplier": threshold,
                        "rule": rule["description"],
                    },
                ))

        except Exception as e:
            print(f"[LinkAlerts] Velocity check failed: {e}")

        return alerts

    async def _alert_exists(
        self,
        source_domain: str,
        target_domain: Optional[str],
        alert_type: str,
    ) -> bool:
        """Check if we already have this alert (deduplication)."""
        query = {
            "bool": {
                "must": [
                    {"term": {"source_domain": source_domain}},
                    {"term": {"alert_type": alert_type}},
                ]
            }
        }

        if target_domain:
            query["bool"]["must"].append({"term": {"target_domain": target_domain}})

        try:
            result = self.es.count(index=self.INDEX_NAME, body={"query": query})
            return result["count"] > 0
        except Exception:
            return False

    async def _store_alerts(self, alerts: List[LinkAlert]):
        """Store alerts in Elasticsearch."""
        def generate_actions():
            for alert in alerts:
                yield {
                    "_index": self.INDEX_NAME,
                    "_id": alert.alert_id,
                    "_source": alert.to_dict(),
                }

        success, errors = bulk(
            self.es,
            generate_actions(),
            chunk_size=100,
            raise_on_error=False,
        )
        print(f"[LinkAlerts] Stored {success} alerts, {len(errors) if errors else 0} errors")

    async def get_alerts(
        self,
        source_domain: Optional[str] = None,
        severity: Optional[str] = None,
        since: Optional[str] = None,
        alert_type: Optional[str] = None,
        size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query stored alerts.

        Args:
            source_domain: Filter by source domain
            severity: Filter by severity (low, medium, high, critical)
            since: ISO date string, get alerts since this date
            alert_type: Filter by alert type
            size: Max results

        Returns:
            List of alert records
        """
        must = []

        if source_domain:
            must.append({"term": {"source_domain": source_domain}})

        if severity:
            must.append({"term": {"severity": severity}})

        if alert_type:
            must.append({"term": {"alert_type": alert_type}})

        if since:
            must.append({"range": {"created_at": {"gte": since}}})

        query = {"bool": {"must": must}} if must else {"match_all": {}}

        try:
            result = self.es.search(
                index=self.INDEX_NAME,
                body={
                    "query": query,
                    "size": size,
                    "sort": [{"created_at": {"order": "desc"}}],
                },
            )

            return [hit["_source"] for hit in result["hits"]["hits"]]
        except Exception as e:
            print(f"[LinkAlerts] Query failed: {e}")
            return []

    async def get_alert_stats(
        self,
        source_domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get alert statistics."""
        must = []
        if source_domain:
            must.append({"term": {"source_domain": source_domain}})

        query = {"bool": {"must": must}} if must else {"match_all": {}}

        try:
            result = self.es.search(
                index=self.INDEX_NAME,
                body={
                    "query": query,
                    "size": 0,
                    "aggs": {
                        "by_type": {"terms": {"field": "alert_type", "size": 20}},
                        "by_severity": {"terms": {"field": "severity", "size": 10}},
                        "by_domain": {"terms": {"field": "source_domain", "size": 20}},
                    },
                },
            )

            aggs = result.get("aggregations", {})

            return {
                "total_alerts": result["hits"]["total"]["value"],
                "by_type": {b["key"]: b["doc_count"] for b in aggs.get("by_type", {}).get("buckets", [])},
                "by_severity": {b["key"]: b["doc_count"] for b in aggs.get("by_severity", {}).get("buckets", [])},
                "by_domain": {b["key"]: b["doc_count"] for b in aggs.get("by_domain", {}).get("buckets", [])},
            }
        except Exception as e:
            return {"error": str(e), "total_alerts": 0}

    async def trigger_archive_change_alerts(
        self,
        url: str,
        diff_report: Dict[str, Any],
        trigger_recrawl: bool = False,
    ) -> Tuple[List[LinkAlert], List[str]]:
        """
        Trigger alerts based on archive diff results.

        Called by snapshot_differ when significant changes are detected.

        Args:
            url: URL that changed
            diff_report: DiffReport as dict with text_added, text_removed,
                        entities_added, entities_removed, links_added, links_removed
            trigger_recrawl: If True, queue re-crawl for high-severity alerts

        Returns:
            Tuple of (triggered alerts, queued job IDs)
        """
        self.ensure_index()
        alerts = []

        # Extract domain from URL
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc

        # Check content change threshold
        lines_changed = len(diff_report.get("text_added", [])) + len(diff_report.get("text_removed", []))
        min_lines = self.ALERT_RULES["archive_content_change"]["min_lines_changed"]

        if lines_changed >= min_lines:
            alerts.append(LinkAlert(
                alert_type="archive_content_change",
                severity=self.ALERT_RULES["archive_content_change"]["severity"],
                source_domain=domain,
                details={
                    "url": url,
                    "lines_added": len(diff_report.get("text_added", [])),
                    "lines_removed": len(diff_report.get("text_removed", [])),
                    "timestamp_before": diff_report.get("timestamp_a"),
                    "timestamp_after": diff_report.get("timestamp_b"),
                    "summary": diff_report.get("summary"),
                },
            ))

        # Check entity additions
        entities_added = diff_report.get("entities_added", {})
        companies_added = entities_added.get("companies", [])
        persons_added = entities_added.get("persons", [])

        if companies_added or persons_added:
            alerts.append(LinkAlert(
                alert_type="archive_entity_added",
                severity=self.ALERT_RULES["archive_entity_added"]["severity"],
                source_domain=domain,
                details={
                    "url": url,
                    "companies_added": companies_added,
                    "persons_added": persons_added,
                    "timestamp_before": diff_report.get("timestamp_a"),
                    "timestamp_after": diff_report.get("timestamp_b"),
                },
            ))

        # Check entity removals (high severity - potential scrubbing)
        entities_removed = diff_report.get("entities_removed", {})
        companies_removed = entities_removed.get("companies", [])
        persons_removed = entities_removed.get("persons", [])

        if companies_removed or persons_removed:
            alerts.append(LinkAlert(
                alert_type="archive_entity_removed",
                severity=self.ALERT_RULES["archive_entity_removed"]["severity"],
                source_domain=domain,
                details={
                    "url": url,
                    "companies_removed": companies_removed,
                    "persons_removed": persons_removed,
                    "timestamp_before": diff_report.get("timestamp_a"),
                    "timestamp_after": diff_report.get("timestamp_b"),
                    "warning": "Possible content scrubbing detected",
                },
            ))

        # Check link changes
        links_added = diff_report.get("links_added", [])
        links_removed = diff_report.get("links_removed", [])
        links_changed = len(links_added) + len(links_removed)
        min_links = self.ALERT_RULES["archive_links_changed"]["min_links_changed"]

        if links_changed >= min_links:
            alerts.append(LinkAlert(
                alert_type="archive_links_changed",
                severity=self.ALERT_RULES["archive_links_changed"]["severity"],
                source_domain=domain,
                details={
                    "url": url,
                    "links_added": links_added[:20],  # Limit for storage
                    "links_removed": links_removed[:20],
                    "links_added_count": len(links_added),
                    "links_removed_count": len(links_removed),
                    "timestamp_before": diff_report.get("timestamp_a"),
                    "timestamp_after": diff_report.get("timestamp_b"),
                },
            ))

        # Store alerts
        if alerts:
            await self._store_alerts(alerts)
            print(f"[LinkAlerts] Triggered {len(alerts)} archive change alerts for {domain}")

        # Trigger re-crawls for high-severity alerts
        job_ids = []
        if trigger_recrawl and SCHEDULER_AVAILABLE and alerts:
            high_severity_alerts = [a for a in alerts if a.severity in ("high", "critical")]
            if high_severity_alerts:
                print(f"[LinkAlerts] Triggering re-crawl for {len(high_severity_alerts)} high-severity alerts")
                for alert in high_severity_alerts:
                    try:
                        job_id = await trigger_recrawl_from_alert(
                            alert_id=alert.alert_id,
                            alert_type=alert.alert_type,
                            source_domain=alert.source_domain,
                            target_domain=alert.target_domain,
                            alert_details=alert.details,
                        )
                        job_ids.append(job_id)
                    except Exception as e:
                        print(f"[LinkAlerts] Failed to queue re-crawl: {e}")

        return alerts, job_ids

    async def clear_alerts(
        self,
        source_domain: Optional[str] = None,
        older_than_days: Optional[int] = None,
    ) -> int:
        """
        Clear alerts (for maintenance).

        Args:
            source_domain: Only clear alerts for this domain
            older_than_days: Only clear alerts older than this many days

        Returns:
            Number of alerts deleted
        """
        must = []

        if source_domain:
            must.append({"term": {"source_domain": source_domain}})

        if older_than_days:
            cutoff = (datetime.utcnow() - timedelta(days=older_than_days)).isoformat()
            must.append({"range": {"created_at": {"lt": cutoff}}})

        query = {"bool": {"must": must}} if must else {"match_all": {}}

        try:
            result = self.es.delete_by_query(
                index=self.INDEX_NAME,
                body={"query": query},
            )
            deleted = result.get("deleted", 0)
            print(f"[LinkAlerts] Cleared {deleted} alerts")
            return deleted
        except Exception as e:
            print(f"[LinkAlerts] Clear failed: {e}")
            return 0


# Convenience functions
async def check_domain_alerts(
    domain: str,
    since_hours: int = 24,
) -> List[Dict[str, Any]]:
    """Check for new alerts on a domain."""
    service = LinkAlertService()
    alerts = await service.check_for_alerts(domain, since_hours)
    return [a.to_dict() for a in alerts]


async def get_all_alerts(
    severity: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get all alerts, optionally filtered by severity."""
    service = LinkAlertService()
    return await service.get_alerts(severity=severity)
