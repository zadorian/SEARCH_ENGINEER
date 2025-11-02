#!/usr/bin/env python3
"""
PDF to Markdown Converter using Claude Native OCR with Files API support
Integrates with entity_extraction_realtime_stream.py for high-quality PDF processing
"""

import os
import sys
import base64
import tempfile
from pathlib import Path
from typing import Optional, Tuple, List
import asyncio
import anthropic
from anthropic import Anthropic
from anthropic.types.beta.messages.batch_create_params import Request
from anthropic.types.beta.message_create_params import MessageCreateParamsNonStreaming
from dotenv import load_dotenv
import time
import signal
from contextlib import contextmanager
import json
import concurrent.futures
from threading import Lock

# Load environment variables from absolute path
env_path = Path('/Users/brain/GARSON/.env')
load_dotenv(env_path)

# Import model constants - CRITICAL: Use consistent models across the system
from ABSOLUTE_MODEL_CONSTANTS import get_claude_model, CLAUDE_OPUS_4

# Import existing converter interface
from pdf_to_markdown_converter import PDFToMarkdownConverter

@contextmanager
def timeout(seconds):
    """Context manager for timing out operations"""
    def signal_handler(signum, frame):
        raise TimeoutError(f"Operation timed out after {seconds} seconds")
    
    # Set up the signal handler
    old_handler = signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

