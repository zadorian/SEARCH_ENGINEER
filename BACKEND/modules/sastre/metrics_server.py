#\!/usr/bin/env python3
"""
SASTRE Prometheus Metrics Server

Exposes metrics at /metrics for Prometheus scraping.
"""

import asyncio
from prometheus_client import (
    Counter, Histogram, Gauge, Info,
    generate_latest, REGISTRY
)
from aiohttp import web

# =============================================================================
# METRICS DEFINITIONS
# =============================================================================

TOOL_CALLS = Counter(
    "sastre_tool_calls_total",
    "Total tool calls",
    ["tool_name", "status"]
)

TOOL_DURATION = Histogram(
    "sastre_tool_duration_seconds",
    "Tool execution duration in seconds",
    ["tool_name"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)

CIRCUIT_STATE = Gauge(
    "sastre_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half_open, 2=open)",
    ["circuit_name"]
)

ACTIVE_INVESTIGATIONS = Gauge(
    "sastre_active_investigations",
    "Number of active investigations"
)

SYSTEM_INFO = Info(
    "sastre_system",
    "SASTRE system information"
)


class MetricsBridge:
    """Bridge between production.py metrics and Prometheus."""
    
    def __init__(self):
        self._initialized = False
    
    def initialize(self):
        if self._initialized:
            return
        SYSTEM_INFO.info({
            "version": "1.0.0",
            "sdk_version": "0.1.18",
            "environment": "production"
        })
        self._initialized = True
    
    def sync_from_production(self):
        try:
            from .production import _circuit_breakers, CircuitState
            state_map = {
                CircuitState.CLOSED: 0,
                CircuitState.HALF_OPEN: 1,
                CircuitState.OPEN: 2
            }
            for name, cb in _circuit_breakers.items():
                CIRCUIT_STATE.labels(circuit_name=name).set(state_map.get(cb.state, 0))
        except Exception:
            pass


metrics_bridge = MetricsBridge()


async def metrics_handler(request):
    metrics_bridge.sync_from_production()
    body = generate_latest(REGISTRY)
    return web.Response(body=body, content_type="text/plain")


async def health_handler(request):
    return web.json_response({"status": "healthy"})


async def start_metrics_server(host: str = "0.0.0.0", port: int = 9090):
    metrics_bridge.initialize()
    app = web.Application()
    app.router.add_get("/metrics", metrics_handler)
    app.router.add_get("/health", health_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"Metrics server running on http://{host}:{port}/metrics")
    return runner


if __name__ == "__main__":
    async def main():
        runner = await start_metrics_server()
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await runner.cleanup()
    
    asyncio.run(main())
