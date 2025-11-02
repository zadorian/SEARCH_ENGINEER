"""
Relationship Enrichment Pipeline
Infers implicit relationships and enriches graph with additional context

Extracts relationships from:
- Shared addresses (same location → potential connection)
- Shared officers (person on multiple company boards)
- Transaction patterns
- Temporal overlaps
"""

from typing import Dict, List, Any, Set, Tuple


class RelationshipEnricher:
    """
    Enriches graph by inferring implicit relationships

    Examples:
    - Person A is officer at Company B
    - Person A is officer at Company C
    - → Infer: Company B and Company C are connected (shared officer)

    - Company X at address "123 Main St"
    - Company Y at address "123 Main St"
    - → Infer: Company X and Company Y share location
    """

    def __init__(self):
        self.inferred_edges: List[Dict[str, Any]] = []
        self.confidence_scores: Dict[Tuple[str, str], float] = {}

    def enrich_graph(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze graph and infer additional relationships

        Args:
            nodes: Existing graph nodes
            edges: Existing graph edges

        Returns:
            {
                "new_edges": [...],  # Inferred relationships
                "confidence_scores": {...}  # Confidence per edge
            }
        """
        self.inferred_edges = []
        self.confidence_scores = {}

        # Build indices for fast lookups
        nodes_by_type = self._index_nodes_by_type(nodes)
        edges_by_source = self._index_edges_by_source(edges)

        # Infer relationships
        self._infer_shared_officers(nodes_by_type, edges_by_source)
        self._infer_shared_addresses(nodes_by_type)
        self._infer_temporal_overlaps(nodes_by_type, edges_by_source)

        return {
            "new_edges": self.inferred_edges,
            "confidence_scores": self.confidence_scores
        }

    def _index_nodes_by_type(
        self,
        nodes: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group nodes by type for faster lookups"""
        index = {}
        for node in nodes:
            node_type = node.get("data", {}).get("type", "unknown")
            if node_type not in index:
                index[node_type] = []
            index[node_type].append(node)
        return index

    def _index_edges_by_source(
        self,
        edges: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Index edges by source node"""
        index = {}
        for edge in edges:
            from_id = edge.get("from")
            if from_id not in index:
                index[from_id] = []
            index[from_id].append(edge)
        return index

    def _infer_shared_officers(
        self,
        nodes_by_type: Dict[str, List[Dict[str, Any]]],
        edges_by_source: Dict[str, List[Dict[str, Any]]]
    ):
        """
        Infer company connections via shared officers

        If Person X is officer at Company A and Company B,
        then A and B are connected (shared officer)
        """
        people = nodes_by_type.get("person", [])

        for person in people:
            person_id = person["id"]

            # Find all companies this person is an officer of
            companies = []
            if person_id in edges_by_source:
                for edge in edges_by_source[person_id]:
                    if edge.get("type") == "officer_of":
                        companies.append(edge.get("to"))

            # If person is officer at multiple companies, connect them
            if len(companies) >= 2:
                for i, company_a in enumerate(companies):
                    for company_b in companies[i+1:]:
                        self._add_inferred_edge(
                            company_a,
                            company_b,
                            "shared_officer",
                            confidence=0.8,
                            evidence={"officer": person_id}
                        )

    def _infer_shared_addresses(
        self,
        nodes_by_type: Dict[str, List[Dict[str, Any]]]
    ):
        """
        Infer company connections via shared addresses

        If Company A and Company B have same registered address,
        they may be connected
        """
        companies = nodes_by_type.get("company", [])

        # Group companies by address
        by_address = {}
        for company in companies:
            address = company.get("data", {}).get("registered_address")
            if address:
                address_str = str(address)  # Convert to string for grouping
                if address_str not in by_address:
                    by_address[address_str] = []
                by_address[address_str].append(company["id"])

        # Connect companies at same address
        for address, company_ids in by_address.items():
            if len(company_ids) >= 2:
                for i, company_a in enumerate(company_ids):
                    for company_b in company_ids[i+1:]:
                        self._add_inferred_edge(
                            company_a,
                            company_b,
                            "shared_address",
                            confidence=0.6,
                            evidence={"address": address}
                        )

    def _infer_temporal_overlaps(
        self,
        nodes_by_type: Dict[str, List[Dict[str, Any]]],
        edges_by_source: Dict[str, List[Dict[str, Any]]]
    ):
        """
        Infer connections based on temporal overlaps

        If Person X was officer at Company A during 2010-2015
        and officer at Company B during 2012-2017,
        then A and B overlap temporally (stronger connection)
        """
        # TODO: Implement temporal overlap detection
        # Requires parsing dates from officer appointed_on/resigned_on
        pass

    def _add_inferred_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str,
        confidence: float,
        evidence: Dict[str, Any]
    ):
        """Add inferred edge to results"""
        edge = {
            "from": from_id,
            "to": to_id,
            "label": edge_type.replace("_", " "),
            "type": edge_type,
            "inferred": True,  # Mark as inferred
            "confidence": confidence,
            "evidence": evidence
        }

        self.inferred_edges.append(edge)
        self.confidence_scores[(from_id, to_id)] = confidence
