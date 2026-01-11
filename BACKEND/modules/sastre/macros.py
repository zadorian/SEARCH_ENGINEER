"""
SASTRE MACROS - Domain-Specific Language for Investigation Chains

MACROS are shorthand for investigation workflows:
    "John Smith" => !uk_registry => c? => !offshore => p? => disambiguate!

Operators:
| Operator | Meaning |
|----------|---------|
| `!domain.com` | Seed domain |
| `bl!` / `!bl` | Backlinks (domains linking TO target) |
| `ol!` / `!ol` | Outlinks (domains linked FROM target) |
| `p?` / `c?` / `e?` | Extract persons / companies / all entities |
| `2015-2020!` | Temporal filter |
| `@RULE_ID` | Execute IO matrix rule by ID |
| `{ a, b, c }` | Parallel execution |
| `=> disambiguate!` | Run disambiguation on results |
| `=> report!` | Generate report |
"""

import re
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class MacroOperator(Enum):
    """MACRO operators."""
    SEED_DOMAIN = "seed_domain"      # !domain.com
    BACKLINKS = "backlinks"          # bl! or !bl
    OUTLINKS = "outlinks"            # ol! or !ol
    EXTRACT_PERSONS = "extract_p"    # p?
    EXTRACT_COMPANIES = "extract_c"  # c?
    EXTRACT_ENTITIES = "extract_e"   # e?
    TEMPORAL = "temporal"            # 2015-2020!
    IO_RULE = "io_rule"              # @RULE_ID
    PARALLEL = "parallel"            # { a, b, c }
    DISAMBIGUATE = "disambiguate"    # disambiguate!
    REPORT = "report"                # report!
    SEARCH = "search"                # Quoted string search


@dataclass
class MacroStep:
    """A single step in a MACRO chain."""
    operator: MacroOperator
    value: str = ""
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MacroChain:
    """A parsed MACRO chain."""
    steps: List[MacroStep]
    original: str
    parallel_groups: List[List[MacroStep]] = field(default_factory=list)


