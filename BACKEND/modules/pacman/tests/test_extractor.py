"""
PACMAN Extractor Tests
"""
import sys
from pathlib import Path

# Add modules to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from PACMAN import UniversalExtractor, extract_all, ExtractionResult


def test_extract_returns_result():
    """Extract should return ExtractionResult."""
    extractor = UniversalExtractor()
    text = "OpenAI announced a funding round in San Francisco."
    result = extractor.extract(text)
    assert isinstance(result, ExtractionResult)


def test_extract_all_convenience():
    """extract_all should return dict."""
    text = "Test document about corporate governance."
    result = extract_all(text)
    assert isinstance(result, dict)


if __name__ == "__main__":
    test_extract_returns_result()
    test_extract_all_convenience()
    print("All tests passed")
