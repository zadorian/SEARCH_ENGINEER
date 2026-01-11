"""
Legend #8: ip_address input model for ALLDOM.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
import re


IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
    r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
)

IPV6_RE = re.compile(
    r"^(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|"
    r"^(?:[0-9a-fA-F]{1,4}:){1,7}:$|"
    r"^(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}$|"
    r"^(?:[0-9a-fA-F]{1,4}:){1,5}(?::[0-9a-fA-F]{1,4}){1,2}$|"
    r"^(?:[0-9a-fA-F]{1,4}:){1,4}(?::[0-9a-fA-F]{1,4}){1,3}$|"
    r"^(?:[0-9a-fA-F]{1,4}:){1,3}(?::[0-9a-fA-F]{1,4}){1,4}$|"
    r"^(?:[0-9a-fA-F]{1,4}:){1,2}(?::[0-9a-fA-F]{1,4}){1,5}$|"
    r"^[0-9a-fA-F]{1,4}:(?::[0-9a-fA-F]{1,4}){1,6}$|"
    r"^:(?::[0-9a-fA-F]{1,4}){1,7}$|"
    r"^::$"
)


@dataclass
class IpAddressInput:
    """
    Legend #8: ip_address
    Routes to reverse DNS, geolocation, ASN lookup, and linked domain discovery.
    """

    ip_address: str
    reverse_dns: bool = True
    geolocation: bool = True
    asn_lookup: bool = True
    find_linked_domains: bool = False
    include_history: bool = False
    tags: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> bool:
        ip = self.ip_address.strip()
        return bool(IPV4_RE.match(ip) or IPV6_RE.match(ip))

    def ip_version(self) -> int:
        """Return 4 for IPv4, 6 for IPv6, 0 if invalid."""
        ip = self.ip_address.strip()
        if IPV4_RE.match(ip):
            return 4
        elif IPV6_RE.match(ip):
            return 6
        return 0

    def is_private(self) -> bool:
        """Check if IP is in private/reserved range."""
        ip = self.ip_address.strip()
        if self.ip_version() != 4:
            return False
        
        octets = [int(o) for o in ip.split(".")]
        
        # 10.0.0.0/8
        if octets[0] == 10:
            return True
        # 172.16.0.0/12
        if octets[0] == 172 and 16 <= octets[1] <= 31:
            return True
        # 192.168.0.0/16
        if octets[0] == 192 and octets[1] == 168:
            return True
        # 127.0.0.0/8 (loopback)
        if octets[0] == 127:
            return True
        
        return False

    def to_dict(self) -> Dict[str, object]:
        return {
            "legend": 8,
            "input_type": "ip_address",
            "ip_address": self.ip_address.strip(),
            "version": self.ip_version(),
            "is_private": self.is_private(),
            "reverse_dns": self.reverse_dns,
            "geolocation": self.geolocation,
            "asn_lookup": self.asn_lookup,
            "find_linked_domains": self.find_linked_domains,
            "include_history": self.include_history,
            "tags": self.tags,
        }
