#!/usr/bin/env python3
"""
Gemini orchestration for large document processing in EDITh.
Handles planning and reviewing large document edits.
"""

import os
import sys
import json
import google.generativeai as genai
from typing import Dict, List, Any

# Configure Gemini
API_KEY = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
if not API_KEY:
    print("Error: GEMINI_API_KEY or GOOGLE_API_KEY not found in environment", file=sys.stderr)
    sys.exit(1)

genai.configure(api_key=API_KEY)

# Initialize the model
model = genai.GenerativeModel('gemini-2.0-flash')

def create_execution_plan(command: str, document_structure: Dict, context: Dict) -> Dict:
    """Create an execution plan for processing document units"""
    
    # Build prompt for Gemini
    prompt = f"""You are an AI orchestrator managing document editing operations.
    
Task: Create an execution plan for the following command:
"{command}"

Document Structure:
- Total sections: {document_structure['totalUnits']}
- Total tokens: {document_structure['totalTokens']}
- Sections:
"""
    
    for unit in document_structure['units']:
        prompt += f"\n  - {unit['title']} (ID: {unit['id']}, ~{unit['tokens']} tokens)"
        prompt += f"\n    Preview: {unit['preview']}"
    
    if context.get('hasContextReference'):
        prompt += "\n\nNote: The command references 'Context' which refers to the context panel files."
    if context.get('hasTargetReference'):
        prompt += "\n\nNote: The command references 'Target' which refers to the main document being edited."
    
    prompt += """

Please create an execution plan that:
1. Analyzes what changes need to be made
2. Provides specific instructions for each section
3. Considers dependencies between sections
4. Ensures consistency across the document

Return a JSON response with:
{
    "summary": "Brief description of the plan",
    "approach": "Overall approach to the task",
    "unitInstructions": {
        "unit-0": "Specific instruction for this section",
        "unit-1": "Specific instruction for this section",
        ...
    },
    "dependencies": ["List of considerations for maintaining consistency"],
    "expectedOutcome": "What the document should look like after changes"
}
"""
    
    try:
        response = model.generate_content(prompt)
        
        # Extract JSON from response
        text = response.text
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0]
        elif '```' in text:
            text = text.split('```')[1].split('```')[0]
        
        plan_data = json.loads(text.strip())
        return plan_data
        
    except Exception as e:
        print(f"Error creating execution plan: {e}", file=sys.stderr)
        return {
            "summary": "Process each section according to the command",
            "approach": "Apply the requested changes to each section",
            "unitInstructions": {
                unit['id']: f"Apply command to section: {unit['title']}"
                for unit in document_structure['units']
            },
            "dependencies": [],
            "expectedOutcome": "Document with requested changes applied"
        }

def review_processed_units(command: str, original_units: List[Dict], 
                          processed_units: List[Dict], execution_plan: Dict) -> Dict:
    """Review processed units for consistency and quality"""
    
    # Build prompt for review
    prompt = f"""You are reviewing the results of a document editing operation.

Original Command: "{command}"

Execution Plan Summary: {execution_plan.get('summary', 'N/A')}

Please review the changes made to each section and:
1. Check if changes properly implement the command
2. Identify any inconsistencies between sections
3. Suggest corrections if needed
4. Verify the overall quality and coherence

Changes by section:
"""
    
    for processed in processed_units[:5]:  # Limit to first 5 for context
        original = next((u for u in original_units if u['id'] == processed['id']), None)
        if original:
            prompt += f"\n\nSection: {original['title']}"
            prompt += f"\nOriginal (first 200 chars): {original['content'][:200]}..."
            prompt += f"\nProcessed (first 200 chars): {processed['processedContent'][:200]}..."
            if processed.get('changes'):
                prompt += f"\nReported changes: {', '.join(processed['changes'][:3])}"
    
    if len(processed_units) > 5:
        prompt += f"\n\n... and {len(processed_units) - 5} more sections"
    
    prompt += """

Return a JSON response with:
{
    "summary": "Overall assessment of the changes",
    "quality": "high|medium|low",
    "needsCorrection": true|false,
    "corrections": [
        {
            "unitId": "unit-X",
            "issue": "Description of the issue",
            "instruction": "Specific instruction to fix it"
        }
    ],
    "consistencyIssues": ["List of any consistency problems found"],
    "overallFeedback": "General feedback about the operation"
}
"""
    
    try:
        response = model.generate_content(prompt)
        
        # Extract JSON from response
        text = response.text
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0]
        elif '```' in text:
            text = text.split('```')[1].split('```')[0]
        
        review_data = json.loads(text.strip())
        return review_data
        
    except Exception as e:
        print(f"Error reviewing units: {e}", file=sys.stderr)
        return {
            "summary": "Review completed",
            "quality": "medium",
            "needsCorrection": False,
            "corrections": [],
            "consistencyIssues": [],
            "overallFeedback": "Changes applied"
        }

def main():
    """Main entry point for the orchestration script"""
    if len(sys.argv) < 2:
        print("Usage: gemini_orchestration.py [plan|review]", file=sys.stderr)
        sys.exit(1)
    
    operation = sys.argv[1]
    
    # Read input from stdin
    input_data = json.loads(sys.stdin.read())
    
    try:
        if operation == 'plan':
            result = create_execution_plan(
                input_data['command'],
                input_data['documentStructure'],
                input_data['context']
            )
        elif operation == 'review':
            result = review_processed_units(
                input_data['command'],
                input_data['originalUnits'],
                input_data['processedUnits'],
                input_data['executionPlan']
            )
        else:
            print(f"Unknown operation: {operation}", file=sys.stderr)
            sys.exit(1)
        
        # Output result as JSON
        print(json.dumps(result))
        
    except Exception as e:
        print(f"Error in {operation}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()