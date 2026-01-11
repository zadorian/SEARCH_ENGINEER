"""
SASTRE Template Bridge - Integration with SASTRE Templates

Connects the SASTRE orchestrator to the template system at:
    ~/.claude/skills/edith-templates/scripts/

This bridge provides:
- route(): Determine jurisdiction/genre/section from tasking
- compose(): Get compiled template context with sections and actions
- validate(): Check section completeness

Usage:
    from SASTRE.bridge.template_bridge import TemplateBridge

    bridge = TemplateBridge()
    routing = bridge.route("DD on Szabo Kft")
    # → {"jurisdiction_id": "hu", "genre_id": "company_dd", "entity_name": "Szabo Kft"}

    composition = bridge.compose(routing)
    # → {"dd_sections": [...], "allowed_actions": [...], "compiled_context": "..."}
"""

import os
import sys
import json
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Template system location (repo-local preferred; fall back to user-installed)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPO_TEMPLATES = _REPO_ROOT / "EDITH" / "templates"
_ENV_TEMPLATE_ROOTS = [
    os.getenv("EDITH_TEMPLATES_DIR"),
    os.getenv("EDITH_TEMPLATES_ROOT"),
    os.getenv("SASTRE_TEMPLATES_DIR"),
]


def _find_templates_dir() -> Path:
    candidates: List[Path] = []

    for root in (p for p in _ENV_TEMPLATE_ROOTS if p):
        candidates.append(Path(root).expanduser())

    candidates.extend([
        _REPO_TEMPLATES,
        Path.home() / ".claude" / "skills" / "edith-templates",
        Path("/Users/attic/01. DRILL_SEARCH/drill-search-app/.claude/skills/edith-templates"),
    ])

    for candidate in candidates:
        try:
            if (candidate / "scripts" / "route.py").exists() and (candidate / "scripts" / "compose.py").exists():
                return candidate
        except Exception:
            continue

    return _REPO_TEMPLATES


TEMPLATES_DIR = _find_templates_dir()
TEMPLATES_CLI = TEMPLATES_DIR / "scripts" / "templates_cli.py"
ROUTE_SCRIPT = TEMPLATES_DIR / "scripts" / "route.py"
COMPOSE_SCRIPT = TEMPLATES_DIR / "scripts" / "compose.py"
VALIDATE_SCRIPT = TEMPLATES_DIR / "scripts" / "validate.py"


@dataclass
class TemplateRouting:
    """Result of routing a tasking to jurisdiction/genre/section."""
    status: str = "unknown"  # exact, ambiguous, error
    jurisdiction_id: Optional[str] = None
    genre_id: Optional[str] = None
    section_id: Optional[str] = None
    entity_name: Optional[str] = None
    entity_detected: bool = False
    confidence_reason: str = ""
    possible_jurisdictions: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TemplateRouting":
        return cls(
            status=data.get("status", "unknown"),
            jurisdiction_id=data.get("jurisdiction_id"),
            genre_id=data.get("genre_id"),
            section_id=data.get("section_id"),
            entity_name=data.get("entity_name"),
            entity_detected=data.get("entity_detected", False),
            confidence_reason=data.get("confidence_reason", ""),
            possible_jurisdictions=data.get("possible_jurisdictions", []),
        )


@dataclass
class TemplateComposition:
    """Result of composing templates for a DD."""
    status: str = "error"
    mode: str = "FULL_DD"  # FULL_DD or SINGLE_SECTION
    manifest_hash: str = ""
    jurisdiction_id: str = ""
    genre_id: str = ""
    entity_name: str = ""
    dd_sections: List[str] = field(default_factory=list)
    optional_sections: List[str] = field(default_factory=list)
    allowed_actions: List[str] = field(default_factory=list)
    jurisdiction_template: str = ""
    genre_template: str = ""
    compiled_context: str = ""
    errors: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TemplateComposition":
        return cls(
            status=data.get("status", "error"),
            mode=data.get("mode", "FULL_DD"),
            manifest_hash=data.get("manifest_hash", ""),
            jurisdiction_id=data.get("jurisdiction_id", ""),
            genre_id=data.get("genre_id", ""),
            entity_name=data.get("entity_name", ""),
            dd_sections=data.get("dd_sections", []),
            optional_sections=data.get("optional_sections", []),
            allowed_actions=data.get("allowed_actions", []),
            jurisdiction_template=data.get("jurisdiction_template", ""),
            genre_template=data.get("genre_template", ""),
            compiled_context=data.get("compiled_context", ""),
            errors=data.get("errors", []),
        )


