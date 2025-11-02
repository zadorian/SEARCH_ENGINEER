#!/usr/bin/env python3
import sys
import json
import os
import traceback
from google import genai
from google.genai import types

# API Key from environment
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
if not GOOGLE_API_KEY:
    print("Error: GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set", file=sys.stderr)
    sys.exit(1)

# Configure the client
client = genai.Client(api_key=GOOGLE_API_KEY)

def fill_gap(context, gap, additional_context=None):
    """Fill a gap using Gemini with grounding for citations"""
    try:
        # Normalize input: accept both dict-based and raw-text inputs
        # If context is a string, derive before/after around the first '[?]'
        if isinstance(context, str):
            text = context
            gap_pos = text.find('[?]')
            if gap_pos == -1:
                # No gap found; return no-op
                return {"text": "", "citations": []}
            before = text[:gap_pos]
            after = text[gap_pos + 3:]
            context = {"before": before.strip(), "after": after.strip()}

        # If gap is a string, convert to default question type
        if isinstance(gap, str):
            gap = {"type": "question", "description": gap}

        # Define the grounding tool
        grounding_tool = types.Tool(
            google_search=types.GoogleSearch()
        )
        
        # Configure generation settings
        config = types.GenerateContentConfig(
            tools=[grounding_tool]
        )
        
        # Build prompt with additional context if provided
        context_prefix = ""
        if additional_context:
            context_prefix = f"""Additional background information:
{additional_context}

Use this context to inform your response when relevant.

"""
        
        # Enable grounding for factual queries
        gap_type = gap.get('type') if isinstance(gap, dict) else 'question'
        if gap_type == 'question':
            prompt = f"""{context_prefix}Given this context: "{context['before']} [?] {context['after']}"
            
Please provide a brief, factual completion for the [?] placeholder. 
The answer should be concise and fit naturally in the sentence.
Respond with just the completion text, no explanation."""
        else:
            prompt = f"""{context_prefix}Given this context: "{context['before']} [{gap['description']}] {context['after']}"
            
The placeholder [{gap['description']}] needs to be replaced with an appropriate word or short phrase.
"{gap['description']}" describes what should go there.
Please provide factual information with sources when available.
Respond with just the replacement text, no explanation."""
        
        # Use grounding for ALL gaps to get citations
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=prompt,
            config=config
        )
        
        result_text = response.text.strip()
        
        # Check if the context after the gap already has punctuation
        after_text = context.get('after', '').strip()
        if after_text and after_text[0] in '.!?':
            # Remove trailing punctuation from result if the next character is already punctuation
            if result_text and result_text[-1] in '.!?':
                result_text = result_text[:-1]
        
        # Extract citations if grounding was used
        citations = []
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                metadata = candidate.grounding_metadata
                
                # Extract URLs from grounding chunks
                if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                    for chunk in metadata.grounding_chunks:
                        if hasattr(chunk, 'web') and chunk.web:
                            if hasattr(chunk.web, 'uri'):
                                citations.append(chunk.web.uri)
                            elif hasattr(chunk.web, 'url'):
                                citations.append(chunk.web.url)
        
        return {
            "text": result_text,
            "citations": citations
        }
    except Exception as e:
        print(json.dumps({"error": f"fill_gap error: {str(e)}"}))
        return None

if __name__ == "__main__":
    try:
        # Read input from stdin
        input_text = sys.stdin.read()
        input_data = json.loads(input_text)
        
        # Extract additional context if provided
        additional_context = input_data.get('additionalContext', None)
        
        result = fill_gap(input_data['context'], input_data['gap'], additional_context)
        
        if result:
            if isinstance(result, dict):
                print(json.dumps({"suggestion": result["text"], "citations": result.get("citations", [])}))
            else:
                # Fallback for old format
                print(json.dumps({"suggestion": result}))
        else:
            print(json.dumps({"error": "Failed to generate suggestion"}))
    except Exception as e:
        print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}))