import logging
import sys

# Setup logging
logger = logging.getLogger("Jester")

try:
    from gliner import GLiNER
    GLINER_AVAILABLE = True
except ImportError:
    GLINER_AVAILABLE = False
    # Don't log warning on import, only on usage attempt

class GlinerExtractor:
    def __init__(self, model_name="urchade/gliner_multi-v2.1"):
        self.available = GLINER_AVAILABLE
        self.model = None
        if self.available:
            try:
                logger.info(f"Loading GLiNER model: {model_name}...")
                self.model = GLiNER.from_pretrained(model_name)
                logger.info("GLiNER model loaded successfully.")
            except Exception as e:
                logger.warning(f"Failed to load GLiNER model: {e}")
                self.available = False

    def extract(self, text):
        """
        Extracts entities and returns them in the 'alias_map' format expected by Jester.
        """
        if not self.available:
            logger.warning("GLiNER is not available. Please install it: 'pip install gliner'")
            return {}
        
        # Truncate text if too huge (GLiNER handles chunks but let's be safe)
        # GLiNER is relatively fast but huge texts can slow it down.
        # We'll pass the full text; GLiNER usually handles it by sliding window or we rely on the user providing reasonable chunks.
        # Actually, splitting huge text is better.
        
        labels = ["person", "organization", "email", "phone number", "location"]
        
        try:
            # Predict
            entities = self.model.predict_entities(text, labels, threshold=0.3)
            
            # Format for Jester's alias_map
            # {"Entity Name": ["Label: person"]}
            entity_map = {}
            for ent in entities:
                name = ent["text"]
                label = ent["label"]
                if name not in entity_map:
                    entity_map[name] = [f"Type: {label}"]
            
            logger.info(f"GLiNER extracted {len(entity_map)} unique entities.")
            return entity_map
            
        except Exception as e:
            logger.error(f"GLiNER extraction failed: {e}")
            return {}

if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)
    extractor = GlinerExtractor()
    text = "John Smith from Apple Inc. called 555-0199."
    print(extractor.extract(text))