#!/usr/bin/env python3
"""
CYMONIDES API Server - Quick Flask server on port 8100
Proxies to Elasticsearch for the remote client
"""

import os
import sys
from flask import Flask, jsonify, request
from elasticsearch import Elasticsearch

app = Flask(__name__)

ES_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
es = Elasticsearch([ES_HOST])

INDICES = [
    "persons_unified",
    "phones_unified",
    "emails_unified",
    "domains_unified",
    "linkedin_unified"
]

@app.route('/health')
def health():
    try:
        if es.ping():
            return jsonify({"status": "ok", "elasticsearch": "connected"})
    except:
        pass
    return jsonify({"status": "error", "elasticsearch": "disconnected"}), 500

@app.route('/search')
def search():
    query = request.args.get('q', '')
    limit = int(request.args.get('limit', 50))

    if not query:
        return jsonify({"error": "Missing query parameter 'q'"}), 400

    results = []
    indices_searched = []

    for index in INDICES:
        try:
            resp = es.search(
                index=index,
                body={
                    "query": {
                        "multi_match": {
                            "query": query,
                            "fields": ["*"],
                            "type": "best_fields"
                        }
                    },
                    "size": limit
                }
            )
            hits = resp.get('hits', {}).get('hits', [])
            for hit in hits:
                results.append({
                    "index": index,
                    "score": hit.get('_score'),
                    "data": hit.get('_source', {})
                })
            indices_searched.append(index)
        except Exception as e:
            pass

    return jsonify({
        "query": query,
        "total": len(results),
        "results": results[:limit],
        "indices_searched": indices_searched
    })

@app.route('/phone/<phone>')
def search_phone(phone):
    try:
        resp = es.search(
            index="phones_unified",
            body={
                "query": {
                    "bool": {
                        "should": [
                            {"match": {"phone": phone}},
                            {"match": {"phone_raw": phone}},
                            {"wildcard": {"phone": f"*{phone[-8:]}*"}}
                        ]
                    }
                },
                "size": 100
            }
        )
        hits = resp.get('hits', {}).get('hits', [])
        return jsonify({
            "query": phone,
            "total": len(hits),
            "results": [h.get('_source', {}) for h in hits]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting CYMONIDES API Server on port 8100...")
    app.run(host='0.0.0.0', port=8100, threaded=True)
