
import os
import json
import logging
from elasticsearch import Elasticsearch, AsyncElasticsearch
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class YoutubeBridge:
    """
    Bridge to the Cymonides YouTube Commons index in Elasticsearch.
    """
    def __init__(self, es_host=None, index_name="cymonides-2"):
        self.es_host = es_host or os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
        self.index_name = index_name
        self.es = AsyncElasticsearch([self.es_host])

    async def search_videos(self, query, limit=10):
        """
        Search for videos in the YouTube Commons index.
        """
        try:
            # Construct a simple multi-match query
            body = {
                "size": limit,
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["title", "description", "transcript", "channel"]
                    }
                }
            }
            
            response = await self.es.search(index=self.index_name, body=body)
            hits = response['hits']['hits']
            
            results = []
            for hit in hits:
                source = hit['_source']
                results.append({
                    "video_id": source.get("video_id"),
                    "title": source.get("title"),
                    "channel": source.get("channel"),
                    "score": hit['_score'],
                    "transcript_snippet": source.get("transcript")[:200] if source.get("transcript") else None
                })
            
            return results

        except Exception as e:
            logger.error(f"Error searching YouTube index: {e}")
            return []

    async def get_video_by_id(self, video_id):
        """
        Retrieve a specific video by ID.
        """
        try:
            body = {
                "query": {
                    "term": {
                        "video_id.keyword": video_id # Assumes video_id is keyword indexed or standard text
                    }
                }
            }
            # Fallback to match if keyword fails or field mapping varies
            
            response = await self.es.search(index=self.index_name, body=body)
            hits = response['hits']['hits']
            
            if hits:
                return hits[0]['_source']
            return None

        except Exception as e:
            logger.error(f"Error getting video {video_id}: {e}")
            return None

    async def close(self):
        await self.es.close()

# Synchronous wrapper if needed
class YoutubeBridgeSync:
    def __init__(self, es_host=None, index_name="cymonides-2"):
        self.es_host = es_host or os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
        self.index_name = index_name
        self.es = Elasticsearch([self.es_host])

    def search_videos(self, query, limit=10):
        try:
            body = {
                "size": limit,
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["title", "description", "transcript", "channel"]
                    }
                }
            }
            response = self.es.search(index=self.index_name, body=body)
            return [hit['_source'] for hit in response['hits']['hits']]
        except Exception as e:
            logger.error(f"Error searching YouTube index: {e}")
            return []
