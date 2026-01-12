#!/usr/bin/env python3
"""
IO Executor - Wraps rule execution to produce IOResult with source_url.

This is TIER 2 of the Ultimate Unification Plan - the Modular Engine (execution logic).

Key responsibilities:
1. Execute rules via RuleExecutor
2. Extract source_url from results (deterministically)
3. Detect walls (paywalls, logins, captchas)
4. Return IOResult with all metadata for footnotes
5. CRITICAL: Implement "Sanctity of Source" - hide internal execution details

The "Sanctity of Source" Pattern:
- Internal execution details (Torpedo, handlers, APIs) NEVER leak to user
- Only public registry names appear in output
- SourceNameResolver translates internal labels to public names

Usage:
    executor = IOExecutor()
    result = await executor.execute("COMPANY_OFFICERS", "Podravka d.d.", "HR")
    # result.source_url = "https://sudreg.pravosudje.hr/..."
    # result.source_name = "Croatian Business Registry"  # Public name
    # result.data = {"officers": [...]}
    # result.status = IOStatus.SUCCESS or IOStatus.WALL
"""

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import logging

from io_result import (
    IOResult,
    IOStatus,
    WallInfo,
    ResultAggregator,
    FootnoteInjector,
    WallSurfacer,
)

# Import compiler for Sanctity of Source
try:
    from io_compiler import IOCompiler
    COMPILER_AVAILABLE = True
except ImportError:
    COMPILER_AVAILABLE = False

# Import the existing executor
try:
    from io_cli import RuleExecutor, IORouter as LegacyIORouter
    EXECUTOR_AVAILABLE = True
except ImportError:
    EXECUTOR_AVAILABLE = False

logger = logging.getLogger(__name__)

MATRIX_DIR = Path(__file__).parent


# =============================================================================
# SOURCE NAME RESOLVER - The "Sanctity of Source" Implementation
# =============================================================================

@dataclass
class PublicSourceInfo:
    """Public-facing source information (visible to user/report)."""
    source_name: str           # e.g., "Hungarian Business Registry"
    display_name: str          # e.g., "Company Officers (Hungary)"
    category: str              # e.g., "corporate_registry"
    jurisdiction: str          # e.g., "HU"
    icon: str = ""             # Optional icon identifier
    is_blocked: bool = False   # Whether source hit a wall


