"""
Orchestrator FastAPI Application
Handles Cloud Scheduler requests and coordinates data ingestion across all services
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from shared.models import SchedulerRequest, SchedulerResponse
from scheduler_handlers import SchedulerHandlers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global scheduler handlers instance
handlers: Optional[SchedulerHandlers] = None


@asynccontextmanager

async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global handlers

    # Startup
    logger.info("Starting orchestrator service...")
    handlers = SchedulerHandlers()

    yield

    # Shutdown
    logger.info("Shutting down orchestrator service...")
    if handlers:
        await handlers.close()


# Create FastAPI app
app = FastAPI(
    title="Stock Analysis Orchestrator",
    description="Orchestrates data ingestion from multiple financial data providers",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_handlers() -> SchedulerHandlers:
    """Dependency to get scheduler handlers"""
    if handlers is None:
        raise HTTPException(status_code=503, detail="Handlers not initialized")
    return handlers


# ===========================================
# HEALTH & STATUS ENDPOINTS
# ===========================================

@app.get("/health")

async def health_check():
    """Health check endpoint for load balancer"""
    return {
        "status": "healthy",
        "service": "orchestrator",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/status")

async def get_status(handlers: SchedulerHandlers = Depends(get_handlers)):
    """Get orchestrator status and statistics"""
    # Get handler stats
    handler_stats = handlers.get_stats()

    # Health check all services
    service_health = await handlers.service_client.health_check_all()

    # Calculate overall health
    all_healthy = all(service.get("healthy", False) for service in service_health.values())

    return {
        "status": "healthy" if all_healthy else "degraded",
        "service": "orchestrator",
        "timestamp": datetime.utcnow().isoformat(),
        "handler_stats": handler_stats,
        "service_health": service_health,
        "service_urls": handlers.service_client.get_service_urls()
    }


# ===========================================
# TIINGO JOB ENDPOINTS
# ===========================================

@app.post("/tiingo/daily-prices", response_model=SchedulerResponse)

async def handle_tiingo_daily_prices(
    request: SchedulerRequest,
    handlers: SchedulerHandlers = Depends(get_handlers)
):
    """
    Cloud Scheduler endpoint for tiingo-daily-prices job
    Fetches EOD daily prices for entire watchlist
    """
    logger.info(f"Processing tiingo-daily-prices job: {request.job}")

    try:
        result = await handlers.handle_tiingo_daily_prices(request)

        return SchedulerResponse(
            status="ok" if result.get("status") == "success" else "error",
            data=result,
            job=request.job,
            message=f"Tiingo daily prices job completed"
        )
    except Exception as e:
        logger.error(f"Tiingo daily prices job failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tiingo/daily-prices-indices", response_model=SchedulerResponse)

async def handle_tiingo_daily_prices_indices(
    request: SchedulerRequest,
    handlers: SchedulerHandlers = Depends(get_handlers)
):
    """
    Cloud Scheduler endpoint for tiingo-daily-prices-indices job
    Fetches EOD daily prices for market indices
    """
    logger.info(f"Processing tiingo-daily-prices-indices job: {request.job}")

    try:
        result = await handlers.handle_tiingo_daily_prices_indices(request)

        return SchedulerResponse(
            status="ok" if result.get("status") == "success" else "error",
            data=result,
            job=request.job,
            message="Tiingo indices daily prices job completed"
        )
    except Exception as e:
        logger.error(f"Tiingo indices daily prices job failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================
# FINNHUB JOB ENDPOINTS
# ===========================================

@app.post("/finnhub/quote-portfolio", response_model=SchedulerResponse)

async def handle_finnhub_quote_portfolio(
    request: SchedulerRequest,
    handlers: SchedulerHandlers = Depends(get_handlers)
):
    """
    Cloud Scheduler endpoint for finnhub-quote-portfolio job
    Fetches intraday quotes for active portfolio symbols
    """
    logger.info(f"Processing finnhub-quote-portfolio job: {request.job}")

    try:
        result = await handlers.handle_finnhub_quote_portfolio(request)

        return SchedulerResponse(
            status="ok" if result.get("status") == "success" else "error",
            data=result,
            job=request.job,
            message="Finnhub portfolio quotes job completed"
        )
    except Exception as e:
        logger.error(f"Finnhub portfolio quotes job failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/finnhub/quote-indices", response_model=SchedulerResponse)

async def handle_finnhub_quote_indices(
    request: SchedulerRequest,
    handlers: SchedulerHandlers = Depends(get_handlers)
):
    """
    Cloud Scheduler endpoint for finnhub-quote-indices job
    Fetches intraday quotes for market indices
    """
    logger.info(f"Processing finnhub-quote-indices job: {request.job}")

    try:
        result = await handlers.handle_finnhub_quote_indices(request)

        return SchedulerResponse(
            status="ok" if result.get("status") == "success" else "error",
            data=result,
            job=request.job,
            message="Finnhub indices quotes job completed"
        )
    except Exception as e:
        logger.error(f"Finnhub indices quotes job failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/finnhub/company-news-universe", response_model=SchedulerResponse)

async def handle_finnhub_company_news_universe(
    request: SchedulerRequest,
    handlers: SchedulerHandlers = Depends(get_handlers)
):
    """
    Cloud Scheduler endpoint for finnhub-company-news-universe job
    Fetches company news for entire watchlist
    """
    logger.info(f"Processing finnhub-company-news-universe job: {request.job}")

    try:
        result = await handlers.handle_finnhub_company_news_universe(request)

        return SchedulerResponse(
            status="ok" if result.get("status") == "success" else "error",
            data=result,
            job=request.job,
            message="Finnhub universe company news job completed"
        )
    except Exception as e:
        logger.error(f"Finnhub universe company news job failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/finnhub/company-news-portfolio", response_model=SchedulerResponse)

async def handle_finnhub_company_news_portfolio(
    request: SchedulerRequest,
    handlers: SchedulerHandlers = Depends(get_handlers)
):
    """
    Cloud Scheduler endpoint for finnhub-company-news-portfolio job
    Fetches company news for active portfolio symbols
    """
    logger.info(f"Processing finnhub-company-news-portfolio job: {request.job}")

    try:
        result = await handlers.handle_finnhub_company_news_portfolio(request)

        return SchedulerResponse(
            status="ok" if result.get("status") == "success" else "error",
            data=result,
            job=request.job,
            message="Finnhub portfolio company news job completed"
        )
    except Exception as e:
        logger.error(f"Finnhub portfolio company news job failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/finnhub/fundamentals-earnings", response_model=SchedulerResponse)

async def handle_finnhub_fundamentals_earnings(
    request: SchedulerRequest,
    handlers: SchedulerHandlers = Depends(get_handlers)
):
    """
    Cloud Scheduler endpoint for finnhub-fundamentals-earnings job
    Fetches fundamentals and earnings data for entire watchlist
    """
    logger.info(f"Processing finnhub-fundamentals-earnings job: {request.job}")

    try:
        result = await handlers.handle_finnhub_fundamentals_earnings(request)

        return SchedulerResponse(
            status="ok" if result.get("status") == "success" else "error",
            data=result,
            job=request.job,
            message="Finnhub fundamentals and earnings job completed"
        )
    except Exception as e:
        logger.error(f"Finnhub fundamentals and earnings job failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================
# POLYGON JOB ENDPOINTS
# ===========================================

@app.post("/polygon/news-universe", response_model=SchedulerResponse)

async def handle_polygon_news_universe(
    request: SchedulerRequest,
    handlers: SchedulerHandlers = Depends(get_handlers)
):
    """
    Cloud Scheduler endpoint for polygon-news-universe job
    Fetches company news for entire watchlist
    """
    logger.info(f"Processing polygon-news-universe job: {request.job}")

    try:
        result = await handlers.handle_polygon_news_universe(request)

        return SchedulerResponse(
            status="ok" if result.get("status") == "success" else "error",
            data=result,
            job=request.job,
            message="Polygon universe news job completed"
        )
    except Exception as e:
        logger.error(f"Polygon universe news job failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/polygon/news-portfolio", response_model=SchedulerResponse)

async def handle_polygon_news_portfolio(
    request: SchedulerRequest,
    handlers: SchedulerHandlers = Depends(get_handlers)
):
    """
    Cloud Scheduler endpoint for polygon-news-portfolio job
    Fetches company news for active portfolio symbols
    """
    logger.info(f"Processing polygon-news-portfolio job: {request.job}")

    try:
        result = await handlers.handle_polygon_news_portfolio(request)

        return SchedulerResponse(
            status="ok" if result.get("status") == "success" else "error",
            data=result,
            job=request.job,
            message="Polygon portfolio news job completed"
        )
    except Exception as e:
        logger.error(f"Polygon portfolio news job failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/polygon/news-market", response_model=SchedulerResponse)

async def handle_polygon_news_market(
    request: SchedulerRequest,
    handlers: SchedulerHandlers = Depends(get_handlers)
):
    """
    Cloud Scheduler endpoint for polygon-news-market job
    Fetches market-wide news stories
    """
    logger.info(f"Processing polygon-news-market job: {request.job}")

    try:
        result = await handlers.handle_polygon_news_market(request)

        return SchedulerResponse(
            status="ok" if result.get("status") == "success" else "error",
            data=result,
            job=request.job,
            message="Polygon market news job completed"
        )
    except Exception as e:
        logger.error(f"Polygon market news job failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================
# ALPHAVANTAGE JOB ENDPOINTS
# ===========================================

@app.post("/alphavantage/technical-indicators", response_model=SchedulerResponse)

async def handle_alphavantage_technical_indicators(
    request: SchedulerRequest,
    handlers: SchedulerHandlers = Depends(get_handlers)
):
    """
    Cloud Scheduler endpoint for alpha-vantage-technical-indicators job
    Fetches technical indicators for entire watchlist
    """
    logger.info(f"Processing alpha-vantage-technical-indicators job: {request.job}")

    try:
        result = await handlers.handle_alphavantage_technical_indicators(request)

        return SchedulerResponse(
            status="ok" if result.get("status") == "success" else "error",
            data=result,
            job=request.job,
            message="AlphaVantage technical indicators job completed"
        )
    except Exception as e:
        logger.error(f"AlphaVantage technical indicators job failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================
# MANUAL TRIGGER ENDPOINTS
# ===========================================

@app.post("/manual/trigger-job")

async def manual_trigger_job(
    request: SchedulerRequest,
    handlers: SchedulerHandlers = Depends(get_handlers)
):
    """
    Manual job trigger for testing and debugging
    Accepts any job name and routes to appropriate handler
    """
    logger.info(f"Manual trigger for job: {request.job}")

    # Job routing map
    job_handlers = {
        "tiingo-daily-prices": handlers.handle_tiingo_daily_prices,
        "tiingo-daily-prices-indices": handlers.handle_tiingo_daily_prices_indices,
        "finnhub-quote-portfolio": handlers.handle_finnhub_quote_portfolio,
        "finnhub-quote-indices": handlers.handle_finnhub_quote_indices,
        "finnhub-company-news-universe": handlers.handle_finnhub_company_news_universe,
        "finnhub-company-news-portfolio": handlers.handle_finnhub_company_news_portfolio,
        "finnhub-fundamentals-earnings": handlers.handle_finnhub_fundamentals_earnings,
        "polygon-news-universe": handlers.handle_polygon_news_universe,
        "polygon-news-portfolio": handlers.handle_polygon_news_portfolio,
        "polygon-news-market": handlers.handle_polygon_news_market,
        "alpha-vantage-technical-indicators": handlers.handle_alphavantage_technical_indicators,
    }

    handler_func = job_handlers.get(request.job)
    if not handler_func:
        available_jobs = list(job_handlers.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unknown job: {request.job}. Available jobs: {available_jobs}"
        )

    try:
        result = await handler_func(request)

        return SchedulerResponse(
            status="ok" if result.get("status") == "success" else "error",
            data=result,
            job=request.job,
            message=f"Manual trigger for {request.job} completed"
        )
    except Exception as e:
        logger.error(f"Manual job trigger failed for {request.job}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)