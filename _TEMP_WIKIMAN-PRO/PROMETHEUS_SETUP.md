# Prometheus Monitoring Setup Guide

## Overview

WIKIMAN-PRO now has full Prometheus observability integrated across all 5 country handlers (UK, Singapore, Hong Kong, Australia, Japan). This guide covers setting up Prometheus scraping, visualization, and alerting.

---

## Quick Start

### 1. Start the Test Metrics Server

```bash
# Start the standalone metrics server
python3 test_metrics_server.py

# Server will start on http://localhost:5055
# Metrics available at http://localhost:5055/metrics
```

### 2. Generate Test Data

```bash
# Generate sample metrics
curl http://localhost:5055/test

# View metrics
curl http://localhost:5055/metrics
```

### 3. Start Prometheus

```bash
# Install Prometheus (macOS)
brew install prometheus

# Start with provided config
prometheus --config.file=prometheus.yml

# Prometheus UI: http://localhost:9090
```

---

## Metrics Endpoint Integration

### Flask Integration (webapp/app.py)

The `/metrics` endpoint has been added to the Flask webapp:

```python
from countries.metrics_endpoint import generate_metrics_response

@app.route("/metrics")
def metrics():
    """Prometheus metrics endpoint for observability."""
    metrics_text = generate_metrics_response()
    from flask import Response
    return Response(metrics_text, mimetype="text/plain; version=0.0.4")
```

**Note**: The main `webapp/app.py` has a pre-existing import issue with `mcp.trailblazer_handlers`. Use `test_metrics_server.py` for testing until that's resolved.

---

## Available Metrics

### API Request Metrics

```promql
# Total API requests by country/endpoint/status
wikiman_api_requests_total{country="uk",endpoint="search",status="200"}

# Request rate (requests per second)
rate(wikiman_api_requests_total[5m])
```

### API Latency Metrics

```promql
# P95 latency by country/endpoint
wikiman_api_latency_ms_quantile{country="uk",endpoint="search",quantile="0.95"}

# P50 (median) latency
wikiman_api_latency_ms_quantile{quantile="0.5"}

# P99 latency
wikiman_api_latency_ms_quantile{quantile="0.99"}

# Average latency
rate(wikiman_api_latency_ms_sum[5m]) / rate(wikiman_api_latency_ms_count[5m])
```

### Cache Metrics

```promql
# Cache hit rate by layer
sum(rate(wikiman_cache_operations_total{result="hit"}[5m])) by (layer)
/
sum(rate(wikiman_cache_operations_total[5m])) by (layer)

# Total cache operations
rate(wikiman_cache_operations_total[5m])
```

### Layer Operations

```promql
# API layer success rate by country
sum(rate(wikiman_layer_operations_total{layer="api",result="success"}[5m])) by (country)
/
sum(rate(wikiman_layer_operations_total{layer="api"}[5m])) by (country)

# Fallback to WIKIMAN layer
rate(wikiman_layer_operations_total{layer="wikiman",result="success"}[5m])
```

---

## Alert Rules

Alert rules are defined in `prometheus_alerts.yml`. Key alerts include:

### Performance Alerts

- **HighAPILatency**: P95 latency > 2000ms for 5 minutes
- **CriticalAPILatency**: P95 latency > 5000ms for 2 minutes

### Error Rate Alerts

- **HighAPIErrorRate**: 5xx error rate > 10% for 5 minutes
- **CriticalAPIErrorRate**: 5xx error rate > 50% for 2 minutes

### Layer Health Alerts

- **HighAPILayerFailureRate**: API layer failures > 30% for 5 minutes
- **FrequentWikimanFallback**: Excessive fallback to WIKIMAN layer

### Cache Alerts

- **LowCacheHitRate**: Cache hit rate < 50% for 10 minutes
- **VeryLowCacheHitRate**: Cache hit rate < 20% for 5 minutes

### Availability Alerts

- **NoAPIRequestsReceived**: No requests for 10 minutes

---

## Prometheus Query Examples

### Top 5 Slowest Endpoints

```promql
topk(5, wikiman_api_latency_ms_quantile{quantile="0.95"})
```

### Error Rate by Country

```promql
sum(rate(wikiman_api_requests_total{status=~"5.."}[5m])) by (country)
/
sum(rate(wikiman_api_requests_total[5m])) by (country)
```

### API vs WIKIMAN Layer Usage

```promql
sum(rate(wikiman_layer_operations_total[5m])) by (layer)
```

### Cache Efficiency

```promql
sum(rate(wikiman_cache_operations_total{result="hit"}[5m]))
/
sum(rate(wikiman_cache_operations_total[5m]))
```

---

## Grafana Dashboard Setup