class ClaudePDFToMarkdownConverter:
    """
    PDF to Markdown converter using Claude's native OCR capabilities.
    Supports both direct document blocks and Files API for better performance.
    """
    
    def __init__(self, use_files_api: bool = False, silent: bool = False, use_batch: bool = False, use_parallel: bool = False):
        """Initialize the Claude PDF converter
        
        Args:
            use_files_api: Whether to use Files API (default: False)
            silent: Whether to suppress progress messages (default: False)
            use_batch: Whether to use batch API for cost savings (default: False)
            use_parallel: Whether to use parallel processing for speed (default: False)
        """
        self.silent = silent
        self.use_batch = use_batch
        self.use_parallel = use_parallel
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
        
        self.client = Anthropic(api_key=api_key)
        self.use_files_api = use_files_api
        # Use a temp directory for output
        self.temp_dir = Path(tempfile.mkdtemp())
        
        if not self.silent:
            print(f"🔧 Claude PDF converter initialized (API key: {'*' * 8}{api_key[-4:]})")
            print(f"📁 Using {'Files API' if use_files_api else 'direct document blocks'}")
            if use_batch:
                print(f"⚡ Using BATCH API for faster parallel processing")
    
    def _log(self, message: str, force_stderr: bool = False):
        """Log a message if not in silent mode"""
        if not self.silent:
            print(message)
        elif force_stderr:
            # Always log to stderr for debugging even in silent mode
            print(message, file=sys.stderr)
        
    def _upload_pdf_to_files_api(self, pdf_path: Path) -> Tuple[str, str]:
        """Upload PDF to Files API and return file_id and cleanup function
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Tuple of (file_id, original_filename)
        """
        self._log("📤 Uploading PDF to Files API...")
        
        # Create a new client with beta headers for Files API
        client_with_beta = Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY'),
            default_headers={"anthropic-beta": "files-api-2025-04-14"}
        )
        
        with open(pdf_path, "rb") as f:
            file_upload = client_with_beta.files.upload(
                file=(pdf_path.name, f, "application/pdf"),
            )
        
        self._log(f"✅ File uploaded: {file_upload.id}")
        return file_upload.id, pdf_path.name
    
    def _split_pdf_base64(self, pdf_data: str, chunk_size_mb: float = 5.0) -> List[Tuple[int, int, str]]:
        """Split PDF base64 data into page ranges for batch processing
        
        Returns list of (start_page, end_page, data_chunk) tuples
        """
        # For now, we'll process the whole PDF in chunks
        # In a real implementation, you'd split by pages
        # This is a simplified version that processes the whole PDF in parallel chunks
        return [(0, -1, pdf_data)]  # Process whole PDF for now
    
    def _split_pdf_into_chunks(self, pdf_path: Path) -> List[Tuple[int, int, str]]:
        """Split PDF into page chunks and return base64 encoded chunks"""
        import PyPDF2
        
        chunks = []
        chunk_size = 5  # Process 5 pages at a time
        
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            total_pages = len(pdf_reader.pages)
            self._log(f"📄 PDF has {total_pages} pages, splitting into chunks of {chunk_size} pages")
            
            # Create chunks
            for start_page in range(0, total_pages, chunk_size):
                end_page = min(start_page + chunk_size, total_pages)
                
                # Create a new PDF with just these pages
                pdf_writer = PyPDF2.PdfWriter()
                for page_num in range(start_page, end_page):
                    pdf_writer.add_page(pdf_reader.pages[page_num])
                
                # Write to memory and encode
                import io
                pdf_bytes = io.BytesIO()
                pdf_writer.write(pdf_bytes)
                pdf_bytes.seek(0)
                
                chunk_data = base64.b64encode(pdf_bytes.read()).decode('utf-8')
                chunks.append((start_page + 1, end_page, chunk_data))
                self._log(f"📦 Created chunk: pages {start_page + 1}-{end_page}")
        
        return chunks
    
    def _process_pdf_with_batch(self, pdf_path: Path, pdf_data: str) -> str:
        """Process PDF using Claude's batch API for faster results"""
        self._log("🚀 Processing PDF with BATCH API...")
        
        # Split PDF into chunks
        pdf_chunks = self._split_pdf_into_chunks(pdf_path)
        self._log(f"📊 Split PDF into {len(pdf_chunks)} chunks")
        
        # Create batch requests
        batch_requests = []
        system_prompt = "You are a raw text extraction engine. Extract ALL text content from this PDF. Output ONLY the extracted text, nothing else."
        
        for idx, (start_page, end_page, chunk_data) in enumerate(pdf_chunks):
            request = Request(
                custom_id=f"pdf_pages_{start_page}_{end_page}",
                params=MessageCreateParamsNonStreaming(
                    model=CLAUDE_OPUS_4,  # Use constant for consistency
                    max_tokens=8000,
                    system=system_prompt,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": chunk_data
                                }
                            },
                            {
                                "type": "text",
                                "text": "Extract all text from this PDF document."
                            }
                        ]
                    }]
                )
            )
            batch_requests.append(request)
        
        # Submit batch
        self._log(f"📦 Submitting batch with {len(batch_requests)} requests...")
        batch = self.client.beta.messages.batches.create(requests=batch_requests)
        self._log(f"📋 Batch ID: {batch.id}")
        
        # Poll for completion
        start_time = time.time()
        while True:
            batch_status = self.client.beta.messages.batches.retrieve(batch.id)
            
            if batch_status.processing_status == "ended":
                self._log(f"✅ Batch completed in {time.time() - start_time:.1f} seconds")
                break
            
            # Log progress
            succeeded = getattr(batch_status.request_counts, 'succeeded', 0)
            processing = getattr(batch_status.request_counts, 'processing', 0)
            self._log(f"⏳ Progress: {succeeded}/{len(batch_requests)} completed, {processing} processing...")
            
            time.sleep(5)
        
        # Collect results
        self._log("📥 Collecting results...")
        extracted_texts = {}
        
        for result in self.client.beta.messages.batches.results(batch.id):
            if result.result.type == "succeeded":
                chunk_id = result.custom_id
                content = result.result.message.content[0].text
                extracted_texts[chunk_id] = content
                self._log(f"✅ {chunk_id}: {len(content)} chars extracted")
            else:
                self._log(f"❌ {result.custom_id} failed: {result.result.error}", force_stderr=True)
        
        # Combine results in order by page number
        combined_text = ""
        for start_page, end_page, _ in pdf_chunks:
            chunk_id = f"pdf_pages_{start_page}_{end_page}"
            if chunk_id in extracted_texts:
                combined_text += extracted_texts[chunk_id] + "\n\n"
        
        return combined_text.strip()
    
    def _process_single_chunk(self, chunk_info: Tuple[int, int, str]) -> Tuple[str, str, int]:
        """Process a single PDF chunk - for parallel execution"""
        start_page, end_page, chunk_data = chunk_info
        chunk_id = f"pdf_pages_{start_page}_{end_page}"
        
        try:
            start_time = time.time()
            system_prompt = "You are a raw text extraction engine. Extract ALL text content from this PDF. Output ONLY the extracted text, nothing else."
            
            message = self.client.messages.create(
                model=CLAUDE_OPUS_4,  # Use constant for consistency
                max_tokens=8000,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": chunk_data
                            }
                        },
                        {
                            "type": "text",
                            "text": "Extract all text from this PDF document."
                        }
                    ]
                }]
            )
            
            elapsed = time.time() - start_time
            content = message.content[0].text
            self._log(f"✅ {chunk_id}: {len(content)} chars in {elapsed:.1f}s")
            return chunk_id, content, start_page
            
        except Exception as e:
            self._log(f"❌ {chunk_id} failed: {e}", force_stderr=True)
            return chunk_id, "", start_page
    
    def _process_pdf_parallel(self, pdf_path: Path) -> str:
        """Process PDF using TRUE parallel processing for speed"""
        self._log("⚡ Processing PDF with PARALLEL threads...")
        
        # Split PDF into chunks
        pdf_chunks = self._split_pdf_into_chunks(pdf_path)
        self._log(f"📊 Split PDF into {len(pdf_chunks)} chunks for parallel processing")
        
        # Process chunks in parallel
        results = []
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(pdf_chunks)) as executor:
            # Submit all chunks for parallel processing
            future_to_chunk = {executor.submit(self._process_single_chunk, chunk): chunk for chunk in pdf_chunks}
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_chunk):
                try:
                    chunk_id, content, start_page = future.result()
                    results.append((start_page, content))
                except Exception as e:
                    self._log(f"❌ Chunk processing failed: {e}", force_stderr=True)
        
        elapsed_time = time.time() - start_time
        self._log(f"⚡ Parallel processing completed in {elapsed_time:.1f} seconds!")
        
        # Sort results by page number and combine
        results.sort(key=lambda x: x[0])
        combined_text = "\n\n".join(content for _, content in results if content)
        
        return combined_text.strip()
    
    def convert(self, pdf_path: str, output_path: Optional[str] = None) -> str:
        """
        Convert PDF to Markdown using Claude's native OCR.
        
        Args:
            pdf_path: Path to input PDF file
            output_path: Optional output path (if not provided, generates one)
            
        Returns:
            Path to the converted Markdown file
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        # Generate output path if not provided
        if output_path is None:
            output_path = self.temp_dir / f"{pdf_path.stem}_claude_extracted.md"
        else:
            output_path = Path(output_path)
        
        file_id = None
        try:
            self._log(f"🔍 Processing PDF with Claude OCR: {pdf_path.name}")
            self._log(f"[DEBUG] Starting Claude PDF conversion for: {pdf_path}", force_stderr=True)
            
            # Check file size
            pdf_size_mb = pdf_path.stat().st_size / (1024 * 1024)
            self._log(f"📏 PDF size: {pdf_size_mb:.2f} MB")
            
            if pdf_size_mb > 500:  # Files API supports up to 500MB
                raise ValueError(f"PDF too large: {pdf_size_mb:.2f} MB (max 500 MB)")
            
            # Prepare system prompt
            system_prompt = "You are a raw text extraction engine. Your ONLY purpose is to extract the complete text content of the provided document, verbatim, from start to finish. Output ONLY the extracted text content. Do NOT include any explanatory text, summaries, greetings, apologies, questions, analysis, metadata, formatting notes, or ANY text other than the raw extracted content of the document itself. This is a machine interface; non-document text will cause errors."
            
            user_text_prompt = "Extract all text from this PDF document."
            
            # Choose method based on configuration
            if self.use_parallel:
                # Use TRUE parallel processing for speed
                extracted_text = self._process_pdf_parallel(pdf_path)
                
            elif self.use_batch:
                # Use batch API for parallel processing
                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()
                    
                if len(pdf_bytes) / (1024 * 1024) > 32:
                    raise ValueError(f"PDF too large for batch processing: {pdf_size_mb:.2f} MB (max 32 MB)")
                    
                pdf_data = base64.b64encode(pdf_bytes).decode('utf-8')
                extracted_text = self._process_pdf_with_batch(pdf_path, pdf_data)
                
            elif self.use_files_api:
                # Upload to Files API
                file_id, original_filename = self._upload_pdf_to_files_api(pdf_path)
                
                self._log(f"📨 Sending PDF to Claude via Files API...")
                # Create message with file reference
                message = self.client.beta.messages.create(
                    model=get_claude_model(),  # Use Sonnet for faster PDF processing
                    max_tokens=32000,
                    betas=["files-api-2025-04-14"],
                    system=system_prompt,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "file",
                                    "file_id": file_id
                                }
                            },
                            {
                                "type": "text",
                                "text": user_text_prompt
                            }
                        ]
                    }]
                )
            else:
                # Use direct base64 encoding (original method)
                self._log(f"📖 Reading PDF file into memory...")
                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()
                    
                if len(pdf_bytes) / (1024 * 1024) > 32:
                    raise ValueError(f"PDF too large for direct encoding: {pdf_size_mb:.2f} MB (max 32 MB)")
                
                self._log(f"🔐 Encoding PDF to base64...")
                pdf_data = base64.b64encode(pdf_bytes).decode('utf-8')
                self._log(f"📊 Base64 size: {len(pdf_data) / (1024 * 1024):.2f} MB")
                
                self._log(f"📨 Sending PDF to Claude API (this may take 30-60 seconds)...")
                import time
                start_time = time.time()
                
                message = self.client.messages.create(
                    model=get_claude_model(),  # Use Sonnet for faster PDF processing
                    max_tokens=32000,
                    system=system_prompt,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_data
                                }
                            },
                            {
                                "type": "text",
                                "text": user_text_prompt
                            }
                        ]
                    }]
                )
                
                elapsed_time = time.time() - start_time
                self._log(f"✅ Claude API responded in {elapsed_time:.1f} seconds")
                
                # Log warning if it took too long
                if elapsed_time > 60:
                    self._log(f"⚠️ WARNING: Claude PDF processing is SLOW - {elapsed_time:.1f}s for {pdf_size_mb:.2f}MB", force_stderr=True)
            
            # Get the extracted text
            if self.use_parallel or self.use_batch:
                # Already have extracted_text from parallel/batch processing
                pass
            elif 'message' in locals() and message.content and len(message.content) > 0:
                # Handle both TextBlock and string content
                content_item = message.content[0]
                if hasattr(content_item, 'text'):
                    extracted_text = content_item.text
                elif isinstance(content_item, str):
                    extracted_text = content_item
                else:
                    extracted_text = str(content_item)
            else:
                if 'extracted_text' not in locals():
                    raise Exception("No content returned from Claude API")
            
            # Debug: Log the actual extraction length and preview
            self._log(f"📊 Claude extracted {len(extracted_text)} characters from PDF")
            
            # Check if Claude is summarizing instead of extracting
            if len(extracted_text) < 100:  # Very short response might indicate an issue
                self._log(f"⚠️  WARNING: Only {len(extracted_text)} chars extracted - might be an issue!")
                self._log(f"📄 Content: {extracted_text[:500]}...")
            
            # Save to output file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(extracted_text)
            
            self._log(f"✅ Claude OCR extraction complete: {output_path}")
            
            # Clean up uploaded file if using Files API
            if self.use_files_api and file_id:
                try:
                    # Create client with beta headers for cleanup
                    client_with_beta = Anthropic(
                        api_key=os.getenv('ANTHROPIC_API_KEY'),
                        default_headers={"anthropic-beta": "files-api-2025-04-14"}
                    )
                    client_with_beta.files.delete(file_id)
                    self._log(f"🗑️  Cleaned up uploaded file: {file_id}")
                except Exception as cleanup_error:
                    print(f"⚠️  Failed to clean up file {file_id}: {cleanup_error}", file=sys.stderr)
            
            return str(output_path)
                
        except anthropic.APIError as e:
            print(f"❌ Claude API Error: {getattr(e, 'message', str(e))}", file=sys.stderr)
            print(f"❌ Error type: {type(e).__name__}", file=sys.stderr)
            print(f"❌ Status code: {getattr(e, 'status_code', 'N/A')}", file=sys.stderr)
            
            # Log to a file for debugging
            with open("/tmp/claude_ocr_error.log", "w") as f:
                f.write(f"Claude OCR Error:\n")
                f.write(f"Error: {e}\n")
                f.write(f"Type: {type(e).__name__}\n")
                f.write(f"Status: {getattr(e, 'status_code', 'N/A')}\n")
                import traceback
                f.write(f"Traceback:\n{traceback.format_exc()}\n")
            
            # Check if it's an API key issue
            if hasattr(e, 'status_code') and e.status_code == 401:
                print("❌ Authentication error - check ANTHROPIC_API_KEY!", file=sys.stderr)
            
            print("⚠️  Falling back to standard PDF converter...", file=sys.stderr)
            
            # Fall back to regular PDF converter
            fallback_converter = PDFToMarkdownConverter()
            return fallback_converter.convert(pdf_path, output_path)
            
        except Exception as e:
            print(f"❌ Unexpected error: {e}", file=sys.stderr)
            print(f"❌ Error type: {type(e).__name__}", file=sys.stderr)
            
            # Log to a file for debugging
            with open("/tmp/claude_ocr_error.log", "w") as f:
                f.write(f"Unexpected Error:\n")
                f.write(f"Error: {e}\n")
                f.write(f"Type: {type(e).__name__}\n")
                import traceback
                f.write(f"Traceback:\n{traceback.format_exc()}\n")
            
            print("⚠️  Falling back to standard PDF converter...", file=sys.stderr)
            
            # Fall back to regular PDF converter
            fallback_converter = PDFToMarkdownConverter()
            return fallback_converter.convert(pdf_path, output_path)
    
    def __del__(self):
        """Clean up temp directory"""
        import shutil
        if hasattr(self, 'temp_dir') and self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
            except:
                pass


# Convenience function for direct usage
def convert_pdf_to_markdown_claude(pdf_path: str, output_path: Optional[str] = None, use_files_api: bool = False, silent: bool = False, use_batch: bool = False, use_parallel: bool = False) -> str:
    """
    Convert PDF to Markdown using Claude's native OCR.
    
    Args:
        pdf_path: Path to PDF file
        output_path: Optional output path
        use_files_api: Whether to use Files API (default: False)
        silent: Whether to suppress progress messages (default: False)
        use_batch: Whether to use batch API for cost savings (default: False)
        use_parallel: Whether to use parallel processing for speed (default: False)
        
    Returns:
        Path to converted Markdown file
    """
    converter = ClaudePDFToMarkdownConverter(use_files_api=use_files_api, silent=silent, use_batch=use_batch, use_parallel=use_parallel)
    return converter.convert(pdf_path, output_path)


if __name__ == "__main__":
    # Test the converter
    if len(sys.argv) < 2:
        print("Usage: python3 pdf_to_markdown_claude.py <pdf_file> [output_file] [options]")
        print("  Options:")
        print("    --use-files-api  Use Files API (requires newer SDK version)")
        print("    --use-batch      Use BATCH API for cost savings (50% off)")
        print("    --use-parallel   Use PARALLEL processing for speed")
        sys.exit(1)
    
    pdf_file = sys.argv[1]
    output_file = None
    use_files_api = False
    use_batch = False
    use_parallel = False
    
    # Parse arguments
    args = sys.argv[2:]
    for arg in args:
        if arg == "--use-files-api":
            use_files_api = True
        elif arg == "--use-batch":
            use_batch = True
        elif arg == "--use-parallel":
            use_parallel = True
        elif not output_file:
            output_file = arg
    
    try:
        result = convert_pdf_to_markdown_claude(pdf_file, output_file, use_files_api=use_files_api, use_batch=use_batch, use_parallel=use_parallel)
        print(f"✅ Conversion complete: {result}")
    except Exception as e:
        print(f"❌ Conversion failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)