import logging
import json
import subprocess
import time
import sys
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from gliner import GLiNER

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("EuropeanNewsEntityFetcher")

SASTRE_HOST = "176.9.2.153"
SASTRE_PASS = "qxXDgr49_9Hwxp"

class EuropeanNewsEntityFetcher:
    def __init__(self):
        try:
            logger.info("Loading GLiNER model...")
            self.gliner = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")
            logger.info("GLiNER loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load GLiNER: {e}")
            self.gliner = None

    def _extract_with_gliner(self, text):
        if not self.gliner:
            return []
        
        # Simple entity labels for news
        labels = ["person", "organization", "company", "location"] 
        try:
            entities = self.gliner.predict_entities(text, labels, threshold=0.5)
            # Normalize to match output format
            normalized = []
            for e in entities:
                normalized.append({
                    "entity_text": e["text"],
                    "entity_type": e["label"].upper(),
                    "confidence": e["score"],
                    "extractor": "gliner"
                })
            return normalized
        except Exception as e:
            logger.error(f"GLiNER prediction failed: {e}")
            return []

    def _extract_with_qwen(self, text):
        logger.info("Triggering Qwen fallback...")
        # Truncate for Qwen to avoid token limits
        text = text[:4000].replace('"', '\"').replace("'", "\'")
        
        # UPDATED PROMPT as per user instructions
        prompt = f"""Extract company and person names from the following text. Return a JSON object with two arrays.

TEXT TO ANALYZE:
{text}

Respond with ONLY valid JSON in this exact format (replace with actual names found):
{{"companies": [], "people": []}}"""

        try:
            # Using sshpass to run ollama on remote host
            cmd = f"sshpass -p '{SASTRE_PASS}' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@{SASTRE_HOST} \"echo '{prompt}' | ollama run qwen3:0.6b --format json 2>/dev/null\""
            
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
            
            if result.returncode != 0:
                logger.error(f"Qwen SSH failed: {result.stderr}")
                return []

            entities = []
            try:
                data = json.loads(result.stdout.strip())
                # Skip placeholder examples - ADDED FILTER
                skip = {"company1", "company2", "person1", "person2", "example", "name1", "name2"}
                
                for company in data.get("companies", []):
                    if company and len(company) > 2 and company.lower() not in skip:
                        entities.append({"entity_text": company, "entity_type": "ORGANIZATION", "confidence": 0.8, "extractor": "qwen"})
                
                for person in data.get("people", []):
                    if person and len(person) > 2 and person.lower() not in skip:
                        entities.append({"entity_text": person, "entity_type": "PERSON", "confidence": 0.8, "extractor": "qwen"})
                        
            except json.JSONDecodeError:
                logger.error("Failed to parse Qwen JSON response")
                logger.debug(f"Raw output: {result.stdout}")
                pass
            
            if entities:
                logger.info(f"Qwen fallback: {len(entities)} entities found")
            else:
                logger.info("Qwen fallback: 0 entities found")
                
            return entities

        except Exception as e:
            logger.error(f"Qwen extraction error: {e}")
            return []

    def process_text(self, text):
        if not text.strip():
            return []
            
        entities = self._extract_with_gliner(text)
        
        if not entities:
            logger.info("GLiNER extracted 0 unique entities.")
            # Trigger fallback if GLiNER fails to find anything
            entities = self._extract_with_qwen(text)
        else:
            logger.info(f"GLiNER extracted {len(entities)} unique entities.")
            
        return entities

class NewsFetcher:
    def __init__(self):
        self.extractor = EuropeanNewsEntityFetcher()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def fetch_url(self, url):
        try:
            logger.info(f"Fetching {url}...")
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def extract_content(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        # Simple extraction of text from paragraphs
        paragraphs = soup.find_all('p')
        text = " ".join([p.get_text() for p in paragraphs])
        return text

    def run_austrian_news_search(self, query="Wirtschaft", pages=2):
        # Austrian sources from news.json
        sources = [
            {"name": "Bergfex", "template": "https://www.bergfex.at/suchen/?q={q}&page={page}"},
            # "Google News Austria" often blocks automated requests
            # Replaced blocking sources (Der Standard, Die Presse) with others found in news.json
            {"name": "Red Pandazine", "template": "https://redpandazine.at/?s={q}"}, # Note: Pagination might be different, but trying basic param
            {"name": "Zentrum Online", "template": "https://zentrum-online.at/?s={q}"}
        ]

        all_entities = []

        for source in sources:
            logger.info(f"--- Processing source: {source['name']} ---")
            for page in range(1, pages + 1):
                # Handle pagination if template supports it, else just run once for page 1
                if "{page}" in source['template']:
                    url = source['template'].format(q=query, page=page)
                else:
                    if page > 1: break # Skip subsequent pages if no pagination in template
                    url = source['template'].format(q=query)
                
                html = self.fetch_url(url)
                
                if html:
                    text = self.extract_content(html)
                    if len(text) < 100:
                        logger.warning(f"Not enough text content found on {url}")
                        continue
                        
                    logger.info(f"Extracted {len(text)} characters from {url}")
                    entities = self.extractor.process_text(text)
                    
                    for entity in entities:
                        entity['source'] = source['name']
                        entity['url'] = url
                        entity['page'] = page
                        all_entities.append(entity)
                
                # Polite delay
                time.sleep(2)

        return all_entities

if __name__ == "__main__":
    fetcher = NewsFetcher()
    entities = fetcher.run_austrian_news_search()
    
    print(json.dumps(entities, indent=2))
    logger.info(f"Total entities extracted: {len(entities)}")
