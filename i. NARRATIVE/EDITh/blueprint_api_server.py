#!/usr/bin/env python3
"""
Blueprint API Server - Handles Claude Opus AI processing for argument reordering
Provides RESTful API endpoints for the ArgumentOrderingPanel
"""

import json
import sys
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import tempfile
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend requests

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSOR_PATH = os.path.join(SCRIPT_DIR, 'claude_opus_blueprint_processor.py')

@app.route('/api/blueprint/process', methods=['POST'])
def process_blueprint():
    """
    Process Blueprint with Claude Opus AI
    Handles argument reordering and text generation
    """
    try:
        # Get request data
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        logger.info(f"Processing blueprint request with {len(data.get('blueprint', {}).get('sections', []))} sections")
        
        # Validate required fields
        required_fields = ['blueprint', 'prompt']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Call the Claude Opus processor
        result = call_claude_processor(data)
        
        if 'error' in result:
            logger.error(f"Claude processor error: {result['error']}")
            return jsonify(result), 500
        
        logger.info("Blueprint processing completed successfully")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error processing blueprint: {str(e)}")
        return jsonify({
            'error': str(e),
            'content': '',
            'thinking': [],
            'tool_uses': []
        }), 500

def call_claude_processor(data):
    """
    Call the Claude Opus blueprint processor
    """
    try:
        # Prepare input data with proper structure
        input_data = {
            'blueprint': data.get('blueprint', {}),
            'prompt': data.get('prompt', ''),
            'contextDocs': data.get('contextDocs', []),
            'options': data.get('options', {})  # Critical: Include options for Smart Note context
        }
        
        # Create temporary file for input
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump(input_data, temp_file)
            temp_file_path = temp_file.name
        
        try:
            # Call the processor
            result = subprocess.run([
                sys.executable, PROCESSOR_PATH
            ], input=json.dumps(input_data), text=True, capture_output=True, timeout=120)
            
            if result.returncode != 0:
                error_msg = result.stderr or "Unknown error occurred"
                logger.error(f"Processor failed with return code {result.returncode}: {error_msg}")
                return {
                    'error': f'Claude processor failed: {error_msg}',
                    'content': '',
                    'thinking': [],
                    'tool_uses': []
                }
            
            # Parse result
            try:
                output = json.loads(result.stdout)
                return output
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse processor output: {e}")
                return {
                    'error': f'Invalid response from Claude processor: {str(e)}',
                    'content': result.stdout[:500] if result.stdout else '',  # Return first 500 chars as fallback
                    'thinking': [],
                    'tool_uses': []
                }
                
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_file_path)
            except:
                pass
                
    except subprocess.TimeoutExpired:
        logger.error("Claude processor timed out")
        return {
            'error': 'Claude processor timed out (120 seconds)',
            'content': '',
            'thinking': [],
            'tool_uses': []
        }
    except Exception as e:
        logger.error(f"Error calling Claude processor: {str(e)}")
        return {
            'error': f'Failed to call Claude processor: {str(e)}',
            'content': '',
            'thinking': [],
            'tool_uses': []
        }

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Blueprint API Server',
        'processor_available': os.path.exists(PROCESSOR_PATH)
    })

@app.route('/api/blueprint/validate', methods=['POST'])
def validate_arguments():
    """
    Validate argument order and dependencies
    """
    try:
        data = request.get_json()
        arguments = data.get('arguments', [])
        
        violations = []
        
        # Check argument dependencies
        for i, arg in enumerate(arguments):
            if 'dependencies' in arg and arg['dependencies']:
                for dep_id in arg['dependencies']:
                    # Find dependency in list
                    dep_index = next((j for j, a in enumerate(arguments) if a.get('id') == dep_id), -1)
                    if dep_index > i:
                        violations.append({
                            'type': 'dependency',
                            'message': f'Argument "{arg.get("claim", "Unknown")}" depends on argument that appears later',
                            'argument_id': arg.get('id'),
                            'dependency_id': dep_id
                        })
        
        return jsonify({
            'valid': len(violations) == 0,
            'violations': violations
        })
        
    except Exception as e:
        logger.error(f"Error validating arguments: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/blueprint/analyze-dependencies', methods=['POST'])
def analyze_dependencies():
    """
    Analyze argument dependencies and suggest optimal ordering
    """
    try:
        data = request.get_json()
        arguments = data.get('arguments', [])
        
        # Simple analysis - sort by strength and check dependencies
        analysis = {
            'suggested_order': sorted(arguments, key=lambda x: x.get('strength', 0.5), reverse=True),
            'dependency_chains': find_dependency_chains(arguments),
            'recommendations': []
        }
        
        # Generate recommendations
        if len(analysis['dependency_chains']) > 0:
            analysis['recommendations'].append('Group dependent arguments together for better flow')
        
        strength_variance = calculate_strength_variance(arguments)
        if strength_variance > 0.3:
            analysis['recommendations'].append('Consider mixing strong and weak arguments for better persuasion')
            
        return jsonify(analysis)
        
    except Exception as e:
        logger.error(f"Error analyzing dependencies: {str(e)}")
        return jsonify({'error': str(e)}), 500

def find_dependency_chains(arguments):
    """Find chains of dependent arguments"""
    chains = []
    # Simple implementation - could be enhanced
    for arg in arguments:
        if 'dependencies' in arg and arg['dependencies']:
            chains.append({
                'root': arg['id'],
                'dependencies': arg['dependencies']
            })
    return chains

def calculate_strength_variance(arguments):
    """Calculate variance in argument strengths"""
    strengths = [arg.get('strength', 0.5) for arg in arguments]
    if not strengths:
        return 0
    
    mean = sum(strengths) / len(strengths)
    variance = sum((x - mean) ** 2 for x in strengths) / len(strengths)
    return variance ** 0.5

if __name__ == '__main__':
    # Check if Claude processor exists
    if not os.path.exists(PROCESSOR_PATH):
        logger.warning(f"Claude processor not found at {PROCESSOR_PATH}")
        logger.warning("API will still start but Claude processing will fail")
    
    # Check for API key
    if not os.environ.get('ANTHROPIC_API_KEY'):
        logger.warning("ANTHROPIC_API_KEY environment variable not set")
        logger.warning("Claude processing will fail without API key")
    
    logger.info("Starting Blueprint API Server...")
    logger.info(f"Claude processor path: {PROCESSOR_PATH}")
    logger.info("Server will run on http://localhost:5000")
    
    # Run development server
    app.run(host='0.0.0.0', port=5000, debug=True)