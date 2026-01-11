#!/usr/bin/env python3
"""
COMPANY DESIGNATORS - Legal Entity Type Keywords by Jurisdiction

Used by entity_harvester.py to search news sources for company mentions.

These are the company type designators that MUST appear with company names
in legal/official contexts (e.g., "Siemens AG", "Podravka d.d.").

EU27 + UK jurisdictions covered.
"""

from typing import Dict, List, Set

# ============================================================================
# DESIGNATORS BY JURISDICTION
# ============================================================================

DESIGNATORS: Dict[str, List[str]] = {
    # -------------------------------------------------------------------------
    # WESTERN EUROPE
    # -------------------------------------------------------------------------
    "DE": [  # Germany
        "GmbH",              # Gesellschaft mit beschränkter Haftung
        "AG",                # Aktiengesellschaft
        "KG",                # Kommanditgesellschaft
        "OHG",               # Offene Handelsgesellschaft
        "e.K.",              # Eingetragener Kaufmann
        "e.V.",              # Eingetragener Verein
        "GmbH & Co. KG",     # Common hybrid
        "UG",                # Unternehmergesellschaft
        "SE",                # Societas Europaea
        "KGaA",              # Kommanditgesellschaft auf Aktien
    ],
    "AT": [  # Austria
        "GmbH",
        "AG",
        "KG",
        "OG",                # Offene Gesellschaft
        "e.U.",              # Eingetragenes Unternehmen
        "Gen.m.b.H.",        # Genossenschaft
        "Privatstiftung",    # Private foundation
    ],
    "CH": [  # Switzerland (included for DACH region)
        "AG",
        "GmbH",
        "SA",                # Société Anonyme (French)
        "Sarl",              # Société à responsabilité limitée
        "Sàrl",
    ],
    "FR": [  # France
        "SA",                # Société Anonyme
        "SARL",              # Société à responsabilité limitée
        "SAS",               # Société par actions simplifiée
        "EURL",              # Entreprise unipersonnelle
        "SNC",               # Société en nom collectif
        "SASU",              # SAS unipersonnelle
        "SCA",               # Société en commandite par actions
        "SCI",               # Société civile immobilière
    ],
    "BE": [  # Belgium
        "NV",                # Naamloze vennootschap
        "BV",                # Besloten vennootschap
        "BVBA",              # (old form)
        "SA",                # Société Anonyme (French)
        "SRL",               # Société à responsabilité limitée
        "SPRL",              # (old form)
        "SC",                # Société coopérative
        "SComm",             # Société en commandite
    ],
    "NL": [  # Netherlands
        "B.V.",              # Besloten Vennootschap
        "BV",
        "N.V.",              # Naamloze Vennootschap
        "NV",
        "V.O.F.",            # Vennootschap onder firma
        "C.V.",              # Commanditaire vennootschap
        "Coöperatie",
    ],
    "LU": [  # Luxembourg
        "SA",
        "Sàrl",
        "SCS",               # Société en commandite simple
        "SCA",               # Société en commandite par actions
        "SE",                # Societas Europaea
        "SICAV",             # Collective investment
    ],

    # -------------------------------------------------------------------------
    # SOUTHERN EUROPE
    # -------------------------------------------------------------------------
    "IT": [  # Italy
        "S.p.A.",            # Società per Azioni
        "SpA",
        "S.r.l.",            # Società a responsabilità limitata
        "Srl",
        "S.a.s.",            # Società in accomandita semplice
        "S.n.c.",            # Società in nome collettivo
        "S.a.p.a.",          # Società in accomandita per azioni
        "Società Cooperativa",
    ],
    "ES": [  # Spain
        "S.A.",              # Sociedad Anónima
        "SA",
        "S.L.",              # Sociedad Limitada
        "SL",
        "S.L.U.",            # Sociedad Limitada Unipersonal
        "S.C.",              # Sociedad Cooperativa
        "S.Com.",            # Sociedad Comanditaria
        "S.L.L.",            # Sociedad Limitada Laboral
    ],
    "PT": [  # Portugal
        "SA",                # Sociedade Anónima
        "Lda",               # Limitada
        "Lda.",
        "SGPS",              # Holding company
        "S.A.",
        "Unipessoal",
    ],
    "GR": [  # Greece
        "Α.Ε.",              # Ανώνυμη Εταιρεία
        "AE",
        "Ε.Π.Ε.",            # Εταιρεία Περιορισμένης Ευθύνης
        "EPE",
        "Ο.Ε.",              # Ομόρρυθμη Εταιρεία
        "Ε.Ε.",              # Ετερόρρυθμη Εταιρεία
        "Ι.Κ.Ε.",            # Ιδιωτική Κεφαλαιουχική Εταιρεία
    ],
    "MT": [  # Malta
        "Ltd",
        "Limited",
        "p.l.c.",
        "PLC",
    ],
    "CY": [  # Cyprus
        "Ltd",
        "Limited",
        "PLC",
        "Λτδ",               # Greek form
    ],

    # -------------------------------------------------------------------------
    # NORTHERN EUROPE
    # -------------------------------------------------------------------------
    "UK": [  # United Kingdom
        "Ltd",
        "Limited",
        "PLC",
        "Plc",
        "LLP",               # Limited Liability Partnership
        "LP",                # Limited Partnership
        "CIC",               # Community Interest Company
        "Inc",               # Occasionally used
    ],
    "IE": [  # Ireland
        "Ltd",
        "Limited",
        "PLC",
        "Plc",
        "DAC",               # Designated Activity Company
        "CLG",               # Company Limited by Guarantee
        "UC",                # Unlimited Company
        "Teoranta",          # Irish for Limited
    ],
    "DK": [  # Denmark
        "A/S",               # Aktieselskab
        "ApS",               # Anpartsselskab
        "I/S",               # Interessentskab
        "K/S",               # Kommanditselskab
        "P/S",               # Partnerselskab
    ],
    "SE": [  # Sweden
        "AB",                # Aktiebolag
        "HB",                # Handelsbolag
        "KB",                # Kommanditbolag
        "Ek. för.",          # Ekonomisk förening
    ],
    "FI": [  # Finland
        "Oy",                # Osakeyhtiö
        "Oyj",               # Julkinen osakeyhtiö (public)
        "Osk",               # Osuuskunta (cooperative)
        "Ky",                # Kommandiittiyhtiö
        "Ay",                # Avoin yhtiö
    ],
    "NO": [  # Norway (EEA, included)
        "AS",                # Aksjeselskap
        "ASA",               # Allmennaksjeselskap
        "ANS",               # Ansvarlig selskap
        "DA",                # Delt ansvar
        "KS",                # Kommandittselskap
    ],

    # -------------------------------------------------------------------------
    # CENTRAL/EASTERN EUROPE
    # -------------------------------------------------------------------------
    "PL": [  # Poland
        "Sp. z o.o.",        # Spółka z ograniczoną odpowiedzialnością
        "sp. z o.o.",
        "S.A.",              # Spółka Akcyjna
        "SA",
        "S.K.A.",            # Spółka Komandytowo-Akcyjna
        "Sp.k.",             # Spółka komandytowa
        "Sp.j.",             # Spółka jawna
    ],
    "CZ": [  # Czech Republic
        "s.r.o.",            # Společnost s ručením omezeným
        "spol. s r.o.",
        "a.s.",              # Akciová společnost
        "k.s.",              # Komanditní společnost
        "v.o.s.",            # Veřejná obchodní společnost
    ],
    "SK": [  # Slovakia
        "s.r.o.",
        "spol. s r.o.",
        "a.s.",
        "k.s.",
        "v.o.s.",
    ],
    "HU": [  # Hungary
        "Kft.",              # Korlátolt felelősségű társaság
        "Kft",
        "Zrt.",              # Zártkörűen működő részvénytársaság
        "Zrt",
        "Nyrt.",             # Nyilvánosan működő részvénytársaság
        "Bt.",               # Betéti társaság
        "Kkt.",              # Közkereseti társaság
    ],
    "RO": [  # Romania
        "S.R.L.",            # Societate cu răspundere limitată
        "SRL",
        "S.A.",              # Societate pe acțiuni
        "SA",
        "S.C.A.",            # Societate în comandită pe acțiuni
        "S.N.C.",            # Societate în nume colectiv
    ],
    "BG": [  # Bulgaria
        "ООД",               # Дружество с ограничена отговорност
        "OOD",
        "ЕООД",              # Едноличен ООД
        "EOOD",
        "АД",                # Акционерно дружество
        "AD",
        "ЕАД",               # Едноличен АД
        "EAD",
        "КД",                # Командитно дружество
    ],
    "HR": [  # Croatia
        "d.o.o.",            # Društvo s ograničenom odgovornošću
        "d.d.",              # Dioničko društvo
        "j.d.o.o.",          # Jednostavno d.o.o.
        "k.d.",              # Komanditno društvo
    ],
    "SI": [  # Slovenia
        "d.o.o.",
        "d.d.",
        "k.d.",
        "d.n.o.",            # Družba z neomejeno odgovornostjo
    ],

    # -------------------------------------------------------------------------
    # BALTIC STATES
    # -------------------------------------------------------------------------
    "EE": [  # Estonia
        "OÜ",                # Osaühing
        "AS",                # Aktsiaselts
        "TÜ",                # Täisühing
        "UÜ",                # Usaldusühing
    ],
    "LV": [  # Latvia
        "SIA",               # Sabiedrība ar ierobežotu atbildību
        "AS",                # Akciju sabiedrība
        "PS",                # Pilnsabiedrība
        "KS",                # Komandītsabiedrība
    ],
    "LT": [  # Lithuania
        "UAB",               # Uždaroji akcinė bendrovė
        "AB",                # Akcinė bendrovė
        "IĮ",                # Individuali įmonė
        "MB",                # Mažoji bendrija
        "TŪB",               # Tikroji ūkinė bendrija
    ],

    # -------------------------------------------------------------------------
    # OTHER EU MEMBERS
    # -------------------------------------------------------------------------
    "RS": [  # Serbia (candidate)
        "d.o.o.",
        "a.d.",              # Akcionarsko društvo
    ],
}

