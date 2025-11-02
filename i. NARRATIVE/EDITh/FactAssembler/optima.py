#!/usr/bin/env python3
"""
ULTRA-OPTIMIZED GAP-FILLING Document Assembler v3.0
Using OpenAI embeddings with parallel processing
"""

import os
import sys
import json
import re
import time
import asyncio
import aiofiles
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field
import hashlib
from collections import defaultdict

# Load environment
from dotenv import load_dotenv
load_dotenv(Path.home() / '.env')

# Import OpenAI
from openai import AsyncOpenAI, OpenAI

# Initialize clients
async_openai = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
sync_openai = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Import converters
try:
    from word_to_markdown_converter import convert_word_to_markdown
    from pdf_to_markdown_converter import PDFToMarkdownConverter
except ImportError:
    print("Warning: Document converters not found. Only .md files will be supported.")

# Cache directory
CACHE_DIR = Path.home() / ".gap_filler_cache"
CACHE_DIR.mkdir(exist_ok=True)

# Constants
GPT_MODEL = "gpt-4-turbo-preview"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 512  # Reduced for speed
MAX_CONCURRENT = 20

@dataclass
class Gap:
    """Represents a gap in the document"""
    position: int
    line_num: int
    context_before: str
    context_after: str
    full_line: str
    hint: Optional[str] = None
    full_match: str = "[...]"
    fill_options: List[Tuple[str, float, str]] = field(default_factory=list)
    analysis: Optional[Dict] = None
    is_outside_request: bool = False
    outside_description: Optional[str] = None
    filled_text: Optional[str] = None
    confidence: float = 0.0
    embedding: Optional[np.ndarray] = None

