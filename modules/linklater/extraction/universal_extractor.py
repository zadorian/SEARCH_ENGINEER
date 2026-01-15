#!/usr/bin/env python3
"""
DEPRECATED: UniversalExtractor has moved to CYMONIDES module.

This stub re-exports from the new location for backwards compatibility.
Update your imports to: from BACKEND.modules.cymonides.extraction.universal_extractor import UniversalExtractor
"""

import warnings
from pathlib import Path
import importlib.util

warnings.warn(
    "universal_extractor has moved to BACKEND.modules.cymonides.extraction. "
    "Update your imports.",
    DeprecationWarning,
    stacklevel=2
)

# Import from new location
_cymonides_path = Path(__file__).parent.parent.parent / "CYMONIDES" / "extraction" / "universal_extractor.py"
spec = importlib.util.spec_from_file_location("universal_extractor", _cymonides_path)
_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_module)

# Re-export everything
UniversalExtractor = _module.UniversalExtractor
get_model = _module.get_model
get_golden_embeddings = _module.get_golden_embeddings
get_red_flag_entities = _module.get_red_flag_entities