@dataclass
class ValidationFailure:
    """A single validation failure."""
    check: str = ""
    severity: str = "warning"  # critical, error, warning, info
    message: str = ""
    line_number: Optional[int] = None
    context: Optional[str] = None
    suggestion: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationFailure":
        return cls(
            check=data.get("check", ""),
            severity=data.get("severity", "warning"),
            message=data.get("message", ""),
            line_number=data.get("line_number"),
            context=data.get("context"),
            suggestion=data.get("suggestion"),
        )


@dataclass
class ValidationResult:
    """Result of validating document content."""
    status: str = "error"  # PASS or FAIL
    jurisdiction: str = ""
    checks_run: int = 0
    checks_passed: int = 0
    checks_failed: int = 0
    failures: List[ValidationFailure] = field(default_factory=list)
    manifest_hash: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationResult":
        failures = [ValidationFailure.from_dict(f) for f in data.get("failures", [])]
        return cls(
            status=data.get("status", "error"),
            jurisdiction=data.get("jurisdiction", ""),
            checks_run=data.get("checks_run", 0),
            checks_passed=data.get("checks_passed", 0),
            checks_failed=data.get("checks_failed", 0),
            failures=failures,
            manifest_hash=data.get("manifest_hash", ""),
        )

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"


class TemplateBridge:
    """
    Bridge between SASTRE orchestrator and the template system.

    Provides three core operations:
    1. route() - Parse tasking to determine jurisdiction/genre/section
    2. compose() - Get compiled template context
    3. validate() - Check section completeness
    """

    def __init__(self):
        self._verify_templates_exist()

        # Try direct import first (faster), fallback to subprocess
        self._use_direct_import = self._try_direct_import()

    def _verify_templates_exist(self) -> None:
        """Verify template system exists."""
        if not TEMPLATES_DIR.exists():
            raise FileNotFoundError(f"Templates directory not found: {TEMPLATES_DIR}")
        if not TEMPLATES_CLI.exists():
            raise FileNotFoundError(f"Templates CLI not found: {TEMPLATES_CLI}")

    def _try_direct_import(self) -> bool:
        """Try to import templates directly for faster execution."""
        try:
            scripts_dir = str(TEMPLATES_DIR / "scripts")
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)

            # Import the modules
            global route_module, compose_module
            import route as route_module
            import compose as compose_module

            logger.info("Template bridge using direct imports")
            return True
        except ImportError as e:
            logger.warning(f"Direct import failed, using subprocess: {e}")
            return False

    def route(self, tasking: str) -> TemplateRouting:
        """
        Route a tasking to jurisdiction/genre/section.

        Args:
            tasking: Natural language query like "DD on Szabo Kft"

        Returns:
            TemplateRouting with detected parameters
        """
        if self._use_direct_import:
            return self._route_direct(tasking)
        return self._route_subprocess(tasking)

    def _route_direct(self, tasking: str) -> TemplateRouting:
        """Route using direct Python import."""
        try:
            result = route_module.route(tasking)
            return TemplateRouting.from_dict(result)
        except Exception as e:
            logger.error(f"Direct routing failed: {e}")
            return TemplateRouting(status="error", confidence_reason=str(e))

    def _route_subprocess(self, tasking: str) -> TemplateRouting:
        """Route using subprocess call."""
        try:
            result = subprocess.run(
                ["python3", str(ROUTE_SCRIPT), tasking, "--json"],
                capture_output=True,
                text=True,
                cwd=str(TEMPLATES_DIR / "scripts"),
                timeout=30
            )

            if result.returncode != 0:
                return TemplateRouting(
                    status="error",
                    confidence_reason=result.stderr or "Route script failed"
                )

            data = json.loads(result.stdout)
            return TemplateRouting.from_dict(data)
        except subprocess.TimeoutExpired:
            return TemplateRouting(status="error", confidence_reason="Routing timeout")
        except json.JSONDecodeError as e:
            return TemplateRouting(status="error", confidence_reason=f"Invalid JSON: {e}")
        except Exception as e:
            return TemplateRouting(status="error", confidence_reason=str(e))

    def compose(
        self,
        routing: TemplateRouting = None,
        jurisdiction_id: str = None,
        genre_id: str = None,
        section_id: str = "overview",
        entity_name: str = None
    ) -> TemplateComposition:
        """
        Compose templates for a DD.

        Can accept either a TemplateRouting object or explicit parameters.

        Returns:
            TemplateComposition with sections, actions, and compiled context
        """
        # Use routing object if provided
        if routing:
            jurisdiction_id = jurisdiction_id or routing.jurisdiction_id
            genre_id = genre_id or routing.genre_id
            section_id = section_id or routing.section_id or "overview"
            entity_name = entity_name or routing.entity_name

        # Validate required params
        if not jurisdiction_id:
            return TemplateComposition(
                status="error",
                errors=["jurisdiction_id required"]
            )
        if not entity_name:
            return TemplateComposition(
                status="error",
                errors=["entity_name required"]
            )

        # Default genre
        genre_id = genre_id or "company_dd"

        if self._use_direct_import:
            return self._compose_direct(jurisdiction_id, genre_id, section_id, entity_name)
        return self._compose_subprocess(jurisdiction_id, genre_id, section_id, entity_name)

    def _compose_direct(
        self,
        jurisdiction_id: str,
        genre_id: str,
        section_id: str,
        entity_name: str
    ) -> TemplateComposition:
        """Compose using direct Python import."""
        try:
            result = compose_module.compose(
                jurisdiction_id=jurisdiction_id,
                genre_id=genre_id,
                section_id=section_id,
                entity_name=entity_name
            )
            return TemplateComposition.from_dict(result)
        except Exception as e:
            logger.error(f"Direct composition failed: {e}")
            return TemplateComposition(status="error", errors=[str(e)])

    def _compose_subprocess(
        self,
        jurisdiction_id: str,
        genre_id: str,
        section_id: str,
        entity_name: str
    ) -> TemplateComposition:
        """Compose using subprocess call."""
        try:
            args = [
                "python3", str(COMPOSE_SCRIPT),
                "--jurisdiction", jurisdiction_id,
                "--genre", genre_id,
                "--section", section_id,
                "--entity", entity_name,
                "--json"
            ]

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                cwd=str(TEMPLATES_DIR / "scripts"),
                timeout=30
            )

            if result.returncode != 0:
                return TemplateComposition(
                    status="error",
                    errors=[result.stderr or "Compose script failed"]
                )

            data = json.loads(result.stdout)
            return TemplateComposition.from_dict(data)
        except subprocess.TimeoutExpired:
            return TemplateComposition(status="error", errors=["Composition timeout"])
        except json.JSONDecodeError as e:
            return TemplateComposition(status="error", errors=[f"Invalid JSON: {e}"])
        except Exception as e:
            return TemplateComposition(status="error", errors=[str(e)])

    def route_and_compose(self, tasking: str) -> tuple[TemplateRouting, TemplateComposition]:
        """
        Combined route + compose in one call.

        Returns:
            Tuple of (routing, composition)
        """
        routing = self.route(tasking)

        if routing.status == "error":
            return routing, TemplateComposition(status="error", errors=["Routing failed"])

        if routing.status == "ambiguous" and not routing.jurisdiction_id:
            return routing, TemplateComposition(
                status="error",
                errors=["Ambiguous jurisdiction, cannot compose"]
            )

        composition = self.compose(routing)
        return routing, composition

    def get_sections_for_genre(self, genre_id: str) -> List[str]:
        """Get section list for a genre."""
        if self._use_direct_import:
            try:
                sections = compose_module.GENRE_SECTIONS.get(genre_id, [])
                return sections
            except Exception:
                pass

        # Fallback to hardcoded known sections
        return GENRE_SECTIONS.get(genre_id, [])

    def get_actions_for_genre(self, genre_id: str) -> List[str]:
        """Get allowed actions for a genre."""
        if self._use_direct_import:
            try:
                actions = compose_module.GENRE_ACTIONS.get(genre_id, [])
                return actions
            except Exception:
                pass

        # Fallback to hardcoded known actions
        return GENRE_ACTIONS.get(genre_id, [])

    def validate(self, content: str, jurisdiction_id: str, strict: bool = False) -> ValidationResult:
        """
        Validate document content against jurisdiction rules.

        Checks for:
        - No invented registries
        - No invented authorities/laws
        - Proper footnote format
        - Entity bolding consistency
        - Required disclaimers
        - Sanctions compliance
        - No future dates

        Args:
            content: Document markdown content
            jurisdiction_id: 2-letter jurisdiction code
            strict: If True, warnings also cause failure

        Returns:
            ValidationResult with status and any failures
        """
        if self._use_direct_import:
            return self._validate_direct(content, jurisdiction_id, strict)
        return self._validate_subprocess(content, jurisdiction_id, strict)

    def _validate_direct(self, content: str, jurisdiction_id: str, strict: bool) -> ValidationResult:
        """Validate using direct Python import."""
        try:
            # Import validate module
            scripts_dir = str(TEMPLATES_DIR / "scripts")
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)

            import validate as validate_module

            validator = validate_module.EdithValidator(jurisdiction_id.upper(), strict=strict)
            result = validator.validate(content)

            # Convert to our ValidationResult
            failures = [
                ValidationFailure(
                    check=f.check,
                    severity=f.severity.value if hasattr(f.severity, 'value') else str(f.severity),
                    message=f.message,
                    line_number=f.line_number,
                    context=f.context,
                    suggestion=f.suggestion,
                )
                for f in result.failures
            ]

            return ValidationResult(
                status=result.status,
                jurisdiction=result.jurisdiction,
                checks_run=result.checks_run,
                checks_passed=result.checks_passed,
                checks_failed=result.checks_failed,
                failures=failures,
                manifest_hash=result.manifest_hash or "",
            )
        except Exception as e:
            logger.error(f"Direct validation failed: {e}")
            return ValidationResult(
                status="error",
                jurisdiction=jurisdiction_id,
                failures=[ValidationFailure(check="import", severity="critical", message=str(e))],
            )

    def _validate_subprocess(self, content: str, jurisdiction_id: str, strict: bool) -> ValidationResult:
        """Validate using subprocess call."""
        try:
            args = [
                "python3", str(VALIDATE_SCRIPT),
                "--jurisdiction", jurisdiction_id.upper(),
                "--json",
            ]
            if strict:
                args.append("--strict")

            result = subprocess.run(
                args,
                input=content,
                capture_output=True,
                text=True,
                cwd=str(TEMPLATES_DIR / "scripts"),
                timeout=60
            )

            # Parse JSON output
            try:
                data = json.loads(result.stdout)
                return ValidationResult.from_dict(data)
            except json.JSONDecodeError:
                # Check exit code for status
                if result.returncode == 0:
                    return ValidationResult(status="PASS", jurisdiction=jurisdiction_id)
                else:
                    return ValidationResult(
                        status="FAIL",
                        jurisdiction=jurisdiction_id,
                        failures=[ValidationFailure(
                            check="subprocess",
                            severity="error",
                            message=result.stderr or "Validation failed"
                        )],
                    )

        except subprocess.TimeoutExpired:
            return ValidationResult(
                status="error",
                jurisdiction=jurisdiction_id,
                failures=[ValidationFailure(check="timeout", severity="critical", message="Validation timeout")],
            )
        except Exception as e:
            return ValidationResult(
                status="error",
                jurisdiction=jurisdiction_id,
                failures=[ValidationFailure(check="exception", severity="critical", message=str(e))],
            )


