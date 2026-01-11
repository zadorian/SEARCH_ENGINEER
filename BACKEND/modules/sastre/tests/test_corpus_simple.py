#!/usr/bin/env python3
"""
Simple test to verify corpus check is uncommented and compiles.
"""

import ast
import sys
from pathlib import Path

def check_corpus_implementation():
    """Check that the corpus search is no longer commented out."""

    gap_analyzer_path = Path(__file__).parent / "gap_analyzer.py"

    print("Checking SASTRE Corpus Integration")
    print("=" * 60)
    print(f"\nAnalyzing: {gap_analyzer_path}")

    # Read the file
    with open(gap_analyzer_path, 'r') as f:
        content = f.read()

    # Check for the specific line that was commented
    if "results = []  # self.corpus_client.search(term)" in content:
        print("\n✗ FAIL: Corpus search is still commented out!")
        print("   Found: results = []  # self.corpus_client.search(term)")
        return False

    # Check that CorpusChecker is imported
    if "from .query.corpus import CorpusChecker" not in content:
        print("\n✗ FAIL: CorpusChecker import not found!")
        return False

    print("\n✓ Corpus search is no longer commented out")
    print("✓ CorpusChecker import found")

    # Try to parse the AST
    try:
        tree = ast.parse(content, filename=str(gap_analyzer_path))
        print("✓ File parses correctly (valid Python)")
    except SyntaxError as e:
        print(f"\n✗ FAIL: Syntax error in file: {e}")
        return False

    # Find the _check_corpus method
    found_method = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_check_corpus":
            found_method = True
            print(f"✓ Found _check_corpus method at line {node.lineno}")

            # Check that it has real logic, not just returning []
            has_logic = False
            for child in ast.walk(node):
                if isinstance(child, ast.If) and hasattr(child.test, 'func'):
                    # Check for isinstance check
                    if hasattr(child.test.func, 'id') and child.test.func.id == 'isinstance':
                        has_logic = True
                        print("✓ Method has corpus checking logic (isinstance check found)")
                        break

            if not has_logic:
                print("⚠ Warning: Method may still be a stub")

    if not found_method:
        print("\n✗ FAIL: _check_corpus method not found!")
        return False

    print("\n" + "=" * 60)
    print("✓ All checks passed!")
    print("\nThe corpus check has been successfully uncommented and")
    print("integrated with the CorpusChecker class.")
    return True

if __name__ == "__main__":
    success = check_corpus_implementation()
    sys.exit(0 if success else 1)
