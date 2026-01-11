import logging
from typing import Dict, Any, Optional
from ...contracts import CoordinateMode, AbsenceType
# Import the actual state provider (Cymonides)
from ...core.cymonides_state import InvestigationState

logger = logging.getLogger(__name__)

class GeoManager:
    """
    Central manager for spatial hierarchy and auto-clustering.
    
    Philosophy: Geography is a Fractal Container.
    Creating an Address node automatically 'bubbles up' parent nodes:
    Address -> Municipality -> Region -> Country
    """
    
    def __init__(self, state: InvestigationState):
        self.state = state

    async def upsert_location_hierarchy(self, address_data: Dict[str, Any]):
        """
        Creates a full hierarchical cluster for an address finding.
        
        Args:
            address_data: Dict containing 'address', 'city', 'region', 'country'
        """
        # 1. Create Country Node (Top Level)
        country_id = None
        if address_data.get("country"):
            country_id = await self.state.create_node(
                label=address_data["country"],
                class_name="location",
                type_name="country",
                properties={"name": address_data["country"], "iso_code": address_data.get("country_code")}
            )
            logger.info(f"  [Geo] Ensured Country: {address_data['country']}")

        # 2. Create Region Node (Container)
        region_id = None
        if address_data.get("region"):
            region_id = await self.state.create_node(
                label=address_data["region"],
                class_name="location",
                type_name="region",
                properties={"name": address_data["region"]}
            )
            if country_id:
                await self.state.create_edge(region_id, country_id, "located_in")
            logger.info(f"  [Geo] Ensured Region: {address_data['region']}")

        # 3. Create Municipality Node (Settlement)
        city_id = None
        if address_data.get("city"):
            city_id = await self.state.create_node(
                label=address_data["city"],
                class_name="location",
                type_name="municipality",
                properties={"name": address_data["city"]}
            )
            if region_id:
                await self.state.create_edge(city_id, region_id, "located_in")
            elif country_id:
                await self.state.create_edge(city_id, country_id, "located_in")
            logger.info(f"  [Geo] Ensured Municipality: {address_data['city']}")

        # 4. Create Address Node (Atomic Leaf)
        if address_data.get("address"):
            addr_id = await self.state.create_node(
                label=address_data["address"],
                class_name="location",
                type_name="address",
                properties={"full_address": address_data["address"]}
            )
            if city_id:
                await self.state.create_edge(addr_id, city_id, "located_in")
            elif country_id:
                await self.state.create_edge(addr_id, country_id, "located_in")
            
            return addr_id
        
        return city_id or region_id or country_id
