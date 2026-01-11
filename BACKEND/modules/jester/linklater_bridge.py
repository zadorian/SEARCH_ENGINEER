"""
Jester → Linklater Bridge

Connects document entity extraction (Jester) with link intelligence (Linklater).
When Jester extracts entities from documents, this bridge automatically triggers
Linklater discovery to expand the investigation.

Usage:
    # After Jester extraction
    from jester.linklater_bridge import JesterLinklaterBridge

    bridge = JesterLinklaterBridge()
    result = await bridge.on_entities_extracted(
        entities={"companies": [...], "persons": [...], "emails": [...]},
        source_document="report.pdf",
        project_id="investigation_123"
    )

    # Or trigger for a specific atom
    result = await bridge.process_atom_entities(atom)
"""

import re
import logging
import asyncio
from typing import Dict, List, Any, Optional, Set
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JesterLinklaterBridge")

# Common free email providers to skip
COMMON_EMAIL_PROVIDERS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com",
    "aol.com", "icloud.com", "me.com", "mac.com", "msn.com", "mail.com",
    "protonmail.com", "proton.me", "yandex.com", "yandex.ru", "mail.ru",
    "gmx.com", "gmx.de", "web.de", "qq.com", "163.com", "126.com",
    "zoho.com", "fastmail.com", "tutanota.com", "hey.com"
}

# Lazy imports for Linklater modules
# These are imported at runtime to avoid asyncio event loop issues
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Flag to indicate if Linklater is available (checked on first use)
LINKLATER_AVAILABLE = True  # Assume available until proven otherwise
ENTITY_EXTRACTION_AVAILABLE = True

def _get_unified_discovery():
    """Lazily import UnifiedDiscovery to avoid import-time asyncio issues."""
    global LINKLATER_AVAILABLE
    try:
        from linklater.discovery.unified_discovery import UnifiedDiscovery
        return UnifiedDiscovery
    except (ImportError, RuntimeError) as e:
        logger.warning(f"UnifiedDiscovery not available: {e}")
        LINKLATER_AVAILABLE = False
        return None

def _get_backlink_pipeline():
    """Lazily import AutomatedBacklinkPipeline to avoid import-time asyncio issues."""
    global LINKLATER_AVAILABLE, ENTITY_EXTRACTION_AVAILABLE
    try:
        from linklater.pipelines import AutomatedBacklinkPipeline, ENTITY_EXTRACTION_AVAILABLE as ea
        ENTITY_EXTRACTION_AVAILABLE = ea
        return AutomatedBacklinkPipeline
    except (ImportError, RuntimeError) as e:
        logger.warning(f"AutomatedBacklinkPipeline not available: {e}")
        LINKLATER_AVAILABLE = False
        ENTITY_EXTRACTION_AVAILABLE = False
        return None


