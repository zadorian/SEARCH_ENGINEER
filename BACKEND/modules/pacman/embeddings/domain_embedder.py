#!/usr/bin/env python3
"""
LINKLATER Domain Content Embedder

Embeds scraped domain content (including archived versions) into Elasticsearch
for semantic search and RAG-based questioning via C0GN1T0.

Features:
- intfloat/multilingual-e5-large (1024 dims) via StandardEmbedder for multilingual support
- 512-token chunking with 50-token overlap
- Elasticsearch dense_vector storage
- Domain-scoped vector search
- RAG integration for GPT-5-mini questioning

Usage:
    from modules.LINKLATER.domain_embedder import DomainEmbedder

    embedder = DomainEmbedder()
    await embedder.embed_content(domain="example.com", url="https://...", content="...", source="cc")
    results = await embedder.search(domain="example.com", query="what products do they sell?", limit=10)
"""

import os
import re
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib
import numpy as np

# Standard Embedder
try:
    import sys
    if '/data' not in sys.path:
        sys.path.insert(0, '/data')
    from shared.embedders import StandardEmbedder, EMBEDDING_DIM as STD_EMBEDDING_DIM
    EMBEDDER_AVAILABLE = True
except ImportError:
    EMBEDDER_AVAILABLE = False

# Elasticsearch
try:
    from elasticsearch import AsyncElasticsearch
    ES_AVAILABLE = True
except ImportError:
    ES_AVAILABLE = False

# Tiktoken for accurate token counting
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

logger = logging.getLogger("LINKLATER.DomainEmbedder")

# Configuration
INDEX_NAME = "cymonides-2"  # Use existing corpus index
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"  # 1024 dims, multilingual
EMBEDDING_DIMS = 1024
CHUNK_SIZE = 512  # tokens
CHUNK_OVERLAP = 50  # tokens
BATCH_SIZE = 50  # embeddings per API call

# Document type for domain content in cymonides-2
DOC_TYPE = "domain_content"

# =============================================================================
# CONCEPT SETS - Semantic classifiers for auto-detecting content types
# =============================================================================
# Each concept has:
#   - id: Unique identifier (used as tag)
#   - name: Human-readable name
#   - description: What this concept captures
#   - example_phrases: Representative phrases that get embedded and averaged
#   - threshold: Minimum cosine similarity to trigger (default 0.65)
#   - category: Grouping for related concepts
# =============================================================================