class SourceNameResolver:
    """
    Translates internal execution identifiers to public source names.
    This is THE SINGLE POINT where internal details are hidden.

    The Double-Sided Index:
    - EXECUTION side: handler type, script path, API version, rate limits
    - PUBLIC side: registry name, display name, category, jurisdiction

    Internal labels like "TORPEDO:AT_CORPORATE_V2" or "API:CH_UK" are
    translated to user-friendly names like "Austrian Corporate Registry".
    """

    # Map internal handler names to friendly descriptions
    HANDLER_DISPLAY_NAMES = {
        "torpedo": "Registry Lookup",
        "corporella": "Corporate Intelligence",
        "eye-d": "OSINT Search",
        "linklater": "Archive Analysis",
        "companies_house_api": "Companies House",
        "opencorporates": "OpenCorporates",
        "brute": "Web Search",
    }

    # Category icons
    CATEGORY_ICONS = {
        "corporate_registry": "building",
        "company_registry": "building",
        "court_records": "gavel",
        "litigation": "gavel",
        "land_registry": "map",
        "property": "home",
        "news": "newspaper",
        "sanctions": "alert",
        "pep": "user-shield",
    }

    def __init__(self, compiler: Optional['IOCompiler'] = None):
        self.compiler = compiler
        if not compiler and COMPILER_AVAILABLE:
            self.compiler = IOCompiler()

    def resolve(
        self,
        rule_id: str,
        execution_label: str = "",
        jurisdiction: str = "",
        handler_type: str = "",
    ) -> PublicSourceInfo:
        """
        Given internal execution details, return public source information.

        Args:
            rule_id: Rule ID (e.g., "COMPANY_OFFICERS_HU")
            execution_label: Internal label (e.g., "TORPEDO:HR_CORPORATE")
            jurisdiction: Jurisdiction code
            handler_type: Handler that executed (e.g., "torpedo")

        Returns:
            PublicSourceInfo with user-friendly names
        """
        # Try to get source from compiler
        source = None
        if self.compiler:
            source = self.compiler.get_source_for_rule(rule_id)

        # Parse jurisdiction from rule_id if not provided
        jur = jurisdiction
        if not jur:
            parts = rule_id.upper().split("_")
            if parts:
                potential_jur = parts[-1]
                jur = self.compiler.resolve_jurisdiction(potential_jur) if self.compiler else potential_jur

        # Determine if blocked from execution_label
        is_blocked = execution_label.upper().startswith("BLOCKED") if execution_label else False

        # Build source name
        if source:
            source_name = source.name
            category = source.category
        else:
            # Fallback: generate from rule_id
            source_name = self._generate_source_name(rule_id, jur)
            category = self._infer_category(rule_id)

        # Build display name
        display_name = self._build_display_name(rule_id, jur, source_name)

        # Get icon
        icon = self.CATEGORY_ICONS.get(category, "")

        return PublicSourceInfo(
            source_name=source_name,
            display_name=display_name,
            category=category,
            jurisdiction=jur.upper() if jur else "",
            icon=icon,
            is_blocked=is_blocked,
        )

    def _generate_source_name(self, rule_id: str, jurisdiction: str) -> str:
        """Generate a friendly source name from rule_id."""
        # Country name lookup
        country_names = {
            "AT": "Austrian", "AU": "Australian", "BE": "Belgian", "BG": "Bulgarian",
            "BR": "Brazilian", "CA": "Canadian", "CH": "Swiss", "CN": "Chinese",
            "CZ": "Czech", "DE": "German", "DK": "Danish", "EE": "Estonian",
            "ES": "Spanish", "FI": "Finnish", "FR": "French", "GB": "UK",
            "GR": "Greek", "HR": "Croatian", "HU": "Hungarian", "IE": "Irish",
            "IN": "Indian", "IT": "Italian", "JP": "Japanese", "KR": "Korean",
            "LT": "Lithuanian", "LU": "Luxembourg", "LV": "Latvian", "MX": "Mexican",
            "NL": "Dutch", "NO": "Norwegian", "NZ": "New Zealand", "PL": "Polish",
            "PT": "Portuguese", "RO": "Romanian", "RU": "Russian", "SE": "Swedish",
            "SG": "Singapore", "SI": "Slovenian", "SK": "Slovak", "UK": "UK",
            "US": "US", "ZA": "South African",
        }

        # Source type from rule name
        rule_upper = rule_id.upper()
        source_type = "Registry"
        if "OFFICER" in rule_upper or "DIRECTOR" in rule_upper:
            source_type = "Business Registry"
        elif "SHAREHOLDER" in rule_upper or "OWNERSHIP" in rule_upper:
            source_type = "Ownership Registry"
        elif "LITIGATION" in rule_upper or "COURT" in rule_upper:
            source_type = "Court Records"
        elif "NEWS" in rule_upper or "MEDIA" in rule_upper:
            source_type = "News Sources"
        elif "SANCTION" in rule_upper:
            source_type = "Sanctions Database"
        elif "COMPANY" in rule_upper or "CORPORATE" in rule_upper:
            source_type = "Business Registry"

        country = country_names.get(jurisdiction.upper(), jurisdiction) if jurisdiction else "Global"
        return f"{country} {source_type}"

    def _infer_category(self, rule_id: str) -> str:
        """Infer category from rule_id."""
        rule_upper = rule_id.upper()
        if "LITIGATION" in rule_upper or "COURT" in rule_upper:
            return "litigation"
        elif "NEWS" in rule_upper:
            return "news"
        elif "SANCTION" in rule_upper:
            return "sanctions"
        elif "PROPERTY" in rule_upper or "LAND" in rule_upper:
            return "property"
        else:
            return "corporate_registry"

    def _build_display_name(self, rule_id: str, jurisdiction: str, source_name: str) -> str:
        """Build display name for UI."""
        # Extract action from rule_id
        rule_upper = rule_id.upper()
        action = "Search"
        if "OFFICER" in rule_upper:
            action = "Officers"
        elif "SHAREHOLDER" in rule_upper:
            action = "Shareholders"
        elif "CORE" in rule_upper:
            action = "Company Profile"
        elif "LITIGATION" in rule_upper:
            action = "Litigation"

        jur_display = f"({jurisdiction.upper()})" if jurisdiction else ""
        return f"{action} {jur_display}".strip()


