# Multi-stage build for smaller production image
FROM python:3.11-slim as builder

WORKDIR /build

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY services/alphavantage-service/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser && useradd -r -g appuser appuser

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy shared modules
COPY shared/ /app/shared/

# Copy service code
COPY services/alphavantage-service/app.py .
COPY services/alphavantage-service/alphavantage_client.py .

# Create non-root user and set permissions
RUN chown -R appuser:appuser /app /home/appuser/.local
USER appuser

# Make sure scripts in .local are usable
ENV PATH=/home/appuser/.local/bin:$PATH

# Set Python path
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:$PORT/health || exit 1

# Set default port (Cloud Run will override)
ENV PORT=8080

# Start the application
CMD exec uvicorn app:app --host 0.0.0.0 --port $PORT --workers 1