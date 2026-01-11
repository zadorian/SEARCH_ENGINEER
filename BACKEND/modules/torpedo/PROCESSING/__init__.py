"""
TORPEDO PROCESSING - Source Classification and Template Extraction

Structure:
├── processor_base.py    - Shared classification logic (uses jester_bridge.py)
├── cr_processor.py      - Corporate Registry processor (extends TorpedoProcessor)
├── news_processor.py    - News processor (extends TorpedoProcessor)
└── SEEKLEECH/           - Search template discovery for unknown domains

All processors use jester_bridge.py cascade (A→B→C→D→Firecrawl→BrightData)
through processor_base.py's TorpedoProcessor.

Usage:
    from TORPEDO.PROCESSING import CRProcessor, NewsProcessor

    # Corporate Registries
    cr = CRProcessor()
    await cr.load_sources()
    results = await cr.classify_jurisdiction("HR", concurrent=20)
    cr.save_classification("cr_classification.json")

    # News Sources
    news = NewsProcessor()
    await news.load_sources()
    results = await news.classify_jurisdiction("UK", concurrent=20)
    news.save_classification("news_classification.json")
"""

from .processor_base import TorpedoProcessor, ProcessorResult, SourceConfig
from .cr_processor import CRProcessor
from .news_processor import NewsProcessor

__all__ = [
    "TorpedoProcessor",
    "ProcessorResult",
    "SourceConfig",
    "CRProcessor",
    "NewsProcessor",
]