class JesterLinklaterBridge:
    """
    Bridge between Jester (document extraction) and Linklater (link intelligence).

    Automatically triggers Linklater discovery when Jester extracts entities.
    """

    def __init__(
        self,
        max_companies: int = 10,
        max_emails: int = 10,
        max_domains_per_company: int = 4,
        enable_backlinks: bool = True,
        enable_subdomains: bool = True,
        enable_entity_extraction: bool = True,
    ):
        """
        Initialize the bridge.

        Args:
            max_companies: Max company names to process per document
            max_emails: Max email domains to process per document
            max_domains_per_company: Max domain variants per company name
            enable_backlinks: Whether to run backlink discovery
            enable_subdomains: Whether to run subdomain discovery
            enable_entity_extraction: Whether to extract entities from backlinks
        """
        self.max_companies = max_companies
        self.max_emails = max_emails
        self.max_domains_per_company = max_domains_per_company
        self.enable_backlinks = enable_backlinks
        self.enable_subdomains = enable_subdomains
        self.enable_entity_extraction = enable_entity_extraction and ENTITY_EXTRACTION_AVAILABLE

        if not LINKLATER_AVAILABLE:
            logger.warning("Linklater not available - bridge will be limited")

    async def on_entities_extracted(
        self,
        entities: Dict[str, List[Any]],
        source_document: str = "",
        project_id: Optional[str] = None,
        entity_labels: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point - triggered when Jester finishes entity extraction.

        Args:
            entities: Dict with entity lists. Supports two formats:
                - Simple: {"companies": ["Acme Ltd"], "emails": ["a@b.com"], ...}
                - Jester format: {"entities": [{"text": "Acme", "label": "ORG"}, ...]}
            source_document: Path or ID of source document
            project_id: Optional project context
            entity_labels: Mapping of Jester labels to entity types
                          e.g., {"ORG": "company", "PER": "person", "EMAIL": "email"}

        Returns:
            Dict with discovery results:
            {
                "domains_discovered": [...],
                "backlinks_found": [...],
                "entities_from_backlinks": [...],
                "alerts": [...],
                "elapsed_ms": int,
                "source_document": str
            }
        """
        start_time = datetime.now()

        results = {
            "source_document": source_document,
            "project_id": project_id,
            "domains_discovered": [],
            "domains_verified": [],
            "backlinks_found": [],
            "entities_from_backlinks": [],
            "alerts": [],
            "errors": [],
            "stats": {
                "companies_processed": 0,
                "emails_processed": 0,
                "domains_tried": 0,
                "domains_verified": 0,
            },
            "elapsed_ms": 0,
        }

        if not LINKLATER_AVAILABLE:
            results["errors"].append("Linklater modules not available")
            return results

        # Normalize entity format
        normalized = self._normalize_entities(entities, entity_labels)

        # 1. Company names → Domain discovery
        companies = normalized.get("companies", [])[:self.max_companies]
        if companies:
            company_results = await self._process_companies(companies, project_id)
            results["domains_discovered"].extend(company_results.get("domains", []))
            results["domains_verified"].extend(company_results.get("verified", []))
            results["stats"]["companies_processed"] = len(companies)
            results["stats"]["domains_tried"] = company_results.get("domains_tried", 0)
            results["stats"]["domains_verified"] = len(company_results.get("verified", []))

        # 2. Email domains → Backlink search
        emails = normalized.get("emails", [])[:self.max_emails]
        if emails and self.enable_backlinks:
            email_results = await self._process_emails(emails, project_id)
            results["backlinks_found"].extend(email_results.get("backlinks", []))
            results["entities_from_backlinks"].extend(email_results.get("entities", []))
            results["stats"]["emails_processed"] = len(emails)

        # 3. Gather alerts from discovery
        for domain_info in results["domains_verified"]:
            if domain_info.get("alerts"):
                results["alerts"].extend(domain_info["alerts"])

        results["elapsed_ms"] = int((datetime.now() - start_time).total_seconds() * 1000)

        logger.info(
            f"JesterLinklaterBridge complete: {results['stats']['companies_processed']} companies, "
            f"{results['stats']['emails_processed']} emails, "
            f"{results['stats']['domains_verified']} domains verified, "
            f"{len(results['backlinks_found'])} backlinks, "
            f"{results['elapsed_ms']}ms"
        )

        return results

    def _normalize_entities(
        self,
        entities: Dict[str, Any],
        label_map: Optional[Dict[str, str]] = None
    ) -> Dict[str, List[str]]:
        """
        Normalize entity format from Jester's nested format to simple lists.

        Handles both:
        - Simple: {"companies": ["Acme"], "emails": ["a@b.com"]}
        - Jester: {"entities": [{"text": "Acme", "label": "ORG"}, ...]}
        """
        # Default label mapping
        default_labels = {
            "ORG": "companies",
            "ORGANIZATION": "companies",
            "COMPANY": "companies",
            "PER": "persons",
            "PERSON": "persons",
            "EMAIL": "emails",
            "PHONE": "phones",
            "GPE": "locations",
            "LOC": "locations",
            "LOCATION": "locations",
            "ADDRESS": "addresses",
            "MONEY": "amounts",
            "DATE": "dates",
        }

        label_map = {**default_labels, **(label_map or {})}

        result = {
            "companies": [],
            "persons": [],
            "emails": [],
            "phones": [],
            "locations": [],
            "addresses": [],
            "amounts": [],
            "dates": [],
        }

        # Handle Jester nested format
        if "entities" in entities and isinstance(entities["entities"], list):
            for entity in entities["entities"]:
                if isinstance(entity, dict):
                    text = entity.get("text", "").strip()
                    label = entity.get("label", "").upper()

                    target_key = label_map.get(label)
                    if target_key and text:
                        result[target_key].append(text)

        # Handle direct format (companies, emails, etc. as top-level keys)
        for key in ["companies", "persons", "emails", "phones", "locations", "addresses"]:
            if key in entities:
                values = entities[key]
                if isinstance(values, list):
                    result[key].extend([v for v in values if isinstance(v, str)])
                elif isinstance(values, dict):
                    # Handle dict format: {"company_name": count, ...}
                    result[key].extend(list(values.keys()))

        # Deduplicate
        for key in result:
            result[key] = list(dict.fromkeys(result[key]))  # Preserve order, remove dupes

        return result

    async def _process_companies(
        self,
        companies: List[str],
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process company names: infer domain names and run discovery.
        """
        results = {
            "domains": [],
            "verified": [],
            "domains_tried": 0,
        }

        for company in companies:
            domain_candidates = self._company_to_domains(company)
            results["domains_tried"] += len(domain_candidates)

            for domain in domain_candidates:
                results["domains"].append({
                    "domain": domain,
                    "source_type": "company",
                    "source_value": company,
                })

                # Try subdomain discovery to verify domain exists
                if self.enable_subdomains:
                    try:
                        UnifiedDiscoveryClass = _get_unified_discovery()
                        if not UnifiedDiscoveryClass:
                            logger.warning("UnifiedDiscovery not available - skipping subdomain discovery")
                            continue
                        discovery = UnifiedDiscoveryClass(domain)
                        subdomain_result = await discovery.discover_subdomains(domain)

                        if subdomain_result.get("subdomains"):
                            results["verified"].append({
                                "domain": domain,
                                "source_company": company,
                                "subdomains": subdomain_result["subdomains"][:20],
                                "subdomain_count": len(subdomain_result.get("subdomains", [])),
                                "alerts": subdomain_result.get("alerts", []),
                            })
                            logger.info(f"Verified domain {domain} from company '{company}' - {len(subdomain_result.get('subdomains', []))} subdomains")
                            break  # Found a valid domain for this company
                    except Exception as e:
                        logger.debug(f"Domain {domain} discovery failed: {e}")

        return results

    async def _process_emails(
        self,
        emails: List[str],
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process email addresses: extract domains and run backlink discovery.
        """
        results = {
            "backlinks": [],
            "entities": [],
        }

        # Extract unique domains from emails
        domains: Set[str] = set()
        for email in emails:
            if "@" in email:
                domain = email.split("@")[1].lower().strip()
                if domain and domain not in COMMON_EMAIL_PROVIDERS:
                    domains.add(domain)

        # Run backlink discovery for each domain
        for domain in domains:
            try:
                AutomatedBacklinkPipelineClass = _get_backlink_pipeline()
                if not AutomatedBacklinkPipelineClass:
                    logger.warning("AutomatedBacklinkPipeline not available - skipping backlink discovery")
                    continue
                pipeline = AutomatedBacklinkPipelineClass(
                    domain,
                    extract_entities=self.enable_entity_extraction,
                    max_entity_pages=20,
                )
                backlink_result = await pipeline.run()

                backlinks = backlink_result.get("backlinks", [])
                if backlinks:
                    results["backlinks"].extend([
                        {
                            **bl,
                            "source_type": "email_domain",
                            "source_email": next((e for e in emails if domain in e), None),
                        }
                        for bl in backlinks[:50]  # Limit per domain
                    ])

                    logger.info(f"Found {len(backlinks)} backlinks for email domain {domain}")

                # Collect entities from backlink pages
                entities = backlink_result.get("aggregated_entities", {})
                if entities:
                    results["entities"].append({
                        "source_domain": domain,
                        "entities": entities,
                    })

            except Exception as e:
                logger.warning(f"Backlink discovery failed for {domain}: {e}")

        return results

    def _company_to_domains(self, company: str) -> List[str]:
        """
        Generate likely domain names from a company name.

        Examples:
            "Acme Holdings Ltd" → ["acmeholdings.com", "acmeholdings.co", "acme-holdings.com", ...]
            "ЮНЕСКО" → ["unesco.com", "unesco.org", ...]
        """
        domains = []

        # Clean company name
        clean = company.lower()

        # Remove common suffixes
        suffixes = [
            " ltd", " limited", " inc", " incorporated", " corp", " corporation",
            " llc", " plc", " gmbh", " ag", " sa", " s.a.", " bv", " nv",
            " oy", " ab", " as", " aps", " srl", " spa", " s.p.a.",
            " ооо", " оао", " зао", " пао",  # Russian
            " בע\"מ",  # Hebrew
        ]
        for suffix in suffixes:
            if clean.endswith(suffix):
                clean = clean[:-len(suffix)]

        # Remove punctuation except hyphens
        clean = re.sub(r'[^\w\s-]', '', clean)

        # Create slug variants
        words = clean.split()

        # No spaces (acmeholdings)
        slug_nospace = ''.join(words)

        # With hyphens (acme-holdings)
        slug_hyphen = '-'.join(words)

        # First word only (acme)
        slug_first = words[0] if words else ""

        # Initials for long names (ah for "Acme Holdings")
        slug_initials = ''.join(w[0] for w in words if w) if len(words) > 2 else ""

        # Common TLDs
        tlds = [".com", ".co", ".io", ".net"]

        # Generate combinations
        seen = set()
        for slug in [slug_nospace, slug_hyphen, slug_first]:
            if slug and len(slug) >= 3 and slug not in seen:
                seen.add(slug)
                for tld in tlds[:self.max_domains_per_company]:
                    domain = slug + tld
                    if domain not in [d for d in domains]:
                        domains.append(domain)

        # Add initials variant for long names
        if slug_initials and len(slug_initials) >= 2:
            domains.append(slug_initials + ".com")

        return domains[:self.max_domains_per_company * 3]

    async def process_atom_entities(
        self,
        atom: Dict[str, Any],
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process entities from a single Jester atom.

        Args:
            atom: Jester atom dict with 'entities' field
            project_id: Optional project context

        Returns:
            Discovery results
        """
        entities = atom.get("entities", [])
        source_doc = atom.get("source_file", atom.get("atom_id", "unknown"))

        return await self.on_entities_extracted(
            entities={"entities": entities},
            source_document=source_doc,
            project_id=project_id,
        )

    async def process_batch_atoms(
        self,
        atoms: List[Dict[str, Any]],
        project_id: Optional[str] = None,
        max_concurrent: int = 5,
    ) -> Dict[str, Any]:
        """
        Process entities from multiple Jester atoms in parallel.

        Args:
            atoms: List of Jester atom dicts
            project_id: Optional project context
            max_concurrent: Max concurrent discovery tasks

        Returns:
            Aggregated discovery results
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_limit(atom):
            async with semaphore:
                return await self.process_atom_entities(atom, project_id)

        tasks = [process_with_limit(atom) for atom in atoms if atom.get("entities")]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        aggregated = {
            "atoms_processed": len(atoms),
            "atoms_with_entities": len(tasks),
            "domains_discovered": [],
            "domains_verified": [],
            "backlinks_found": [],
            "entities_from_backlinks": [],
            "alerts": [],
            "errors": [],
        }

        for result in results:
            if isinstance(result, Exception):
                aggregated["errors"].append(str(result))
            elif isinstance(result, dict):
                aggregated["domains_discovered"].extend(result.get("domains_discovered", []))
                aggregated["domains_verified"].extend(result.get("domains_verified", []))
                aggregated["backlinks_found"].extend(result.get("backlinks_found", []))
                aggregated["entities_from_backlinks"].extend(result.get("entities_from_backlinks", []))
                aggregated["alerts"].extend(result.get("alerts", []))

        return aggregated


# Convenience functions
async def bridge_jester_to_linklater(
    entities: Dict[str, Any],
    source_document: str = "",
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to bridge Jester entities to Linklater.

    Args:
        entities: Jester entity output
        source_document: Source document path/ID
        project_id: Project context

    Returns:
        Linklater discovery results
    """
    bridge = JesterLinklaterBridge()
    return await bridge.on_entities_extracted(
        entities=entities,
        source_document=source_document,
        project_id=project_id,
    )


def is_bridge_available() -> bool:
    """Check if Linklater bridge is available."""
    return LINKLATER_AVAILABLE


# CLI interface
if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Jester → Linklater Bridge")
    parser.add_argument("--entities-file", help="JSON file with entities", required=True)
    parser.add_argument("--source", help="Source document name", default="manual_input")
    parser.add_argument("--project", help="Project ID", default=None)
    parser.add_argument("--output", help="Output JSON file", default="bridge_results.json")

    args = parser.parse_args()

    with open(args.entities_file, 'r') as f:
        entities = json.load(f)

    async def run():
        result = await bridge_jester_to_linklater(
            entities=entities,
            source_document=args.source,
            project_id=args.project,
        )

        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2, default=str)

        print(f"Results saved to {args.output}")
        print(f"Domains verified: {len(result.get('domains_verified', []))}")
        print(f"Backlinks found: {len(result.get('backlinks_found', []))}")

    asyncio.run(run())
