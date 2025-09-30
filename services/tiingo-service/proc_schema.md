# Tiingo Service Data Processing Schema

## Overview

The Tiingo service handles EOD (End of Day) daily price data ingestion from the Tiingo API. This document describes how raw Tiingo responses are normalized and processed for storage in Firestore.

## API Endpoints Used

### Daily Prices Endpoint
- **URL:** `https://api.tiingo.com/tiingo/daily/{ticker}/prices`
- **Parameters:**
  - `token`: API authentication token
  - `startDate`: Start date in YYYY-MM-DD format
  - `endDate`: End date in YYYY-MM-DD format 
  - `format`: Response format (json)

## Raw Response Format

Tiingo returns an array of daily price records for each ticker:

```json
[
  {
    "date": "2024-01-31T00:00:00.000Z",
    "close": 194.17,
    "high": 194.4,
    "low": 191.0,
    "open": 191.5,
    "volume": 65234567,
    "adjClose": 194.17,
    "adjHigh": 194.4,
    "adjLow": 191.0,
    "adjOpen": 191.5,
    "adjVolume": 65234567,
    "divCash": 0.0,
    "splitFactor": 1.0
  }
]
```

## Normalization Process

### 1. Date Standardization
- **Input:** `"2024-01-31T00:00:00.000Z"`
- **Output:** `"2024-01-31"`
- **Process:** Extract date portion, discard time component

### 2. Field Mapping
Raw Tiingo fields are mapped to standardized schema:

| Tiingo Field | Normalized Field | Type | Description |
|--------------|------------------|------|-------------|
| `date` | `date` | string | Trading date (YYYY-MM-DD) |
| `open` | `open` | float | Opening price |
| `high` | `high` | float | Highest price |
| `low` | `low` | float | Lowest price |
| `close` | `close` | float | Closing price |
| `volume` | `volume` | integer | Trading volume |
| `adjOpen` | `adj_open` | float | Adjusted opening price |
| `adjHigh` | `adj_high` | float | Adjusted highest price |
| `adjLow` | `adj_low` | float | Adjusted lowest price |
| `adjClose` | `adj_close` | float | Adjusted closing price |
| `adjVolume` | `adj_volume` | integer | Adjusted volume |
| `divCash` | `div_cash` | float | Dividend cash amount |
| `splitFactor` | `split_factor` | float | Stock split factor |

### 3. Data Enrichment
Additional fields added during processing:

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `ticker` | string | Request parameter | Stock symbol |
| `source` | string | Constant | Always "tiingo" |
| `ingested_at` | string | System | ISO timestamp when processed |

### 4. Type Conversion and Validation

```python
# Price validation
if price < 0:
    logger.warning(f"Negative price detected for {ticker}: {price}")
    
# Volume validation  
if volume < 0:
    volume = 0  # Set to 0 for negative volumes

# Split factor validation
if split_factor <= 0:
    split_factor = 1.0  # Default to no split
```

## Processed Output Schema

Final normalized record stored in Firestore:

```json
{
  "ticker": "AAPL",
  "date": "2024-01-31",
  "open": 191.5,
  "high": 194.4,
  "low": 191.0,
  "close": 194.17,
  "volume": 65234567,
  "adj_open": 191.5,
  "adj_high": 194.4,
  "adj_low": 191.0,
  "adj_close": 194.17,
  "adj_volume": 65234567,
  "div_cash": 0.0,
  "split_factor": 1.0,
  "source": "tiingo",
  "ingested_at": "2024-01-31T22:15:30.123456Z"
}
```

## Error Handling

### API Errors
- **404 Not Found:** Ticker not supported or no data available
- **429 Rate Limited:** Too many requests, implement backoff
- **500 Server Error:** Tiingo API issue, retry with exponential backoff

### Data Quality Issues
- **Missing required fields:** Skip record, log warning
- **Invalid data types:** Attempt conversion, default to 0/null if failed
- **Negative prices:** Log warning but preserve data
- **Future dates:** Skip record, likely data error

## Rate Limiting

### Tiingo API Limits
- **Free Tier:** 1,000 requests per hour
- **Paid Tier:** Higher limits based on plan
- **Recommended:** 50 requests per minute maximum

### Implementation
```python
# Check rate limit before each request
def check_rate_limit(self):
    recent_requests = len([
        ts for ts in self.request_timestamps 
        if ts > datetime.utcnow() - timedelta(minutes=1)
    ])
    
    if recent_requests >= self.rate_limit_per_minute:
        raise RateLimitError("Per-minute rate limit exceeded")
```

## Firestore Storage

### Collection Path
- **Daily Prices:** `prices_daily/{ticker}_{date}`
- **Document ID:** `AAPL_2024-01-31`

### Composite Indexes Required
- `ticker` (ascending) + `date` (descending)
- `date` (descending) - for time-based queries
- `source` (ascending) + `ingested_at` (descending) - for monitoring

### Sample Query
```python
# Get last 30 days of AAPL prices
query = db.collection('prices_daily') \
    .where('ticker', '==', 'AAPL') \
    .order_by('date', direction='DESC') \
    .limit(30)
```

## Data Quality Checks

### Validation Rules
1. **Price Consistency:** `high >= low`, `high >= open/close`, `low <= open/close`
2. **Date Sequence:** No gaps in trading days (excluding weekends/holidays)
3. **Volume Sanity:** Volume should be > 0 for actively traded stocks
4. **Adjustment Factors:** Split factors should be positive, div_cash >= 0

### Quality Metrics
- **Completeness:** Percentage of expected records received
- **Timeliness:** Delay between market close and data availability
- **Accuracy:** Spot checks against other data sources

## Monitoring and Alerting

### Key Metrics
- **API Response Time:** Track p95, p99 latencies
- **Error Rate:** 4xx/5xx responses as percentage
- **Data Freshness:** Time since last successful ingestion
- **Rate Limit Usage:** Requests per hour vs. limit

### Alerts
- **High Error Rate:** > 5% errors in last hour
- **Stale Data:** No successful ingestion in last 2 hours during market days
- **Rate Limit Approach:** > 90% of hourly rate limit used

## Testing Strategy

### Unit Tests
- Mock Tiingo API responses
- Test normalization logic
- Validate error handling

### Integration Tests  
- Test with Tiingo API sandbox
- Verify Firestore writes
- End-to-end pipeline test

### Data Quality Tests
- Compare with known good data
- Check for data anomalies
- Validate business rules