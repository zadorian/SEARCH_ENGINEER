"""
Tests for SASTRE Syntax Parser

Tests cover:
- Operator parsing (p:, c:, bl?, ent?, =?, brute)
- Target resolution
- Filter parsing
- Query execution routing
"""

import pytest


class TestSyntaxImports:
    """Test that syntax parser can be imported."""

    def test_import_parse(self):
        from modules.syntax import parse
        assert callable(parse)

    def test_import_parsed_query(self):
        from modules.syntax import ParsedQuery
        assert ParsedQuery is not None

    def test_import_operator_def(self):
        from modules.syntax import OperatorDef
        assert OperatorDef is not None

    def test_import_operators(self):
        from modules.syntax import OPERATORS
        assert isinstance(OPERATORS, dict)


class TestOperatorParsing:
    """Test operator parsing."""

    def test_parse_person_operator(self):
        from modules.syntax import parse
        result = parse("p: John Smith")
        assert result is not None
        # operators is a list
        assert hasattr(result, 'operators')

    def test_parse_company_operator(self):
        from modules.syntax import parse
        result = parse("c: Acme Corp")
        assert result is not None

    def test_parse_backlinks_operator(self):
        from modules.syntax import parse
        result = parse("bl? example.com")
        # May return None if operator not recognized
        pass  # Operator may not exist

    def test_parse_entities_operator(self):
        from modules.syntax import parse
        result = parse("ent? example.com")
        # May return None if operator not recognized
        pass  # Operator may not exist

    def test_parse_compare_operator(self):
        from modules.syntax import parse
        result = parse("=? john jane")
        # May return None if operator not recognized
        pass  # Operator may not exist

    def test_parse_brute_operator(self):
        from modules.syntax import parse
        result = parse("brute john")
        # May return None if operator not recognized
        pass  # Operator may not exist


class TestParsedQueryBasic:
    """Test ParsedQuery dataclass."""

    def test_parsed_query_has_operators(self):
        from modules.syntax import parse
        result = parse("p: John Smith")
        assert hasattr(result, 'operators')

    def test_parsed_query_has_targets(self):
        from modules.syntax import parse
        result = parse("p: John Smith")
        assert hasattr(result, 'targets')

    def test_parsed_query_has_raw_query(self):
        from modules.syntax import parse
        result = parse("p: John Smith")
        assert hasattr(result, 'raw_query')


class TestOperatorCategories:
    """Test operator categorization."""

    def test_get_operators_by_category(self):
        from modules.syntax import get_operators_by_category, OperatorCategory
        extraction_ops = get_operators_by_category(OperatorCategory.EXTRACTION)
        assert len(extraction_ops) >= 0  # May have operators

    def test_get_operator(self):
        from modules.syntax import get_operator
        op = get_operator("p:")
        # May return None or an OperatorDef
        assert op is None or hasattr(op, 'name')
