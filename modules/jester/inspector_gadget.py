import sys
import os
import json
import asyncio
from pathlib import Path
import logging

# Setup logging
logger = logging.getLogger("Jester.Inspector")

# Path setup to reach sibling modules and project root
current_dir = os.path.dirname(os.path.abspath(__file__))
modules_dir = os.path.dirname(current_dir) # python-backend/modules
project_root = os.path.dirname(os.path.dirname(modules_dir)) # DRILL_SEARCH/drill-search-app

sys.path.append(modules_dir)
sys.path.append(project_root)

# Import Gemini LongText
try:
    from gemini_longtext import GeminiCLI, DirectConversation
    GEMINI_LONGTEXT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Gemini LongText not found: {e}")
    GEMINI_LONGTEXT_AVAILABLE = False

# Import LangExtract
try:
    from extractors.gemini_langextract import GeminiLangExtractor
    LANGEXTRACT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Gemini LangExtract not found: {e}")
    LANGEXTRACT_AVAILABLE = False

class InspectorGadget:
    """
    The Ultimate Hybrid: Combines Gemini (Long Context) and LangExtract
    to power-up Jester's sorting capabilities.
    """
    def __init__(self):
        # Use Gemini 3 Pro (Long Context) for the Sweep/Discovery phase.
        # Check for API keys first
        has_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        
        if GEMINI_LONGTEXT_AVAILABLE and has_key:
            try:
                self.longtext_cli = GeminiCLI(model="gemini-3-pro-preview")
            except Exception as e:
                logger.error(f"Failed to initialize GeminiCLI: {e}")
                self.longtext_cli = None
        else:
            if not has_key:
                logger.warning("Inspector Gadget disabled: No GOOGLE_API_KEY or GEMINI_API_KEY found.")
            self.longtext_cli = None
            
        self.lang_extractor = GeminiLangExtractor() if LANGEXTRACT_AVAILABLE else None

    def initial_sweep(self, file_path):
        """
        Uses Gemini 3 Pro (LongText) to read the whole doc and find aliases.
        """
        if not self.longtext_cli:
            logger.error("Inspector Gadget: Gemini Unavailable. Skipping sweep.")
            return {}
            
        logger.info(f"Sweeping {file_path} with Gemini 3 Pro (Ultimate Mode)...")
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            chat = DirectConversation(self.longtext_cli.client, self.longtext_cli.model, content)
            
            prompt = """
            Analyze this entire document. 
            Identify all KEY ENTITIES (People, Organizations).
            For each, list their PRIMARY NAME and any ALIASES (e.g. "J. Smith", "The CEO", "He" if clearly referring to them).
            
            Return strictly valid JSON:
            {
                "entities": [
                    {"name": "John Smith", "aliases": ["J. Smith", "The CEO", "He"]},
                    {"name": "EvilCorp", "aliases": ["The Company", "EC"]}
                ]
            }
            """
            response = chat.send(prompt)
            
            # Parse JSON
            clean_resp = response.replace('```json', '').replace('```', '').strip()
            start = clean_resp.find('{')
            end = clean_resp.rfind('}') + 1
            if start != -1 and end != 0:
                clean_resp = clean_resp[start:end]
                
            data = json.loads(clean_resp)
            count = len(data.get('entities', []))
            logger.info(f"Found {count} entities with aliases map.")
            return data
        except Exception as e:
            logger.error(f"Inspector Gadget failed: {e}")
            return {}

    def discover_topics(self, file_path):
        """
        Uses Gemini 3 Pro to read the doc and auto-generate topic definitions.
        """
        if not self.longtext_cli:
            logger.error("Inspector Gadget: Gemini Unavailable. Skipping discovery.")
            return {}
            
        logger.info(f"Discovering topics in {file_path} (Gemini 3 Pro)...")
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            chat = DirectConversation(self.longtext_cli.client, self.longtext_cli.model, content)
            
            prompt = """
            Analyze this document. Identify the 5-10 most critical THEMES or INVESTIGATIVE ANGLES.
            For each, provide a short Label and a precise Description of what constitutes evidence for it.
            
            Return strictly valid JSON:
            {
                "topics": {
                    "Financial Irregularities": "Any mention of off-book accounts, bribery, or shell companies.",
                    "Key Leadership": "Mentions of the CEO, board members, or key decision makers."
                }
            }
            """
            response = chat.send(prompt)
            
            clean_resp = response.replace('```json', '').replace('```', '').strip()
            start = clean_resp.find('{')
            end = clean_resp.rfind('}') + 1
            if start != -1 and end != 0:
                clean_resp = clean_resp[start:end]
                
            data = json.loads(clean_resp)
            topics = data.get("topics", {})
            logger.info(f"Discovered {len(topics)} topics.")
            return topics
        except Exception as e:
            logger.error(f"Topic discovery failed: {e}")
            return {}

    async def run_langextract(self, file_path):
        """
        Uses Gemini LangExtract (Gemini 2.0 Flash) for structured extraction.
        """
        if not self.lang_extractor:
            logger.error("Inspector Gadget: LangExtract unavailable (check 'extractors' module).")
            return {}
            
        logger.info(f"Running LangExtract on {file_path}...")
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            result = await self.lang_extractor.extract(content)
            
            entity_map = {}
            if hasattr(result, 'entities'):
                for ent in result.entities:
                    name = ent.text
                    label = ent.type.value if hasattr(ent.type, 'value') else str(ent.type)
                    
                    desc = f"Type: {label}"
                    if hasattr(ent, 'context') and ent.context:
                        desc += f" | {ent.context[:50]}..."
                    
                    if name not in entity_map:
                        entity_map[name] = [desc]
                    elif desc not in entity_map[name]:
                        entity_map[name].append(desc)
            
            logger.info(f"LangExtract found {len(entity_map)} unique entities.")
            return entity_map
            
        except Exception as e:
            logger.error(f"LangExtract failed: {e}")
            return {}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing Inspector Gadget...")
    ig = InspectorGadget()
    if ig.longtext_cli:
        print("✅ Gemini 3 Pro (LongText) Loaded")
    else:
        print("❌ Gemini 3 Pro Failed to Load")