@dataclass
class SourceChunk:
    """A chunk of source text with metadata"""
    source_name: str
    text: str
    start_idx: int
    end_idx: int
    embedding: Optional[np.ndarray] = None

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors"""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

class UltraOptimizedGapFiller:
    """Main gap filler using embeddings and parallel processing"""
    
    def __init__(self):
        self.source_chunks: List[SourceChunk] = []
        self.chunk_embeddings: Optional[np.ndarray] = None
        
    async def process_document(self, target_path: Path, source_paths: List[Path]) -> Tuple[str, Dict]:
        """Main processing pipeline"""
        start_time = time.time()
        print("\n🚀 Starting Ultra-Optimized Gap Filling v3.0")
        print("=" * 80)
        
        # 1. Load target document
        print(f"\n📄 Loading target: {target_path.name}")
        target_content = await self.load_document(target_path)
        
        # 2. Extract instructions and find gaps
        instructions = self.extract_instructions(target_content)
        if instructions:
            print(f"📋 Found {len(instructions)} global instructions")
            
        gaps = self.find_gaps(target_content)
        print(f"🔍 Found {len(gaps)} gaps to fill")
        
        if not gaps:
            print("✅ No gaps found!")
            return target_content, {}
        
        # 3. Load sources and create chunks
        print(f"\n📚 Loading {len(source_paths)} source(s)...")
        sources = await self.load_sources(source_paths)
        
        # 4. Build embedding index
        print("🏗️ Building embedding index...")
        await self.build_embedding_index(sources)
        
        # 5. Process gaps with OpenAI optimization
        print(f"\n🔬 Analyzing and filling {len(gaps)} gaps...")
        await self.process_gaps_optimized(gaps, instructions)
        
        # 6. Apply fills to document
        print("\n✏️ Applying gap fills...")
        filled_content = self.apply_fills(target_content, gaps)
        
        # 7. Generate report
        report = self.generate_report(gaps, time.time() - start_time)
        
        return filled_content, report
    
    async def load_document(self, file_path: Path) -> str:
        """Load and convert document with caching"""
        # Check cache first
        cache_key = f"{file_path.name}_{file_path.stat().st_mtime}"
        cache_path = CACHE_DIR / f"{hashlib.md5(cache_key.encode()).hexdigest()}.md"
        
        if cache_path.exists():
            print(f"   Using cached conversion")
            async with aiofiles.open(cache_path, 'r', encoding='utf-8') as f:
                return await f.read()
        
        # Convert if needed
        content = ""
        if file_path.suffix.lower() in ['.docx', '.doc']:
            print(f"   Converting Word document...")
            temp_path = file_path.parent / f"{file_path.stem}_temp.md"
            try:
                convert_word_to_markdown(str(file_path), str(temp_path))
                with open(temp_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                temp_path.unlink()
            except Exception as e:
                print(f"   Error converting: {e}")
                return ""
                
        elif file_path.suffix.lower() == '.pdf':
            print(f"   Converting PDF...")
            temp_path = file_path.parent / f"{file_path.stem}_temp.md"
            try:
                converter = PDFToMarkdownConverter()
                converter.convert(str(file_path), str(temp_path))
                with open(temp_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                temp_path.unlink()
            except Exception as e:
                print(f"   Error converting: {e}")
                return ""
        else:
            # Plain text/markdown
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
        
        # Cache the converted content
        async with aiofiles.open(cache_path, 'w', encoding='utf-8') as f:
            await f.write(content)
        
        return content
    
    def extract_instructions(self, content: str) -> List[str]:
        """Extract ++instruction++ markers"""
        instructions = []
        for match in re.finditer(r'\+\+([^+]+)\+\+', content):
            instructions.append(match.group(1).strip())
        return instructions
    
    def find_gaps(self, content: str, context_window: int = 500) -> List[Gap]:
        """Find all gaps in the document"""
        gaps = []
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines):
            for match in re.finditer(r'\[([^]]+)\]', line):
                matched_text = match.group(1)
                full_match = match.group(0)
                
                # Skip footnotes
                if matched_text.isdigit():
                    continue
                
                # Check if it's a gap
                is_gap = '...' in matched_text or matched_text == '..'
                hint = None if is_gap else matched_text
                
                # Check for outside request
                is_outside = False
                outside_desc = None
                if hint:
                    if hint.lower() == "outside!":
                        is_outside = True
                        outside_desc = "general information"
                    elif hint.lower().startswith("outside:"):
                        is_outside = True
                        outside_desc = hint[8:].strip()
                
                position = match.start()
                
                # Get context
                context_before = ""
                for i in range(max(0, line_num - 5), line_num + 1):
                    context_before += lines[i] + "\n"
                context_before = context_before[-context_window:]
                
                context_after = ""
                for i in range(line_num, min(len(lines), line_num + 6)):
                    context_after += lines[i] + "\n"
                context_after = context_after[:context_window]
                
                gap = Gap(
                    position=position,
                    line_num=line_num,
                    context_before=context_before.strip(),
                    context_after=context_after.strip(),
                    full_line=line,
                    hint=hint,
                    full_match=full_match,
                    is_outside_request=is_outside,
                    outside_description=outside_desc
                )
                gaps.append(gap)
        
        return gaps
    
    async def load_sources(self, source_paths: List[Path]) -> Dict[str, str]:
        """Load all sources concurrently"""
        sources = {}
        
        async def load_single_source(path: Path) -> List[Tuple[str, str]]:
            results = []
            
            if path.is_file():
                content = await self.load_document(path)
                if content:
                    results.append((path.name, content))
                    
            elif path.is_dir():
                # Load all markdown files
                for file_path in path.glob("*.md"):
                    content = await self.load_document(file_path)
                    if content:
                        results.append((file_path.name, content))
            
            return results
        
        # Load all sources in parallel
        all_results = await asyncio.gather(
            *[load_single_source(p) for p in source_paths]
        )
        
        # Flatten results
        for results in all_results:
            for name, content in results:
                sources[name] = content
                print(f"   ✅ Loaded: {name}")
        
        return sources
    
    async def build_embedding_index(self, sources: Dict[str, str]):
        """Build embedding index from sources"""
        # Create chunks
        chunk_size = 500
        overlap = 100
        
        for source_name, content in sources.items():
            words = content.split()
            for i in range(0, len(words), chunk_size - overlap):
                chunk_text = ' '.join(words[i:i + chunk_size])
                chunk = SourceChunk(
                    source_name=source_name,
                    text=chunk_text,
                    start_idx=i,
                    end_idx=min(i + chunk_size, len(words))
                )
                self.source_chunks.append(chunk)
        
        print(f"   Created {len(self.source_chunks)} chunks")
        
        # Get embeddings in batches
        await self.embed_chunks()
    
    async def embed_chunks(self, batch_size: int = 100):
        """Get embeddings for all chunks"""
        all_embeddings = []
        
        for i in range(0, len(self.source_chunks), batch_size):
            batch = self.source_chunks[i:i+batch_size]
            texts = [chunk.text for chunk in batch]
            
            try:
                response = await async_openai.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=texts,
                    dimensions=EMBEDDING_DIMENSIONS
                )
                
                embeddings = [np.array(item.embedding) for item in response.data]
                all_embeddings.extend(embeddings)
                
                # Assign embeddings to chunks
                for chunk, embedding in zip(batch, embeddings):
                    chunk.embedding = embedding
                    
            except Exception as e:
                print(f"   Error getting embeddings: {e}")
                # Use zero vectors as fallback
                for chunk in batch:
                    chunk.embedding = np.zeros(EMBEDDING_DIMENSIONS)
                all_embeddings.extend([np.zeros(EMBEDDING_DIMENSIONS)] * len(batch))
        
        self.chunk_embeddings = np.array(all_embeddings)
        print(f"   ✅ Embedded {len(all_embeddings)} chunks")
    
    async def process_gaps_optimized(self, gaps: List[Gap], instructions: List[str]):
        """Process all gaps with OpenAI optimization"""
        # Separate inside and outside gaps
        inside_gaps = [g for g in gaps if not g.is_outside_request]
        outside_gaps = [g for g in gaps if g.is_outside_request]
        
        # Process different gap types in parallel
        tasks = []
        
        if inside_gaps:
            tasks.append(self.process_inside_gaps(inside_gaps, instructions))
        
        if outside_gaps:
            tasks.append(self.process_outside_gaps(outside_gaps, instructions))
        
        await asyncio.gather(*tasks)
    
    async def process_inside_gaps(self, gaps: List[Gap], instructions: List[str]):
        """Process gaps that need source searching"""
        # First, analyze all gaps
        await self.analyze_gaps_batch(gaps, instructions)
        
        # Get embeddings for gap contexts
        gap_texts = []
        for gap in gaps:
            context = f"{gap.context_before} [MISSING: {gap.hint or '...'}] {gap.context_after}"
            if gap.analysis and gap.analysis.get("search_terms"):
                context += " " + " ".join(gap.analysis["search_terms"])
            gap_texts.append(context)
        
        # Get embeddings
        try:
            response = await async_openai.embeddings.create(
                model=EMBEDDING_MODEL,
                input=gap_texts,
                dimensions=EMBEDDING_DIMENSIONS
            )
            
            for gap, embedding_data in zip(gaps, response.data):
                gap.embedding = np.array(embedding_data.embedding)
                
        except Exception as e:
            print(f"   Error getting gap embeddings: {e}")
            for gap in gaps:
                gap.embedding = np.zeros(EMBEDDING_DIMENSIONS)
        
        # Search for fills using embeddings
        for gap in gaps:
            if gap.embedding is not None:
                fills = self.search_with_embeddings(gap)
                gap.fill_options = fills
                
                # Synthesize best fill
                if fills:
                    gap.filled_text, gap.confidence = await self.synthesize_fill(gap, fills[:3])
    
    def search_with_embeddings(self, gap: Gap, top_k: int = 10) -> List[Tuple[str, float, str]]:
        """Search for relevant chunks using embeddings"""
        if gap.embedding is None or self.chunk_embeddings is None:
            return []
        
        # Calculate similarities
        similarities = []
        for i, chunk in enumerate(self.source_chunks):
            if chunk.embedding is not None:
                sim = cosine_similarity(gap.embedding, chunk.embedding)
                similarities.append((i, sim))
        
        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        # Get top results
        results = []
        for idx, sim in similarities[:top_k]:
            chunk = self.source_chunks[idx]
            results.append((chunk.text, sim, chunk.source_name))
        
        return results
    
    async def synthesize_fill(self, gap: Gap, top_chunks: List[Tuple[str, float, str]]) -> Tuple[str, float]:
        """Synthesize fill from top chunks"""
        if not top_chunks:
            return "[No match found]", 0.0
        
        # Format sources
        sources_text = "\n\n".join([
            f"Source {i+1} (similarity: {score:.2f}):\n{text[:500]}"
            for i, (text, score, source) in enumerate(top_chunks)
        ])
        
        prompt = f"""Based on these sources, what text should fill this gap?

