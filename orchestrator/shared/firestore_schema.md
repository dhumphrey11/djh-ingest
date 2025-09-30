# Firestore Schema Documentation

This document describes the complete Firestore schema for the stock analysis data ingestion pipeline.

## Collections Overview

### Raw Data Collections
- `raw_ingestion_logs/` - All raw API responses for audit and debugging
- `react_universeSymbols/` - Complete watchlist configuration
- `react_activeSymbols/` - Currently held positions

### Processed Data Collections
- `prices_daily/` - Daily OHLCV data
- `prices_intraday/` - Real-time quotes
- `fundamentals/` - Company financial data
- `technical_indicators/` - Technical analysis indicators
- `news_articles/` - Company and market news
- `insider_transactions/` - Insider trading data
- `earnings_calendar/` - Earnings announcements
- `analyst_ratings/` - Analyst recommendations
- `market_indices/` - Market index data
- `economic_indicators/` - Economic data

---

## Raw Data Collections

### raw_ingestion_logs/{source}/{api_name}/{YYYY-MM-DD}/{uuid}

Stores all raw API responses for audit, debugging, and potential reprocessing.

**Document Structure:**
```json
{
  "request": {
    "url": "https://api.tiingo.com/tiingo/daily/AAPL/prices",
    "params": {
      "token": "[REDACTED]",
      "startDate": "2024-01-01",
      "endDate": "2024-01-31"
    },
    "headers": {
      "User-Agent": "djh-ingest/1.0",
      "Accept": "application/json"
    },
    "scope": "entire_watchlist",
    "timestamp": "2024-01-31T15:30:00Z"
  },
  "response": {
    "data": [...], // Raw API response JSON
    "status_code": 200,
    "latency_ms": 245,
    "error_flag": false
  },
  "metadata": {
    "job_id": "tiingo-daily-prices-20240131",
    "orchestrator_instance": "orchestrator-abc123",
    "tickers_requested": ["AAPL", "MSFT", "GOOGL"],
    "tickers_successful": ["AAPL", "MSFT", "GOOGL"],
    "tickers_failed": []
  }
}
```

**Path Examples:**
- `raw_ingestion_logs/tiingo/daily-prices/2024-01-31/abc123-def456-ghi789`
- `raw_ingestion_logs/finnhub/quote/2024-01-31/xyz789-uvw456-rst123`
- `raw_ingestion_logs/polygon/news/2024-01-31/mno345-pqr678-stu901`

### react_universeSymbols/

Configuration collection defining the complete watchlist of symbols to track.

**Document ID:** `config` (single document)
**Document Structure:**
```json
{
  "symbols": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "sector": "Technology",
      "market_cap_category": "large",
      "added_date": "2024-01-01T00:00:00Z",
      "active": true,
      "tags": ["faang", "consumer_electronics"]
    },
    {
      "ticker": "MSFT",
      "name": "Microsoft Corporation", 
      "sector": "Technology",
      "market_cap_category": "large",
      "added_date": "2024-01-01T00:00:00Z",
      "active": true,
      "tags": ["faang", "cloud", "enterprise"]
    }
  ],
  "indices": [
    {
      "symbol": "SPY",
      "name": "SPDR S&P 500 ETF",
      "type": "etf",
      "benchmark": true
    },
    {
      "symbol": "QQQ", 
      "name": "Invesco QQQ ETF",
      "type": "etf",
      "benchmark": true
    }
  ],
  "last_updated": "2024-01-31T15:30:00Z",
  "version": 1
}
```

### react_activeSymbols/

Currently held positions requiring frequent intraday updates.

**Document ID:** `positions` (single document)
**Document Structure:**
```json
{
  "positions": [
    {
      "ticker": "AAPL",
      "quantity": 100,
      "avg_cost": 175.50,
      "position_date": "2024-01-15T00:00:00Z",
      "position_value": 17550.00,
      "priority": "high",
      "alerts_enabled": true
    }
  ],
  "cash_position": 50000.00,
  "total_portfolio_value": 125000.00,
  "last_updated": "2024-01-31T15:30:00Z",
  "update_frequency": "15min_during_market_hours"
}
```

