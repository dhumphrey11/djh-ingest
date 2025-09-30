"""
Finnhub Service FastAPI Application
Handles intraday quotes, company news, fundamentals, earnings, insider transactions, analyst ratings
"""

import logging
import os
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from finnhub_client import FinnhubClient, FinnhubError
from shared.models import ServiceResponse, ScopeType
from shared.utils.env import get_config, setup_logging, load_api_keys


# Setup logging
config = get_config()
setup_logging(config)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Finnhub Data Service",
    description="Microservice for fetching real-time quotes, news, fundamentals from Finnhub API",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global client instance
finnhub_client: Optional[FinnhubClient] = None


def get_finnhub_client() -> FinnhubClient:
    """Dependency to get Finnhub client instance"""
    global finnhub_client
    if finnhub_client is None:
        api_keys = load_api_keys(config)
        api_key = api_keys.get('finnhub_api_key')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="Finnhub API key not configured"
            )
        finnhub_client = FinnhubClient(api_key=api_key)
    return finnhub_client


@app.on_event("startup")

async def startup_event():
    """Initialize service on startup"""
    logger.info("Starting Finnhub service")
    try:
        client = get_finnhub_client()
        await client.health_check()
        logger.info("Finnhub service initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Finnhub service: {e}")


@app.on_event("shutdown")

async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down Finnhub service")
    global finnhub_client
    if finnhub_client:
        await finnhub_client.close()
        finnhub_client = None


@app.get("/health")

async def health_check():
    """Health check endpoint"""
    try:
        client = get_finnhub_client()
        await client.health_check()
        return {
            "status": "healthy",
            "service": "finnhub-service",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Service unhealthy: {str(e)}"
        )


# Request models

class FetchRequest(BaseModel):
    """Base request model for fetch endpoints"""
    tickers: List[str]
    scope: ScopeType
    job_id: str
    run_time: datetime


class QuoteRequest(FetchRequest):
    """Request model for quote endpoint"""
    pass


class NewsRequest(FetchRequest):
    """Request model for news endpoint"""
    from_date: Optional[str] = None
    to_date: Optional[str] = None


class FundamentalsRequest(FetchRequest):
    """Request model for fundamentals endpoint"""
    pass


# Route handlers
@app.post("/fetch", response_model=ServiceResponse)

async def fetch_quotes(
    request: QuoteRequest,
    client: FinnhubClient = Depends(get_finnhub_client)
):
    """
    Fetch real-time quotes for given tickers
    """
    return await _execute_fetch(
        client.fetch_quotes,
        request,
        "quotes"
    )


@app.post("/fetch/news", response_model=ServiceResponse)

async def fetch_company_news(
    request: NewsRequest,
    client: FinnhubClient = Depends(get_finnhub_client)
):
    """
    Fetch company news for given tickers
    """
    return await _execute_fetch(
        lambda tickers: client.fetch_company_news(
            tickers=tickers,
            from_date=request.from_date,
            to_date=request.to_date
        ),
        request,
        "company_news"
    )


@app.post("/fetch/fundamentals", response_model=ServiceResponse)

async def fetch_fundamentals(
    request: FundamentalsRequest,
    client: FinnhubClient = Depends(get_finnhub_client)
):
    """
    Fetch basic fundamentals for given tickers
    """
    return await _execute_fetch(
        client.fetch_fundamentals,
        request,
        "fundamentals"
    )


@app.post("/fetch/earnings", response_model=ServiceResponse)

async def fetch_earnings(
    request: FetchRequest,
    client: FinnhubClient = Depends(get_finnhub_client)
):
    """
    Fetch earnings calendar for given tickers
    """
    return await _execute_fetch(
        client.fetch_earnings_calendar,
        request,
        "earnings"
    )


@app.post("/fetch/insider-transactions", response_model=ServiceResponse)

async def fetch_insider_transactions(
    request: FetchRequest,
    client: FinnhubClient = Depends(get_finnhub_client)
):
    """
    Fetch insider transactions for given tickers
    """
    return await _execute_fetch(
        client.fetch_insider_transactions,
        request,
        "insider_transactions"
    )


@app.post("/fetch/analyst-ratings", response_model=ServiceResponse)

async def fetch_analyst_ratings(
    request: FetchRequest,
    client: FinnhubClient = Depends(get_finnhub_client)
):
    """
    Fetch analyst ratings for given tickers
    """
    return await _execute_fetch(
        client.fetch_analyst_ratings,
        request,
        "analyst_ratings"
    )


