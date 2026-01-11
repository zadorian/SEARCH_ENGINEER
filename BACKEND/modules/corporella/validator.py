#!/usr/bin/env python3
"""Validate execution results for completeness and data quality."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Callable

from orchestrator import ExecutionResult, ExecutionStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "event": "%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)


class ValidationSeverity(str, Enum):
    """Validation issue severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationIssue:
    """Individual validation issue."""

    severity: ValidationSeverity
    field: str
    message: str
    actual_value: Optional[Any] = None
    expected_value: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "severity": self.severity.value,
            "field": self.field,
            "message": self.message,
            "actual_value": str(self.actual_value) if self.actual_value is not None else None,
            "expected_value": str(self.expected_value) if self.expected_value is not None else None,
        }


@dataclass
class ValidationResult:
    """Result of validating an ExecutionResult."""

    execution_id: str
    is_valid: bool
    confidence_score: float  # 0.0 to 1.0
    issues: List[ValidationIssue] = field(default_factory=list)
    warnings_count: int = 0
    errors_count: int = 0
    critical_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "execution_id": self.execution_id,
            "is_valid": self.is_valid,
            "confidence_score": round(self.confidence_score, 2),
            "warnings_count": self.warnings_count,
            "errors_count": self.errors_count,
            "critical_count": self.critical_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


class ValidationRule:
    """Base class for validation rules."""

    def __init__(self, name: str, severity: ValidationSeverity = ValidationSeverity.ERROR):
        """Initialize validation rule.

        Args:
            name: Rule name
            severity: Default severity for issues
        """
        self.name = name
        self.severity = severity

    def validate(self, result: ExecutionResult) -> List[ValidationIssue]:
        """Validate execution result.

        Args:
            result: ExecutionResult to validate

        Returns:
            List of validation issues (empty if valid)
        """
        raise NotImplementedError("Subclasses must implement validate()")


class RequiredFieldRule(ValidationRule):
    """Validate that required fields are present and non-empty."""

    def __init__(self, required_fields: List[str], severity: ValidationSeverity = ValidationSeverity.ERROR):
        """Initialize rule.

        Args:
            required_fields: List of required field names
            severity: Issue severity
        """
        super().__init__("required_fields", severity)
        self.required_fields = required_fields

    def validate(self, result: ExecutionResult) -> List[ValidationIssue]:
        """Check for required fields."""
        issues = []

        for field_name in self.required_fields:
            value = getattr(result, field_name, None)

            if value is None or (isinstance(value, str) and not value.strip()):
                issues.append(ValidationIssue(
                    severity=self.severity,
                    field=field_name,
                    message=f"Required field '{field_name}' is missing or empty",
                    actual_value=value,
                    expected_value="non-empty value",
                ))

        return issues


class DataCompletenessRule(ValidationRule):
    """Validate that data dictionary has expected keys."""

    def __init__(self, expected_keys: List[str], severity: ValidationSeverity = ValidationSeverity.WARNING):
        """Initialize rule.

        Args:
            expected_keys: Expected keys in data dictionary
            severity: Issue severity
        """
        super().__init__("data_completeness", severity)
        self.expected_keys = expected_keys

    def validate(self, result: ExecutionResult) -> List[ValidationIssue]:
        """Check data completeness."""
        issues = []

        if result.status != ExecutionStatus.SUCCESS:
            return issues

        if not result.data:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                field="data",
                message="Data dictionary is missing for successful execution",
                actual_value=None,
                expected_value="non-empty dictionary",
            ))
            return issues

        missing_keys = [key for key in self.expected_keys if key not in result.data]

        for key in missing_keys:
            issues.append(ValidationIssue(
                severity=self.severity,
                field=f"data.{key}",
                message=f"Expected data key '{key}' is missing",
                actual_value=None,
                expected_value=key,
            ))

        return issues


