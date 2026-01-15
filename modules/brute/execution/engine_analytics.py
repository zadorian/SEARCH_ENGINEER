#!/usr/bin/env python3
"""
Engine Analytics - Per-engine performance tracking for every search.

Tracks metrics per engine per search:
- Response time (ms)
- Result count (raw, after dedup)
- Success/failure rate
- Unique URL contribution (URLs only this engine found)
- Duplicate contribution (URLs also found by others)
- Error types and rate limits hit
- Result quality indicators (has title, has snippet, has date)

Outputs analytics summary after every search for improvement insights.
Also persists historical data for trend analysis.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from collections import defaultdict
import statistics


@dataclass
class EngineMetrics:
    """Metrics for a single engine in a single search."""
    engine_code: str
    engine_name: str

    # Timing
    start_time: float = 0.0
    end_time: float = 0.0
    response_time_ms: float = 0.0

    # Query tracking - exact query sent to this engine
    query_variant: str = ""  # Format: "ENGINE_CODE:exact_query_syntax"
    query_variants: List[str] = field(default_factory=list)  # All variants if multiple

    # Counts
    raw_results: int = 0
    unique_results: int = 0  # URLs only this engine found (EXCLUSIVE)
    duplicate_results: int = 0  # URLs also found by others
    filtered_out: int = 0  # Results removed by filters

    # Quality indicators
    results_with_title: int = 0
    results_with_snippet: int = 0
    results_with_date: int = 0
    avg_snippet_length: float = 0.0

    # Status
    success: bool = False
    error: Optional[str] = None
    error_type: Optional[str] = None  # 'timeout', 'rate_limit', 'network', 'parse', 'other'
    http_status: Optional[int] = None
    rate_limited: bool = False

    # Efficiency metrics (calculated after dedup)
    unique_contribution_rate: float = 0.0  # unique_results / raw_results
    value_score: float = 0.0  # Composite: speed + unique contribution + quality


@dataclass
class SearchAnalytics:
    """Complete analytics for a single search."""
    query: str
    search_id: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Overall metrics
    total_engines: int = 0
    successful_engines: int = 0
    failed_engines: int = 0

    total_raw_results: int = 0
    total_unique_results: int = 0
    total_duplicates: int = 0
    dedup_ratio: float = 0.0  # unique / raw

    total_time_ms: float = 0.0
    avg_engine_time_ms: float = 0.0

    # Per-engine breakdown
    engine_metrics: Dict[str, EngineMetrics] = field(default_factory=dict)

    # Rankings (calculated after collection)
    fastest_engines: List[str] = field(default_factory=list)
    most_unique_engines: List[str] = field(default_factory=list)
    highest_value_engines: List[str] = field(default_factory=list)
    failed_engine_list: List[str] = field(default_factory=list)


class EngineAnalyticsCollector:
    """
    Collects and analyzes per-engine metrics during search execution.

    Usage:
        collector = EngineAnalyticsCollector(query="test query")

        # For each engine:
        collector.start_engine("GO")
        results = run_google_search()
        collector.record_engine("GO", results, success=True)

        # After deduplication:
        collector.calculate_unique_contributions(all_results, url_to_engines)

        # Get analytics:
        analytics = collector.finalize()
        collector.print_summary()
        collector.save_to_db()
    """

    def __init__(self, query: str, search_id: Optional[str] = None):
        self.query = query
        self.search_id = search_id or f"search_{int(time.time() * 1000)}"
        self.start_time = time.time()
        self.engine_metrics: Dict[str, EngineMetrics] = {}
        self.url_to_engines: Dict[str, Set[str]] = defaultdict(set)
        self._finalized = False

        # DB path for historical tracking
        self.db_path = Path(__file__).parent.parent / "data" / "engine_analytics.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database for historical tracking."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS engine_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    search_id TEXT,
                    query TEXT,
                    engine_code TEXT,
                    response_time_ms REAL,
                    raw_results INTEGER,
                    unique_results INTEGER,
                    success INTEGER,
                    error_type TEXT,
                    rate_limited INTEGER,
                    value_score REAL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_engine_stats_engine
                ON engine_stats(engine_code, timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_engine_stats_search
                ON engine_stats(search_id)
            """)

    def start_engine(self, engine_code: str, engine_name: Optional[str] = None):
        """Mark start time for an engine."""
        self.engine_metrics[engine_code] = EngineMetrics(
            engine_code=engine_code,
            engine_name=engine_name or engine_code,
            start_time=time.time()
        )

    def record_engine(
        self,
        engine_code: str,
        results: List[Dict[str, Any]],
        success: bool = True,
        error: Optional[str] = None,
        error_type: Optional[str] = None,
        http_status: Optional[int] = None,
        rate_limited: bool = False,
        query_variant: Optional[str] = None
    ):
        """Record results and metrics for an engine.

        Args:
            query_variant: The exact query sent to this engine (e.g., "Glencore mining site:*.gov")
        """
        end_time = time.time()

        if engine_code not in self.engine_metrics:
            self.start_engine(engine_code)

        metrics = self.engine_metrics[engine_code]
        metrics.end_time = end_time
        metrics.response_time_ms = (end_time - metrics.start_time) * 1000
        metrics.success = success
        metrics.error = error
        metrics.error_type = error_type
        metrics.http_status = http_status
        metrics.rate_limited = rate_limited

        # Track query variant
        if query_variant:
            full_variant = f"{engine_code}:{query_variant}"
            metrics.query_variant = full_variant
            if full_variant not in metrics.query_variants:
                metrics.query_variants.append(full_variant)

        if success and results:
            metrics.raw_results = len(results)

            # Track URL to engine mapping
            for r in results:
                url = r.get('url', '')
                if url:
                    self.url_to_engines[url].add(engine_code)

            # Quality metrics
            snippet_lengths = []
            for r in results:
                if r.get('title'):
                    metrics.results_with_title += 1
                snippet = r.get('snippet') or r.get('description', '')
                if snippet:
                    metrics.results_with_snippet += 1
                    snippet_lengths.append(len(snippet))
                if r.get('date') or r.get('published_date'):
                    metrics.results_with_date += 1

            if snippet_lengths:
                metrics.avg_snippet_length = statistics.mean(snippet_lengths)

    def record_failure(
        self,
        engine_code: str,
        error: str,
        error_type: str = 'other',
        http_status: Optional[int] = None,
        rate_limited: bool = False
    ):
        """Record a failed engine execution."""
        self.record_engine(
            engine_code,
            results=[],
            success=False,
            error=error,
            error_type=error_type,
            http_status=http_status,
            rate_limited=rate_limited
        )

    def calculate_unique_contributions(self):
        """
        Calculate which results are unique to each engine vs duplicates.
        Must be called after all engines have reported.
        """
        for engine_code, metrics in self.engine_metrics.items():
            unique = 0
            duplicate = 0

            for url, engines in self.url_to_engines.items():
                if engine_code in engines:
                    if len(engines) == 1:
                        unique += 1
                    else:
                        duplicate += 1

            metrics.unique_results = unique
            metrics.duplicate_results = duplicate

            # Calculate unique contribution rate
            if metrics.raw_results > 0:
                metrics.unique_contribution_rate = unique / metrics.raw_results

    def _calculate_value_scores(self):
        """Calculate composite value score for each engine."""
        # Get ranges for normalization
        all_times = [m.response_time_ms for m in self.engine_metrics.values() if m.success]
        all_unique = [m.unique_results for m in self.engine_metrics.values() if m.success]

        if not all_times or not all_unique:
            return

        max_time = max(all_times) if all_times else 1
        max_unique = max(all_unique) if all_unique else 1

        for metrics in self.engine_metrics.values():
            if not metrics.success:
                metrics.value_score = 0.0
                continue

            # Normalize speed (faster = higher, so invert)
            speed_score = 1 - (metrics.response_time_ms / max_time) if max_time > 0 else 0

            # Normalize unique contribution
            unique_score = metrics.unique_results / max_unique if max_unique > 0 else 0

            # Quality score
            quality_score = 0.0
            if metrics.raw_results > 0:
                quality_score = (
                    (metrics.results_with_title / metrics.raw_results) * 0.3 +
                    (metrics.results_with_snippet / metrics.raw_results) * 0.5 +
                    (metrics.results_with_date / metrics.raw_results) * 0.2
                )

            # Composite: 30% speed, 40% unique contribution, 30% quality
            metrics.value_score = (
                speed_score * 0.30 +
                unique_score * 0.40 +
                quality_score * 0.30
            )

    def finalize(self) -> SearchAnalytics:
        """Finalize analytics and calculate rankings."""
        if self._finalized:
            return self._get_analytics()

        self.calculate_unique_contributions()
        self._calculate_value_scores()
        self._finalized = True

        return self._get_analytics()

    def _get_analytics(self) -> SearchAnalytics:
        """Build the SearchAnalytics object."""
        total_time = (time.time() - self.start_time) * 1000

        successful = [m for m in self.engine_metrics.values() if m.success]
        failed = [m for m in self.engine_metrics.values() if not m.success]

        total_raw = sum(m.raw_results for m in successful)
        total_unique = len(self.url_to_engines)

        analytics = SearchAnalytics(
            query=self.query,
            search_id=self.search_id,
            total_engines=len(self.engine_metrics),
            successful_engines=len(successful),
            failed_engines=len(failed),
            total_raw_results=total_raw,
            total_unique_results=total_unique,
            total_duplicates=total_raw - total_unique,
            dedup_ratio=total_unique / total_raw if total_raw > 0 else 0,
            total_time_ms=total_time,
            avg_engine_time_ms=statistics.mean([m.response_time_ms for m in successful]) if successful else 0,
            engine_metrics={k: v for k, v in self.engine_metrics.items()},
            failed_engine_list=[m.engine_code for m in failed]
        )

        # Rankings
        if successful:
            sorted_by_speed = sorted(successful, key=lambda m: m.response_time_ms)
            analytics.fastest_engines = [m.engine_code for m in sorted_by_speed[:5]]

            sorted_by_unique = sorted(successful, key=lambda m: m.unique_results, reverse=True)
            analytics.most_unique_engines = [m.engine_code for m in sorted_by_unique[:5]]

            sorted_by_value = sorted(successful, key=lambda m: m.value_score, reverse=True)
            analytics.highest_value_engines = [m.engine_code for m in sorted_by_value[:5]]

        return analytics

    def print_summary(self):
        """Print a formatted analytics summary to console."""
        analytics = self.finalize()

        print("\n" + "=" * 80)
        print("ENGINE ANALYTICS REPORT")
        print("=" * 80)
        print(f"Query: {analytics.query}")
        print(f"Search ID: {analytics.search_id}")
        print(f"Total Time: {analytics.total_time_ms:.0f}ms")
        print()

        # Overall stats
        print("OVERALL STATISTICS")
        print("-" * 40)
        print(f"  Engines: {analytics.successful_engines}/{analytics.total_engines} successful")
        print(f"  Raw Results: {analytics.total_raw_results}")
        print(f"  Unique URLs: {analytics.total_unique_results}")
        print(f"  Duplicates Removed: {analytics.total_duplicates}")
        print(f"  Dedup Ratio: {analytics.dedup_ratio:.1%}")
        print()

        # Per-engine breakdown
        print("PER-ENGINE BREAKDOWN")
        print("-" * 80)
        print(f"{'Engine':<8} {'Time':>8} {'Raw':>6} {'Unique':>6} {'Dupe':>6} {'Quality':>8} {'Value':>6} {'Status':<12}")
        print("-" * 80)

        for code in sorted(self.engine_metrics.keys()):
            m = self.engine_metrics[code]
            if m.success:
                quality = f"{m.results_with_snippet}/{m.raw_results}" if m.raw_results else "N/A"
                status = "OK"
            else:
                quality = "N/A"
                status = m.error_type or "FAILED"
                if m.rate_limited:
                    status = "RATE_LIM"

            print(f"{code:<8} {m.response_time_ms:>7.0f}ms {m.raw_results:>6} {m.unique_results:>6} "
                  f"{m.duplicate_results:>6} {quality:>8} {m.value_score:>5.2f} {status:<12}")

        print()

        # Rankings
        print("RANKINGS")
        print("-" * 40)
        print(f"  Fastest: {', '.join(analytics.fastest_engines)}")
        print(f"  Most Unique: {', '.join(analytics.most_unique_engines)}")
        print(f"  Highest Value: {', '.join(analytics.highest_value_engines)}")
        if analytics.failed_engine_list:
            print(f"  Failed: {', '.join(analytics.failed_engine_list)}")

        print()

        # Recommendations
        self._print_recommendations(analytics)

        print("=" * 80)

    def _print_recommendations(self, analytics: SearchAnalytics):
        """Print actionable recommendations based on analytics."""
        print("RECOMMENDATIONS")
        print("-" * 40)

        recommendations = []

        # High duplicate engines
        for code, m in self.engine_metrics.items():
            if m.success and m.raw_results > 5:
                if m.unique_contribution_rate < 0.1:
                    recommendations.append(
                        f"  • {code}: Low unique contribution ({m.unique_contribution_rate:.0%}). "
                        f"Consider deprioritizing."
                    )

        # Slow engines with low value
        for code, m in self.engine_metrics.items():
            if m.success and m.response_time_ms > 10000 and m.value_score < 0.3:
                recommendations.append(
                    f"  • {code}: Slow ({m.response_time_ms:.0f}ms) with low value ({m.value_score:.2f}). "
                    f"Consider removing from fast tier."
                )

        # Rate limited engines
        rate_limited = [m.engine_code for m in self.engine_metrics.values() if m.rate_limited]
        if rate_limited:
            recommendations.append(
                f"  • Rate limited: {', '.join(rate_limited)}. Increase delays or rotate proxies."
            )

        # Failed engines
        for m in self.engine_metrics.values():
            if not m.success and m.error_type == 'parse':
                recommendations.append(
                    f"  • {m.engine_code}: Parse error - API may have changed."
                )

        if not recommendations:
            recommendations.append("  • All engines performing well. No issues detected.")

        for rec in recommendations:
            print(rec)

    def save_to_db(self):
        """Save analytics to SQLite for historical tracking."""
        analytics = self.finalize()

        with sqlite3.connect(self.db_path) as conn:
            for code, m in self.engine_metrics.items():
                conn.execute("""
                    INSERT INTO engine_stats
                    (timestamp, search_id, query, engine_code, response_time_ms,
                     raw_results, unique_results, success, error_type, rate_limited, value_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    analytics.timestamp,
                    analytics.search_id,
                    analytics.query[:200],  # Truncate long queries
                    code,
                    m.response_time_ms,
                    m.raw_results,
                    m.unique_results,
                    1 if m.success else 0,
                    m.error_type,
                    1 if m.rate_limited else 0,
                    m.value_score
                ))

        # Also save to JSON file for easy inspection
        self.save_to_json()

    def save_to_json(self):
        """Append analytics to persistent JSON file."""
        json_path = self.db_path.parent / "engine_analytics.json"

        # Load existing data or create new structure
        existing_data = {"searches": [], "engine_totals": {}}
        if json_path.exists():
            try:
                with open(json_path, 'r') as f:
                    existing_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                existing_data = {"searches": [], "engine_totals": {}}

        analytics = self.finalize()

        # Build search entry with per-engine query variants
        search_entry = {
            "timestamp": analytics.timestamp,
            "search_id": analytics.search_id,
            "query": analytics.query,
            "total_time_ms": analytics.total_time_ms,
            "total_unique_results": analytics.total_unique_results,
            "total_raw_results": analytics.total_raw_results,
            "engines": {}
        }

        for code, m in self.engine_metrics.items():
            # Get all query variants run by this engine
            query_variants = m.query_variants if m.query_variants else [f"{code}:{analytics.query}"]

            search_entry["engines"][code] = {
                "queries_sent": query_variants,  # All query variants this engine ran
                "response_time_ms": round(m.response_time_ms, 1),
                "raw_results": m.raw_results,
                "exclusive_unique": m.unique_results,  # Found ONLY by this engine
                "duplicates": m.duplicate_results,
                "unique_contribution_rate": round(m.unique_contribution_rate * 100, 1),
                "value_score": round(m.value_score, 3),
                "success": m.success,
                "error": m.error
            }

            # Update engine totals
            if code not in existing_data["engine_totals"]:
                existing_data["engine_totals"][code] = {
                    "total_searches": 0,
                    "total_raw_results": 0,
                    "total_exclusive_unique": 0,
                    "total_duplicates": 0,
                    "avg_response_time_ms": 0,
                    "success_count": 0,
                    "fail_count": 0
                }

            totals = existing_data["engine_totals"][code]
            totals["total_searches"] += 1
            totals["total_raw_results"] += m.raw_results
            totals["total_exclusive_unique"] += m.unique_results
            totals["total_duplicates"] += m.duplicate_results
            if m.success:
                totals["success_count"] += 1
                # Running average for response time
                n = totals["success_count"]
                totals["avg_response_time_ms"] = (
                    (totals["avg_response_time_ms"] * (n - 1) + m.response_time_ms) / n
                )
            else:
                totals["fail_count"] += 1

        # Append search entry
        existing_data["searches"].append(search_entry)

        # Keep only last 1000 searches to prevent file bloat
        if len(existing_data["searches"]) > 1000:
            existing_data["searches"] = existing_data["searches"][-1000:]

        # Write back
        with open(json_path, 'w') as f:
            json.dump(existing_data, f, indent=2)

        print(f"📊 Analytics saved to {json_path}")

    def to_dict(self) -> Dict[str, Any]:
        """Export analytics as dictionary for JSON serialization."""
        analytics = self.finalize()
        return {
            'query': analytics.query,
            'search_id': analytics.search_id,
            'timestamp': analytics.timestamp,
            'summary': {
                'total_engines': analytics.total_engines,
                'successful_engines': analytics.successful_engines,
                'failed_engines': analytics.failed_engines,
                'total_raw_results': analytics.total_raw_results,
                'total_unique_results': analytics.total_unique_results,
                'total_duplicates': analytics.total_duplicates,
                'dedup_ratio': analytics.dedup_ratio,
                'total_time_ms': analytics.total_time_ms,
                'avg_engine_time_ms': analytics.avg_engine_time_ms,
            },
            'rankings': {
                'fastest': analytics.fastest_engines,
                'most_unique': analytics.most_unique_engines,
                'highest_value': analytics.highest_value_engines,
                'failed': analytics.failed_engine_list,
            },
            'engines': {
                code: {
                    'response_time_ms': m.response_time_ms,
                    'raw_results': m.raw_results,
                    'unique_results': m.unique_results,
                    'duplicate_results': m.duplicate_results,
                    'unique_contribution_rate': m.unique_contribution_rate,
                    'results_with_title': m.results_with_title,
                    'results_with_snippet': m.results_with_snippet,
                    'avg_snippet_length': m.avg_snippet_length,
                    'value_score': m.value_score,
                    'success': m.success,
                    'error': m.error,
                    'error_type': m.error_type,
                    'rate_limited': m.rate_limited,
                }
                for code, m in self.engine_metrics.items()
            }
        }


def get_historical_stats(engine_code: str, days: int = 7) -> Dict[str, Any]:
    """Get historical performance stats for an engine."""
    db_path = Path(__file__).parent.parent / "data" / "engine_analytics.db"

    if not db_path.exists():
        return {}

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        # Get recent stats
        rows = conn.execute("""
            SELECT
                AVG(response_time_ms) as avg_time,
                AVG(CASE WHEN success = 1 THEN raw_results ELSE 0 END) as avg_results,
                AVG(CASE WHEN success = 1 THEN unique_results ELSE 0 END) as avg_unique,
                AVG(value_score) as avg_value,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as success_rate,
                SUM(CASE WHEN rate_limited = 1 THEN 1 ELSE 0 END) as rate_limit_count,
                COUNT(*) as total_searches
            FROM engine_stats
            WHERE engine_code = ?
            AND timestamp > datetime('now', ?)
        """, (engine_code, f'-{days} days')).fetchone()

        if rows and rows['total_searches'] > 0:
            return {
                'engine_code': engine_code,
                'period_days': days,
                'total_searches': rows['total_searches'],
                'avg_response_time_ms': rows['avg_time'],
                'avg_raw_results': rows['avg_results'],
                'avg_unique_results': rows['avg_unique'],
                'avg_value_score': rows['avg_value'],
                'success_rate': rows['success_rate'],
                'rate_limit_count': rows['rate_limit_count'],
            }

    return {}


def get_historical_rankings(days: int = 7) -> Dict[str, Any]:
    """Get historical rankings for all engines - who produces most unique and highest total."""
    db_path = Path(__file__).parent.parent / "data" / "engine_analytics.db"

    if not db_path.exists():
        return {'top_unique_producers': [], 'top_total_producers': [], 'searches_analyzed': 0}

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        # Get engines ranked by total unique results (exclusive finds)
        unique_rows = conn.execute("""
            SELECT
                engine_code,
                SUM(unique_results) as total_exclusive_finds,
                AVG(unique_results) as avg_exclusive_per_search,
                COUNT(*) as searches
            FROM engine_stats
            WHERE success = 1
            AND timestamp > datetime('now', ?)
            GROUP BY engine_code
            ORDER BY total_exclusive_finds DESC
            LIMIT 10
        """, (f'-{days} days',)).fetchall()

        # Get engines ranked by total raw output
        output_rows = conn.execute("""
            SELECT
                engine_code,
                SUM(raw_results) as total_output,
                AVG(raw_results) as avg_output_per_search,
                COUNT(*) as searches
            FROM engine_stats
            WHERE success = 1
            AND timestamp > datetime('now', ?)
            GROUP BY engine_code
            ORDER BY total_output DESC
            LIMIT 10
        """, (f'-{days} days',)).fetchall()

        # Get total searches
        total = conn.execute("""
            SELECT COUNT(DISTINCT search_id) as cnt
            FROM engine_stats
            WHERE timestamp > datetime('now', ?)
        """, (f'-{days} days',)).fetchone()

        return {
            'period_days': days,
            'searches_analyzed': total['cnt'] if total else 0,
            'top_unique_producers': [
                {
                    'engine': row['engine_code'],
                    'total_exclusive_finds': row['total_exclusive_finds'],
                    'avg_per_search': row['avg_exclusive_per_search'],
                    'searches': row['searches']
                }
                for row in unique_rows
            ],
            'top_total_producers': [
                {
                    'engine': row['engine_code'],
                    'total_output': row['total_output'],
                    'avg_per_search': row['avg_output_per_search'],
                    'searches': row['searches']
                }
                for row in output_rows
            ]
        }


def print_historical_rankings(days: int = 7):
    """Print historical rankings to console."""
    rankings = get_historical_rankings(days)

    print("\n" + "=" * 80)
    print(f"HISTORICAL ENGINE RANKINGS (Last {days} days)")
    print("=" * 80)
    print(f"Searches Analyzed: {rankings['searches_analyzed']}")
    print()

    print("TOP UNIQUE PRODUCERS (Exclusive Finds - URLs found ONLY by this engine)")
    print("-" * 60)
    print(f"{'Rank':<5} {'Engine':<8} {'Total Exclusive':>15} {'Avg/Search':>12} {'Searches':>10}")
    print("-" * 60)
    for i, entry in enumerate(rankings['top_unique_producers'], 1):
        print(f"{i:<5} {entry['engine']:<8} {entry['total_exclusive_finds']:>15} "
              f"{entry['avg_per_search']:>11.1f} {entry['searches']:>10}")
    print()

    print("TOP TOTAL OUTPUT (Raw Results - even if duplicated)")
    print("-" * 60)
    print(f"{'Rank':<5} {'Engine':<8} {'Total Output':>15} {'Avg/Search':>12} {'Searches':>10}")
    print("-" * 60)
    for i, entry in enumerate(rankings['top_total_producers'], 1):
        print(f"{i:<5} {entry['engine']:<8} {entry['total_output']:>15} "
              f"{entry['avg_per_search']:>11.1f} {entry['searches']:>10}")

    print("=" * 80)


if __name__ == '__main__':
    # Demo
    print("Engine Analytics Demo")
    print("=" * 60)

    collector = EngineAnalyticsCollector(query="test query demo")

    # Simulate some engine results
    import random

    engines = ['GO', 'BI', 'BR', 'DD', 'EX', 'YA']

    for code in engines:
        collector.start_engine(code)
        time.sleep(random.uniform(0.1, 0.5))  # Simulate response time

        if random.random() > 0.2:  # 80% success rate
            results = [
                {'url': f'https://example{i}.com/page{random.randint(1,100)}',
                 'title': f'Result {i}',
                 'snippet': 'This is a test snippet ' * random.randint(1, 5)}
                for i in range(random.randint(5, 30))
            ]
            collector.record_engine(code, results, success=True)
        else:
            collector.record_failure(code, "Timeout", error_type='timeout')

    collector.print_summary()
    collector.save_to_db()

    # Export as JSON
    print("\nJSON Export (partial):")
    data = collector.to_dict()
    print(json.dumps(data['summary'], indent=2))
