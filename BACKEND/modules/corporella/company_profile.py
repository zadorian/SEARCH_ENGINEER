"""
Company Profile API endpoint
Provides unified access to company information from multiple sources
"""

import sys
from pathlib import Path

MODULES_DIR = Path(__file__).resolve().parents[1]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from corporella.opencorporates_brute import OpenCorporatesAPI
from SEARCH_ENGINES.occrp_aleph import AlephAPI
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class CompanyProfileAPI:
    """Unified company profile API"""
    
    def __init__(self):
        self.opencorporates = OpenCorporatesAPI()
        # AlephAPI requires API key, so only initialize if available
        self.aleph = None
        
    def initialize_aleph(self, api_key: str):
        """Initialize Aleph API with API key"""
        self.aleph = AlephAPI(api_key)
        
    async def get_company_profile(self, company_name: str, jurisdiction: Optional[str] = None) -> Dict[str, Any]:
        """
        Get unified company profile from multiple sources
        
        Args:
            company_name: Name of the company to search
            jurisdiction: Optional jurisdiction code (e.g., 'us_de', 'gb')
            
        Returns:
            Unified company profile data
        """
        profile = {
            "company_name": company_name,
            "jurisdiction": jurisdiction,
            "sources": {}
        }
        
        # Get OpenCorporates data
        try:
            oc_results = await self.opencorporates.search_companies(company_name, jurisdiction)
            if oc_results and oc_results.get("companies"):
                profile["sources"]["opencorporates"] = oc_results["companies"][0]
        except Exception as e:
            logger.error(f"OpenCorporates search failed: {e}")
            profile["sources"]["opencorporates"] = {"error": str(e)}
            
        # Get OCCRP Aleph data if available
        if self.aleph:
            try:
                aleph_results = self.aleph.search_entities(company_name, schema="Company")
                if aleph_results and aleph_results.get("results"):
                    profile["sources"]["occrp_aleph"] = aleph_results["results"][0]
            except Exception as e:
                logger.error(f"OCCRP Aleph search failed: {e}")
                profile["sources"]["occrp_aleph"] = {"error": str(e)}
                
        return profile

# Create global instance
profile_api = CompanyProfileAPI()

@router.get("/company/{company_name}")
async def get_company_profile(
    company_name: str,
    jurisdiction: Optional[str] = Query(None, description="Jurisdiction code (e.g., 'us_de', 'gb')"),
    aleph_api_key: Optional[str] = Query(None, description="OCCRP Aleph API key")
):
    """
    Get unified company profile from multiple sources
    """
    if aleph_api_key:
        profile_api.initialize_aleph(aleph_api_key)
        
    try:
        profile = await profile_api.get_company_profile(company_name, jurisdiction)
        return profile
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/company/search/{query}")
async def search_companies(
    query: str,
    jurisdiction: Optional[str] = Query(None, description="Jurisdiction code"),
    limit: int = Query(10, description="Maximum number of results")
):
    """
    Search for companies across multiple sources
    """
    results = {
        "query": query,
        "jurisdiction": jurisdiction,
        "limit": limit,
        "results": []
    }
    
    try:
        # Search OpenCorporates
        oc_results = await profile_api.opencorporates.search_companies(query, jurisdiction)
        if oc_results and oc_results.get("companies"):
            for company in oc_results["companies"][:limit]:
                results["results"].append({
                    "source": "opencorporates",
                    "data": company
                })
    except Exception as e:
        logger.error(f"Company search failed: {e}")
        
    return results
