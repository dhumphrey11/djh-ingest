# Orchestrator Service

The orchestrator service coordinates data ingestion across all microservices based on Cloud Scheduler requests.

## Architecture

The orchestrator receives HTTP requests from Google Cloud Scheduler and:

1. **Routes requests** to appropriate handler based on job name
2. **Fetches ticker lists** from Firestore configuration based on job scope
3. **Calls microservices** via HTTP to perform data ingestion
4. **Logs raw API responses** to Firestore for audit trail
5. **Stores processed data** in structured Firestore collections
6. **Returns results** to Cloud Scheduler

## Key Components

### 1. FastAPI Application (`app.py`)
- **Health endpoints**: `/health`, `/status`
- **Job endpoints**: Each Cloud Scheduler job has a dedicated endpoint
- **Manual trigger**: `/manual/trigger-job` for testing
- **CORS enabled**: For development and monitoring tools

### 2. Scheduler Handlers (`scheduler_handlers.py`)
- **Job execution logic**: Maps Cloud Scheduler requests to data operations
- **Service orchestration**: Coordinates calls to all 4 microservices
- **Error handling**: Comprehensive retry logic and error reporting
- **Statistics tracking**: Job success/failure metrics

### 3. Service Client (`clients/service_client.py`)
- **HTTP client**: Makes requests to all microservices
- **Health checking**: Monitors service availability
- **Retry logic**: Exponential backoff for failed requests
- **Connection pooling**: Reuses HTTP connections for efficiency

### 4. Firestore Logger (`firestore_logger.py`)
- **Raw data logging**: Stores all API responses for audit trail
- **Batch operations**: Efficient bulk writes to Firestore
- **Configuration retrieval**: Gets watchlist and active symbols
- **Schema enforcement**: Ensures consistent data structure

## Job Types

### Tiingo Jobs
- **tiingo-daily-prices**: EOD prices for entire watchlist
- **tiingo-daily-prices-indices**: EOD prices for market indices

### Finnhub Jobs
- **finnhub-quote-portfolio**: Intraday quotes for active symbols
- **finnhub-quote-indices**: Intraday quotes for indices
- **finnhub-company-news-universe**: Company news for watchlist
- **finnhub-company-news-portfolio**: Company news for active symbols
- **finnhub-fundamentals-earnings**: Fundamentals and earnings data

### Polygon Jobs
- **polygon-news-universe**: Company news for watchlist
- **polygon-news-portfolio**: Company news for active symbols
- **polygon-news-market**: Market-wide news articles

### AlphaVantage Jobs
- **alpha-vantage-technical-indicators**: Technical indicators for watchlist

## Scopes

Each job operates on a specific scope:

- **ENTIRE_WATCHLIST**: All symbols in the watchlist (~500-1000 tickers)
- **ACTIVE_SYMBOLS**: Currently active portfolio positions (~50-100 tickers)
- **INDICES**: Market indices (SPY, QQQ, IWM, etc.)
- **NONE**: No specific tickers (market-wide data)

## Environment Variables

```bash
# Service URLs (default to localhost for development)
TIINGO_SERVICE_URL=http://tiingo-service:8001
FINNHUB_SERVICE_URL=http://finnhub-service:8002
POLYGON_SERVICE_URL=http://polygon-service:8003
ALPHAVANTAGE_SERVICE_URL=http://alphavantage-service:8004

# Google Cloud
GOOGLE_CLOUD_PROJECT=your-project-id
FIRESTORE_DATABASE=your-database-id

# Development
LOG_LEVEL=INFO
```

## Development

### Local Development
```bash
# Start dependencies (Firestore emulator)
gcloud beta emulators firestore start --host-port=localhost:8080

# Set environment variables
export FIRESTORE_EMULATOR_HOST=localhost:8080
export GOOGLE_CLOUD_PROJECT=your-project

# Install dependencies
pip install -r requirements.txt

# Run the service
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### Docker Development
```bash
# Build image
docker build -t orchestrator-service .

# Run container
docker run -p 8000:8000 \
  -e GOOGLE_CLOUD_PROJECT=your-project \
  -e FIRESTORE_EMULATOR_HOST=host.docker.internal:8080 \
  orchestrator-service
```

## API Endpoints

### Health & Status
```bash
# Health check
curl http://localhost:8000/health

# Detailed status with service health
curl http://localhost:8000/status
```

### Job Execution
```bash
# Manual job trigger (for testing)
curl -X POST http://localhost:8000/manual/trigger-job \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "active_symbols",
    "job": "finnhub-quote-portfolio"
  }'

# Specific job endpoint (used by Cloud Scheduler)
curl -X POST http://localhost:8000/finnhub/quote-portfolio \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "active_symbols",
    "job": "finnhub-quote-portfolio",
    "run_time": "2024-01-01T10:00:00Z"
  }'
```

## Monitoring

The orchestrator provides comprehensive monitoring:

### Handler Statistics
- **jobs_processed**: Total number of jobs executed
- **jobs_successful**: Number of successful jobs
- **jobs_failed**: Number of failed jobs
- **last_job_time**: Timestamp of last job execution

### Service Health
- **Response times**: Latency for each microservice
- **Status checks**: Health status of all dependencies
- **Connection status**: HTTP client pool health

### Logging
- **Structured logging**: JSON formatted logs for Cloud Logging
- **Job tracing**: Request IDs for tracking job execution
- **Error details**: Stack traces and error context
- **Performance metrics**: Execution times and resource usage

## Error Handling

The orchestrator implements robust error handling:

### Service Failures
- **Retry logic**: Exponential backoff for transient failures
- **Circuit breaker**: Prevents cascading failures
- **Graceful degradation**: Continues processing other jobs

### Data Validation
- **Request validation**: Pydantic models for type safety
- **Response validation**: Ensures data integrity
- **Schema enforcement**: Consistent Firestore document structure

### Monitoring Integration
- **Health checks**: Kubernetes/Cloud Run readiness probes
- **Metrics export**: Prometheus/Cloud Monitoring integration
- **Alert conditions**: Failure rate and latency thresholds

## Deployment

The orchestrator is designed for Cloud Run deployment:

### Container Requirements
- **Multi-stage build**: Optimized for production
- **Non-root user**: Security hardening
- **Health checks**: Built-in container health monitoring
- **Resource limits**: Memory and CPU constraints

### Cloud Run Configuration
- **Concurrency**: 100 concurrent requests per instance
- **Timeout**: 15 minutes for long-running jobs
- **Memory**: 2GB for data processing
- **CPU**: 2 vCPU for concurrent operations

### Scaling
- **Auto-scaling**: 0-10 instances based on load
- **Cold start optimization**: Fast startup with pre-loaded connections
- **Resource efficiency**: Shared HTTP client pools