class MacroParser:
    """
    Parse MACROS DSL into executable chains.

    Syntax examples:
        "John Smith" => !uk_registry => c?
        !example.com => bl! => p?
        { !domain1.com, !domain2.com } => c? => disambiguate!
        @corporella => c? => 2020-2024! => report!
    """

    # Regex patterns for operators
    PATTERNS = {
        # Quoted string (search term)
        'quoted': re.compile(r'"([^"]+)"'),
        # Domain seed (!domain.com)
        'domain': re.compile(r'!([a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z]{2,})'),
        # Backlinks (bl! or !bl)
        'backlinks': re.compile(r'(?:bl!|!bl)'),
        # Outlinks (ol! or !ol)
        'outlinks': re.compile(r'(?:ol!|!ol)'),
        # Extract persons (p?)
        'extract_p': re.compile(r'p\?'),
        # Extract companies (c?)
        'extract_c': re.compile(r'c\?'),
        # Extract all entities (e?)
        'extract_e': re.compile(r'e\?'),
        # Temporal filter (YYYY-YYYY!)
        'temporal': re.compile(r'(\d{4})-(\d{4})!'),
        # IO rule (@rule_id)
        'io_rule': re.compile(r'@([a-zA-Z_][a-zA-Z0-9_]*)'),
        # Parallel group ({ ... })
        'parallel': re.compile(r'\{([^}]+)\}'),
        # Disambiguate (disambiguate!)
        'disambiguate': re.compile(r'disambiguate!'),
        # Report (report!)
        'report': re.compile(r'report!'),
        # Named registry shortcuts
        'registry': re.compile(r'!(uk_registry|us_registry|de_registry|offshore|sanctions)'),
    }

    # Registry shortcuts to IO module mappings
    REGISTRY_SHORTCUTS = {
        'uk_registry': {'module': 'corporella', 'jurisdiction': 'UK'},
        'us_registry': {'module': 'corporella', 'jurisdiction': 'US'},
        'de_registry': {'module': 'corporella', 'jurisdiction': 'DE'},
        'offshore': {'module': 'corporella', 'jurisdictions': ['CY', 'BVI', 'PA', 'CH']},
        'sanctions': {'module': 'red_flag', 'list': 'sanctions'},
    }

    @classmethod
    def parse(cls, macro_string: str) -> MacroChain:
        """
        Parse a MACRO string into a MacroChain.

        Args:
            macro_string: The MACRO DSL string

        Returns:
            MacroChain with parsed steps
        """
        original = macro_string.strip()
        steps = []
        parallel_groups = []

        # Split by arrow operator (=>)
        parts = re.split(r'\s*=>\s*', original)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Check for parallel group
            parallel_match = cls.PATTERNS['parallel'].match(part)
            if parallel_match:
                inner = parallel_match.group(1)
                parallel_items = [p.strip() for p in inner.split(',')]
                group = []
                for item in parallel_items:
                    step = cls._parse_single(item)
                    if step:
                        group.append(step)
                if group:
                    parallel_groups.append(group)
                    # Add placeholder step
                    steps.append(MacroStep(
                        operator=MacroOperator.PARALLEL,
                        value=inner,
                        params={'group_index': len(parallel_groups) - 1}
                    ))
                continue

            # Parse single operator
            step = cls._parse_single(part)
            if step:
                steps.append(step)

        return MacroChain(
            steps=steps,
            original=original,
            parallel_groups=parallel_groups
        )

    @classmethod
    def _parse_single(cls, part: str) -> Optional[MacroStep]:
        """Parse a single MACRO operator."""
        part = part.strip()

        # Quoted string (search term)
        quoted_match = cls.PATTERNS['quoted'].match(part)
        if quoted_match:
            return MacroStep(
                operator=MacroOperator.SEARCH,
                value=quoted_match.group(1)
            )

        # Registry shortcuts (!uk_registry, etc.)
        registry_match = cls.PATTERNS['registry'].match(part)
        if registry_match:
            shortcut = registry_match.group(1)
            config = cls.REGISTRY_SHORTCUTS.get(shortcut, {})
            return MacroStep(
                operator=MacroOperator.IO_RULE,
                value=shortcut,
                params=config
            )

        # Domain seed
        domain_match = cls.PATTERNS['domain'].match(part)
        if domain_match:
            return MacroStep(
                operator=MacroOperator.SEED_DOMAIN,
                value=domain_match.group(1)
            )

        # Backlinks
        if cls.PATTERNS['backlinks'].match(part):
            return MacroStep(operator=MacroOperator.BACKLINKS)

        # Outlinks
        if cls.PATTERNS['outlinks'].match(part):
            return MacroStep(operator=MacroOperator.OUTLINKS)

        # Extract persons
        if cls.PATTERNS['extract_p'].match(part):
            return MacroStep(operator=MacroOperator.EXTRACT_PERSONS)

        # Extract companies
        if cls.PATTERNS['extract_c'].match(part):
            return MacroStep(operator=MacroOperator.EXTRACT_COMPANIES)

        # Extract all entities
        if cls.PATTERNS['extract_e'].match(part):
            return MacroStep(operator=MacroOperator.EXTRACT_ENTITIES)

        # Temporal filter
        temporal_match = cls.PATTERNS['temporal'].match(part)
        if temporal_match:
            return MacroStep(
                operator=MacroOperator.TEMPORAL,
                value=f"{temporal_match.group(1)}-{temporal_match.group(2)}",
                params={
                    'start_year': int(temporal_match.group(1)),
                    'end_year': int(temporal_match.group(2))
                }
            )

        # IO rule
        io_match = cls.PATTERNS['io_rule'].match(part)
        if io_match:
            return MacroStep(
                operator=MacroOperator.IO_RULE,
                value=io_match.group(1)
            )

        # Disambiguate
        if cls.PATTERNS['disambiguate'].match(part):
            return MacroStep(operator=MacroOperator.DISAMBIGUATE)

        # Report
        if cls.PATTERNS['report'].match(part):
            return MacroStep(operator=MacroOperator.REPORT)

        # Unknown - treat as search term
        if part:
            return MacroStep(
                operator=MacroOperator.SEARCH,
                value=part
            )

        return None


