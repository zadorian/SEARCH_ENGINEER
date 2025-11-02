# FactAssembler Service: Operational Runbook

This document provides a comprehensive guide for operators to run, monitor, and troubleshoot the FactAssembler service and its integration with the Search Engineer application.

## 1. Service Overview

**Purpose:** The FactAssembler service is a microservice responsible for on-demand scraping of web content and performing AI-powered entity extraction and fact assembly. It is consumed by the `fact_assembler_bridge.py` in the main Search Engineer application.

**Architecture:**
- **Web Server:** A Flask application (`web_assembler_simple.py`) that exposes a REST API.
- **Scraping:** Uses a primary service (Firecrawl) with a local Scrapy implementation as a fallback.
- **Job Processing:** Analysis jobs are run as background subprocesses.
- **Data Storage:** Project data, sources, and results are stored on the filesystem in a directory defined by the `FACTASSEMBLER_PROJECTS_DIR` environment variable (defaults to `~/GARSON/entity_projects`).
- **Metrics:** A separate SQLite database (`factassembler_metrics.db`) and a Flask dashboard (`metrics_dashboard.py`) are used for performance monitoring.

---

## 2. Deployment and Configuration

### 2.1. Dependencies

Ensure all Python dependencies are installed:
```bash
pip install -r requirements.txt
pip install flask flask_socketio eventlet scrapy html2text
```

### 2.2. Environment Variables

The service is configured via environment variables, typically stored in a `.env` file in the `FactAssembler` directory.

| Variable                       | Description                                                                 | Default Value                      | Required |
| ------------------------------ | --------------------------------------------------------------------------- | ---------------------------------- | -------- |
| `FACTASSEMBLER_PROJECTS_DIR`   | The root directory to store all project data, sources, and results.         | `~/GARSON/entity_projects`         | No       |
| `FIRECRAWL_API_KEY`            | API key for the Firecrawl scraping service.                                 | `None`                             | Yes      |
| `SECRET_KEY`                   | A secret key for the Flask web server.                                      | `dev-secret-key...`                | Yes (Prod) |

### 2.3. Running the Service

**Standalone:**
To run the main FactAssembler API server:
```bash
cd FactAssembler
python web_assembler_simple.py
```
The service will be available at `http://localhost:8888`.

**Metrics Dashboard:**
To run the performance metrics dashboard:
```bash
cd FactAssembler
python metrics_dashboard.py
```
The dashboard will be available at `http://localhost:9090`.

---

## 3. Monitoring and Health Checks

### 3.1. Service Health Endpoint

A basic health check can be performed by querying the main page of the web server. A `200 OK` response indicates the server is running.

```bash
curl -I http://localhost:8888/
```

### 3.2. Metrics Dashboard

The primary tool for monitoring is the metrics dashboard. Access the summary endpoint to get a snapshot of recent activity:

```bash
curl http://localhost:9090/metrics/summary
```

**Key Metrics to Watch:**
- **`scrape_stats`**:
  - **Success Rate:** Monitor the ratio of successful to failed scrapes for both `firecrawl` and `scrapy`. A high failure rate for Scrapy may indicate that websites are blocking the scraper.
  - **Average Duration:** A sudden increase in the average scrape duration can indicate network latency or issues with target websites.
- **`api_stats`**:
  - **Failure Rate:** Any failures on the API endpoints (e.g., `POST /api/project/create`) should be investigated immediately.
  - **Average Duration:** Monitor for performance degradation in the API.

---

## 4. Troubleshooting Guide

### 4.1. Issue: Integration test fails with `401 Unauthorized` from Firecrawl.

- **Cause:** The `FIRECRAWL_API_KEY` is missing, invalid, or the subscription has expired.
- **Solution:**
  1.  Verify that the `FIRECRAWL_API_KEY` is correctly set in the `.env` file.
  2.  Check the Firecrawl dashboard to ensure the API key is active and the subscription is current.
  3.  The system is designed to fall back to Scrapy, so this is not a critical failure, but it will impact performance and quality.

### 4.2. Issue: Integration test fails with `PermissionError` or `FileNotFoundError`.

- **Cause:** The service is trying to write to a directory that does not exist or for which it does not have permissions. This is often caused by a hardcoded absolute path.
- **Solution:**
  1.  Check the `FACTASSEMBLER_PROJECTS_DIR` environment variable. Ensure it points to a valid, writable directory.
  2.  If the variable is not set, the service defaults to `~/GARSON/entity_projects`. Ensure this directory is writable by the user running the service.
  3.  Examine the traceback to see if any other modules (like `firecrawl_service.py`) have hardcoded paths that need to be corrected.

### 4.3. Issue: Analysis jobs are failing with `Process exited with code 1`.

- **Cause:** The underlying analysis script (e.g., `entity_extraction_realtime_stream.py`) is crashing.
- **Solution:**
  1.  **Locate the Job Log:** The server creates a log file for every job. The path is: `<FACTASSEMBLER_PROJECTS_DIR>/<project_id>/<job_id>_log.txt`.
  2.  **Analyze the Log:** The log file contains the full `stdout` and `stderr` from the failed script, including the traceback. This will pinpoint the exact cause of the error (e.g., a Python exception, missing dependency in the script's environment).

### 4.4. Issue: The Scrapy fallback is failing with "can't pickle" errors.

- **Cause:** The `multiprocessing` library used by the Scrapy runner cannot serialize a function that is defined inside another function.
- **Solution:**
  1.  Ensure that the target function for the `multiprocessing.Process` (e.g., `_spider_process`) is defined at the top level of the Python module (`ScrapeR/local_scraper.py`).
