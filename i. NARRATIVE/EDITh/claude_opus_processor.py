#!/usr/bin/env python3
"""
Claude Opus 4 Processor for Blueprint-to-Text Generation
Supports extended thinking for complex document generation
"""

import json
import sys
import os
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from anthropic import Anthropic

class ClaudeOpusProcessor:
    def __init__(self):
        self.api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        
        self.client = Anthropic(api_key=self.api_key)
        self.model = "claude-opus-4-1-20250805"
        self.max_tokens = 8000  # Increased to accommodate thinking tokens
        self.temperature = 0.7
        
    def generate_text_from_blueprint(self, blueprint: Dict, prompt: str, use_extended_thinking: bool = True) -> Dict:
        """
        Generate text from a blueprint using Claude Opus 4 with extended thinking
        
        Args:
            blueprint: The document blueprint structure
            prompt: The formatted prompt describing the blueprint
            use_extended_thinking: Whether to use extended thinking mode
            
        Returns:
            Dict with 'content' and optionally 'thinking' fields
        """
        try:
            # Prepare the system prompt
            system_prompt = """You are Claude Code Opus 4, an advanced AI assistant specialized in generating 
high-quality text from document blueprints. You excel at understanding document structure, 
intent, and style to create coherent, well-organized content that precisely follows specifications.

When given a blueprint, you will:
1. Carefully analyze the global intent and document style
2. Generate content for each section according to its specifications
3. Maintain consistency in tone and style throughout
4. Ensure smooth transitions between sections
5. Include all required key points and follow argument order
6. Match target lengths where specified

You are known for your ability to generate thoughtful, nuanced content that goes beyond 
surface-level writing to create truly engaging and purposeful documents."""

            # Prepare the user prompt
            user_prompt = f"""Please generate a complete document based on the following blueprint:

{prompt}

Important instructions:
- Generate complete, publication-ready content for each section
- Follow the specified intent, style, and tone for each section
- Include smooth transitions between sections
- Ensure the document flows naturally while adhering to the blueprint structure
- If target lengths are specified, aim to match them closely
- The final output should be a cohesive, well-written document ready for use

Begin generating the document now:"""

            # Call Claude API with extended thinking
            response = asyncio.run(self.call_claude_api(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                use_extended_thinking=use_extended_thinking
            ))
            
            return {
                "content": response.get('content', ''),
                "thinking": response.get('thinking'),
                "model": response.get('model', self.model),
                "timestamp": datetime.now().isoformat(),
                "usage": response.get('usage')
            }
            
        except Exception as e:
            print(f"Error generating text from blueprint: {str(e)}", file=sys.stderr)
            raise
    
    async def call_claude_api(self, system_prompt: str, user_prompt: str, use_extended_thinking: bool = True) -> Dict:
        """
        Call Claude API with extended thinking support
        
        Args:
            system_prompt: System message for Claude
            user_prompt: User message for Claude
            use_extended_thinking: Whether to use extended thinking mode
            
        Returns:
            Dict with response data including content and thinking
        """
        try:
            # Prepare the request parameters
            request_params = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ]
            }
            
            # Add extended thinking configuration if enabled
            # Note: Extended thinking is currently only supported by select models
            if use_extended_thinking:
                request_params["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": 4000  # Budget for thinking (less than max_tokens)
                }
                # Temperature must be 1 when thinking is enabled
                request_params["temperature"] = 1.0
            else:
                request_params["temperature"] = self.temperature
            
            # Make the API call
            try:
                response = await asyncio.to_thread(
                    self.client.messages.create,
                    **request_params
                )
            except Exception as e:
                # If extended thinking is not supported, retry without it
                if "does not support thinking" in str(e) and use_extended_thinking:
                    print(f"Extended thinking not supported by model {self.model}, falling back to normal mode", file=sys.stderr)
                    request_params.pop("thinking", None)
                    request_params["temperature"] = self.temperature
                    response = await asyncio.to_thread(
                        self.client.messages.create,
                        **request_params
                    )
                else:
                    raise
            
            # Extract content and thinking from response
            content = ""
            thinking = None
            
            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "thinking":
                    # For Claude 4, thinking is summarized
                    thinking = getattr(block, 'summary', '[Thinking redacted]')
            
            return {
                "content": content,
                "thinking": thinking,
                "model": response.model,
                "usage": {
                    "input_tokens": response.usage.input_tokens if hasattr(response, 'usage') else 0,
                    "output_tokens": response.usage.output_tokens if hasattr(response, 'usage') else 0
                }
            }
            
        except Exception as e:
            raise Exception(f"Claude API error: {str(e)}")
    
    def generate_placeholder_content(self, blueprint):
        """Generate placeholder content based on blueprint structure (fallback)"""
        lines = []
        
        # Title
        lines.append(f"# {blueprint.get('title', 'Untitled Document')}\n")
        
        # Introduction based on global intent
        if blueprint.get('globalIntent'):
            lines.append(f"This document {blueprint['globalIntent'].lower()}.\n")
        
        # Process sections
        sections = blueprint.get('sections', [])
        for i, section in enumerate(sections):
            lines.append(f"\n## {section.get('title', f'Section {i+1}')}\n")
            
            if section.get('intent'):
                lines.append(f"{section['intent']}. ")
            
            if section.get('keyPoints'):
                lines.append("Key points covered:\n")
                for point in section['keyPoints']:
                    lines.append(f"- {point}\n")
            
            # Add placeholder paragraph
            lines.append(f"\nThis section would contain detailed content about {section.get('title', 'this topic').lower()}, ")
            lines.append(f"written in a {section.get('style', 'clear')} style")
            
            if section.get('metadata', {}).get('targetLength'):
                lines.append(f", targeting approximately {section['metadata']['targetLength']}")
            
            lines.append(".\n")
        
        return '\n'.join(lines)

def main():
    """Main entry point for the script"""
    try:
        # Read input from stdin
        input_data = json.loads(sys.stdin.read())
        
        blueprint = input_data.get('blueprint')
        prompt = input_data.get('prompt')
        use_extended_thinking = input_data.get('useExtendedThinking', True)
        
        if not blueprint or not prompt:
            raise ValueError("Blueprint and prompt are required")
        
        # Initialize processor
        processor = ClaudeOpusProcessor()
        
        # Generate text from blueprint
        result = processor.generate_text_from_blueprint(
            blueprint=blueprint,
            prompt=prompt,
            use_extended_thinking=use_extended_thinking
        )
        
        # Output the result
        print(json.dumps(result))
        
    except Exception as e:
        error_response = {
            "error": str(e),
            "content": None,
            "thinking": None
        }
        print(json.dumps(error_response))
        sys.exit(1)

if __name__ == "__main__":
    main()