async def _execute_fetch(fetch_func, request: FetchRequest, data_type: str):
    """
    Common execution pattern for fetch operations
    """
    start_time = datetime.utcnow()
    logger.info(f"Processing {data_type} request for {len(request.tickers)} tickers, job_id: {request.job_id}")

    try:
        results = await fetch_func(request.tickers)

        # Calculate metrics
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        successful_tickers = [r['ticker'] for r in results if 'error' not in r]
        failed_tickers = [r['ticker'] for r in results if 'error' in r]

        logger.info(
            f"Completed {data_type} request - Success: {len(successful_tickers)}, "
            f"Failed: {len(failed_tickers)}, Duration: {duration_ms}ms"
        )

        if failed_tickers:
            logger.warning(f"Failed tickers for {data_type}: {failed_tickers}")

        return ServiceResponse(
            status="ok",
            fetched=len(successful_tickers),
            data=results,
            errors=[f"Failed: {ticker}" for ticker in failed_tickers] if failed_tickers else None,
            duration_ms=duration_ms
        )

    except FinnhubError as e:
        logger.error(f"Finnhub API error: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Finnhub API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in {data_type}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# Individual ticker endpoints for testing/debugging
@app.get("/ticker/{ticker}/quote")

async def get_quote(
    ticker: str,
    client: FinnhubClient = Depends(get_finnhub_client)
):
    """Get real-time quote for a single ticker"""
    try:
        data = await client.fetch_quotes([ticker.upper()])

        if not data or len(data) == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No quote data found for ticker {ticker}"
            )

        ticker_data = data[0]
        if 'error' in ticker_data:
            raise HTTPException(
                status_code=404,
                detail=f"Error fetching quote for {ticker}: {ticker_data['error']}"
            )

        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "data": ticker_data
        }

    except HTTPException:
        raise
    except FinnhubError as e:
        logger.error(f"Finnhub API error for ticker {ticker}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Finnhub API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting quote for {ticker}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/ticker/{ticker}/news")

async def get_ticker_news(
    ticker: str,
    from_date: Optional[str] = Query(None, description="From date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="To date (YYYY-MM-DD)"),
    client: FinnhubClient = Depends(get_finnhub_client)
):
    """Get company news for a single ticker"""
    try:
        data = await client.fetch_company_news(
            tickers=[ticker.upper()],
            from_date=from_date,
            to_date=to_date
        )

        if not data or len(data) == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No news data found for ticker {ticker}"
            )

        ticker_data = data[0]
        if 'error' in ticker_data:
            raise HTTPException(
                status_code=404,
                detail=f"Error fetching news for {ticker}: {ticker_data['error']}"
            )

        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "data": ticker_data,
            "count": len(ticker_data.get('data', []))
        }

    except HTTPException:
        raise
    except FinnhubError as e:
        logger.error(f"Finnhub API error for ticker {ticker}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Finnhub API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting news for {ticker}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/ticker/{ticker}/fundamentals")

async def get_fundamentals(
    ticker: str,
    client: FinnhubClient = Depends(get_finnhub_client)
):
    """Get basic fundamentals for a single ticker"""
    try:
        data = await client.fetch_fundamentals([ticker.upper()])

        if not data or len(data) == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No fundamentals data found for ticker {ticker}"
            )

        ticker_data = data[0]
        if 'error' in ticker_data:
            raise HTTPException(
                status_code=404,
                detail=f"Error fetching fundamentals for {ticker}: {ticker_data['error']}"
            )

        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "data": ticker_data
        }

    except HTTPException:
        raise
    except FinnhubError as e:
        logger.error(f"Finnhub API error for ticker {ticker}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Finnhub API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting fundamentals for {ticker}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/market/news")

async def get_market_news(
    category: str = Query("general", description="News category"),
    client: FinnhubClient = Depends(get_finnhub_client)
):
    """Get general market news"""
    try:
        data = await client.fetch_market_news(category=category)

        return {
            "status": "ok",
            "category": category,
            "data": data,
            "count": len(data)
        }

    except FinnhubError as e:
        logger.error(f"Finnhub API error for market news: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Finnhub API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting market news: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/metrics")

async def get_metrics():
    """Get service metrics"""

    if not finnhub_client:
        return {
            "status": "not_initialized",
            "client_stats": None
        }

    return {
        "status": "ok",
        "client_stats": finnhub_client.get_stats(),
        "service": "finnhub-service",
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        reload=False
    )