"""
TORPEDO - Unified Search with Source Templates

Structure:
├── EXECUTION/           - Search execution against classified sources
│   ├── base_searcher.py
│   ├── cr_searcher.py
│   └── news_searcher.py
├── PROCESSING/          - Source classification and template extraction
│   ├── processor_base.py
│   ├── cr_processor.py
│   ├── news_processor.py
│   └── SEEKLEECH/       - Search template discovery
├── jester_bridge.py     - JESTER A/B/C/D + Firecrawl + BrightData
└── torpedo_cli.py       - Unified CLI

IMPORTANT: UK NOT GB for United Kingdom!

CLI Usage:
    torpedo process cr sources.json --jurisdiction UK,DE
    torpedo process news sources/news.json --limit 100
    torpedo search cr "Acme Ltd" --jurisdiction UK
    torpedo search news "corruption" --jurisdiction HR
    torpedo info --sources sources.json

Python Usage:
    from TORPEDO.EXECUTION import CRSearcher, NewsSearcher

    cr = CRSearcher()
    await cr.load_sources()
    results = await cr.search("Acme Ltd", "UK")
"""

from pathlib import Path

TORPEDO_ROOT = Path(__file__).parent
PROCESSING_DIR = TORPEDO_ROOT / "PROCESSING"
EXECUTION_DIR = TORPEDO_ROOT / "EXECUTION"

# Searchers from EXECUTION
from .EXECUTION.base_searcher import BaseSearcher
from .EXECUTION.cr_searcher import CRSearcher
from .EXECUTION.news_searcher import NewsSearcher

# SEEKLEECH components
from .PROCESSING.SEEKLEECH.taxonomy import THEMATIC_TAXONOMY
from .PROCESSING.SEEKLEECH.schemas import InputSchema, OutputSchema
