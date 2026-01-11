"""
SASTRE Linklater Bridge

Bridge to Linklater link intelligence system.

Provides:
- Backlinks (domains linking TO target)
- Outlinks (domains linked FROM target)
- Entity extraction (AI-powered)
- Archive scraping (CC -> Wayback -> Firecrawl)
- Co-citation (related sites)
- WHOIS clustering (ownership-linked domains)
- GA tracker discovery
- Historical search
"""

# Re-export from bridges.py
from ..bridges import LinklaterBridge, ExtendedLinklaterBridge

__all__ = ['LinklaterBridge', 'ExtendedLinklaterBridge']
