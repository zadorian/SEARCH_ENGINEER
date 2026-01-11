import os
import requests
import json

class RocketReachClient:
    """
    RocketReach API Client
    Documentation: https://rocketreach.co/api
    """
    
    BASE_URL = "https://api.rocketreach.co/v2"
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("ROCKETREACH_API_KEY")
        if not self.api_key:
            print("Warning: ROCKETREACH_API_KEY not found.")

    def _get_headers(self):
        return {
            "Api-Key": self.api_key,
            "Content-Type": "application/json"
        }

    def lookup_email(self, email: str):
        """Lookup person by email"""
        if not self.api_key: return None
        
        try:
            # Using the Lookup Profile endpoint
            response = requests.get(
                f"{self.BASE_URL}/person/lookup",
                params={"email": email},
                headers=self._get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return self._normalize_profile(data)
            return None
        except Exception as e:
            print(f"RocketReach lookup_email error: {e}")
            return None

    def lookup_linkedin(self, linkedin_url: str):
        """Lookup person by LinkedIn URL"""
        if not self.api_key: return None
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/person/lookup",
                params={"li_url": linkedin_url},
                headers=self._get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return self._normalize_profile(data)
            return None
        except Exception as e:
            print(f"RocketReach lookup_linkedin error: {e}")
            return None

    def search(self, name: str, company: str = None):
        """Search person by name and optional company"""
        if not self.api_key: return None
        
        try:
            query = {"name": name}
            if company:
                query["current_employer"] = company
                
            response = requests.post(
                f"{self.BASE_URL}/person/search",
                json={"query": query},
                headers=self._get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                profiles = data.get("profiles", [])
                return [self._normalize_profile(p) for p in profiles]
            return None
        except Exception as e:
            print(f"RocketReach search error: {e}")
            return None

    def _normalize_profile(self, data):
        """Normalize RocketReach data to standard format"""
        if not data: return None
        return {
            "name": data.get("name"),
            "current_title": data.get("current_title"),
            "current_employer": data.get("current_employer"),
            "location": data.get("location"),
            "linkedin_url": data.get("linkedin_url"),
            "emails": [e.get("email") for e in data.get("emails", [])],
            "phones": [p.get("number") for p in data.get("phones", [])],
            "profile_pic": data.get("profile_pic"),
            "source_raw": data
        }
