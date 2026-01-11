"""
Adapters for bridging modern and legacy engine patterns.
"""
from .modern_engine_adapter import ModernEngineAdapter, create_adapted_runner

__all__ = ["ModernEngineAdapter", "create_adapted_runner"]