CONCEPT_SETS: List[Dict[str, Any]] = [
    # =========================================================================
    # OWNERSHIP & CORPORATE STRUCTURE
    # =========================================================================
    {
        "id": "beneficial_ownership",
        "name": "Beneficial Ownership",
        "description": "Content about ultimate beneficial owners, UBOs, and ownership stakes",
        "category": "ownership",
        "threshold": 0.52,
        "example_phrases": [
            "beneficial owner holds 25% or more of the shares",
            "ultimate beneficial owner of the company",
            "UBO disclosure requirements under anti-money laundering regulations",
            "person who ultimately owns or controls the legal entity",
            "beneficial ownership register and transparency",
            "individual who exercises significant control",
            "ownership structure showing natural persons at the top",
            "declaration of ultimate beneficial ownership",
            # From mined methodology patterns
            "traced ownership through chain of holding companies",
            "piercing the corporate veil to identify true owner",
            "ownership obscured through nominee arrangements",
            "control exercised through voting agreements",
            "economic beneficiary versus legal owner distinction",
            "PSC register showing person with significant control",
            "trust deed revealing underlying beneficiaries",
            "power of attorney granting control rights",
        ]
    },
    {
        "id": "corporate_structure",
        "name": "Corporate Structure",
        "description": "Organizational charts, subsidiaries, parent companies, holding structures",
        "category": "ownership",
        "threshold": 0.50,
        "example_phrases": [
            "corporate group structure with subsidiaries",
            "wholly owned subsidiary of the parent company",
            "holding company that owns operating entities",
            "organizational structure of the corporate group",
            "intermediate holding company in the Netherlands",
            "subsidiary undertakings and associated companies",
            "parent company controls through direct and indirect shareholdings",
            "special purpose vehicle established for the transaction",
            # From mined methodology patterns
            "branch versus subsidiary analysis",
            "dormant company within group structure",
            "consolidated accounts requirement threshold",
            "exemption from audit for small subsidiary",
            "foreign branch registration requirements",
            "representative office versus local incorporation",
            "vertical versus horizontal group structure",
            "minority interest in associated company",
            # From mined jurisdictions (entity types across 77 countries)
            "AG Aktiengesellschaft joint-stock company in Switzerland or Germany",
            "GmbH Gesellschaft mit beschränkter Haftung German limited liability company",
            "B.V. Besloten Vennootschap Dutch Private Limited Company",
            "N.V. Naamloze Vennootschap Dutch Public Limited Company",
            "Kft Limited liability company in Hungary",
            "Zrt Joint-stock company in Hungary",
            "S.a.r.l. Luxembourg Private limited liability company",
            "Ltd Private Limited Company in UK",
            "PTE Limited Private Limited Company in Singapore",
            "SRL società a responsabilità limitata Italian limited liability company",
            "SA Sociedad Anónima Spanish public limited company",
            "Sp z o o Polish Limited Liability Company",
            "a.s. joint stock company in Czech Republic",
            "OY Finnish limited company",
            "AB Swedish limited company",
        ]
    },
    {
        "id": "shareholder_information",
        "name": "Shareholder Information",
        "description": "Information about shareholders, equity stakes, share capital",
        "category": "ownership",
        "threshold": 0.50,
        "example_phrases": [
            "major shareholders holding more than 5%",
            "shareholder register shows the following equity holders",
            "share capital divided into ordinary and preference shares",
            "shareholders agreement governing voting rights",
            "institutional investors own majority stake",
            "minority shareholder protection provisions",
            "significant shareholding notification threshold",
            "capital structure and equity ownership breakdown",
            # From mined methodology patterns
            "convertible instrument affecting fully diluted ownership",
            "share pledge securing financing arrangement",
            "drag along and tag along rights",
            "anti-dilution protection for investor",
            "liquidation preference in preference shares",
            "voting trust concentrating control",
            "treasury shares and buyback program",
            "warrant exercise affecting ownership",
        ]
    },
    {
        "id": "director_officer_info",
        "name": "Directors & Officers",
        "description": "Board members, executives, management, key personnel",
        "category": "ownership",
        "threshold": 0.50,
        "example_phrases": [
            "board of directors comprises the following members",
            "chief executive officer appointed by the board",
            "non-executive director with oversight responsibilities",
            "management team includes experienced executives",
            "key management personnel and their remuneration",
            "directors' responsibilities and fiduciary duties",
            "corporate governance and board composition",
            "senior executives with significant influence",
            # From mined methodology patterns
            "professional director serving on multiple boards",
            "nominee director representing shareholder interest",
            "independent director for audit committee",
            "alternate director stepping in for absent member",
            "shadow director exercising actual control",
            "de facto director without formal appointment",
            "disqualified director serving in contravention",
            "company secretary with administrative duties",
        ]
    },

    # =========================================================================
    # COMPLIANCE RED FLAGS
    # =========================================================================
    {
        "id": "sanctions_exposure",
        "name": "Sanctions & Embargoes",
        "description": "References to sanctions, embargoes, OFAC, restricted parties",
        "category": "compliance_red_flag",
        "threshold": 0.55,
        "example_phrases": [
            "designated under OFAC sanctions program",
            "entity appears on EU consolidated sanctions list",
            "comprehensive sanctions imposed by United Nations",
            "trade embargo restrictions apply to this jurisdiction",
            "specially designated nationals and blocked persons list",
            "sanctioned individual with ties to the regime",
            "export control restrictions under EAR regulations",
            "secondary sanctions risk from transactions",
            # From mined methodology patterns
            "checked compliance databases and World-Check for sanctions or watchlist entries",
            "searched major international sanctioning bodies and watchlists",
            "confirm no sanctions by UN Security Council EU or US OFAC",
            "checked FinCEN Files leak data for suspicious transactions",
            "cross-referenced management team against international sanctions watchlists",
            "confirm no current shareholders or management subject to UN EU or OFAC sanctions",
            "searched lists from major international sanctioning bodies and law enforcement",
            "multiple sanctions databases and watchlists searched for subject names",
        ]
    },
    {
        "id": "pep_exposure",
        "name": "PEP Exposure",
        "description": "Politically exposed persons, government officials, state connections",
        "category": "compliance_red_flag",
        "threshold": 0.52,
        "example_phrases": [
            "politically exposed person serving as government minister",
            "former senior government official with regulatory influence",
            "close associate of politically exposed person",
            "family member of senior political figure",
            "head of state-owned enterprise under government control",
            "senior military official or general officer",
            "member of parliament or legislative assembly",
            "ambassador or senior diplomatic representative",
            # From mined methodology patterns
            "son of former president with family business ties",
            "regional governor with oversight of state contracts",
            "central bank official influencing monetary policy",
            "spouse of cabinet minister involved in procurement",
            "former intelligence service officer now in business",
            "political party treasurer managing campaign funds",
            "state enterprise director with appointment power",
            "judicial official with case assignment authority",
        ]
    },
    {
        "id": "offshore_structure",
        "name": "Offshore Structures",
        "description": "Shell companies, tax havens, offshore jurisdictions, nominee arrangements",
        "category": "compliance_red_flag",
        "threshold": 0.52,
        "example_phrases": [
            "company incorporated in British Virgin Islands",
            "offshore holding structure in the Cayman Islands",
            "nominee director and nominee shareholder arrangement",
            "bearer share company with anonymous ownership",
            "tax haven jurisdiction with bank secrecy laws",
            "shell company with no substantial operations",
            "offshore trust in Jersey or Guernsey",
            "mailbox company with registered agent only",
            # From mined sector structures
            "offshore vehicle networks for asset concealment",
            "Jersey-registered trading entities with nominee shareholders",
            "Cyprus nominee ownership with local professional directors",
            "founding shareholders transferring to nominees before investigation",
            "use of nominees for sensitive jurisdictions",
            "ownership through Guernsey and offshore LLC structures",
            "multiple subsidiary layers through Dutch BV entities",
            "high-value luxury properties with complex offshore ownership",
            # From mined jurisdictions (77 country profiles)
            "disclosure of shareholders is not mandated by law in the Cayman Islands",
            "BVI provides significant privacy protection for beneficial owners",
            "Belize jurisdiction used for offshore holding structures",
            "Jersey jurisdiction commonly used for aviation companies and high-value assets",
            "Guernsey had zero capital gains tax and corporation tax for most companies",
            "Seychelles provides corporate secrecy suitable for offshore structures",
            "Marshall Islands popular jurisdiction for shipping company registration",
            "Liberia commonly used for offshore holding structures",
            "Luxembourg entity used as foreign finance vehicle",
            "Netherlands used extensively for holding company structures",
            "Switzerland company ownership details for private companies not required to be disclosed",
            "Singapore privacy laws limit disclosure of ultimate beneficial ownership",
            "St Vincent popular jurisdiction for offshore trading platforms",
            "Bermuda Digital Asset Business license for cryptocurrency trading",
            "Isle of Man aviation registry provides comprehensive ownership tracking",
        ]
    },
    {
        "id": "money_laundering_indicators",
        "name": "Money Laundering Indicators",
        "description": "AML red flags, suspicious transactions, layering, placement",
        "category": "compliance_red_flag",
        "threshold": 0.55,
        "example_phrases": [
            "suspicious activity report filed with financial intelligence unit",
            "complex layering through multiple jurisdictions",
            "placement of cash proceeds through shell companies",
            "integration of illicit funds into legitimate business",
            "unusual transaction patterns inconsistent with business profile",
            "structuring transactions to avoid reporting thresholds",
            "round-trip transaction with no apparent business purpose",
            "money laundering typology identified in FATF guidance",
            # From mined methodology patterns
            "trade-based money laundering through over-invoicing",
            "real estate purchases with unexplained wealth",
            "correspondent banking used to move illicit funds",
            "smurfing deposits below reporting thresholds",
            "shell company receiving funds without services rendered",
            "casino chip transactions for cash conversion",
            "virtual currency used to obscure transaction trail",
            "front company generating fictitious revenue",
        ]
    },
    {
        "id": "corruption_bribery",
        "name": "Corruption & Bribery",
        "description": "FCPA, UK Bribery Act, kickbacks, improper payments",
        "category": "compliance_red_flag",
        "threshold": 0.55,
        "example_phrases": [
            "violation of Foreign Corrupt Practices Act",
            "bribery of foreign government officials",
            "improper payments to secure government contracts",
            "kickback scheme involving procurement officials",
            "facilitation payments to customs officers",
            "corrupt practices in public procurement process",
            "UK Bribery Act compliance program",
            "agent fees potentially disguising improper payments",
            # From mined methodology patterns
            "third-party intermediary with government connections",
            "success fee contingent on contract award",
            "consulting agreement with no clear deliverables",
            "payment routed through high-risk jurisdiction",
            "lavish entertainment of foreign officials",
            "family members hired by vendor after contract award",
            "donation to charity affiliated with decision-maker",
            "inflated subcontract to politically connected firm",
        ]
    },
    {
        "id": "fraud_indicators",
        "name": "Fraud Indicators",
        "description": "Financial fraud, misrepresentation, accounting irregularities",
        "category": "compliance_red_flag",
        "threshold": 0.52,
        "example_phrases": [
            "fraudulent misrepresentation to investors",
            "accounting irregularities discovered by auditors",
            "material misstatement in financial reports",
            "Ponzi scheme defrauding investors",
            "securities fraud charges filed by regulators",
            "falsified invoices for non-existent goods",
            "embezzlement of company funds by executives",
            "inflated revenue through fictitious transactions",
            # From mined methodology patterns
            "round-tripping revenue to inflate growth metrics",
            "related party transactions not properly disclosed",
            "channel stuffing to meet quarterly targets",
            "bill and hold arrangements without substance",
            "capitalization of expenses that should be expensed",
            "cookie jar reserves manipulation",
            "side letters modifying contract terms",
            "aggressive revenue recognition before delivery",
        ]
    },
    {
        "id": "regulatory_violations",
        "name": "Regulatory Violations",
        "description": "Enforcement actions, fines, license revocations, compliance failures",
        "category": "compliance_red_flag",
        "threshold": 0.50,
        "example_phrases": [
            "enforcement action taken by financial regulator",
            "substantial fine imposed for compliance violations",
            "license revoked due to regulatory breaches",
            "consent order requiring remediation measures",
            "cease and desist order issued by authorities",
            "compliance failures identified in regulatory examination",
            "deferred prosecution agreement with Department of Justice",
            "settlement reached without admitting wrongdoing",
            # From mined methodology patterns
            "MiFID II violation and market abuse fine",
            "GDPR breach resulting in regulatory action",
            "antitrust investigation and cartel allegations",
            "environmental permit violations and EPA enforcement",
            "health and safety prosecution after incident",
            "labor law violations and employment tribunal",
            "tax evasion charges by revenue authorities",
            "import export control violations and customs penalties",
        ]
    },
    {
        "id": "adverse_media",
        "name": "Adverse Media",
        "description": "Negative news, litigation, investigations, controversies",
        "category": "compliance_red_flag",
        "threshold": 0.50,
        "example_phrases": [
            "subject of ongoing criminal investigation",
            "named defendant in class action lawsuit",
            "implicated in financial scandal",
            "facing allegations of misconduct",
            "controversy surrounding business practices",
            "whistleblower allegations against management",
            "under investigation by law enforcement authorities",
            "negative media coverage regarding ethics violations",
            # From mined methodology patterns
            "investigative journalism exposing wrongdoing",
            "leaked documents revealing hidden practices",
            "consumer complaints on review platforms",
            "social media backlash and viral criticism",
            "NGO report documenting abuses",
            "former employee speaking to media",
            "regulatory warning letter made public",
            "industry blacklisting or debarment",
        ]
    },

    # =========================================================================
    # FINANCIAL INFORMATION
    # =========================================================================
    {
        "id": "financial_statements",
        "name": "Financial Statements",
        "description": "Balance sheets, income statements, annual reports, audited accounts",
        "category": "financial",
        "threshold": 0.50,
        "example_phrases": [
            "audited financial statements for the fiscal year",
            "consolidated balance sheet showing assets and liabilities",
            "income statement reflecting revenue and expenses",
            "cash flow statement for operating activities",
            "annual report filed with securities regulator",
            "notes to the financial statements",
            "independent auditor's report on financial position",
            "quarterly earnings release and financial results",
            # From mined methodology patterns
            "qualified audit opinion raising concerns",
            "going concern warning in auditor report",
            "restatement of prior period financials",
            "off-balance sheet liabilities disclosure",
            "segment reporting by business unit",
            "related party transaction footnote disclosure",
            "contingent liability and legal reserve",
            "goodwill impairment testing results",
        ]
    },
    {
        "id": "valuation_metrics",
        "name": "Valuation & Metrics",
        "description": "Company valuations, financial ratios, enterprise value",
        "category": "financial",
        "threshold": 0.50,
        "example_phrases": [
            "enterprise value calculated at market capitalization plus debt",
            "valuation multiple based on EBITDA",
            "price to earnings ratio compared to industry peers",
            "discounted cash flow analysis of future earnings",
            "asset-based valuation of tangible and intangible assets",
            "fairness opinion from independent financial advisor",
            "comparable company analysis for valuation purposes",
            "implied equity value from transaction terms",
            # From mined methodology patterns
            "sum of the parts valuation for conglomerate",
            "liquidation value floor for distressed asset",
            "control premium in acquisition context",
            "minority discount for non-controlling stake",
            "leveraged buyout model and returns analysis",
            "NAV discount for holding company",
            "revenue multiple for high-growth company",
            "replacement cost method for asset valuation",
        ]
    },

    # =========================================================================
    # LEGAL & CONTRACTUAL
    # =========================================================================
    {
        "id": "legal_proceedings",
        "name": "Legal Proceedings",
        "description": "Lawsuits, litigation, court cases, legal disputes",
        "category": "legal",
        "threshold": 0.50,
        "example_phrases": [
            "plaintiff filed lawsuit in district court",
            "defendant contested allegations in legal proceedings",
            "court ruled in favor of the complainant",
            "settlement reached in commercial dispute",
            "judgment entered against the respondent",
            "arbitration proceedings commenced under ICC rules",
            "injunctive relief sought by the petitioner",
            "appeal pending before higher court",
            # From mined methodology patterns
            "ICSID arbitration for investment treaty claim",
            "discovery dispute over document production",
            "class certification denied by court",
            "summary judgment motion pending",
            "preliminary injunction granted",
            "multidistrict litigation consolidated",
            "expert witness testimony on damages",
            "enforcement of foreign judgment",
        ]
    },
    {
        "id": "contracts_agreements",
        "name": "Contracts & Agreements",
        "description": "Material contracts, joint ventures, partnerships, M&A",
        "category": "legal",
        "threshold": 0.50,
        "example_phrases": [
            "parties entered into definitive merger agreement",
            "joint venture agreement establishing partnership",
            "material contract for supply of goods and services",
            "acquisition of target company for enterprise value",
            "share purchase agreement with customary representations",
            "licensing agreement for intellectual property rights",
            "term sheet outlining principal transaction terms",
            "binding agreement subject to regulatory approval",
            # From mined methodology patterns
            "MAC clause invoked to terminate deal",
            "earnout dispute over milestone achievement",
            "indemnification claim for breach of warranty",
            "escrow release following holdback period",
            "non-compete covenant restricting competition",
            "change of control provision triggered",
            "assignment and novation of contract rights",
            "force majeure clause activated by event",
        ]
    },

    # =========================================================================
    # REPUTATION & PUBLIC PERCEPTION
    # =========================================================================
    {
        "id": "reputation_damage",
        "name": "Reputation Damage",
        "description": "Scandals, controversies, reputational harm, public criticism",
        "category": "reputation",
        "threshold": 0.50,
        "example_phrases": [
            "major scandal damaged the company's reputation",
            "reputational crisis following public revelations",
            "brand value suffered significant damage",
            "public backlash against controversial business practices",
            "loss of consumer trust after product safety issues",
            "corporate scandal led to executive resignations",
            "reputation tarnished by association with misconduct",
            "widespread criticism from industry watchdogs",
            # From mined methodology patterns
            "celebrity endorsement withdrawn after controversy",
            "boycott campaign affecting sales",
            "shareholder activism targeting board",
            "proxy fight for corporate control",
            "reputation consultants engaged for crisis",
            "brand rehabilitation campaign launched",
            "apology statement issued by leadership",
            "stakeholder trust severely eroded",
        ]
    },
    {
        "id": "negative_publicity",
        "name": "Negative Publicity",
        "description": "Bad press, critical media coverage, public criticism",
        "category": "reputation",
        "threshold": 0.50,
        "example_phrases": [
            "negative media coverage dominated headlines",
            "scathing investigative journalism exposed problems",
            "critical press reports questioned management integrity",
            "unfavorable publicity surrounding business dealings",
            "media scrutiny intensified after disclosures",
            "journalists uncovered questionable practices",
            "viral social media criticism spread rapidly",
            "damaging leaks to the press harmed public image",
            # From mined methodology patterns
            "documentary film exposing company practices",
            "podcast investigation attracting attention",
            "Twitter storm trending against company",
            "Reddit thread compiling complaints",
            "Glassdoor reviews revealing culture problems",
            "influencer criticism reaching millions",
            "negative TrustPilot reviews accumulating",
            "news aggregators amplifying critical coverage",
        ]
    },
    {
        "id": "esg_concerns",
        "name": "ESG Concerns",
        "description": "Environmental, Social, and Governance issues, sustainability failures",
        "category": "reputation",
        "threshold": 0.50,
        "example_phrases": [
            "environmental violations and pollution incidents",
            "poor labor practices and worker exploitation",
            "corporate governance failures and board dysfunction",
            "lack of diversity in senior leadership",
            "human rights concerns in supply chain",
            "failure to meet sustainability commitments",
            "greenwashing accusations regarding climate claims",
            "shareholder activism over ESG performance",
            # From mined methodology patterns
            "carbon footprint disclosure requirements",
            "scope 3 emissions reporting gaps",
            "water usage and scarcity impact",
            "biodiversity loss from operations",
            "modern slavery statement deficiencies",
            "gender pay gap reporting concerns",
            "executive compensation controversy",
            "board independence and conflicts",
        ]
    },
    {
        "id": "customer_complaints",
        "name": "Customer Complaints",
        "description": "Consumer complaints, product issues, service failures",
        "category": "reputation",
        "threshold": 0.50,
        "example_phrases": [
            "numerous customer complaints filed with regulators",
            "consumer protection agency received multiple grievances",
            "widespread dissatisfaction with product quality",
            "class action by consumers alleging deceptive practices",
            "Better Business Bureau complaints and poor ratings",
            "product recalls due to safety defects",
            "refund demands and consumer lawsuits",
            "pattern of unresolved customer disputes",
            # From mined methodology patterns
            "CFPB complaint database entries",
            "FTC investigation into consumer practices",
            "state attorney general consumer action",
            "ombudsman findings against company",
            "chargebacks and payment disputes spike",
            "warranty claim denial patterns",
            "subscription trap and dark patterns",
            "misleading advertising complaints",
        ]
    },

    # =========================================================================
    # REGULATORY & COMPLIANCE (Enhanced)
    # =========================================================================
    {
        "id": "regulatory_enforcement",
        "name": "Regulatory Enforcement",
        "description": "Enforcement actions, penalties, sanctions by regulators",
        "category": "regulatory",
        "threshold": 0.52,
        "example_phrases": [
            "regulator imposed substantial monetary penalty",
            "enforcement action resulted in record fine",
            "regulatory investigation concluded with sanctions",
            "agency issued formal enforcement order",
            "penalty for non-compliance with regulations",
            "administrative proceedings by securities commission",
            "disgorgement of ill-gotten gains ordered",
            "civil money penalty assessed by banking regulator",
            # From mined methodology patterns
            "NPA non-prosecution agreement with conditions",
            "corporate integrity agreement imposed",
            "remediation deadline set by regulator",
            "independent consultant appointed for compliance",
            "enhanced monitoring period required",
            "restrictions on business expansion",
            "increased capital requirements imposed",
            "senior management barred from industry",
        ]
    },
    {
        "id": "license_issues",
        "name": "License Issues",
        "description": "License revocations, suspensions, denials, operating restrictions",
        "category": "regulatory",
        "threshold": 0.52,
        "example_phrases": [
            "operating license revoked by authorities",
            "business license suspended pending investigation",
            "application for license renewal denied",
            "conditional license with remediation requirements",
            "permit cancelled for regulatory violations",
            "authorization withdrawn by supervisory body",
            "restricted from conducting certain business activities",
            "probationary status imposed on license",
            # From mined methodology patterns
            "fit and proper test failed for director",
            "passport rights revoked by home regulator",
            "temporary registration pending full authorization",
            "grandfathered license not renewed",
            "multiple jurisdictions revoking permissions",
            "operating without required license",
            "regulatory perimeter breach identified",
            "license condition violated triggering review",
        ]
    },
    {
        "id": "compliance_failures",
        "name": "Compliance Failures",
        "description": "Ongoing compliance issues, audit findings, control weaknesses",
        "category": "regulatory",
        "threshold": 0.50,
        "example_phrases": [
            "significant deficiencies in compliance program",
            "internal audit identified control weaknesses",
            "failure to implement adequate AML procedures",
            "compliance gaps exposed by regulatory examination",
            "lack of effective internal controls",
            "remediation required for compliance shortcomings",
            "systemic failures in risk management",
            "inadequate policies and procedures for regulatory requirements",
            # From mined methodology patterns
            "three lines of defense model breakdown",
            "first line risk ownership failure",
            "compliance culture deficiencies",
            "training program inadequate for staff",
            "suspicious activity monitoring gaps",
            "customer due diligence failures",
            "record retention policy violations",
            "conflicts of interest not managed",
        ]
    },
    {
        "id": "government_investigations",
        "name": "Government Investigations",
        "description": "Federal/state investigations, subpoenas, grand jury proceedings",
        "category": "regulatory",
        "threshold": 0.55,
        "example_phrases": [
            "subject of federal grand jury investigation",
            "Department of Justice opened criminal inquiry",
            "subpoena received from prosecutors",
            "SEC formal investigation initiated",
            "congressional inquiry into business practices",
            "state attorney general launched investigation",
            "FBI probe into alleged misconduct",
            "target of multi-agency regulatory investigation",
            # From mined methodology patterns
            "IRS criminal investigation division involvement",
            "HSI homeland security investigation",
            "FinCEN geographic targeting order",
            "CFTC investigation into market manipulation",
            "OCC enforcement against national bank",
            "CFIUS review blocking transaction",
            "Commerce Department BIS investigation",
            "Treasury OFAC investigation and designation",
        ]
    },

    # =========================================================================
    # INDUSTRY / SECTOR CONCEPTS
    # =========================================================================
    {
        "id": "energy_trading",
        "name": "Energy & Trading",
        "description": "Energy sector, oil/gas trading, utilities, commodities",
        "category": "industry",
        "threshold": 0.50,
        "example_phrases": [
            "energy trading company operating across European markets",
            "natural gas and electricity wholesale trading",
            "oil and gas exploration and production activities",
            "utility company providing electricity distribution",
            "commodity trading desk specializing in energy derivatives",
            "LNG terminal operations and storage facilities",
            "power plant generation capacity and output",
            "renewable energy project development and financing",
            # From mined sector red flags
            "complex multi-jurisdictional ownership structures in energy sector",
            "EU unbundling created opportunities for politically connected entities",
            "complex ownership structures obscuring true beneficiaries",
            "rapid rise of individuals without apparent capital sources",
            "joint ventures with state-controlled entities",
            "under-pricing of state assets in energy privatization",
            "Continental Wind scandal involving grid access bribes",
            "storage and transportation networks with opaque ownership",
        ]
    },
    {
        "id": "banking_finance",
        "name": "Banking & Finance",
        "description": "Banks, investment firms, financial services, asset management",
        "category": "industry",
        "threshold": 0.50,
        "example_phrases": [
            "commercial bank providing retail and corporate banking services",
            "investment bank specializing in M&A advisory",
            "private equity fund managing institutional capital",
            "hedge fund employing quantitative trading strategies",
            "asset management company with AUM of several billion",
            "venture capital firm investing in early-stage startups",
            "insurance company underwriting commercial risks",
            "payment processing and fintech services provider",
            # From mined sector red flags
            "facilitating investments for Russian oligarchs",
            "high NPL ratios especially above 30 percent",
            "ownership transfers before IPO",
            "political family connections in banking sector",
            "previous criminal proceedings affecting licensing",
            "Swiss franc loan scandal and regulatory compliance issues",
            "senior management instability in financial institution",
            "alumni networks from elite institutions facilitating deals",
        ]
    },
    {
        "id": "real_estate_property",
        "name": "Real Estate & Property",
        "description": "Property development, real estate investment, land holdings",
        "category": "industry",
        "threshold": 0.50,
        "example_phrases": [
            "real estate developer constructing residential towers",
            "commercial property portfolio across prime locations",
            "property investment vehicle holding rental assets",
            "luxury residential development in prestigious area",
            "shopping center and retail park owner operator",
            "industrial warehouse and logistics property fund",
            "hotel and hospitality property management company",
            "land bank for future development opportunities",
            # From mined sector patterns
            "offshore vehicle holding London super-prime property",
            "unexplained wealth orders targeting real estate",
            "beneficial owner hidden behind nominee structure",
            "property purchased through SLP or LP structure",
            "real estate as money laundering vehicle",
            "golden visa investment in property development",
            "REIT structure for tax-efficient property holding",
            "land registry opacity and offshore ownership",
        ]
    },
    {
        "id": "construction_infrastructure",
        "name": "Construction & Infrastructure",
        "description": "Construction, engineering, infrastructure projects",
        "category": "industry",
        "threshold": 0.50,
        "example_phrases": [
            "construction company specializing in large infrastructure projects",
            "civil engineering contractor for roads and bridges",
            "building contractor for commercial developments",
            "infrastructure project financing and development",
            "public works contractor with government contracts",
            "engineering consulting firm for major projects",
            "general contractor for industrial facilities",
            "public procurement contract for construction works",
            # From mined sector red flags
            "infrastructure concession with government guarantee",
            "PPP public-private partnership for toll roads",
            "EPC contractor for turnkey project delivery",
            "cost overruns and delayed completion on major project",
            "construction permits and environmental approvals",
            "subcontractor network with labor compliance issues",
            "mega-project with sovereign guarantee financing",
            "infrastructure development in high-corruption jurisdiction",
        ]
    },
    {
        "id": "technology_software",
        "name": "Technology & Software",
        "description": "Tech companies, software, IT services, digital platforms",
        "category": "industry",
        "threshold": 0.50,
        "example_phrases": [
            "software company developing enterprise solutions",
            "technology startup disrupting traditional industry",
            "IT services provider offering managed solutions",
            "cloud computing and SaaS platform provider",
            "cybersecurity company protecting digital assets",
            "artificial intelligence and machine learning startup",
            "e-commerce platform enabling online transactions",
            "digital transformation consulting services",
            # From mined sector patterns
            "fintech company processing digital payments",
            "cryptocurrency exchange and blockchain services",
            "data analytics and business intelligence provider",
            "platform economy with gig worker model",
            "surveillance technology and facial recognition",
            "dual-use technology with export control implications",
            "venture-backed startup with rapid scaling",
            "tech unicorn with pre-IPO valuation concerns",
        ]
    },
    {
        "id": "shipping_maritime",
        "name": "Shipping & Maritime",
        "description": "Shipping, maritime transport, vessel ownership",
        "category": "industry",
        "threshold": 0.52,
        "example_phrases": [
            "shipping company operating bulk carrier fleet",
            "container vessel owner with global routes",
            "tanker shipping for crude oil and petroleum products",
            "maritime transport services across international waters",
            "ship management company handling vessel operations",
            "port terminal operator and logistics services",
            "vessel registered in Marshall Islands flag state",
            "dry bulk shipping with Panamax and Capesize vessels",
            # From mined sector red flags
            "flag of convenience registration in Liberia or Panama",
            "shadow fleet tanker evading oil sanctions",
            "ship-to-ship transfer for cargo obfuscation",
            "beneficial owner hidden behind shell company",
            "maritime fraud and cargo theft incidents",
            "crew exploitation and labor standard violations",
            "dark fleet operating with AIS disabled",
            "vessel age and class certification concerns",
        ]
    },
    {
        "id": "aviation_aerospace",
        "name": "Aviation & Aerospace",
        "description": "Airlines, aircraft, aerospace, aviation services",
        "category": "industry",
        "threshold": 0.52,
        "example_phrases": [
            "private jet aircraft registered to offshore company",
            "airline operator with commercial passenger routes",
            "aviation charter services for executive travel",
            "aircraft leasing company with fleet portfolio",
            "aerospace manufacturer supplying components",
            "business aviation management and operations",
            "helicopter charter and medical evacuation services",
            "aircraft registered in Isle of Man or Cayman Islands",
            # From mined sector patterns
            "fractional jet ownership through management company",
            "aircraft beneficial ownership through trust structure",
            "aviation sanctions circumvention and re-registration",
            "AOC holder with operating base in tax haven",
            "aircraft parts and maintenance supply chain",
            "airport ground handling and FBO services",
            "cargo airline with suspicious freight patterns",
            "aviation finance and leasing from Ireland",
        ]
    },
    {
        "id": "healthcare_pharma",
        "name": "Healthcare & Pharma",
        "description": "Healthcare, pharmaceuticals, medical devices, biotech",
        "category": "industry",
        "threshold": 0.50,
        "example_phrases": [
            "pharmaceutical company developing novel therapeutics",
            "healthcare provider operating hospital network",
            "biotechnology firm researching gene therapies",
            "medical device manufacturer with FDA approvals",
            "clinical trial services and contract research",
            "generic drug manufacturer and distributor",
            "healthcare technology and digital health solutions",
            "pharmacy chain and retail health services",
            # From mined sector patterns
            "opioid manufacturer facing litigation claims",
            "healthcare fraud and billing irregularities",
            "pharmaceutical pricing and patent abuse concerns",
            "medical device recall and product liability",
            "clinical data manipulation or trial fraud",
            "controlled substance distribution violations",
            "pharmacy benefit manager kickback allegations",
            "telemedicine provider with prescribing concerns",
        ]
    },
    {
        "id": "mining_extractives",
        "name": "Mining & Extractives",
        "description": "Mining, minerals, extractive industries, resources",
        "category": "industry",
        "threshold": 0.52,
        "example_phrases": [
            "mining company extracting precious metals",
            "iron ore and mineral extraction operations",
            "gold and silver mining with refining facilities",
            "coal mining operations in developing countries",
            "rare earth elements extraction and processing",
            "diamond mining and gemstone production",
            "mineral exploration licenses and concessions",
            "extractive industry with environmental concerns",
            # From mined sector red flags
            "conflict minerals sourcing from DRC region",
            "artisanal mining with child labor concerns",
            "mining concession in corrupt jurisdiction",
            "tailings dam and environmental disaster risk",
            "resource curse and governance failures",
            "blood diamonds and Kimberley Process violations",
            "illegal mining and smuggling operations",
            "community displacement and land rights disputes",
        ]
    },
    {
        "id": "defense_military",
        "name": "Defense & Military",
        "description": "Defense contractors, military equipment, security services",
        "category": "industry",
        "threshold": 0.55,
        "example_phrases": [
            "defense contractor supplying military equipment",
            "arms manufacturer exporting weapons systems",
            "private military contractor and security services",
            "dual-use technology with military applications",
            "aerospace defense systems integration",
            "military vehicle and armor production",
            "intelligence services and surveillance technology",
            "end-user certificate for defense exports",
            # From mined sector red flags
            "arms embargo circumvention through intermediaries",
            "Wagner Group or private military involvement",
            "defense procurement corruption and bribery",
            "weapons diversion to conflict zones",
            "export control violations for defense articles",
            "sanctioned defense entities and blacklisted companies",
            "state-owned defense enterprise linked to regime",
            "mercenary services and human rights violations",
        ]
    },

    # =========================================================================
    # CORPORATE STRUCTURE PATTERNS
    # =========================================================================
    {
        "id": "holding_company",
        "name": "Holding Company Structure",
        "description": "Holding companies, investment vehicles, parent entities",
        "category": "structure",
        "threshold": 0.50,
        "example_phrases": [
            "holding company established to own subsidiaries",
            "parent company controlling multiple operating entities",
            "investment holding vehicle for portfolio companies",
            "Netherlands BV as intermediate holding company",
            "Luxembourg holding company for European operations",
            "group structure with ultimate parent at top",
            "Irish holding company for IP and licensing",
            "Delaware holding company for US investments",
            # From mined sector structures
            "intermediate holding company in tax-efficient jurisdiction",
            "Cyprus holding company for Eastern European investments",
            "ultimate beneficial owner through chain of holdings",
            "management company providing group services",
            "Swiss AG as regional holding platform",
            "Singapore holding for Asian portfolio companies",
            "holding structure with profit participation loans",
            "Dutch cooperative as holding vehicle",
        ]
    },
    {
        "id": "nominee_arrangement",
        "name": "Nominee Arrangements",
        "description": "Nominee directors, nominee shareholders, proxy holders",
        "category": "structure",
        "threshold": 0.55,
        "example_phrases": [
            "nominee director acting on behalf of beneficial owner",
            "nominee shareholder holding shares in trust",
            "professional director providing corporate services",
            "corporate services provider as registered agent",
            "power of attorney granted to nominee",
            "bearer shares with nominee holder",
            "professional trustee as legal owner",
            "nominee arrangement obscuring true ownership",
            # From mined sector structures
            "formation agent listed as initial director",
            "shelf company purchased with nominee directors",
            "fiduciary services firm providing nominee shareholders",
            "resident director requirement fulfilled by service provider",
            "corporate secretary and registered office services",
            "professional directorship with multiple appointments",
            "letter of wishes to nominee trustee",
            "undisclosed principal behind nominee structure",
        ]
    },
    {
        "id": "special_purpose_vehicle",
        "name": "Special Purpose Vehicle",
        "description": "SPVs, project companies, ring-fenced entities",
        "category": "structure",
        "threshold": 0.52,
        "example_phrases": [
            "special purpose vehicle established for the transaction",
            "SPV created to hold specific assets",
            "project finance vehicle for infrastructure investment",
            "ring-fenced entity isolating project risks",
            "orphan structure with charitable trust ownership",
            "securitization vehicle for asset-backed securities",
            "acquisition vehicle for leveraged buyout",
            "bankruptcy-remote SPV structure",
            # From mined sector structures
            "single asset SPV for real estate holding",
            "conduit entity for financing arrangement",
            "debt issuance vehicle for bond offering",
            "structured finance vehicle for CLO",
            "project company for infrastructure concession",
            "PropCo OpCo separation structure",
            "tax-efficient vehicle for cross-border investment",
            "escrow SPV for acquisition completion",
        ]
    },
    {
        "id": "joint_venture",
        "name": "Joint Venture",
        "description": "JVs, partnerships, consortium arrangements",
        "category": "structure",
        "threshold": 0.50,
        "example_phrases": [
            "joint venture established between partners",
            "consortium agreement for major project",
            "strategic partnership combining expertise",
            "50-50 joint venture with equal ownership",
            "minority joint venture stake in local operation",
            "partnership agreement governing profit sharing",
            "cooperation agreement for market entry",
            "alliance structure for technology development",
            # From mined sector structures
            "incorporated joint venture with shared governance",
            "unincorporated JV governed by cooperation agreement",
            "production sharing agreement with state company",
            "joint development agreement for technology IP",
            "franchise arrangement with local partner",
            "distribution joint venture for market access",
            "manufacturing JV with technology transfer",
            "equity swap arrangement between partners",
        ]
    },
    {
        "id": "trust_foundation",
        "name": "Trust & Foundation",
        "description": "Trusts, foundations, family offices",
        "category": "structure",
        "threshold": 0.52,
        "example_phrases": [
            "family trust holding inherited wealth",
            "private foundation for charitable purposes",
            "discretionary trust with beneficiary rights",
            "offshore trust in Jersey or Guernsey",
            "Liechtenstein stiftung foundation structure",
            "family office managing multi-generational wealth",
            "irrevocable trust with professional trustee",
            "purpose trust for asset protection",
            # From mined sector structures
            "Dutch STAK foundation for share administration",
            "Panamanian private interest foundation",
            "protector appointed to oversee trustee",
            "reserved powers retained by settlor",
            "dynasty trust spanning multiple generations",
            "STAR trust in Cayman Islands",
            "charitable remainder trust for tax planning",
            "blind trust for conflict of interest mitigation",
        ]
    },

    # =========================================================================
    # METHODOLOGY & RESEARCH SOURCES
    # =========================================================================
    {
        "id": "corporate_registry_source",
        "name": "Corporate Registry",
        "description": "Official company registry filings and records",
        "category": "methodology",
        "threshold": 0.50,
        "example_phrases": [
            "according to corporate registry filings",
            "company house records confirm the directors",
            "registered office address per official registry",
            "annual accounts filed with companies house",
            "extract from commercial register shows ownership",
            "certificate of incorporation and memorandum",
            "official registry confirms company status as active",
            "registered agent address in incorporation documents",
            # From mined methodology patterns
            "used Swiss corporate registries to trace ownership through entities",
            "tracked ownership changes through Hungarian regulatory authority approvals",
            "traced Cyprus-incorporated entities and their directors",
            "searched California corporate registry for LLC filing and officers",
            "searched Delaware corporate registry for company registration details",
            "accessed corporate filings and financial data for revenue analysis",
            "from the Luxembourg Register of Commerce and Societies",
            "searched Brazilian trade registry for company registration and ownership structure",
            # From mined arbitrage patterns (cross-jurisdictional intelligence)
            "information about Cyprus entity obtained from Hungarian energy regulator MEKH",
            "Hungarian regulatory filings disclosed Swiss holding company details",
            "Luxembourg company filings required disclosure of beneficial owner identity documents",
            "German BaFin regulatory filings revealed connections to Jersey entities",
            "UK Companies House reveals ultimate controllers of complex holding structures",
            "foreign filing in Luxembourg disclosed passport details and residential addresses",
            "regulatory overlap enables tracking ownership across jurisdictions",
            "parent company disclosure requirements provide transparency into holding structures",
        ]
    },
    {
        "id": "court_litigation_source",
        "name": "Court & Litigation",
        "description": "Court records, legal filings, judgment database",
        "category": "methodology",
        "threshold": 0.52,
        "example_phrases": [
            "court records reveal ongoing litigation",
            "judgment entered in commercial dispute",
            "legal proceedings filed in district court",
            "docket search shows pending cases",
            "bankruptcy filing and creditor claims",
            "arbitration award published in database",
            "injunction granted by presiding judge",
            "settlement agreement ending litigation",
            # From mined methodology patterns
            "identified legal actions where company was plaintiff in loan default cases",
            "search of publicly available litigation records",
            "court records research for tax tribunal decisions and high court rulings",
            "searched Constitutional Court and Supreme Court records for litigation",
            "Wikileaks cable referenced containing information about director",
            "used European Commission documents for ownership verification",
            "Polish bankruptcy and litigation records searched",
            "found driving conviction record in news archives",
        ]
    },
    {
        "id": "media_coverage",
        "name": "Media Coverage",
        "description": "News articles, press coverage, investigative journalism",
        "category": "methodology",
        "threshold": 0.62,
        "example_phrases": [
            "according to media reports published in",
            "news coverage indicates controversy",
            "investigative journalism revealed allegations",
            "press release announced the transaction",
            "newspaper article reported on the matter",
            "media monitoring identified negative coverage",
            "interview with company spokesperson stated",
            "leaked documents published by journalists",
            # From mined methodology patterns
            "internet archive searches for website historical data",
            "used media reports to identify yacht ownership and usage patterns",
            "extensive media searches in Armenian Russian and English for adverse information",
            "French-language media research through press and social media searches",
            "referenced Financial Times reporting on bribery allegations",
            "comprehensive media coverage analysis including local outlets and major publications",
            "analysis of Hungarian media outlets reporting on ownership and political connections",
            "analyzed interviews with company executives and media reports for ownership details",
        ]
    },
    {
        "id": "social_media_osint",
        "name": "Social Media OSINT",
        "description": "Social media profiles, LinkedIn, digital footprint",
        "category": "methodology",
        "threshold": 0.50,
        "example_phrases": [
            "LinkedIn profile shows employment history",
            "social media presence indicates lifestyle",
            "Facebook account reveals connections",
            "Twitter posts provide public statements",
            "Instagram photos show luxury assets",
            "digital footprint across platforms",
            "professional network connections on LinkedIn",
            "online profile confirms biographical details",
            # From mined methodology patterns
            "social media profile verification attempts",
            "analyzed wiretapping recordings that emerged publicly",
            "searched social media platforms for company presence and business information",
            "dark web data breach analysis for email addresses and passwords",
            "used LinkedIn profile of company owner for business information",
            "extensive social media monitoring across Facebook Twitter and LinkedIn",
            "open source research on Forbes rankings and public procurement records",
            "reviewed Instagram profile for travel information and LinkedIn for employment",
        ]
    },
    {
        "id": "regulatory_filing_source",
        "name": "Regulatory Filings",
        "description": "SEC filings, regulatory disclosures, official notices",
        "category": "methodology",
        "threshold": 0.50,
        "example_phrases": [
            "SEC filing discloses material information",
            "regulatory notice published by authority",
            "prospectus filed for securities offering",
            "annual report submitted to regulator",
            "beneficial ownership filing Form 13F",
            "proxy statement reveals executive compensation",
            "disclosure requirement under securities law",
            "regulatory filing confirms transaction details",
            # From mined arbitrage patterns (regulatory disclosure arbitrage)
            "energy regulator requires disclosure of ownership changes for regulated entities",
            "financial regulator required disclosure of related entities for acquisition approval",
            "Hungarian MEKH regulatory filing revealed Cyprus and Swiss ownership structure",
            "German BaFin acquisition filing disclosed Jersey holding company connections",
            "regulatory overlap between jurisdictions enables information gathering",
            "sector-specific regulator disclosure requirements exceed corporate registry",
            "FCA regulatory filings provide enhanced transparency for financial entities",
            "central bank approval process requires disclosure of ultimate beneficial owners",
        ]
    },

    # =========================================================================
    # EVENTS & TEMPORAL MARKERS
    # =========================================================================
    {
        "id": "acquisition_merger",
        "name": "Acquisition & Merger",
        "description": "M&A transactions, takeovers, business combinations",
        "category": "events",
        "threshold": 0.50,
        "example_phrases": [
            "acquisition of target company for enterprise value",
            "merger agreement signed between parties",
            "takeover bid launched for public company",
            "strategic acquisition to expand market presence",
            "private equity buyout of family business",
            "cross-border merger requiring regulatory approval",
            "hostile takeover attempt resisted by board",
            "acquisition completed following due diligence",
            # From mined events patterns
            "asset purchase agreement for business carve-out",
            "squeeze-out of minority shareholders post-acquisition",
            "earnout provisions tied to future performance",
            "break-up fee in failed acquisition attempt",
            "SPAC merger as alternative to traditional IPO",
            "transformative acquisition changing company direction",
            "bolt-on acquisition to consolidate market position",
            "management participation in buyout transaction",
        ]
    },
    {
        "id": "bankruptcy_insolvency",
        "name": "Bankruptcy & Insolvency",
        "description": "Bankruptcy, liquidation, insolvency proceedings",
        "category": "events",
        "threshold": 0.55,
        "example_phrases": [
            "company filed for bankruptcy protection",
            "liquidator appointed to wind up affairs",
            "insolvency proceedings commenced by creditors",
            "administration entered due to financial difficulties",
            "creditors meeting to approve restructuring plan",
            "distressed company seeking turnaround",
            "Chapter 11 reorganization in United States",
            "compulsory winding up order by court",
            # From mined events patterns
            "pre-pack administration sale of business",
            "trading while insolvent concerns",
            "phoenixing to shed liabilities and restart",
            "preferential payment to connected creditors",
            "fraudulent conveyance of assets pre-bankruptcy",
            "directors disqualification for misconduct",
            "creditors left with significant shortfall",
            "insolvency practitioner appointed to realize assets",
        ]
    },
    {
        "id": "ipo_listing",
        "name": "IPO & Listing",
        "description": "Initial public offerings, stock listings, going public",
        "category": "events",
        "threshold": 0.52,
        "example_phrases": [
            "initial public offering on stock exchange",
            "company listed on NYSE or NASDAQ",
            "dual listing on multiple exchanges",
            "secondary offering to raise additional capital",
            "delisting from public markets",
            "prospectus filed for share offering",
            "underwriter managing the IPO process",
            "market capitalization at time of listing",
            # From mined events patterns
            "reverse takeover as backdoor listing",
            "direct listing without underwriter support",
            "share price performance post-IPO",
            "lock-up expiry and insider selling",
            "IPO valuation concerns and overpricing",
            "going private transaction by management",
            "AIM or junior market listing for growth company",
            "cross-listing on foreign exchange for visibility",
        ]
    },
    {
        "id": "restructuring",
        "name": "Restructuring",
        "description": "Corporate restructuring, reorganization, spin-offs",
        "category": "events",
        "threshold": 0.50,
        "example_phrases": [
            "corporate restructuring to streamline operations",
            "spin-off of division into separate company",
            "demerger creating two independent entities",
            "group reorganization for tax efficiency",
            "management buyout of operating unit",
            "carve-out transaction separating business",
            "internal reorganization of group structure",
            "hive-down of assets to new subsidiary",
            # From mined events patterns
            "debt restructuring and covenant renegotiation",
            "operational turnaround under new management",
            "headcount reduction and cost cutting program",
            "asset disposal to deleverage balance sheet",
            "rights issue to shore up capital base",
            "migration of domicile to new jurisdiction",
            "change of accounting policy or restatement",
            "business model pivot and strategic reset",
        ]
    },
    {
        "id": "management_change",
        "name": "Management Change",
        "description": "Executive appointments, resignations, board changes",
        "category": "events",
        "threshold": 0.50,
        "example_phrases": [
            "new CEO appointed to lead company",
            "resignation of chief executive officer",
            "board member stepped down from position",
            "executive team restructuring announced",
            "chairman transition to new leadership",
            "management shakeup following poor results",
            "director appointed to fill vacancy",
            "key person departure creating uncertainty",
            # From mined events patterns
            "founder forced out by investors",
            "succession planning for family business",
            "turnaround CEO brought in from outside",
            "activist investor demanding board seats",
            "executive terminated for cause following investigation",
            "interim management pending permanent appointment",
            "key employee non-compete and gardening leave",
            "C-suite exodus raising governance concerns",
        ]
    },
    {
        "id": "investigation_probe",
        "name": "Investigation & Probe",
        "description": "Investigations, probes, inquiries, audits",
        "category": "events",
        "threshold": 0.52,
        "example_phrases": [
            "investigation launched by authorities",
            "regulatory probe into business practices",
            "internal investigation by special committee",
            "forensic audit to examine transactions",
            "inquiry by parliamentary committee",
            "whistleblower complaint triggered investigation",
            "dawn raid by enforcement officers",
            "subpoena issued for documents and testimony",
            # From mined events patterns
            "DOJ deferred prosecution agreement reached",
            "SFO Serious Fraud Office investigation ongoing",
            "SEC enforcement action for securities violations",
            "grand jury investigation and criminal charges",
            "compliance monitor appointed for oversight",
            "congressional inquiry and subpoena for records",
            "FCA investigation into market conduct",
            "multi-jurisdictional investigation coordinated by authorities",
        ]
    },

    # =========================================================================
    # GEOGRAPHIC / JURISDICTION RISK
    # =========================================================================
    {
        "id": "russia_cis_connection",
        "name": "Russia/CIS Connection",
        "description": "Connections to Russia, CIS countries, former Soviet states",
        "category": "geographic_risk",
        "threshold": 0.55,
        "example_phrases": [
            # Core Russia/CIS identifiers
            "Russian oligarch with significant business interests",
            "company registered in Moscow or St Petersburg",
            "connections to individuals close to Kremlin",
            "operations in former Soviet republics",
            "Kazakhstan or Uzbekistan business activities",
            "Ukrainian company with Russian ownership",
            "Belarus-based entity under sanctions",
            "oligarch structure with Russian beneficiaries",
            # From embedded books corpus (Kleptopia, Londongrad, Putin's Kleptocracy)
            "kleptocratic tribute system underlying Russia's authoritarian regime",
            "political leaders close to Putin have become multimillionaires",
            "oligarchs around them have become billionaires according to Forbes Russia",
            "deny kleptocrats access to our financial system",
            "FSB MVD and militia all have distinct money collection systems",
            "product and producer of this pervasive system of corruption",
            "KGB veterans who knew the details of these accounts",
            "commercial banks born from oligarch structures in 1990s",
            "Russia's oil barons and metal magnates",
            "oligarch firms versus non-oligarch private domestic firms",
            "London's oligarch belts in Kensington",
            "Russian organized crime responds to pressure from authorities",
            "corruption of high-level ministers and officials",
            "offshore accounts under strict control of the KGB",
            "siloviki network controlling state enterprises",
            "energy dependency politics and corruption in former Soviet Union",
            "domestic oligarchs and Russian pressure on Ukraine Belarus Lithuania",
            "fallen oligarch with Astana connections",
            "near abroad contest over Ukraine and the Caucasus",
            "Petrostate Putin power and the new Russia",
            "Yukos affair and struggle for Russia's resources",
            "operative in the Kremlin with KGB background",
            # From mined jurisdictions (Russia/CIS 77 country profiles)
            "Russian banking sector subject to multiple regulatory frameworks and sanctions regimes",
            "Ukrainian corporate transparency improving but still requires local source networks",
            "government connections require HUMINT sources in Ukraine",
            "Kazakhstan media dominated by state-owned and pro-government outlets with mass surveillance",
            "Azerbaijan telecommunications sector requires government licensing and regulatory oversight",
            "Armenian banking sector subject to specific regulatory oversight",
            "Georgian banking sector subject to regulatory oversight",
            "Moldova specific regulations for financial institutions requiring enhanced due diligence",
            "Kyrgyzstan banking sector underwent significant regulatory changes",
            "beneficial ownership beyond immediate shareholders unavailable in Kazakhstan",
            "Estonian strong beneficial ownership transparency enables cross-border corporate intelligence",
            "PJSC Public Joint Stock Company Russian corporate structure",
            "CJSC Closed Joint Stock Company Armenian and CIS corporate form",
            "Danske Bank Estonia branch involved in major money laundering scandal",
        ]
    },
    {
        "id": "china_connection",
        "name": "China Connection",
        "description": "Chinese ownership, PRC connections, Hong Kong links",
        "category": "geographic_risk",
        "threshold": 0.52,
        "example_phrases": [
            "Chinese state-owned enterprise involvement",
            "PRC government connections or affiliations",
            "Hong Kong company with mainland ownership",
            "Chinese investor acquiring strategic assets",
            "Communist Party connections or membership",
            "Belt and Road Initiative project involvement",
            "technology transfer to Chinese entities",
            "joint venture with Chinese partner",
            # From mined geographic patterns
            "Taiwan Strait tensions affecting business operations",
            "Xinjiang supply chain and forced labor concerns",
            "VIE structure for foreign investment in China",
            "princelings and red aristocracy business networks",
            "CFIUS review for Chinese acquisition",
            "military-civil fusion strategy implications",
            "Chinese entity on Commerce Department Entity List",
            "Macau gaming and junket operator connections",
            # From mined jurisdictions (China country profile)
            "wholly foreign owned enterprise structure indicates foreign investment vehicle",
            "limited liability company WFOE in PRC",
            "registered capital and paid-up capital requirements in China",
            "Chinese company registration details and incorporation date",
            "company status and shareholder information in Chinese registry",
        ]
    },
    {
        "id": "middle_east_gulf",
        "name": "Middle East & Gulf",
        "description": "UAE, Saudi, Qatar, Gulf state connections",
        "category": "geographic_risk",
        "threshold": 0.50,
        "example_phrases": [
            "Dubai-based holding company structure",
            "sovereign wealth fund investment from Gulf",
            "Saudi Arabian business connections",
            "UAE free zone company registration",
            "Qatari investment in European assets",
            "Bahrain financial services operations",
            "Kuwait investor with regional portfolio",
            "Abu Dhabi Global Market registration",
            # From mined geographic patterns
            "DIFC financial center operations",
            "hawala and informal value transfer concerns",
            "GCC royal family business network",
            "Yemen conflict supply chain involvement",
            "Saudi Vision 2030 investment opportunities",
            "JAFZA Jebel Ali free zone entity",
            "Oman investment in strategic sectors",
            "Iran sanctions exposure through Gulf routes",
            # From mined jurisdictions (Gulf country profiles)
            "UAE prohibits criticism of ruling families and government officials in media",
            "Saudi Corporate Registry is not available to the public online",
            "Kuwait Investment Authority participation indicates sovereign investment involvement",
            "Qatar Investment Authority and Qatar Foundation involvement suggests state-level strategic interest",
            "government ministries and Royal family structures in UAE",
            "security council activities and intelligence operations restricted",
            "personal financial details and internal government communications unavailable",
            "sovereign fund strategies and internal investment committee decisions",
        ]
    },
]

