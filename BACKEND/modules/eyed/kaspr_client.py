import os
import requests
import json

class KasprClient:
    """
    Kaspr API Client
    Documentation: https://api.kaspr.io/docs
    """
    
    BASE_URL = "https://api.kaspr.io/v1"
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("KASPR_API_KEY")
        if not self.api_key:
            print("Warning: KASPR_API_KEY not found.")

    def _get_headers(self):
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }

    def enrich_linkedin(self, linkedin_url: str):
        """Enrich from LinkedIn URL"""
        if not self.api_key: return None
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/enrich",
                json={"linkedin_url": linkedin_url},
                headers=self._get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return self._normalize_profile(data.get("profile"))
            return None
        except Exception as e:
            print(f"Kaspr enrich_linkedin error: {e}")
            return None

    def _normalize_profile(self, data):
        if not data: return None
        return {
            "name": data.get("name"),
            "current_title": data.get("job_title"),
            "current_employer": data.get("company_name"),
            "location": data.get("location"),
            "linkedin_url": data.get("linkedin_url"),
            "emails": [e.get("address") for e in data.get("emails", [])],
            "phones": [p.get("number") for p in data.get("phones", [])],
            "source_raw": data
        }
