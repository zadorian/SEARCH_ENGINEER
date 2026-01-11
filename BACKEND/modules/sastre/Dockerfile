# SASTRE AI - Production Docker Image
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app/SASTRE/

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8201/health || exit 1

# Default port
EXPOSE 8201 9090

# Run orchestrator
CMD ["python", "-m", "uvicorn", "SASTRE.orchestrator_service:app", "--host", "0.0.0.0", "--port", "8201"]
