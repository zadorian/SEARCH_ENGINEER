from elasticsearch import Elasticsearch, helpers
import uuid
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ElasticManager")

class ElasticManager:
    def __init__(self, index_name="jester_atoms"):
        self.index_name = index_name
        
        # Load Config with fallbacks
        self.host = os.getenv("ELASTIC_URL", os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"))
        self.user = os.getenv("ELASTIC_USER", os.getenv("ELASTICSEARCH_USER"))
        self.password = os.getenv("ELASTIC_PASSWORD", os.getenv("ELASTICSEARCH_PASSWORD"))
        
        # Configure Auth
        auth = None
        if self.user and self.password:
            auth = (self.user, self.password)
            
        # Initialize Client
        self.client = Elasticsearch(
            self.host,
            basic_auth=auth,
            request_timeout=30,
            retry_on_timeout=True,
            max_retries=3
        )
        
        # Ensure Index Exists
        try:
            if not self.client.ping():
                logger.warning(f"⚠️ Could not ping Elasticsearch at {self.host}")
            self.ensure_index()
        except Exception as e:
            logger.error(f"❌ Elasticsearch initialization failed: {e}")

    def ensure_index(self):
        if not self.client.indices.exists(index=self.index_name):
            mapping = {
                "mappings": {
                    "properties": {
                        "atom_id": {"type": "keyword"},
                        "content": {"type": "text"},
                        "previous_context": {"type": "text"},
                        "source_file": {"type": "keyword"},
                        "source_location": {"type": "keyword"},
                        "assigned_topics": {"type": "keyword"},
                        "status": {"type": "keyword"},
                        "entities": {
                            "type": "nested",
                            "properties": {
                                "text": {"type": "keyword"},
                                "label": {"type": "keyword"}
                            }
                        },
                        "created_at": {"type": "date"}
                    }
                }
            }
            self.client.indices.create(index=self.index_name, body=mapping)
            logger.info(f"Created index {self.index_name}")
        else:
            # logger.info(f"Index {self.index_name} exists")
            pass

    def index_atoms(self, atoms):
        """
        Bulk index a list of atom dictionaries.
        """
        actions = []
        for atom in atoms:
            # Ensure timestamp
            if "created_at" not in atom:
                atom["created_at"] = datetime.utcnow().isoformat()
            
            action = {
                "_index": self.index_name,
                "_id": atom["atom_id"],
                "_source": atom
            }
            actions.append(action)
        
        if actions:
            helpers.bulk(self.client, actions)
            self.client.indices.refresh(index=self.index_name)
            logger.info(f"Indexed {len(atoms)} atoms to {self.index_name}")

    def get_pending_atoms(self, limit=100):
        query = {
            "query": {
                "term": { "status": "pending" }
            },
            "size": limit
        }
        response = self.client.search(index=self.index_name, body=query)
        return [hit["_source"] for hit in response["hits"]["hits"]]

    def update_atom_status(self, atom_id, topics, entities=None, status="classified"):
        """Updates atom with topics, entities, and status."""
        doc_update = {
            "assigned_topics": topics,
            "status": status
        }
        if entities is not None:
            doc_update["entities"] = entities

        self.client.update(
            index=self.index_name,
            id=atom_id,
            body={"doc": doc_update},
            refresh="wait_for"
        )

    def get_unassigned_atoms(self):
        query = {
             "query": {
                "bool": {
                    "should": [
                        {"term": { "status": "unassigned" }},
                        {"term": { "status": "error" }}
                    ],
                    "minimum_should_match": 1
                }
            },
            "size": 10000
        }
        response = self.client.search(index=self.index_name, body=query)
        return [hit["_source"] for hit in response["hits"]["hits"]]

    def get_atoms_by_topic(self, topic_id):
        query = {
             "query": {
                "term": { "assigned_topics": topic_id }
            },
            "size": 10000
        }
        response = self.client.search(index=self.index_name, body=query)
        return [hit["_source"] for hit in response["hits"]["hits"]]

    def clear_index(self):
        """
        DANGEROUS: Clears the index.
        
        SAFETY LOCK: This method will REFUSE to delete any index that does not
        start with 'jester_atoms'. This prevents accidental deletion of system
        indices or other project data.
        """
        # Safety check: Ensure we are only deleting Jester indices
        if not self.index_name.startswith("jester_atoms"):
            logger.error(f"❌ Refusing to clear index '{self.index_name}' (Safety Lock: Must start with 'jester_atoms')")
            return

        if self.client.indices.exists(index=self.index_name):
            self.client.indices.delete(index=self.index_name)
            self.ensure_index()
            logger.info(f"Cleared index {self.index_name}")

    def get_all_atoms(self):
        """Fetches all atoms from the index."""
        query = {
            "query": {
                "match_all": {}
            },
            "size": 10000 
        }
        response = self.client.search(index=self.index_name, body=query)
        return [hit["_source"] for hit in response["hits"]["hits"]]

    def get_atoms_by_entity(self, entity_text: str, entity_label: str):
        """Fetches atoms that contain a specific entity."""
        query = {
            "query": {
                "nested": {
                    "path": "entities",
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"entities.text": entity_text}},
                                {"term": {"entities.label": entity_label}}
                            ]
                        }
                    }
                }
            },
            "size": 10000
        }
        response = self.client.search(index=self.index_name, body=query)
        return [hit["_source"] for hit in response["hits"]["hits"]]

    def search_knowledge_graph(self, query_text: str, limit: int = 10, project_id: str = None):
        """
        Searches the main Knowledge Graph (Cymonides) for context.
        If project_id is provided, searches that specific project index.
        Otherwise, searches all cymonides-1-* indices (global search).
        """
        if project_id:
            graph_index = f"cymonides-1-{project_id}"
        else:
            logger.info("Searching global knowledge graph (wildcard)")
            graph_index = "cymonides-1-*"

        # Check existence only if specific index (wildcards always "exist" query-wise or throw distinct error)
        if project_id and not self.client.indices.exists(index=graph_index):
            logger.warning(f"Graph index '{graph_index}' does not exist.")
            return []

        query = {
            "query": {
                "multi_match": {
                    "query": query_text,
                    "fields": ["label^2", "content", "metadata.content", "canonicalValue", "metadata.description"],
                    "type": "best_fields"
                }
            },
            "size": limit
        }

        try:
            response = self.client.search(index=graph_index, body=query)
            return [hit["_source"] for hit in response["hits"]["hits"]]
        except Exception as e:
            logger.error(f"Graph search failed: {e}")
            return []