# Always include international company forms across jurisdictions.
ALWAYS_DESIGNATORS: List[str] = [
    "Ltd",
    "Ltd.",
    "Limited",
    "Inc",
    "Inc.",
    "Incorporated",
    "AG",
    "A.G.",
    "SA",
    "S.A.",
    "SAS",
    "S.A.S.",
    "LLP",
    "L.L.P.",
    "LLC",
    "L.L.C.",
]

# EU27 + UK jurisdiction codes
EU27_UK = [
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
    "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
    "PL", "PT", "RO", "SK", "SI", "ES", "SE", "UK"
]

# DACH region (German-speaking)
DACH = ["DE", "AT", "CH"]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _merge_designators(base: List[str]) -> List[str]:
    merged: List[str] = []
    seen = set()
    for d in base + ALWAYS_DESIGNATORS:
        if d in seen:
            continue
        merged.append(d)
        seen.add(d)
    return merged


def get_designators(jurisdiction: str) -> List[str]:
    """Get designators for a jurisdiction."""
    jur = jurisdiction.upper()
    if jur == "GB":
        jur = "UK"
    return _merge_designators(DESIGNATORS.get(jur, []))


def get_all_eu_designators() -> Dict[str, List[str]]:
    """Get all designators for EU27 + UK."""
    return {jur: get_designators(jur) for jur in EU27_UK if jur in DESIGNATORS}


def get_unique_designators() -> Set[str]:
    """Get all unique designators across all jurisdictions."""
    unique = set(ALWAYS_DESIGNATORS)
    for designators in DESIGNATORS.values():
        unique.update(designators)
    return unique


def get_designator_to_jurisdictions() -> Dict[str, List[str]]:
    """Map designators to their jurisdictions (for disambiguation)."""
    mapping = {}
    for jur in DESIGNATORS.keys():
        for d in get_designators(jur):
            if d not in mapping:
                mapping[d] = []
            mapping[d].append(jur)
    return mapping


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        jur = sys.argv[1].upper()
        designators = get_designators(jur)
        if designators:
            print(f"{jur}: {', '.join(designators)}")
        else:
            print(f"No designators for {jur}")
    else:
        print(f"EU27 + UK Jurisdictions: {len(EU27_UK)}")
        print(f"Total unique designators: {len(get_unique_designators())}")
        print()
        for jur in sorted(EU27_UK):
            d = get_designators(jur)
            print(f"  {jur}: {len(d)} designators - {', '.join(d[:5])}{'...' if len(d) > 5 else ''}")
