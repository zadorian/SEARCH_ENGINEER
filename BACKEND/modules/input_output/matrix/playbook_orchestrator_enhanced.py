#!/usr/bin/env python3
"""
Enhanced Playbook Orchestrator

Extends the existing IOExecutor with additional capabilities:
- Error classification and reporting
- Progress streaming
- Smart playbook selection
- Playbook chaining
- Result caching

Use this as a wrapper around IOExecutor for advanced features.
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, AsyncIterator, Any, Callable
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum


class ErrorCategory(Enum):
    """Error classification for better reporting."""
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    AUTH_FAILED = "auth_failed"
    PARSE_ERROR = "parse_error"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


@dataclass
class PlaybookProgress:
    """Progress update during playbook execution."""
    stage: str  # 'executing', 'completed', 'failed'
    rule_id: str
    rule_index: int
    total_rules: int
    result: Optional[Dict] = None
    error: Optional[str] = None

    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage."""
        return (self.rule_index / self.total_rules) * 100 if self.total_rules > 0 else 0


@dataclass
class PlaybookRecommendation:
    """Playbook recommendation with scoring."""
    playbook: Dict
    score: float
    coverage: float  # How many goal fields it returns
    success_rate: float
    rule_count: int
    estimated_duration: float  # seconds


class ErrorClassifier:
    """Classify errors for better reporting."""

    @staticmethod
    def classify(error_msg: str) -> ErrorCategory:
        """Classify error based on message and context."""
        if not error_msg:
            return ErrorCategory.UNKNOWN

        error_lower = error_msg.lower()

        # Timeout patterns
        if any(word in error_lower for word in ['timeout', 'timed out', 'deadline exceeded']):
            return ErrorCategory.TIMEOUT

        # Not found patterns
        if any(word in error_lower for word in ['not found', '404', 'no results', 'no data']):
            return ErrorCategory.NOT_FOUND

        # Rate limit patterns
        if any(word in error_lower for word in ['rate limit', 'too many requests', '429', 'quota exceeded']):
            return ErrorCategory.RATE_LIMITED

        # Auth patterns
        if any(word in error_lower for word in ['unauthorized', '401', '403', 'forbidden', 'api key', 'authentication']):
            return ErrorCategory.AUTH_FAILED

        # Parse patterns
        if any(word in error_lower for word in ['parse', 'json', 'decode', 'invalid format', 'malformed']):
            return ErrorCategory.PARSE_ERROR

        # Network patterns
        if any(word in error_lower for word in ['connection', 'network', 'dns', 'unreachable', 'refused']):
            return ErrorCategory.NETWORK_ERROR

        return ErrorCategory.UNKNOWN


class ResultCache:
    """Simple in-memory cache for rule results."""

    def __init__(self, ttl_seconds: int = 86400):  # 24 hours default
        self._cache: Dict[str, Dict] = {}
        self._timestamps: Dict[str, datetime] = {}
        self.ttl = timedelta(seconds=ttl_seconds)

    def _make_key(self, rule_id: str, value: str, jurisdiction: str = None) -> str:
        """Generate cache key."""
        return f"{rule_id}:{value}:{jurisdiction or 'none'}"

    def get(self, rule_id: str, value: str, jurisdiction: str = None) -> Optional[Dict]:
        """Get cached result if not expired."""
        key = self._make_key(rule_id, value, jurisdiction)

        if key in self._cache:
            timestamp = self._timestamps.get(key)
            if timestamp and datetime.now() - timestamp < self.ttl:
                return self._cache[key]
            else:
                # Expired - remove
                del self._cache[key]
                del self._timestamps[key]

        return None

    def set(self, rule_id: str, value: str, result: Dict, jurisdiction: str = None):
        """Cache result."""
        key = self._make_key(rule_id, value, jurisdiction)
        self._cache[key] = result
        self._timestamps[key] = datetime.now()

    def clear(self):
        """Clear all cached results."""
        self._cache.clear()
        self._timestamps.clear()

    def stats(self) -> Dict:
        """Get cache statistics."""
        return {
            'cached_items': len(self._cache),
            'oldest_entry': min(self._timestamps.values()) if self._timestamps else None,
            'newest_entry': max(self._timestamps.values()) if self._timestamps else None
        }


