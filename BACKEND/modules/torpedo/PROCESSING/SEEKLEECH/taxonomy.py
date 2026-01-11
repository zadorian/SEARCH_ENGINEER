"""
SeekLeech Engine v2.0 - Thematic Taxonomy

Defines the thematic categories for classifying sources.
Used for filtering sources by topic (corporate, legal, property, etc.)
"""

from typing import Dict, List, Set


# ─────────────────────────────────────────────────────────────
# Thematic Taxonomy - Hierarchical Categories
# ─────────────────────────────────────────────────────────────

THEMATIC_TAXONOMY: Dict[str, Dict[str, str]] = {
    "corporate": {
        "corporate_registry": "Company registration and incorporation records",
        "officers": "Directors, officers, executives, board members",
        "shareholders": "Ownership, shareholdings, equity structure",
        "beneficial_ownership": "Ultimate beneficial owners (UBO), control structure",
        "filings": "Annual reports, financial statements, regulatory filings",
        "branches": "Subsidiaries, branch offices, affiliated entities",
        "trademarks": "Trademark registrations and applications",
        "patents": "Patent filings and registrations"
    },
    "legal": {
        "court_records": "Court cases, civil and criminal proceedings",
        "litigation": "Lawsuits, legal disputes, settlements",
        "bankruptcy": "Insolvency, restructuring, liquidation records",
        "liens": "Liens, charges, encumbrances, security interests",
        "enforcement": "Enforcement actions, penalties, fines",
        "judgments": "Court judgments and orders",
        "arbitration": "Arbitration proceedings and awards"
    },
    "property": {
        "land_registry": "Property ownership records, title deeds",
        "cadastre": "Land surveys, boundaries, parcel information",
        "mortgages": "Property charges, mortgages, secured loans",
        "planning": "Zoning, building permits, planning applications",
        "valuation": "Property valuations, assessments",
        "transactions": "Property sales, transfers, conveyances"
    },
    "regulatory": {
        "sanctions": "Sanctions lists, watchlists, embargoes",
        "pep": "Politically exposed persons databases",
        "licenses": "Business licenses, permits, authorizations",
        "procurement": "Government contracts, tenders, public procurement",
        "tax_records": "Tax filings, obligations, assessments",
        "adverse_media": "Negative news, regulatory actions",
        "compliance": "Compliance registers, regulatory notifications"
    },
    "financial": {
        "stock_exchange": "Listed company filings, stock exchange data",
        "banking": "Banking licenses, financial institution registers",
        "insurance": "Insurance company registers, policies",
        "investment": "Investment adviser registrations, fund data",
        "credit": "Credit ratings, creditworthiness data",
        "securities": "Securities filings, prospectuses"
    },
    "professional": {
        "lawyers": "Bar associations, lawyer registers, solicitor directories",
        "doctors": "Medical practitioner registers, healthcare professionals",
        "accountants": "CPA registers, auditor registrations",
        "engineers": "Professional engineer registers",
        "notaries": "Notary public registers",
        "architects": "Architect registrations"
    },
    "government": {
        "legislation": "Laws, statutes, regulations",
        "gazette": "Official gazettes, government publications",
        "parliament": "Parliamentary records, debates, votes",
        "cabinet": "Cabinet decisions, executive orders",
        "statistics": "Official statistics, census data"
    },
    "media": {
        "news": "News archives, press releases",
        "press": "Press releases, announcements",
        "documents": "Document repositories, archives"
    }
}


# ─────────────────────────────────────────────────────────────
# Flat list of all tags
# ─────────────────────────────────────────────────────────────

ALL_THEMATIC_TAGS: List[str] = []
for category, tags in THEMATIC_TAXONOMY.items():
    ALL_THEMATIC_TAGS.extend(tags.keys())


# ─────────────────────────────────────────────────────────────
# Tag to Category mapping
# ─────────────────────────────────────────────────────────────

TAG_TO_CATEGORY: Dict[str, str] = {}
for category, tags in THEMATIC_TAXONOMY.items():
    for tag in tags.keys():
        TAG_TO_CATEGORY[tag] = category


# ─────────────────────────────────────────────────────────────
# Input Type Mappings
# ─────────────────────────────────────────────────────────────

INPUT_TYPES: Dict[str, Dict[str, str]] = {
    "company_name": {
        "description": "Company or organization name",
        "examples": ["Acme Corp", "Deutsche Bank AG", "株式会社サンプル"],
        "default_format": "free_text"
    },
    "company_reg_id": {
        "description": "Company registration number or ID",
        "examples": ["12345678", "HRB 12345", "01234567-1-12"],
        "default_format": "alphanumeric"
    },
    "person_name": {
        "description": "Person's name",
        "examples": ["John Smith", "María García", "山田太郎"],
        "default_format": "free_text"
    },
    "case_number": {
        "description": "Court case or filing number",
        "examples": ["2023-CV-12345", "1:20-cv-01234"],
        "default_format": "formatted"
    },
    "property_address": {
        "description": "Property or land address",
        "examples": ["123 Main St", "1234/5 District 7"],
        "default_format": "free_text"
    },
    "parcel_id": {
        "description": "Land parcel or cadastral ID",
        "examples": ["12345-67-890", "0123/4567/89"],
        "default_format": "formatted"
    },
    "trademark": {
        "description": "Trademark name or number",
        "examples": ["ACME", "TM12345678"],
        "default_format": "free_text"
    },
    "patent_number": {
        "description": "Patent application or grant number",
        "examples": ["US12345678", "EP1234567"],
        "default_format": "formatted"
    },
    "date_range": {
        "description": "Date or date range filter",
        "examples": ["2020-01-01", "2020-01-01 to 2020-12-31"],
        "default_format": "date"
    },
    "keyword": {
        "description": "General keyword search",
        "examples": ["fraud", "sanctions", "bankruptcy"],
        "default_format": "free_text"
    }
}


