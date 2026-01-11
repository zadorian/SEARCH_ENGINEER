import asyncio
import traceback
from typing import List, Tuple
from website_searchers.website_searcher import WebsiteSearcher
from website_searchers.ai_searcher import client as ai_client
from datetime import datetime

class ComparisonSearcher:
    """
    Handles commands using the =? operator to compare search results across multiple targets.
    
    Comparison Types:
    1. NER (Named Entity Recognition) Comparisons:
       - p! : People comparison (e.g., "p! :domain1.com? =? domain2.com?")
       - c! : Company comparison
       - l! : Location comparison
       - @! : Email comparison
       - t! : Phone number comparison
       - ent! : All entities comparison
    
    2. Content Comparisons:
       - Regular: Compare content between different domains
         Example: "domain1.com? =? domain2.com?"
       
       - Temporal: Compare content across time for same domain
         Examples: 
         - "p! :2022! domain.com? =? domain.com?"
         - "2022! domain.com? =? 2023! domain.com? =? domain.com?"
         - "2020-2023! domain.com?"  # Compare all versions from 2020 to 2023
    
    3. Special Comparisons:
       - bl!/!bl : Backlinks comparison
       - ga! : Google Analytics comparison
       - whois! : WHOIS data comparison
    """

    def __init__(self):
        self.website_searcher = WebsiteSearcher()

    async def handle_comparison_command(self, command: str) -> str:
        """
        Handle comparison command with =? syntax.
        
        Command Format Examples:
        1. NER comparison: "p! :domain1.com? =? domain2.com?"
        2. Temporal comparison: "p! :2022! domain.com? =? domain.com?"
        3. Multi-version comparison: "2020! domain.com? =? 2021! domain.com? =? 2022! domain.com?"
        4. Year range comparison: "2020-2023! domain.com?"
        5. Simple content: "domain1.com? =? domain2.com?"
        """
        try:
            # Check for year range format first
            if '-' in command and '!' in command:
                start_year, end_year = command.split('!')[0].split('-')
                domain = command.split('!')[1].strip('?')
                if start_year.isdigit() and end_year.isdigit():
                    return await self._handle_year_range_comparison(int(start_year), int(end_year), domain)

            # Split on =? to get parts
            parts = command.split('=?')
            if len(parts) < 2:
                return "Invalid comparison command. Need at least two parts separated by =?"

            # Get results for each part
            results = []
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                    
                # Process each part as a regular command
                searcher = WebsiteSearcher()
                
                # If this is just a URL (no search type prefix), treat it as a content fetch
                if not any(prefix in part for prefix in ['p!', 'c!', 'l!', '@!', 't!', 'ent!', 'bl!', '!bl', 'ga!', 'whois!']):
                    result = await searcher.process_command(part)
                    results.append((part, result))
                else:
                    # Handle normal search commands
                    result = await searcher.process_command(part)
                    results.append((part, result))

            if len(results) < 2:
                return "Need at least two valid parts to compare"

            # For NER searches (people, companies, locations), show overlap analysis
            if any('p!' in part[0] or 'c!' in part[0] or 'l!' in part[0] for part in results):
                return self._format_ner_comparison(results)

            # Check if this is a temporal comparison (archived versions)
            is_temporal = self._is_temporal_comparison(results)
            if is_temporal:
                return await self._compare_archived_versions(results)

            # For all other comparisons (content, backlinks, GA), use AI analysis
            return await self._compare_with_ai(results)

        except Exception as e:
            traceback.print_exc()
            return f"Error in handle_comparison_command: {str(e)}"

    def _is_temporal_comparison(self, results: List[Tuple[str, str]]) -> bool:
        """Check if this is a comparison of archived versions."""
        if len(results) < 2:
            return False
            
        # Extract base domains from all results
        domains = []
        for cmd, _ in results:
            # Remove year and command prefixes
            parts = cmd.split('!')
            if len(parts) > 1:
                domain = parts[-1].strip('?').strip()
                domains.append(domain)
            else:
                domains.append(cmd.strip('?').strip())
                
        # If all domains are the same, it's a temporal comparison
        return len(set(domains)) == 1 and any('!' in cmd for cmd, _ in results)

    async def _handle_year_range_comparison(self, start_year: int, end_year: int, domain: str) -> str:
        """Handle comparison of multiple years in a range."""
        results = []
        current_year = datetime.now().year
        
        # Get content for each year
        for year in range(start_year, end_year + 1):
            cmd = f"{year}! {domain}"
            result = await self.website_searcher.process_command(cmd)
            if result:
                results.append((cmd, result))
                
        # Add current version if we're not already in current year
        if end_year < current_year:
            current_result = await self.website_searcher.process_command(domain)
            if current_result:
                results.append((f"Current ({current_year}): {domain}", current_result))
                
        if len(results) < 2:
            return "Not enough archived versions found for comparison"
            
        return await self._compare_archived_versions(results)

    async def _compare_archived_versions(self, results: List[Tuple[str, str]]) -> str:
        """Compare multiple archived versions of the same website."""
        try:
            # Format versions data for comparison
            versions_data = []
            for cmd, content in results:
                # Extract year from command if present
                year = "Current"
                if '!' in cmd:
                    year_part = cmd.split('!')[0].strip()
                    if year_part.isdigit():
                        year = year_part
                
                versions_data.append(f"=== Version {year} ===\n{content}\n")
                
            combined_data = "\n".join(versions_data)
            
            # Use specialized prompt for archived versions comparison
            from prompts import get_archived_versions_comparison_prompt
            prompt = get_archived_versions_comparison_prompt(combined_data)
            
            # Use AI for analysis
            response = ai_client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert at analyzing website evolution over time. "
                            "Focus on identifying meaningful changes, patterns, and trends. "
                            "Be specific about when changes occurred and whether they persisted."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            return response.choices[0].message.content
            
        except Exception as e:
            traceback.print_exc()
            return f"Error comparing archived versions: {str(e)}"

    async def _compare_with_ai(self, results: List[tuple]) -> str:
        """
        Uses AI to compare the outcomes from each target.
        
        Comparison Types Handled:
        1. Regular content comparison between different domains
        2. Temporal comparison (same domain, different time periods)
        3. Special comparisons (backlinks, GA data, WHOIS)
        """
        try:
            # Format input for AI comparison
            comparison_input = []
            for domain, res in results:
                comparison_input.append(f"--- Content from {domain} ---\n{res}\n")

            combined_results_text = "\n".join(comparison_input)

            # Detect temporal comparison (comparing same domain across time)
            is_temporal = False
            if len(results) == 2:
                target1, target2 = results[0][0], results[1][0]
                # Check if one target is a year-specific version of the other
                if ('!' in target1 and target1.split('!')[1].strip() == target2.strip()) or \
                   ('!' in target2 and target2.split('!')[1].strip() == target1.strip()):
                    is_temporal = True

            # Select appropriate prompt based on content type
            if any(marker in results[0][0] for marker in ['p!', 'c!', 'l!', '@!', 't!', 'ent!']):
                from prompts import get_ner_comparison_prompt
                prompt = get_ner_comparison_prompt(results[0][0], combined_results_text, is_temporal)
            else:
                # For simple content comparisons
                from prompts import get_content_comparison_prompt
                prompt = get_content_comparison_prompt(combined_results_text, is_temporal)

            # Use OpenAI for comparison analysis
            response = ai_client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful AI that compares website content. "
                            "Focus first on identifying key similarities and overlaps, "
                            "then note significant differences. Be concise and conversational. "
                            "If you spot patterns or connections, mention them briefly."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            return response.choices[0].message.content

        except Exception as e:
            traceback.print_exc()
            return f"Error during AI comparison: {str(e)}"

    def _format_ner_comparison(self, results: List[Tuple[str, str]]) -> str:
        """
        Format NER comparison results to show original results and simple analysis.
        
        Analysis Priorities:
        1. Entity Overlap: Show entities that appear in all compared sources
        2. Notable Contrasts: Highlight significant differences in entity counts
        3. Pattern Detection: Identify patterns like regional names or common features
        """
        output = []
        
        # Show original results for each URL
        for cmd, result in results:
            output.append(f"\n=== Results for {cmd} ===")
            output.append(result)
        
        # Extract and analyze entities
        all_entities = []
        for cmd, result in results:
            entities = set()
            lines = result.split('\n')
            for line in lines:
                if line.startswith('- '):
                    entities.add(line[2:])
            all_entities.append((cmd, entities))
        
        # Analyze overlap and patterns
        if len(all_entities) >= 2:
            common = all_entities[0][1]
            for _, entities in all_entities[1:]:
                common = common & entities
            
            output.append("\n=== Analysis ===")
            analysis = []
            
            # 1. Analyze overlaps
            if common:
                names = sorted(common)
                if len(names) == 1:
                    analysis.append(f"{names[0]} appears on both sites.")
                else:
                    analysis.append(f"{', '.join(names)} appear on both sites.")
            else:
                analysis.append("There's no overlap in people between these sites.")
            
            # 2. Analyze contrasts
            site1_unique = all_entities[0][1] - all_entities[1][1]
            site2_unique = all_entities[1][1] - all_entities[0][1]
            
            if len(site1_unique) == 0 and len(site2_unique) > 0:
                analysis.append(f"The second site mentions {len(site2_unique)} additional people not found on the first site.")
            elif len(site2_unique) == 0 and len(site1_unique) > 0:
                analysis.append(f"The first site mentions {len(site1_unique)} additional people not found on the second site.")
            elif abs(len(site1_unique) - len(site2_unique)) > 3:
                analysis.append(f"The second site lists significantly more people ({len(all_entities[1][1])}) than the first site ({len(all_entities[0][1])}).")
            
            # 3. Analyze patterns (e.g., regional names)
            all_names = all_entities[0][1] | all_entities[1][1]
            hungarian_count = sum(1 for name in all_names if any(suffix in name.lower() for suffix in ['szabo', 'radnoti', 'mester']))
            if hungarian_count >= 2:
                analysis.append("Several of the names appear to be Hungarian.")
            
            output.append(" ".join(analysis))
                
        return "\n".join(output)

async def demo():
    """
    Simple demo usage if you run 'comparison.py' directly:
    python comparison.py "p! :company1.com! =? company2.com?"
    """
    import sys
    if len(sys.argv) < 2:
        print("Usage: python comparison.py \"<search-object> : <target1> =? <target2>\"")
        return

    command = sys.argv[1]
    comp = ComparisonSearcher()
    result = await comp.handle_comparison_command(command)
    print("\n=== Final Comparison Output ===\n")
    print(result)

if __name__ == "__main__":
    asyncio.run(demo()) 