class PlaybookOrchestrator:
    """
    Enhanced Playbook Orchestrator.

    Wraps IOExecutor with advanced features:
    - Error classification
    - Progress streaming
    - Smart playbook selection
    - Result caching
    - Playbook chaining
    """

    def __init__(self, executor, enable_cache: bool = True, cache_ttl: int = 86400):
        """
        Initialize orchestrator.

        Args:
            executor: IOExecutor instance
            enable_cache: Enable result caching
            cache_ttl: Cache time-to-live in seconds (default 24 hours)
        """
        self.executor = executor
        self.router = executor.router
        self.cache = ResultCache(ttl_seconds=cache_ttl) if enable_cache else None

    async def execute_playbook_enhanced(
        self,
        playbook_id: str,
        value: str,
        jurisdiction: str = None,
        parallel: bool = None,
        use_cache: bool = True
    ) -> Dict:
        """
        Execute playbook with enhanced error reporting.

        Returns detailed error classification and metrics.
        """
        cache_key = f"playbook:{playbook_id}"
        if self.cache and use_cache:
            cached = self.cache.get(cache_key, value, jurisdiction)
            if cached is not None:
                return cached

        # Use base executor
        result = await self.executor.execute_playbook(
            playbook_id, value, jurisdiction, parallel
        )

        if 'error' in result:
            return result

        # Classify errors
        error_categories = defaultdict(list)
        successful_rules = []
        failed_rules = []

        for rule_result in result.get('results', []):
            rule_id = rule_result.get('rule_id', 'unknown')

            if rule_result.get('status') == 'success':
                successful_rules.append(rule_id)
            else:
                error_msg = rule_result.get('error', '')
                category = ErrorClassifier.classify(error_msg)
                error_categories[category.value].append({
                    'rule_id': rule_id,
                    'error': error_msg
                })
                failed_rules.append(rule_id)

        # Add enhanced metadata
        result['error_breakdown'] = dict(error_categories)
        result['successful_rules'] = successful_rules
        result['failed_rules'] = failed_rules
        rules_executed = result.get('rules_executed', len(result.get('results', [])))
        result['success_rate'] = len(successful_rules) / rules_executed if rules_executed > 0 else 0

        if self.cache and use_cache:
            self.cache.set(cache_key, value, result, jurisdiction)

        return result

    async def execute_playbook_stream(
        self,
        playbook_id: str,
        value: str,
        jurisdiction: str = None
    ) -> AsyncIterator[PlaybookProgress]:
        """
        Stream playbook execution progress.

        Yields progress updates as each rule completes.
        """
        playbook = self.executor._find_playbook(playbook_id)
        if not playbook:
            yield PlaybookProgress(
                stage='failed',
                rule_id='',
                rule_index=0,
                total_rules=0,
                error=f'Playbook not found: {playbook_id}'
            )
            return

        rule_ids = playbook.get('rules', [])
        total_rules = len(rule_ids)

        for idx, rule_id in enumerate(rule_ids):
            # Yield executing status
            yield PlaybookProgress(
                stage='executing',
                rule_id=rule_id,
                rule_index=idx,
                total_rules=total_rules
            )

            # Execute rule
            try:
                result = await self.executor.execute_by_rule(
                    rule_id, value, jurisdiction or playbook.get('jurisdiction')
                )

                # Yield completed status
                yield PlaybookProgress(
                    stage='completed',
                    rule_id=rule_id,
                    rule_index=idx + 1,
                    total_rules=total_rules,
                    result=result
                )

            except Exception as e:
                # Yield failed status
                yield PlaybookProgress(
                    stage='failed',
                    rule_id=rule_id,
                    rule_index=idx + 1,
                    total_rules=total_rules,
                    error=str(e)
                )

    def recommend_playbooks(
        self,
        input_code: int,
        jurisdiction: str = None,
        goals: List[int] = None,
        limit: int = 5,
        min_success_rate: float = 0.5
    ) -> List[PlaybookRecommendation]:
        """
        Recommend best playbooks for given inputs and goals.

        Args:
            input_code: Field code of input (e.g., 13 for company_name)
            jurisdiction: Optional jurisdiction filter
            goals: List of desired output field codes
            limit: Maximum number of recommendations
            min_success_rate: Minimum success rate threshold

        Returns:
            List of PlaybookRecommendation objects sorted by score
        """
        recommendations = []
        goals_set = set(goals) if goals else set()

        for pb in self.router.playbooks:
            # Check if playbook accepts our input
            requires = pb.get('requires_any', [])
            if input_code not in requires:
                continue

            # Check jurisdiction
            pb_jur = pb.get('jurisdiction', 'GLOBAL')
            if jurisdiction and pb_jur not in (jurisdiction, 'GLOBAL', 'none'):
                continue

            # Calculate coverage
            returns = set(pb.get('returns', []))
            coverage = len(goals_set & returns) / len(goals_set) if goals_set else 0.5

            # Get success rate
            success_rate = pb.get('success_rate', 0.5)

            # Filter by minimum success rate
            if success_rate < min_success_rate:
                continue

            # Calculate score (weighted: coverage 60%, success 40%)
            score = coverage * 0.6 + success_rate * 0.4

            # Estimate duration (assume 3 seconds per rule average)
            rule_count = len(pb.get('rules', []))
            estimated_duration = rule_count * 3.0

            recommendations.append(PlaybookRecommendation(
                playbook=pb,
                score=score,
                coverage=coverage,
                success_rate=success_rate,
                rule_count=rule_count,
                estimated_duration=estimated_duration
            ))

        # Sort by score descending
        recommendations.sort(key=lambda x: x.score, reverse=True)

        return recommendations[:limit]

    async def execute_playbook_chain(
        self,
        playbook_ids: List[str],
        initial_value: str,
        jurisdiction: str = None,
        value_selector: Optional[Callable[[Dict], Optional[str]]] = None
    ) -> Dict:
        """
        Execute multiple playbooks in sequence.

        Outputs are aggregated for inspection. If a value_selector is provided,
        its output is used as the input value for the next playbook.

        Returns:
            Dict with results from all playbooks and extracted entities
        """
        results = {}
        current_value = initial_value
        all_extracted_entities = defaultdict(list)

        for idx, playbook_id in enumerate(playbook_ids):
            print(f"Executing playbook {idx + 1}/{len(playbook_ids)}: {playbook_id}")

            result = await self.execute_playbook_enhanced(
                playbook_id, current_value, jurisdiction
            )

            results[playbook_id] = result

            if value_selector:
                try:
                    next_value = value_selector(result)
                except Exception:
                    next_value = None
                if next_value:
                    current_value = str(next_value)

            # Extract entities from results for next step
            # (This is simplified - real implementation would use entity extraction)
            for rule_result in result.get('results', []):
                if rule_result.get('status') == 'success':
                    data = rule_result.get('data', {})
                    # Store extracted entities by type
                    for key, val in data.items():
                        if val:
                            all_extracted_entities[key].append(val)

        return {
            'playbook_chain': playbook_ids,
            'initial_value': initial_value,
            'jurisdiction': jurisdiction,
            'playbook_results': results,
            'extracted_entities': dict(all_extracted_entities),
            'total_playbooks': len(playbook_ids),
            'successful_playbooks': sum(1 for r in results.values() if r.get('status') == 'success')
        }

    async def execute_auto(
        self,
        input_code: int,
        value: str,
        jurisdiction: str = None,
        goals: List[int] = None,
        max_playbooks: int = 3
    ) -> Dict:
        """
        Automatically select and execute best playbooks.

        Args:
            input_code: Field code of input
            value: Input value
            jurisdiction: Optional jurisdiction
            goals: Desired output field codes
            max_playbooks: Maximum playbooks to execute

        Returns:
            Combined results from all selected playbooks
        """
        # Get recommendations
        recommendations = self.recommend_playbooks(
            input_code, jurisdiction, goals, limit=max_playbooks
        )

        if not recommendations:
            return {
                'error': 'No suitable playbooks found',
                'input_code': input_code,
                'jurisdiction': jurisdiction,
                'goals': goals
            }

        # Execute top playbooks
        playbook_ids = [rec.playbook['id'] for rec in recommendations]

        return await self.execute_playbook_chain(playbook_ids, value, jurisdiction)

    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        if self.cache:
            return self.cache.stats()
        return {'cache_enabled': False}

    def clear_cache(self):
        """Clear result cache."""
        if self.cache:
            self.cache.clear()