class PerformanceRule(ValidationRule):
    """Validate execution performance against SLA."""

    def __init__(self, max_duration_ms: int, severity: ValidationSeverity = ValidationSeverity.WARNING):
        """Initialize rule.

        Args:
            max_duration_ms: Maximum acceptable duration in milliseconds
            severity: Issue severity
        """
        super().__init__("performance", severity)
        self.max_duration_ms = max_duration_ms

    def validate(self, result: ExecutionResult) -> List[ValidationIssue]:
        """Check performance."""
        issues = []

        if result.duration_ms > self.max_duration_ms:
            issues.append(ValidationIssue(
                severity=self.severity,
                field="duration_ms",
                message=f"Execution exceeded SLA ({result.duration_ms}ms > {self.max_duration_ms}ms)",
                actual_value=result.duration_ms,
                expected_value=f"<= {self.max_duration_ms}ms",
            ))

        return issues


class EntityMatchRule(ValidationRule):
    """Validate that result data mentions the queried entity."""

    def __init__(self, severity: ValidationSeverity = ValidationSeverity.WARNING):
        """Initialize rule."""
        super().__init__("entity_match", severity)

    def validate(self, result: ExecutionResult) -> List[ValidationIssue]:
        """Check entity match."""
        issues = []

        if result.status != ExecutionStatus.SUCCESS or not result.parsed_query:
            return issues

        entity_name = result.parsed_query.entity_name
        if not entity_name:
            return issues

        # Check if entity appears in data
        data_str = json.dumps(result.data).lower() if result.data else ""
        entity_lower = entity_name.lower()

        if entity_lower not in data_str:
            issues.append(ValidationIssue(
                severity=self.severity,
                field="data",
                message=f"Result data does not mention queried entity '{entity_name}'",
                actual_value="entity not found in data",
                expected_value=f"data containing '{entity_name}'",
            ))

        return issues


