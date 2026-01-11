"""
Jurisdiction-Aware Dynamic Actions
Detects company jurisdiction and provides dynamic buttons for:
1. Original registry links (from OpenCorporates)
2. Country-specific DDG bangs (corporate registry category)
3. API-based fetchers where available
4. Dynamic flow-based actions from detected IDs
5. Slot-filling actions for empty fields
"""

from typing import Dict, List, Any, Optional
import re
from utils.dynamic_flow_router import flow_router
from utils.id_decoder import decode_id

class JurisdictionActions:
    """Generate dynamic action buttons based on detected jurisdiction"""

    # Country registry bangs from DDG
    REGISTRY_BANGS = {
        # United States (by state)
        "us_al": {"bang": "!alabama", "name": "Alabama SOS"},
        "us_ak": {"bang": "!alaska", "name": "Alaska Corporations"},
        "us_az": {"bang": "!arizona", "name": "Arizona Corporation Commission"},
        "us_ar": {"bang": "!arkansas", "name": "Arkansas SOS"},
        "us_ca": {"bang": "!california", "name": "California SOS", "api": True},
        "us_co": {"bang": "!colorado", "name": "Colorado SOS"},
        "us_ct": {"bang": "!connecticut", "name": "Connecticut SOS"},
        "us_de": {"bang": "!delaware", "name": "Delaware Division of Corporations", "api": True},
        "us_fl": {"bang": "!florida", "name": "Florida Division of Corporations"},
        "us_ga": {"bang": "!georgia", "name": "Georgia Corporations"},
        "us_hi": {"bang": "!hawaii", "name": "Hawaii BREG"},
        "us_id": {"bang": "!idaho", "name": "Idaho SOS"},
        "us_il": {"bang": "!illinois", "name": "Illinois SOS"},
        "us_in": {"bang": "!indiana", "name": "Indiana SOS"},
        "us_ia": {"bang": "!iowa", "name": "Iowa SOS"},
        "us_ks": {"bang": "!kansas", "name": "Kansas SOS"},
        "us_ky": {"bang": "!kentucky", "name": "Kentucky SOS"},
        "us_la": {"bang": "!louisiana", "name": "Louisiana SOS"},
        "us_me": {"bang": "!maine", "name": "Maine SOS"},
        "us_md": {"bang": "!maryland", "name": "Maryland SDAT"},
        "us_ma": {"bang": "!massachusetts", "name": "Massachusetts SOC"},
        "us_mi": {"bang": "!michigan", "name": "Michigan LARA"},
        "us_mn": {"bang": "!minnesota", "name": "Minnesota SOS"},
        "us_ms": {"bang": "!mississippi", "name": "Mississippi SOS"},
        "us_mo": {"bang": "!missouri", "name": "Missouri SOS"},
        "us_mt": {"bang": "!montana", "name": "Montana SOS"},
        "us_ne": {"bang": "!nebraska", "name": "Nebraska SOS"},
        "us_nv": {"bang": "!nevada", "name": "Nevada SOS", "api": True},
        "us_nh": {"bang": "!newhampshire", "name": "New Hampshire SOS"},
        "us_nj": {"bang": "!newjersey", "name": "New Jersey Division of Revenue"},
        "us_nm": {"bang": "!newmexico", "name": "New Mexico SOS"},
        "us_ny": {"bang": "!newyork", "name": "New York DOS"},
        "us_nc": {"bang": "!northcarolina", "name": "North Carolina SOS"},
        "us_nd": {"bang": "!northdakota", "name": "North Dakota SOS"},
        "us_oh": {"bang": "!ohio", "name": "Ohio SOS"},
        "us_ok": {"bang": "!oklahoma", "name": "Oklahoma SOS"},
        "us_or": {"bang": "!oregon", "name": "Oregon SOS"},
        "us_pa": {"bang": "!pennsylvania", "name": "Pennsylvania DOS"},
        "us_ri": {"bang": "!rhodeisland", "name": "Rhode Island SOS"},
        "us_sc": {"bang": "!southcarolina", "name": "South Carolina SOS"},
        "us_sd": {"bang": "!southdakota", "name": "South Dakota SOS"},
        "us_tn": {"bang": "!tennessee", "name": "Tennessee SOS"},
        "us_tx": {"bang": "!texas", "name": "Texas SOS"},
        "us_ut": {"bang": "!utah", "name": "Utah Division of Corporations"},
        "us_vt": {"bang": "!vermont", "name": "Vermont SOS"},
        "us_va": {"bang": "!virginia", "name": "Virginia SCC"},
        "us_wa": {"bang": "!washington", "name": "Washington SOS"},
        "us_wv": {"bang": "!westvirginia", "name": "West Virginia SOS"},
        "us_wi": {"bang": "!wisconsin", "name": "Wisconsin DFI"},
        "us_wy": {"bang": "!wyoming", "name": "Wyoming SOS"},

        # UK
        "gb": {"bang": "!companieshouse", "name": "UK Companies House", "api": True},

        # Europe
        "de": {"bang": "!handelsregister", "name": "German Handelsregister"},
        "fr": {"bang": "!infogreffe", "name": "French Infogreffe"},
        "nl": {"bang": "!kvk", "name": "Netherlands KVK"},
        "be": {"bang": "!kbo", "name": "Belgium KBO"},
        "es": {"bang": "!rmc", "name": "Spanish Registro Mercantil"},
        "it": {"bang": "!registroimprese", "name": "Italian Registro Imprese"},
        "ch": {"bang": "!zefix", "name": "Swiss Zefix"},
        "at": {"bang": "!firmenbuch", "name": "Austrian Firmenbuch"},
        "pl": {"bang": "!krs", "name": "Polish KRS"},
        "se": {"bang": "!bolagsverket", "name": "Swedish Bolagsverket"},
        "dk": {"bang": "!cvr", "name": "Danish CVR"},
        "no": {"bang": "!brreg", "name": "Norwegian Brønnøysundregistrene"},
        "fi": {"bang": "!ytj", "name": "Finnish YTJ"},

        # Asia Pacific
        "au": {"bang": "!asic", "name": "Australian ASIC"},
        "nz": {"bang": "!companiesoffice", "name": "NZ Companies Office"},
        "sg": {"bang": "!acra", "name": "Singapore ACRA"},
        "hk": {"bang": "!icris", "name": "Hong Kong ICRIS"},
        "jp": {"bang": "!houjin", "name": "Japanese Corporate Number"},
        "kr": {"bang": "!dart", "name": "Korean DART"},
        "in": {"bang": "!mca", "name": "Indian MCA"},

        # Americas
        "ca": {"bang": "!corporationscanada", "name": "Corporations Canada"},
        "mx": {"bang": "!rpc", "name": "Mexican RPC"},
        "br": {"bang": "!cnpj", "name": "Brazilian CNPJ"},

        # Other
        "za": {"bang": "!cipc", "name": "South African CIPC"},
        "ae": {"bang": "!moec", "name": "UAE Ministry of Economy"},
    }

    def __init__(self):
        self.actions = []

    def generate_actions(
        self,
        jurisdiction: str,
        company_name: str,
        company_number: Optional[str] = None,
        opencorporates_url: Optional[str] = None,
        registry_url: Optional[str] = None,
        entity_data: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate dynamic action buttons for a jurisdiction

        Args:
            jurisdiction: ISO jurisdiction code (e.g., "us_ca", "gb")
            company_name: Company name for search
            company_number: Official company number if available
            opencorporates_url: OpenCorporates URL (contains link to registry)
            registry_url: Direct registry URL if available

        Returns:
            List of action objects:
            [
                {
                    "type": "link" | "fetch" | "search",
                    "label": "🇬🇧 UK Companies House",
                    "url": "https://...",  # for links
                    "action": "fetch_uk_ch",  # for fetch buttons
                    "bang": "!companieshouse",  # for search buttons
                    "has_api": True,  # if we can auto-fetch
                    "description": "Official UK registry with full filings"
                }
            ]
        """
        actions = []

        jurisdiction_lower = jurisdiction.lower()

        # 1. ORIGINAL REGISTRY LINK (from OpenCorporates)
        if registry_url:
            country_name = self._get_country_name(jurisdiction_lower)
            actions.append({
                "type": "link",
                "label": f"🌐 {country_name} Official Registry",
                "url": registry_url,
                "description": "Open official government registry",
                "priority": 1
            })

        # 2. DDG BANG FOR JURISDICTION
        if jurisdiction_lower in self.REGISTRY_BANGS:
            bang_info = self.REGISTRY_BANGS[jurisdiction_lower]
            actions.append({
                "type": "search",
                "label": f"🔍 Search {bang_info['name']}",
                "bang": bang_info['bang'],
                "query": company_name,
                "description": f"Search via DuckDuckGo {bang_info['bang']}",
                "priority": 2
            })

        # 3. API-BASED FETCH (if available)
        api_action = self._get_api_action(jurisdiction_lower, company_name, company_number)
        if api_action:
            actions.append(api_action)

        # 4. OPENCORPORATES LINK
        if opencorporates_url:
            actions.append({
                "type": "link",
                "label": "📊 OpenCorporates Full Profile",
                "url": opencorporates_url,
                "description": "View on OpenCorporates",
                "priority": 4
            })

        # 5. ALEPH SEARCH (always available)
        actions.append({
            "type": "fetch",
            "label": "🔎 OCCRP Aleph Search",
            "action": "fetch_aleph",
            "query": company_name,
            "jurisdiction": jurisdiction,
            "description": "Search investigative database",
            "priority": 5
        })

        # 6. EDGAR (if US company)
        if jurisdiction_lower.startswith("us_"):
            actions.append({
                "type": "fetch",
                "label": "📄 SEC EDGAR Filings",
                "action": "fetch_edgar",
                "query": company_name,
                "description": "Search SEC filings (public companies only)",
                "priority": 3
            })

        # 7. DYNAMIC FLOW-BASED ACTIONS (from detected IDs and empty slots)
        if entity_data:
            flow_actions = self._generate_flow_actions(entity_data, jurisdiction)
            actions.extend(flow_actions)

        return sorted(actions, key=lambda x: x.get("priority", 99))

    def _get_country_name(self, jurisdiction: str) -> str:
        """Get human-readable country/state name"""
        # Map to flag emoji + name
        flags = {
            "gb": "🇬🇧 UK",
            "de": "🇩🇪 Germany",
            "fr": "🇫🇷 France",
            "nl": "🇳🇱 Netherlands",
            "us_ca": "🇺🇸 California",
            "us_de": "🇺🇸 Delaware",
            "us_ny": "🇺🇸 New York",
            "au": "🇦🇺 Australia",
            "sg": "🇸🇬 Singapore",
        }
        return flags.get(jurisdiction, jurisdiction.upper())

    def _get_api_action(
        self,
        jurisdiction: str,
        company_name: str,
        company_number: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Get API-based fetch action if available"""

        # UK Companies House API
        if jurisdiction == "gb" and company_number:
            return {
                "type": "fetch",
                "label": "🇬🇧 Fetch from UK Companies House",
                "action": "fetch_uk_ch",
                "company_number": company_number,
                "has_api": True,
                "description": "Auto-fetch from official UK API",
                "priority": 1
            }

        # US State-specific APIs
        if jurisdiction == "us_ca" and company_number:
            return {
                "type": "fetch",
                "label": "🇺🇸 Fetch from California SOS",
                "action": "fetch_ca_sos",
                "company_number": company_number,
                "has_api": True,
                "description": "Auto-fetch from California API",
                "priority": 1
            }

        if jurisdiction == "us_de" and company_number:
            return {
                "type": "fetch",
                "label": "🇺🇸 Fetch from Delaware Corporations",
                "action": "fetch_de_corp",
                "company_number": company_number,
                "has_api": True,
                "description": "Auto-fetch from Delaware API",
                "priority": 1
            }

        # Add more APIs as needed
        return None

    def _generate_flow_actions(
        self,
        entity_data: Dict[str, Any],
        jurisdiction: str
    ) -> List[Dict[str, Any]]:
        """
        Generate dynamic actions based on detected IDs and empty slots
        Uses the flow router to create bidirectional actions
        """
        actions = []

        # Analyze the entity to find available actions and fillable slots
        flow_analysis = flow_router.analyze_entity(entity_data)

        # 1. AVAILABLE ACTIONS (from detected IDs/inputs)
        for action in flow_analysis.get("available_actions", []):
            # Convert flow router action to our action format
            if action.get("action", "").startswith("fetch_"):
                actions.append({
                    "type": "flow_fetch",
                    "label": f"🔄 {action.get('description', 'Fetch data')}",
                    "action": action["action"],
                    "input_type": action.get("input_type"),
                    "input_value": action.get("value"),
                    "jurisdiction": action.get("jurisdiction"),
                    "decoded_info": action.get("decoded_info", {}),
                    "description": action.get("description"),
                    "priority": 6  # Flow actions have lower priority than direct actions
                })

        # 2. FILLABLE SLOTS (what inputs we need)
        fillable_slots = flow_analysis.get("fillable_slots", [])
        if fillable_slots:
            # Group slots by type for cleaner presentation
            slot_actions = []
            for slot_info in fillable_slots:
                slot_path = slot_info["slot_path"]
                possible_inputs = slot_info["possible_inputs"]

                # Create action for each possible input type that could fill this slot
                for input_option in possible_inputs[:2]:  # Limit to top 2 options
                    slot_actions.append({
                        "type": "slot_fill",
                        "label": f"🔍 Need: {input_option['input_type']}",
                        "slot_path": slot_path,
                        "input_type": input_option["input_type"],
                        "input_format": input_option.get("input_format"),
                        "example": input_option.get("example"),
                        "fetcher": input_option.get("fetcher"),
                        "description": input_option.get("description", f"Fill {slot_path}"),
                        "priority": 7  # Slot fill suggestions have lowest priority
                    })

            actions.extend(slot_actions)

        return actions


# Example usage
if __name__ == "__main__":
    import json

    actions = JurisdictionActions()

    # Test UK company
    print("=" * 80)
    print("UK COMPANY EXAMPLE:")
    print("=" * 80)
    uk_actions = actions.generate_actions(
        jurisdiction="GB",
        company_name="Revolut Ltd",
        company_number="08804411",
        opencorporates_url="https://opencorporates.com/companies/gb/08804411",
        registry_url="https://find-and-update.company-information.service.gov.uk/company/08804411"
    )
    print(json.dumps(uk_actions, indent=2))

    # Test US company
    print("\n" + "=" * 80)
    print("US COMPANY EXAMPLE (California):")
    print("=" * 80)
    us_actions = actions.generate_actions(
        jurisdiction="us_ca",
        company_name="Apple Inc",
        company_number="0806592",
        opencorporates_url="https://opencorporates.com/companies/us_ca/0806592",
        registry_url="https://bizfileonline.sos.ca.gov/search/business"
    )
    print(json.dumps(us_actions, indent=2))
