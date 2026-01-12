"""
Pluggable Storage Backend for Crawlers

Abstract storage interface for crawler state, usable by both
web (DRILL) and tor (SerDavos) crawlers.

Implementations:
- MemoryStorage: In-memory (fast, non-persistent)
- SQLiteStorage: SQLite-backed (persistent)
- Future: RedisStorage for distributed crawling
"""

import json
import logging
from collections import deque
from dataclasses import dataclass
from typing import Dict, Set, Any, Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class QueueItem:
    url: str
    depth: int
    priority: int = 0
    mission_id: Optional[str] = None
    mission_budget: Optional[int] = None


class StorageBackend(Protocol):
    """
    Abstract storage interface for crawler state.

    All methods are async for consistency, even MemoryStorage.
    """
    async def is_visited(self, url: str) -> bool: ...
    async def mark_visited(self, url: str, timestamp: float) -> None: ...
    async def get_visit_time(self, url: str) -> Optional[float]: ...
    async def enqueue(
        self,
        url: str,
        depth: int,
        priority: int = 0,
        mission_id: Optional[str] = None,
        mission_budget: Optional[int] = None,
    ) -> None: ...
    async def dequeue(self, prefer_priority: Optional[int] = None) -> Optional[QueueItem]: ...
    async def queue_size(self) -> int: ...
    async def get_domain_count(self, domain: str) -> int: ...
    async def increment_domain_count(self, domain: str) -> None: ...
    async def save_state(self, state: dict) -> None: ...
    async def load_state(self) -> Optional[dict]: ...


class MemoryStorage:
    """In-memory storage backend (default)."""

    def __init__(self):
        self._visited: Dict[str, float] = {}  # url -> timestamp
        self._queue_high: deque = deque()
        self._queue_normal: deque = deque()
        self._queue_low: deque = deque()
        self._domain_counts: Dict[str, int] = {}
        self._state: Dict[str, Any] = {}

    async def is_visited(self, url: str) -> bool:
        return url in self._visited

    async def mark_visited(self, url: str, timestamp: float) -> None:
        self._visited[url] = timestamp

    async def get_visit_time(self, url: str) -> Optional[float]:
        return self._visited.get(url)

    async def enqueue(
        self,
        url: str,
        depth: int,
        priority: int = 0,
        mission_id: Optional[str] = None,
        mission_budget: Optional[int] = None,
    ) -> None:
        item = QueueItem(
            url=url,
            depth=depth,
            priority=priority,
            mission_id=mission_id,
            mission_budget=mission_budget,
        )
        if priority and priority > 0:
            self._queue_high.append(item)
        elif priority and priority < 0:
            self._queue_low.append(item)
        else:
            self._queue_normal.append(item)

    async def dequeue(self, prefer_priority: Optional[int] = None) -> Optional[QueueItem]:
        if prefer_priority is None:
            if self._queue_high:
                return self._queue_high.popleft()
            if self._queue_normal:
                return self._queue_normal.popleft()
            if self._queue_low:
                return self._queue_low.popleft()
            return None

        if prefer_priority > 0:
            if self._queue_high:
                return self._queue_high.popleft()
            if self._queue_normal:
                return self._queue_normal.popleft()
            if self._queue_low:
                return self._queue_low.popleft()
            return None

        if prefer_priority < 0:
            if self._queue_low:
                return self._queue_low.popleft()
            if self._queue_normal:
                return self._queue_normal.popleft()
            if self._queue_high:
                return self._queue_high.popleft()
            return None

        if self._queue_normal:
            return self._queue_normal.popleft()
        if self._queue_high:
            return self._queue_high.popleft()
        if self._queue_low:
            return self._queue_low.popleft()
        return None

    async def queue_size(self) -> int:
        return len(self._queue_high) + len(self._queue_normal) + len(self._queue_low)

    async def get_domain_count(self, domain: str) -> int:
        return self._domain_counts.get(domain, 0)

    async def increment_domain_count(self, domain: str) -> None:
        self._domain_counts[domain] = self._domain_counts.get(domain, 0) + 1

    async def save_state(self, state: dict) -> None:
        self._state = state

    async def load_state(self) -> Optional[dict]:
        return self._state if self._state else None

    def get_visited_urls(self) -> Set[str]:
        """Get all visited URLs (for backward compatibility)."""
        return set(self._visited.keys())

    def get_domain_counts(self) -> Dict[str, int]:
        """Get domain counts (for backward compatibility)."""
        return self._domain_counts.copy()

    def clear(self) -> None:
        """Clear all storage."""
        self._visited.clear()
        self._queue_high.clear()
        self._queue_normal.clear()
        self._queue_low.clear()
        self._domain_counts.clear()
        self._state.clear()


