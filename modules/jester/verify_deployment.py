#!/usr/bin/env python3
"""
Final Verification Script
Ensures API endpoints and Jester logic are fully functional.
"""

import requests
import json
import sys
import time

API_BASE = "http://localhost:8000/api"

def log(msg):
    print(f"[VERIFY] {msg}")

def verify_api_health():
    log("Checking API health...")
    try:
        resp = requests.get(f"{API_BASE}/health")
        if resp.status_code == 200:
            log("API is HEALTHY")
            return True
        else:
            log(f"API Unhealthy: {resp.status_code}")
            return False
    except Exception as e:
        log(f"API Connection Failed: {e}")
        return False

def verify_jester_endpoint():
    log("Checking Jester endpoint (Dry Run)...")
    
    payload = {
        "mode": "fill_section",
        "content": "Test content for context injection.",
        "query": "Test query",
        "config": {
            "context": "## Test Section",
            "tier": "fast",
            "verify": False
        }
    }
    
    try:
        resp = requests.post(f"{API_BASE}/jester/run", json=payload)
        if resp.status_code == 200:
            job_id = resp.json().get("jobId")
            log(f"Jester Endpoint Functional. Job ID: {job_id}")
            return True
        else:
            log(f"Jester Endpoint Failed: {resp.text}")
            return False
    except Exception as e:
        log(f"Jester Request Failed: {e}")
        return False

if __name__ == "__main__":
    if verify_api_health() and verify_jester_endpoint():
        log("ALL SYSTEMS GO. Deployment Verified.")
        sys.exit(0)
    else:
        log("VERIFICATION FAILED.")
        sys.exit(1)
