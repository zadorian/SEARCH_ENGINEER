#!/usr/bin/env python3
"""
WikiMan Book Management System
Handles PDF upload, image extraction, and auto-image injection for reference materials
"""

import os
import sys
import re
import json
import fitz  # PyMuPDF - install with: pip install PyMuPDF
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging
from datetime import datetime

# Import OpenAI tools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'toolkit'))
from openai_assistants import (
    get_assistants_manager,
    create_thread_sync,
    add_message_sync,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WikiManBookManager:
    """Manages PDF books with images for WikiMan"""
    
    def __init__(self, context_dir: Path = Path("context")):
        """Initialize the book manager"""
        self.context_dir = context_dir
        self.books_dir = context_dir / "books"
        self.images_dir = context_dir / "book_images"
        self.catalog_file = context_dir / "book_catalog.json"
        
        # Create directories
        self.books_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing catalog
        self.catalog = self._load_catalog()
        
        # Get OpenAI manager
        self.manager = get_assistants_manager()
    
    def _load_catalog(self) -> Dict:
        """Load existing book catalog"""
        if self.catalog_file.exists():
            with open(self.catalog_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_catalog(self):
        """Save book catalog"""
        with open(self.catalog_file, 'w') as f:
            json.dump(self.catalog, f, indent=2)
    
    def extract_images_from_pdf(self, pdf_path: str, book_key: str) -> Dict[str, Dict]:
        """
        Extract all images from PDF and map them to figure references
        
        Returns:
            Dictionary mapping figure references to image info
        """
        logger.info(f"Extracting images from {pdf_path}")
        
        doc = fitz.open(pdf_path)
        figure_catalog = {}
        book_images_dir = self.images_dir / book_key
        book_images_dir.mkdir(exist_ok=True)
        
        # Track figure references across pages
        all_figures = []
        
        # First pass: collect all figure references
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            
            # Find various figure reference patterns
            patterns = [
                r'Figure (\d+\.\d+):\s*([^\n]+)',  # Figure 9.03: Caption
                r'Fig\. (\d+\.\d+):\s*([^\n]+)',   # Fig. 9.03: Caption
                r'Figure (\d+):\s*([^\n]+)',       # Figure 9: Caption
                r'Image (\d+\.\d+):\s*([^\n]+)',   # Image 9.03: Caption
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    fig_num, caption = match
                    all_figures.append({
                        'number': fig_num,
                        'caption': caption.strip(),
                        'page': page_num + 1,
                        'full_ref': f"Figure {fig_num}"
                    })
        
        logger.info(f"Found {len(all_figures)} figure references in text")
        
        # Second pass: extract images and match to figures
        image_count = 0
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                try:
                    # Extract image
                    xref = img[0]
                    pix = fitz.Pixmap(doc, xref)
                    
                    # Convert to PNG if needed
                    if pix.n - pix.alpha > 3:  # CMYK or other
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    
                    # Generate filename
                    # Try to match with figure reference on same page
                    figure_key = None
                    for fig in all_figures:
                        if fig['page'] == page_num + 1:
                            if figure_key is None:  # Take first unmatched figure on page
                                figure_key = fig['full_ref']
                                caption = fig['caption']
                                break
                    
                    if not figure_key:
                        figure_key = f"Page{page_num + 1}_Image{img_index + 1}"
                        caption = f"Image from page {page_num + 1}"
                    
                    # Save image
                    safe_key = figure_key.replace(' ', '_').replace('.', '_').replace(':', '')
                    img_path = book_images_dir / f"{safe_key}.png"
                    pix.save(str(img_path))
                    
                    # Add to catalog
                    figure_catalog[figure_key] = {
                        "local_path": str(img_path),
                        "page": page_num + 1,
                        "caption": caption,
                        "width": pix.width,
                        "height": pix.height,
                        "openai_file_id": None  # Will be filled when uploaded
                    }
                    
                    image_count += 1
                    logger.info(f"Extracted: {figure_key} from page {page_num + 1}")
                    
                    pix = None  # Free memory
                    
                except Exception as e:
                    logger.error(f"Error extracting image {img_index} from page {page_num}: {e}")
        
        doc.close()
        logger.info(f"Extracted {image_count} images total")
        return figure_catalog
    
    def upload_images_to_openai(self, figure_catalog: Dict[str, Dict]) -> Dict[str, Dict]:
        """
        Upload all extracted images to OpenAI
        
        Returns:
            Updated catalog with OpenAI file IDs
        """
        logger.info(f"Uploading {len(figure_catalog)} images to OpenAI")
        
        from openai import OpenAI
        client = OpenAI()
        
        for figure_key, info in figure_catalog.items():
            try:
                with open(info["local_path"], "rb") as img_file:
                    # Upload to OpenAI
                    uploaded_file = client.files.create(
                        file=img_file,
                        purpose="assistants"
                    )
                    
                    # Store the file_id
                    info["openai_file_id"] = uploaded_file.id
                    logger.info(f"Uploaded {figure_key}: {uploaded_file.id}")
                    
            except Exception as e:
                logger.error(f"Error uploading {figure_key}: {e}")
        
        return figure_catalog
    
    def add_book_to_wikiman(
        self, 
        pdf_path: str, 
        book_name: str,
        thread_manager = None
    ) -> str:
        """
        Complete process to add a book to WikiMan with image support
        
        Args:
            pdf_path: Path to the PDF file
            book_name: Human-readable name for the book
            thread_manager: WikiMan's JurisdictionThreadManager instance
            
        Returns:
            The book key to use for queries (e.g., "BOOK-OSINT-TECHNIQUES")
        """
        from openai import OpenAI
        client = OpenAI()
        
        book_key = f"BOOK-{book_name.upper().replace(' ', '-')}"
        logger.info(f"Adding book '{book_name}' as {book_key}")
        
        # Step 1: Extract images from PDF
        print(f"\n📚 Processing '{book_name}'...")
        print("   Step 1: Extracting images and figure references...")
        figure_catalog = self.extract_images_from_pdf(pdf_path, book_key)
        print(f"   ✅ Found {len(figure_catalog)} figures/images")
        
        # Step 2: Upload images to OpenAI
        print("   Step 2: Uploading images to OpenAI...")
        figure_catalog = self.upload_images_to_openai(figure_catalog)
        uploaded_count = sum(1 for info in figure_catalog.values() if info.get("openai_file_id"))
        print(f"   ✅ Uploaded {uploaded_count}/{len(figure_catalog)} images")
        
        # Step 3: Upload PDF for text search
        print("   Step 3: Uploading PDF for text search...")
        with open(pdf_path, 'rb') as f:
            pdf_file = client.files.create(
                file=f,
                purpose="assistants"
            )
        print(f"   ✅ PDF uploaded: {pdf_file.id}")
        
        # Step 4: Create vector store
        print("   Step 4: Creating vector store...")
        vector_store = client.beta.vector_stores.create(
            name=f"WikiMan: {book_name}",
            file_ids=[pdf_file.id]
        )
        print(f"   ✅ Vector store created: {vector_store.id}")
        
        # Step 5: Update assistant to include this vector store
        if thread_manager and hasattr(thread_manager, 'assistant_id'):
            print("   Step 5: Updating assistant with vector store...")
            try:
                client.beta.assistants.update(
                    assistant_id=thread_manager.assistant_id,
                    tool_resources={
                        "file_search": {
                            "vector_store_ids": [vector_store.id]
                        }
                    }
                )
                print(f"   ✅ Assistant updated")
            except Exception as e:
                logger.error(f"Could not update assistant: {e}")
                print(f"   ⚠️  Could not update assistant: {e}")
        
        # Step 6: Create dedicated thread if thread_manager provided
        thread_id = None
        if thread_manager:
            print("   Step 6: Creating dedicated thread...")
            thread = create_thread_sync()
            thread_id = thread['id']
            
            # Store in thread manager
            thread_manager.threads[book_key] = {
                'thread_id': thread_id,
                'type': 'reference_material',
                'book_name': book_name,
                'pdf_file_id': pdf_file.id,
                'vector_store_id': vector_store.id,
                'figure_catalog': figure_catalog,
                'created_at': datetime.now().isoformat(),
                'question_count': 0
            }
            thread_manager._save_threads()
            print(f"   ✅ Thread created: {thread_id}")
        
        # Step 7: Save to our catalog
        self.catalog[book_key] = {
            'book_name': book_name,
            'pdf_path': pdf_path,
            'pdf_file_id': pdf_file.id,
            'vector_store_id': vector_store.id,
            'thread_id': thread_id,
            'figure_catalog': figure_catalog,
            'added_date': datetime.now().isoformat()
        }
        self._save_catalog()
        
        print(f"\n✅ Book successfully added to WikiMan!")
        print(f"   📖 Query with: :{book_key}")
        print(f"   📸 Auto-image injection enabled for {len(figure_catalog)} figures")
        print(f"\n   Example: 'How do I use uBlock Origin? :{book_key}'")
        
        return book_key
    
    def get_figure_urls(self, book_key: str) -> List[Tuple[str, str]]:
        """
        Get a list of all figures and their local paths for manual upload
        
        Returns:
            List of (figure_reference, local_path) tuples
        """
        if book_key not in self.catalog:
            return []
        
        figure_catalog = self.catalog[book_key].get('figure_catalog', {})
        return [(ref, info['local_path']) for ref, info in figure_catalog.items()]
    
    def inject_images_in_response(self, response: str, book_key: str) -> List[Dict]:
        """
        Parse response for figure references and inject actual images
        
        Args:
            response: The assistant's text response
            book_key: The book being referenced
            
        Returns:
            List of content blocks with text and images interleaved
        """
        if book_key not in self.catalog:
            return [{"type": "text", "text": response}]
        
        figure_catalog = self.catalog[book_key].get('figure_catalog', {})
        
        # Find all figure references
        figure_pattern = r'(Figure \d+(?:\.\d+)?)'
        parts = re.split(figure_pattern, response)
        
        enhanced_content = []
        for part in parts:
            if re.match(figure_pattern, part):
                # This is a figure reference
                if part in figure_catalog and figure_catalog[part].get('openai_file_id'):
                    # Add the text reference
                    enhanced_content.append({
                        "type": "text",
                        "text": f"\n{part}: {figure_catalog[part]['caption']}\n"
                    })
                    # Add the actual image
                    enhanced_content.append({
                        "type": "image_file",
                        "image_file": {"file_id": figure_catalog[part]['openai_file_id']}
                    })
                    logger.info(f"Injected image for {part}")
                else:
                    # Figure not found or not uploaded
                    enhanced_content.append({
                        "type": "text",
                        "text": f"{part} [Image not available]"
                    })
            else:
                # Regular text
                if part:  # Skip empty strings
                    enhanced_content.append({
                        "type": "text",
                        "text": part
                    })
        
        return enhanced_content


def main():
    """Command-line interface for book management"""
    import argparse
    
    parser = argparse.ArgumentParser(description="WikiMan Book Manager")
    parser.add_argument("action", choices=["add", "list", "extract"], 
                      help="Action to perform")
    parser.add_argument("--pdf", help="Path to PDF file")
    parser.add_argument("--name", help="Name for the book")
    parser.add_argument("--book-key", help="Book key for operations")
    
    args = parser.parse_args()
    
    manager = WikiManBookManager()
    
    if args.action == "add":
        if not args.pdf or not args.name:
            print("Error: --pdf and --name required for add action")
            return
        
        if not Path(args.pdf).exists():
            print(f"Error: PDF file not found: {args.pdf}")
            return
        
        book_key = manager.add_book_to_wikiman(args.pdf, args.name)
        print(f"\nBook added successfully: {book_key}")
    
    elif args.action == "list":
        if not manager.catalog:
            print("No books in catalog")
        else:
            print("\n📚 WikiMan Book Catalog:")
            for book_key, info in manager.catalog.items():
                print(f"\n   {book_key}:")
                print(f"      Name: {info['book_name']}")
                print(f"      Added: {info['added_date'][:10]}")
                print(f"      Images: {len(info.get('figure_catalog', {}))}")
    
    elif args.action == "extract":
        if not args.book_key:
            print("Error: --book-key required for extract action")
            return
        
        urls = manager.get_figure_urls(args.book_key)
        if not urls:
            print(f"No book found with key: {args.book_key}")
        else:
            print(f"\n📸 Extracted images for {args.book_key}:")
            for ref, path in urls:
                print(f"   {ref}: {path}")


if __name__ == "__main__":
    main()