### 1. Install Grafana

```bash
# macOS
brew install grafana

# Start Grafana
brew services start grafana

# Access: http://localhost:3000
# Default login: admin/admin
```

### 2. Add Prometheus Data Source

1. Go to Configuration → Data Sources
2. Click "Add data source"
3. Select "Prometheus"
4. URL: `http://localhost:9090`
5. Click "Save & Test"

### 3. Create Dashboard

Create panels for:

1. **API Request Rate** (by country)
   - Query: `sum(rate(wikiman_api_requests_total[5m])) by (country)`
   - Visualization: Time series

2. **API Latency (P95)** (by country)
   - Query: `wikiman_api_latency_ms_quantile{quantile="0.95"}`
   - Visualization: Time series

3. **Error Rate** (by country)
   - Query: Error rate formula from above
   - Visualization: Gauge (with thresholds)

4. **Cache Hit Rate** (by layer)
   - Query: Cache hit rate formula from above
   - Visualization: Gauge

5. **Layer Usage Distribution**
   - Query: `sum(rate(wikiman_layer_operations_total[5m])) by (layer)`
   - Visualization: Pie chart

---

## Testing Metrics Collection

### 1. Start Test Server

```bash
python3 test_metrics_server.py
```

### 2. Generate Traffic

```bash
# Generate test metrics multiple times
for i in {1..10}; do
  curl -s http://localhost:5055/test > /dev/null
  sleep 1
done
```

### 3. Verify Metrics

```bash
# Check metrics endpoint
curl http://localhost:5055/metrics

# Should show increasing counters and latency samples
```

### 4. Query in Prometheus

```bash
# Open Prometheus UI
open http://localhost:9090

# Try queries:
# - wikiman_api_requests_total
# - rate(wikiman_api_requests_total[1m])
# - wikiman_api_latency_ms_quantile{quantile="0.95"}
```

---

## Production Deployment

### 1. Update webapp/app.py Import

Fix the import issue in `webapp/app.py`:

```python
# Change:
from mcp.trailblazer_handlers import (...)

# To:
from custom_mcp_handlers.trailblazer_handlers import (...)
```

### 2. Configure Prometheus for Production

Update `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'wikiman-pro'
    static_configs:
      - targets: ['your-production-host:5055']
    metrics_path: '/metrics'
```

### 3. Set Up Alertmanager (Optional)

```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'country']
  receiver: 'team-notifications'

receivers:
  - name: 'team-notifications'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK'
        channel: '#monitoring'
```

---

## Verification Checklist

- [ ] Test server starts successfully (`python3 test_metrics_server.py`)
- [ ] `/metrics` endpoint returns Prometheus format
- [ ] Test metrics generation works (`curl http://localhost:5055/test`)
- [ ] Prometheus scrapes successfully
- [ ] All 5 countries appear in metrics (UK, SG, HK, AU, JP)
- [ ] Latency percentiles calculated correctly
- [ ] Cache hit rate displays properly
- [ ] Layer operations tracked accurately
- [ ] Alert rules validate without errors

---

## Troubleshooting

### Metrics Not Appearing

```bash
# Check if metrics endpoint is accessible
curl http://localhost:5055/metrics

# Verify Prometheus targets
# Open: http://localhost:9090/targets
# Should show wikiman-pro target as "UP"
```

### High Cardinality Warnings

If you see high cardinality warnings, check:
- Are you creating unique label values per request?
- Ensure country codes are from fixed set (uk, sg, hk, au, jp)
- Limit status codes to standard HTTP codes

### Alert Rules Not Firing

```bash
# Validate alert rules
promtool check rules prometheus_alerts.yml

# Check alert status in Prometheus
# Open: http://localhost:9090/alerts
```

---

## Files Created

1. `test_metrics_server.py` - Standalone test server for metrics endpoint
2. `prometheus.yml` - Prometheus scraping configuration
3. `prometheus_alerts.yml` - Alert rule definitions
4. `PROMETHEUS_SETUP.md` - This setup guide

---

## Next Steps

1. ✅ Metrics endpoint integrated
2. ✅ Prometheus configuration created
3. ✅ Alert rules defined
4. 🔲 Start Prometheus locally
5. 🔲 Create Grafana dashboards
6. 🔲 Fix webapp import issue
7. 🔲 Deploy to production
8. 🔲 Configure Alertmanager

---

## Support

For issues or questions:
- Check the metrics endpoint directly: `curl http://localhost:5055/metrics`
- View Prometheus targets: http://localhost:9090/targets
- Review Prometheus logs for scraping errors
- Verify handler instrumentation in `countries/{uk,sg,hk,au,jp}/handler.py`
