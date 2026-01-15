"""Brute search configuration module"""
from .unified_config import config, UnifiedConfig

# Alias for backwards compatibility
Config = UnifiedConfig

__all__ = ['config', 'Config', 'UnifiedConfig']
