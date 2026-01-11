"""
WHOIS resource metadata for ALLDOM.

Entity-centric: Returns domain, person, company, email, address entities.
Operations (current/history/reverse/cluster) are modes, not output types.
"""

from .base import ResourceMetadata, StaticCapabilityResource, EntityCodes


class WhoisResource(StaticCapabilityResource):
    """
    Native WHOIS capabilities via WhoisXML API.

    HAVE (accepts):
        - email (1): Reverse WHOIS by registrant email
        - domain (6): Current/historical WHOIS lookup
        - company_name (13): Reverse WHOIS by registrant org

    GET (provides):
        - domain (6): Domain records, related domains
        - person (7): Registrant names
        - company_name (13): Registrant organizations
        - email (1): Contact emails
        - address (11): Registrant addresses

    Operations:
        - current: Get current WHOIS record
        - history: Get historical WHOIS records
        - reverse: Find domains by email/registrant/org
        - cluster: Find related domains by registrant
    """

    metadata = ResourceMetadata(
        name="whois",
        accepts=[
            EntityCodes.EMAIL,        # 1 - Reverse WHOIS by email
            EntityCodes.DOMAIN,       # 6 - Domain lookup
            EntityCodes.COMPANY_NAME, # 13 - Reverse WHOIS by org
        ],
        provides=[
            EntityCodes.DOMAIN,       # 6 - Domain records
            EntityCodes.PERSON,       # 7 - Registrant names
            EntityCodes.COMPANY_NAME, # 13 - Registrant orgs
            EntityCodes.EMAIL,        # 1 - Contact emails
            EntityCodes.ADDRESS,      # 11 - Registrant addresses
        ],
        description="WHOIS lookup, history, reverse search, and domain clustering via WhoisXML API.",
        operations=["current", "history", "reverse", "cluster"],
        default_operation="current",
        friction="Paywalled",
    )