# Fallback genre sections (used if direct import fails)
GENRE_SECTIONS = {
    "company_dd": [
        "Executive Summary", "Company Overview", "Ownership & Shareholders",
        "Directors & Officers", "Group Structure", "Business Operations",
        "Financial Statements", "Regulatory Status & Licenses",
        "Sanctions & Watchlists", "Litigation", "Insolvency",
        "Adverse Media", "Research Limitations"
    ],
    "person_dd": [
        "Executive Summary", "Subject Overview", "Identity Verification",
        "Address History", "Employment History", "Business Affiliations",
        "Directorships & Officerships", "Sanctions & Watchlists",
        "Litigation", "Adverse Media", "Research Limitations"
    ],
    "enhanced_dd": [
        "Executive Summary", "Company Overview", "Ownership & Shareholders",
        "Ultimate Beneficial Owners", "Directors & Officers", "Group Structure",
        "Subsidiaries & Affiliates", "Business Operations", "Financial Statements",
        "Financial Analysis", "Key Contracts & Customers", "Regulatory Status & Licenses",
        "Industry Regulation", "Sanctions & Watchlists", "Litigation",
        "Regulatory Actions", "Criminal Matters", "Insolvency",
        "Adverse Media", "ESG Considerations", "Research Methodology",
        "Research Limitations"
    ],
    "investment_dd": [
        "Executive Summary", "Company Overview", "Ownership & Shareholders",
        "Ultimate Beneficial Owners", "Directors & Officers", "Key Management",
        "Group Structure", "Business Operations", "Market Position",
        "Financial Statements", "Financial Analysis", "Valuation Considerations",
        "Regulatory Status & Licenses", "Sanctions & Watchlists", "Litigation",
        "Adverse Media", "Research Limitations"
    ],
    "pep_profile": [
        "Executive Summary", "Subject Overview", "Political Career",
        "Government Positions", "Political Party Affiliations", "Family & Associates",
        "Business Interests", "Asset Declarations", "Directorships & Officerships",
        "Sanctions & Watchlists", "Litigation", "Adverse Media", "Research Limitations"
    ],
}

