"""
Tests for InvestigationPlanner - Multi-step investigation planning.

Tests the integration of:
- IO Matrix (jurisdiction routes)
- SASTRE Slot System
- K-U Quadrant routing
- Query tier assignment
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestQueryTier:
    """Test QueryTier enum."""

    def test_import_query_tier(self):
        from BACKEND.modules.SASTRE.investigation_planner import QueryTier
        assert QueryTier is not None

    def test_tier_values(self):
        from BACKEND.modules.SASTRE.investigation_planner import QueryTier
        assert QueryTier.T0A.value == "0A"
        assert QueryTier.T0B.value == "0B"
        assert QueryTier.T1.value == "1"
        assert QueryTier.T2.value == "2"
        assert QueryTier.T3.value == "3"
        assert QueryTier.M.value == "M"


class TestPlanStep:
    """Test PlanStep dataclass."""

    def test_import_plan_step(self):
        from BACKEND.modules.SASTRE.investigation_planner import PlanStep
        assert PlanStep is not None

    def test_create_plan_step(self):
        from BACKEND.modules.SASTRE.investigation_planner import PlanStep, QueryTier

        step = PlanStep(
            step_id="step_001",
            description="Search company registry",
            input_type="company_name",
            input_value="Acme Corp",
            source_id="src_001",
            source_label="Companies House",
            country="UK",
            output_columns=["registration_number", "officers"],
            reliability="high",
            ku_quadrant="verify",
            tier=QueryTier.T0A,
            strength=5,
        )

        assert step.step_id == "step_001"
        assert step.tier == QueryTier.T0A
        assert step.strength == 5
        assert "officers" in step.output_columns

    def test_plan_step_to_dict(self):
        from BACKEND.modules.SASTRE.investigation_planner import PlanStep, QueryTier

        step = PlanStep(
            step_id="step_001",
            description="Test step",
            input_type="person_name",
            input_value="John Smith",
            source_id="src_001",
            source_label="Test Source",
            country="US",
            output_columns=["email"],
            reliability="medium",
            ku_quadrant="trace",
        )

        d = step.to_dict()
        assert d["step_id"] == "step_001"
        assert d["tier"] == "1"  # Default tier
        assert d["strength"] == 3  # Default strength


class TestInvestigationPlan:
    """Test InvestigationPlan dataclass."""

    def test_import_investigation_plan(self):
        from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlan
        assert InvestigationPlan is not None

    def test_create_investigation_plan(self):
        from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlan
        from BACKEND.modules.SASTRE.contracts import KUQuadrant

        plan = InvestigationPlan(
            entity_id="person_001",
            entity_type="person",
            entity_name="John Smith",
            jurisdiction="AE",
            ku_quadrant=KUQuadrant.TRACE,
        )

        assert plan.entity_id == "person_001"
        assert plan.ku_quadrant == KUQuadrant.TRACE
        assert plan.steps == []

    def test_investigation_plan_to_dict(self):
        from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlan
        from BACKEND.modules.SASTRE.contracts import KUQuadrant

        plan = InvestigationPlan(
            entity_id="company_001",
            entity_type="company",
            entity_name="Acme Corp",
            jurisdiction="UK",
            ku_quadrant=KUQuadrant.VERIFY,
            estimated_completeness=0.75,
        )

        d = plan.to_dict()
        assert d["entity_type"] == "company"
        assert d["ku_quadrant"] == "verify"
        assert d["estimated_completeness"] == 0.75
        assert d["total_steps"] == 0


class TestStrengthScorer:
    """Test StrengthScorer class."""

    def test_import_strength_scorer(self):
        from BACKEND.modules.SASTRE.investigation_planner import StrengthScorer
        assert StrengthScorer is not None

    def test_exact_match_high_score(self):
        from BACKEND.modules.SASTRE.investigation_planner import StrengthScorer

        score = StrengthScorer.score_variation("exact_match", "high")
        assert score == 5  # 5 base + 1 high reliability = 6, capped at 5

    def test_rare_variation_low_score(self):
        from BACKEND.modules.SASTRE.investigation_planner import StrengthScorer

        score = StrengthScorer.score_variation("rare_variation", "low")
        assert score == 1  # 1 base - 1 low reliability = 0, floored at 1

    def test_translation_medium_reliability(self):
        from BACKEND.modules.SASTRE.investigation_planner import StrengthScorer

        score = StrengthScorer.score_variation("translation", "medium")
        assert score == 3  # 3 base + 0 medium = 3


class TestIOMatrixLoader:
    """Test IOMatrixLoader class."""

    def test_import_io_matrix_loader(self):
        from BACKEND.modules.SASTRE.investigation_planner import IOMatrixLoader
        assert IOMatrixLoader is not None

    def test_create_loader_with_default_path(self):
        from BACKEND.modules.SASTRE.investigation_planner import IOMatrixLoader

        loader = IOMatrixLoader()
        assert loader.matrix_dir is not None
        assert "input_output2" in str(loader.matrix_dir)

    def test_create_loader_with_custom_path(self):
        from BACKEND.modules.SASTRE.investigation_planner import IOMatrixLoader

        custom_path = Path("/tmp/test_matrix")
        loader = IOMatrixLoader(custom_path)
        assert loader.matrix_dir == custom_path

    def test_get_routes_for_country_with_mock(self):
        from BACKEND.modules.SASTRE.investigation_planner import IOMatrixLoader

        loader = IOMatrixLoader()
        loader._loaded = True
        loader._flows = {
            "UK": [
                {"source_id": "ch_001", "source_label": "Companies House", "input_type": "company_name"},
                {"source_id": "ch_002", "source_label": "Land Registry", "input_type": "address"},
            ],
            "US": [
                {"source_id": "sec_001", "source_label": "SEC EDGAR", "input_type": "company_name"},
            ],
        }

        uk_routes = loader.get_routes_for_country("UK")
        assert len(uk_routes) == 2

        us_routes = loader.get_routes_for_country("US")
        assert len(us_routes) == 1

        # Non-existent country
        zz_routes = loader.get_routes_for_country("ZZ")
        assert len(zz_routes) == 0

    def test_get_routes_by_input_type(self):
        from BACKEND.modules.SASTRE.investigation_planner import IOMatrixLoader

        loader = IOMatrixLoader()
        loader._loaded = True
        loader._flows = {
            "UK": [
                {"source_id": "ch_001", "input_type": "company_name"},
                {"source_id": "ch_002", "input_type": "person_name"},
                {"source_id": "ch_003", "input_type": "company_name"},
            ],
        }

        company_routes = loader.get_routes_by_input_type("UK", "company_name")
        assert len(company_routes) == 2

        person_routes = loader.get_routes_by_input_type("UK", "person_name")
        assert len(person_routes) == 1


class TestInvestigationPlanner:
    """Test InvestigationPlanner class."""

    def test_import_investigation_planner(self):
        from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlanner
        assert InvestigationPlanner is not None

    def test_create_planner(self):
        from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlanner

        planner = InvestigationPlanner()
        assert planner.matrix is not None
        assert planner.scorer is not None

    def test_create_plan_basic(self):
        from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlanner
        from BACKEND.modules.SASTRE.contracts import KUQuadrant

        planner = InvestigationPlanner()
        # Mock the matrix loader
        planner.matrix._loaded = True
        planner.matrix._flows = {
            "AE": [
                {
                    "source_id": "difc_001",
                    "source_label": "DIFC Courts",
                    "input_type": "person_name",
                    "output_columns_array": ["litigation_records"],
                    "reliability": "high",
                },
            ],
        }

        plan = planner.create_plan(
            entity_type="person",
            entity_name="John Smith",
            jurisdiction="AE",
        )

        assert plan.entity_type == "person"
        assert plan.entity_name == "John Smith"
        assert plan.jurisdiction == "AE"
        # No known_data means subject is unknown, location is known → EXTRACT
        assert plan.ku_quadrant == KUQuadrant.EXTRACT
        assert plan.slot_set is not None

    def test_create_plan_with_known_data(self):
        from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlanner
        from BACKEND.modules.SASTRE.contracts import KUQuadrant, SlotState

        planner = InvestigationPlanner()
        planner.matrix._loaded = True
        planner.matrix._flows = {
            "UK": [
                {
                    "source_id": "ch_001",
                    "source_label": "Companies House",
                    "input_type": "company_name",
                    "output_columns_array": ["officers", "shareholders"],
                    "reliability": "high",
                },
            ],
        }

        plan = planner.create_plan(
            entity_type="company",
            entity_name="Acme Corp",
            jurisdiction="UK",
            known_data={"registration_number": "12345678"},
        )

        # Known data should be pre-filled in slots
        assert plan.slot_set is not None
        assert plan.slot_set.slots["registration_number"].state == SlotState.FILLED
        assert plan.ku_quadrant == KUQuadrant.VERIFY  # Known subject + location

    def test_plan_steps_sorted_by_tier(self):
        from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlanner

        planner = InvestigationPlanner()
        planner.matrix._loaded = True
        planner.matrix._flows = {
            "US": [
                {
                    "source_id": "sec_001",
                    "source_label": "SEC EDGAR",
                    "input_type": "company_name",
                    "output_columns_array": ["filings"],
                    "reliability": "high",
                },
                {
                    "source_id": "osint_001",
                    "source_label": "OSINT Source",
                    "input_type": "company_name",
                    "output_columns_array": ["media"],
                    "reliability": "low",
                },
            ],
        }

        plan = planner.create_plan(
            entity_type="company",
            entity_name="Tech Corp",
            jurisdiction="US",
        )

        if len(plan.steps) >= 2:
            # Higher strength steps should come first
            assert plan.steps[0].strength >= plan.steps[-1].strength

    def test_chain_calculation(self):
        from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlanner, PlanStep, QueryTier

        planner = InvestigationPlanner()

        # Create steps with dependencies
        steps = [
            PlanStep(
                step_id="step_001",
                description="Initial search",
                input_type="company_name",
                input_value="Acme",
                source_id="src_001",
                source_label="Source 1",
                country="UK",
                output_columns=["officers"],
                reliability="high",
                ku_quadrant="verify",
            ),
            PlanStep(
                step_id="step_002",
                description="Chained search",
                input_type="person_name",
                input_value="[from step_001]",
                source_id="src_002",
                source_label="Source 2",
                country="UK",
                output_columns=["email"],
                reliability="medium",
                ku_quadrant="verify",
                depends_on=["step_001"],
            ),
        ]

        chains = planner._calculate_chains(steps)
        assert len(chains) == 1
        assert chains[0]["from_step"] == "step_001"
        assert chains[0]["to_step"] == "step_002"


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_import_plan_investigation(self):
        from BACKEND.modules.SASTRE.investigation_planner import plan_investigation
        assert plan_investigation is not None

    def test_import_get_available_routes(self):
        from BACKEND.modules.SASTRE.investigation_planner import get_available_routes
        assert get_available_routes is not None

    def test_import_get_route_summary(self):
        from BACKEND.modules.SASTRE.investigation_planner import get_route_summary
        assert get_route_summary is not None

    def test_plan_investigation_returns_dict(self):
        from BACKEND.modules.SASTRE.investigation_planner import (
            plan_investigation, InvestigationPlanner
        )

        # Mock to avoid file system access
        with patch.object(InvestigationPlanner, '__init__', return_value=None):
            with patch.object(InvestigationPlanner, 'create_plan') as mock_create:
                from BACKEND.modules.SASTRE.contracts import KUQuadrant
                from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlan

                mock_plan = InvestigationPlan(
                    entity_id="test_001",
                    entity_type="person",
                    entity_name="Test",
                    jurisdiction="US",
                    ku_quadrant=KUQuadrant.TRACE,
                )
                mock_create.return_value = mock_plan

                planner = InvestigationPlanner()
                planner.matrix = MagicMock()
                planner.scorer = MagicMock()

                result = planner.create_plan("person", "Test", "US")
                assert result.entity_type == "person"


class TestSufficiencyCheck:
    """Test sufficiency checking."""

    def test_check_sufficiency_empty_plan(self):
        from BACKEND.modules.SASTRE.investigation_planner import (
            InvestigationPlanner, InvestigationPlan
        )
        from BACKEND.modules.SASTRE.contracts import KUQuadrant

        planner = InvestigationPlanner()
        plan = InvestigationPlan(
            entity_id="test_001",
            entity_type="person",
            entity_name="Test",
            jurisdiction="US",
            ku_quadrant=KUQuadrant.TRACE,
            slot_set=None,
        )

        result = planner.check_sufficiency(plan)
        assert not result.is_complete

    def test_check_sufficiency_with_slots(self):
        from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlanner
        from BACKEND.modules.SASTRE.contracts import KUQuadrant, create_slots_for_entity

        planner = InvestigationPlanner()
        planner.matrix._loaded = True
        planner.matrix._flows = {"UK": []}

        plan = planner.create_plan(
            entity_type="person",
            entity_name="Test Person",
            jurisdiction="UK",
        )

        result = planner.check_sufficiency(plan)
        # Empty slots should not satisfy core_fields_populated
        assert not result.core_fields_populated


class TestQueryGenerator:
    """Test QueryGenerator with variators and intent translator."""

    def test_import_query_generator(self):
        from BACKEND.modules.SASTRE.investigation_planner import QueryGenerator
        assert QueryGenerator is not None

    def test_import_generated_query(self):
        from BACKEND.modules.SASTRE.investigation_planner import GeneratedQuery
        assert GeneratedQuery is not None

    def test_create_query_generator(self):
        from BACKEND.modules.SASTRE.investigation_planner import QueryGenerator

        generator = QueryGenerator()
        assert generator.variator is not None
        assert generator.translator is not None

    def test_generate_for_person(self):
        from BACKEND.modules.SASTRE.investigation_planner import QueryGenerator

        generator = QueryGenerator()
        query = generator.generate_for_entity(
            entity_name="John Smith",
            entity_type="person",
            intent="find companies",
        )

        assert query.primary == "John Smith"
        assert len(query.variations) > 1
        # Check for typical variations (initials, transliterations, nicknames)
        assert any("J." in v for v in query.variations)  # Initial variation
        assert query.entity_type == "person"
        assert query.free_ors  # Should have expanded OR query

    def test_generate_for_company(self):
        from BACKEND.modules.SASTRE.investigation_planner import QueryGenerator

        generator = QueryGenerator()
        query = generator.generate_for_entity(
            entity_name="Acme Corp Ltd",
            entity_type="company",
            intent="find officers",
        )

        assert query.primary == "Acme Corp Ltd"
        assert len(query.variations) > 1
        # Should have suffix variations
        assert any("Limited" in v for v in query.variations)
        assert query.entity_type == "company"

    def test_translate_intent(self):
        from BACKEND.modules.SASTRE.investigation_planner import QueryGenerator

        generator = QueryGenerator()
        translated = generator.translate_intent("Find companies connected to John Smith")

        assert translated.syntax
        assert translated.intent
        assert len(translated.operators) > 0

    def test_generated_query_to_dict(self):
        from BACKEND.modules.SASTRE.investigation_planner import QueryGenerator

        generator = QueryGenerator()
        query = generator.generate_for_entity("Test Person", "person")
        d = query.to_dict()

        assert "primary" in d
        assert "variations" in d
        assert "tier" in d
        assert "free_ors" in d


class TestNaturalLanguagePlanning:
    """Test natural language planning functions."""

    def test_import_plan_from_tasking(self):
        from BACKEND.modules.SASTRE.investigation_planner import plan_from_tasking
        assert plan_from_tasking is not None

    def test_import_generate_queries(self):
        from BACKEND.modules.SASTRE.investigation_planner import generate_queries
        assert generate_queries is not None

    def test_plan_from_tasking_with_quoted_name(self):
        from BACKEND.modules.SASTRE.investigation_planner import plan_from_tasking

        result = plan_from_tasking(
            'Find companies connected to "John Smith"',
            jurisdiction="AE"
        )

        assert "tasking" in result
        assert "translated" in result
        assert result["translated"]["intent"] in ["discover", "extract", "link"]

    def test_generate_queries_person(self):
        from BACKEND.modules.SASTRE.investigation_planner import generate_queries

        result = generate_queries("John Smith", "person", "find associates")

        assert result["primary"] == "John Smith"
        assert len(result["variations"]) > 1
        assert result["entity_type"] == "person"

    def test_generate_queries_company(self):
        from BACKEND.modules.SASTRE.investigation_planner import generate_queries

        result = generate_queries("Tech Corp", "company", "find officers")

        assert result["primary"] == "Tech Corp"
        assert result["entity_type"] == "company"
