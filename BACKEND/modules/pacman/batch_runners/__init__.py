"""
PACMAN Runners
Batch execution modes for extraction
"""

from .base import (
    BaseRunner,
    RunnerResult,
    RunnerStats,
    RunnerStatus,
)

from .tiered import TieredRunner
from .blitz import BlitzRunner


def get_runner(mode: str, config=None):
    """Get a runner by mode name."""
    runners = {
        'tiered': TieredRunner,
        'blitz': BlitzRunner,
    }
    
    runner_class = runners.get(mode)
    if runner_class is None:
        raise ValueError(f'Unknown runner mode: {mode}')
    
    return runner_class(config)


__all__ = [
    'BaseRunner',
    'RunnerResult',
    'RunnerStats',
    'RunnerStatus',
    'TieredRunner',
    'BlitzRunner',
    'get_runner',
]