# Example usage
async def main():
    """Example usage of enhanced orchestrator."""
    from io_cli import IORouter, IOExecutor

    # Initialize
    router = IORouter()
    executor = IOExecutor(router)
    orchestrator = PlaybookOrchestrator(executor, enable_cache=True)

    # Example 1: Execute with enhanced reporting
    print("Example 1: Enhanced execution")
    result = await orchestrator.execute_playbook_enhanced(
        'PLAYBOOK_CH_CORPORATE_REGISTRY_SEARCH_0',
        'Nestlé S.A.',
        'CH'
    )
    print(f"Success rate: {result.get('success_rate', 0):.1%}")
    print(f"Error breakdown: {result.get('error_breakdown', {})}")

    # Example 2: Stream progress
    print("\nExample 2: Streaming execution")
    async for progress in orchestrator.execute_playbook_stream(
        'PLAYBOOK_CH_CORPORATE_REGISTRY_SEARCH_0',
        'Nestlé S.A.',
        'CH'
    ):
        print(f"[{progress.progress_percent:.1f}%] {progress.stage} {progress.rule_id}")

    # Example 3: Get recommendations
    print("\nExample 3: Playbook recommendations")
    recommendations = orchestrator.recommend_playbooks(
        input_code=13,  # company_name
        jurisdiction='CH',
        goals=[42, 58, 59],  # company_address, company_number, company_status
        limit=3
    )

    for idx, rec in enumerate(recommendations):
        print(f"{idx + 1}. {rec.playbook['label']}")
        print(f"   Score: {rec.score:.2f} | Coverage: {rec.coverage:.1%} | Success: {rec.success_rate:.1%}")
        print(f"   Est. duration: {rec.estimated_duration:.1f}s | Rules: {rec.rule_count}")

    # Example 4: Auto-execute
    print("\nExample 4: Auto-execute best playbooks")
    result = await orchestrator.execute_auto(
        input_code=13,
        value='BP plc',
        jurisdiction='GB',
        goals=[42, 58, 59],
        max_playbooks=2
    )
    print(f"Executed {result['total_playbooks']} playbooks")
    print(f"Successful: {result['successful_playbooks']}")

    # Cache stats
    print(f"\nCache stats: {orchestrator.get_cache_stats()}")


if __name__ == '__main__':
    asyncio.run(main())