class SQLiteStorage:
    """SQLite-based persistent storage backend."""

    def __init__(self, db_path: str = "crawler_storage.db"):
        self.db_path = db_path
        self._conn = None
        self._initialized = False

    async def _ensure_initialized(self):
        if self._initialized:
            return

        try:
            import aiosqlite
            self._conn = await aiosqlite.connect(self.db_path)

            # Create tables
            await self._conn.execute("""
                CREATE TABLE IF NOT EXISTS visited (
                    url TEXT PRIMARY KEY,
                    timestamp REAL
                )
            """)
            await self._conn.execute("""
                CREATE TABLE IF NOT EXISTS queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT,
                    depth INTEGER,
                    priority INTEGER DEFAULT 0,
                    mission_id TEXT,
                    mission_budget INTEGER
                )
            """)
            await self._conn.execute("""
                CREATE TABLE IF NOT EXISTS domain_counts (
                    domain TEXT PRIMARY KEY,
                    count INTEGER
                )
            """)
            await self._conn.execute("""
                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            await self._conn.commit()
            self._initialized = True

            # Ensure priority column exists for older DBs
            async with self._conn.execute("PRAGMA table_info(queue)") as cursor:
                columns = [row[1] for row in await cursor.fetchall()]
            if "priority" not in columns:
                await self._conn.execute("ALTER TABLE queue ADD COLUMN priority INTEGER DEFAULT 0")
                await self._conn.commit()
            if "mission_id" not in columns:
                await self._conn.execute("ALTER TABLE queue ADD COLUMN mission_id TEXT")
                await self._conn.commit()
            if "mission_budget" not in columns:
                await self._conn.execute("ALTER TABLE queue ADD COLUMN mission_budget INTEGER")
                await self._conn.commit()
        except ImportError:
            raise ImportError("SQLiteStorage requires aiosqlite: pip install aiosqlite")

    async def is_visited(self, url: str) -> bool:
        await self._ensure_initialized()
        async with self._conn.execute(
            "SELECT 1 FROM visited WHERE url = ?", (url,)
        ) as cursor:
            return await cursor.fetchone() is not None

    async def mark_visited(self, url: str, timestamp: float) -> None:
        await self._ensure_initialized()
        await self._conn.execute(
            "INSERT OR REPLACE INTO visited (url, timestamp) VALUES (?, ?)",
            (url, timestamp)
        )
        await self._conn.commit()

    async def get_visit_time(self, url: str) -> Optional[float]:
        await self._ensure_initialized()
        async with self._conn.execute(
            "SELECT timestamp FROM visited WHERE url = ?", (url,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def enqueue(
        self,
        url: str,
        depth: int,
        priority: int = 0,
        mission_id: Optional[str] = None,
        mission_budget: Optional[int] = None,
    ) -> None:
        await self._ensure_initialized()
        await self._conn.execute(
            "INSERT INTO queue (url, depth, priority, mission_id, mission_budget) VALUES (?, ?, ?, ?, ?)",
            (url, depth, priority, mission_id, mission_budget)
        )
        await self._conn.commit()

    async def dequeue(self, prefer_priority: Optional[int] = None) -> Optional[QueueItem]:
        await self._ensure_initialized()
        order_clause = "priority DESC, id ASC"
        if prefer_priority is not None:
            if prefer_priority > 0:
                order_clause = "priority DESC, id ASC"
            elif prefer_priority < 0:
                order_clause = "CASE WHEN priority < 0 THEN 0 WHEN priority = 0 THEN 1 ELSE 2 END, id ASC"
            else:
                order_clause = "CASE WHEN priority = 0 THEN 0 WHEN priority > 0 THEN 1 ELSE 2 END, id ASC"

        async with self._conn.execute(
            f"SELECT id, url, depth, priority, mission_id, mission_budget FROM queue ORDER BY {order_clause} LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                await self._conn.execute("DELETE FROM queue WHERE id = ?", (row[0],))
                await self._conn.commit()
                return QueueItem(
                    url=row[1],
                    depth=row[2],
                    priority=row[3] if row[3] is not None else 0,
                    mission_id=row[4],
                    mission_budget=row[5],
                )
        return None

    async def queue_size(self) -> int:
        await self._ensure_initialized()
        async with self._conn.execute("SELECT COUNT(*) FROM queue") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_domain_count(self, domain: str) -> int:
        await self._ensure_initialized()
        async with self._conn.execute(
            "SELECT count FROM domain_counts WHERE domain = ?", (domain,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def increment_domain_count(self, domain: str) -> None:
        await self._ensure_initialized()
        await self._conn.execute("""
            INSERT INTO domain_counts (domain, count) VALUES (?, 1)
            ON CONFLICT(domain) DO UPDATE SET count = count + 1
        """, (domain,))
        await self._conn.commit()

    async def save_state(self, state: dict) -> None:
        await self._ensure_initialized()
        await self._conn.execute(
            "INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)",
            ("crawl_state", json.dumps(state))
        )
        await self._conn.commit()

    async def load_state(self) -> Optional[dict]:
        await self._ensure_initialized()
        async with self._conn.execute(
            "SELECT value FROM state WHERE key = ?", ("crawl_state",)
        ) as cursor:
            row = await cursor.fetchone()
            return json.loads(row[0]) if row else None

    async def close(self):
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
            self._initialized = False

    async def clear(self):
        """Clear all storage tables."""
        await self._ensure_initialized()
        await self._conn.execute("DELETE FROM visited")
        await self._conn.execute("DELETE FROM queue")
        await self._conn.execute("DELETE FROM domain_counts")
        await self._conn.execute("DELETE FROM state")
        await self._conn.commit()


class RedisStorage:
    """Redis-backed persistent storage backend."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        namespace: str = "drill",
        use_bloom: bool = False,
        bloom_capacity: int = 1000000,
        bloom_error_rate: float = 0.01,
    ):
        try:
            import redis.asyncio as redis  # type: ignore
        except ImportError as exc:
            raise ImportError("RedisStorage requires redis>=4.2 (redis.asyncio)") from exc

        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._namespace = namespace
        self._use_bloom = use_bloom
        self._bloom_capacity = bloom_capacity
        self._bloom_error_rate = bloom_error_rate
        self._bloom_ready = False

    def _key(self, name: str) -> str:
        return f"{self._namespace}:{name}"

    async def _ensure_bloom(self) -> bool:
        if not self._use_bloom:
            return False
        if self._bloom_ready:
            return True
        key = self._key("visited_bloom")
        try:
            await self._redis.execute_command(
                "BF.RESERVE",
                key,
                self._bloom_error_rate,
                self._bloom_capacity,
            )
            self._bloom_ready = True
        except Exception:
            self._bloom_ready = False
        return self._bloom_ready

    async def is_visited(self, url: str) -> bool:
        if await self._ensure_bloom():
            try:
                return bool(await self._redis.execute_command("BF.EXISTS", self._key("visited_bloom"), url))
            except Exception:
                pass
        return bool(await self._redis.sismember(self._key("visited_set"), url))

    async def mark_visited(self, url: str, timestamp: float) -> None:
        if await self._ensure_bloom():
            try:
                await self._redis.execute_command("BF.ADD", self._key("visited_bloom"), url)
            except Exception:
                await self._redis.sadd(self._key("visited_set"), url)
        else:
            await self._redis.sadd(self._key("visited_set"), url)

        await self._redis.hset(self._key("visited_ts"), url, timestamp)

    async def get_visit_time(self, url: str) -> Optional[float]:
        value = await self._redis.hget(self._key("visited_ts"), url)
        return float(value) if value is not None else None

    async def enqueue(
        self,
        url: str,
        depth: int,
        priority: int = 0,
        mission_id: Optional[str] = None,
        mission_budget: Optional[int] = None,
    ) -> None:
        payload = json.dumps({
            "url": url,
            "depth": depth,
            "priority": priority,
            "mission_id": mission_id,
            "mission_budget": mission_budget,
        })
        if priority and priority > 0:
            await self._redis.rpush(self._key("queue_high"), payload)
        elif priority and priority < 0:
            await self._redis.rpush(self._key("queue_low"), payload)
        else:
            await self._redis.rpush(self._key("queue_normal"), payload)

    async def dequeue(self, prefer_priority: Optional[int] = None) -> Optional[QueueItem]:
        queues = []
        if prefer_priority is None:
            queues = ["queue_high", "queue_normal", "queue_low"]
        elif prefer_priority > 0:
            queues = ["queue_high", "queue_normal", "queue_low"]
        elif prefer_priority < 0:
            queues = ["queue_low", "queue_normal", "queue_high"]
        else:
            queues = ["queue_normal", "queue_high", "queue_low"]

        payload = None
        for name in queues:
            payload = await self._redis.lpop(self._key(name))
            if payload:
                break
        if not payload:
            return None
        try:
            data = json.loads(payload)
            mission_budget = data.get("mission_budget")
            if mission_budget is not None:
                try:
                    mission_budget = int(mission_budget)
                except Exception:
                    mission_budget = None
            return QueueItem(
                url=data.get("url"),
                depth=int(data.get("depth", 0)),
                priority=int(data.get("priority", 0)),
                mission_id=data.get("mission_id"),
                mission_budget=mission_budget,
            )
        except Exception:
            return None

    async def queue_size(self) -> int:
        high = await self._redis.llen(self._key("queue_high"))
        normal = await self._redis.llen(self._key("queue_normal"))
        low = await self._redis.llen(self._key("queue_low"))
        return int(high) + int(normal) + int(low)

    async def get_domain_count(self, domain: str) -> int:
        value = await self._redis.hget(self._key("domain_counts"), domain)
        return int(value) if value is not None else 0

    async def increment_domain_count(self, domain: str) -> None:
        await self._redis.hincrby(self._key("domain_counts"), domain, 1)

    async def save_state(self, state: dict) -> None:
        await self._redis.set(self._key("state"), json.dumps(state))

    async def load_state(self) -> Optional[dict]:
        value = await self._redis.get(self._key("state"))
        return json.loads(value) if value else None

    async def clear(self) -> None:
        keys = [
            self._key("visited_set"),
            self._key("visited_bloom"),
            self._key("visited_ts"),
            self._key("queue_high"),
            self._key("queue_normal"),
            self._key("queue_low"),
            self._key("domain_counts"),
            self._key("state"),
        ]
        await self._redis.delete(*keys)

    async def close(self) -> None:
        try:
            await self._redis.close()
        except Exception:
            pass
