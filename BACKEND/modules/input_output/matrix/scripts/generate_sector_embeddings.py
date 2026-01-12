#!/usr/bin/env python3
"""
Generate Sector Embeddings
--------------------------
Reads the unified `sectors.json`, creates a rich semantic text representation for each sector,
and generates vector embeddings using 'all-MiniLM-L6-v2'.

Output: `input_output/matrix/definitions/sector_embeddings.json`
"""

import json
import os
import logging
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent # Drill Search Root
DEFINITIONS_DIR = BASE_DIR / "input_output" / "matrix" / "definitions"
SECTORS_FILE = DEFINITIONS_DIR / "sectors.json"
OUTPUT_FILE = DEFINITIONS_DIR / "sector_embeddings.json"

def generate_embeddings():
    if not SECTORS_FILE.exists():
        logger.error(f"Sectors file not found at {SECTORS_FILE}")
        return

    logger.info("Loading sector definitions...")
    with open(SECTORS_FILE, 'r') as f:
        data = json.load(f)

    sectors = data.get('sectors', [])
    logger.info(f"Found {len(sectors)} sectors.")

    # Initialize Model
    logger.info("Loading embedding model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer('all-MiniLM-L6-v2')

    embeddings_map = {
        "model": "all-MiniLM-L6-v2",
        "generated_at": data.get("last_updated"), # Sync version
        "sectors": {}
    }

    for sector in sectors:
        sector_id = sector['id']
        name = sector['name']
        description = sector['description']
        keywords = ", ".join(sector.get('keywords', []))
        
        # Construct a rich semantic string for the sector
        # We weight the name and description heavily
        semantic_text = f"{name}: {description}. Keywords: {keywords}."
        
        logger.info(f"Encoding sector: {name}...")
        vector = model.encode(semantic_text)
        
        # Store as list for JSON serialization
        embeddings_map["sectors"][sector_id] = {
            "vector": vector.tolist(),
            "text_hash": hash(semantic_text) # Simple version check
        }

    # Save to file
    logger.info(f"Saving embeddings to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(embeddings_map, f)
    
    logger.info("Done.")

if __name__ == "__main__":
    generate_embeddings()
