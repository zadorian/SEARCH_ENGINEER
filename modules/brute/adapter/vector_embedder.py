"""
CyMonides 2.0 - Vector Embedding System
Generates embeddings for content, schemas, and metadata for semantic search
"""

from typing import Dict, List, Any, Optional
from openai import OpenAI
from config.unified_config import config
import json


class VectorEmbedder:
    """
    Vector Embedding System

    Generates embeddings for multiple aspects:
    1. Content embeddings - Full text of entities/documents
    2. Schema embeddings - Field names and structure
    3. Metadata embeddings - Tags, categories, types

    This enables semantic search over:
    - "Find entities with contact information" → matches email/phone fields
    - "Find entities with employment history" → matches jobs/positions
    - "Find documents about quantum computing" → semantic content match
    """

    def __init__(self):
        """Initialize embedder"""
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY required for embeddings")

        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.model = "text-embedding-ada-002"
        self.dimensions = config.VECTOR_DIMENSIONS

    def embed_document(self, doc: Dict[str, Any], embed_schema: bool = True) -> Dict[str, Any]:
        """
        Generate all embeddings for a document

        Args:
            doc: Document to embed
            embed_schema: Also generate schema embedding

        Returns:
            Document with added embedding fields
        """
        doc_type = doc.get("doc_type", "document")

        # 1. Content embedding (main semantic search)
        content_text = self._extract_content_for_embedding(doc, doc_type)
        if content_text:
            doc["content_vector"] = self._generate_embedding(content_text)

        # 2. Schema embedding (semantic field search)
        if embed_schema:
            schema_text = self._extract_schema_for_embedding(doc)
            if schema_text:
                doc["schema_vector"] = self._generate_embedding(schema_text)

        # 3. Metadata embedding (semantic type/category search)
        metadata_text = self._extract_metadata_for_embedding(doc)
        if metadata_text:
            doc["metadata_vector"] = self._generate_embedding(metadata_text)

        return doc

    def _extract_content_for_embedding(self, doc: Dict[str, Any], doc_type: str) -> str:
        """
        Extract main content text for embedding

        For entities: name + description + observations
        For documents: title + content
        For relations: relation description
        """
        parts = []

        if doc_type == "entity":
            # Entity name (most important)
            if name := doc.get("name"):
                parts.append(f"Name: {name}")

            # Entity type
            if entity_type := doc.get("entity_type"):
                parts.append(f"Type: {entity_type}")

            # Description
            if desc := doc.get("description"):
                parts.append(f"Description: {desc}")

            # Key fields (email, phone, etc.)
            for field in ["email", "phone", "address", "website", "linkedin"]:
                if value := doc.get(field):
                    parts.append(f"{field}: {value}")

            # Observations (rich context)
            if observations := doc.get("observations"):
                obs_texts = []
                for obs in observations[:10]:  # Limit to top 10
                    if isinstance(obs, dict):
                        obs_texts.append(obs.get("text", ""))
                    elif isinstance(obs, str):
                        obs_texts.append(obs)
                if obs_texts:
                    parts.append("Observations: " + " ".join(obs_texts))

        elif doc_type == "document":
            # Document title
            if title := doc.get("title"):
                parts.append(f"Title: {title}")

            # Document content (truncate if very long)
            if content := doc.get("content"):
                content_text = content[:2000]  # First 2000 chars
                parts.append(f"Content: {content_text}")

        elif doc_type == "relation":
            # Relation description
            from_e = doc.get("from_entity", "")
            to_e = doc.get("to_entity", "")
            rel_type = doc.get("relation_type", "")
            parts.append(f"{from_e} {rel_type} {to_e}")

            # Relation properties
            if props := doc.get("properties"):
                parts.append(json.dumps(props))

        elif doc_type == "observation":
            # Observation text
            if text := doc.get("text"):
                parts.append(text)

        return "\n".join(parts)

    def _extract_schema_for_embedding(self, doc: Dict[str, Any]) -> str:
        """
        Extract schema/field information for embedding

        This enables queries like:
        - "Find entities with contact information"
        - "Find entities with employment history"
        - "Find entities with social media profiles"
        """
        parts = []

        # Document type
        doc_type = doc.get("doc_type", "")
        if doc_type:
            parts.append(f"document type: {doc_type}")

        # Entity type (for entities)
        if entity_type := doc.get("entity_type"):
            parts.append(f"entity type: {entity_type}")

        # Available fields (natural language description)
        field_descriptions = {
            "email": "has email address contact information",
            "phone": "has phone number contact information",
            "address": "has physical address location information",
            "website": "has website url web presence",
            "linkedin": "has linkedin profile social media",
            "twitter": "has twitter profile social media",
            "facebook": "has facebook profile social media",
            "github": "has github profile developer",
            "company": "has company affiliation employment",
            "job_title": "has job title position role employment",
            "education": "has education background academic",
            "skills": "has skills expertise capabilities",
            "certifications": "has certifications qualifications",
            "industry": "has industry sector category",
            "founded": "has founding date established",
            "employees": "has employee count size",
            "revenue": "has revenue financial information",
            "funding": "has funding investment information",
            "locations": "has locations offices geographic presence",
        }

        for field, description in field_descriptions.items():
            if field in doc:
                parts.append(description)

        # Observations (rich structured data indicator)
        if observations := doc.get("observations"):
            if len(observations) > 0:
                parts.append("has detailed observations rich context")

        # Relations (connectivity indicator)
        if relations := doc.get("relations"):
            if len(relations) > 0:
                parts.append("has relationships connections network")

        return " ".join(parts)

    def _extract_metadata_for_embedding(self, doc: Dict[str, Any]) -> str:
        """
        Extract metadata for embedding

        This enables queries like:
        - "Find tech companies"
        - "Find people in finance"
        - "Find entities related to AI"
        """
        parts = []

        # Tags (explicit categorization)
        if tags := doc.get("tags"):
            if isinstance(tags, list):
                parts.extend(tags)
            elif isinstance(tags, str):
                parts.append(tags)

        # Country (geographic)
        if country := doc.get("country"):
            parts.append(f"country: {country}")

        # Industry (for companies)
        if industry := doc.get("industry"):
            parts.append(f"industry: {industry}")

        # Categories (explicit)
        if categories := doc.get("categories"):
            if isinstance(categories, list):
                parts.extend(categories)

        # Entity type (semantic)
        if entity_type := doc.get("entity_type"):
            parts.append(entity_type)

        return " ".join(parts)

    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector from text

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return [0.0] * self.dimensions

        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text,
                encoding_format="float"
            )
            return response.data[0].embedding

        except Exception as e:
            print(f"⚠️  Embedding generation failed: {e}")
            return [0.0] * self.dimensions

    def batch_embed(
        self,
        texts: List[str],
        max_batch_size: int = None
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts efficiently

        Args:
            texts: List of texts to embed
            max_batch_size: Batch size (default from config)

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        max_batch_size = max_batch_size or config.VECTOR_EMBEDDING_BATCH_SIZE
        embeddings = []

        # Process in batches
        for i in range(0, len(texts), max_batch_size):
            batch = texts[i:i + max_batch_size]

            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=batch,
                    encoding_format="float"
                )

                batch_embeddings = [item.embedding for item in response.data]
                embeddings.extend(batch_embeddings)

            except Exception as e:
                print(f"⚠️  Batch embedding failed: {e}")
                # Fill with zero vectors for failed batch
                embeddings.extend([[0.0] * self.dimensions] * len(batch))

        return embeddings

    def search_by_schema(
        self,
        query: str,
        backend,
        zone_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search by schema description

        Example queries:
        - "Find entities with contact information"
        - "Find entities with employment history"
        - "Find companies with financial data"

        Args:
            query: Natural language schema query
            backend: Backend to search
            zone_id: Zone filter
            limit: Max results

        Returns:
            Matching documents
        """
        # Generate query embedding
        query_vector = self._generate_embedding(query)

        # Search using schema_vector field
        # Note: This requires backend support for schema_vector field
        # For now, fall back to content search
        print(f"🔍 Semantic schema search: {query}")
        return backend.search_vector(query_vector, zone_id, limit=limit)

    def enrich_existing_documents(
        self,
        backend,
        zone_id: Optional[str] = None,
        batch_size: int = 100
    ):
        """
        Add embeddings to existing documents that don't have them

        Args:
            backend: Backend instance
            zone_id: Optional zone filter
            batch_size: Process in batches
        """
        print("🔄 Enriching existing documents with embeddings...")

        # Get documents without embeddings
        # This is a simplified version - real implementation would need pagination
        try:
            count = backend.count(zone_id)
            print(f"📊 Found {count} documents")

            # TODO: Implement actual enrichment with backend.get_all()
            # For now, just a placeholder
            print("⚠️  Bulk enrichment not yet implemented")

        except Exception as e:
            print(f"❌ Enrichment failed: {e}")


# Singleton instance
_embedder_instance = None


def get_embedder() -> VectorEmbedder:
    """Get singleton VectorEmbedder instance"""
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = VectorEmbedder()
    return _embedder_instance
