"""
CyMonides 2.0 - Unified Backend Router
Smart routing between Elasticsearch (primary) and Whoosh (backup)
"""

from typing import Dict, List, Any, Optional, Literal
from pathlib import Path
import json
from datetime import datetime
from config.unified_config import config
from core.vector_embedder import get_embedder


class UnifiedBackend:
    """
    Unified Backend Router

    Intelligently routes operations to:
    - Elasticsearch (primary, preferred)
    - Whoosh (backup, fallback)

    Features:
    - Automatic fallback on Elasticsearch failure
    - Optional dual indexing (index to both)
    - Transparent API (callers don't know which backend is used)
    - Health monitoring and automatic recovery
    """

    def __init__(self):
        """Initialize unified backend"""
        self.elasticsearch_backend = None
        self.whoosh_backend = None

        # Backend status
        self.elasticsearch_available = False
        self.whoosh_available = False
        self.current_backend = None

        # Statistics
        self.stats = {
            "elasticsearch_calls": 0,
            "whoosh_calls": 0,
            "elasticsearch_failures": 0,
            "whoosh_failures": 0,
            "fallbacks": 0,
            "dual_indexed": 0
        }

        # Initialize embedder
        try:
            self.embedder = get_embedder()
            self.embeddings_enabled = True
            print("✅ Vector embeddings enabled")
        except Exception as e:
            print(f"⚠️  Vector embeddings disabled: {e}")
            self.embedder = None
            self.embeddings_enabled = False

        # Initialize backends
        self._initialize_backends()

    def _initialize_backends(self):
        """Initialize both backends"""
        # Try to initialize Elasticsearch
        try:
            from core.elasticsearch_backend import ElasticsearchBackend
            self.elasticsearch_backend = ElasticsearchBackend()
            self.elasticsearch_available = True
            self.current_backend = "elasticsearch"
            print("✅ Elasticsearch backend initialized")
        except Exception as e:
            print(f"⚠️  Elasticsearch unavailable: {e}")
            self.elasticsearch_available = False

        # Try to initialize Whoosh if enabled
        if config.WHOOSH_ENABLED:
            try:
                from core.whoosh_backend import WhooshBackend
                self.whoosh_backend = WhooshBackend()
                self.whoosh_available = True
                if not self.current_backend:
                    self.current_backend = "whoosh"
                print("✅ Whoosh backend initialized")
            except Exception as e:
                print(f"⚠️  Whoosh unavailable: {e}")
                self.whoosh_available = False

        # Check if we have at least one backend
        if not self.elasticsearch_available and not self.whoosh_available:
            raise RuntimeError("No backend available! Both Elasticsearch and Whoosh failed to initialize.")

        # Print backend status
        print(f"\n🎯 Backend Status:")
        print(f"   Primary: Elasticsearch {'✓' if self.elasticsearch_available else '✗'}")
        print(f"   Backup: Whoosh {'✓' if self.whoosh_available else '✗'}")
        print(f"   Active: {self.current_backend}")
        print(f"   Dual Indexing: {'✓' if config.ENABLE_BACKUP_INDEXING else '✗'}\n")

    def _get_backend(self, prefer_elastic: bool = True):
        """
        Get available backend, with preference

        Args:
            prefer_elastic: Try Elasticsearch first if available

        Returns:
            (backend, backend_name) tuple
        """
        if prefer_elastic and self.elasticsearch_available:
            return (self.elasticsearch_backend, "elasticsearch")
        elif self.whoosh_available:
            return (self.whoosh_backend, "whoosh")
        elif self.elasticsearch_available:
            return (self.elasticsearch_backend, "elasticsearch")
        else:
            raise RuntimeError("No backend available")

    def _execute_with_fallback(self, operation: str, *args, **kwargs) -> Dict[str, Any]:
        """
        Execute operation with automatic fallback

        Args:
            operation: Method name to call
            *args, **kwargs: Arguments to pass

        Returns:
            Result from successful backend
        """
        # Try primary backend first (Elasticsearch if available)
        backend, backend_name = self._get_backend(prefer_elastic=config.PREFER_ELASTIC)

        try:
            method = getattr(backend, operation)
            result = method(*args, **kwargs)

            # Update stats
            if backend_name == "elasticsearch":
                self.stats["elasticsearch_calls"] += 1
            else:
                self.stats["whoosh_calls"] += 1

            # Add backend info to result
            if isinstance(result, dict):
                result["_backend"] = backend_name

            # Dual indexing for write operations
            if config.ENABLE_BACKUP_INDEXING and operation.startswith(("index_", "create_", "add_")):
                self._dual_index(operation, result, *args, **kwargs)

            return result

        except Exception as e:
            # Update failure stats
            if backend_name == "elasticsearch":
                self.stats["elasticsearch_failures"] += 1
            else:
                self.stats["whoosh_failures"] += 1

            print(f"⚠️  {backend_name} failed for {operation}: {e}")

            # Try fallback
            if backend_name == "elasticsearch" and self.whoosh_available:
                print(f"🔄 Falling back to Whoosh...")
                self.stats["fallbacks"] += 1
                try:
                    method = getattr(self.whoosh_backend, operation)
                    result = method(*args, **kwargs)
                    self.stats["whoosh_calls"] += 1

                    if isinstance(result, dict):
                        result["_backend"] = "whoosh"
                        result["_fallback"] = True

                    return result
                except Exception as fallback_error:
                    self.stats["whoosh_failures"] += 1
                    raise RuntimeError(f"Both backends failed. Elasticsearch: {e}, Whoosh: {fallback_error}")

            elif backend_name == "whoosh" and self.elasticsearch_available:
                print(f"🔄 Falling back to Elasticsearch...")
                self.stats["fallbacks"] += 1
                try:
                    method = getattr(self.elasticsearch_backend, operation)
                    result = method(*args, **kwargs)
                    self.stats["elasticsearch_calls"] += 1

                    if isinstance(result, dict):
                        result["_backend"] = "elasticsearch"
                        result["_fallback"] = True

                    return result
                except Exception as fallback_error:
                    self.stats["elasticsearch_failures"] += 1
                    raise RuntimeError(f"Both backends failed. Whoosh: {e}, Elasticsearch: {fallback_error}")

            else:
                # No fallback available
                raise RuntimeError(f"Operation failed and no fallback available: {e}")

    def _dual_index(self, operation: str, primary_result: Dict[str, Any], *args, **kwargs):
        """
        Index to backup backend as well (async/best-effort)

        Args:
            operation: Operation that was performed
            primary_result: Result from primary backend
            *args, **kwargs: Original arguments
        """
        try:
            primary_backend = primary_result.get("_backend")

            # Determine backup backend
            if primary_backend == "elasticsearch" and self.whoosh_available:
                backup_backend = self.whoosh_backend
            elif primary_backend == "whoosh" and self.elasticsearch_available:
                backup_backend = self.elasticsearch_backend
            else:
                return  # No backup available

            # Execute on backup (best effort, don't fail if it errors)
            method = getattr(backup_backend, operation)
            method(*args, **kwargs)
            self.stats["dual_indexed"] += 1

        except Exception as e:
            # Dual indexing failure is not critical
            print(f"⚠️  Dual indexing failed (non-critical): {e}")

    # === Entity Operations ===

    def index_entity(self, entity: Dict[str, Any], zone_id: str = "default") -> Dict[str, Any]:
        """Index an entity"""
        entity["zone_id"] = zone_id

        # Generate embeddings if enabled
        if self.embeddings_enabled and self.embedder:
            try:
                entity = self.embedder.embed_document(entity, embed_schema=True)
            except Exception as e:
                print(f"⚠️  Embedding generation failed (non-critical): {e}")

        return self._execute_with_fallback("index_entity", entity)

    def index_relation(self, relation: Dict[str, Any], zone_id: str = "default") -> Dict[str, Any]:
        """Index a relation between entities"""
        relation["zone_id"] = zone_id
        return self._execute_with_fallback("index_relation", relation)

    def index_observation(self, observation: Dict[str, Any], zone_id: str = "default") -> Dict[str, Any]:
        """Index an observation"""
        observation["zone_id"] = zone_id
        return self._execute_with_fallback("index_observation", observation)

    # === Document Operations ===

    def index_document(self, document: Dict[str, Any], zone_id: str = "default") -> Dict[str, Any]:
        """Index a document"""
        document["zone_id"] = zone_id

        # Generate embeddings if enabled
        if self.embeddings_enabled and self.embedder:
            try:
                document = self.embedder.embed_document(document, embed_schema=True)
            except Exception as e:
                print(f"⚠️  Embedding generation failed (non-critical): {e}")

        return self._execute_with_fallback("index_document", document)

    def index_document_dual_parallel(
        self,
        document: Dict[str, Any],
        zone_id: str = "default",
        tags: Optional[List[str]] = None,
        auto_timestamp: bool = True
    ) -> Dict[str, Any]:
        """
        Index document to BOTH Elasticsearch AND Whoosh in parallel.

        This is for 'remember' functionality where web pages should be:
        - Indexed in Whoosh (fast, temporary browsing)
        - Indexed in Elasticsearch (permanent, larger datasets)
        - Both happen simultaneously using threading

        Args:
            document: Document to index
            zone_id: Zone to index into (default: "default")
            tags: Optional tags to add (e.g., ["#remembered", "#important"])
            auto_timestamp: Automatically add timestamp (default: True)

        Returns:
            Dict with results from both backends
        """
        import threading
        from datetime import datetime

        # Prepare document
        document["zone_id"] = zone_id

        # Add automatic timestamp if requested
        if auto_timestamp:
            if "timestamp" not in document:
                document["timestamp"] = datetime.now().isoformat()
            if "indexed_at" not in document:
                document["indexed_at"] = datetime.now().isoformat()

        # Add tags if provided
        if tags:
            existing_tags = document.get("tags", [])
            # Ensure tags start with # if not already
            normalized_tags = [tag if tag.startswith("#") else f"#{tag}" for tag in tags]
            # Merge with existing tags
            all_tags = list(set(existing_tags + normalized_tags))
            document["tags"] = all_tags

        # Generate embeddings if enabled (do this once before parallel indexing)
        if self.embeddings_enabled and self.embedder:
            try:
                document = self.embedder.embed_document(document, embed_schema=True)
            except Exception as e:
                print(f"⚠️  Embedding generation failed (non-critical): {e}")

        # Check which backends are available
        if not (self.elasticsearch_available or self.whoosh_available):
            raise RuntimeError("No backends available for indexing")

        results = {
            "elasticsearch": None,
            "whoosh": None,
            "success": False,
            "errors": []
        }

        def index_to_elasticsearch():
            """Thread function to index to Elasticsearch"""
            if not self.elasticsearch_available:
                return
            try:
                result = self.elasticsearch_backend.index_document(document)
                results["elasticsearch"] = result
                print(f"✅ Elasticsearch indexed: {result.get('_id', 'unknown')}")
            except Exception as e:
                error_msg = f"Elasticsearch indexing failed: {e}"
                results["errors"].append(error_msg)
                print(f"❌ {error_msg}")

        def index_to_whoosh():
            """Thread function to index to Whoosh"""
            if not self.whoosh_available:
                return
            try:
                result = self.whoosh_backend.index_document(document)
                results["whoosh"] = result
                print(f"✅ Whoosh indexed: {result.get('_id', 'unknown')}")
            except Exception as e:
                error_msg = f"Whoosh indexing failed: {e}"
                results["errors"].append(error_msg)
                print(f"❌ {error_msg}")

        # Create threads
        threads = []

        if self.elasticsearch_available:
            es_thread = threading.Thread(target=index_to_elasticsearch, name="ES-Index")
            threads.append(es_thread)

        if self.whoosh_available:
            whoosh_thread = threading.Thread(target=index_to_whoosh, name="Whoosh-Index")
            threads.append(whoosh_thread)

        # Start all threads (parallel execution)
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Update statistics
        if results["elasticsearch"] and results["whoosh"]:
            self.stats["dual_indexed"] += 1

        # Mark as successful if at least one backend succeeded
        results["success"] = bool(results["elasticsearch"] or results["whoosh"])

        # Return primary result (prefer Elasticsearch, fallback to Whoosh)
        if results["elasticsearch"]:
            results["_backend"] = "elasticsearch"
            results["_id"] = results["elasticsearch"].get("_id")
        elif results["whoosh"]:
            results["_backend"] = "whoosh"
            results["_id"] = results["whoosh"].get("_id")

        return results

    # === Search Operations ===

    def search_keyword(
        self,
        query: str,
        zone_id: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """BM25 keyword search"""
        return self._execute_with_fallback("search_keyword", query, zone_id, doc_type, limit)

    def search_vector(
        self,
        query_vector: List[float],
        zone_id: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Vector similarity search"""
        # Check if backend supports vectors
        backend, backend_name = self._get_backend(prefer_elastic=config.PREFER_ELASTIC)

        if backend_name == "whoosh":
            print("⚠️  Vector search not available in Whoosh, falling back to keyword search")
            # Fall back to keyword search (convert vector to text query - simplified)
            return self.search_keyword("", zone_id, doc_type, limit)

        return self._execute_with_fallback("search_vector", query_vector, zone_id, doc_type, limit)

    def search_hybrid(
        self,
        query_text: str,
        query_vector: List[float],
        zone_id: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Hybrid search (BM25 + vector)"""
        # Check if backend supports hybrid
        backend, backend_name = self._get_backend(prefer_elastic=config.PREFER_ELASTIC)

        if backend_name == "whoosh":
            print("⚠️  Hybrid search not available in Whoosh, using keyword search only")
            return self.search_keyword(query_text, zone_id, doc_type, limit)

        return self._execute_with_fallback("search_hybrid", query_text, query_vector, zone_id, doc_type, limit)

    # === Graph Operations ===

    def traverse_graph(
        self,
        start_entity_id: str,
        max_depth: int = 2,
        relation_filter: Optional[List[str]] = None,
        zone_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Traverse knowledge graph from starting entity"""
        return self._execute_with_fallback("traverse_graph", start_entity_id, max_depth, relation_filter, zone_id)

    # === Utility Operations ===

    def get_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID"""
        return self._execute_with_fallback("get_by_id", doc_id)

    def delete_by_id(self, doc_id: str) -> bool:
        """Delete document by ID"""
        return self._execute_with_fallback("delete_by_id", doc_id)

    def count(self, zone_id: Optional[str] = None, doc_type: Optional[str] = None) -> int:
        """Count documents"""
        return self._execute_with_fallback("count", zone_id, doc_type)

    # === Health & Stats ===

    def health_check(self) -> Dict[str, Any]:
        """Check health of all backends"""
        health = {
            "elasticsearch": {
                "available": self.elasticsearch_available,
                "status": "unknown"
            },
            "whoosh": {
                "available": self.whoosh_available,
                "status": "unknown"
            },
            "current_backend": self.current_backend
        }

        # Test Elasticsearch
        if self.elasticsearch_available:
            try:
                self.elasticsearch_backend.count()
                health["elasticsearch"]["status"] = "healthy"
            except Exception as e:
                health["elasticsearch"]["status"] = f"unhealthy: {e}"
                self.elasticsearch_available = False

        # Test Whoosh
        if self.whoosh_available:
            try:
                self.whoosh_backend.count()
                health["whoosh"]["status"] = "healthy"
            except Exception as e:
                health["whoosh"]["status"] = f"unhealthy: {e}"
                self.whoosh_available = False

        return health

    def get_stats(self) -> Dict[str, Any]:
        """Get backend statistics"""
        return {
            **self.stats,
            "elasticsearch_available": self.elasticsearch_available,
            "whoosh_available": self.whoosh_available,
            "current_backend": self.current_backend,
            "fallback_rate": (
                self.stats["fallbacks"] / max(1, self.stats["elasticsearch_calls"] + self.stats["whoosh_calls"])
            ) * 100 if self.stats["fallbacks"] > 0 else 0.0
        }

    def switch_backend(self, backend: Literal["elasticsearch", "whoosh"]):
        """
        Manually switch active backend

        Args:
            backend: "elasticsearch" or "whoosh"
        """
        if backend == "elasticsearch" and self.elasticsearch_available:
            self.current_backend = "elasticsearch"
            print("✅ Switched to Elasticsearch")
        elif backend == "whoosh" and self.whoosh_available:
            self.current_backend = "whoosh"
            print("✅ Switched to Whoosh")
        else:
            raise ValueError(f"Backend {backend} is not available")

    def sync_backends(self):
        """
        Synchronize data between backends

        Copies all data from primary to backup
        """
        if not (self.elasticsearch_available and self.whoosh_available):
            print("⚠️  Both backends must be available for sync")
            return

        print("🔄 Syncing backends...")

        # Determine source and target
        if config.PREFER_ELASTIC:
            source = self.elasticsearch_backend
            target = self.whoosh_backend
            source_name = "Elasticsearch"
            target_name = "Whoosh"
        else:
            source = self.whoosh_backend
            target = self.elasticsearch_backend
            source_name = "Whoosh"
            target_name = "Elasticsearch"

        try:
            # Get all documents from source
            # This is a simplified version - real implementation would need pagination
            count = source.count()
            print(f"📊 Found {count} documents in {source_name}")

            # TODO: Implement actual sync logic with pagination
            print(f"⚠️  Full sync not yet implemented")

        except Exception as e:
            print(f"❌ Sync failed: {e}")

    def __repr__(self):
        """String representation"""
        return (
            f"UnifiedBackend("
            f"primary={'Elasticsearch' if config.PREFER_ELASTIC else 'Whoosh'}, "
            f"elastic={'✓' if self.elasticsearch_available else '✗'}, "
            f"whoosh={'✓' if self.whoosh_available else '✗'}, "
            f"dual_indexing={'✓' if config.ENABLE_BACKUP_INDEXING else '✗'}"
            f")"
        )


# Singleton instance
_backend_instance = None


def get_unified_backend() -> UnifiedBackend:
    """Get singleton UnifiedBackend instance"""
    global _backend_instance
    if _backend_instance is None:
        _backend_instance = UnifiedBackend()
    return _backend_instance
