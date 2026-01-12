"""
PACMAN Patterns - Contact Information
Email, phone numbers
"""

import re

# Email - comprehensive pattern
EMAIL = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', re.I)

# International phone (with country code)
PHONE_INTL = re.compile(r'(?:\+|00)[\d\s\-\(\)]{10,20}')

# Phone patterns by format
PHONE_US = re.compile(r'\b(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b')
PHONE_UK = re.compile(r'\b(?:\+44[\s.-]?)?0?[\d\s.-]{10,12}\b')
PHONE_EU = re.compile(r'\b(?:\+[1-9]\d{0,2})[\s.-]?[\d\s.-]{8,12}\b')


ALL_CONTACTS = {
    'EMAIL': EMAIL,
    'PHONE_INTL': PHONE_INTL,
    'PHONE_US': PHONE_US,
    'PHONE_UK': PHONE_UK,
    'PHONE_EU': PHONE_EU,
}
