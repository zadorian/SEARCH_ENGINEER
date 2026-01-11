from docx import Document
import os
import json
from xml.etree import ElementTree
from whoosh.index import create_in
from whoosh.fields import *
from whoosh.qparser import QueryParser
from pathlib import Path
import sys

def process_docx(input_file):
    """Process a single DOCX file and return structured data"""
    doc = Document(input_file)
    
    doc_data = {
        "metadata": {
            "filename": os.path.basename(input_file),
            "title": "",
        },
        "paragraphs": [],
        "footnotes": {},
    }
    
    # Get footnotes
    for rel in doc.part.rels.values():
        if rel.reltype == 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes':
            footnote_part = rel.target_part
            xml = footnote_part.blob.decode('utf-8')
            root = ElementTree.fromstring(xml)
            
            for footnote in root.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}footnote'):
                footnote_id = footnote.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id')
                if footnote_id and footnote_id != '-1':
                    text_elements = footnote.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t')
                    footnote_text = ' '.join(elem.text for elem in text_elements if elem.text)
                    doc_data["footnotes"][footnote_id] = {
                        "text": footnote_text.strip(),
                        "references": []
                    }

    # Get main text with footnote references
    for para_num, paragraph in enumerate(doc.element.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p')):
        text = ''
        footnotes_in_para = []
        
        for run in paragraph.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}r'):
            footnote_ref = run.find('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}footnoteReference')
            if footnote_ref is not None:
                ref_id = footnote_ref.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id')
                text += f'[{ref_id}]'
                footnotes_in_para.append(ref_id)
                doc_data["footnotes"][ref_id]["references"].append(para_num)
            for t in run.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
                if t.text:
                    text += t.text
        
        if text.strip():
            para_data = {
                "text": text,
                "footnotes": footnotes_in_para,
                "paragraph_number": para_num
            }
            doc_data["paragraphs"].append(para_data)
            
            if not doc_data["metadata"]["title"] and para_num == 0:
                doc_data["metadata"]["title"] = text.strip()
    
    return doc_data

def create_whoosh_index(index_dir):
    """Create Whoosh index schema"""
    schema = Schema(
        title=TEXT(stored=True),
        filename=ID(stored=True),
        paragraph=TEXT(stored=True),
        paragraph_number=NUMERIC(stored=True),
        footnotes=KEYWORD(stored=True, commas=True),
        footnote_texts=TEXT(stored=True),
        source_urls=TEXT(stored=True)
    )
    
    if not os.path.exists(index_dir):
        os.makedirs(index_dir)
    
    return create_in(index_dir, schema)

def index_document(writer, doc_data):
    """Index a document's paragraphs in Whoosh"""
    for para in doc_data["paragraphs"]:
        # Collect footnote texts and URLs for this paragraph
        footnote_texts = []
        urls = []
        for fn_id in para["footnotes"]:
            if fn_id in doc_data["footnotes"]:
                fn_text = doc_data["footnotes"][fn_id]["text"]
                footnote_texts.append(f"[{fn_id}] {fn_text}")
                # Extract URLs from footnote text
                if "http" in fn_text:
                    urls.extend([word for word in fn_text.split() if word.startswith("http")])
        
        writer.add_document(
            title=doc_data["metadata"]["title"],
            filename=doc_data["metadata"]["filename"],
            paragraph=para["text"],
            paragraph_number=para["paragraph_number"],
            footnotes=",".join(para["footnotes"]),
            footnote_texts=" | ".join(footnote_texts),
            source_urls=" | ".join(urls)
        )

def main():
    input_dir = "/Users/brain/Report_Library/consolidated_docx/Consolidated"
    json_dir = os.path.expanduser("~/Report_Library/processed_docs")
    index_dir = os.path.expanduser("~/Report_Library/search_index")
    
    # Clean up existing index
    if os.path.exists(index_dir):
        print(f"Removing existing index at {index_dir}")
        import shutil
        shutil.rmtree(index_dir)
    
    # Create output directories
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(index_dir, exist_ok=True)
    
    # Create Whoosh index
    ix = create_whoosh_index(index_dir)
    
    # Process all DOCX files
    docx_files = list(Path(input_dir).glob("*.docx"))
    print(f"Found {len(docx_files)} documents to process")
    
    with ix.writer() as writer:
        for docx_file in docx_files:
            try:
                print(f"\nProcessing: {docx_file.name}")
                
                # Check if file exists and is readable
                if not docx_file.exists():
                    print(f"  Error: File not found - {docx_file}")
                    continue
                    
                # Process document
                doc_data = process_docx(str(docx_file))
                if not doc_data:
                    print(f"  Error: Failed to process document")
                    continue
                
                # Save JSON
                json_path = os.path.join(json_dir, f"{docx_file.stem}.json")
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(doc_data, f, indent=2, ensure_ascii=False)
                
                # Index document
                index_document(writer, doc_data)
                
                print(f"  Found {len(doc_data['footnotes'])} footnotes")
                print(f"  Processed {len(doc_data['paragraphs'])} paragraphs")
                
            except Exception as e:
                print(f"  Error processing {docx_file.name}: {str(e)}")
                continue

    print("\nIndexing complete!")

if __name__ == "__main__":
    main() 