class MacroExecutor:
    """
    Execute parsed MACRO chains using existing infrastructure.

    Bridges to:
    - IO Matrix for routing
    - Linklater for backlinks/outlinks
    - JASPER for entity extraction
    - Disambiguator for resolution
    """

    def __init__(self, io_bridge=None, linklater=None):
        self.io_bridge = io_bridge
        self.linklater = linklater
        self._results = []
        self._context = {}

    async def execute(self, chain: MacroChain) -> Dict[str, Any]:
        """
        Execute a MACRO chain.

        Args:
            chain: Parsed MacroChain

        Returns:
            Dict with results and entities found
        """
        self._results = []
        self._context = {
            'domains': [],
            'entities': [],
            'temporal_filter': None,
        }

        for step in chain.steps:
            await self._execute_step(step, chain)

        return {
            'results': self._results,
            'context': self._context,
            'chain': chain.original,
        }

    async def _execute_step(self, step: MacroStep, chain: MacroChain) -> None:
        """Execute a single MACRO step."""

        if step.operator == MacroOperator.SEARCH:
            # Add search term to context
            self._context['search_term'] = step.value
            self._results.append({
                'type': 'search',
                'value': step.value,
            })

        elif step.operator == MacroOperator.SEED_DOMAIN:
            # Add domain to context
            self._context['domains'].append(step.value)
            self._results.append({
                'type': 'domain_seed',
                'domain': step.value,
            })

        elif step.operator == MacroOperator.BACKLINKS:
            # Get backlinks for all domains in context
            if self.linklater:
                for domain in self._context.get('domains', []):
                    try:
                        backlinks = await self.linklater.get_backlinks(domain)
                        self._results.append({
                            'type': 'backlinks',
                            'domain': domain,
                            'count': len(backlinks),
                            'links': backlinks[:100],  # Limit for memory
                        })
                        # Add discovered domains to context
                        for link in backlinks:
                            if hasattr(link, 'source_domain'):
                                self._context['domains'].append(link.source_domain)
                    except Exception as e:
                        self._results.append({
                            'type': 'error',
                            'operation': 'backlinks',
                            'domain': domain,
                            'error': str(e),
                        })

        elif step.operator == MacroOperator.OUTLINKS:
            # Get outlinks for all domains in context
            if self.linklater:
                for domain in self._context.get('domains', []):
                    try:
                        outlinks = await self.linklater.get_outlinks(domain)
                        self._results.append({
                            'type': 'outlinks',
                            'domain': domain,
                            'count': len(outlinks),
                            'links': outlinks[:100],
                        })
                        for link in outlinks:
                            if hasattr(link, 'target_domain'):
                                self._context['domains'].append(link.target_domain)
                    except Exception as e:
                        self._results.append({
                            'type': 'error',
                            'operation': 'outlinks',
                            'domain': domain,
                            'error': str(e),
                        })

        elif step.operator in (MacroOperator.EXTRACT_PERSONS,
                               MacroOperator.EXTRACT_COMPANIES,
                               MacroOperator.EXTRACT_ENTITIES):
            # Entity extraction - would use JASPER or Linklater
            extract_type = {
                MacroOperator.EXTRACT_PERSONS: 'persons',
                MacroOperator.EXTRACT_COMPANIES: 'companies',
                MacroOperator.EXTRACT_ENTITIES: 'all',
            }[step.operator]

            self._results.append({
                'type': 'extract',
                'extract_type': extract_type,
                'domains': self._context.get('domains', []),
            })

        elif step.operator == MacroOperator.TEMPORAL:
            # Set temporal filter in context
            self._context['temporal_filter'] = step.params
            self._results.append({
                'type': 'temporal_filter',
                'start': step.params.get('start_year'),
                'end': step.params.get('end_year'),
            })

        elif step.operator == MacroOperator.IO_RULE:
            # Execute IO rule
            if self.io_bridge:
                try:
                    result = await self.io_bridge.execute_rule(
                        step.value,
                        self._context
                    )
                    self._results.append({
                        'type': 'io_rule',
                        'rule': step.value,
                        'result': result,
                    })
                except Exception as e:
                    self._results.append({
                        'type': 'error',
                        'operation': 'io_rule',
                        'rule': step.value,
                        'error': str(e),
                    })

        elif step.operator == MacroOperator.PARALLEL:
            # Execute parallel group - TRULY PARALLEL using asyncio.gather
            group_index = step.params.get('group_index', 0)
            if group_index < len(chain.parallel_groups):
                group = chain.parallel_groups[group_index]
                # Create coroutines for all steps (don't await yet)
                tasks = [
                    self._execute_step(parallel_step, chain)
                    for parallel_step in group
                ]
                # Execute ALL tasks concurrently, wait for all to complete
                results = await asyncio.gather(*tasks, return_exceptions=True)
                # Handle any exceptions
                for result in results:
                    if isinstance(result, Exception):
                        self._results.append({
                            'type': 'error',
                            'operation': 'parallel_step',
                            'error': str(result),
                        })

        elif step.operator == MacroOperator.DISAMBIGUATE:
            # Mark for disambiguation
            self._results.append({
                'type': 'disambiguate',
                'entities': self._context.get('entities', []),
            })

        elif step.operator == MacroOperator.REPORT:
            # Mark for report generation
            self._results.append({
                'type': 'report',
                'context': self._context,
            })


