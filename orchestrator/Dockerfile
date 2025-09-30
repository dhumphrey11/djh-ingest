FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy orchestrator code (includes shared modules)
COPY . ./orchestrator/

# Set the working directory to orchestrator
WORKDIR /app/orchestrator

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Set Python path to include /app for shared modules
ENV PYTHONPATH=/app

# Health check - Cloud Run uses PORT env variable
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

# Expose port - use PORT environment variable for Cloud Run
EXPOSE ${PORT:-8080}

# Run the application - use PORT environment variable for Cloud Run
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]