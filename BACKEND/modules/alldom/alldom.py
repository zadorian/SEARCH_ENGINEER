#!/usr/bin/env python3
"""
ALLDOM - Unified Domain Intelligence Orchestrator

Thin layer that routes ALL domain-focused operations to appropriate modules:
- LINKLATER: backlinks (bl?), outlinks (ol?)
- BACKDRILL: archive lookups (CommonCrawl, Wayback, Memento)
- MAPPER (JESTER): URL discovery (subdomains, sitemaps, search engines)
- EYE-D: WHOIS lookups
- MACROS: age!, ga!, tech!
- EXIF: metadata extraction (meta?, exif?, docs?, dates?)

Usage:
    from modules.alldom import AllDom

    ad = AllDom()

    # Run specific operator
    result = await ad.execute("bl?", "example.com")
    result = await ad.execute("whois:", "example.com")

    # Metadata/EXIF extraction
    result = await ad.execute("meta?", "example.com")   # Full metadata scan
    result = await ad.execute("exif?", "example.com")   # Images only
    result = await ad.execute("docs?", "example.com")   # Documents only
    result = await ad.execute("dates?", "example.com")  # Extract dates

    # Full domain scan
    report = await ad.scan("example.com", depth="full")
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class AllDomResult:
    """Result container for AllDom operations."""
    operator: str
    target: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    source: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class AllDom:
    """
    Ultra-thin orchestration layer for domain-focused operations.

    Routes operators to appropriate modules without duplicating logic.
    """

    # Operator → (bridge_module, method) routing table
    OPERATOR_ROUTES = {
        # Link analysis → LINKLATER
        "bl?": ("linklater", "backlinks"),
        "bl!": ("linklater", "backlinks_domains"),
        "ol?": ("linklater", "outlinks"),
        "ol!": ("linklater", "outlinks_domains"),
        # Similar content u2192 LINKLATER
        "similar:": ("linklater", "similar"),
# Content search operators        "keyword:": ("keyword", "search_keyword"),        "?:": ("ai_qa", "ask_question"),

        # Archive → BACKDRILL
        "<-!": ("backdrill", "fetch"),
        "wb:": ("backdrill", "wayback"),
        "cc:": ("backdrill", "commoncrawl"),

        # URL discovery → MAPPER (JESTER)
        "map?": ("mapper", "discover"),       # Authorized: map?
        
        # WHOIS → Native
        "whois?": ("whois", "lookup"),        # Authorized: whois?
        "whois:": ("whois", "lookup"),        # Authorized: whois:

        # DNS → EYE-D
        "dns:": ("eyed", "dns"),

        # Macros
        "age?": ("macros", "age"),            # Authorized: age?

        # Entity extraction (delegates to operator_handlers)
        "@ent?": ("entities", "extract_all"),
        "@p?": ("entities", "extract_persons"),
        "@c?": ("entities", "extract_companies"),
        "@e?": ("entities", "extract_emails"),
        "@t?": ("entities", "extract_phones"),

        # Metadata/EXIF extraction
        "meta?": ("exif", "scan"),
        "exif?": ("exif", "images_only"),
        "docs?": ("exif", "documents_only"),
        "dates?": ("exif", "extract_dates"),
    }

    def __init__(self):
        self._bridges: Dict[str, Any] = {}
        self._initialized = False

    async def _ensure_bridges(self):
        """Lazy-load bridges on first use."""
        if self._initialized:
            return

        try:
            from .bridges import linklater, backdrill, mapper, eyed, macros, entities, exif
            from . import whoisxmlapi as whois
            self._bridges = {
                "linklater": linklater,
                "backdrill": backdrill,
                "mapper": mapper,
                "eyed": eyed,
                "macros": macros,
                "entities": entities,
                "exif": exif,
                "whois": whois,
            }
            self._initialized = True
            logger.debug("AllDom bridges loaded")
        except ImportError as e:
            logger.error(f"Failed to load AllDom bridges: {e}")
            raise

    async def execute(self, operator: str, target: str, **kwargs) -> AllDomResult:
        """
        Execute a single operator against target domain/URL.

        Args:
            operator: Operator string (bl?, ol?, whois:, etc.)
            target: Domain or URL to operate on
            **kwargs: Additional parameters for the operation

        Returns:
            AllDomResult with data or error
        """
        await self._ensure_bridges()

        # Normalize operator
        op = operator.strip().lower()

        # Find route
        route = self.OPERATOR_ROUTES.get(op)
        if not route:
            return AllDomResult(
                operator=operator,
                target=target,
                success=False,
                error=f"Unknown operator: {operator}"
            )

        bridge_name, method_name = route
        bridge = self._bridges.get(bridge_name)

        if not bridge:
            return AllDomResult(
                operator=operator,
                target=target,
                success=False,
                error=f"Bridge not loaded: {bridge_name}"
            )

        # Get and call the method
        method = getattr(bridge, method_name, None)
        if not method:
            return AllDomResult(
                operator=operator,
                target=target,
                success=False,
                error=f"Method not found: {bridge_name}.{method_name}"
            )

        try:
            # Call the bridge method
            if asyncio.iscoroutinefunction(method):
                data = await method(target, **kwargs)
            else:
                data = method(target, **kwargs)

            return AllDomResult(
                operator=operator,
                target=target,
                success=True,
                data=data,
                source=bridge_name
            )
        except Exception as e:
            logger.error(f"AllDom execute failed: {operator} on {target}: {e}")
            return AllDomResult(
                operator=operator,
                target=target,
                success=False,
                error=str(e),
                source=bridge_name
            )

    async def execute_stream(
        self,
        operator: str,
        target: str,
        **kwargs
    ) -> AsyncIterator[AllDomResult]:
        """
        Execute operator with streaming results.

        Yields results as they arrive from the underlying module.
        """
        await self._ensure_bridges()

        op = operator.strip().lower()
        route = self.OPERATOR_ROUTES.get(op)

        if not route:
            yield AllDomResult(
                operator=operator,
                target=target,
                success=False,
                error=f"Unknown operator: {operator}"
            )
            return

        bridge_name, method_name = route
        bridge = self._bridges.get(bridge_name)

        if not bridge:
            yield AllDomResult(
                operator=operator,
                target=target,
                success=False,
                error=f"Bridge not loaded: {bridge_name}"
            )
            return

        # Look for streaming method (method_name + "_stream")
        stream_method = getattr(bridge, f"{method_name}_stream", None)
        if not stream_method:
            # Fall back to non-streaming
            result = await self.execute(operator, target, **kwargs)
            yield result
            return

        try:
            async for item in stream_method(target, **kwargs):
                yield AllDomResult(
                    operator=operator,
                    target=target,
                    success=True,
                    data=item,
                    source=bridge_name
                )
        except Exception as e:
            logger.error(f"AllDom stream failed: {operator} on {target}: {e}")
            yield AllDomResult(
                operator=operator,
                target=target,
                success=False,
                error=str(e),
                source=bridge_name
            )

    async def scan(
        self,
        domain: str,
        depth: str = "fast",
        operators: Optional[List[str]] = None
    ) -> Dict[str, AllDomResult]:
        """
        Full domain scan combining multiple operators.

        Args:
            domain: Target domain to scan
            depth: "fast" (basic) or "full" (comprehensive)
            operators: Specific operators to run (default: based on depth)

        Returns:
            Dict mapping operator to result
        """
        await self._ensure_bridges()

        # Default operator sets by depth
        if operators is None:
            if depth == "fast":
                operators = ["whois:", "age!", "map!"]
            elif depth == "full":
                operators = [
                    "whois:", "age!", "ga!", "tech!",
                    "map!", "sub!", "sitemap:",
                    "bl?", "ol?",
                ]
            else:
                operators = ["whois:", "age!"]

        results = {}

        # Run operators concurrently
        tasks = [
            self.execute(op, domain)
            for op in operators
        ]

        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for op, result in zip(operators, completed):
            if isinstance(result, Exception):
                results[op] = AllDomResult(
                    operator=op,
                    target=domain,
                    success=False,
                    error=str(result)
                )
            else:
                results[op] = result

        return results

    def list_operators(self) -> List[Dict[str, str]]:
        """List all available operators with their routing info."""
        return [
            {
                "operator": op,
                "bridge": route[0],
                "method": route[1]
            }
            for op, route in self.OPERATOR_ROUTES.items()
        ]


# Convenience functions
async def execute(operator: str, target: str, **kwargs) -> AllDomResult:
    """Execute single operator (convenience function)."""
    ad = AllDom()
    return await ad.execute(operator, target, **kwargs)


async def scan(domain: str, depth: str = "fast") -> Dict[str, AllDomResult]:
    """Full domain scan (convenience function)."""
    ad = AllDom()
    return await ad.scan(domain, depth=depth)
