#!/usr/bin/env python3
"""
FORENSIC SEARCH API - Unified Interface
========================================
Single entry point for all forensic search operations.

Features:
- Rule-based query building (no API needed)
- Gemini AI-powered investigation
- Forensic scoring with depth priority
- Authenticity validation
- Dynamic questioning
- Export to JSON/TXT

Usage:
    from forensic_api import ForensicAPI
    
    api = ForensicAPI()
    
    # Rule-based (no API key needed)
    queries = api.build_queries("John Smith", company="Acme Corp")
    
    # AI-powered (requires GOOGLE_API_KEY)
    report = await api.investigate("John Smith", context="Director at Acme")
    
    # Score a result
    score = api.score_result("http://example.com/staff.pdf", "pdf", "page_4_plus")
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import logging

# Import our modules
try:
    from forensic_gemini import (
        ForensicSearchAgent,
        ForensicScorer,
        AuthenticityValidator,
        ForensicGeminiClient,
        MAX_OUTPUT_TOKENS,
        FORENSIC_MASTER_PROMPT,
        # Also import query building components from forensic_gemini
        ForensicQueryBuilder as MandatoryQueryBuilder,
    )
    # DynamicQuestioner may be in forensic_gemini or separate file
    try:
        from query_refiner import (
            DynamicQuestioner,
            HIGH_AUTHORITY_EXCLUSIONS,
            ROLE_EXPANSIONS,
            quick_expand,
            get_exclusion_string,
            get_role_or_clause
        )
    except ImportError:
        # Fallback - these are also available in forensic_gemini
        DynamicQuestioner = None
        HIGH_AUTHORITY_EXCLUSIONS = []
        ROLE_EXPANSIONS = {}
        quick_expand = None
        get_exclusion_string = None
        get_role_or_clause = None
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some modules not available: {e}")
    MODULES_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# =============================================================================
# UNIFIED API CLASS
# =============================================================================

class ForensicAPI:
    """
    Unified API for Forensic Search operations.
    
    Provides both rule-based and AI-powered search capabilities
    with forensic scoring that prioritizes depth over authority.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Forensic API.
        
        Args:
            api_key: Google API key for Gemini (optional for rule-based operations)
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        
        # Initialize components
        self.scorer = ForensicScorer()
        self.validator = AuthenticityValidator()
        self.questioner = DynamicQuestioner()
        self.builder = MandatoryQueryBuilder()
        
        # Lazy load Gemini client
        self._gemini = None
        self._agent = None
        
        logger.info("ForensicAPI initialized")
        if not self.api_key:
            logger.info("  → Running in rule-based mode (no API key)")
        else:
            logger.info("  → API key available for AI operations")
    
    @property
    def gemini(self):
        """Lazy-load Gemini client"""
        if self._gemini is None and self.api_key:
            try:
                self._gemini = ForensicGeminiClient(self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Gemini: {e}")
        return self._gemini
    
    @property
    def agent(self):
        """Lazy-load full agent"""
        if self._agent is None:
            self._agent = ForensicSearchAgent(self.api_key)
        return self._agent
    
    # =========================================================================
    # CORE OPERATIONS
    # =========================================================================
    
    def build_queries(
        self,
        target: str,
        pivot: Optional[str] = None,
        company: Optional[str] = None,
        role: Optional[str] = None,
        location: Optional[str] = None,
        year_range: Optional[Tuple[int, int]] = None,
        include_negative_fingerprints: bool = True
    ) -> Dict[str, Any]:
        """
        Build comprehensive forensic queries (rule-based, no API needed).
        
        Includes ALL mandatory operators:
        - filetype:pdf
        - inurl: variations
        - before:/after: temporal
        - archive searches
        
        Args:
            target: The main search target (anchor)
            pivot: Optional secondary identifier
            company: Company/organization context
            role: Job title/role (will be OR-expanded)
            location: Geographic location
            year_range: Tuple of (start_year, end_year)
            include_negative_fingerprints: Whether to add exclusion queries
        
        Returns:
            Dict with queries organized by tier and metadata
        """
        # Build queries
        queries_by_tier = self.builder.build_mandatory_queries(
            anchor=target,
            pivot=pivot,
            company=company,
            role=role,
            location=location,
            year_range=year_range
        )
        
        # Get refinement data
        refinement = self.questioner.refine_query(
            target, pivot, company, location, role
        )
        
        # Flatten for easier consumption
        flat_queries = self.builder.flatten_queries(queries_by_tier)
        
        # Calculate stats
        tier_counts = {tier: len(qs) for tier, qs in queries_by_tier.items() if qs}
        
        return {
            "meta": {
                "target": target,
                "pivot": pivot,
                "company": company,
                "role": role,
                "location": location,
                "year_range": year_range,
                "timestamp": datetime.now().isoformat(),
                "mode": "rule_based",
                "mandatory_operators": {
                    "filetype": True,
                    "inurl": True,
                    "temporal": True,
                    "archive": True
                }
            },
            "refinement": {
                "name_variations": refinement.or_variations,
                "negative_fingerprints": refinement.negative_fingerprints,
                "context_terms": refinement.context_terms,
                "questions_applied": refinement.questions_applied
            },
            "queries_by_tier": queries_by_tier,
            "queries_flat": flat_queries,
            "statistics": {
                "total_queries": len(flat_queries),
                "tier_distribution": tier_counts
            }
        }
    
    async def investigate(
        self,
        target: str,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run AI-powered forensic investigation using Gemini.
        
        Requires GOOGLE_API_KEY to be set.
        
        Args:
            target: Investigation target
            context: Additional context
        
        Returns:
            Full investigation report with queries and results
        """
        if not self.gemini:
            raise ValueError(
                "Gemini client not available. "
                "Set GOOGLE_API_KEY or use build_queries() for rule-based operation."
            )
        
        return await self.gemini.generate_queries(target, context)
    
    def score_result(
        self,
        url: str,
        source_type: str = "unknown",
        page_position: str = "unknown"
    ) -> Dict[str, Any]:
        """
        Score a search result using forensic criteria.
        
        Scoring prioritizes:
        - Depth (page 1 is PENALIZED, page 4+ is BONUS)
        - Low-authority sources (forums, blogs, PDFs score higher)
        - Authenticity (invalid URLs score 0)
        
        Args:
            url: Result URL
            source_type: Type of source (pdf, forum, blog, news, etc.)
            page_position: Estimated Google result position
        
        Returns:
            Score breakdown with recommendation
        """
        # Validate URL
        is_valid, reason = self.validator.validate(url)
        
        # Calculate score
        score, breakdown = self.scorer.score(
            url=url,
            source_type=source_type,
            page_position=page_position,
            is_authentic=is_valid
        )
        
        # Determine recommendation
        if score >= 80:
            recommendation = "CRITICAL - High forensic value, low-authority deep source"
        elif score >= 60:
            recommendation = "HIGH - Good forensic value, investigate further"
        elif score >= 40:
            recommendation = "MEDIUM - Standard result, may contain useful info"
        else:
            recommendation = "LOW - High-authority or shallow result, likely already visible"
        
        return {
            "url": url,
            "forensic_score": score,
            "score_breakdown": breakdown,
            "authenticity": {
                "verified": is_valid,
                "reason": reason
            },
            "recommendation": recommendation
        }
    
    def validate_url(self, url: str) -> Dict[str, Any]:
        """
        Validate a URL for authenticity.
        
        Checks for:
        - Valid structure
        - Real TLD
        - No hallucination patterns
        
        Args:
            url: URL to validate
        
        Returns:
            Validation result with reason
        """
        is_valid, reason = self.validator.validate(url)
        return {
            "url": url,
            "is_valid": is_valid,
            "reason": reason
        }
    
    # =========================================================================
    # UTILITY OPERATIONS
    # =========================================================================
    
    def expand_role(self, role: str) -> List[str]:
        """Expand a role/title into OR-stackable variations"""
        return self.questioner.expand_role(role)
    
    def get_name_variations(self, name: str) -> List[str]:
        """Generate realistic name variations"""
        return self.questioner.generate_name_variations(name)
    
    def get_negative_fingerprints(self, anchor: str) -> List[str]:
        """Get negative fingerprints for a term"""
        return self.questioner.identify_negative_fingerprints(anchor)
    
    def get_exclusion_string(self, num_domains: int = 6) -> str:
        """Get authority exclusion string for queries"""
        return " ".join(f"-site:{d}" for d in HIGH_AUTHORITY_EXCLUSIONS[:num_domains])
    
    def get_role_or_clause(self, role: str) -> str:
        """Get OR clause for a role"""
        variations = self.expand_role(role)
        return " OR ".join(f'"{v}"' for v in variations)
    
    def get_system_prompt(self) -> str:
        """Get the forensic system prompt for custom implementations"""
        return FORENSIC_MASTER_PROMPT
    
    # =========================================================================
    # EXPORT OPERATIONS
    # =========================================================================
    
    def export_queries(
        self,
        data: Dict[str, Any],
        filename: Optional[str] = None,
        format: str = "json"
    ) -> str:
        """
        Export queries to file.
        
        Args:
            data: Query data to export
            filename: Output filename (auto-generated if None)
            format: "json" or "txt"
        
        Returns:
            Path to exported file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target = data.get("meta", {}).get("target", "investigation")
            target_safe = "".join(c for c in target if c.isalnum() or c in " _-")[:30]
            filename = f"forensic_{target_safe}_{timestamp}.{format}"
        
        if format == "json":
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        elif format == "txt":
            with open(filename, 'w') as f:
                f.write(f"FORENSIC SEARCH QUERIES\n")
                f.write(f"{'='*60}\n")
                f.write(f"Target: {data.get('meta', {}).get('target', 'N/A')}\n")
                f.write(f"Generated: {datetime.now().isoformat()}\n")
                f.write(f"\n")
                
                for tier, queries in data.get("queries_by_tier", {}).items():
                    if queries:
                        f.write(f"\n{tier.upper()}\n")
                        f.write(f"{'-'*40}\n")
                        for q in queries:
                            f.write(f"  {q}\n")
                
                f.write(f"\n{'='*60}\n")
                f.write(f"Total queries: {data.get('statistics', {}).get('total_queries', 0)}\n")
        
        logger.info(f"Exported to: {filename}")
        return filename


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def build_queries(
    target: str,
    company: Optional[str] = None,
    role: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Quick query building without explicit API instantiation"""
    api = ForensicAPI()
    return api.build_queries(target, company=company, role=role, **kwargs)


def score_result(url: str, source_type: str = "unknown", page_position: str = "unknown") -> Dict:
    """Quick result scoring"""
    api = ForensicAPI()
    return api.score_result(url, source_type, page_position)


def expand_role(role: str) -> List[str]:
    """Quick role expansion"""
    api = ForensicAPI()
    return api.expand_role(role)


async def investigate(target: str, context: Optional[str] = None) -> Dict[str, Any]:
    """Quick AI investigation"""
    api = ForensicAPI()
    return await api.investigate(target, context)


# =============================================================================
# CLI INTERFACE
# =============================================================================

async def interactive_cli():
    """Interactive command-line interface"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║           FORENSIC SEARCH API - Interactive Mode             ║
║                                                              ║
║   Commands: build, score, expand, investigate, export, quit  ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    api = ForensicAPI()
    current_data = None
    
    while True:
        try:
            cmd = input("\n> ").strip().lower()
            
            if cmd == "quit" or cmd == "exit":
                print("Goodbye!")
                break
            
            elif cmd == "build":
                target = input("  Target: ").strip()
                company = input("  Company (Enter to skip): ").strip() or None
                role = input("  Role (Enter to skip): ").strip() or None
                
                current_data = api.build_queries(target, company=company, role=role)
                
                print(f"\n  ✓ Generated {current_data['statistics']['total_queries']} queries")
                print(f"\n  Tier distribution:")
                for tier, count in current_data['statistics']['tier_distribution'].items():
                    print(f"    {tier}: {count}")
                
                print(f"\n  Sample queries:")
                for q in current_data['queries_flat'][:5]:
                    print(f"    [{q['tier']}] {q['q'][:60]}...")
            
            elif cmd == "score":
                url = input("  URL to score: ").strip()
                source = input("  Source type (pdf/forum/blog/news/unknown): ").strip() or "unknown"
                position = input("  Page position (page_1/page_2/page_3/page_4_plus/unknown): ").strip() or "unknown"
                
                result = api.score_result(url, source, position)
                
                print(f"\n  Forensic Score: {result['forensic_score']}/100")
                print(f"  Breakdown: {result['score_breakdown']}")
                print(f"  Authentic: {result['authenticity']['verified']}")
                print(f"  Recommendation: {result['recommendation']}")
            
            elif cmd == "expand":
                role = input("  Role to expand: ").strip()
                variations = api.expand_role(role)
                print(f"\n  Variations: {', '.join(variations)}")
                print(f"  OR clause: ({' OR '.join(f'\"{v}\"' for v in variations)})")
            
            elif cmd == "investigate":
                if not api.gemini:
                    print("  ✗ API key not available. Use 'build' for rule-based queries.")
                    continue
                
                target = input("  Investigation target: ").strip()
                context = input("  Additional context (Enter to skip): ").strip() or None
                
                print("  Running AI investigation...")
                result = await api.investigate(target, context)
                
                print(f"\n  ✓ Investigation complete")
                if "queries" in result:
                    print(f"  Generated {len(result['queries'])} queries")
                current_data = result
            
            elif cmd == "export":
                if not current_data:
                    print("  ✗ No data to export. Run 'build' or 'investigate' first.")
                    continue
                
                format_choice = input("  Format (json/txt): ").strip() or "json"
                filename = api.export_queries(current_data, format=format_choice)
                print(f"  ✓ Exported to: {filename}")
            
            elif cmd == "help":
                print("""
  Commands:
    build       - Build forensic queries (rule-based)
    score       - Score a URL with forensic criteria
    expand      - Expand a role into OR variations
    investigate - Run AI-powered investigation (requires API key)
    export      - Export current data to file
    quit        - Exit
                """)
            
            else:
                print(f"  Unknown command: {cmd}. Type 'help' for commands.")
        
        except KeyboardInterrupt:
            print("\n  Interrupted. Type 'quit' to exit.")
        except Exception as e:
            print(f"  Error: {e}")


async def main():
    """Main entry point"""
    import sys
    
    if len(sys.argv) > 1:
        # CLI mode with arguments
        cmd = sys.argv[1]
        
        if cmd == "build" and len(sys.argv) >= 3:
            target = sys.argv[2]
            company = sys.argv[4] if len(sys.argv) > 4 and sys.argv[3] == "--company" else None
            role = sys.argv[4] if len(sys.argv) > 4 and sys.argv[3] == "--role" else None
            
            api = ForensicAPI()
            result = api.build_queries(target, company=company, role=role)
            print(json.dumps(result, indent=2, default=str))
        
        elif cmd == "score" and len(sys.argv) >= 3:
            url = sys.argv[2]
            api = ForensicAPI()
            result = api.score_result(url)
            print(json.dumps(result, indent=2))
        
        else:
            print("Usage:")
            print("  python forensic_api.py                    # Interactive mode")
            print("  python forensic_api.py build <target>     # Build queries")
            print("  python forensic_api.py score <url>        # Score URL")
    else:
        # Interactive mode
        await interactive_cli()


if __name__ == "__main__":
    asyncio.run(main())