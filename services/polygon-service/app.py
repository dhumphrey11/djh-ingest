"""
Polygon Service FastAPI Application
Handles market-wide and company news from Polygon API
"""

import logging
import os
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from polygon_client import PolygonClient, PolygonError
from shared.models import ServiceRequest, ServiceResponse, ScopeType
from shared.utils.env import get_config, setup_logging, load_api_keys


# Setup logging
config = get_config()
setup_logging(config)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Polygon Data Service",
    description="Microservice for fetching news from Polygon API",
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
polygon_client: Optional[PolygonClient] = None


def get_polygon_client() -> PolygonClient:
    """Dependency to get Polygon client instance"""
    global polygon_client
    if polygon_client is None:
        api_keys = load_api_keys(config)
        api_key = api_keys.get('polygon_api_key')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="Polygon API key not configured"
            )
        polygon_client = PolygonClient(api_key=api_key)
    return polygon_client


@app.on_event("startup")
async def startup_event():
    """Initialize service on startup"""
    logger.info("Starting Polygon service")
    try:
        client = get_polygon_client()
        await client.health_check()
        logger.info("Polygon service initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Polygon service: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down Polygon service")
    global polygon_client
    if polygon_client:
        await polygon_client.close()
        polygon_client = None


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        client = get_polygon_client()
        await client.health_check()
        return {
            "status": "healthy",
            "service": "polygon-service",
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


class NewsRequest(FetchRequest):
    """Request model for news endpoint"""
    published_date: Optional[str] = None
    limit: Optional[int] = None


# Route handlers
@app.post("/fetch", response_model=ServiceResponse)
async def fetch_company_news(
    request: NewsRequest,
    client: PolygonClient = Depends(get_polygon_client)
):
    """
    Fetch company news for given tickers
    """
    return await _execute_fetch(
        lambda tickers: client.fetch_company_news(
            tickers=tickers,
            published_date=request.published_date,
            limit=request.limit
        ),
        request,
        "company_news"
    )


@app.post("/fetch/market", response_model=ServiceResponse)
async def fetch_market_news(
    request: FetchRequest,
    client: PolygonClient = Depends(get_polygon_client)
):
    """
    Fetch general market news
    """
    return await _execute_fetch(
        lambda _: client.fetch_market_news(),
        request,
        "market_news"
    )


async def _execute_fetch(fetch_func, request: FetchRequest, data_type: str):
    """Common execution pattern for fetch operations"""
    start_time = datetime.utcnow()
    logger.info(f"Processing {data_type} request for {len(request.tickers)} tickers, job_id: {request.job_id}")
    
    try:
        results = await fetch_func(request.tickers)
        
        # Calculate metrics
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        # For news, count successful articles rather than tickers
        if isinstance(results, list) and len(results) > 0 and isinstance(results[0], dict):
            if 'ticker' in results[0]:
                # Company news - count successful tickers
                successful_count = len([r for r in results if 'error' not in r])
                failed_count = len([r for r in results if 'error' in r])
                failed_items = [r['ticker'] for r in results if 'error' in r]
            else:
                # Market news - count articles
                successful_count = len(results)
                failed_count = 0
                failed_items = []
        else:
            successful_count = 0
            failed_count = 0
            failed_items = []
        
        logger.info(
            f"Completed {data_type} request - Success: {successful_count}, "
            f"Failed: {failed_count}, Duration: {duration_ms}ms"
        )
        
        if failed_items:
            logger.warning(f"Failed items for {data_type}: {failed_items}")
        
        return ServiceResponse(
            status="ok",
            fetched=successful_count,
            data=results,
            errors=[f"Failed: {item}" for item in failed_items] if failed_items else None,
            duration_ms=duration_ms
        )
        
    except PolygonError as e:
        logger.error(f"Polygon API error: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Polygon API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in {data_type}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# Individual endpoints for testing/debugging
@app.get("/ticker/{ticker}/news")
async def get_ticker_news(
    ticker: str,
    published_date: Optional[str] = Query(None, description="Published date (YYYY-MM-DD)"),
    limit: Optional[int] = Query(10, description="Number of articles to return"),
    client: PolygonClient = Depends(get_polygon_client)
):
    """Get company news for a single ticker"""
    try:
        data = await client.fetch_company_news(
            tickers=[ticker.upper()],
            published_date=published_date,
            limit=limit
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
            "data": ticker_data.get('data', []),
            "count": len(ticker_data.get('data', []))
        }
        
    except HTTPException:
        raise
    except PolygonError as e:
        logger.error(f"Polygon API error for ticker {ticker}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Polygon API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting news for {ticker}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/market/news")
async def get_market_news(
    published_date: Optional[str] = Query(None, description="Published date (YYYY-MM-DD)"),
    limit: Optional[int] = Query(10, description="Number of articles to return"),
    client: PolygonClient = Depends(get_polygon_client)
):
    """Get general market news"""
    try:
        data = await client.fetch_market_news(
            published_date=published_date,
            limit=limit
        )
        
        return {
            "status": "ok",
            "data": data,
            "count": len(data)
        }
        
    except PolygonError as e:
        logger.error(f"Polygon API error for market news: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Polygon API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting market news: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/news/search")
async def search_news(
    query: str = Query(..., description="Search query"),
    published_date: Optional[str] = Query(None, description="Published date (YYYY-MM-DD)"),
    limit: Optional[int] = Query(10, description="Number of articles to return"),
    client: PolygonClient = Depends(get_polygon_client)
):
    """Search news articles by keyword"""
    try:
        data = await client.search_news(
            query=query,
            published_date=published_date,
            limit=limit
        )
        
        return {
            "status": "ok",
            "query": query,
            "data": data,
            "count": len(data)
        }
        
    except PolygonError as e:
        logger.error(f"Polygon API error for news search: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Polygon API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error searching news: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/tickers/trending")
async def get_trending_tickers(
    client: PolygonClient = Depends(get_polygon_client)
):
    """Get trending ticker symbols from news coverage"""
    try:
        data = await client.get_trending_tickers()
        
        return {
            "status": "ok",
            "data": data,
            "count": len(data)
        }
        
    except PolygonError as e:
        logger.error(f"Polygon API error for trending tickers: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Polygon API error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting trending tickers: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/metrics")
async def get_metrics():
    """Get service metrics"""
    global polygon_client
    
    if not polygon_client:
        return {
            "status": "not_initialized",
            "client_stats": None
        }
    
    return {
        "status": "ok",
        "client_stats": polygon_client.get_stats(),
        "service": "polygon-service",
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