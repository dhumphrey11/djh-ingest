"""
AlphaVantage Service FastAPI Application
Handles technical indicators from AlphaVantage API
"""

import logging
import os
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from alphavantage_client import AlphaVantageClient, AlphaVantageError
from shared.models import ServiceRequest, ServiceResponse, ScopeType
from shared.utils.env import get_config, setup_logging, load_api_keys


# Setup logging
config = get_config()
setup_logging(config)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="AlphaVantage Data Service",
    description="Microservice for fetching technical indicators from AlphaVantage API",
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
alphavantage_client: Optional[AlphaVantageClient] = None


def get_alphavantage_client() -> AlphaVantageClient:
    """Dependency to get AlphaVantage client instance"""
    global alphavantage_client
    if alphavantage_client is None:
        api_keys = load_api_keys(config)
        api_key = api_keys.get('alphavantage_api_key')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="AlphaVantage API key not configured"
            )
        alphavantage_client = AlphaVantageClient(api_key=api_key)
    return alphavantage_client


@app.on_event("startup")
async def startup_event():
    """Initialize service on startup"""
    logger.info("Starting AlphaVantage service")
    try:
        client = get_alphavantage_client()
        await client.health_check()
        logger.info("AlphaVantage service initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize AlphaVantage service: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down AlphaVantage service")
    global alphavantage_client
    if alphavantage_client:
        await alphavantage_client.close()
        alphavantage_client = None


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        client = get_alphavantage_client()
        await client.health_check()
        return {
            "status": "healthy",
            "service": "alphavantage-service",
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


class TechnicalIndicatorRequest(FetchRequest):
    """Request model for technical indicators"""
    indicators: Optional[List[str]] = None  # If None, fetch all default indicators
    interval: Optional[str] = "daily"  # daily, weekly, monthly
    time_period: Optional[int] = None  # For indicators that support it


# Route handlers
@app.post("/fetch", response_model=ServiceResponse)
async def fetch_technical_indicators(
    request: TechnicalIndicatorRequest,
    client: AlphaVantageClient = Depends(get_alphavantage_client)
):
    """
    Fetch technical indicators for given tickers
    """
    return await _execute_fetch(
        lambda tickers: client.fetch_technical_indicators(
            tickers=tickers,
            indicators=request.indicators,
            interval=request.interval,
            time_period=request.time_period
        ),
        request,
        "technical_indicators"
    )


async def _execute_fetch(fetch_func, request: FetchRequest, data_type: str):
    """Common execution pattern for fetch operations"""
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
        
    except AlphaVantageError as e:
        logger.error(f"AlphaVantage API error: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"AlphaVantage API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in {data_type}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# Individual ticker endpoints for testing/debugging
@app.get("/ticker/{ticker}/indicators")
async def get_ticker_indicators(
    ticker: str,
    indicators: Optional[str] = Query(None, description="Comma-separated list of indicators (RSI,SMA,MACD)"),
    interval: str = Query("daily", description="Time interval"),
    time_period: Optional[int] = Query(None, description="Time period for indicators"),
    client: AlphaVantageClient = Depends(get_alphavantage_client)
):
    """Get technical indicators for a single ticker"""
    try:
        indicator_list = indicators.split(',') if indicators else None
        
        data = await client.fetch_technical_indicators(
            tickers=[ticker.upper()],
            indicators=indicator_list,
            interval=interval,
            time_period=time_period
        )
        
        if not data or len(data) == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No indicator data found for ticker {ticker}"
            )
        
        ticker_data = data[0]
        if 'error' in ticker_data:
            raise HTTPException(
                status_code=404,
                detail=f"Error fetching indicators for {ticker}: {ticker_data['error']}"
            )
        
        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "data": ticker_data.get('data', {}),
            "indicators": list(ticker_data.get('data', {}).keys())
        }
        
    except HTTPException:
        raise
    except AlphaVantageError as e:
        logger.error(f"AlphaVantage API error for ticker {ticker}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"AlphaVantage API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting indicators for {ticker}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/ticker/{ticker}/indicator/{indicator}")
async def get_single_indicator(
    ticker: str,
    indicator: str,
    interval: str = Query("daily", description="Time interval"),
    time_period: Optional[int] = Query(None, description="Time period"),
    client: AlphaVantageClient = Depends(get_alphavantage_client)
):
    """Get a single technical indicator for a ticker"""
    try:
        data = await client.fetch_single_indicator(
            ticker=ticker.upper(),
            indicator=indicator.upper(),
            interval=interval,
            time_period=time_period
        )
        
        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "indicator": indicator.upper(),
            "data": data
        }
        
    except AlphaVantageError as e:
        logger.error(f"AlphaVantage API error for {ticker}/{indicator}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"AlphaVantage API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting {indicator} for {ticker}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/supported-indicators")
async def get_supported_indicators():
    """Get list of supported technical indicators"""
    return {
        "status": "ok",
        "indicators": {
            "trend": ["SMA", "EMA", "WMA", "DEMA", "TEMA", "TRIMA"],
            "momentum": ["RSI", "STOCH", "STOCHF", "STOCHRSI", "WILLR", "ADX", "ADXR"],
            "volume": ["OBV", "AD", "CHAIKIN"],
            "volatility": ["BBANDS", "NATR", "TRANGE", "ATR"],
            "price_transform": ["AVGPRICE", "MEDPRICE", "TYPPRICE", "WCLPRICE"],
            "overlap": ["UPPERBB", "MIDDLEBB", "LOWERBB", "HT_TRENDLINE"],
            "momentum_oscillators": ["MACD", "MACDEXT", "CCI", "CMO", "ROC", "ROCR"],
            "cycle_indicators": ["HT_DCPERIOD", "HT_DCPHASE", "HT_PHASOR", "HT_SINE"],
            "pattern_recognition": ["CDL2CROWS", "CDL3BLACKCROWS", "CDL3INSIDE", "CDL3LINESTRIKE"]
        },
        "intervals": ["1min", "5min", "15min", "30min", "60min", "daily", "weekly", "monthly"],
        "default_indicators": ["RSI", "SMA", "EMA", "MACD", "BBANDS", "STOCH", "ADX"]
    }


@app.get("/rate-limit/status")
async def get_rate_limit_status(
    client: AlphaVantageClient = Depends(get_alphavantage_client)
):
    """Get current rate limit status"""
    stats = client.get_stats()
    
    return {
        "status": "ok",
        "rate_limit": stats.get("rate_limit_status", {}),
        "recent_activity": {
            "requests_last_minute": stats["rate_limit_status"]["recent_requests"],
            "per_minute_limit": stats["rate_limit_status"]["per_minute_limit"],
            "utilization_percent": round(
                stats["rate_limit_status"]["recent_requests"] / 
                max(stats["rate_limit_status"]["per_minute_limit"], 1) * 100, 2
            )
        },
        "recommendations": client.get_throttling_recommendations()
    }


@app.get("/metrics")
async def get_metrics():
    """Get service metrics"""
    
    if not alphavantage_client:
        return {
            "status": "not_initialized",
            "client_stats": None
        }
    
    return {
        "status": "ok",
        "client_stats": alphavantage_client.get_stats(),
        "service": "alphavantage-service",
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