# Fallback genre actions
GENRE_ACTIONS = {
    "company_dd": [
        "SEARCH_REGISTRY", "SEARCH_OFFICERS", "SEARCH_SHAREHOLDERS",
        "SEARCH_FINANCIALS", "SEARCH_REGULATORY", "SEARCH_SANCTIONS",
        "SEARCH_COURT", "SEARCH_GAZETTE", "SEARCH_NEWS", "SEARCH_MEDIA"
    ],
    "person_dd": [
        "SEARCH_PASSPORT", "SEARCH_ADDRESS", "SEARCH_EMPLOYMENT",
        "SEARCH_DIRECTORSHIPS", "SEARCH_SANCTIONS", "SEARCH_COURT",
        "SEARCH_NEWS", "SEARCH_MEDIA", "SEARCH_LINKEDIN"
    ],
    "enhanced_dd": [
        "SEARCH_REGISTRY", "SEARCH_OFFICERS", "SEARCH_SHAREHOLDERS",
        "SEARCH_UBO", "SEARCH_FINANCIALS", "SEARCH_REGULATORY",
        "SEARCH_SANCTIONS", "SEARCH_COURT", "SEARCH_GAZETTE",
        "SEARCH_NEWS", "SEARCH_MEDIA", "SEARCH_ESG", "SEARCH_IP"
    ],
    "investment_dd": [
        "SEARCH_REGISTRY", "SEARCH_OFFICERS", "SEARCH_SHAREHOLDERS",
        "SEARCH_UBO", "SEARCH_FINANCIALS", "SEARCH_REGULATORY",
        "SEARCH_SANCTIONS", "SEARCH_COURT", "SEARCH_NEWS",
        "SEARCH_MARKET", "SEARCH_COMPETITORS"
    ],
    "pep_profile": [
        "SEARCH_POLITICAL", "SEARCH_GOVERNMENT", "SEARCH_FAMILY",
        "SEARCH_ASSETS", "SEARCH_DIRECTORSHIPS", "SEARCH_SANCTIONS",
        "SEARCH_COURT", "SEARCH_NEWS", "SEARCH_MEDIA"
    ],
}


# Singleton instance
_bridge_instance: Optional[TemplateBridge] = None


def get_template_bridge() -> TemplateBridge:
    """Get singleton template bridge instance."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = TemplateBridge()
    return _bridge_instance


# Convenience functions
def route_tasking(tasking: str) -> TemplateRouting:
    """Route a tasking to jurisdiction/genre/section."""
    return get_template_bridge().route(tasking)


def compose_templates(
    jurisdiction_id: str,
    genre_id: str = "company_dd",
    section_id: str = "overview",
    entity_name: str = ""
) -> TemplateComposition:
    """Compose templates for a DD."""
    return get_template_bridge().compose(
        jurisdiction_id=jurisdiction_id,
        genre_id=genre_id,
        section_id=section_id,
        entity_name=entity_name
    )


def route_and_compose(tasking: str) -> tuple[TemplateRouting, TemplateComposition]:
    """Route and compose in one call."""
    return get_template_bridge().route_and_compose(tasking)


def validate_content(content: str, jurisdiction_id: str, strict: bool = False) -> ValidationResult:
    """Validate document content against jurisdiction rules."""
    return get_template_bridge().validate(content, jurisdiction_id, strict)