Gap context:
Before: {gap.context_before[-200:]}
Gap: {gap.full_match}
After: {gap.context_after[:200]}

Analysis: Looking for {gap.analysis.get('info_type', 'information') if gap.analysis else 'information'}

Sources found:
{sources_text}

Provide the exact text to fill the gap. Be concise and match the document's style.
Return JSON: {{"fill": "exact text", "confidence": 0.0-1.0}}"""

        try:
            response = await async_openai.chat.completions.create(
                model=GPT_MODEL,
                messages=[
                    {"role": "system", "content": "Extract precise information to fill document gaps."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result.get("fill", "[No fill]"), result.get("confidence", 0.0)
            
        except Exception as e:
            print(f"   Error synthesizing: {e}")
            # Fallback to best chunk
            if top_chunks:
                return top_chunks[0][0][:100], top_chunks[0][1]
            return "[Error]", 0.0
    
    async def analyze_gaps_batch(self, gaps: List[Gap], instructions: List[str]):
        """Analyze gaps in optimized batches"""
        batch_size = 20
        
        for i in range(0, len(gaps), batch_size):
            batch = gaps[i:i+batch_size]
            
            # Format batch for analysis
            gaps_data = []
            for idx, gap in enumerate(batch):
                gaps_data.append({
                    "id": idx,
                    "before": gap.context_before[-200:],
                    "gap": gap.full_match,
                    "after": gap.context_after[:200],
                    "hint": gap.hint
                })
            
            instruction_text = ""
            if instructions:
                instruction_text = "\nConsider these instructions:\n" + "\n".join(f"- {inst}" for inst in instructions)
            
            prompt = f"""Analyze these document gaps and determine what information is needed.
{instruction_text}

