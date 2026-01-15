"""
Concept Miner - Extracts and maps phrases from mined report data to concepts.

Reads from:
- report_genres.json - genre types and purpose indicators
- methodology_patterns.json - research methods and their contexts
- dead_ends_catalog.json - what was sought (sought_category)
- semantic_clusters.json - keyword clusters
- mined_sectors.json - sector-specific red flags
- mined_section_templates.json - section types and key phrases

Outputs additional example_phrases for each concept in CONCEPT_SETS.

IMPORTANT: Filters out case-specific content (company names, person names, etc.)
to ensure only generic conceptual vocabulary is used.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Any, Set

logger = logging.getLogger(__name__)


# =============================================================================
# CASE-SPECIFIC CONTENT FILTERS
# =============================================================================
# Patterns and words that indicate case-specific content to exclude

# Patterns that suggest case-specific content
CASE_SPECIFIC_PATTERNS = [
    r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b',  # Two capitalized words (likely names)
    r'\b[A-Z]{2,}\s+[A-Z][a-z]+\b',     # ACRONYM + Name
    r'\b(Mr\.|Mrs\.|Ms\.|Dr\.)\s+\w+',  # Titles with names
    r'\b\d{4}\b',                        # Years
    r'\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b', # Dates
    r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d', # Month + date
    r'https?://\S+',                     # URLs
    r'\b[A-Z]{3,}\b(?!\s+(Act|Law|Code|Regulation))',  # Acronyms (except legal)
    r'^\d+\s*%',                         # Percentage at start
    r'\bProject\s+[A-Z][A-Za-z]+\b',    # Project names
    r'\b(Pursuant to|According to)\s+', # Case-specific references
    r'\bfor\s+[A-Z][A-Za-z]+',          # "for [CompanyName]" patterns
    r'\bof\s+[A-Z][A-Za-z]+\s+(Ltd|LLC|Inc|Corp|SA|AG|GmbH|BV|NV|Holdings?|Holdco|Investments?|Group|Capital|Partners)\b',  # "of [Company Entity]"
    r'\b(Ltd|LLC|Inc|Corp|SA|AG|GmbH|BV|NV|SE|Plc|LP|LLP)\b',  # Company suffixes
    r'\b(Holdings?|Holdco|Investments?|Group|Capital|Partners|Industries|Enterprises|International|Worldwide)\b',  # Corporate suffixes
]

# Company name patterns - strong indicators this is case-specific
COMPANY_SUFFIX_PATTERNS = [
    r'\b\w+\s+(Ltd|LLC|Inc|Corp|SA|AG|GmbH|BV|NV|SE|Plc|LP|LLP|SARL|SRL|SpA|AS|AB|OY|KS|SL|Ltda)\b',
    r'\b\w+\s+(Holdings?|Holdco|Investments?|Group|Capital|Partners|Industries|Enterprises)\b',
    r'\b\w+\s+(International|Worldwide|Global|Europe|Asia|Americas|UK|US)\b',
]

# Specific words/phrases that are too generic or case-specific
EXCLUDED_PHRASES = {
    # Too generic
    "according to", "the company", "the subject", "our research", "no information",
    "was identified", "was found", "were identified", "were found", "no records",
    "according to the", "a search of", "a targeted search", "10 year scope",
    "access limitations", "no coverage found", "no instances found",

    # Case-specific indicators
    "project", "client", "pursuant to your request", "assignment completion",
    "desktop review", "our client", "the client", "interim report",

    # Meta-phrases about methodology, not concepts
    "generally believed", "highly likely", "matter of public record",
    "confirmed ownership structure", "revealed by",

    # Phrases that indicate case-specific content
    "accounts for", "statements for", "records for", "information for",
    "accounts of", "records of", " of hb", " of dis ", " of dsf ", " of bny ",
    "kyndryl", "kazakhtelecom", "marmor lux", "enke investments", "batumi",
    "content discovered", "gpay", "bulgarian", "mellon",
}

# Country/jurisdiction names to filter (case-specific)
JURISDICTION_WORDS = {
    "brazil", "brazilian", "germany", "german", "hungary", "hungarian",
    "serbia", "serbian", "russia", "russian", "ukraine", "ukrainian",
    "china", "chinese", "cyprus", "cypriot", "switzerland", "swiss",
    "austria", "austrian", "netherlands", "dutch", "luxembourg",
    "guernsey", "jersey", "isle of man", "cayman", "bvi", "british virgin",
    "panama", "bahamas", "bermuda", "malta", "liechtenstein",
    # But keep these as they're relevant to offshore concepts
}

# Words that indicate this is a TEMPLATE phrase (good to keep)
TEMPLATE_INDICATORS = {
    "ownership", "shareholder", "beneficial owner", "ubo", "director", "officer",
    "sanctions", "sanctioned", "ofac", "pep", "politically exposed",
    "offshore", "shell company", "nominee", "holding company", "subsidiary",
    "litigation", "lawsuit", "court", "regulatory", "compliance", "violation",
    "fraud", "corruption", "bribery", "money laundering", "aml",
    "financial statement", "annual report", "audit", "accounts",
}


def is_case_specific(phrase: str) -> bool:
    """
    Check if a phrase is case-specific (should be excluded).

    Returns True if the phrase contains:
    - Proper nouns (company/person names)
    - Specific dates, years, or numbers
    - Project names or client references
    - Country-specific content
    - Company names with legal suffixes (Ltd, Inc, GmbH, etc.)
    """
    phrase_lower = phrase.lower().strip()

    # Too short or too long
    if len(phrase_lower) < 10 or len(phrase_lower) > 200:
        return True

    # Check excluded phrases - these are ALWAYS excluded
    for excluded in EXCLUDED_PHRASES:
        if excluded in phrase_lower:
            return True

    # Strong company name patterns - ALWAYS exclude (e.g., "Acme Holdings")
    for pattern in COMPANY_SUFFIX_PATTERNS:
        if re.search(pattern, phrase, re.IGNORECASE):
            return True

    # Check for "for [SpecificEntity]" patterns - indicates case-specific
    # e.g., "Financial statements for Kyndryl Brazil subsidiary"
    for_entity_pattern = r'\bfor\s+[A-Z][A-Za-z]+(\s+[A-Z][A-Za-z]+)*'
    if re.search(for_entity_pattern, phrase):
        return True

    # Check for "of [SpecificEntity]" patterns with 2+ capitalized words
    # e.g., "Beneficial owners of HB – Zbirni Kastodi"
    of_entity_pattern = r'\bof\s+[A-Z][A-Za-z]+(\s+[A-Z][A-Za-z]+)+'
    if re.search(of_entity_pattern, phrase):
        return True

    # Check if it's a PURE template phrase (only template content, no proper nouns)
    has_template = any(t in phrase_lower for t in TEMPLATE_INDICATORS)
    if has_template:
        # Count proper nouns (capitalized words that aren't common words)
        words = phrase.split()
        common_caps = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'by', 'for', 'with', 'to'}
        proper_nouns = [w for w in words if len(w) > 2 and w[0].isupper()
                        and w.lower() not in common_caps
                        and not any(t.lower().startswith(w.lower()[:4]) for t in TEMPLATE_INDICATORS)]
        # If only 0-1 proper noun and has template indicator, keep it
        if len(proper_nouns) <= 1:
            return False  # Keep template phrase

    # Check case-specific patterns
    for pattern in CASE_SPECIFIC_PATTERNS:
        if re.search(pattern, phrase, re.IGNORECASE):
            return True

    # Check for capitalized words that suggest proper nouns
    words = phrase.split()
    capitalized_count = sum(1 for w in words if len(w) > 0 and w[0].isupper() and len(w) > 2)
    if capitalized_count >= 2 and len(words) <= 8:
        # Multiple capitalized words in short phrase = likely names
        return True

    return False


def clean_phrase(phrase: str) -> str:
    """Clean and normalize a phrase."""
    # Remove extra whitespace
    phrase = re.sub(r'\s+', ' ', phrase).strip()
    # Remove leading/trailing punctuation
    phrase = phrase.strip('.,;:()[]{}"\'-')
    return phrase


def filter_phrases(phrases: Set[str]) -> Set[str]:
    """Filter out case-specific phrases from a set."""
    filtered = set()
    for phrase in phrases:
        cleaned = clean_phrase(phrase)
        if cleaned and not is_case_specific(cleaned):
            filtered.add(cleaned)
    return filtered

# Path to matrix files
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MATRIX_PATH = PROJECT_ROOT / "input_output" / "matrix"
MATRIX_MERGED_PATH = MATRIX_PATH / "_merged"
MATRIX_BACKUP_PATH = PROJECT_ROOT / "input_output" / "matrix_backup_20251125"
MINED_PATH = MATRIX_BACKUP_PATH / "mined"


# =============================================================================
# CONCEPT CATEGORY MAPPINGS
# =============================================================================
# Map mined data categories to our concept IDs

GENRE_TO_CONCEPT = {
    # Primary/secondary types that map to concepts
    "beneficial_ownership_analysis": ["beneficial_ownership"],
    "sanctions_screening": ["sanctions_exposure"],
    "pep_screening": ["pep_exposure"],
    "political_exposure": ["pep_exposure"],
    "asset_trace": ["corporate_structure", "shareholder_information"],
    "fraud_investigation": ["fraud_indicators"],
    "litigation_support": ["legal_proceedings"],
    "regulatory_compliance_investigation": ["regulatory_violations", "regulatory_enforcement", "compliance_failures"],
    "corporate_intelligence": ["corporate_structure", "director_officer_info"],
    "due_diligence": ["beneficial_ownership", "sanctions_exposure", "reputation_damage"],
    "background_check": ["adverse_media", "director_officer_info", "negative_publicity"],
    "investigative_journalism": ["adverse_media", "corruption_bribery", "negative_publicity", "reputation_damage"],
    "governance_assessment": ["regulatory_violations", "esg_concerns", "compliance_failures"],
    "criminal_intelligence": ["fraud_indicators", "money_laundering_indicators", "government_investigations"],
    "forensic_analysis": ["fraud_indicators", "money_laundering_indicators"],
    "cyber_threat_intelligence": ["adverse_media"],
    # New mappings for reputation and regulatory
    "reputational_assessment": ["reputation_damage", "negative_publicity", "adverse_media"],
    "media_monitoring": ["negative_publicity", "adverse_media", "reputation_damage"],
    "esg_assessment": ["esg_concerns", "regulatory_violations"],
    "consumer_protection": ["customer_complaints", "regulatory_enforcement"],
    "licensing_investigation": ["license_issues", "regulatory_enforcement"],
    # INDUSTRY SECTOR MAPPINGS
    "energy_sector": ["energy_trading"],
    "oil_gas": ["energy_trading"],
    "commodities_trading": ["energy_trading"],
    "banking_sector": ["banking_finance"],
    "financial_services": ["banking_finance"],
    "fintech": ["banking_finance", "technology_software"],
    "real_estate": ["real_estate_property"],
    "property_development": ["real_estate_property"],
    "construction": ["construction_infrastructure"],
    "infrastructure": ["construction_infrastructure"],
    "technology": ["technology_software"],
    "software": ["technology_software"],
    "shipping": ["shipping_maritime"],
    "maritime": ["shipping_maritime"],
    "aviation": ["aviation_aerospace"],
    "aerospace": ["aviation_aerospace"],
    "healthcare": ["healthcare_pharma"],
    "pharmaceutical": ["healthcare_pharma"],
    "mining": ["mining_extractives"],
    "extractives": ["mining_extractives"],
    "defense": ["defense_military"],
    "military": ["defense_military"],
    "arms_trade": ["defense_military"],
    # STRUCTURE MAPPINGS
    "holding_structure_analysis": ["holding_company", "corporate_structure"],
    "nominee_investigation": ["nominee_arrangement"],
    "spv_analysis": ["special_purpose_vehicle"],
    "joint_venture_review": ["joint_venture"],
    "trust_investigation": ["trust_foundation"],
    # METHODOLOGY MAPPINGS (report types)
    "corporate_registry_report": ["corporate_registry_source"],
    "court_records_report": ["court_litigation_source"],
    "media_analysis_report": ["media_coverage"],
    "osint_report": ["social_media_osint"],
    "regulatory_filing_analysis": ["regulatory_filing_source"],
    # EVENTS MAPPINGS
    "ma_analysis": ["acquisition_merger"],
    "merger_investigation": ["acquisition_merger"],
    "bankruptcy_investigation": ["bankruptcy_insolvency"],
    "insolvency_review": ["bankruptcy_insolvency"],
    "ipo_analysis": ["ipo_listing"],
    "listing_review": ["ipo_listing"],
    "restructuring_analysis": ["restructuring"],
    "management_review": ["management_change"],
    "investigation_coverage": ["investigation_probe"],
    # GEOGRAPHIC RISK MAPPINGS
    "russia_cis_investigation": ["russia_cis_connection"],
    "russia_sanctions": ["russia_cis_connection", "sanctions_exposure"],
    "china_investigation": ["china_connection"],
    "china_nexus": ["china_connection"],
    "middle_east_investigation": ["middle_east_gulf"],
    "gulf_region_review": ["middle_east_gulf"],
}

METHOD_TO_CONCEPT = {
    "sanctions_screening": ["sanctions_exposure"],
    "pep_screening": ["pep_exposure"],
    "beneficial_ownership_analysis": ["beneficial_ownership"],
    "beneficial_ownership_registry": ["beneficial_ownership"],
    "beneficial_ownership_search": ["beneficial_ownership"],
    "corporate_registry_search": ["corporate_structure", "shareholder_information", "corporate_registry_source"],
    "court_search": ["legal_proceedings", "court_litigation_source"],
    "litigation_search": ["legal_proceedings", "court_litigation_source"],
    "regulatory_search": ["regulatory_violations", "regulatory_enforcement", "regulatory_filing_source"],
    "bankruptcy_search": ["regulatory_violations", "financial_statements", "compliance_failures", "bankruptcy_insolvency"],
    "insolvency_search": ["regulatory_violations", "financial_statements", "bankruptcy_insolvency"],
    "financial_records_search": ["financial_statements", "valuation_metrics"],
    "offshore_leaks_search": ["offshore_structure"],
    "offshore_database_search": ["offshore_structure"],
    "panama_papers_analysis": ["offshore_structure", "money_laundering_indicators"],
    "data_breach_analysis": ["adverse_media", "reputation_damage"],
    "dark_web_monitoring": ["adverse_media", "fraud_indicators"],
    "adverse_media_monitoring": ["adverse_media", "negative_publicity", "reputation_damage", "media_coverage"],
    # New methods for reputation and regulatory
    "reputational_search": ["reputation_damage", "negative_publicity"],
    "media_search": ["negative_publicity", "adverse_media", "media_coverage"],
    "esg_screening": ["esg_concerns"],
    "consumer_complaint_search": ["customer_complaints"],
    "license_search": ["license_issues"],
    "enforcement_search": ["regulatory_enforcement", "government_investigations"],
    "government_investigation_search": ["government_investigations", "investigation_probe"],
    "compliance_audit": ["compliance_failures"],
    # INDUSTRY/SECTOR METHODS
    "energy_sector_search": ["energy_trading"],
    "oil_gas_search": ["energy_trading"],
    "commodities_analysis": ["energy_trading"],
    "banking_search": ["banking_finance"],
    "financial_services_search": ["banking_finance"],
    "real_estate_search": ["real_estate_property"],
    "property_search": ["real_estate_property"],
    "construction_search": ["construction_infrastructure"],
    "infrastructure_search": ["construction_infrastructure"],
    "tech_sector_search": ["technology_software"],
    "shipping_search": ["shipping_maritime"],
    "maritime_search": ["shipping_maritime"],
    "aviation_search": ["aviation_aerospace"],
    "healthcare_search": ["healthcare_pharma"],
    "pharma_search": ["healthcare_pharma"],
    "mining_search": ["mining_extractives"],
    "extractives_search": ["mining_extractives"],
    "defense_search": ["defense_military"],
    # STRUCTURE METHODS
    "holding_structure_search": ["holding_company"],
    "nominee_search": ["nominee_arrangement"],
    "spv_search": ["special_purpose_vehicle"],
    "joint_venture_search": ["joint_venture"],
    "trust_search": ["trust_foundation"],
    # EVENTS METHODS
    "ma_search": ["acquisition_merger"],
    "merger_search": ["acquisition_merger"],
    "ipo_search": ["ipo_listing"],
    "restructuring_search": ["restructuring"],
    "management_change_search": ["management_change"],
    # GEOGRAPHIC RISK METHODS
    "russia_search": ["russia_cis_connection"],
    "cis_search": ["russia_cis_connection"],
    "china_search": ["china_connection"],
    "middle_east_search": ["middle_east_gulf"],
    "gulf_search": ["middle_east_gulf"],
    # SOCIAL MEDIA/OSINT
    "linkedin_search": ["social_media_osint"],
    "twitter_search": ["social_media_osint"],
    "social_media_search": ["social_media_osint"],
    "osint_search": ["social_media_osint"],
}

SOUGHT_CATEGORY_TO_CONCEPT = {
    "beneficial_ownership": ["beneficial_ownership"],
    "financial_information": ["financial_statements", "valuation_metrics"],
    "litigation_records": ["legal_proceedings"],
    "regulatory_records": ["regulatory_violations", "regulatory_enforcement", "compliance_failures"],
    "sanctions_status": ["sanctions_exposure"],
    # New categories
    "reputation": ["reputation_damage", "negative_publicity", "adverse_media"],
    "media_coverage": ["negative_publicity", "adverse_media"],
    "esg": ["esg_concerns"],
    "consumer_complaints": ["customer_complaints"],
    "licensing": ["license_issues"],
    "government_investigation": ["government_investigations"],
    "enforcement_actions": ["regulatory_enforcement"],
}

SECTION_TYPE_TO_CONCEPT = {
    "ownership_analysis": ["beneficial_ownership", "corporate_structure", "shareholder_information"],
    "biographical": ["director_officer_info"],
    "corporate_structure": ["corporate_structure", "director_officer_info"],
    "media_analysis": ["adverse_media", "negative_publicity", "reputation_damage"],
    "litigation": ["legal_proceedings"],
    "financial_analysis": ["financial_statements", "valuation_metrics"],
    "sanctions": ["sanctions_exposure"],
    "political_exposure": ["pep_exposure"],
    # New section types
    "reputation": ["reputation_damage", "negative_publicity"],
    "regulatory": ["regulatory_violations", "regulatory_enforcement", "compliance_failures"],
    "esg": ["esg_concerns"],
    "consumer": ["customer_complaints"],
    "licensing": ["license_issues"],
    "investigations": ["government_investigations"],
}

CLUSTER_TO_CONCEPT = {
    "control": ["beneficial_ownership", "corporate_structure", "shareholder_information", "director_officer_info"],
    "legal": ["sanctions_exposure", "legal_proceedings", "regulatory_violations", "government_investigations"],
    "financial": ["financial_statements", "valuation_metrics"],
    "network": ["corporate_structure"],
    # New clusters
    "reputation": ["reputation_damage", "negative_publicity", "adverse_media", "esg_concerns"],
    "regulatory": ["regulatory_enforcement", "license_issues", "compliance_failures", "government_investigations"],
    "consumer": ["customer_complaints"],
    # INDUSTRY CLUSTERS
    "energy": ["energy_trading"],
    "banking": ["banking_finance"],
    "real_estate": ["real_estate_property"],
    "construction": ["construction_infrastructure"],
    "technology": ["technology_software"],
    "shipping": ["shipping_maritime"],
    "aviation": ["aviation_aerospace"],
    "healthcare": ["healthcare_pharma"],
    "mining": ["mining_extractives"],
    "defense": ["defense_military"],
    # STRUCTURE CLUSTERS
    "holding": ["holding_company", "corporate_structure"],
    "nominee": ["nominee_arrangement", "offshore_structure"],
    "spv": ["special_purpose_vehicle"],
    "partnership": ["joint_venture"],
    "trust": ["trust_foundation"],
    # METHODOLOGY CLUSTERS
    "registry": ["corporate_registry_source"],
    "court": ["court_litigation_source", "legal_proceedings"],
    "media": ["media_coverage", "adverse_media"],
    "osint": ["social_media_osint"],
    "filing": ["regulatory_filing_source"],
    # EVENTS CLUSTERS
    "merger": ["acquisition_merger"],
    "bankruptcy": ["bankruptcy_insolvency"],
    "ipo": ["ipo_listing"],
    "restructure": ["restructuring"],
    "leadership": ["management_change"],
    "investigation": ["investigation_probe", "government_investigations"],
    # GEOGRAPHIC CLUSTERS
    "russia": ["russia_cis_connection"],
    "cis": ["russia_cis_connection"],
    "china": ["china_connection"],
    "middle_east": ["middle_east_gulf"],
    "gulf": ["middle_east_gulf"],
}


def load_json_file(path: Path) -> Dict:
    """Load JSON file safely."""
    if not path.exists():
        logger.warning(f"File not found: {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {path}: {e}")
        return {}


def extract_from_genres(data: Dict) -> Dict[str, Set[str]]:
    """Extract phrases from report_genres.json."""
    phrases_by_concept: Dict[str, Set[str]] = {}

    genre_profiles = data.get("genre_profiles", {})

    for genre_type, profile in genre_profiles.items():
        # Get mapped concepts for this genre
        concepts = GENRE_TO_CONCEPT.get(genre_type, [])

        # Add purpose indicators as phrases
        for indicator in profile.get("purpose_indicators", []):
            if len(indicator) > 10:  # Skip very short phrases
                for concept in concepts:
                    if concept not in phrases_by_concept:
                        phrases_by_concept[concept] = set()
                    phrases_by_concept[concept].add(indicator)

    return phrases_by_concept


def extract_from_methodology(data: Dict) -> Dict[str, Set[str]]:
    """Extract phrases from methodology_patterns.json."""
    phrases_by_concept: Dict[str, Set[str]] = {}

    # Extract from method counts - these are the method types
    method_counts = data.get("method_counts", {})

    for method_type in method_counts.keys():
        concepts = METHOD_TO_CONCEPT.get(method_type, [])
        # Convert method type to natural phrase
        phrase = method_type.replace("_", " ")
        for concept in concepts:
            if concept not in phrases_by_concept:
                phrases_by_concept[concept] = set()
            phrases_by_concept[concept].add(phrase)

    return phrases_by_concept


def extract_from_dead_ends(data: Dict) -> Dict[str, Set[str]]:
    """Extract phrases from dead_ends_catalog.json."""
    phrases_by_concept: Dict[str, Set[str]] = {}

    # Extract from by_jurisdiction
    for jurisdiction, dead_ends in data.get("by_jurisdiction", {}).items():
        for dead_end in dead_ends:
            sought = dead_end.get("sought", "")
            sought_category = dead_end.get("sought_category", "")

            concepts = SOUGHT_CATEGORY_TO_CONCEPT.get(sought_category, [])

            if sought and len(sought) > 10:
                for concept in concepts:
                    if concept not in phrases_by_concept:
                        phrases_by_concept[concept] = set()
                    phrases_by_concept[concept].add(sought)

    return phrases_by_concept


def extract_from_semantic_clusters(data: Dict) -> Dict[str, Set[str]]:
    """Extract phrases from semantic_clusters.json."""
    phrases_by_concept: Dict[str, Set[str]] = {}

    clusters = data.get("clusters", [])

    for cluster in clusters:
        cluster_id = cluster.get("id", "")
        concepts = CLUSTER_TO_CONCEPT.get(cluster_id, [])

        # Add keywords as phrases
        for keyword in cluster.get("keywords", []):
            for concept in concepts:
                if concept not in phrases_by_concept:
                    phrases_by_concept[concept] = set()
                phrases_by_concept[concept].add(keyword)

        # Add code labels as phrases (convert from snake_case)
        for code_label in cluster.get("code_labels", {}).values():
            phrase = code_label.replace("_", " ")
            for concept in concepts:
                if concept not in phrases_by_concept:
                    phrases_by_concept[concept] = set()
                phrases_by_concept[concept].add(phrase)

    return phrases_by_concept


def extract_from_sections(data: Dict) -> Dict[str, Set[str]]:
    """Extract phrases from mined_section_templates.json."""
    phrases_by_concept: Dict[str, Set[str]] = {}

    templates = data.get("templates", [])

    for template in templates:
        section_type = template.get("section_type", "")
        concepts = SECTION_TYPE_TO_CONCEPT.get(section_type, [])

        # Add typical content as phrases
        for content in template.get("typical_content", []):
            if len(content) > 10:
                for concept in concepts:
                    if concept not in phrases_by_concept:
                        phrases_by_concept[concept] = set()
                    phrases_by_concept[concept].add(content)

        # Add key phrases
        for phrase in template.get("key_phrases", []):
            if len(phrase) > 10:
                for concept in concepts:
                    if concept not in phrases_by_concept:
                        phrases_by_concept[concept] = set()
                    phrases_by_concept[concept].add(phrase)

    return phrases_by_concept


def extract_from_sectors(data: Dict) -> Dict[str, Set[str]]:
    """Extract red flags and industry concepts from mined_sectors.json."""
    phrases_by_concept: Dict[str, Set[str]] = {}

    # Map sector names to industry concepts
    SECTOR_TO_INDUSTRY = {
        "energy": "energy_trading",
        "oil": "energy_trading",
        "gas": "energy_trading",
        "commodities": "energy_trading",
        "trading": "energy_trading",
        "utilities": "energy_trading",
        "banking": "banking_finance",
        "finance": "banking_finance",
        "financial": "banking_finance",
        "fintech": "banking_finance",
        "investment": "banking_finance",
        "private equity": "banking_finance",
        "real estate": "real_estate_property",
        "property": "real_estate_property",
        "construction": "construction_infrastructure",
        "infrastructure": "construction_infrastructure",
        "engineering": "construction_infrastructure",
        "technology": "technology_software",
        "software": "technology_software",
        "tech": "technology_software",
        "it": "technology_software",
        "digital": "technology_software",
        "shipping": "shipping_maritime",
        "maritime": "shipping_maritime",
        "logistics": "shipping_maritime",
        "freight": "shipping_maritime",
        "aviation": "aviation_aerospace",
        "aerospace": "aviation_aerospace",
        "airline": "aviation_aerospace",
        "healthcare": "healthcare_pharma",
        "pharma": "healthcare_pharma",
        "pharmaceutical": "healthcare_pharma",
        "medical": "healthcare_pharma",
        "biotech": "healthcare_pharma",
        "mining": "mining_extractives",
        "extractives": "mining_extractives",
        "minerals": "mining_extractives",
        "metals": "mining_extractives",
        "defense": "defense_military",
        "military": "defense_military",
        "arms": "defense_military",
        "weapons": "defense_military",
        "security": "defense_military",
    }

    sectors = data.get("sectors", [])

    for sector in sectors:
        sector_name = sector.get("sector", "").lower()

        # Map sector to industry concept
        for keyword, concept in SECTOR_TO_INDUSTRY.items():
            if keyword in sector_name:
                if concept not in phrases_by_concept:
                    phrases_by_concept[concept] = set()
                # Add sector description as a phrase
                if sector.get("description"):
                    phrases_by_concept[concept].add(sector.get("description"))

        # Red flags often map to compliance concepts
        for red_flag in sector.get("red_flags", []):
            if len(red_flag) > 15:
                # Map red flags to appropriate concepts
                red_flag_lower = red_flag.lower()

                if "offshore" in red_flag_lower or "nominee" in red_flag_lower:
                    if "offshore_structure" not in phrases_by_concept:
                        phrases_by_concept["offshore_structure"] = set()
                    phrases_by_concept["offshore_structure"].add(red_flag)

                if "ownership" in red_flag_lower or "beneficial" in red_flag_lower:
                    if "beneficial_ownership" not in phrases_by_concept:
                        phrases_by_concept["beneficial_ownership"] = set()
                    phrases_by_concept["beneficial_ownership"].add(red_flag)

                if "regulatory" in red_flag_lower or "compliance" in red_flag_lower:
                    if "regulatory_violations" not in phrases_by_concept:
                        phrases_by_concept["regulatory_violations"] = set()
                    phrases_by_concept["regulatory_violations"].add(red_flag)

                if "procurement" in red_flag_lower or "tender" in red_flag_lower:
                    if "corruption_bribery" not in phrases_by_concept:
                        phrases_by_concept["corruption_bribery"] = set()
                    phrases_by_concept["corruption_bribery"].add(red_flag)

                if "complex" in red_flag_lower or "obscuring" in red_flag_lower:
                    if "money_laundering_indicators" not in phrases_by_concept:
                        phrases_by_concept["money_laundering_indicators"] = set()
                    phrases_by_concept["money_laundering_indicators"].add(red_flag)

                # Map red flags to geographic risk concepts
                if "russia" in red_flag_lower or "cis" in red_flag_lower or "ukraine" in red_flag_lower:
                    if "russia_cis_connection" not in phrases_by_concept:
                        phrases_by_concept["russia_cis_connection"] = set()
                    phrases_by_concept["russia_cis_connection"].add(red_flag)

                if "china" in red_flag_lower or "chinese" in red_flag_lower or "prc" in red_flag_lower:
                    if "china_connection" not in phrases_by_concept:
                        phrases_by_concept["china_connection"] = set()
                    phrases_by_concept["china_connection"].add(red_flag)

                if "middle east" in red_flag_lower or "gulf" in red_flag_lower or "uae" in red_flag_lower or "qatar" in red_flag_lower or "saudi" in red_flag_lower:
                    if "middle_east_gulf" not in phrases_by_concept:
                        phrases_by_concept["middle_east_gulf"] = set()
                    phrases_by_concept["middle_east_gulf"].add(red_flag)

        # Typical structures map to corporate/ownership concepts
        for structure in sector.get("typical_structures", []):
            if len(structure) > 15:
                structure_lower = structure.lower()

                if "offshore" in structure_lower or "jersey" in structure_lower or "guernsey" in structure_lower:
                    if "offshore_structure" not in phrases_by_concept:
                        phrases_by_concept["offshore_structure"] = set()
                    phrases_by_concept["offshore_structure"].add(structure)

                if "holding" in structure_lower or "subsidiary" in structure_lower:
                    if "corporate_structure" not in phrases_by_concept:
                        phrases_by_concept["corporate_structure"] = set()
                    phrases_by_concept["corporate_structure"].add(structure)
                    if "holding_company" not in phrases_by_concept:
                        phrases_by_concept["holding_company"] = set()
                    phrases_by_concept["holding_company"].add(structure)

                if "nominee" in structure_lower:
                    if "nominee_arrangement" not in phrases_by_concept:
                        phrases_by_concept["nominee_arrangement"] = set()
                    phrases_by_concept["nominee_arrangement"].add(structure)

                if "spv" in structure_lower or "special purpose" in structure_lower:
                    if "special_purpose_vehicle" not in phrases_by_concept:
                        phrases_by_concept["special_purpose_vehicle"] = set()
                    phrases_by_concept["special_purpose_vehicle"].add(structure)

                if "joint venture" in structure_lower or "jv" in structure_lower:
                    if "joint_venture" not in phrases_by_concept:
                        phrases_by_concept["joint_venture"] = set()
                    phrases_by_concept["joint_venture"].add(structure)

                if "trust" in structure_lower or "foundation" in structure_lower or "stiftung" in structure_lower:
                    if "trust_foundation" not in phrases_by_concept:
                        phrases_by_concept["trust_foundation"] = set()
                    phrases_by_concept["trust_foundation"].add(structure)

    return phrases_by_concept


def merge_phrase_sets(*phrase_dicts: Dict[str, Set[str]]) -> Dict[str, List[str]]:
    """Merge multiple phrase dictionaries and convert sets to lists."""
    merged: Dict[str, Set[str]] = {}

    for phrase_dict in phrase_dicts:
        for concept, phrases in phrase_dict.items():
            if concept not in merged:
                merged[concept] = set()
            merged[concept].update(phrases)

    # Convert to lists and sort
    return {k: sorted(list(v)) for k, v in merged.items()}


def mine_concept_phrases() -> Dict[str, List[str]]:
    """
    Main function: Extract all mined phrases mapped to concepts.

    Returns:
        Dict mapping concept_id -> list of example phrases from mined data
    """
    logger.info("Mining concept phrases from report library...")

    # Load all source files
    genres = load_json_file(MATRIX_MERGED_PATH / "report_genres.json")
    methodology = load_json_file(MATRIX_MERGED_PATH / "methodology_patterns.json")
    dead_ends = load_json_file(MATRIX_MERGED_PATH / "dead_ends_catalog.json")
    clusters = load_json_file(MATRIX_PATH / "semantic_clusters.json")
    sections = load_json_file(MINED_PATH / "mined_section_templates.json")
    sectors = load_json_file(MINED_PATH / "mined_sectors.json")

    # Extract phrases from each source
    genre_phrases = extract_from_genres(genres)
    method_phrases = extract_from_methodology(methodology)
    dead_end_phrases = extract_from_dead_ends(dead_ends)
    cluster_phrases = extract_from_semantic_clusters(clusters)
    section_phrases = extract_from_sections(sections)
    sector_phrases = extract_from_sectors(sectors)

    # Merge all
    merged = merge_phrase_sets(
        genre_phrases,
        method_phrases,
        dead_end_phrases,
        cluster_phrases,
        section_phrases,
        sector_phrases,
    )

    # Apply case-specific filtering to remove company/person names, dates, etc.
    filtered: Dict[str, List[str]] = {}
    filtered_count = 0
    for concept, phrases in merged.items():
        phrase_set = set(phrases)
        original_count = len(phrase_set)
        clean_set = filter_phrases(phrase_set)
        filtered_count += original_count - len(clean_set)
        filtered[concept] = sorted(list(clean_set))

    # Log stats
    total_phrases = sum(len(v) for v in filtered.values())
    logger.info(f"Mined {total_phrases} phrases across {len(filtered)} concepts (filtered {filtered_count} case-specific phrases)")
    for concept, phrases in sorted(filtered.items()):
        logger.debug(f"  {concept}: {len(phrases)} phrases")

    return filtered


def get_enhanced_phrases_for_concept(concept_id: str, base_phrases: List[str]) -> List[str]:
    """
    Get enhanced phrases for a single concept by combining base phrases with mined phrases.

    Args:
        concept_id: The concept identifier (e.g., "beneficial_ownership")
        base_phrases: The original example_phrases from CONCEPT_SETS

    Returns:
        Combined list of phrases (base + mined), deduplicated
    """
    mined = mine_concept_phrases()
    mined_for_concept = mined.get(concept_id, [])

    # Combine and deduplicate
    all_phrases = list(set(base_phrases + mined_for_concept))

    # Filter out very short phrases
    all_phrases = [p for p in all_phrases if len(p) > 8]

    return sorted(all_phrases)


# Pre-compute mined phrases (cached)
_MINED_PHRASES_CACHE: Dict[str, List[str]] = {}


def get_mined_phrases() -> Dict[str, List[str]]:
    """Get cached mined phrases."""
    global _MINED_PHRASES_CACHE
    if not _MINED_PHRASES_CACHE:
        _MINED_PHRASES_CACHE = mine_concept_phrases()
    return _MINED_PHRASES_CACHE


if __name__ == "__main__":
    # Test mining
    logging.basicConfig(level=logging.INFO)

    phrases = mine_concept_phrases()

    print("\n=== MINED CONCEPT PHRASES ===\n")
    for concept, phrase_list in sorted(phrases.items()):
        print(f"\n{concept} ({len(phrase_list)} phrases):")
        for p in phrase_list[:10]:  # Show first 10
            print(f"  - {p}")
        if len(phrase_list) > 10:
            print(f"  ... and {len(phrase_list) - 10} more")