---

## Processed Data Collections

### prices_daily/{ticker}_{date}

Daily OHLCV price data from Tiingo.

**Document ID Format:** `AAPL_2024-01-31`
**Document Structure:**
```json
{
  "ticker": "AAPL",
  "date": "2024-01-31",
  "open": 191.50,
  "high": 194.40,
  "low": 191.00,
  "close": 194.17,
  "volume": 65234567,
  "adj_open": 191.50,
  "adj_high": 194.40,
  "adj_low": 191.00,
  "adj_close": 194.17,
  "adj_volume": 65234567,
  "div_cash": 0.0,
  "split_factor": 1.0,
  "source": "tiingo",
  "ingested_at": "2024-01-31T22:00:00Z"
}
```

**Indexes:**
- `ticker` (ascending)
- `date` (descending)
- `ticker, date` (composite)

### prices_intraday/{ticker}_{timestamp}

Real-time quote data from Finnhub.

**Document ID Format:** `AAPL_2024-01-31T15:30:00Z`
**Document Structure:**
```json
{
  "ticker": "AAPL",
  "current_price": 194.25,
  "change": 2.75,
  "percent_change": 1.44,
  "high": 194.40,
  "low": 191.00,
  "open": 191.50,
  "previous_close": 191.50,
  "timestamp": 1706712600,
  "volume": 45234567,
  "bid": 194.24,
  "ask": 194.26,
  "source": "finnhub",
  "ingested_at": "2024-01-31T15:30:15Z"
}
```

**Indexes:**
- `ticker` (ascending)
- `timestamp` (descending)
- `ticker, timestamp` (composite)

### fundamentals/{ticker}_{report_date}

Company fundamental data from Finnhub.

**Document ID Format:** `AAPL_2024-Q4`
**Document Structure:**
```json
{
  "ticker": "AAPL",
  "report_date": "2024-Q4",
  "period_end_date": "2024-09-30",
  "fiscal_year": 2024,
  "fiscal_quarter": 4,
  "market_cap": 3000000000000,
  "shares_outstanding": 15500000000,
  "pe_ratio": 29.5,
  "pb_ratio": 45.2,
  "roe": 0.175,
  "roa": 0.12,
  "debt_to_equity": 1.95,
  "current_ratio": 0.95,
  "revenue_ttm": 385000000000,
  "net_income_ttm": 100000000000,
  "gross_margin": 0.44,
  "operating_margin": 0.28,
  "net_margin": 0.26,
  "source": "finnhub",
  "ingested_at": "2024-01-31T15:30:00Z"
}
```

### technical_indicators/{ticker}_{indicator}_{date}

Technical analysis indicators from AlphaVantage.

**Document ID Format:** `AAPL_RSI_2024-01-31`
**Document Structure:**
```json
{
  "ticker": "AAPL",
  "indicator": "RSI",
  "date": "2024-01-31",
  "value": 67.5,
  "parameters": {
    "time_period": 14,
    "series_type": "close"
  },
  "signal": "neutral", // oversold, neutral, overbought
  "source": "alphavantage",
  "ingested_at": "2024-01-31T15:30:00Z"
}
```

**For multi-value indicators (MACD, Bollinger Bands):**
```json
{
  "ticker": "AAPL",
  "indicator": "MACD",
  "date": "2024-01-31",
  "value": {
    "macd": 2.45,
    "signal": 2.12,
    "histogram": 0.33
  },
  "parameters": {
    "fast_period": 12,
    "slow_period": 26,
    "signal_period": 9
  },
  "signal": "bullish_crossover",
  "source": "alphavantage",
  "ingested_at": "2024-01-31T15:30:00Z"
}
```

### news_articles/{ticker?}_{article_id}

News articles from Finnhub and Polygon.

**Document ID Format:** 
- Company news: `AAPL_finnhub_12345678`
- Market news: `market_polygon_87654321`

