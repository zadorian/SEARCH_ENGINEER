"""
PACMAN Patterns - Cryptocurrency Addresses
"""

import re

# Bitcoin (Legacy P2PKH and P2SH)
BTC_LEGACY = re.compile(r'\b([13][a-km-zA-HJ-NP-Z1-9]{25,34})\b')

# Bitcoin Bech32 (SegWit)
BTC_BECH32 = re.compile(r'\b(bc1[a-z0-9]{39,59})\b')

# Ethereum
ETH = re.compile(r'\b(0x[a-fA-F0-9]{40})\b')

# Litecoin
LTC = re.compile(r'\b([LM3][a-km-zA-HJ-NP-Z1-9]{26,33})\b')

# Ripple (XRP)
XRP = re.compile(r'\b(r[0-9a-zA-Z]{24,34})\b')

# Monero
XMR = re.compile(r'\b(4[0-9AB][1-9A-HJ-NP-Za-km-z]{93})\b')


ALL_CRYPTO = {
    'BTC': BTC_LEGACY,
    'BTC_BECH32': BTC_BECH32,
    'ETH': ETH,
    'LTC': LTC,
    'XRP': XRP,
    'XMR': XMR,
}