Gaps:
{json.dumps(gaps_data, indent=2)}

For each gap, provide:
- info_type: what kind of information is missing
- search_terms: key terms to search for
- constraints: any requirements
- expected_format: expected format of the answer

Return as JSON object with gap IDs as keys."""

            try:
                response = await async_openai.chat.completions.create(
                    model=GPT_MODEL,
                    messages=[
                        {"role": "system", "content": "You are an expert document analyst."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                
                analyses = json.loads(response.choices[0].message.content)
                
                # Assign analyses to gaps
                for idx, gap in enumerate(batch):
                    if str(idx) in analyses:
                        gap.analysis = analyses[str(idx)]
                    
            except Exception as e:
                print(f"   Error analyzing batch: {e}")
    
    async def process_outside_gaps(self, gaps: List[Gap], instructions: List[str]):
        """Process gaps that need AI general knowledge"""
        batch_size = 10
        
        for i in range(0, len(gaps), batch_size):
            batch = gaps[i:i+batch_size]
            
            gaps_data = []
            for idx, gap in enumerate(batch):
                gaps_data.append({
                    "id": idx,
                    "before": gap.context_before[-200:],
                    "gap": gap.full_match,
                    "after": gap.context_after[:200],
                    "description": gap.outside_description or "general information"
                })
            
            prompt = f"""Fill these gaps using your general knowledge (not from specific sources).

Gaps:
{json.dumps(gaps_data, indent=2)}

