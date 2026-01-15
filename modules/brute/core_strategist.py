"""
Cymonides Strategist: Methodological RAG Engine

This module implements "Retrieval Augmented Generation" for *Methodology*.
Instead of retrieving facts, it retrieves *Capabilities* (Rules, Sources, Registries) 
from the Directory Index and uses an LLM to construct a coherent 
investigation strategy.
"""

import os
import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add project paths
sys.path.insert(0, str(Path(__file__).parent.parent))

from brute.adapter.drill_search_adapter import DrillSearchAdapter

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

class CymonidesStrategist:
    def __init__(self):
        self.adapter = DrillSearchAdapter()
        # Load environment (for API key)
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent.parent / ".env")
        
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY")) if ANTHROPIC_AVAILABLE else None

    def generate_strategy(self, context: str, intent: str = "investigation") -> Dict[str, Any]:
        """
        Generate an investigation strategy based on the available Directory capabilities.
        
        Args:
            context: The subject/context (e.g. "Offshore company in Panama linked to Russia")
            intent: The goal (e.g. "Find beneficial owners", "Trace assets")
            
        Returns:
            JSON object with the strategy (steps, tools, rationale)
        """
        if not self.client:
            return {"error": "Anthropic API key not found. Strategy requires LLM."}

        print(f"🤔 Strategizing for: '{context}' with intent: '{intent}'...")

        # 1. Retrieval: Find relevant capabilities in the Directory
        # We query the vector index for rules/sources matching the context/intent
        query = f"{context} {intent} arbitrage opportunity registry database"
        
        # Search specifically in the 'directory' and 'system' suites (Rules & Capabilities)
        directory_hits = self.adapter.search_hybrid(
            query=query,
            k=15,
            keyword_weight=0.3, # Lean towards semantic
            # We assume 'suite' field is populated from our previous indexing script
            # Filters are applied if possible, otherwise we filter post-retrieval
        )
        
        # Filter for relevant types if not done by search
        relevant_hits = [
            h for h in directory_hits 
            if h.get('metadata', {}).get('suite') in ['directory', 'system'] 
            or h.get('node_class') in ['resource', 'logic']
        ]
        
        print(f"📚 Retrieved {len(relevant_hits)} relevant capabilities from Directory.")

        # 2. Context Construction: Format capabilities for the LLM
        capabilities_context = ""
        for i, hit in enumerate(relevant_hits):
            meta = hit.get('metadata', {})
            capabilities_context += f"[{i+1}] {hit.get('label')}\n"
            capabilities_context += f"    Type: {hit.get('typeName')}\n"
            capabilities_context += f"    Description: {hit.get('content')[:300]}...\n"
            if meta.get('jurisdiction'):
                capabilities_context += f"    Jurisdiction: {meta.get('jurisdiction')}\n"
            if meta.get('friction'):
                capabilities_context += f"    Friction: {meta.get('friction')}\n"
            capabilities_context += "\n"

        # 3. Generation: Ask Claude to build the plan
        prompt = f"""
You are the Cymonides Strategist, an expert OSINT investigation planner.
Your goal is to build a concrete, step-by-step investigation plan for the following scenario, using ONLY the provided tools/sources.

SCENARIO:
Context: {context}
Intent: {intent}

AVAILABLE CAPABILITIES (Retrieved from Directory):
{capabilities_context}

INSTRUCTIONS:
1. Analyze the capabilities to find the best path to the goal.
2. Look for "Arbitrage Opportunities" (low friction, high disclosure) in the capabilities.
3. Construct a numbered list of steps.
4. For each step, cite the specific Tool/Source [ID] you would use.
5. Explain WHY this path is chosen (the strategy).

Return valid JSON:
{{
  "analysis": "Brief analysis of the landscape and opportunities",
  "steps": [
    {{ "step": 1, "action": "Description", "tool": "Tool Name [ID]", "reasoning": "Why" }}
  ],
  "arbitrage_opportunities": ["List specific arbitrage opportunities found"],
  "missing_capabilities": "What tools/data are missing that would help?"
}}
"""

        # Verified against platform.claude.com documentation (Nov 2025)
        # Model: Claude Sonnet 4.5
        model_id = "claude-sonnet-4-5-20250929"
        
        try:
            response = self.client.messages.create(
                model=model_id,
                max_tokens=4096, # Increased output limit for 4.5
                messages=[{"role": "user", "content": prompt}]
            )
        except Exception as e:
            print(f"❌ Model Execution Failed: {e}")
            return {
                "error": str(e),
                "raw_response": "",
                "source_hits": relevant_hits
            }

        text_response = response.content[0].text
        
        # Extract JSON
        try:
            # Simple extraction if wrapped in markdown
            if "```json" in text_response:
                json_str = text_response.split("```json")[1].split("```")[0].strip()
            elif "{" in text_response:
                start = text_response.find("{")
                end = text_response.rfind("}") + 1
                json_str = text_response[start:end]
            else:
                json_str = text_response

            strategy = json.loads(json_str)
            strategy["source_hits"] = relevant_hits # Include raw hits for UI linking
            return strategy
        except Exception as e:
            print(f"❌ JSON Parse Error: {e}")
            return {
                "error": "Failed to parse strategy",
                "raw_response": text_response,
                "source_hits": relevant_hits
            }

if __name__ == "__main__":
    # CLI Mode for testing
    if len(sys.argv) > 1:
        context = sys.argv[1]
        intent = sys.argv[2] if len(sys.argv) > 2 else "investigation"
        
        strategist = CymonidesStrategist()
        result = strategist.generate_strategy(context, intent)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python3 core_strategist.py 'Context' 'Intent'")

