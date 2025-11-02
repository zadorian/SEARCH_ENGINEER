"""
Graph Data Bridge
Extracts entities and relationships from WIKIMAN-PRO search results
Converts to vis-network format for EYE-D visualization
"""

from typing import Dict, List, Any, Optional
from datetime import datetime


def search_for_graph(
    query: str,
    router: str = "c",
    max_depth: int = 2
) -> Dict[str, Any]:
    """
    Execute WIKIMAN search and extract graph data

    Args:
        query: Search query (company name, person name, etc.)
        router: WIKIMAN router ('c' company, 'p' person, 'cuk' UK company, etc.)
        max_depth: How many relationship layers to extract (1-3)

    Returns:
        {
            "nodes": [...],  # vis-network nodes
            "edges": [...],  # vis-network edges
            "metadata": {
                "query": "...",
                "router": "...",
                "timestamp": "...",
                "entity_count": 42
            }
        }
    """
    # TODO: Import WIKIMAN search functions
    # For now, return structure

    return {
        "nodes": [],
        "edges": [],
        "metadata": {
            "query": query,
            "router": router,
            "timestamp": datetime.utcnow().isoformat(),
            "entity_count": 0,
            "max_depth": max_depth
        }
    }


def extract_entities_from_uk_company(company_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract graph entities from UK Companies House data

    Extracts:
    - Company (root node)
    - Officers (directors, secretaries)
    - PSC (beneficial owners)
    - Addresses
    - Relationships between all entities

    Args:
        company_data: Result from search_uk_company()

    Returns:
        {
            "nodes": [...],
            "edges": [...]
        }
    """
    nodes = []
    edges = []

    # Extract company node
    company_name = company_data.get("name", "Unknown Company")
    company_number = company_data.get("registration_number", "")

    company_node = {
        "id": f"company_{company_number}",
        "label": company_name,
        "type": "company",
        "data": {
            "company_number": company_number,
            "status": company_data.get("status"),
            "incorporation_date": company_data.get("incorporation_date"),
            "jurisdiction": "gb"
        }
    }
    nodes.append(company_node)

    # Extract officer nodes
    officers = company_data.get("officers", [])
    for i, officer in enumerate(officers):
        officer_id = f"officer_{company_number}_{i}"
        officer_node = {
            "id": officer_id,
            "label": officer.get("name", "Unknown Officer"),
            "type": "person",
            "data": {
                "role": officer.get("role"),
                "appointed_on": officer.get("appointed_on"),
                "resigned_on": officer.get("resigned_on")
            }
        }
        nodes.append(officer_node)

        # Create edge: officer → company
        edge = {
            "from": officer_id,
            "to": company_node["id"],
            "label": officer.get("role", "officer"),
            "type": "officer_of"
        }
        edges.append(edge)

    # Extract PSC nodes (beneficial owners)
    psc = company_data.get("psc", [])
    for i, person in enumerate(psc):
        psc_id = f"psc_{company_number}_{i}"
        psc_node = {
            "id": psc_id,
            "label": person.get("name", "Unknown PSC"),
            "type": "person",
            "data": {
                "kind": person.get("kind"),
                "natures_of_control": person.get("natures_of_control", [])
            }
        }
        nodes.append(psc_node)

        # Create edge: PSC → company
        control_label = ", ".join(person.get("natures_of_control", ["controls"]))
        edge = {
            "from": psc_id,
            "to": company_node["id"],
            "label": control_label,
            "type": "controls"
        }
        edges.append(edge)

    return {
        "nodes": nodes,
        "edges": edges
    }


def extract_entities_from_vector_search(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract graph entities from WIKIMAN vector search results

    Args:
        results: List of vector search results from WIKIMAN

    Returns:
        {
            "nodes": [...],
            "edges": [...]
        }
    """
    nodes = []
    edges = []

    for i, result in enumerate(results):
        node_id = f"doc_{i}"
        title = result.get("title", "Unknown Document")
        score = result.get("score", 0.0)

        node = {
            "id": node_id,
            "label": title,
            "type": "document",
            "data": {
                "score": score,
                "preview": result.get("preview", ""),
                "text": result.get("text", "")
            }
        }
        nodes.append(node)

    # TODO: Extract entities from document text
    # TODO: Find relationships between documents

    return {
        "nodes": nodes,
        "edges": edges
    }
