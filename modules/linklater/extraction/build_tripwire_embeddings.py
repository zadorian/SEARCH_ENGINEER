#!/usr/bin/env python3
"""
Build Tripwire Embeddings from Comprehensive Golden Lists.

Generates 768-dimensional embeddings using intfloat/multilingual-e5-base for:
1. Investigation themes (ownership_analysis, asset_trace, etc.)
2. Industry themes (banking, pharma, etc.)
3. Phenomena (IPO, fraud, sanctions, etc.)
4. Red flags (money laundering, PEP, offshore, etc.)
5. Methodologies (corporate_registry_search, humint, etc.)

Output: golden_lists_with_embeddings.json - ready for tripwire matching.
"""

import json
import logging
import torch
import numpy as np
from pathlib import Path
from typing import Dict, List, Any
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
INPUT_FILE = PROJECT_ROOT / "input_output" / "matrix" / "golden_lists_comprehensive.json"
OUTPUT_FILE = PROJECT_ROOT / "input_output" / "matrix" / "golden_lists_with_embeddings.json"

# Model config - matches UniversalExtractor
MODEL_NAME = "intfloat/multilingual-e5-base"
EMBEDDING_DIM = 768


def load_model():
    """Load the embedding model."""
    try:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading model: {MODEL_NAME}")
        device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        logger.info(f"Using device: {device}")
        model = SentenceTransformer(MODEL_NAME, device=device)
        return model
    except ImportError:
        logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
        raise


def embed_category(model, category: Dict) -> Dict:
    """
    Embed a category and its variations.

    For E5 models, we use "passage: " prefix for the concepts.
    Returns the category with added embedding vectors.
    """
    variations = category.get('variations', [])
    canonical = category.get('canonical', '')

    if not variations:
        variations = [canonical]

    # Prepare texts with E5 prefix
    texts = [f"passage: {v}" for v in variations[:50]]  # Cap at 50 for efficiency

    # Get embeddings for all variations
    embeddings = model.encode(texts, convert_to_tensor=True, show_progress_bar=False)

    # Compute prototype vector (mean of all variation embeddings)
    prototype = torch.mean(embeddings, dim=0)

    # Also store individual variation embeddings for fine-grained matching
    variation_embeddings = embeddings.cpu().numpy().tolist()

    # Store prototype and variation embeddings
    category['embedding'] = prototype.cpu().numpy().tolist()
    category['variation_embeddings'] = variation_embeddings[:20]  # Store top 20 for efficiency

    return category


def build_embeddings():
    """Main embedding pipeline."""
    logger.info("=" * 60)
    logger.info("Building Tripwire Embeddings")
    logger.info("=" * 60)

    # Load golden lists
    logger.info(f"\nLoading: {INPUT_FILE}")
    with open(INPUT_FILE, 'r') as f:
        data = json.load(f)

    # Load model
    model = load_model()

    # Update meta
    data['meta']['has_embeddings'] = True
    data['meta']['embedding_model'] = MODEL_NAME
    data['meta']['embedding_dim'] = EMBEDDING_DIM

    # Embed each category type
    category_types = ['themes', 'phenomena', 'red_flags', 'methodologies']

    for cat_type in category_types:
        categories = data.get(cat_type, {}).get('categories', [])
        if not categories:
            continue

        logger.info(f"\nEmbedding {len(categories)} {cat_type}...")

        for i, cat in enumerate(tqdm(categories, desc=cat_type)):
            categories[i] = embed_category(model, cat)

        data[cat_type]['categories'] = categories

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("EMBEDDING SUMMARY")
    logger.info("=" * 60)

    total_embeddings = 0
    for cat_type in category_types:
        categories = data.get(cat_type, {}).get('categories', [])
        embedded = sum(1 for c in categories if 'embedding' in c)
        total_embeddings += embedded
        logger.info(f"{cat_type}: {embedded} categories embedded")

    logger.info(f"\nTotal: {total_embeddings} category embeddings")
    logger.info(f"Embedding dimension: {EMBEDDING_DIM}")

    # Save
    logger.info(f"\nSaving to: {OUTPUT_FILE}")
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info("=" * 60)
    logger.info("DONE - Embeddings ready for tripwire matching")
    logger.info("=" * 60)

    return data


def verify_embeddings():
    """Quick verification of embeddings."""
    if not OUTPUT_FILE.exists():
        logger.error(f"Output file not found: {OUTPUT_FILE}")
        return

    with open(OUTPUT_FILE, 'r') as f:
        data = json.load(f)

    print("\n=== EMBEDDING VERIFICATION ===\n")

    for cat_type in ['themes', 'phenomena', 'red_flags', 'methodologies']:
        categories = data.get(cat_type, {}).get('categories', [])
        if not categories:
            continue

        # Check first category
        first = categories[0]
        emb = first.get('embedding', [])

        print(f"{cat_type}:")
        print(f"  First category: {first['canonical']}")
        print(f"  Embedding dim: {len(emb)}")
        print(f"  Embedding sample: [{emb[0]:.4f}, {emb[1]:.4f}, ..., {emb[-1]:.4f}]")
        print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--verify', action='store_true', help="Only verify existing embeddings")
    args = parser.parse_args()

    if args.verify:
        verify_embeddings()
    else:
        build_embeddings()
        verify_embeddings()