For each gap, provide accurate information based on public knowledge.
Return JSON object with gap IDs as keys, each containing:
{{"fill": "exact text", "confidence": 0.0-1.0}}"""

            try:
                response = await async_openai.chat.completions.create(
                    model=GPT_MODEL,
                    messages=[
                        {"role": "system", "content": "Provide accurate general knowledge to fill gaps."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                
                results = json.loads(response.choices[0].message.content)
                
                for idx, gap in enumerate(batch):
                    if str(idx) in results:
                        result = results[str(idx)]
                        gap.filled_text = result.get("fill", "[No fill]")
                        gap.confidence = result.get("confidence", 0.0)
                        
            except Exception as e:
                print(f"   Error with outside gaps: {e}")
    
    def apply_fills(self, content: str, gaps: List[Gap]) -> str:
        """Apply all fills to the document"""
        # Extract existing footnotes
        lines = content.split('\n')
        footnotes = {}
        content_lines = []
        in_footnotes = False
        
        for line in lines:
            if re.match(r'^\[\d+\]', line):
                in_footnotes = True
            
            if in_footnotes:
                match = re.match(r'^\[(\d+)\]\s*(.*)', line)
                if match:
                    footnotes[int(match.group(1))] = match.group(2)
            else:
                content_lines.append(line)
        
        lines = content_lines
        highest_footnote = max(footnotes.keys()) if footnotes else 0
        
        # Sort gaps by position (reverse order)
        sorted_gaps = sorted(gaps, key=lambda g: (g.line_num, g.position), reverse=True)
        
        MIN_CONFIDENCE = 0.3
        filled_count = 0
        
        for gap in sorted_gaps:
            if not gap.filled_text or gap.confidence < MIN_CONFIDENCE:
                # Add comment for unfilled gap
                line = lines[gap.line_num]
                comment = f" <!-- Gap not filled: {gap.full_match} (confidence: {gap.confidence:.2f}) -->"
                lines[gap.line_num] = line + comment
                continue
            
            # Apply fill with bold+italic highlight
            highlighted_fill = f"***{gap.filled_text}***"
            
            # Add footnote
            highest_footnote += 1
            highlighted_fill += f"[{highest_footnote}]"
            
            # Create footnote text
            source_type = "AI Knowledge" if gap.is_outside_request else "Source documents"
            footnote_text = (f"Gap '{gap.full_match}' filled with '{gap.filled_text}' "
                           f"(confidence: {gap.confidence:.2f}, source: {source_type}).")
            footnotes[highest_footnote] = footnote_text
            
            # Replace gap in line
            line = lines[gap.line_num]
            escaped_match = re.escape(gap.full_match)
            lines[gap.line_num] = re.sub(escaped_match, highlighted_fill, line, count=1)
            filled_count += 1
        
        # Reconstruct document
        filled_content = '\n'.join(lines)
        
        # Add footnotes
        if footnotes:
            filled_content += "\n\n---\n\n"
            for num, text in sorted(footnotes.items()):
                filled_content += f"[{num}] {text}\n"
        
        print(f"\n✅ Filled {filled_count}/{len(gaps)} gaps")
        
        return filled_content
    
    def generate_report(self, gaps: List[Gap], elapsed_time: float) -> Dict:
        """Generate detailed report"""
        filled_gaps = [g for g in gaps if g.filled_text and g.confidence >= 0.3]
        low_confidence = [g for g in gaps if g.filled_text and g.confidence < 0.3]
        unfilled = [g for g in gaps if not g.filled_text]
        
        report = {
            "summary": {
                "total_gaps": len(gaps),
                "filled": len(filled_gaps),
                "low_confidence": len(low_confidence),
                "unfilled": len(unfilled),
                "processing_time": f"{elapsed_time:.1f}s",
                "avg_time_per_gap": f"{elapsed_time/len(gaps):.2f}s" if gaps else "0s"
            },
            "gaps": []
        }
        
        for gap in gaps:
            gap_info = {
                "line": gap.line_num,
                "original": gap.full_match,
                "filled_with": gap.filled_text or "[Not filled]",
                "confidence": gap.confidence,
                "type": "AI Knowledge" if gap.is_outside_request else "Source search",
                "context": f"...{gap.context_before[-50:]} {gap.full_match} {gap.context_after[:50]}..."
            }
            report["gaps"].append(gap_info)
        
        return report

async def main():
    """Main entry point"""
    print("🚀 ULTRA-OPTIMIZED GAP-FILLING Document Assembler v3.0")
    print("=" * 80)
    print("Features:")
    print("  • Parallel processing with GPT-4")
    print("  • Fast embedding-based search")
    print("  • Document conversion caching")
    print("  • Support for Word, PDF, and Markdown")
    print("  • [outside!] requests for AI general knowledge")
    print("=" * 80)
    
    # Get inputs
    target_input = input("\nTarget document with [...] gaps: ").strip().strip('"\'')
    if not target_input:
        print("❌ No target specified")
        return
    
    source_input = input("Source documents/folder (comma-separated): ").strip().strip('"\'')
    if not source_input:
        print("❌ No sources specified")
        return
    
    # Parse paths
    target_path = Path(target_input)
    if not target_path.exists():
        print(f"❌ Target not found: {target_path}")
        return
    
    source_paths = []
    for source in source_input.split(','):
        source = source.strip().strip('"\'')
        if source:
            path = Path(source)
            if path.exists():
                source_paths.append(path)
            else:
                print(f"⚠️ Source not found: {path}")
    
    if not source_paths:
        print("❌ No valid sources found")
        return
    
    # Process document
    filler = UltraOptimizedGapFiller()
    
    try:
        filled_content, report = await filler.process_document(target_path, source_paths)
        
        # Save results
        output_path = target_path.parent / f"{target_path.stem}_filled.md"
        async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
            await f.write(filled_content)
        
        print(f"\n✅ Saved filled document to: {output_path}")
        
        # Save report
        report_path = target_path.parent / f"{target_path.stem}_gap_report.json"
        async with aiofiles.open(report_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(report, indent=2))
        
        print(f"📊 Saved report to: {report_path}")
        
        # Print summary
        print("\n📈 Summary:")
        print(f"   Total gaps: {report['summary']['total_gaps']}")
        print(f"   Successfully filled: {report['summary']['filled']}")
        print(f"   Low confidence: {report['summary']['low_confidence']}")
        print(f"   Could not fill: {report['summary']['unfilled']}")
        print(f"   Total time: {report['summary']['processing_time']}")
        print(f"   Average per gap: {report['summary']['avg_time_per_gap']}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Run with proper event loop handling
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Cancelled by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")