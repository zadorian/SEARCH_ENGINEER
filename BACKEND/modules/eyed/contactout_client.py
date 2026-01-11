import os
import requests
import json

class ContactOutClient:
    """
    ContactOut API Client
    Documentation: https://contactout.com/api
    """
    
    BASE_URL = "https://api.contactout.com/v1"
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("CONTACTOUT_API_KEY")
        if not self.api_key:
            print("Warning: CONTACTOUT_API_KEY not found.")

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def enrich_email(self, email: str):
        """Enrich email to find person/profile"""
        if not self.api_key: return None
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/people/enrich",
                params={"email": email},
                headers=self._get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return self._normalize_profile(data.get("person"))
            return None
        except Exception as e:
            print(f"ContactOut enrich_email error: {e}")
            return None

    def enrich_linkedin(self, linkedin_url: str):
        """Enrich LinkedIn profile"""
        if not self.api_key: return None
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/people/enrich",
                params={"profile": linkedin_url},
                headers=self._get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return self._normalize_profile(data.get("person"))
            return None
        except Exception as e:
            print(f"ContactOut enrich_linkedin error: {e}")
            return None

    def _normalize_profile(self, data):
        if not data: return None
        return {
            "name": data.get("fullName"),
            "current_title": data.get("title"),
            "current_employer": data.get("company", {}).get("name"),
            "location": data.get("location"),
            "linkedin_url": data.get("linkedIn"),
            "emails": data.get("emails", []),
            "phones": data.get("phones", []),
            "source_raw": data
        }
