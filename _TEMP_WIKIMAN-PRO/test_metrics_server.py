#!/usr/bin/env python3
"""
Simple Flask server to test the Prometheus metrics endpoint.
Run: python3 test_metrics_server.py
Then: curl http://localhost:5055/metrics
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, Response
from countries.metrics_endpoint import generate_metrics_response, increment_api_requests, observe_api_latency, increment_cache_hits, increment_layer_usage

app = Flask(__name__)


@app.route("/")
def index():
    return """
    <h1>WIKIMAN-PRO Metrics Test Server</h1>
    <ul>
        <li><a href="/metrics">Prometheus Metrics Endpoint</a></li>
        <li><a href="/test">Generate Test Metrics</a></li>
    </ul>
    """


@app.route("/metrics")
def metrics():
    """Prometheus metrics endpoint for observability."""
    metrics_text = generate_metrics_response()
    return Response(metrics_text, mimetype="text/plain; version=0.0.4")


@app.route("/test")
def test():
    """Generate some test metrics."""
    # Simulate some API calls
    increment_api_requests(country="uk", endpoint="search", status=200)
    increment_api_requests(country="sg", endpoint="search", status=200)
    increment_api_requests(country="hk", endpoint="profile", status=200)
    increment_api_requests(country="au", endpoint="search", status=404)
    increment_api_requests(country="jp", endpoint="search", status=200)

    # Simulate latencies
    observe_api_latency(country="uk", endpoint="search", latency_ms=245.5)
    observe_api_latency(country="sg", endpoint="search", latency_ms=198.2)
    observe_api_latency(country="hk", endpoint="profile", latency_ms=156.7)
    observe_api_latency(country="au", endpoint="search", latency_ms=512.3)
    observe_api_latency(country="jp", endpoint="search", latency_ms=89.4)

    # Simulate cache operations
    increment_cache_hits(layer="api", hit=True)
    increment_cache_hits(layer="api", hit=True)
    increment_cache_hits(layer="api", hit=False)
    increment_cache_hits(layer="wikiman", hit=True)

    # Simulate layer usage
    increment_layer_usage(country="uk", layer="api", success=True)
    increment_layer_usage(country="sg", layer="api", success=True)
    increment_layer_usage(country="hk", layer="api", success=True)
    increment_layer_usage(country="au", layer="api", success=False)
    increment_layer_usage(country="jp", layer="wikiman", success=True)

    return """
    <h1>Test Metrics Generated!</h1>
    <p>Metrics have been generated for all 5 countries (UK, SG, HK, AU, JP)</p>
    <p><a href="/metrics">View Prometheus Metrics</a></p>
    """


if __name__ == "__main__":
    print("=" * 60)
    print("WIKIMAN-PRO Metrics Test Server")
    print("=" * 60)
    print("Starting server on http://localhost:5055")
    print()
    print("Endpoints:")
    print("  - http://localhost:5055/          (Home page)")
    print("  - http://localhost:5055/metrics   (Prometheus metrics)")
    print("  - http://localhost:5055/test      (Generate test metrics)")
    print()
    print("Test with:")
    print("  curl http://localhost:5055/metrics")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5055, debug=False)