**Document Structure:**
```json
{
  "article_id": "finnhub_12345678",
  "ticker": "AAPL", // Optional - null for market news
  "headline": "Apple Reports Record Q4 Earnings",
  "summary": "Apple Inc. reported record fourth-quarter earnings...",
  "url": "https://example.com/article/12345",
  "source": "Reuters",
  "category": "earnings",
  "published_at": "2024-01-31T14:30:00Z",
  "sentiment_score": 0.75, // -1 to 1, calculated by ingestion pipeline
  "sentiment_label": "positive", // negative, neutral, positive
  "keywords": ["earnings", "revenue", "iphone", "services"],
  "related_tickers": ["AAPL"],
  "image_url": "https://example.com/image.jpg",
  "provider": "finnhub", // finnhub, polygon
  "ingested_at": "2024-01-31T15:30:00Z"
}
```

**Indexes:**
- `ticker` (ascending)
- `published_at` (descending)
- `ticker, published_at` (composite)
- `category, published_at` (composite)

### insider_transactions/{ticker}_{tx_id}

Insider trading data from Finnhub.

**Document ID Format:** `AAPL_tx_20240131_001`
**Document Structure:**
```json
{
  "ticker": "AAPL",
  "transaction_id": "tx_20240131_001",
  "person_name": "Timothy D. Cook",
  "person_title": "Chief Executive Officer",
  "transaction_type": "sale", // purchase, sale, option_exercise, gift
  "shares": 100000,
  "transaction_price": 194.25,
  "transaction_value": 19425000.00,
  "shares_owned_after": 3300000,
  "filing_date": "2024-01-31",
  "transaction_date": "2024-01-29",
  "form_type": "4",
  "source": "finnhub",
  "ingested_at": "2024-01-31T15:30:00Z"
}
```

### earnings_calendar/{ticker}_{earnings_date}

Earnings calendar data from Finnhub.

**Document ID Format:** `AAPL_2024-05-02`
**Document Structure:**
```json
{
  "ticker": "AAPL",
  "earnings_date": "2024-05-02",
  "quarter": 2,
  "fiscal_year": 2024,
  "report_time": "after_market", // before_market, during_market, after_market
  "eps_estimate": 1.55,
  "eps_actual": null, // Filled after announcement
  "revenue_estimate": 90500000000,
  "revenue_actual": null,
  "surprise_percent": null,
  "analyst_count": 32,
  "last_updated": "2024-01-31T15:30:00Z",
  "source": "finnhub",
  "ingested_at": "2024-01-31T15:30:00Z"
}
```

### analyst_ratings/{ticker}_{date}

Analyst recommendations from Finnhub.

**Document ID Format:** `AAPL_2024-01-31`
**Document Structure:**
```json
{
  "ticker": "AAPL",
  "date": "2024-01-31",
  "period": "2024-01", // Monthly aggregation
  "strong_buy": 15,
  "buy": 12,
  "hold": 8,
  "sell": 2,
  "strong_sell": 0,
  "total_analysts": 37,
  "average_rating": 4.08, // 1-5 scale
  "rating_change": 0.15, // Change from previous month
  "consensus": "buy", // strong_sell, sell, hold, buy, strong_buy
  "price_target_avg": 205.50,
  "price_target_high": 225.00,
  "price_target_low": 185.00,
  "source": "finnhub",
  "ingested_at": "2024-01-31T15:30:00Z"
}
```

### market_indices/{symbol}_{date}

Market index and ETF data.

**Document ID Format:** `SPY_2024-01-31`
**Document Structure:**
```json
{
  "symbol": "SPY",
  "name": "SPDR S&P 500 ETF",
  "date": "2024-01-31",
  "open": 485.20,
  "high": 487.60,
  "low": 484.10,
  "close": 487.45,
  "volume": 45234567,
  "change": 2.25,
  "change_percent": 0.46,
  "dividend_yield": 0.0129,
  "source": "tiingo",
  "ingested_at": "2024-01-31T22:00:00Z"
}
```