def parse_macro(macro_string: str) -> MacroChain:
    """Convenience function to parse a MACRO string."""
    return MacroParser.parse(macro_string)


async def execute_macro(
    macro_string: str,
    io_bridge=None,
    linklater=None
) -> Dict[str, Any]:
    """
    Convenience function to parse and execute a MACRO.

    Args:
        macro_string: MACRO DSL string
        io_bridge: Optional IOBridge instance
        linklater: Optional LinkLater instance

    Returns:
        Execution results
    """
    chain = parse_macro(macro_string)
    executor = MacroExecutor(io_bridge, linklater)
    return await executor.execute(chain)


# Example MACROS for common investigation patterns
INVESTIGATION_MACROS = {
    # Person investigation
    'person_full': '"{{name}}" => !uk_registry => c? => !offshore => p? => disambiguate!',

    # Company deep dive
    'company_deep': '"{{company}}" => @corporella => p? => !uk_registry => c? => disambiguate!',

    # Domain intelligence
    'domain_intel': '!{{domain}} => bl! => p? => c? => ol! => disambiguate!',

    # Offshore trail
    'offshore_trail': '"{{entity}}" => !offshore => c? => p? => disambiguate! => report!',

    # Sanctions check
    'sanctions_check': '"{{name}}" => @sanctions => disambiguate!',

    # Historical research
    'historical': '"{{query}}" => 2015-2024! => @archives => e? => disambiguate!',
}


def get_investigation_macro(pattern: str, **kwargs) -> str:
    """
    Get a pre-defined investigation MACRO with substituted values.

    Args:
        pattern: Pattern name (e.g., 'person_full', 'company_deep')
        **kwargs: Values to substitute (e.g., name="John Smith")

    Returns:
        Expanded MACRO string
    """
    template = INVESTIGATION_MACROS.get(pattern)
    if not template:
        raise ValueError(f"Unknown investigation pattern: {pattern}")

    # Simple template substitution
    result = template
    for key, value in kwargs.items():
        result = result.replace(f'{{{{{key}}}}}', str(value))

    return result
