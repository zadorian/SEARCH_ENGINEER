import os
import uuid
import logging
import sys
from pathlib import Path
from elastic_manager import ElasticManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Ingester")

# PDF Extraction Libraries
try:
    from unstructured.partition.pdf import partition_pdf
    UNSTRUCTURED_AVAILABLE = True
except ImportError:
    UNSTRUCTURED_AVAILABLE = False

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

class Ingester:
    def __init__(self, index_name="jester_atoms"):
        self.elastic = ElasticManager(index_name=index_name)

    def extract_pages_from_pdf(self, file_path: Path):
        """Generator that yields text page-by-page (or element-by-element)."""
        try:
            # Priority 1: Unstructured (High Quality)
            if UNSTRUCTURED_AVAILABLE:
                logger.info(f"Using 'unstructured' to parse {file_path.name} (High Quality)")
                try:
                    elements = partition_pdf(filename=str(file_path))
                    # Yield grouped text to simulate pages/chunks
                    chunk = ""
                    for el in elements:
                        chunk += str(el) + "\n\n"
                        if len(chunk) > 2000: # Yield every ~2KB
                            yield chunk
                            chunk = ""
                    if chunk:
                        yield chunk
                    return # Stop here if successful
                except Exception as e:
                    logger.warning(f"Unstructured failed ({e}), falling back to pypdf.")

            # Priority 2: PyPDF (Streaming/Fast)
            if PYPDF_AVAILABLE:
                logger.info(f"Using 'pypdf' to parse {file_path.name} (Fast Stream)")
                import pypdf
                with open(file_path, 'rb') as f:
                    reader = pypdf.PdfReader(f)
                    total_pages = len(reader.pages)
                    logger.info(f"Streaming {total_pages} pages...")
                    for i, page in enumerate(reader.pages):
                        text = page.extract_text()
                        if text:
                            yield text + "\n\n"
            else:
                logger.error("No PDF library found (unstructured or pypdf).")
                yield ""
                
        except Exception as e:
            logger.error(f"Error streaming PDF {file_path.name}: {e}")
            yield ""

    def ingest_text(self, text: str, source_name="Context", batch_size=100):
        """
        Ingest raw text content directly.
        """
        if not text:
            return 0
            
        logger.info(f"Ingesting text source: {source_name} ({len(text)} chars)")
        
        total_atoms = 0
        batch = []
        
        # Naive split by double newline
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        
        for idx, para in enumerate(paragraphs):
            prev_context = paragraphs[idx-1] if idx > 0 else ""
            
            atom = {
                "atom_id": str(uuid.uuid4()),
                "content": para,
                "previous_context": prev_context,
                "source_file": source_name,
                "source_location": f"para_{idx}",
                "assigned_topics": [],
                "status": "pending",
                "metadata": {
                    "type": "injected_context"
                }
            }
            batch.append(atom)
            
            if len(batch) >= batch_size:
                self.elastic.index_atoms(batch)
                total_atoms += len(batch)
                batch = []
                
        if batch:
            self.elastic.index_atoms(batch)
            total_atoms += len(batch)
            
        return total_atoms

    def ingest_search_results(self, results: list, batch_size=100):
        """
        Ingest a list of search results (dicts with 'content', 'url', 'title').
        Acts as a multi-file ingestion stream.
        """
        logger.info(f"Ingesting {len(results)} search results...")
        
        total_atoms = 0
        batch = []
        
        for result in results:
            content = result.get('content', '')
            source_url = result.get('url', 'unknown_url')
            source_title = result.get('title', 'Unknown Title')
            
            if not content:
                continue
                
            # Split content into paragraphs (naive splitting)
            # Use double newline as primary separator
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
            
            for idx, para in enumerate(paragraphs):
                # Context: previous paragraph
                prev_context = paragraphs[idx-1] if idx > 0 else ""
                
                atom = {
                    "atom_id": str(uuid.uuid4()),
                    "content": para,
                    "previous_context": prev_context,
                    "source_file": source_title, # Use title as 'file' name
                    "source_location": source_url, # Use URL as location
                    "assigned_topics": [],
                    "status": "pending",
                    "metadata": {
                        "type": "search_result",
                        "url": source_url,
                        "timestamp": result.get('timestamp')
                    }
                }
                batch.append(atom)
                
                if len(batch) >= batch_size:
                    self.elastic.index_atoms(batch)
                    total_atoms += len(batch)
                    batch = []
                    
        # Flush remaining
        if batch:
            self.elastic.index_atoms(batch)
            total_atoms += len(batch)
            
        return total_atoms

    def ingest_file(self, file_path_str, batch_size=100):
        file_path = Path(file_path_str)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return 0

        logger.info(f"Ingesting {file_path}...")
        
        total_atoms = 0
        batch = []
        atom_idx = 0

        # Stream content source
        content_stream = []
        if file_path.suffix.lower() == '.pdf':
            content_stream = self.extract_pages_from_pdf(file_path)
        else:
            # Text/Markdown: Read chunks
            def text_generator():
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    while True:
                        chunk = f.read(4096) # 4KB chunks
                        if not chunk: break
                        yield chunk
            content_stream = text_generator()

        # Process stream
        buffer = ""
        
        for chunk in content_stream:
            buffer += chunk
            
            # Split buffer into paragraphs
            while '\n\n' in buffer:
                split_idx = buffer.find('\n\n')
                para = buffer[:split_idx].strip()
                buffer = buffer[split_idx+2:]
                
                if para:
                    # Simple context window: just the last atom text
                    prev_context = ""
                    if batch:
                        prev_context = batch[-1]['content']
                    
                    atom = {
                        "atom_id": str(uuid.uuid4()),
                        "content": para,
                        "previous_context": prev_context, 
                        "source_file": file_path.name,
                        "source_location": f"sequence_{atom_idx}",
                        "assigned_topics": [],
                        "status": "pending"
                    }
                    batch.append(atom)
                    atom_idx += 1
                    
                    if len(batch) >= batch_size:
                        self.elastic.index_atoms(batch)
                        total_atoms += len(batch)
                        batch = [] # Clear batch
        
        # Flush remaining buffer
        if buffer.strip():
            atom = {
                "atom_id": str(uuid.uuid4()),
                "content": buffer.strip(),
                "previous_context": batch[-1]['content'] if batch else "",
                "source_file": file_path.name,
                "source_location": f"sequence_{atom_idx}",
                "assigned_topics": [],
                "status": "pending"
            }
            batch.append(atom)

        # Flush final batch
        if batch:
            self.elastic.index_atoms(batch)
            total_atoms += len(batch)
            
        return total_atoms

if __name__ == "__main__":
    # Hack for local module import if run directly
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    
    if len(sys.argv) > 1:
        ingester = Ingester()
        count = ingester.ingest_file(sys.argv[1])
        print(f"Ingested {count} atoms.")
    else:
        print("Usage: python ingester.py <file_path>")