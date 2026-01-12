# ALLDOM Output Handlers
"""
Output handlers for ALLDOM - transform raw data into graph nodes.

Each handler has:
- _code: Legend code from codes.json (set on output nodes)
- process(value, context, raw_data): Creates and saves graph node
- _save(node): Saves to disk + Elasticsearch

Entity types produced:
- domain_url (_code=6): Domain entities
- ip_address (_code=8): IP entities
- dns_record (_code=193): DNS records
- email (_code=1): Email entities
- phone (_code=2): Phone entities
- person (_code=7): Person entities
- company (_code=13): Company entities
- address (_code=20): Address entities
"""

from .domain_url import DomainUrlOutputHandler
from .ip_address import IpAddressOutputHandler
from .dns_record import DnsRecordOutputHandler
from .email import EmailOutputHandler
from .phone import PhoneOutputHandler
from .person_name import PersonNameOutputHandler
from .company_name import CompanyNameOutputHandler
from .address import AddressOutputHandler

__all__ = [
    'DomainUrlOutputHandler',
    'IpAddressOutputHandler',
    'DnsRecordOutputHandler',
    'EmailOutputHandler',
    'PhoneOutputHandler',
    'PersonNameOutputHandler',
    'CompanyNameOutputHandler',
    'AddressOutputHandler',
]