class IOExecutor:
    """
    Execute IO routes and return IOResult with source_url.

    The Hands - Uses ResilientExecutor with Circuit Breakers and Fallbacks.

    Key Feature: "Sanctity of Source" - Internal execution details are NEVER
    exposed to the user. Only public source names appear in output.

    Wraps RuleExecutor to:
    1. Track source URLs from resources
    2. Detect walls and create WallInfo
    3. Return structured IOResult with public source names
    4. Hide internal execution details (handlers, scripts, APIs)
    """

    # Patterns that indicate a wall was hit
    WALL_PATTERNS = {
        'paywall': [
            r'subscription required',
            r'premium access',
            r'pay to view',
            r'purchase access',
            r'subscribe to',
        ],
        'login': [
            r'login required',
            r'sign in to',
            r'please log in',
            r'authentication required',
            r'must be logged in',
        ],
        'captcha': [
            r'captcha',
            r'verify you are human',
            r'robot check',
            r'security check',
        ],
        'blocked': [
            r'access denied',
            r'forbidden',
            r'blocked',
            r'rate limit',
            r'too many requests',
        ],
    }

    def __init__(self, project_id: str = None, compiler: Optional[IOCompiler] = None):
        self.project_id = project_id
        self._rule_executor = None
        self._router = None
        self._rules_by_id = None
        self._registries = None
        self._compiler = compiler
        self._name_resolver = None

    def _lazy_load(self):
        """Lazy load dependencies."""
        if self._rule_executor is not None:
            return

        if not EXECUTOR_AVAILABLE:
            raise RuntimeError("RuleExecutor not available - check io_cli.py import")

        self._rule_executor = RuleExecutor(project_id=self.project_id)
        self._router = LegacyIORouter()
        self._rules_by_id = self._load_rules()
        self._registries = self._load_registries()

        # Initialize compiler and name resolver for Sanctity of Source
        if not self._compiler and COMPILER_AVAILABLE:
            self._compiler = IOCompiler()
        self._name_resolver = SourceNameResolver(self._compiler)

    def _load_rules(self) -> Dict[str, Dict]:
        """Load rules indexed by ID."""
        rules_path = MATRIX_DIR / "rules.json"
        if not rules_path.exists():
            return {}
        with open(rules_path) as f:
            rules_list = json.load(f)
            return {rule['id']: rule for rule in rules_list}

    def _load_registries(self) -> Dict[str, Dict]:
        """Load registries for URL resolution."""
        registries_path = MATRIX_DIR / "registries.json"
        if not registries_path.exists():
            return {}
        with open(registries_path) as f:
            return json.load(f)

    async def close(self):
        """Close executor resources."""
        if self._rule_executor:
            await self._rule_executor.close()
            self._rule_executor = None

    def _extract_source_url(self, rule: Dict, raw_result: Dict, jurisdiction: str = None) -> str:
        """
        Extract the source URL from rule resources and execution result.

        Priority:
        1. URL from successful API/scrape response
        2. URL from rule's resources
        3. URL from registry for jurisdiction
        4. Fallback to search_url_template
        """
        # Check execution results for URLs
        for res in raw_result.get('results', []):
            if res.get('url'):
                return res['url']
            if res.get('source_url'):
                return res['source_url']

        # Check rule resources
        resources = rule.get('resources', [])
        for resource in resources:
            url = resource.get('url') or resource.get('search_url_template')
            if url:
                # Substitute jurisdiction if present
                if jurisdiction and '{jurisdiction}' in url:
                    url = url.replace('{jurisdiction}', jurisdiction)
                return url

        # Check search_url_template
        template = rule.get('search_url_template', '')
        if template:
            if jurisdiction and '{jurisdiction}' in template:
                template = template.replace('{jurisdiction}', jurisdiction)
            return template

        # Check registry for jurisdiction
        if jurisdiction and jurisdiction.upper() in self._registries:
            reg = self._registries[jurisdiction.upper()]
            if reg.get('url'):
                return reg['url']

        return ""

    def _detect_wall(self, raw_result: Dict, source_url: str) -> Optional[WallInfo]:
        """
        Detect if the result indicates a wall (paywall, login, etc.).

        Returns WallInfo if wall detected, None otherwise.
        """
        # Check status
        if raw_result.get('status') == 'success':
            return None

        # Check error messages and output
        check_texts = []
        for res in raw_result.get('results', []):
            if res.get('error'):
                check_texts.append(str(res['error']).lower())
            if res.get('output'):
                check_texts.append(str(res['output']).lower())
            if res.get('data') and isinstance(res['data'], str):
                check_texts.append(res['data'].lower())

        combined_text = ' '.join(check_texts)

        # Check patterns
        for wall_type, patterns in self.WALL_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, combined_text, re.IGNORECASE):
                    return WallInfo(
                        wall_type=wall_type,
                        closest_url=source_url,
                        instructions=self._get_wall_instructions(wall_type),
                        registry_name=raw_result.get('label', ''),
                    )

        # Check for HTTP 4xx/5xx
        for res in raw_result.get('results', []):
            status_code = res.get('status_code', 0)
            if status_code == 401 or status_code == 403:
                return WallInfo(
                    wall_type='login',
                    closest_url=source_url,
                    instructions="Authentication required. Log in manually and retry.",
                )
            elif status_code == 402:
                return WallInfo(
                    wall_type='paywall',
                    closest_url=source_url,
                    instructions="Payment/subscription required for access.",
                )
            elif status_code == 429:
                return WallInfo(
                    wall_type='rate_limit',
                    closest_url=source_url,
                    instructions="Rate limited. Wait and retry, or use different IP.",
                )

        return None

    def _get_wall_instructions(self, wall_type: str) -> str:
        """Get human-readable instructions for wall type."""
        instructions = {
            'paywall': "Subscription required. Purchase access or use alternative source.",
            'login': "Login required. Create account or log in manually.",
            'captcha': "Captcha detected. Complete verification in browser.",
            'blocked': "Access blocked. Try different IP or wait before retrying.",
            'rate_limit': "Rate limited. Wait and retry with delays.",
        }
        return instructions.get(wall_type, "Manual intervention required.")

    def _extract_data(self, raw_result: Dict) -> Dict[str, Any]:
        """
        Extract structured data from raw execution result.
        """
        data = {}

        for res in raw_result.get('results', []):
            if res.get('data'):
                res_data = res['data']
                if isinstance(res_data, dict):
                    data.update(res_data)
                elif isinstance(res_data, list):
                    # Append to existing lists or create new
                    key = res.get('type', 'items')
                    if key in data and isinstance(data[key], list):
                        data[key].extend(res_data)
                    else:
                        data[key] = res_data

            # Extract from output if JSON
            if res.get('output'):
                try:
                    output_data = json.loads(res['output'])
                    if isinstance(output_data, dict):
                        data.update(output_data)
                except (json.JSONDecodeError, TypeError):
                    pass

        return data

    async def execute(
        self,
        route_id: str,
        entity: str,
        jurisdiction: str = None,
    ) -> IOResult:
        """
        Execute an IO route and return structured IOResult.

        Args:
            route_id: Rule ID (e.g., "COMPANY_OFFICERS")
            entity: Entity value (e.g., "Podravka d.d.")
            jurisdiction: Optional jurisdiction code (e.g., "HR")

        Returns:
            IOResult with source_url, data, and wall info
        """
        self._lazy_load()

        start_time = datetime.utcnow()

        # Get rule
        rule = self._rules_by_id.get(route_id)
        if not rule:
            return IOResult(
                route_id=route_id,
                entity=entity,
                jurisdiction=jurisdiction,
                status=IOStatus.ERROR,
                source_url="",
                error_message=f"Rule not found: {route_id}",
            )

        # Execute via RuleExecutor
        try:
            raw_result = await self._rule_executor.execute_rule(rule, entity, jurisdiction)
        except Exception as e:
            return IOResult(
                route_id=route_id,
                entity=entity,
                jurisdiction=jurisdiction,
                status=IOStatus.ERROR,
                source_url="",
                error_message=str(e),
            )

        end_time = datetime.utcnow()
        execution_ms = int((end_time - start_time).total_seconds() * 1000)

        # Extract source URL
        source_url = self._extract_source_url(rule, raw_result, jurisdiction)

        # Detect wall
        wall_info = self._detect_wall(raw_result, source_url)

        # Determine status
        if wall_info:
            status = IOStatus.WALL
        elif raw_result.get('status') == 'success':
            status = IOStatus.SUCCESS
        else:
            status = IOStatus.ERROR

        # Extract data
        data = self._extract_data(raw_result)

        # CRITICAL: Resolve public source info (Sanctity of Source)
        # Internal execution details NEVER leak to user
        execution_label = raw_result.get('label', '')
        handler_type = raw_result.get('handler', '')

        public_info = self._name_resolver.resolve(
            rule_id=route_id,
            execution_label=execution_label,
            jurisdiction=jurisdiction,
            handler_type=handler_type,
        ) if self._name_resolver else None

        # Update wall_info with public registry name
        if wall_info and public_info:
            wall_info.registry_name = public_info.source_name

        return IOResult(
            route_id=route_id,
            entity=entity,
            jurisdiction=jurisdiction,
            status=status,
            source_url=source_url,
            data=data,
            wall_info=wall_info,
            error_message=raw_result.get('error') if status == IOStatus.ERROR else None,
            executed_at=start_time,
            execution_ms=execution_ms,
            # PUBLIC SIDE (visible to user/report) - Sanctity of Source
            source_name=public_info.source_name if public_info else "",
            source_display_name=public_info.display_name if public_info else "",
            source_category=public_info.category if public_info else "",
        )

    async def execute_many(
        self,
        route_ids: List[str],
        entity: str,
        jurisdiction: str = None,
    ) -> List[IOResult]:
        """
        Execute multiple routes in parallel.
        """
        tasks = [
            self.execute(route_id, entity, jurisdiction)
            for route_id in route_ids
        ]
        return await asyncio.gather(*tasks)

    async def execute_for_section(
        self,
        section_id: str,
        entity: str,
        jurisdiction: str,
        required_actions: List[str],
    ) -> ResultAggregator:
        """
        Execute all required actions for a section and aggregate results.

        Args:
            section_id: Section ID (e.g., "directors_officers")
            entity: Entity value
            jurisdiction: Jurisdiction code
            required_actions: List of route IDs to execute

        Returns:
            ResultAggregator with merged data and all source URLs
        """
        aggregator = ResultAggregator()

        # Execute all routes
        results = await self.execute_many(required_actions, entity, jurisdiction)

        # Add to aggregator (deduplicates)
        for result in results:
            aggregator.add(result)

        return aggregator


