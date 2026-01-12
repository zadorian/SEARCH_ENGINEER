"""
PACMAN Patterns - Global Identifiers
LEI, IBAN, VAT, IMO, etc.
"""

import re

# Legal Entity Identifier (20 characters)
LEI = re.compile(r'\b[A-Z0-9]{4}00[A-Z0-9]{12}\d{2}\b')

# International Bank Account Number
IBAN = re.compile(r'\b([A-Z]{2}\d{2}[A-Z0-9]{4,30})\b')

# SWIFT/BIC Code
SWIFT = re.compile(r'\b([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b')

# VAT Numbers (EU generic)
VAT = re.compile(r'\b(?:VAT|TVA|BTW|MwSt|IVA|USt)[:\s]*([A-Z]{2}\d{8,12})\b', re.I)

# IMO Number (vessel)
IMO = re.compile(r'\bIMO[:\s]*(\d{7})\b', re.I)

# MMSI (vessel)
MMSI = re.compile(r'\bMMSI[:\s]*(\d{9})\b', re.I)

# ISIN (securities)
ISIN = re.compile(r'\b([A-Z]{2}[A-Z0-9]{9}\d)\b')

# DUNS Number
DUNS = re.compile(r'\bD-?U-?N-?S[:\s]*(\d{2}-?\d{3}-?\d{4})\b', re.I)


# All patterns for fast iteration
ALL_IDENTIFIERS = {
    'LEI': LEI,
    'IBAN': IBAN,
    'SWIFT': SWIFT,
    'VAT': VAT,
    'IMO': IMO,
    'MMSI': MMSI,
    'ISIN': ISIN,
    'DUNS': DUNS,
}
