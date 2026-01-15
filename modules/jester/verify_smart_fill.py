#!/usr/bin/env python3
"""
Verification Script for Jester Smart Fill & Context Bridges
Tests:
1. Context persistence (via API simulation)
2. Jester 'fill_section' execution with context injection
3. Grid -> Narrative flow (conceptually)
"""

import requests
import json
import sys
import time

API_BASE = "http://localhost:8000/api"

def log(msg):
    print(f"[TEST] {msg}")

def test_jester_fill_section():
    log("Testing Jester Smart Fill...")
    
    # 1. Simulate Context Injection
    context_material = """
    Google's revenue in 2023 was $307 billion.
    The CEO is Sundar Pichai.
    """
    
    payload = {
        "mode": "fill_section",
        "content": context_material, # Background material
        "query": "What is the revenue and who is CEO?",
        "config": {
            "context": "## Financial Overview", # The Topic
            "tier": "fast",
            "verify": False
        }
    }
    
    try:
        # Start Job
        log("Sending request to /jester/run...")
        resp = requests.post(f"{API_BASE}/jester/run", json=payload)
        if resp.status_code != 200:
            log(f"FAILED: {resp.text}")
            return False
            
        job_id = resp.json().get("jobId")
        log(f"Job started: {job_id}")
        
        # Stream Result
        log("Streaming results...")
        stream = requests.get(f"{API_BASE}/jester/stream/{job_id}", stream=True)
        
        result_content = ""
        for line in stream.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                if decoded.startswith("data: "):
                    data = json.loads(decoded[6:])
                    if data.get("type") == "result":
                        result_content = data.get("result")
                        log("Received Final Result!")
                    elif data.get("status") == "completed":
                        break
                    elif data.get("text"):
                        log(f"Progress: {data['text']}")
                        
        if "307 billion" in result_content and "Sundar Pichai" in result_content:
            log("SUCCESS: Result contains expected context data.")
            return True
        else:
            log(f"FAILURE: Result missing context data. Got: {result_content[:100]}...")
            return False
            
    except Exception as e:
        log(f"EXCEPTION: {e}")
        return False

if __name__ == "__main__":
    if test_jester_fill_section():
        sys.exit(0)
    else:
        sys.exit(1)