# Pre-compute concept IDs for quick lookup
CONCEPT_IDS = {c["id"]: c for c in CONCEPT_SETS}
CONCEPT_CATEGORIES = list(set(c["category"] for c in CONCEPT_SETS))


class DomainEmbedder:
    """
    Embeds domain content for semantic search and RAG.

    Uses intfloat/multilingual-e5-large (StandardEmbedder) for multilingual embeddings.
    Stores chunked content with embeddings in Elasticsearch.
    """

    def __init__(self):
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.es_url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")

        self.openai_client = None
        self.es_client = None
        self.openai_client = None  # Deprecated, using StandardEmbedder
        self.tokenizer = None
        
        # Initialize StandardEmbedder (replaces OpenAI)
        self.embedder = StandardEmbedder()

        self._initialized = False

        # Concept set embeddings cache (lazy-loaded)
        self._concept_embeddings: Dict[str, List[float]] = {}
        self._concepts_initialized = False

    async def initialize(self):
        """Initialize clients and ensure index exists."""
        if self._initialized:
            return

        # OpenAI client
        if OPENAI_AVAILABLE and self.openai_key:
            self.openai_client = AsyncOpenAI(api_key=self.openai_key)
            logger.info("OpenAI client initialized")
        else:
            logger.warning("OpenAI unavailable - no API key or missing package")

        # Elasticsearch client
        if ES_AVAILABLE:
            self.es_client = AsyncElasticsearch(self.es_url)
            await self._ensure_index()
            logger.info("Elasticsearch client initialized")
        else:
            logger.warning("Elasticsearch unavailable - missing package")

        # Tokenizer
        if TIKTOKEN_AVAILABLE:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
            logger.info("Tiktoken initialized")
        else:
            logger.info("Tiktoken unavailable - using word-based chunking")

        self._initialized = True

    async def _ensure_index(self):
        """Ensure cymonides-2 has the e5-large embedding field for domain content."""
        if not self.es_client:
            return

        exists = await self.es_client.indices.exists(index=INDEX_NAME)
        if not exists:
            # Create cymonides-2 with all required fields
            mappings = {
                "mappings": {
                    "properties": {
                        # Core content fields
                        "content": {"type": "text"},
                        "title": {"type": "text"},
                        "url": {"type": "keyword"},
                        "source_type": {"type": "keyword"},  # domain_content, report, youtube, book

                        # Domain-specific metadata
                        "domain": {"type": "keyword"},
                        "domain_tld": {"type": "keyword"},
                        "domain_registrar": {"type": "keyword"},
                        "domain_created": {"type": "date"},
                        "archive_timestamp": {"type": "date"},
                        "scrape_source": {"type": "keyword"},  # cc, wayback, firecrawl
                        "content_hash": {"type": "keyword"},  # MD5 of full content for exact-match

                        # Chunking metadata
                        "chunk_index": {"type": "integer"},
                        "total_chunks": {"type": "integer"},
                        "url_hash": {"type": "keyword"},

                        # Embeddings - both MiniLM (384) and e5-large (1024)
                        "content_embedding": {
                            "type": "dense_vector",
                            "dims": 384,
                            "index": True,
                            "similarity": "cosine"
                        },
                        "content_embedding_e5": {
                            "type": "dense_vector",
                            "dims": EMBEDDING_DIMS,
                            "index": True,
                            "similarity": "cosine"
                        },

                        # Other metadata
                        "language": {"type": "keyword"},
                        "created_at": {"type": "date"},
                        "indexed_at": {"type": "date"},

                        # Concept detection tags
                        "concept_tags": {"type": "keyword"},  # ["beneficial_ownership", "sanctions_exposure"]
                        "concept_scores": {"type": "object"},  # {"beneficial_ownership": 0.82, ...}
                    }
                },
                "settings": {
                    "number_of_shards": 2,
                    "number_of_replicas": 0
                }
            }
            await self.es_client.indices.create(index=INDEX_NAME, body=mappings)
            logger.info(f"Created index: {INDEX_NAME}")
        else:
            # Add e5-large embedding field if missing
            try:
                mapping = await self.es_client.indices.get_mapping(index=INDEX_NAME)
                props = mapping.get(INDEX_NAME, {}).get("mappings", {}).get("properties", {})

                if "content_embedding_e5" not in props:
                    await self.es_client.indices.put_mapping(
                        index=INDEX_NAME,
                        body={
                            "properties": {
                                "content_embedding_e5": {
                                    "type": "dense_vector",
                                    "dims": EMBEDDING_DIMS,
                                    "index": True,
                                    "similarity": "cosine"
                                },
                                "domain": {"type": "keyword"},
                                "domain_tld": {"type": "keyword"},
                                "scrape_source": {"type": "keyword"},
                                "archive_timestamp": {"type": "date"},
                                "content_hash": {"type": "keyword"},
                                "chunk_index": {"type": "integer"},
                                "total_chunks": {"type": "integer"},
                                "url_hash": {"type": "keyword"},
                                "source_type": {"type": "keyword"},
                                "concept_tags": {"type": "keyword"},
                                "concept_scores": {"type": "object"},
                            }
                        }
                    )
                    logger.info("Added e5-large embedding field to cymonides-2")
            except Exception as e:
                logger.warning(f"Could not update mapping: {e}")

    # =========================================================================
    # CONCEPT DETECTION
    # =========================================================================

    def _get_concepts_hash(self) -> str:
        """Generate hash of all concept phrases for cache invalidation."""
        import json
        phrases_data = [(c["id"], sorted(c.get("example_phrases", []))) for c in CONCEPT_SETS]
        return hashlib.md5(json.dumps(phrases_data, sort_keys=True).encode()).hexdigest()[:16]

    def _get_cache_path(self) -> str:
        """Get path for concept embeddings cache file."""
        cache_dir = os.path.join(os.path.dirname(__file__), ".cache")
        os.makedirs(cache_dir, exist_ok=True)
        return os.path.join(cache_dir, "concept_embeddings.json")

    def _load_cached_embeddings(self) -> bool:
        """Load concept embeddings from disk cache if valid."""
        import json
        cache_path = self._get_cache_path()
        if not os.path.exists(cache_path):
            return False

        try:
            with open(cache_path, 'r') as f:
                cache = json.load(f)

            # Check if cache is still valid (same hash = same phrases)
            if cache.get("hash") != self._get_concepts_hash():
                logger.info("Concept cache invalidated - phrases changed")
                return False

            self._concept_embeddings = cache.get("embeddings", {})
            logger.info(f"Loaded {len(self._concept_embeddings)} concept embeddings from cache")
            return True
        except Exception as e:
            logger.warning(f"Failed to load concept cache: {e}")
            return False

    def _save_embeddings_cache(self):
        """Save concept embeddings to disk cache."""
        import json
        cache_path = self._get_cache_path()
        try:
            cache = {
                "hash": self._get_concepts_hash(),
                "embeddings": self._concept_embeddings,
                "created": datetime.now().isoformat(),
                "concept_count": len(self._concept_embeddings),
                "phrase_count": sum(len(c.get("example_phrases", [])) for c in CONCEPT_SETS)
            }
            with open(cache_path, 'w') as f:
                json.dump(cache, f)
            logger.info(f"Saved concept embeddings cache: {len(self._concept_embeddings)} concepts")
        except Exception as e:
            logger.warning(f"Failed to save concept cache: {e}")

    async def _initialize_concepts(self, use_mined_phrases: bool = True):
        """
        Lazy-load concept embeddings (averaged from example phrases).
        Uses disk cache to avoid re-embedding on every restart.

        Args:
            use_mined_phrases: If True, enhance base phrases with mined phrases from
                              1000+ real corporate intelligence reports.
        """
        if self._concepts_initialized:
            return

        if not self.openai_client:
            logger.warning("Cannot initialize concepts - OpenAI client unavailable")
            return

        # Try loading from cache first (avoids ~$0.002 API cost per restart)
        if self._load_cached_embeddings():
            self._concepts_initialized = True
            return

        # Try to load mined phrases from report library
        mined_phrases: Dict[str, List[str]] = {}
        if use_mined_phrases:
            try:
                from modules.LINKLATER.concept_miner import get_mined_phrases
                mined_phrases = get_mined_phrases()
                logger.info(f"Loaded mined phrases for {len(mined_phrases)} concepts from report library")
            except Exception as e:
                logger.warning(f"Could not load mined phrases: {e}")

        logger.info(f"Initializing {len(CONCEPT_SETS)} concept embeddings...")

        for concept in CONCEPT_SETS:
            concept_id = concept["id"]
            base_phrases = concept["example_phrases"]

            # Combine base phrases with mined phrases (if available)
            additional_phrases = mined_phrases.get(concept_id, [])
            all_phrases = list(set(base_phrases + additional_phrases))

            # Limit to reasonable number for embedding (avoid huge API calls)
            # Take all base phrases + sample of additional
            if len(all_phrases) > 50:
                # Keep all base phrases, sample from mined
                all_phrases = base_phrases + additional_phrases[:50 - len(base_phrases)]

            try:
                # Embed all phrases for this concept
                response = await self.openai_client.embeddings.create(
                    input=all_phrases,
                    model=EMBEDDING_MODEL
                )

                # Average the phrase embeddings to get concept centroid
                embeddings = [d.embedding for d in response.data]
                centroid = np.mean(embeddings, axis=0).tolist()

                self._concept_embeddings[concept_id] = centroid
                logger.debug(f"Embedded concept: {concept_id} ({len(all_phrases)} phrases, {len(additional_phrases)} mined)")

            except Exception as e:
                logger.error(f"Failed to embed concept {concept_id}: {e}")

        self._concepts_initialized = True
        total_mined = sum(len(mined_phrases.get(c["id"], [])) for c in CONCEPT_SETS)
        logger.info(f"Concept embeddings initialized: {len(self._concept_embeddings)} concepts (+{total_mined} mined phrases)")

        # Save to cache for next restart (avoids re-embedding)
        self._save_embeddings_cache()

    async def detect_concepts(
        self,
        text: str,
        categories: Optional[List[str]] = None,
        return_all: bool = False
    ) -> Dict[str, Any]:
        """
        Detect which concepts are present in text using semantic similarity.

        Args:
            text: Text to analyze
            categories: Filter to specific categories (e.g., ["compliance_red_flag"])
            return_all: If True, return all scores; if False, only above threshold

        Returns:
            {
                "detected": [
                    {"id": "sanctions_exposure", "name": "Sanctions & Embargoes",
                     "score": 0.78, "category": "compliance_red_flag"}
                ],
                "categories": {"compliance_red_flag": 2, "ownership": 1},
                "all_scores": {...}  # if return_all=True
            }
        """
        await self.initialize()
        await self._initialize_concepts()

        if not self.openai_client or not self._concept_embeddings:
            return {"detected": [], "categories": {}, "error": "Concepts not available"}

        # Embed the input text
        try:
            response = await self.openai_client.embeddings.create(
                input=text[:8000],  # Limit for API
                model=EMBEDDING_MODEL
            )
            text_embedding = np.array(response.data[0].embedding)
        except Exception as e:
            logger.error(f"Text embedding failed: {e}")
            return {"detected": [], "categories": {}, "error": str(e)}

        # Compare against all concepts
        detected = []
        all_scores = {}
        category_counts = {}

        for concept in CONCEPT_SETS:
            concept_id = concept["id"]
            concept_category = concept["category"]

            # Filter by category if specified
            if categories and concept_category not in categories:
                continue

            if concept_id not in self._concept_embeddings:
                continue

            concept_embedding = np.array(self._concept_embeddings[concept_id])

            # Cosine similarity
            similarity = float(np.dot(text_embedding, concept_embedding) / (
                np.linalg.norm(text_embedding) * np.linalg.norm(concept_embedding)
            ))

            all_scores[concept_id] = similarity

            # Check against threshold
            threshold = concept.get("threshold", 0.65)
            if similarity >= threshold:
                detected.append({
                    "id": concept_id,
                    "name": concept["name"],
                    "description": concept["description"],
                    "score": round(similarity, 4),
                    "category": concept_category,
                    "threshold": threshold
                })

                # Count categories
                category_counts[concept_category] = category_counts.get(concept_category, 0) + 1

        # Sort by score descending
        detected.sort(key=lambda x: x["score"], reverse=True)

        result = {
            "detected": detected,
            "categories": category_counts,
            "concept_count": len(detected)
        }

        if return_all:
            result["all_scores"] = all_scores

        return result

    async def detect_concepts_for_embedding(
        self,
        embedding: List[float],
        categories: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        Fast concept detection using pre-computed embedding (no re-embedding).

        Args:
            embedding: Pre-computed content embedding
            categories: Filter to specific categories

        Returns:
            Dict of concept_id -> score for concepts above threshold
        """
        await self._initialize_concepts()

        if not self._concept_embeddings:
            return {}

        text_embedding = np.array(embedding)
        detected_scores = {}

        for concept in CONCEPT_SETS:
            concept_id = concept["id"]

            if categories and concept["category"] not in categories:
                continue

            if concept_id not in self._concept_embeddings:
                continue

            concept_embedding = np.array(self._concept_embeddings[concept_id])

            # Cosine similarity
            similarity = float(np.dot(text_embedding, concept_embedding) / (
                np.linalg.norm(text_embedding) * np.linalg.norm(concept_embedding)
            ))

            threshold = concept.get("threshold", 0.65)
            if similarity >= threshold:
                detected_scores[concept_id] = round(similarity, 4)

        return detected_scores

    async def get_domain_concepts(
        self,
        domain: str,
        categories: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated concept detection for all content from a domain.

        Returns concepts found across all indexed pages, with counts and
        sample URLs for each concept.
        """
        await self.initialize()

        if not self.es_client:
            return {"error": "Elasticsearch unavailable"}

        domain = domain.lower().strip()

        # Query for all documents with concept_tags
        try:
            result = await self.es_client.search(
                index=INDEX_NAME,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"domain": domain}},
                                {"exists": {"field": "concept_tags"}}
                            ]
                        }
                    },
                    "size": 0,
                    "aggs": {
                        "concepts": {
                            "terms": {"field": "concept_tags", "size": 50}
                        },
                        "by_url": {
                            "terms": {"field": "url", "size": 100},
                            "aggs": {
                                "concepts": {
                                    "terms": {"field": "concept_tags", "size": 20}
                                }
                            }
                        }
                    }
                }
            )

            # Parse aggregations
            concept_counts = {}
            for bucket in result["aggregations"]["concepts"]["buckets"]:
                concept_id = bucket["key"]
                concept_counts[concept_id] = {
                    "count": bucket["doc_count"],
                    "concept": CONCEPT_IDS.get(concept_id, {})
                }

            # URL breakdown
            url_concepts = {}
            for url_bucket in result["aggregations"]["by_url"]["buckets"]:
                url = url_bucket["key"]
                url_concepts[url] = [
                    b["key"] for b in url_bucket["concepts"]["buckets"]
                ]

            # Filter by category if specified
            if categories:
                concept_counts = {
                    k: v for k, v in concept_counts.items()
                    if CONCEPT_IDS.get(k, {}).get("category") in categories
                }

            return {
                "domain": domain,
                "concepts": concept_counts,
                "url_breakdown": url_concepts,
                "total_pages_with_concepts": len(url_concepts)
            }

        except Exception as e:
            logger.error(f"get_domain_concepts failed: {e}")
            return {"error": str(e)}

    async def search_by_concept(
        self,
        concept_id: str,
        domain: Optional[str] = None,
        min_score: float = 0.0,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Find all content tagged with a specific concept.

        Args:
            concept_id: Concept to search for (e.g., "sanctions_exposure")
            domain: Optional domain filter
            min_score: Minimum concept score
            limit: Max results

        Returns:
            List of matching documents with URLs and scores
        """
        await self.initialize()

        if not self.es_client:
            return []

        # Build query
        must_clauses = [{"term": {"concept_tags": concept_id}}]
        if domain:
            must_clauses.append({"term": {"domain": domain.lower().strip()}})

        try:
            result = await self.es_client.search(
                index=INDEX_NAME,
                body={
                    "query": {"bool": {"must": must_clauses}},
                    "size": limit,
                    "_source": ["url", "domain", "content", "concept_tags", "concept_scores", "archive_timestamp"]
                }
            )

            docs = []
            for hit in result["hits"]["hits"]:
                source = hit["_source"]
                concept_scores = source.get("concept_scores", {})
                score = concept_scores.get(concept_id, 0)

                if score >= min_score:
                    docs.append({
                        "url": source.get("url"),
                        "domain": source.get("domain"),
                        "content_snippet": source.get("content", "")[:500],
                        "concept_score": score,
                        "all_concepts": source.get("concept_tags", []),
                        "timestamp": source.get("archive_timestamp")
                    })

            # Sort by score
            docs.sort(key=lambda x: x["concept_score"], reverse=True)
            return docs

        except Exception as e:
            logger.error(f"search_by_concept failed: {e}")
            return []

    def _chunk_text(self, text: str) -> List[str]:
        """
        Chunk text into overlapping segments.

        Uses tiktoken for accurate token counting, falls back to word-based.
        512 tokens with 50 token overlap.
        """
        if not text or not text.strip():
            return []

        if self.tokenizer:
            # Token-based chunking
            tokens = self.tokenizer.encode(text)
            chunks = []

            start = 0
            while start < len(tokens):
                end = min(start + CHUNK_SIZE, len(tokens))
                chunk_tokens = tokens[start:end]
                chunk_text = self.tokenizer.decode(chunk_tokens)
                chunks.append(chunk_text)

                # Move forward with overlap
                start = end - CHUNK_OVERLAP
                if start >= len(tokens):
                    break

            return chunks
        else:
            # Word-based fallback (approximate 1 token = 0.75 words)
            words = text.split()
            word_chunk_size = int(CHUNK_SIZE * 0.75)
            word_overlap = int(CHUNK_OVERLAP * 0.75)

            chunks = []
            start = 0
            while start < len(words):
                end = min(start + word_chunk_size, len(words))
                chunk_words = words[start:end]
                chunks.append(" ".join(chunk_words))

                start = end - word_overlap
                if start >= len(words):
                    break

            return chunks

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Batch embed texts using OpenAI text-embedding-3-large.

        Returns list of 3072-dim embeddings.
        """
        if not self.embedder or not texts:
            return []


        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            try:
                # Use StandardEmbedder (synchronous)
                all_embeddings = self.embedder.encode_batch_passages(
                    texts=texts,
                    batch_size=BATCH_SIZE,
                    show_progress=False
                )
            except Exception as e:
                logger.error(f"Embedding batch {i} failed: {e}")
                # Fill with None to maintain alignment

        return all_embeddings

    def _detect_language(self, text: str) -> str:
        """Simple language detection based on character patterns."""
        # Check for Cyrillic (Russian, Ukrainian, etc.)
        cyrillic = len(re.findall(r'[\u0400-\u04FF]', text))
        # Check for CJK (Chinese, Japanese, Korean)
        cjk = len(re.findall(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', text))
        # Check for Arabic
        arabic = len(re.findall(r'[\u0600-\u06FF]', text))
        # Latin
        latin = len(re.findall(r'[a-zA-Z]', text))

        total = cyrillic + cjk + arabic + latin
        if total == 0:
            return "unknown"

        if cyrillic / total > 0.3:
            return "cyrillic"
        elif cjk / total > 0.3:
            return "cjk"
        elif arabic / total > 0.3:
            return "arabic"
        else:
            return "latin"

    async def embed_content(
        self,
        domain: str,
        url: str,
        content: str,
        source: str = "unknown",
        timestamp: Optional[str] = None,
        skip_if_exists: bool = True
    ) -> Dict[str, Any]:
        """
        Embed and store domain content.

        Args:
            domain: Target domain (e.g., "example.com")
            url: Source URL
            content: Text content to embed
            source: Source type (cc, wayback, firecrawl, live)
            timestamp: Archive/scrape timestamp (ISO format)
            skip_if_exists: Skip if URL+timestamp already embedded

        Returns:
            {
                "status": "success" | "skipped" | "error",
                "chunks_embedded": int,
                "domain": str
            }
        """
        await self.initialize()

        if not self.es_client or not self.openai_client:
            return {"status": "error", "error": "Clients not available", "chunks_embedded": 0}

        domain = domain.lower().strip()
        url_hash = hashlib.md5(f"{url}:{timestamp or 'live'}".encode()).hexdigest()
        content_hash = hashlib.md5(content.encode()).hexdigest()  # For exact-match comparison

        # Check if already embedded
        if skip_if_exists:
            existing = await self.es_client.search(
                index=INDEX_NAME,
                body={
                    "query": {"term": {"url_hash": url_hash}},
                    "size": 1
                }
            )
            if existing["hits"]["total"]["value"] > 0:
                return {"status": "skipped", "reason": "already_embedded", "chunks_embedded": 0, "domain": domain}

        # Chunk content
        chunks = self._chunk_text(content)
        if not chunks:
            return {"status": "skipped", "reason": "no_content", "chunks_embedded": 0, "domain": domain}

        # Embed chunks
        embeddings = await self._embed_texts(chunks)

        # Detect language (from first chunk)
        language = self._detect_language(chunks[0])

        # Extract TLD from domain
        tld = domain.split(".")[-1] if "." in domain else ""

        # Initialize concept detection (lazy-load)
        await self._initialize_concepts()

        # Index documents to cymonides-2 with proper structure
        now = datetime.utcnow().isoformat() + "Z"
        docs_indexed = 0
        all_concepts_detected = set()

        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            if embedding is None:
                continue

            # Detect concepts for this chunk using its embedding
            concept_scores = await self.detect_concepts_for_embedding(embedding)
            concept_tags = list(concept_scores.keys())
            all_concepts_detected.update(concept_tags)

            doc = {
                # Core content (matches cymonides-2 schema)
                "content": chunk,
                "title": f"{domain} - chunk {i+1}/{len(chunks)}",
                "url": url,
                "source_type": DOC_TYPE,  # "domain_content"

                # Domain-specific metadata
                "domain": domain,
                "domain_tld": tld,
                "archive_timestamp": timestamp or now,
                "scrape_source": source,
                "content_hash": content_hash,  # MD5 of full page content

                # Chunking metadata
                "chunk_index": i,
                "total_chunks": len(chunks),
                "url_hash": url_hash,

                # e5-large embedding (1024 dims, multilingual)
                "content_embedding_e5": embedding,

                # Concept detection (auto-tagged)
                "concept_tags": concept_tags,
                "concept_scores": concept_scores,

                # Other metadata
                "language": language,
                "created_at": now,
                "indexed_at": now,
            }

            doc_id = f"domain_{url_hash}_{i}"
            try:
                await self.es_client.index(index=INDEX_NAME, id=doc_id, body=doc)
                docs_indexed += 1
            except Exception as e:
                logger.error(f"Failed to index chunk {i}: {e}")

        concepts_found = list(all_concepts_detected)
        if concepts_found:
            logger.info(f"Embedded {docs_indexed}/{len(chunks)} chunks for {domain}: {url} | Concepts: {concepts_found}")
        else:
            logger.info(f"Embedded {docs_indexed}/{len(chunks)} chunks for {domain}: {url}")

        return {
            "status": "success",
            "chunks_embedded": docs_indexed,
            "total_chunks": len(chunks),
            "domain": domain,
            "url": url,
            "language": language,
            "concepts_detected": concepts_found
        }

    async def search(
        self,
        domain: str,
        query: str,
        limit: int = 10,
        min_score: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Semantic search within domain content.

        Args:
            domain: Domain to search (e.g., "example.com")
            query: Natural language query
            limit: Max results to return
            min_score: Minimum cosine similarity threshold

        Returns:
            List of matching chunks with scores and metadata.
        """
        await self.initialize()

        if not self.es_client or not self.openai_client:
            return []

        domain = domain.lower().strip()

        # Embed query
        try:
            response = await self.openai_client.embeddings.create(
                input=query,
                model=EMBEDDING_MODEL
            )
            query_embedding = response.data[0].embedding
        except Exception as e:
            logger.error(f"Query embedding failed: {e}")
            return []

        # Vector search scoped to domain using OpenAI embeddings
        search_body = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"domain": domain}},
                        {"term": {"source_type": DOC_TYPE}}  # Only domain_content docs
                    ],
                    "should": [
                        {
                            "script_score": {
                                "query": {"match_all": {}},
                                "script": {
                                    "source": "cosineSimilarity(params.query_vector, 'content_embedding_e5') + 1.0",
                                    "params": {"query_vector": query_embedding}
                                }
                            }
                        }
                    ]
                }
            },
            "size": limit,
            "min_score": min_score + 1.0,  # Adjust for +1.0 in script
            "_source": ["domain", "url", "archive_timestamp", "scrape_source", "content", "chunk_index", "language"]
        }

        try:
            results = await self.es_client.search(index=INDEX_NAME, body=search_body)

            matches = []
            for hit in results["hits"]["hits"]:
                src = hit["_source"]
                matches.append({
                    "score": hit["_score"] - 1.0,  # Remove +1.0 offset
                    "domain": src.get("domain"),
                    "url": src.get("url"),
                    "timestamp": src.get("archive_timestamp"),
                    "source": src.get("scrape_source"),
                    "content_chunk": src.get("content"),
                    "chunk_index": src.get("chunk_index"),
                    "language": src.get("language"),
                })

            return matches
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    async def get_domain_stats(self, domain: str) -> Dict[str, Any]:
        """Get embedding statistics for a domain."""
        await self.initialize()

        if not self.es_client:
            return {"error": "Elasticsearch unavailable"}

        domain = domain.lower().strip()

        try:
            result = await self.es_client.search(
                index=INDEX_NAME,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"domain": domain}},
                                {"term": {"source_type": DOC_TYPE}}
                            ]
                        }
                    },
                    "size": 0,
                    "aggs": {
                        "total_chunks": {"value_count": {"field": "chunk_index"}},
                        "unique_urls": {"cardinality": {"field": "url"}},
                        "sources": {"terms": {"field": "scrape_source"}},
                        "languages": {"terms": {"field": "language"}},
                        "date_range": {
                            "stats": {"field": "archive_timestamp"}
                        }
                    }
                }
            )

            aggs = result["aggregations"]
            return {
                "domain": domain,
                "total_chunks": aggs["total_chunks"]["value"],
                "unique_urls": aggs["unique_urls"]["value"],
                "sources": {b["key"]: b["doc_count"] for b in aggs["sources"]["buckets"]},
                "languages": {b["key"]: b["doc_count"] for b in aggs["languages"]["buckets"]},
                "oldest_content": aggs["date_range"].get("min_as_string"),
                "newest_content": aggs["date_range"].get("max_as_string")
            }
        except Exception as e:
            logger.error(f"Stats failed: {e}")
            return {"error": str(e)}

    async def delete_domain(self, domain: str) -> Dict[str, Any]:
        """Delete all embeddings for a domain (only domain_content docs)."""
        await self.initialize()

        if not self.es_client:
            return {"error": "Elasticsearch unavailable"}

        domain = domain.lower().strip()

        try:
            result = await self.es_client.delete_by_query(
                index=INDEX_NAME,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"domain": domain}},
                                {"term": {"source_type": DOC_TYPE}}
                            ]
                        }
                    }
                }
            )

            return {
                "domain": domain,
                "deleted": result["deleted"],
                "status": "success"
            }
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return {"error": str(e)}

    async def get_url_versions(
        self,
        url: str,
        include_embeddings: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all archived versions of a specific URL.

        Args:
            url: URL to get versions for
            include_embeddings: Whether to include embedding vectors (for comparison)

        Returns:
            List of versions sorted by timestamp (oldest first)
        """
        await self.initialize()

        if not self.es_client:
            return []

        source_fields = ["url", "archive_timestamp", "scrape_source", "content_hash", "content", "chunk_index", "total_chunks"]
        if include_embeddings:
            source_fields.append("content_embedding_e5")

        try:
            result = await self.es_client.search(
                index=INDEX_NAME,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"url": url}},
                                {"term": {"source_type": DOC_TYPE}},
                                {"term": {"chunk_index": 0}}  # First chunk only (representative)
                            ]
                        }
                    },
                    "sort": [{"archive_timestamp": "asc"}],
                    "size": 100,
                    "_source": source_fields
                }
            )

            versions = []
            for hit in result["hits"]["hits"]:
                src = hit["_source"]
                v = {
                    "url": src.get("url"),
                    "timestamp": src.get("archive_timestamp"),
                    "source": src.get("scrape_source"),
                    "content_hash": src.get("content_hash"),
                    "preview": src.get("content", "")[:500],
                    "total_chunks": src.get("total_chunks", 1)
                }
                if include_embeddings and "content_embedding_e5" in src:
                    v["embedding"] = src["content_embedding_e5"]
                versions.append(v)

            return versions
        except Exception as e:
            logger.error(f"get_url_versions failed: {e}")
            return []

    async def compare_versions(
        self,
        url: str,
        timestamp1: Optional[str] = None,
        timestamp2: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compare two versions of a URL using semantic similarity.

        Args:
            url: URL to compare
            timestamp1: First timestamp (None = oldest)
            timestamp2: Second timestamp (None = newest)

        Returns:
            {
                "url": str,
                "version1": {...},
                "version2": {...},
                "content_identical": bool,  # MD5 hash match
                "semantic_similarity": float,  # Cosine similarity (0-1)
                "drift_category": "identical" | "minor" | "moderate" | "significant" | "different"
            }
        """
        versions = await self.get_url_versions(url, include_embeddings=True)

        if len(versions) < 2:
            return {
                "url": url,
                "error": "Need at least 2 versions to compare",
                "versions_found": len(versions)
            }

        # Select versions to compare
        v1 = versions[0]  # Oldest by default
        v2 = versions[-1]  # Newest by default

        # Override if specific timestamps provided
        if timestamp1:
            v1_match = [v for v in versions if v["timestamp"] == timestamp1]
            if v1_match:
                v1 = v1_match[0]

        if timestamp2:
            v2_match = [v for v in versions if v["timestamp"] == timestamp2]
            if v2_match:
                v2 = v2_match[0]

        # Check exact match via content hash
        content_identical = v1.get("content_hash") == v2.get("content_hash")

        # Compute semantic similarity if embeddings available
        semantic_similarity = None
        drift_category = "unknown"

        emb1 = v1.get("embedding")
        emb2 = v2.get("embedding")

        if emb1 and emb2:
            # Cosine similarity
            vec1 = np.array(emb1)
            vec2 = np.array(emb2)
            dot = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            if norm1 > 0 and norm2 > 0:
                semantic_similarity = float(dot / (norm1 * norm2))

                # Categorize drift
                if content_identical or semantic_similarity >= 0.99:
                    drift_category = "identical"
                elif semantic_similarity >= 0.95:
                    drift_category = "minor"
                elif semantic_similarity >= 0.85:
                    drift_category = "moderate"
                elif semantic_similarity >= 0.70:
                    drift_category = "significant"
                else:
                    drift_category = "different"

        # Clean up embeddings from response
        v1_clean = {k: v for k, v in v1.items() if k != "embedding"}
        v2_clean = {k: v for k, v in v2.items() if k != "embedding"}

        return {
            "url": url,
            "version1": v1_clean,
            "version2": v2_clean,
            "content_identical": content_identical,
            "semantic_similarity": semantic_similarity,
            "drift_category": drift_category,
            "total_versions": len(versions)
        }

    async def get_semantic_drift_timeline(
        self,
        url: str
    ) -> Dict[str, Any]:
        """
        Analyze semantic drift across all versions of a URL.

        Returns timeline of changes with similarity scores between consecutive versions.
        """
        versions = await self.get_url_versions(url, include_embeddings=True)

        if len(versions) < 2:
            return {
                "url": url,
                "error": "Need at least 2 versions for drift analysis",
                "versions_found": len(versions)
            }

        drift_timeline = []
        significant_changes = []

        for i in range(1, len(versions)):
            v_prev = versions[i - 1]
            v_curr = versions[i]

            emb_prev = v_prev.get("embedding")
            emb_curr = v_curr.get("embedding")

            similarity = None
            if emb_prev and emb_curr:
                vec_prev = np.array(emb_prev)
                vec_curr = np.array(emb_curr)
                dot = np.dot(vec_prev, vec_curr)
                norm_prev = np.linalg.norm(vec_prev)
                norm_curr = np.linalg.norm(vec_curr)
                if norm_prev > 0 and norm_curr > 0:
                    similarity = float(dot / (norm_prev * norm_curr))

            content_changed = v_prev.get("content_hash") != v_curr.get("content_hash")

            entry = {
                "from_timestamp": v_prev.get("timestamp"),
                "to_timestamp": v_curr.get("timestamp"),
                "from_source": v_prev.get("source"),
                "to_source": v_curr.get("source"),
                "content_changed": content_changed,
                "similarity": similarity
            }
            drift_timeline.append(entry)

            # Track significant changes (similarity < 0.85)
            if similarity is not None and similarity < 0.85:
                significant_changes.append({
                    "timestamp": v_curr.get("timestamp"),
                    "similarity": similarity,
                    "preview": v_curr.get("preview", "")[:200]
                })

        # Calculate overall drift (first vs last)
        first_emb = versions[0].get("embedding")
        last_emb = versions[-1].get("embedding")
        overall_drift = None

        if first_emb and last_emb:
            vec_first = np.array(first_emb)
            vec_last = np.array(last_emb)
            dot = np.dot(vec_first, vec_last)
            norm_first = np.linalg.norm(vec_first)
            norm_last = np.linalg.norm(vec_last)
            if norm_first > 0 and norm_last > 0:
                overall_drift = float(dot / (norm_first * norm_last))

        return {
            "url": url,
            "total_versions": len(versions),
            "first_seen": versions[0].get("timestamp"),
            "last_seen": versions[-1].get("timestamp"),
            "overall_similarity": overall_drift,
            "significant_changes": len(significant_changes),
            "drift_timeline": drift_timeline,
            "change_events": significant_changes
        }

    async def find_similar_pages(
        self,
        domain: str,
        url: str,
        threshold: float = 0.85,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Find pages within a domain that are semantically similar to a given URL.

        Useful for detecting duplicate/near-duplicate content.
        """
        await self.initialize()

        if not self.es_client or not self.openai_client:
            return []

        # Get embedding for target URL (first chunk)
        try:
            target_result = await self.es_client.search(
                index=INDEX_NAME,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"url": url}},
                                {"term": {"source_type": DOC_TYPE}},
                                {"term": {"chunk_index": 0}}
                            ]
                        }
                    },
                    "sort": [{"archive_timestamp": "desc"}],
                    "size": 1,
                    "_source": ["content_embedding_e5"]
                }
            )

            if not target_result["hits"]["hits"]:
                return []

            target_embedding = target_result["hits"]["hits"][0]["_source"].get("content_embedding_e5")
            if not target_embedding:
                return []

            # Search for similar pages in same domain
            search_body = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"domain": domain.lower().strip()}},
                            {"term": {"source_type": DOC_TYPE}},
                            {"term": {"chunk_index": 0}}  # First chunks only
                        ],
                        "must_not": [
                            {"term": {"url": url}}  # Exclude self
                        ]
                    }
                },
                "size": limit * 2,  # Fetch extra to filter by threshold
                "_source": ["url", "archive_timestamp", "content_hash", "content"]
            }

            candidates = await self.es_client.search(index=INDEX_NAME, body=search_body)

            # Compute similarities
            similar_pages = []
            target_vec = np.array(target_embedding)
            target_norm = np.linalg.norm(target_vec)

            for hit in candidates["hits"]["hits"]:
                src = hit["_source"]
                # Get embedding for this candidate
                cand_result = await self.es_client.search(
                    index=INDEX_NAME,
                    body={
                        "query": {
                            "bool": {
                                "must": [
                                    {"term": {"url": src["url"]}},
                                    {"term": {"chunk_index": 0}}
                                ]
                            }
                        },
                        "sort": [{"archive_timestamp": "desc"}],
                        "size": 1,
                        "_source": ["content_embedding_e5"]
                    }
                )

                if cand_result["hits"]["hits"]:
                    cand_emb = cand_result["hits"]["hits"][0]["_source"].get("content_embedding_e5")
                    if cand_emb:
                        cand_vec = np.array(cand_emb)
                        cand_norm = np.linalg.norm(cand_vec)
                        if target_norm > 0 and cand_norm > 0:
                            similarity = float(np.dot(target_vec, cand_vec) / (target_norm * cand_norm))
                            if similarity >= threshold:
                                similar_pages.append({
                                    "url": src["url"],
                                    "timestamp": src.get("archive_timestamp"),
                                    "similarity": similarity,
                                    "preview": src.get("content", "")[:200]
                                })

            # Sort by similarity desc and limit
            similar_pages.sort(key=lambda x: x["similarity"], reverse=True)
            return similar_pages[:limit]

        except Exception as e:
            logger.error(f"find_similar_pages failed: {e}")
            return []

    async def compare_texts(
        self,
        text1: str,
        text2: str
    ) -> Dict[str, Any]:
        """
        Compare two arbitrary texts using semantic similarity.

        Works with long texts - full pages, documents, articles.
        Not limited to keywords.

        Args:
            text1: First text (any length)
            text2: Second text (any length)

        Returns:
            {
                "similarity": float (0-1),
                "category": "identical" | "very_similar" | "similar" | "related" | "different",
                "text1_tokens": int,
                "text2_tokens": int
            }
        """
        await self.initialize()

        if not self.openai_client:
            return {"error": "OpenAI client unavailable", "similarity": None}

        # Get token counts
        text1_tokens = len(self.tokenizer.encode(text1)) if self.tokenizer else len(text1.split())
        text2_tokens = len(self.tokenizer.encode(text2)) if self.tokenizer else len(text2.split())

        # For very long texts, use chunked comparison
        # Compare first chunk embedding as representative
        if text1_tokens > CHUNK_SIZE:
            text1 = self._chunk_text(text1)[0]
        if text2_tokens > CHUNK_SIZE:
            text2 = self._chunk_text(text2)[0]

        try:
            # Embed both texts
            response = await self.openai_client.embeddings.create(
                input=[text1, text2],
                model=EMBEDDING_MODEL
            )
            emb1 = np.array(response.data[0].embedding)
            emb2 = np.array(response.data[1].embedding)

            # Cosine similarity
            dot = np.dot(emb1, emb2)
            norm1 = np.linalg.norm(emb1)
            norm2 = np.linalg.norm(emb2)
            similarity = float(dot / (norm1 * norm2)) if norm1 > 0 and norm2 > 0 else 0.0

            # Categorize
            if similarity >= 0.98:
                category = "identical"
            elif similarity >= 0.90:
                category = "very_similar"
            elif similarity >= 0.80:
                category = "similar"
            elif similarity >= 0.65:
                category = "related"
            else:
                category = "different"

            return {
                "similarity": round(similarity, 4),
                "category": category,
                "text1_tokens": text1_tokens,
                "text2_tokens": text2_tokens,
            }

        except Exception as e:
            logger.error(f"compare_texts failed: {e}")
            return {"error": str(e), "similarity": None}

    async def find_similar_in_corpus(
        self,
        text: str,
        domain: Optional[str] = None,
        limit: int = 20,
        min_score: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Find documents in corpus similar to a given text.

        The text can be an entire page, document, or article.
        Not limited to short queries.

        Args:
            text: Long text to compare against corpus
            domain: Optional - limit search to specific domain
            limit: Max results
            min_score: Minimum similarity threshold

        Returns:
            List of similar documents with scores
        """
        await self.initialize()

        if not self.openai_client or not self.es_client:
            return []

        # For long texts, use first chunk as representative embedding
        tokens = len(self.tokenizer.encode(text)) if self.tokenizer else len(text.split())
        search_text = self._chunk_text(text)[0] if tokens > CHUNK_SIZE else text

        try:
            # Embed the search text
            response = await self.openai_client.embeddings.create(
                input=search_text,
                model=EMBEDDING_MODEL
            )
            query_embedding = response.data[0].embedding

            # Build search query
            must_clauses = [{"term": {"source_type": DOC_TYPE}}]
            if domain:
                must_clauses.append({"term": {"domain": domain.lower().strip()}})

            search_body = {
                "query": {
                    "bool": {
                        "must": must_clauses,
                        "should": [
                            {
                                "script_score": {
                                    "query": {"match_all": {}},
                                    "script": {
                                        "source": "cosineSimilarity(params.query_vector, 'content_embedding_e5') + 1.0",
                                        "params": {"query_vector": query_embedding}
                                    }
                                }
                            }
                        ]
                    }
                },
                "size": limit,
                "min_score": min_score + 1.0,
                "_source": ["domain", "url", "archive_timestamp", "scrape_source", "content", "chunk_index"]
            }

            results = await self.es_client.search(index=INDEX_NAME, body=search_body)

            matches = []
            for hit in results["hits"]["hits"]:
                src = hit["_source"]
                matches.append({
                    "score": round(hit["_score"] - 1.0, 4),
                    "domain": src.get("domain"),
                    "url": src.get("url"),
                    "timestamp": src.get("archive_timestamp"),
                    "source": src.get("scrape_source"),
                    "preview": src.get("content", "")[:500],
                })

            return matches

        except Exception as e:
            logger.error(f"find_similar_in_corpus failed: {e}")
            return []

    async def compare_documents(
        self,
        url1: str,
        url2: str,
        timestamp1: Optional[str] = None,
        timestamp2: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compare two documents by URL using full content similarity.

        Can compare:
        - Two different URLs
        - Same URL at different timestamps
        - Cross-domain comparison

        Args:
            url1: First URL
            url2: Second URL
            timestamp1: Optional timestamp for url1
            timestamp2: Optional timestamp for url2

        Returns:
            Full comparison with similarity score and content previews
        """
        await self.initialize()

        if not self.es_client:
            return {"error": "Elasticsearch unavailable"}

        async def get_doc_embedding(url: str, timestamp: Optional[str]) -> Optional[tuple]:
            """Get document embedding and content."""
            query = {
                "bool": {
                    "must": [
                        {"term": {"url": url}},
                        {"term": {"source_type": DOC_TYPE}},
                        {"term": {"chunk_index": 0}}  # First chunk
                    ]
                }
            }

            sort = [{"archive_timestamp": "desc"}]
            if timestamp:
                query["bool"]["must"].append({"term": {"archive_timestamp": timestamp}})

            result = await self.es_client.search(
                index=INDEX_NAME,
                body={
                    "query": query,
                    "sort": sort,
                    "size": 1,
                    "_source": ["content_embedding_e5", "content", "archive_timestamp", "domain"]
                }
            )

            if result["hits"]["hits"]:
                src = result["hits"]["hits"][0]["_source"]
                return (
                    src.get("content_embedding_e5"),
                    src.get("content", "")[:500],
                    src.get("archive_timestamp"),
                    src.get("domain")
                )
            return None

        try:
            doc1 = await get_doc_embedding(url1, timestamp1)
            doc2 = await get_doc_embedding(url2, timestamp2)

            if not doc1:
                return {"error": f"Document not found: {url1}"}
            if not doc2:
                return {"error": f"Document not found: {url2}"}

            emb1, content1, ts1, domain1 = doc1
            emb2, content2, ts2, domain2 = doc2

            if not emb1 or not emb2:
                return {"error": "Embeddings not available for one or both documents"}

            # Compute similarity
            vec1 = np.array(emb1)
            vec2 = np.array(emb2)
            dot = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            similarity = float(dot / (norm1 * norm2)) if norm1 > 0 and norm2 > 0 else 0.0

            # Categorize
            if similarity >= 0.98:
                category = "identical"
            elif similarity >= 0.90:
                category = "very_similar"
            elif similarity >= 0.80:
                category = "similar"
            elif similarity >= 0.65:
                category = "related"
            else:
                category = "different"

            return {
                "url1": url1,
                "url2": url2,
                "similarity": round(similarity, 4),
                "category": category,
                "doc1": {
                    "domain": domain1,
                    "timestamp": ts1,
                    "preview": content1,
                },
                "doc2": {
                    "domain": domain2,
                    "timestamp": ts2,
                    "preview": content2,
                },
                "same_domain": domain1 == domain2,
            }

        except Exception as e:
            logger.error(f"compare_documents failed: {e}")
            return {"error": str(e)}

    async def analyze_version_changes(
        self,
        url: str,
        significance_threshold: float = 0.85
    ) -> Dict[str, Any]:
        """
        AI-to-AI pipeline: Detect and explain version changes.

        1. Get all versions
        2. Find significant change points (similarity < threshold)
        3. AI analyzes each change: what changed, what was added/removed
        4. Returns structured analysis

        Args:
            url: URL to analyze
            significance_threshold: Similarity below this = significant change

        Returns:
            {
                "url": str,
                "total_versions": int,
                "significant_changes": [
                    {
                        "from_version": {...},
                        "to_version": {...},
                        "similarity": float,
                        "change_type": "major" | "moderate",
                        "ai_analysis": {
                            "summary": str,
                            "added": [str],
                            "removed": [str],
                            "modified": [str],
                            "significance": str
                        }
                    }
                ],
                "overall_narrative": str
            }
        """
        await self.initialize()

        if not self.openai_client or not self.es_client:
            return {"error": "Clients unavailable"}

        # Step 1: Get all versions with content
        versions = await self._get_versions_with_content(url)

        if len(versions) < 2:
            return {
                "url": url,
                "total_versions": len(versions),
                "significant_changes": [],
                "overall_narrative": "Not enough versions to analyze changes."
            }

        # Step 2: Find significant change points
        significant_changes = []

        for i in range(1, len(versions)):
            v_prev = versions[i - 1]
            v_curr = versions[i]

            # Compare embeddings
            similarity = await self._compute_similarity(
                v_prev.get("embedding"),
                v_curr.get("embedding")
            )

            if similarity is not None and similarity < significance_threshold:
                change_type = "major" if similarity < 0.70 else "moderate"

                # Step 3: AI analyzes what changed
                ai_analysis = await self._ai_analyze_change(
                    v_prev.get("content", ""),
                    v_curr.get("content", ""),
                    v_prev.get("timestamp"),
                    v_curr.get("timestamp"),
                    similarity
                )

                significant_changes.append({
                    "from_version": {
                        "timestamp": v_prev.get("timestamp"),
                        "source": v_prev.get("source"),
                        "preview": v_prev.get("content", "")[:300],
                    },
                    "to_version": {
                        "timestamp": v_curr.get("timestamp"),
                        "source": v_curr.get("source"),
                        "preview": v_curr.get("content", "")[:300],
                    },
                    "similarity": round(similarity, 4),
                    "change_type": change_type,
                    "ai_analysis": ai_analysis,
                })

        # Step 4: Generate overall narrative
        overall_narrative = await self._generate_change_narrative(url, versions, significant_changes)

        return {
            "url": url,
            "total_versions": len(versions),
            "first_seen": versions[0].get("timestamp"),
            "last_seen": versions[-1].get("timestamp"),
            "significant_changes": significant_changes,
            "overall_narrative": overall_narrative,
        }

    async def _get_versions_with_content(self, url: str) -> List[Dict[str, Any]]:
        """Get all versions of URL with full content and embeddings."""
        try:
            result = await self.es_client.search(
                index=INDEX_NAME,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"url": url}},
                                {"term": {"source_type": DOC_TYPE}},
                                {"term": {"chunk_index": 0}}
                            ]
                        }
                    },
                    "sort": [{"archive_timestamp": "asc"}],
                    "size": 100,
                    "_source": ["content", "content_embedding_e5", "archive_timestamp", "scrape_source"]
                }
            )

            versions = []
            for hit in result["hits"]["hits"]:
                src = hit["_source"]
                versions.append({
                    "content": src.get("content", ""),
                    "embedding": src.get("content_embedding_e5"),
                    "timestamp": src.get("archive_timestamp"),
                    "source": src.get("scrape_source"),
                })

            return versions
        except Exception as e:
            logger.error(f"_get_versions_with_content failed: {e}")
            return []

    async def _compute_similarity(self, emb1: Optional[List[float]], emb2: Optional[List[float]]) -> Optional[float]:
        """Compute cosine similarity between two embeddings."""
        if not emb1 or not emb2:
            return None

        vec1 = np.array(emb1)
        vec2 = np.array(emb2)
        dot = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 > 0 and norm2 > 0:
            return float(dot / (norm1 * norm2))
        return None

    async def _ai_analyze_change(
        self,
        content_before: str,
        content_after: str,
        timestamp_before: str,
        timestamp_after: str,
        similarity: float
    ) -> Dict[str, Any]:
        """
        AI analyzes what changed between two versions.

        Returns structured analysis of additions, removals, modifications.
        """
        if not self.openai_client:
            return {"error": "OpenAI unavailable"}

        # Truncate for context window
        max_chars = 6000
        before_text = content_before[:max_chars] if len(content_before) > max_chars else content_before
        after_text = content_after[:max_chars] if len(content_after) > max_chars else content_after

        prompt = f"""Analyze the changes between these two versions of a webpage.

VERSION 1 (from {timestamp_before}):
{before_text}

---

VERSION 2 (from {timestamp_after}):
{after_text}

---

The semantic similarity between versions is {similarity:.2%}.

Provide a structured analysis:
1. SUMMARY: One sentence describing the main change
2. ADDED: List key content/sections that were added (bullet points)
3. REMOVED: List key content/sections that were removed (bullet points)
4. MODIFIED: List key content that was changed/updated (bullet points)
5. SIGNIFICANCE: Why might this change matter for an investigation? (one sentence)

Be specific. Reference actual text from the pages. If no changes in a category, say "None"."""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Fast, good at analysis
                messages=[
                    {"role": "system", "content": "You are an investigative analyst comparing webpage versions to identify significant changes. Be precise and cite specific content."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
            )

            analysis_text = response.choices[0].message.content

            # Parse structured response
            return self._parse_change_analysis(analysis_text)

        except Exception as e:
            logger.error(f"_ai_analyze_change failed: {e}")
            return {"error": str(e), "raw": ""}

    def _parse_change_analysis(self, analysis_text: str) -> Dict[str, Any]:
        """Parse AI analysis into structured format."""
        result = {
            "summary": "",
            "added": [],
            "removed": [],
            "modified": [],
            "significance": "",
            "raw": analysis_text,
        }

        lines = analysis_text.split("\n")
        current_section = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            line_lower = line.lower()

            if line_lower.startswith("summary:") or line_lower.startswith("1."):
                current_section = "summary"
                text = line.split(":", 1)[-1].strip() if ":" in line else ""
                if text:
                    result["summary"] = text
            elif line_lower.startswith("added:") or line_lower.startswith("2."):
                current_section = "added"
            elif line_lower.startswith("removed:") or line_lower.startswith("3."):
                current_section = "removed"
            elif line_lower.startswith("modified:") or line_lower.startswith("4."):
                current_section = "modified"
            elif line_lower.startswith("significance:") or line_lower.startswith("5."):
                current_section = "significance"
                text = line.split(":", 1)[-1].strip() if ":" in line else ""
                if text:
                    result["significance"] = text
            elif line.startswith("-") or line.startswith("•") or line.startswith("*"):
                item = line.lstrip("-•* ").strip()
                if item and item.lower() != "none":
                    if current_section in ["added", "removed", "modified"]:
                        result[current_section].append(item)
            elif current_section == "summary" and not result["summary"]:
                result["summary"] = line
            elif current_section == "significance" and not result["significance"]:
                result["significance"] = line

        return result

    async def _generate_change_narrative(
        self,
        url: str,
        versions: List[Dict],
        significant_changes: List[Dict]
    ) -> str:
        """Generate overall narrative about how the page evolved."""
        if not self.openai_client:
            return "AI narrative generation unavailable."

        if not significant_changes:
            return f"Page has {len(versions)} versions with no significant semantic changes detected."

        # Build context for AI
        changes_summary = []
        for i, change in enumerate(significant_changes, 1):
            ts_from = change["from_version"]["timestamp"]
            ts_to = change["to_version"]["timestamp"]
            sim = change["similarity"]
            summary = change.get("ai_analysis", {}).get("summary", "")
            changes_summary.append(f"{i}. {ts_from} → {ts_to} (similarity: {sim:.0%}): {summary}")

        prompt = f"""Based on these significant changes detected in {url}, write a brief investigative narrative (2-3 sentences) summarizing how the page evolved over time and what this might indicate:

{chr(10).join(changes_summary)}

Focus on patterns, trends, or red flags an investigator should note."""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an investigative analyst. Write concise, factual summaries."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"_generate_change_narrative failed: {e}")
            return f"Detected {len(significant_changes)} significant changes across {len(versions)} versions."

    async def quick_change_detection(
        self,
        url: str,
        threshold: float = 0.85
    ) -> Dict[str, Any]:
        """
        Fast change detection - just identifies WHERE changes occurred.

        No AI analysis, just similarity scores. Use for quick scans before deep analysis.
        """
        await self.initialize()

        if not self.es_client:
            return {"error": "Elasticsearch unavailable"}

        versions = await self.get_url_versions(url, include_embeddings=True)

        if len(versions) < 2:
            return {
                "url": url,
                "total_versions": len(versions),
                "change_points": [],
                "has_significant_changes": False,
            }

        change_points = []

        for i in range(1, len(versions)):
            v_prev = versions[i - 1]
            v_curr = versions[i]

            emb_prev = v_prev.get("embedding")
            emb_curr = v_curr.get("embedding")

            similarity = await self._compute_similarity(emb_prev, emb_curr)

            if similarity is not None and similarity < threshold:
                change_points.append({
                    "index": i,
                    "from_timestamp": v_prev.get("timestamp"),
                    "to_timestamp": v_curr.get("timestamp"),
                    "similarity": round(similarity, 4),
                    "severity": "major" if similarity < 0.70 else "moderate",
                })

        return {
            "url": url,
            "total_versions": len(versions),
            "change_points": change_points,
            "has_significant_changes": len(change_points) > 0,
        }

    async def close(self):
        """Close clients."""
        if self.es_client:
            await self.es_client.close()
        if self.openai_client:
            await self.openai_client.close()


# Singleton instance
_embedder = None

def get_domain_embedder() -> DomainEmbedder:
    """Get or create singleton embedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = DomainEmbedder()
    return _embedder


async def embed_scraped_content(
    domain: str,
    url: str,
    content: str,
    source: str = "unknown",
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience function for embedding scraped content.

    Call this after any scrape operation (CC, Wayback, Firecrawl).
    """
    embedder = get_domain_embedder()
    return await embedder.embed_content(domain, url, content, source, timestamp)


async def search_domain_content(
    domain: str,
    query: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Convenience function for searching domain content.

    Use in RAG pipelines for domain-scoped Q&A.
    """
    embedder = get_domain_embedder()
    return await embedder.search(domain, query, limit)