# =============================================================================
# SECTION FILLER - Fill section markdown with IOResults
# =============================================================================

class SectionFiller:
    """
    Fill a section template with IOResults data and inject footnotes.

    This is the final step:
    1. Get aggregated data from ResultAggregator
    2. Fill slots in template
    3. Inject footnotes deterministically from source_urls
    4. Surface walls for manual retrieval
    """

    def __init__(self):
        self.footnote_injector = FootnoteInjector()

    def fill_section(
        self,
        template: str,
        aggregator: ResultAggregator,
        slot_to_field_map: Dict[str, str] = None,
    ) -> str:
        """
        Fill a section template with data and footnotes.

        Args:
            template: Section markdown template with {{SLOT:...}} placeholders
            aggregator: ResultAggregator with IOResults
            slot_to_field_map: Optional mapping of slot names to data field names

        Returns:
            Filled markdown with footnotes and wall section
        """
        self.footnote_injector.reset()

        # Get merged data
        data = aggregator.get_merged_data()

        # Fill slots
        filled = self._fill_slots(template, data)

        # Inject footnotes from successful results
        if slot_to_field_map:
            filled = self.footnote_injector.inject_from_io_results(
                filled, aggregator.get_successes(), slot_to_field_map
            )
        else:
            # Auto-inject for key values
            for result in aggregator.get_successes():
                if result.source_url:
                    # Inject for entity name
                    filled = self.footnote_injector.inject_footnote_after_value(
                        filled, result.entity, result.source_url
                    )

        # Add footnotes at end
        footnotes = self.footnote_injector.render_footnotes()

        # Add wall section if any
        walls_section = WallSurfacer.format_all_walls(aggregator.results)

        return filled + footnotes + ("\n\n" + walls_section if walls_section else "")

    def _fill_slots(self, template: str, data: Dict[str, Any]) -> str:
        """
        Fill {{SLOT:name}} placeholders with data values.
        """
        # Pattern: {{SLOT:name|field:XX|default=value}}
        pattern = r'\{\{SLOT:(\w+)(?:\|field:\d+)?(?:\|default=([^}]*))?\}\}'

        def replace_slot(match):
            slot_name = match.group(1)
            default = match.group(2) if match.group(2) else ""

            # Try to find value in data
            value = data.get(slot_name)
            if value is None:
                # Try common variations
                value = data.get(slot_name.lower())
            if value is None:
                value = data.get(slot_name.replace('_', ''))

            if value is not None:
                if isinstance(value, list):
                    return ", ".join(str(v) for v in value)
                return str(value)

            return default

        return re.sub(pattern, replace_slot, template)