### economic_indicators/{indicator}_{date}

Economic indicators (future expansion).

**Document ID Format:** `unemployment_rate_2024-01-31`
**Document Structure:**
```json
{
  "indicator": "unemployment_rate",
  "name": "U.S. Unemployment Rate",
  "date": "2024-01-31",
  "value": 3.7,
  "unit": "percent",
  "frequency": "monthly",
  "source": "fred", // Federal Reserve Economic Data
  "release_date": "2024-02-02",
  "revised": false,
  "ingested_at": "2024-02-02T15:30:00Z"
}
```

---

## Collection Patterns and Conventions

### Document ID Patterns
- **Daily data:** `{ticker}_{YYYY-MM-DD}`
- **Intraday data:** `{ticker}_{YYYY-MM-DD}T{HH:MM:SS}Z`
- **Quarterly data:** `{ticker}_{YYYY-Q#}`
- **News articles:** `{ticker}_{provider}_{article_id}` or `market_{provider}_{article_id}`
- **Transactions:** `{ticker}_{tx_id}` or `{ticker}_{type}_{date}_{sequence}`

### Required Fields
All processed documents must include:
- `ingested_at`: ISO 8601 timestamp when data was ingested
- `source`: Data provider (tiingo, finnhub, polygon, alphavantage)

### Optional Standard Fields
- `last_updated`: When the source data was last updated
- `version`: Document schema version for future migrations
- `quality_score`: Data quality assessment (0-1 scale)
- `alerts`: Associated alert rules or triggers

### Retention Policies

#### Raw Data
- `raw_ingestion_logs/`: Retain for 90 days, then archive to Cloud Storage
- Archive policy: Move to Coldline storage after 30 days

#### Processed Data
- **Daily prices:** Retain indefinitely (historical analysis)
- **Intraday quotes:** Retain for 30 days (storage optimization)
- **News articles:** Retain for 2 years
- **Fundamentals:** Retain indefinitely
- **Technical indicators:** Retain for 1 year
- **Insider transactions:** Retain indefinitely (regulatory)
- **Earnings calendar:** Retain indefinitely
- **Analyst ratings:** Retain for 2 years

---

## Firestore Composite Indexes

The following composite indexes should be created for optimal query performance:

```javascript
// Collection: prices_daily
{ "ticker": "asc", "date": "desc" }

// Collection: prices_intraday  
{ "ticker": "asc", "timestamp": "desc" }

// Collection: news_articles
{ "ticker": "asc", "published_at": "desc" }
{ "category": "asc", "published_at": "desc" }
{ "sentiment_label": "asc", "published_at": "desc" }

// Collection: technical_indicators
{ "ticker": "asc", "indicator": "asc", "date": "desc" }

// Collection: earnings_calendar
{ "ticker": "asc", "earnings_date": "asc" }
{ "earnings_date": "asc", "quarter": "asc" }

// Collection: analyst_ratings
{ "ticker": "asc", "date": "desc" }
{ "consensus": "asc", "date": "desc" }

// Collection: raw_ingestion_logs (for cleanup queries)
{ "metadata.job_id": "asc", "response.timestamp": "desc" }
```

Create these indexes using the Firebase Console or gcloud CLI:
```bash
gcloud firestore indexes composite create \
  --collection-group=prices_daily \
  --field-config field-path=ticker,order=ascending \
  --field-config field-path=date,order=descending
```

---

## Migration and Versioning

### Schema Versioning
Each document type should include a `schema_version` field to enable future migrations:

```json
{
  "schema_version": "1.0",
  // ... document fields
}
```

### Migration Strategy
1. Deploy new ingestion code that writes both old and new schema versions
2. Run migration script to update existing documents
3. Update query code to use new schema
4. Remove old schema write capability

### Backward Compatibility
- Never remove required fields without migration
- Always add new fields as optional
- Use field aliases in Pydantic models for renames
- Document breaking changes in migration notes