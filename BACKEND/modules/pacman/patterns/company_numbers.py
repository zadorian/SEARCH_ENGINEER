"""
PACMAN Patterns - Company Registration Numbers by Jurisdiction
25+ countries with validated patterns
"""

import re

# === UNITED KINGDOM ===
UK_CRN = re.compile(r'\b(?:CRN|Company\s*(?:No|Number|Reg(?:istration)?)|Registered\s*(?:No|Number))[:\s]*([A-Z]{0,2}\d{6,8})\b', re.I)

# === GERMANY ===
DE_HRB = re.compile(r'\b(HR[AB])\s*(\d{4,6})\b', re.I)

# === FRANCE ===
FR_SIREN = re.compile(r'\b(?:SIREN|SIRET)[:\s]*(\d{9}(?:\d{5})?)\b', re.I)
FR_RCS = re.compile(r'\bRCS[:\s]*([A-Z]+)\s*(\d{9})\b', re.I)

# === NETHERLANDS ===
NL_KVK = re.compile(r'\b(?:KVK|KvK|Kvk)[:\s]*(\d{8})\b', re.I)

# === BELGIUM ===
BE_BCE = re.compile(r'\b(?:BCE|KBO|BTW|TVA)[:\s]*(?:BE)?[\s]?(\d{4}[\.\s]?\d{3}[\.\s]?\d{3})\b', re.I)

# === SPAIN ===
ES_CIF = re.compile(r'\b(?:CIF|NIF)[:\s]*([A-Z]\d{7}[A-Z0-9])\b', re.I)

# === ITALY ===
IT_PIVA = re.compile(r'\b(?:P\.?\s*IVA|Partita\s*IVA)[:\s]*(?:IT)?(\d{11})\b', re.I)
IT_REA = re.compile(r'\b(?:REA|C\.C\.I\.A\.A\.)[:\s]*([A-Z]{2})[:\s-]*(\d{5,7})\b', re.I)
IT_CF = re.compile(r'\b(?:Codice\s*Fiscale|C\.F\.)[:\s]*([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b', re.I)

# === AUSTRIA ===
AT_FN = re.compile(r'\b(?:FN|Firmenbuch)[:\s]*(\d{5,6}[a-z]?)\b', re.I)

# === SWITZERLAND ===
CH_UID = re.compile(r'\b(?:UID|CHE)[:\s-]*(\d{3}[\.\s]?\d{3}[\.\s]?\d{3})\b', re.I)

# === POLAND ===
PL_KRS = re.compile(r'\b(?:KRS)[:\s]*(\d{10})\b', re.I)
PL_NIP = re.compile(r'\b(?:NIP)[:\s]*(\d{3}[-\s]?\d{3}[-\s]?\d{2}[-\s]?\d{2})\b', re.I)
PL_REGON = re.compile(r'\b(?:REGON)[:\s]*(\d{9}(?:\d{5})?)\b', re.I)

# === CZECH REPUBLIC ===
CZ_ICO = re.compile(r'\b(?:IČO?|ICO)[:\s]*(\d{8})\b', re.I)

# === HUNGARY ===
HU_CEGJSZ = re.compile(r'\b(?:Cg\.|Cégjegyzék)[:\s]*(\d{2}-\d{2}-\d{6})\b', re.I)

# === CROATIA ===
HR_OIB = re.compile(r'\b(?:OIB)[:\s]*(\d{11})\b', re.I)
HR_MBS = re.compile(r'\b(?:MBS)[:\s]*(\d{11})\b', re.I)

# === SLOVENIA ===
SI_MAT = re.compile(r'\b(?:matična\s*št|mat\.?\s*št)[:\s]*(\d{7,10})\b', re.I)

# === ROMANIA ===
RO_CUI = re.compile(r'\b(?:CUI|CIF|Cod\s*fiscal)[:\s]*(?:RO)?(\d{2,10})\b', re.I)

# === BULGARIA ===
BG_EIK = re.compile(r'\b(?:EIK|BULSTAT|ЕИК)[:\s]*(\d{9,13})\b', re.I)