# =============================================================================
# CLI
# =============================================================================

async def main():
    """CLI for testing IOExecutor."""
    import argparse

    parser = argparse.ArgumentParser(description="IO Executor - Execute routes with source_url tracking")
    parser.add_argument("route_id", help="Route ID (e.g., COMPANY_OFFICERS)")
    parser.add_argument("entity", help="Entity value (e.g., 'Podravka d.d.')")
    parser.add_argument("--jurisdiction", "-j", help="Jurisdiction code (e.g., HR)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    executor = IOExecutor()
    try:
        result = await executor.execute(args.route_id, args.entity, args.jurisdiction)

        if args.json:
            print(json.dumps(result.to_dict(), indent=2, default=str))
        else:
            print(f"\n{'='*60}")
            print(f"Route: {result.route_id}")
            print(f"Entity: {result.entity}")
            print(f"Jurisdiction: {result.jurisdiction}")
            print(f"Status: {result.status.value}")
            print(f"Source URL: {result.source_url}")
            print(f"Execution: {result.execution_ms}ms")
            print(f"{'='*60}\n")

            if result.status == IOStatus.SUCCESS:
                print("Data:")
                print(json.dumps(result.data, indent=2, default=str))
            elif result.status == IOStatus.WALL:
                print("WALL HIT:")
                print(WallSurfacer.format_wall_for_user(result))
            else:
                print(f"Error: {result.error_message}")

    finally:
        await executor.close()


if __name__ == "__main__":
    asyncio.run(main())
