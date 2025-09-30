# Stock Analysis Ingestion & Orchestration Pipeline

[![Deploy Stock Analysis Pipeline](https://github.com/your-username/djh-ingest/actions/workflows/deploy.yml/badge.svg)](https://github.com/your-username/djh-ingest/actions/workflows/deploy.yml)

A production-ready microservices architecture for ingesting financial data from multiple providers (Tiingo, Finnhub, Polygon, AlphaVantage) with automated orchestration via Google Cloud Scheduler.

## 🏗️ Architecture

The pipeline consists of 5 containerized services deployed to Google Cloud Run:

- **4 Data Provider Services**: Independent FastAPI applications for each financial data provider
- **1 Orchestrator Service**: Coordinates data ingestion based on Cloud Scheduler requests
- **Firestore Database**: Stores raw API responses and processed data
- **Cloud Scheduler**: Triggers jobs at different frequencies throughout trading hours

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Cloud Scheduler│    │   Orchestrator   │    │   Microservices │
│                 │    │     Service      │    │                 │
│ • tiingo-daily- │───▶│                  │───▶│ • Tiingo        │
│   prices        │    │ • Routes requests│    │ • Finnhub       │
│ • finnhub-quotes│    │ • Fetches tickers│    │ • Polygon       │
│ • polygon-news  │    │ • Logs responses │    │ • AlphaVantage  │
│ • alpha-tech-   │    │ • Stores data    │    │                 │
│   indicators    │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │   Firestore DB   │
                       │                  │
                       │ • Raw API logs   │
                       │ • Processed data │
                       │ • Configuration  │
                       │ • Watchlists     │
                       └──────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Google Cloud Project with billing enabled
- gcloud CLI installed and authenticated
- Docker installed (for local development)

### 1. Clone and Setup

```bash
git clone https://github.com/your-username/djh-ingest.git
cd djh-ingest

# Set your Google Cloud project
export GOOGLE_CLOUD_PROJECT="djh-app-3bdc2"
```

### 2. Configure API Keys

Store your API keys in Google Secret Manager:

```bash
# Create secrets for each data provider
echo "ddc257a665ff43d87b07ece1e03e63de789abd5f" | gcloud secrets create TIINGO_API_KEY --data-file=-
echo "d3bnevpr01qqg7bvbmggd3bnevpr01qqg7bvbmh0" | gcloud secrets create FINNHUB_API_KEY --data-file=-
echo "5RZwJ4YGHf6sHoJrQeCSGcZ2G_tGukPz" | gcloud secrets create POLYGON_API_KEY --data-file=-
echo "HUW8OAWG0BZ7D55D" | gcloud secrets create ALPHAVANTAGE_API_KEY --data-file=-
```

### 3. Deploy to Cloud Run

```bash
# Deploy all services
./infra/deploy_all.sh

# Create Cloud Scheduler jobs
export ORCHESTRATOR_URL="https://your-orchestrator-url"
./infra/create_schedulers.sh
```

### 4. Initialize Firestore

Create the required collections and initial configuration:

```bash
# Set up Firestore database (follow shared/firestore_schema.md)
gcloud firestore databases create --region=us-central1
```

## 📊 Data Sources & Frequency

### Tiingo
- **Daily Prices**: Entire watchlist - Daily at 6:00 PM ET
- **Index Prices**: Market indices - Daily at 6:05 PM ET

### Finnhub
- **Intraday Quotes**: Portfolio/indices - Every 5 minutes during market hours
- **Company News**: Universe (every 2 hours), Portfolio (hourly) during business hours
- **Fundamentals & Earnings**: Daily at 7:00 AM ET

### Polygon
- **Company News**: Universe (every 3 hours), Portfolio (hourly)
- **Market News**: Every 30 minutes during business hours

### AlphaVantage
- **Technical Indicators**: Daily at 5:00 PM ET (7 indicators: SMA, EMA, RSI, MACD, BB, Stoch, ADX)

## 🏃‍♂️ Local Development

### Run Individual Services

```bash
# Terminal 1: Start Firestore emulator
gcloud beta emulators firestore start --host-port=localhost:8080

# Terminal 2: Set environment variables
export FIRESTORE_EMULATOR_HOST=localhost:8080
export GOOGLE_CLOUD_PROJECT=test-project

# Terminal 3: Run a service (example: Tiingo)
cd services/tiingo-service
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8001 --reload
```

### Run with Docker Compose

```bash
# Build all services
docker-compose build

# Start services
docker-compose up -d

# Check health
curl http://localhost:8000/health  # Orchestrator
curl http://localhost:8001/health  # Tiingo
curl http://localhost:8002/health  # Finnhub
curl http://localhost:8003/health  # Polygon
curl http://localhost:8004/health  # AlphaVantage
```

## 🔧 Configuration

### Environment Variables

Each service uses these common environment variables:

```bash
# Google Cloud
GOOGLE_CLOUD_PROJECT=your-project-id
FIRESTORE_DATABASE=your-database-id

# Service URLs (for orchestrator)
TIINGO_SERVICE_URL=https://tiingo-service-url
FINNHUB_SERVICE_URL=https://finnhub-service-url
POLYGON_SERVICE_URL=https://polygon-service-url
ALPHAVANTAGE_SERVICE_URL=https://alphavantage-service-url

# Development
LOG_LEVEL=INFO
```

### Watchlist Configuration

Configure your watchlist in Firestore:

```javascript
// Collection: config/watchlist
{
  "symbols": ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", ...],
  "active_symbols": ["AAPL", "GOOGL", "MSFT"],
  "indices": ["SPY", "QQQ", "IWM", "DIA"],
  "updated_at": "2024-01-01T00:00:00Z"
}
```

## 🛠️ Service Details

### Tiingo Service (`services/tiingo-service/`)
- **Purpose**: End-of-day daily prices for stocks and indices
- **Endpoints**: `/daily-prices`
- **Rate Limit**: 1000 requests/hour
- **Data**: OHLCV prices with volume and dividend adjustments

### Finnhub Service (`services/finnhub-service/`)
- **Purpose**: Real-time quotes, news, fundamentals, earnings, insider transactions, analyst ratings
- **Endpoints**: `/quote`, `/company-news`, `/fundamentals`, `/earnings`, `/insider-transactions`, `/analyst-ratings`
- **Rate Limit**: 60 requests/minute (free tier)
- **Data**: Most comprehensive dataset including real-time market data

### Polygon Service (`services/polygon-service/`)
- **Purpose**: Company and market news with advanced search capabilities
- **Endpoints**: `/company-news`, `/market-news`
- **Rate Limit**: 5 requests/minute (free tier)
- **Data**: High-quality news articles with sentiment and trending ticker detection

### AlphaVantage Service (`services/alphavantage-service/`)
- **Purpose**: Technical indicators with sophisticated rate limiting
- **Endpoints**: `/technical-indicators`
- **Rate Limit**: 25 requests/day (free tier) - Requires careful throttling
- **Data**: 7 key technical indicators with configurable parameters

### Orchestrator Service (`orchestrator/`)
- **Purpose**: Coordinates all services based on Cloud Scheduler requests
- **Features**: Job routing, Firestore logging, service health monitoring, manual triggers
- **Monitoring**: Comprehensive job statistics and service health checks

## 📈 Monitoring & Observability

### Health Checks

All services expose health endpoints:

```bash
# Check individual service health
curl https://tiingo-service-url/health

# Check orchestrator status (includes all service health)
curl https://orchestrator-url/status
```

### Logging

Structured logging is available in Google Cloud Logging:

- **Request/Response logs**: All API calls with timing and parameters
- **Error logs**: Detailed error information with stack traces
- **Job execution logs**: Cloud Scheduler job results and statistics

### Metrics

Key metrics tracked:

- **API call success/failure rates**
- **Response times and latency**
- **Rate limit utilization**
- **Data ingestion volumes**
- **Job execution statistics**

## 🔐 Security

### Authentication

- **Service-to-Service**: Uses Google Cloud IAM with least privilege
- **API Keys**: Stored in Google Secret Manager
- **External Access**: All services require authentication (no public endpoints)

### Rate Limiting

Each service implements provider-specific rate limiting:

- **Exponential backoff** with jitter for retries
- **Circuit breaker** pattern for cascade failure prevention
- **Adaptive throttling** for AlphaVantage's strict limits

### Data Privacy

- **Raw API responses** logged for audit trail but not exposed externally
- **PII handling**: No personal information stored
- **Encryption**: All data encrypted in transit and at rest

## 🚀 Deployment

### Automated Deployment (Recommended)

The GitHub Actions workflow automatically:

1. **Tests** all code changes
2. **Builds** Docker images
3. **Deploys** to Cloud Run
4. **Configures** service-to-service IAM
5. **Runs** health checks
6. **Creates** deployment records

### Manual Deployment

```bash
# Build and deploy all services
./infra/deploy_all.sh

# Or deploy individual services
gcloud run deploy tiingo-service \
  --image gcr.io/PROJECT_ID/tiingo-service:latest \
  --region us-central1
```

### Infrastructure as Code

Key infrastructure components:

- **Cloud Run services** with appropriate CPU/memory/scaling settings
- **Cloud Scheduler jobs** with proper timing and payload configuration  
- **IAM bindings** for secure service-to-service communication
- **Firestore database** with security rules and indexes

## 🔍 Troubleshooting

### Common Issues

#### Service Health Check Failures

```bash
# Check service logs
gcloud logs read --limit=50 --service=tiingo-service

# Check resource utilization
gcloud run services describe tiingo-service --region=us-central1
```

#### Rate Limit Errors

```bash
# Check current rate limit utilization in logs
gcloud logs read --filter="rate limit" --limit=20

# Adjust rate limiting parameters in service code
```

#### Authentication Errors

```bash
# Verify API keys in Secret Manager
gcloud secrets versions list TIINGO_API_KEY

# Check service account permissions
gcloud projects get-iam-policy $GOOGLE_CLOUD_PROJECT
```

### Debug Mode

Enable debug logging:

```bash
gcloud run services update SERVICE_NAME \
  --set-env-vars="LOG_LEVEL=DEBUG"
```

## 📚 API Documentation

### Orchestrator Endpoints

- `GET /health` - Health check
- `GET /status` - Detailed status with service health
- `POST /tiingo/daily-prices` - Trigger Tiingo daily prices job
- `POST /finnhub/quote-portfolio` - Trigger Finnhub portfolio quotes
- `POST /polygon/news-market` - Trigger Polygon market news
- `POST /manual/trigger-job` - Manual job trigger for testing

### Service Request Format

All scheduler requests follow this format:

```json
{
  "scope": "entire_watchlist|active_symbols|indices|none",
  "job": "job-name",
  "run_time": "2024-01-01T10:00:00Z",
  "tickers": ["AAPL", "GOOGL"] // Optional override
}
```

### Service Response Format

```json
{
  "status": "ok|error",
  "job": "job-name",
  "message": "Human readable message",
  "data": {
    "tickers_processed": 100,
    "records_stored": 500,
    "duration_ms": 2500
  },
  "timestamp": "2024-01-01T10:00:00Z"
}
```

## 🤝 Contributing

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Development Guidelines

- **Follow** existing code style and patterns
- **Add** comprehensive tests for new functionality
- **Update** documentation for any API changes
- **Use** type hints and docstrings
- **Ensure** all services pass health checks

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙋‍♂️ Support

- **Documentation**: Check service-specific READMEs in each service directory
- **Issues**: Create a GitHub issue with detailed reproduction steps
- **Discussions**: Use GitHub Discussions for questions and feature requests

## Project Structure

```
├── README.md
├── .github/workflows/
│   └── deploy.yml
├── infra/
│   ├── create_schedulers.sh
│   └── deploy_all.sh
├── services/
│   ├── tiingo-service/
│   ├── finnhub-service/
│   ├── polygon-service/
│   └── alphavantage-service/
├── orchestrator/
├── shared/
│   ├── models.py
│   ├── utils/
│   ├── firestore_schema.md
│   └── firestore_rules.rules
└── test_client.py
```

## Quick Start

### Prerequisites
- Python 3.9+
- Docker
- gcloud CLI configured
- GCP project with APIs enabled:
  - Cloud Run API
  - Cloud Scheduler API
  - Cloud Firestore API
  - Cloud Build API
  - Secret Manager API

### Local Development

1. **Clone and setup environment**:
```bash
git clone <repo-url>
cd djh-ingest
cp .env.example .env
# Edit .env with your API keys
```

2. **Install dependencies**:
```bash
# For each service
cd services/tiingo-service && pip install -r requirements.txt
cd ../finnhub-service && pip install -r requirements.txt
cd ../polygon-service && pip install -r requirements.txt
cd ../alphavantage-service && pip install -r requirements.txt
cd ../../orchestrator && pip install -r requirements.txt
```

3. **Run services locally**:
```bash
# Terminal 1 - Tiingo Service
cd services/tiingo-service
uvicorn app:app --reload --port 8001

# Terminal 2 - Finnhub Service
cd services/finnhub-service
uvicorn app:app --reload --port 8002

# Terminal 3 - Polygon Service
cd services/polygon-service
uvicorn app:app --reload --port 8003

# Terminal 4 - AlphaVantage Service
cd services/alphavantage-service
uvicorn app:app --reload --port 8004

# Terminal 5 - Orchestrator
cd orchestrator
uvicorn app:app --reload --port 8000
```

4. **Test the system**:
```bash
python test_client.py
```

### Environment Variables (.env)

```bash
# Required for local development
GCP_PROJECT=your-gcp-project-id
FIRESTORE_EMULATOR_HOST=localhost:8080  # Optional for local testing
TIINGO_API_KEY=your-tiingo-key
FINNHUB_API_KEY=your-finnhub-key
POLYGON_API_KEY=your-polygon-key
ALPHAVANTAGE_API_KEY=your-alphavantage-key

# Service URLs (for orchestrator to call services)
TIINGO_SERVICE_URL=http://localhost:8001
FINNHUB_SERVICE_URL=http://localhost:8002
POLYGON_SERVICE_URL=http://localhost:8003
ALPHAVANTAGE_SERVICE_URL=http://localhost:8004
```

## GCP Deployment

### 1. Setup Service Accounts

```bash
# Set your project
export GCP_PROJECT="your-project-id"
gcloud config set project $GCP_PROJECT

# Create service accounts
gcloud iam service-accounts create ingest-sa \
    --display-name="Data Ingestion Service Account"

gcloud iam service-accounts create scheduler-invoker \
    --display-name="Cloud Scheduler Invoker"

# Grant permissions
gcloud projects add-iam-policy-binding $GCP_PROJECT \
    --member="serviceAccount:ingest-sa@$GCP_PROJECT.iam.gserviceaccount.com" \
    --role="roles/datastore.user"

gcloud projects add-iam-policy-binding $GCP_PROJECT \
    --member="serviceAccount:scheduler-invoker@$GCP_PROJECT.iam.gserviceaccount.com" \
    --role="roles/run.invoker"
```

### 2. Store API Keys in Secret Manager

```bash
echo -n "your-tiingo-key" | gcloud secrets create tiingo-api-key --data-file=-
echo -n "your-finnhub-key" | gcloud secrets create finnhub-api-key --data-file=-
echo -n "your-polygon-key" | gcloud secrets create polygon-api-key --data-file=-
echo -n "your-alphavantage-key" | gcloud secrets create alphavantage-api-key --data-file=-

# Grant access to service account
for secret in tiingo-api-key finnhub-api-key polygon-api-key alphavantage-api-key; do
    gcloud secrets add-iam-policy-binding $secret \
        --member="serviceAccount:ingest-sa@$GCP_PROJECT.iam.gserviceaccount.com" \
        --role="roles/secretmanager.secretAccessor"
done
```

### 3. Deploy Services

```bash
chmod +x infra/deploy_all.sh
./infra/deploy_all.sh
```

### 4. Create Scheduler Jobs

```bash
chmod +x infra/create_schedulers.sh
./infra/create_schedulers.sh
```

## API Endpoints

### Orchestrator Endpoints (Cloud Scheduler targets)

- `POST /ingest/tiingo/daily-prices` - Daily EOD prices for entire watchlist
- `POST /ingest/tiingo/daily-prices/indices` - Daily EOD prices for indices
- `POST /ingest/finnhub/quote/portfolio` - Intraday quotes for active holdings
- `POST /ingest/finnhub/quote/indices` - Intraday quotes for indices
- `POST /ingest/finnhub/company-news/universe` - Company news for entire watchlist
- `POST /ingest/finnhub/company-news/portfolio` - Company news for active holdings
- `POST /ingest/finnhub/fundamentals-earnings` - Fundamentals and earnings
- `POST /ingest/polygon/news/universe` - News for entire watchlist
- `POST /ingest/polygon/news/portfolio` - News for active holdings
- `POST /ingest/polygon/news/market` - Market-wide news
- `POST /ingest/alphavantage/technical-indicators` - Technical indicators

### Frontend API Endpoints

- `GET /signals/latest?ticker=AAPL` - Latest technical indicators and news sentiment

## Firestore Collections

### Raw Data
- `raw_ingestion_logs/{source}/{api_name}/{YYYY-MM-DD}/{uuid}` - All raw API responses

### Processed Data
- `prices_daily/{ticker}_{date}` - Daily OHLCV data
- `prices_intraday/{ticker}_{timestamp}` - Intraday quotes
- `fundamentals/{ticker}_{report_date}` - Financial fundamentals
- `technical_indicators/{ticker}_{indicator}_{date}` - Technical analysis
- `news_articles/{ticker?}_{article_id}` - Company and market news
- `insider_transactions/{ticker}_{tx_id}` - Insider trading data
- `earnings_calendar/{ticker}_{earnings_date}` - Earnings calendar
- `analyst_ratings/{ticker}_{date}` - Analyst recommendations

### Configuration Collections
- `react_universeSymbols/` - Complete watchlist of symbols to track
- `react_activeSymbols/` - Currently held positions requiring frequent updates

## Monitoring & Logging

All services emit structured logs to Cloud Logging with:
- `job`: Scheduler job name
- `source`: Data provider (tiingo, finnhub, etc.)
- `api`: Specific API endpoint
- `tickers_count`: Number of symbols processed
- `duration_ms`: Request duration
- `status`: Success/failure status
- `error`: Error details if applicable

View logs in GCP Console:
```
gcloud logging read 'resource.type="cloud_run_revision" AND labels."service-name"="orchestrator"'
```

## Security

- All API keys stored in Secret Manager
- Firestore security rules restrict access:
  - Read: Authenticated users only
  - Write: Service accounts only
  - Raw logs: Admin access only
- OIDC authentication for Cloud Scheduler → Cloud Run
- No secrets in code or environment files

## CI/CD

GitHub Actions workflow automatically:
1. Builds Docker images for all services
2. Deploys to Cloud Run
3. Updates environment variables

Required GitHub Secrets:
- `GCP_PROJECT`: Your GCP project ID
- `GCP_REGION`: Deployment region (e.g., us-central1)
- `GCP_SA_KEY`: Service account JSON key for deployments

## Troubleshooting

### Common Issues

1. **Authentication errors**: Verify service account permissions and OIDC configuration
2. **Rate limiting**: Check API quotas and adjust scheduler frequency
3. **Firestore permissions**: Ensure service accounts have `roles/datastore.user`
4. **Memory limits**: Adjust Cloud Run memory allocation in deployment scripts

### Testing Scheduler Jobs

```bash
# Test individual jobs
gcloud scheduler jobs run tiingo-daily-prices --project=$GCP_PROJECT
gcloud scheduler jobs run finnhub-quote-portfolio --project=$GCP_PROJECT
```

### Local Firestore Emulator

```bash
# Start emulator
gcloud emulators firestore start --host-port=localhost:8080

# Set environment variable
export FIRESTORE_EMULATOR_HOST=localhost:8080
```

## Contributing

1. Follow the existing service structure for new data sources
2. Add comprehensive error handling and logging
3. Include unit tests for client functions
4. Update documentation for new endpoints
5. Test locally before deploying

## License

MIT License - see LICENSE file for details.