# === NORWAY ===
NO_ORGNR = re.compile(r'\b(?:Org\.?\s*nr\.?|organisasjonsnummer)[:\s]*(\d{9})\b', re.I)

# === SWEDEN ===
SE_ORGNR = re.compile(r'\b(?:Org\.?\s*nr\.?|organisationsnummer)[:\s]*(\d{6}-?\d{4})\b', re.I)

# === DENMARK ===
DK_CVR = re.compile(r'\b(?:CVR)[:\s]*(\d{8})\b', re.I)

# === FINLAND ===
FI_YTUNNUS = re.compile(r'\b(?:Y-tunnus|FI)[:\s]*(\d{7}-?\d)\b', re.I)

# === PORTUGAL ===
PT_NIPC = re.compile(r'\b(?:NIPC|NIF)[:\s]*(\d{9})\b', re.I)

# === GREECE ===
GR_GEMI = re.compile(r'\b(?:ΓΕΜΗ|GEMI|ΑΦΜ)[:\s]*(\d{9,12})\b', re.I)

# === IRELAND ===
IE_CRO = re.compile(r'\b(?:CRO|Company\s*Number)[:\s]*(\d{5,6})\b', re.I)

# === LUXEMBOURG ===
LU_RCS = re.compile(r'\bRCS[:\s]*(B\d{5,6})\b', re.I)

# === CYPRUS ===
CY_HE = re.compile(r'\b(?:HE|ΗΕ)[:\s]*(\d{5,6})\b', re.I)

# === MALTA ===
MT_CRN = re.compile(r'\b(?:C\s*)?(\d{5})\b', re.I)

# === JERSEY/GUERNSEY/ISLE OF MAN ===
JE_CRN = re.compile(r'\b(?:Jersey|JE)[:\s]*(\d{5,6})\b', re.I)
GG_CRN = re.compile(r'\b(?:Guernsey)[:\s]*(\d{5,6})\b', re.I)
IM_CRN = re.compile(r'\b(?:Isle of Man)[:\s]*(\d{6})\b', re.I)

# === UNITED STATES ===
US_EIN = re.compile(r'\b(?:EIN|Tax\s*ID)[:\s]*(\d{2}-?\d{7})\b', re.I)
US_CIK = re.compile(r'\b(?:CIK)[:\s]*(\d{10})\b', re.I)


# All patterns grouped by region
EUROPE_PATTERNS = {
    'UK_CRN': UK_CRN, 'DE_HRB': DE_HRB, 'FR_SIREN': FR_SIREN, 'FR_RCS': FR_RCS,
    'NL_KVK': NL_KVK, 'BE_BCE': BE_BCE, 'ES_CIF': ES_CIF, 'IT_PIVA': IT_PIVA,
    'IT_REA': IT_REA, 'IT_CF': IT_CF, 'AT_FN': AT_FN, 'CH_UID': CH_UID,
    'PL_KRS': PL_KRS, 'PL_NIP': PL_NIP, 'PL_REGON': PL_REGON, 'CZ_ICO': CZ_ICO,
    'HU_CEGJSZ': HU_CEGJSZ, 'HR_OIB': HR_OIB, 'HR_MBS': HR_MBS, 'SI_MAT': SI_MAT,
    'RO_CUI': RO_CUI, 'BG_EIK': BG_EIK, 'NO_ORGNR': NO_ORGNR, 'SE_ORGNR': SE_ORGNR,
    'DK_CVR': DK_CVR, 'FI_YTUNNUS': FI_YTUNNUS, 'PT_NIPC': PT_NIPC, 'GR_GEMI': GR_GEMI,
    'IE_CRO': IE_CRO, 'LU_RCS': LU_RCS, 'CY_HE': CY_HE, 'MT_CRN': MT_CRN,
    'JE_CRN': JE_CRN, 'GG_CRN': GG_CRN, 'IM_CRN': IM_CRN,
}

US_PATTERNS = {
    'US_EIN': US_EIN, 'US_CIK': US_CIK,
}

ALL_COMPANY_NUMBERS = {**EUROPE_PATTERNS, **US_PATTERNS}
