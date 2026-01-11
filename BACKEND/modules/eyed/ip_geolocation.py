#!/usr/bin/env python3
"""
IP Geolocation Service
Provides IP geolocation functionality via ip-api.com
"""
import requests
import logging

logger = logging.getLogger(__name__)

class IPGeolocation:
    """IP geolocation service using ip-api.com"""
    
    def __init__(self):
        self.cache = {}
        self.api_base = "http://ip-api.com/json/"
    
    def lookup(self, ip_address: str) -> dict:
        """
        Lookup geolocation for an IP address
        """
        if ip_address in self.cache:
            return self.cache[ip_address]
        
        try:
            # Call ip-api.com (Free tier: 45 req/min, non-commercial)
            response = requests.get(f"{self.api_base}{ip_address}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    result = {
                        "ip": ip_address,
                        "country": data.get("country"),
                        "countryCode": data.get("countryCode"),
                        "region": data.get("regionName"),
                        "city": data.get("city"),
                        "zip": data.get("zip"),
                        "latitude": data.get("lat"),
                        "longitude": data.get("lon"),
                        "timezone": data.get("timezone"),
                        "isp": data.get("isp"),
                        "organization": data.get("org"),
                        "as": data.get("as"),
                        "status": "success",
                        "source": "ip-api.com"
                    }
                    self.cache[ip_address] = result
                    return result
            
            logger.warning(f"IP lookup failed for {ip_address}: {response.text}")
            
        except Exception as e:
            logger.error(f"IP lookup exception for {ip_address}: {str(e)}")
            
        # Fallback/Error response
        result = {
            "ip": ip_address,
            "country": "Unknown",
            "city": "Unknown",
            "latitude": 0.0,
            "longitude": 0.0,
            "status": "error",
            "error": "Lookup failed"
        }
        return result
    
    def reverse_dns(self, ip_address: str) -> list:
        """Get domains hosted on this IP (Placeholder)"""
        # In a real implementation, this would query a Passive DNS database
        return []