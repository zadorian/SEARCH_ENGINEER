import json
import logging
import importlib
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("country_api_router")

class CountryRouter:
    """
    Routes requests to specialized Country APIs/CLIs.
    """
    
    def __init__(self):
        self.registry = self._load_registry()
        self._cache = {}

    def _load_registry(self) -> Dict:
        """Load registry.json."""
        path = Path(__file__).parent / "registry.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return {}

    def get_api_config(self, jurisdiction: str) -> Optional[Dict]:
        """Get API config for a jurisdiction."""
        if not jurisdiction:
            return None
        
        jur = jurisdiction.upper()
        config = self.registry.get(jur)
        
        # Handle aliases (e.g., GB -> UK)
        if config and "alias" in config:
            jur = config["alias"]
            config = self.registry.get(jur)
            
        return config

    def has_api(self, jurisdiction: str) -> bool:
        """Check if a jurisdiction has a dedicated API/CLI."""
        return self.get_api_config(jurisdiction) is not None

    async def execute(self, query: str, jurisdiction: str) -> Dict[str, Any]:
        """
        Execute a query against a specific country API.
        
        Args:
            query: The search query (e.g. "cde: Siemens" or just "Siemens")
            jurisdiction: The 2-letter country code (e.g. "DE")
        """
        config = self.get_api_config(jurisdiction)
        if not config:
            return {"error": f"No API available for jurisdiction: {jurisdiction}", "fallback_to_torpedo": True}

        module_path = config.get("module")
        class_name = config.get("class")
        method_name = config.get("method", "execute")

        try:
            # Dynamic import
            if module_path not in self._cache:
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name)
                self._cache[module_path] = cls()
            
            instance = self._cache[module_path]
            method = getattr(instance, method_name)

            logger.info(f"Routing to {jurisdiction} API: {module_path}.{class_name}.{method_name}")
            
            # Execute
            if asyncio.iscoroutinefunction(method):
                result = await method(query)
            else:
                result = method(query)
                
            # Normalize result if object
            if hasattr(result, "to_dict"):
                return result.to_dict()
            return result

        except ImportError as e:
            logger.error(f"Failed to import country module {module_path}: {e}")
            return {"error": str(e), "fallback_to_torpedo": True}
        except Exception as e:
            logger.error(f"Country API execution error: {e}")
            return {"error": str(e), "fallback_to_torpedo": True}

    async def search_company(self, name: str, jurisdiction: str) -> Dict[str, Any]:
        """Helper to format query with correct prefix."""
        # Map jurisdiction to prefix (e.g. DE -> cde:)
        # Default logic: c{lowercode}:
        if not jurisdiction:
             return {"error": "Jurisdiction required for Country API"}
             
        prefix = f"c{jurisdiction.lower()}:"
        query = f"{prefix} {name}"
        return await self.execute(query, jurisdiction)

    async def search_person(self, name: str, jurisdiction: str) -> Dict[str, Any]:
        """Helper to format query with correct prefix."""
        prefix = f"p{jurisdiction.lower()}:"
        query = f"{prefix} {name}"
        return await self.execute(query, jurisdiction)