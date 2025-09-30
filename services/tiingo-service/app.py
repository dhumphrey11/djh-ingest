"""
Tiingo Service FastAPI Application
Handles EOD daily prices for entire watchlist & indices
"""

import logging
import os
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tiingo_client import TiingoClient, TiingoError
from shared.models import ServiceResponse, ScopeType
from shared.utils.env import get_config, setup_logging, load_api_keys, validate_service_config


# Setup logging
config = get_config()
setup_logging(config)
logger = logging.getLogger(__name__)

# Validate service-specific configuration
validate_service_config(config, "tiingo_api_key")

# Initialize FastAPI app
app = FastAPI(
    title="Tiingo Data Service",
    description="Microservice for fetching EOD daily prices from Tiingo API",
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
tiingo_client: Optional[TiingoClient] = None


def get_tiingo_client() -> TiingoClient:
    """Dependency to get Tiingo client instance"""
    global tiingo_client
    if tiingo_client is None:
        api_keys = load_api_keys(config)
        api_key = api_keys.get('tiingo_api_key')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="Tiingo API key not configured"
            )
        tiingo_client = TiingoClient(api_key=api_key)
    return tiingo_client


@app.on_event("startup")

async def startup_event():
    """Initialize service on startup"""
    logger.info("Starting Tiingo service")
    try:
        # Initialize client to verify API key
        client = get_tiingo_client()
        await client.health_check()
        logger.info("Tiingo service initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Tiingo service: {e}")
        # Don't raise here - let health check handle it


@app.on_event("shutdown")

async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down Tiingo service")
    global tiingo_client
    if tiingo_client:
        await tiingo_client.close()
        tiingo_client = None


@app.get("/health")

async def health_check():
    """Health check endpoint"""
    try:
        client = get_tiingo_client()
        await client.health_check()
        return {
            "status": "healthy",
            "service": "tiingo-service",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Service unhealthy: {str(e)}"
        )


class FetchRequest(BaseModel):
    """Request model for fetch endpoint"""
    tickers: List[str]
    scope: ScopeType
    job_id: str
    run_time: datetime
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@app.post("/fetch", response_model=ServiceResponse)

async def fetch_daily_prices(
    request: FetchRequest,
    client: TiingoClient = Depends(get_tiingo_client)
):
    """
    Fetch daily prices for given tickers

    Args:
        request: Fetch request with tickers and parameters
        client: Tiingo client dependency

    Returns:
        ServiceResponse with fetched data
    """
    start_time = datetime.utcnow()
    logger.info(f"Processing fetch request for {len(request.tickers)} tickers, job_id: {request.job_id}")

    try:
        # Fetch data for all tickers
        results = await client.fetch_daily_prices(
            tickers=request.tickers,
            start_date=request.start_date,
            end_date=request.end_date
        )

        # Calculate metrics
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        successful_tickers = [r['ticker'] for r in results if 'error' not in r]
        failed_tickers = [r['ticker'] for r in results if 'error' in r]

        logger.info(
            f"Completed fetch request - Success: {len(successful_tickers)}, "
            f"Failed: {len(failed_tickers)}, Duration: {duration_ms}ms"
        )

        # Log any failures
        if failed_tickers:
            logger.warning(f"Failed tickers: {failed_tickers}")

        return ServiceResponse(
            status="ok",
            fetched=len(successful_tickers),
            data=results,
            errors=[f"Failed: {ticker}" for ticker in failed_tickers] if failed_tickers else None,
            duration_ms=duration_ms
        )

    except TiingoError as e:
        logger.error(f"Tiingo API error: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Tiingo API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in fetch_daily_prices: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/supported_tickers")

async def get_supported_tickers(
    client: TiingoClient = Depends(get_tiingo_client)
):
    """
    Get list of supported tickers from Tiingo

    Returns:
        List of supported ticker symbols
    """
    try:
        tickers = await client.get_supported_tickers()
        return {
            "status": "ok",
            "count": len(tickers),
            "tickers": tickers[:100] if len(tickers) > 100 else tickers,  # Limit response size
            "total_available": len(tickers)
        }
    except TiingoError as e:
        logger.error(f"Failed to get supported tickers: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Tiingo API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting supported tickers: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/ticker/{ticker}/latest")

async def get_latest_price(
    ticker: str,
    client: TiingoClient = Depends(get_tiingo_client)
):
    """
    Get latest daily price for a single ticker

    Args:
        ticker: Stock ticker symbol
        client: Tiingo client dependency

    Returns:
        Latest price data for the ticker
    """
    try:
        data = await client.fetch_daily_prices(
            tickers=[ticker.upper()],
            start_date=None,
            end_date=None
        )

        if not data or len(data) == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for ticker {ticker}"
            )

        ticker_data = data[0]
        if 'error' in ticker_data:
            raise HTTPException(
                status_code=404,
                detail=f"Error fetching data for {ticker}: {ticker_data['error']}"
            )

        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "data": ticker_data
        }

    except HTTPException:
        raise
    except TiingoError as e:
        logger.error(f"Tiingo API error for ticker {ticker}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Tiingo API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting latest price for {ticker}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/metrics")

async def get_metrics():
    """
    Get service metrics

    Returns:
        Service performance metrics
    """

    if not tiingo_client:
        return {
            "status": "not_initialized",
            "client_stats": None
        }

    return {
        "status": "ok",
        "client_stats": tiingo_client.get_stats(),
        "service": "tiingo-service",
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
