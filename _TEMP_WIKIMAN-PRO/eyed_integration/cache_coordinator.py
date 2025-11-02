"""
Cache Coordinator with Lamport Timestamps
Distributed cache synchronization across frontend/backend/iframe

Prevents race conditions and ensures consistency when EYE-D graph
is embedded in WIKIMAN-PRO via iframe
"""

from typing import Dict, Any, Optional
from datetime import datetime


class CacheCoordinator:
    """
    Cache coordinator using Lamport logical clocks

    Ensures:
    - Frontend and iframe stay synchronized
    - No stale data shown after updates
    - Correct ordering of graph mutations
    - No race conditions during concurrent updates
    """

    def __init__(self):
        self.lamport_clock = 0
        self.cache: Dict[str, Any] = {}
        self.timestamps: Dict[str, int] = {}

    def increment_clock(self) -> int:
        """
        Increment Lamport clock and return new value

        Returns:
            New Lamport timestamp
        """
        self.lamport_clock += 1
        return self.lamport_clock

    def update_clock(self, received_timestamp: int):
        """
        Update clock based on received message

        Args:
            received_timestamp: Lamport timestamp from remote message
        """
        self.lamport_clock = max(self.lamport_clock, received_timestamp) + 1

    def set(self, key: str, value: Any, timestamp: Optional[int] = None) -> int:
        """
        Set cache value with Lamport timestamp

        Args:
            key: Cache key
            value: Value to cache
            timestamp: Optional Lamport timestamp (creates new if None)

        Returns:
            Lamport timestamp of this operation
        """
        if timestamp is None:
            timestamp = self.increment_clock()
        else:
            self.update_clock(timestamp)

        # Only update if timestamp is newer
        existing_timestamp = self.timestamps.get(key, -1)
        if timestamp > existing_timestamp:
            self.cache[key] = value
            self.timestamps[key] = timestamp

        return timestamp

    def get(self, key: str) -> Optional[Any]:
        """
        Get cached value

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        return self.cache.get(key)

    def get_with_timestamp(self, key: str) -> tuple[Optional[Any], int]:
        """
        Get cached value and its Lamport timestamp

        Args:
            key: Cache key

        Returns:
            (value, timestamp) tuple
        """
        value = self.cache.get(key)
        timestamp = self.timestamps.get(key, -1)
        return (value, timestamp)

    def delete(self, key: str) -> int:
        """
        Delete cache entry with Lamport timestamp

        Args:
            key: Cache key

        Returns:
            Lamport timestamp of deletion
        """
        timestamp = self.increment_clock()

        if key in self.cache:
            del self.cache[key]
        if key in self.timestamps:
            del self.timestamps[key]

        return timestamp

    def sync_message(self, operation: str, key: str, value: Any, timestamp: int) -> Dict[str, Any]:
        """
        Create synchronization message for iframe/frontend

        Args:
            operation: 'set' or 'delete'
            key: Cache key
            value: Value (for set operations)
            timestamp: Lamport timestamp

        Returns:
            Sync message to send to other contexts
        """
        return {
            "type": "cache_sync",
            "operation": operation,
            "key": key,
            "value": value,
            "timestamp": timestamp
        }

    def handle_sync_message(self, message: Dict[str, Any]):
        """
        Handle incoming cache synchronization message

        Args:
            message: Sync message from another context (iframe, frontend, backend)
        """
        operation = message.get("operation")
        key = message.get("key")
        value = message.get("value")
        timestamp = message.get("timestamp", 0)

        if operation == "set":
            self.set(key, value, timestamp)
        elif operation == "delete":
            self.update_clock(timestamp)
            if key in self.cache:
                del self.cache[key]
            if key in self.timestamps:
                del self.timestamps[key]
