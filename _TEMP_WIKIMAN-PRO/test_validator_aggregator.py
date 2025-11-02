#!/usr/bin/env python3
"""Unit tests for validator.py and aggregator.py."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from validator import (
    Validator,
    ValidationResult,
    ValidationIssue,
    ValidationSeverity,
    RequiredFieldRule,
    DataCompletenessRule,
    PerformanceRule,
    EntityMatchRule,
)
from aggregator import (
    Aggregator,
    AggregatedResult,
    OutputFormat,
)
from orchestrator import ExecutionResult, ExecutionStatus
from query_parser import ParsedQuery
from query_router import RouteMode


@pytest.fixture
def successful_result():
    """Create successful execution result."""
    return ExecutionResult(
        execution_id="exec_001",
        query="Get Hungarian corporate info for MOL Group",
        parsed_query=ParsedQuery(
            country_code="hu",
            country_name="hungary",
            source_type="corporate_registry",
            entity_name="MOL Group",
            original_query="Get Hungarian corporate info for MOL Group",
        ),
        mode=RouteMode.REPLAY,
        status=ExecutionStatus.SUCCESS,
        duration_ms=1500,
        data={
            "entity_name": "MOL Group",
            "country_code": "hu",
            "source_type": "corporate_registry",
            "company_status": "active",
            "registration_number": "12345",
        },
        timestamp=datetime.now(),
    )


@pytest.fixture
def incomplete_result():
    """Create incomplete execution result (missing data)."""
    return ExecutionResult(
        execution_id="exec_002",
        query="Get German corporate info for Siemens AG",
        parsed_query=ParsedQuery(
            country_code="de",
            country_name="germany",
            source_type="corporate_registry",
            entity_name="Siemens AG",
            original_query="Get German corporate info for Siemens AG",
        ),
        mode=RouteMode.AI,
        status=ExecutionStatus.SUCCESS,
        duration_ms=2500,
        data={
            "country_code": "de",
            # Missing entity_name and source_type
        },
        timestamp=datetime.now(),
    )


@pytest.fixture
def failed_result():
    """Create failed execution result."""
    return ExecutionResult(
        execution_id="exec_003",
        query="Get UK corporate info for BP",
        parsed_query=ParsedQuery(
            country_code="gb",
            country_name="uk",
            source_type="corporate_registry",
            entity_name="BP",
            original_query="Get UK corporate info for BP",
        ),
        mode=RouteMode.REPLAY,
        status=ExecutionStatus.ERROR,
        duration_ms=500,
        error_type="NetworkError",
        error_message="Connection timeout",
        timestamp=datetime.now(),
    )


class TestValidationRules:
    """Tests for individual validation rules."""

    def test_required_field_rule_passes(self, successful_result):
        """RequiredFieldRule passes with all required fields."""
        rule = RequiredFieldRule(["execution_id", "query", "status"])

        issues = rule.validate(successful_result)

        assert len(issues) == 0

    def test_required_field_rule_fails(self):
        """RequiredFieldRule fails with missing fields."""
        result = ExecutionResult(
            execution_id="",  # Empty
            query="Test query",
            parsed_query=None,
            mode=RouteMode.AI,
            status=ExecutionStatus.SUCCESS,
            duration_ms=1000,
        )

        rule = RequiredFieldRule(["execution_id"])

        issues = rule.validate(result)

        assert len(issues) == 1
        assert issues[0].field == "execution_id"
        assert issues[0].severity == ValidationSeverity.ERROR

    def test_data_completeness_rule_passes(self, successful_result):
        """DataCompletenessRule passes with all expected keys."""
        rule = DataCompletenessRule(["entity_name", "country_code"])

        issues = rule.validate(successful_result)

        assert len(issues) == 0

    def test_data_completeness_rule_fails(self, incomplete_result):
        """DataCompletenessRule fails with missing keys."""
        rule = DataCompletenessRule(["entity_name", "source_type"])

        issues = rule.validate(incomplete_result)

        assert len(issues) == 2  # Both keys missing
        assert any(i.field == "data.entity_name" for i in issues)
        assert any(i.field == "data.source_type" for i in issues)

    def test_performance_rule_passes(self, successful_result):
        """PerformanceRule passes within SLA."""
        rule = PerformanceRule(max_duration_ms=5000)

        issues = rule.validate(successful_result)

        assert len(issues) == 0

    def test_performance_rule_fails(self, successful_result):
        """PerformanceRule fails when exceeding SLA."""
        successful_result.duration_ms = 10000  # Exceed limit
        rule = PerformanceRule(max_duration_ms=5000)

        issues = rule.validate(successful_result)

        assert len(issues) == 1
        assert issues[0].field == "duration_ms"

    def test_entity_match_rule_passes(self, successful_result):
        """EntityMatchRule passes when entity mentioned in data."""
        rule = EntityMatchRule()

        issues = rule.validate(successful_result)

        assert len(issues) == 0

    def test_entity_match_rule_fails(self, incomplete_result):
        """EntityMatchRule fails when entity not in data."""
        rule = EntityMatchRule()

        issues = rule.validate(incomplete_result)

        assert len(issues) == 1
        assert "Siemens AG" in issues[0].message


class TestValidator:
    """Tests for Validator class."""

    def test_validator_initialization(self):
        """Validator initializes with default rules."""
        validator = Validator()

        assert len(validator.rules) > 0
        assert validator.min_confidence_threshold == 0.5

    def test_validate_successful_result(self, successful_result):
        """Validator passes for complete successful result."""
        validator = Validator()

        validation_result = validator.validate(successful_result)

        assert validation_result.is_valid is True
        assert validation_result.confidence_score > 0.7
        assert validation_result.critical_count == 0

    def test_validate_incomplete_result(self, incomplete_result):
        """Validator flags incomplete result."""
        validator = Validator()

        validation_result = validator.validate(incomplete_result)

        # May or may not be valid depending on confidence threshold
        assert validation_result.warnings_count > 0
        assert len(validation_result.issues) > 0

    def test_validate_failed_result(self, failed_result):
        """Validator marks failed execution as invalid."""
        validator = Validator()

        validation_result = validator.validate(failed_result)

        assert validation_result.is_valid is False
        assert validation_result.confidence_score == 0.0

    def test_batch_validation(self, successful_result, incomplete_result, failed_result):
        """Validator validates multiple results."""
        validator = Validator()

        results = [successful_result, incomplete_result, failed_result]
        validation_results = validator.validate_batch(results)

        assert len(validation_results) == 3
        assert isinstance(validation_results[0], ValidationResult)

    def test_confidence_calculation(self, successful_result):
        """Validator calculates confidence scores correctly."""
        validator = Validator()

        # Perfect result
        validation_result = validator.validate(successful_result)
        assert validation_result.confidence_score > 0.8

        # Result with missing data
        successful_result.data = {"country_code": "hu"}  # Minimal data
        validation_result = validator.validate(successful_result)
        assert validation_result.confidence_score < 0.8

    def test_add_custom_rule(self, successful_result):
        """Validator accepts custom rules."""
        validator = Validator()

        initial_count = len(validator.rules)
        custom_rule = RequiredFieldRule(["execution_id"])
        validator.add_rule(custom_rule)

        assert len(validator.rules) == initial_count + 1

        validation_result = validator.validate(successful_result)
        assert validation_result.is_valid is True

    def test_validation_stats(self, successful_result, incomplete_result, failed_result):
        """Validator generates validation statistics."""
        validator = Validator()

        results = [successful_result, incomplete_result, failed_result]
        validation_results = validator.validate_batch(results)

        stats = validator.get_stats(validation_results)

        assert stats["total_results"] == 3
        assert "valid_count" in stats
        assert "avg_confidence" in stats
        assert stats["total_issues"] > 0


class TestAggregator:
    """Tests for Aggregator class."""

    def test_aggregator_initialization(self):
        """Aggregator initializes correctly."""
        aggregator = Aggregator()

        assert aggregator.deduplicate is True
        assert aggregator.validator is not None

    def test_aggregate_empty_results(self):
        """Aggregator handles empty result list."""
        aggregator = Aggregator()

        aggregated = aggregator.aggregate([])

        assert aggregated.total_executions == 0
        assert aggregated.successful_executions == 0

    def test_aggregate_single_result(self, successful_result):
        """Aggregator processes single result."""
        aggregator = Aggregator()

        aggregated = aggregator.aggregate([successful_result])

        assert aggregated.total_executions == 1
        assert aggregated.successful_executions == 1
        assert aggregated.avg_duration_ms == 1500

    def test_aggregate_multiple_results(self, successful_result, incomplete_result, failed_result):
        """Aggregator processes multiple results."""
        aggregator = Aggregator()

        results = [successful_result, incomplete_result, failed_result]
        aggregated = aggregator.aggregate(results, validate=True)

        assert aggregated.total_executions == 3
        assert aggregated.successful_executions == 2
        assert aggregated.failed_executions == 1
        assert aggregated.validation_results is not None
        assert len(aggregated.valid_results) >= 1

    def test_deduplication(self, successful_result):
        """Aggregator removes duplicate results."""
        aggregator = Aggregator(deduplicate=True)

        # Create duplicate
        duplicate = ExecutionResult(
            execution_id="exec_002",  # Different ID
            query=successful_result.query,
            parsed_query=successful_result.parsed_query,
            mode=successful_result.mode,
            status=successful_result.status,
            duration_ms=1600,
            data=successful_result.data,
            timestamp=datetime.now(),
        )

        aggregated = aggregator.aggregate([successful_result, duplicate])

        # Should deduplicate based on country/entity/source_type
        assert aggregated.total_executions == 1

    def test_no_deduplication(self, successful_result):
        """Aggregator keeps duplicates when disabled."""
        aggregator = Aggregator(deduplicate=False)

        # Create duplicate
        duplicate = ExecutionResult(
            execution_id="exec_002",
            query=successful_result.query,
            parsed_query=successful_result.parsed_query,
            mode=successful_result.mode,
            status=successful_result.status,
            duration_ms=1600,
            data=successful_result.data,
            timestamp=datetime.now(),
        )

        aggregated = aggregator.aggregate([successful_result, duplicate])

        assert aggregated.total_executions == 2

    def test_summary_statistics(self, successful_result, failed_result):
        """Aggregator generates summary statistics."""
        aggregator = Aggregator()

        results = [successful_result, failed_result]
        aggregated = aggregator.aggregate(results, validate=True)

        stats = aggregated.summary_stats

        assert "status_breakdown" in stats
        assert "mode_breakdown" in stats
        assert "country_breakdown" in stats
        assert "performance" in stats

    def test_export_json(self, successful_result, incomplete_result):
        """Aggregator exports to JSON."""
        aggregator = Aggregator()

        results = [successful_result, incomplete_result]
        aggregated = aggregator.aggregate(results)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "results.json"

            aggregator.export(aggregated, output_path, OutputFormat.JSON)

            assert output_path.exists()

            # Verify JSON structure
            with open(output_path) as f:
                data = json.load(f)

            assert "metadata" in data
            assert "results" in data
            assert len(data["results"]) == 2

    def test_export_csv(self, successful_result, incomplete_result):
        """Aggregator exports to CSV."""
        aggregator = Aggregator()

        results = [successful_result, incomplete_result]
        aggregated = aggregator.aggregate(results)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "results.csv"

            aggregator.export(aggregated, output_path, OutputFormat.CSV)

            assert output_path.exists()

            # Verify CSV structure
            with open(output_path) as f:
                lines = f.readlines()

            assert len(lines) == 3  # Header + 2 results

    def test_export_jsonl(self, successful_result, incomplete_result):
        """Aggregator exports to JSON Lines."""
        aggregator = Aggregator()

        results = [successful_result, incomplete_result]
        aggregated = aggregator.aggregate(results)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "results.jsonl"

            aggregator.export(aggregated, output_path, OutputFormat.JSON_LINES)

            assert output_path.exists()

            # Verify JSONL structure
            with open(output_path) as f:
                lines = f.readlines()

            assert len(lines) == 2
            # Each line should be valid JSON
            for line in lines:
                json.loads(line)

    def test_export_valid_only(self, successful_result, failed_result):
        """Aggregator exports only valid results when specified."""
        aggregator = Aggregator()

        results = [successful_result, failed_result]
        aggregated = aggregator.aggregate(results, validate=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "results.json"

            # Export valid only
            aggregator.export(aggregated, output_path, OutputFormat.JSON, include_invalid=False)

            with open(output_path) as f:
                data = json.load(f)

            # Should only have successful result
            assert len(data["results"]) == 1
            assert data["results"][0]["status"] == "success"

    def test_merge_data(self, successful_result, incomplete_result):
        """Aggregator merges data by entity."""
        aggregator = Aggregator()

        results = [successful_result, incomplete_result]

        merged = aggregator.merge_data(results, key_field="entity_name")

        # Should have data for MOL Group (Siemens AG has no entity_name in data)
        assert "MOL Group" in merged
        assert merged["MOL Group"]["country_code"] == "hu"


class TestIntegration:
    """Integration tests for validator and aggregator."""

    def test_end_to_end_validation_and_aggregation(self, successful_result, incomplete_result, failed_result):
        """End-to-end test with validation and aggregation."""
        # Create validator and aggregator
        validator = Validator()
        aggregator = Aggregator(validator=validator)

        # Aggregate with validation
        results = [successful_result, incomplete_result, failed_result]
        aggregated = aggregator.aggregate(results, validate=True)

        # Assertions
        assert aggregated.total_executions == 3
        assert aggregated.validation_results is not None
        assert len(aggregated.valid_results) > 0
        assert aggregated.summary_stats["validation"]["total_results"] == 3

        # Export
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "results.json"
            csv_path = Path(tmpdir) / "results.csv"

            aggregator.export(aggregated, json_path, OutputFormat.JSON)
            aggregator.export(aggregated, csv_path, OutputFormat.CSV)

            assert json_path.exists()
            assert csv_path.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