class Validator:
    """Validate execution results for completeness and data quality.

    Features:
    - Configurable validation rules
    - Confidence scoring
    - Issue categorization by severity
    - Batch validation support
    """

    def __init__(
        self,
        rules: Optional[List[ValidationRule]] = None,
        min_confidence_threshold: float = 0.5,
    ):
        """Initialize validator.

        Args:
            rules: List of validation rules (uses defaults if None)
            min_confidence_threshold: Minimum confidence for valid results
        """
        self.rules = rules or self._default_rules()
        self.min_confidence_threshold = min_confidence_threshold

        logger.info(f"Validator initialized with {len(self.rules)} rules")

    def _default_rules(self) -> List[ValidationRule]:
        """Get default validation rules.

        Returns:
            List of default validation rules
        """
        return [
            RequiredFieldRule(
                required_fields=["execution_id", "query", "status", "duration_ms"],
                severity=ValidationSeverity.CRITICAL,
            ),
            DataCompletenessRule(
                expected_keys=["entity_name", "country_code", "source_type"],
                severity=ValidationSeverity.WARNING,
            ),
            PerformanceRule(
                max_duration_ms=30000,  # 30 seconds
                severity=ValidationSeverity.INFO,
            ),
            EntityMatchRule(
                severity=ValidationSeverity.WARNING,
            ),
        ]

    def validate(self, result: ExecutionResult) -> ValidationResult:
        """Validate a single execution result.

        Args:
            result: ExecutionResult to validate

        Returns:
            ValidationResult with issues and confidence score
        """
        all_issues: List[ValidationIssue] = []

        # Run all validation rules
        for rule in self.rules:
            try:
                issues = rule.validate(result)
                all_issues.extend(issues)
            except Exception as e:
                logger.error(f"Validation rule '{rule.name}' failed: {e}")
                all_issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    field="validator",
                    message=f"Validation rule '{rule.name}' failed: {e}",
                ))

        # Count issues by severity
        warnings_count = sum(1 for i in all_issues if i.severity == ValidationSeverity.WARNING)
        errors_count = sum(1 for i in all_issues if i.severity == ValidationSeverity.ERROR)
        critical_count = sum(1 for i in all_issues if i.severity == ValidationSeverity.CRITICAL)

        # Calculate confidence score
        confidence_score = self._calculate_confidence(result, all_issues)

        # Determine if valid
        is_valid = (
            result.status == ExecutionStatus.SUCCESS
            and critical_count == 0
            and confidence_score >= self.min_confidence_threshold
        )

        validation_result = ValidationResult(
            execution_id=result.execution_id,
            is_valid=is_valid,
            confidence_score=confidence_score,
            issues=all_issues,
            warnings_count=warnings_count,
            errors_count=errors_count,
            critical_count=critical_count,
        )

        logger.info(
            f"Validation completed: {result.execution_id} - "
            f"valid={is_valid}, confidence={confidence_score:.2f}, "
            f"issues={len(all_issues)} (C:{critical_count} E:{errors_count} W:{warnings_count})"
        )

        return validation_result

    def validate_batch(self, results: List[ExecutionResult]) -> List[ValidationResult]:
        """Validate multiple execution results.

        Args:
            results: List of ExecutionResult objects

        Returns:
            List of ValidationResult objects
        """
        logger.info(f"Batch validation started: {len(results)} results")

        validation_results = [self.validate(result) for result in results]

        valid_count = sum(1 for vr in validation_results if vr.is_valid)
        logger.info(f"Batch validation completed: {valid_count}/{len(results)} valid")

        return validation_results

    def _calculate_confidence(
        self,
        result: ExecutionResult,
        issues: List[ValidationIssue],
    ) -> float:
        """Calculate confidence score based on result and issues.

        Args:
            result: ExecutionResult
            issues: List of validation issues

        Returns:
            Confidence score between 0.0 and 1.0
        """
        # Start with base score
        if result.status != ExecutionStatus.SUCCESS:
            return 0.0

        confidence = 1.0

        # Deduct points for issues
        for issue in issues:
            if issue.severity == ValidationSeverity.CRITICAL:
                confidence -= 0.5
            elif issue.severity == ValidationSeverity.ERROR:
                confidence -= 0.2
            elif issue.severity == ValidationSeverity.WARNING:
                confidence -= 0.1
            elif issue.severity == ValidationSeverity.INFO:
                confidence -= 0.05

        # Data completeness bonus
        if result.data and len(result.data) > 3:
            confidence += 0.1

        # Entity match bonus
        if result.parsed_query and result.parsed_query.entity_name and result.data:
            data_str = json.dumps(result.data).lower()
            if result.parsed_query.entity_name.lower() in data_str:
                confidence += 0.1

        return max(0.0, min(1.0, confidence))

    def add_rule(self, rule: ValidationRule) -> None:
        """Add a validation rule.

        Args:
            rule: Validation rule to add
        """
        self.rules.append(rule)
        logger.info(f"Added validation rule: {rule.name}")

    def get_stats(self, validation_results: List[ValidationResult]) -> Dict[str, Any]:
        """Get validation statistics.

        Args:
            validation_results: List of validation results

        Returns:
            Dictionary with statistics
        """
        if not validation_results:
            return {
                "total_results": 0,
                "valid_count": 0,
                "invalid_count": 0,
                "avg_confidence": 0.0,
                "total_issues": 0,
            }

        valid_count = sum(1 for vr in validation_results if vr.is_valid)
        total_issues = sum(len(vr.issues) for vr in validation_results)
        avg_confidence = sum(vr.confidence_score for vr in validation_results) / len(validation_results)

        return {
            "total_results": len(validation_results),
            "valid_count": valid_count,
            "invalid_count": len(validation_results) - valid_count,
            "validation_rate": valid_count / len(validation_results) if validation_results else 0.0,
            "avg_confidence": round(avg_confidence, 2),
            "total_issues": total_issues,
            "avg_issues_per_result": round(total_issues / len(validation_results), 2),
        }


if __name__ == "__main__":
    # Quick test
    import sys
    from datetime import datetime
    from query_parser import ParsedQuery
    from query_router import RouteMode

    print("Testing Validator...")

    try:
        # Create test execution result
        test_result = ExecutionResult(
            execution_id="test_001",
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
            },
            timestamp=datetime.now(),
        )

        # Create validator
        validator = Validator()

        # Validate
        validation_result = validator.validate(test_result)

        print(f"✓ Validation completed")
        print(f"  Valid: {validation_result.is_valid}")
        print(f"  Confidence: {validation_result.confidence_score:.2f}")
        print(f"  Issues: {len(validation_result.issues)}")

        if validation_result.issues:
            print("\n  Issues found:")
            for issue in validation_result.issues:
                print(f"    [{issue.severity.value}] {issue.field}: {issue.message}")

        print("\n✓ All tests passed!")

    except Exception as e:
        print(f"\n✗ Test failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
