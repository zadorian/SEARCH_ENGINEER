"""
Iframe Manager
Isolates EYE-D's global JavaScript state from WIKIMAN-PRO React app

Prevents vis-network's 14,773 lines of global state from causing
10,000+ setState() calls in React
"""

from typing import Dict, List, Any, Callable, Optional
import json


class IframeManager:
    """
    Manages iframe-based isolation for EYE-D graph visualization

    Architecture:
    - WIKIMAN-PRO React app (parent)
    - EYE-D vis-network graph (iframe child)
    - PostMessage bridge for communication
    - Cache coordinator for data sync

    Benefits:
    - Prevents React re-render storms
    - Isolates vis-network globals
    - Enables independent updates
    - Maintains security (same-origin)
    """

    def __init__(self, iframe_id: str = "eyed-graph-iframe"):
        self.iframe_id = iframe_id
        self.message_handlers: Dict[str, Callable] = {}
        self.pending_messages: List[Dict[str, Any]] = []

    def register_handler(self, message_type: str, handler: Callable):
        """
        Register message handler for iframe communication

        Args:
            message_type: Type of message to handle
            handler: Function to call when message received
        """
        self.message_handlers[message_type] = handler

    def send_message(self, message_type: str, data: Any):
        """
        Send message to iframe

        Args:
            message_type: Type of message
            data: Message payload
        """
        message = {
            "type": message_type,
            "data": data,
            "timestamp": None  # Set by cache coordinator if needed
        }

        # In browser: window.frames[iframe_id].postMessage(message, origin)
        # For now, queue message
        self.pending_messages.append(message)

    def handle_message(self, event: Dict[str, Any]):
        """
        Handle incoming message from iframe

        Args:
            event: PostMessage event data
        """
        message_type = event.get("type")
        data = event.get("data")

        if message_type in self.message_handlers:
            handler = self.message_handlers[message_type]
            handler(data)

    def load_graph(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]):
        """
        Load graph data into iframe

        Args:
            nodes: vis-network nodes
            edges: vis-network edges
        """
        self.send_message("load_graph", {
            "nodes": nodes,
            "edges": edges
        })

    def update_node(self, node_id: str, updates: Dict[str, Any]):
        """
        Update single node in iframe graph

        Args:
            node_id: Node to update
            updates: Properties to update
        """
        self.send_message("update_node", {
            "node_id": node_id,
            "updates": updates
        })

    def update_nodes(self, updates: List[Dict[str, Any]]):
        """
        Batch update multiple nodes

        Args:
            updates: List of {node_id, updates} dicts
        """
        self.send_message("update_nodes", {
            "updates": updates
        })

    def add_nodes(self, nodes: List[Dict[str, Any]]):
        """
        Add new nodes to graph

        Args:
            nodes: vis-network nodes to add
        """
        self.send_message("add_nodes", {
            "nodes": nodes
        })

    def remove_nodes(self, node_ids: List[str]):
        """
        Remove nodes from graph

        Args:
            node_ids: IDs of nodes to remove
        """
        self.send_message("remove_nodes", {
            "node_ids": node_ids
        })

    def add_edges(self, edges: List[Dict[str, Any]]):
        """
        Add new edges to graph

        Args:
            edges: vis-network edges to add
        """
        self.send_message("add_edges", {
            "edges": edges
        })

    def remove_edges(self, edge_ids: List[str]):
        """
        Remove edges from graph

        Args:
            edge_ids: IDs of edges to remove
        """
        self.send_message("remove_edges", {
            "edge_ids": edge_ids
        })

    def focus_node(self, node_id: str, animation: bool = True):
        """
        Focus (center and zoom to) a specific node

        Args:
            node_id: Node to focus
            animation: Whether to animate the transition
        """
        self.send_message("focus_node", {
            "node_id": node_id,
            "animation": animation
        })

    def fit_graph(self, animation: bool = True):
        """
        Fit entire graph in viewport

        Args:
            animation: Whether to animate the transition
        """
        self.send_message("fit_graph", {
            "animation": animation
        })

    def get_selection(self) -> Dict[str, Any]:
        """
        Get currently selected nodes/edges

        Returns:
            {
                "nodes": ["id1", "id2"],
                "edges": ["edge1"]
            }
        """
        # In browser: Request selection from iframe via postMessage
        # For now, return empty
        return {"nodes": [], "edges": []}

    def export_image(self, format: str = "png") -> str:
        """
        Export graph as image

        Args:
            format: Image format ('png', 'svg', 'jpeg')

        Returns:
            Base64-encoded image data
        """
        self.send_message("export_image", {
            "format": format
        })
        # In browser: Wait for response via postMessage
        return ""