# ─────────────────────────────────────────────────────────────
# Tag Detection Keywords
# ─────────────────────────────────────────────────────────────

TAG_KEYWORDS: Dict[str, List[str]] = {
    # Corporate
    "corporate_registry": [
        "company", "corporation", "business", "enterprise", "firm",
        "unternehmensregister", "handelsregister", "registro mercantil",
        "societe", "société", "gesellschaft", "corporate", "incorporat",
        "cégjegyzék", "rejestr", "registro", "cadastro"
    ],
    "officers": [
        "director", "officer", "executive", "board", "management",
        "geschäftsführer", "vorstand", "dirigeant", "administrador",
        "officer", "secretary", "ceo", "cfo"
    ],
    "shareholders": [
        "shareholder", "owner", "equity", "stockholder", "share",
        "aktionär", "actionnaire", "accionista", "ownership"
    ],
    "beneficial_ownership": [
        "beneficial owner", "ubo", "ultimate", "control",
        "wirtschaftlich berechtigter", "bénéficiaire effectif"
    ],
    "filings": [
        "filing", "annual report", "financial statement", "accounts",
        "jahresabschluss", "comptes annuels", "cuentas anuales"
    ],

    # Legal
    "court_records": [
        "court", "case", "judgment", "trial", "proceeding",
        "gericht", "tribunal", "juzgado", "cour", "rechtsprechung"
    ],
    "litigation": [
        "litigation", "lawsuit", "dispute", "claim", "sue"
    ],
    "bankruptcy": [
        "bankruptcy", "insolvency", "liquidation", "restructuring",
        "insolvenz", "konkurs", "faillite", "quiebra"
    ],
    "liens": [
        "lien", "charge", "encumbrance", "security", "mortgage",
        "pfandrecht", "hypothèque", "gravamen"
    ],

    # Property
    "land_registry": [
        "land", "property", "real estate", "title", "deed",
        "grundbuch", "cadastre", "catastro", "immobiliare"
    ],

    # Regulatory
    "sanctions": [
        "sanction", "watchlist", "embargo", "restricted", "blocked",
        "sdn", "ofac", "ofsi"
    ],
    "pep": [
        "pep", "politically exposed", "public official", "government official"
    ],
    "licenses": [
        "license", "permit", "authorization", "licence",
        "genehmigung", "autorisation", "permiso"
    ],
    "procurement": [
        "procurement", "tender", "contract", "bid", "public contract",
        "vergabe", "marché public", "contratación"
    ],

    # Financial
    "stock_exchange": [
        "stock", "exchange", "listed", "securities", "prospectus",
        "börse", "bourse", "bolsa"
    ],
    "banking": [
        "bank", "financial institution", "credit", "lending"
    ],
    "insurance": [
        "insurance", "insurer", "underwriter", "policy"
    ],

    # Professional
    "lawyers": [
        "lawyer", "attorney", "solicitor", "advocate", "bar", "barrister",
        "anwalt", "avocat", "abogado", "advokat"
    ],
    "doctors": [
        "doctor", "physician", "medical", "healthcare", "practitioner"
    ],
    "accountants": [
        "accountant", "cpa", "auditor", "chartered accountant"
    ]
}


# ─────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────

def detect_thematic_tags(text: str, url: str = "", domain: str = "") -> List[str]:
    """
    Detect thematic tags from text content, URL, and domain.
    Returns list of matching tags.
    """
    combined = f"{text} {url} {domain}".lower()
    detected: Set[str] = set()

    for tag, keywords in TAG_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in combined:
                detected.add(tag)
                break

    return list(detected)


def get_category_for_tag(tag: str) -> str:
    """Get parent category for a tag."""
    return TAG_TO_CATEGORY.get(tag, "misc")


def get_tags_for_category(category: str) -> List[str]:
    """Get all tags in a category."""
    return list(THEMATIC_TAXONOMY.get(category, {}).keys())


def get_related_tags(tag: str) -> List[str]:
    """Get related tags (same category)."""
    category = get_category_for_tag(tag)
    return get_tags_for_category(category)


def validate_tag(tag: str) -> bool:
    """Check if tag is valid."""
    return tag in ALL_THEMATIC_TAGS


def get_input_type_info(input_type: str) -> Dict[str, str]:
    """Get info about an input type."""
    return INPUT_TYPES.get(input_type, {
        "description": "Unknown input type",
        "examples": [],
        "default_format": "free_text"
    })


# ─────────────────────────────────────────────────────────────
# Section to Thematic Mapping
# ─────────────────────────────────────────────────────────────

SECTION_TO_THEMATIC: Dict[str, List[str]] = {
    "cr": ["corporate_registry", "officers", "shareholders", "beneficial_ownership", "filings"],
    "lit": ["court_records", "litigation", "bankruptcy", "liens", "judgments"],
    "reg": ["sanctions", "pep", "licenses", "compliance"],
    "at": ["land_registry", "cadastre", "mortgages", "property"],
    "misc": ["news", "documents", "government"]
}


def get_default_tags_for_section(section: str) -> List[str]:
    """Get default thematic tags for a section type."""
    return SECTION_TO_THEMATIC.get(section, [])
