"""
PACMAN Runner Base Class
All execution modes inherit from this
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RunnerStatus(Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    PAUSED = 'paused'
    COMPLETED = 'completed'
    FAILED = 'failed'


@dataclass
class RunnerResult:
    """Result from a single URL/domain processing."""
    url: str
    status: str
    content: Optional[str] = None
    entities: Dict[str, List] = field(default_factory=dict)
    links: List[str] = field(default_factory=list)
    red_flags: List[str] = field(default_factory=list)
    tier: str = 'EXTRACT'
    scrape_method: str = 'unknown'
    duration_ms: int = 0
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)


@dataclass
class RunnerStats:
    """Statistics for a runner execution."""
    total: int = 0
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    @property
    def rate_per_second(self) -> float:
        if self.duration_seconds > 0:
            return self.processed / self.duration_seconds
        return 0.0


class BaseRunner(ABC):
    """Base class for all PACMAN runners."""
    
    name: str = 'base'
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.stats = RunnerStats()
        self.status = RunnerStatus.PENDING
        self._checkpoint_file: Optional[str] = None
    
    @abstractmethod
    async def run(self, inputs: List[str]) -> AsyncIterator[RunnerResult]:
        """
        Run extraction on inputs (URLs or domains).
        Yields results as they complete.
        """
        pass
    
    @abstractmethod
    async def run_single(self, input: str) -> RunnerResult:
        """Process a single input."""
        pass
    
    def set_checkpoint(self, filepath: str):
        """Set checkpoint file for resume capability."""
        self._checkpoint_file = filepath
    
    def save_checkpoint(self, processed: List[str]):
        """Save progress checkpoint."""
        if self._checkpoint_file:
            import json
            with open(self._checkpoint_file, 'w') as f:
                json.dump({
                    'processed': processed,
                    'stats': {
                        'total': self.stats.total,
                        'processed': self.stats.processed,
                        'succeeded': self.stats.succeeded,
                        'failed': self.stats.failed,
                    }
                }, f)
    
    def load_checkpoint(self) -> List[str]:
        """Load checkpoint to resume."""
        if self._checkpoint_file:
            import json
            from pathlib import Path
            if Path(self._checkpoint_file).exists():
                with open(self._checkpoint_file) as f:
                    data = json.load(f)
                    return data.get('processed', [])
        return []
    
    def pause(self):
        """Pause execution."""
        self.status = RunnerStatus.PAUSED
    
    def resume(self):
        """Resume execution."""
        if self.status == RunnerStatus.PAUSED:
            self.status = RunnerStatus.RUNNING
