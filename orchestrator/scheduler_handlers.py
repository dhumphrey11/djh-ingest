"""
Scheduler handlers for Cloud Scheduler requests
Each handler maps to a specific scheduled job and orchestrates data ingestion
"""

import logging
from datetime import datetime
from typing import Dict, Any, List

from shared.models import SchedulerRequest, ScopeType
from shared.utils.env import get_config

from firestore_logger import get_firestore_logger
from clients.service_client import ServiceClient


logger = logging.getLogger(__name__)
config = get_config()


class SchedulerHandlers:
    """
    Handlers for Cloud Scheduler requests
    Each method corresponds to a scheduled job endpoint
    """
    
    def __init__(self):
        self.service_client = ServiceClient()
        self.stats = {
            "jobs_processed": 0,
            "jobs_successful": 0,
            "jobs_failed": 0,
            "last_job_time": None
        }
    
    async def close(self):
        """Close service client connections"""
        await self.service_client.close()
    
    # ===========================================
    # TIINGO HANDLERS
    # ===========================================
    
    async def handle_tiingo_daily_prices(self, request: SchedulerRequest) -> Dict[str, Any]:
        """
        Handler for tiingo-daily-prices job
        Fetches EOD prices for entire watchlist
        """
        return await self._execute_job(
            job_name="tiingo-daily-prices",
            request=request,
            handler_func=self._process_tiingo_daily_prices,
            expected_scope=ScopeType.ENTIRE_WATCHLIST
        )
    
    async def handle_tiingo_daily_prices_indices(self, request: SchedulerRequest) -> Dict[str, Any]:
        """
        Handler for tiingo-daily-prices-indices job  
        Fetches EOD prices for market indices
        """
        return await self._execute_job(
            job_name="tiingo-daily-prices-indices",
            request=request,
            handler_func=self._process_tiingo_daily_prices,
            expected_scope=ScopeType.INDICES
        )
    
    async def _process_tiingo_daily_prices(
        self,
        tickers: List[str],
        request: SchedulerRequest
    ) -> Dict[str, Any]:
        """Process Tiingo daily prices request"""
        logger.info(f"Processing Tiingo daily prices for {len(tickers)} symbols")
        
        # Call Tiingo service
        response = await self.service_client.fetch_tiingo_daily_prices(
            tickers=tickers,
            job_id=request.job,
            run_time=request.run_time or datetime.utcnow()
        )
        
        # Log raw response
        fs_logger = await get_firestore_logger()
        await fs_logger.log_raw(
            source="tiingo",
            api_name="daily-prices",
            scope=request.scope,
            request_params={"tickers": tickers},
            response_data=response,
            status_code=200,
            latency_ms=0,  # Service client handles timing
            job_id=request.job
        )
        
        # Process and store data
        if response.get("status") == "ok" and response.get("data"):
            processed_count = await self._store_daily_prices_data(response["data"])
            return {
                "status": "success",
                "tickers_processed": len(tickers),
                "records_stored": processed_count,
                "source": "tiingo"
            }
        else:
            raise Exception(f"Tiingo service error: {response}")
    
    # ===========================================
    # FINNHUB HANDLERS
    # ===========================================
    
    async def handle_finnhub_quote_portfolio(self, request: SchedulerRequest) -> Dict[str, Any]:
        """Handler for finnhub-quote-portfolio job"""
        return await self._execute_job(
            job_name="finnhub-quote-portfolio",
            request=request,
            handler_func=self._process_finnhub_quotes,
            expected_scope=ScopeType.ACTIVE_SYMBOLS
        )
    
    async def handle_finnhub_quote_indices(self, request: SchedulerRequest) -> Dict[str, Any]:
        """Handler for finnhub-quote-indices job"""
        return await self._execute_job(
            job_name="finnhub-quote-indices",
            request=request,
            handler_func=self._process_finnhub_quotes,
            expected_scope=ScopeType.INDICES
        )
    
    async def handle_finnhub_company_news_universe(self, request: SchedulerRequest) -> Dict[str, Any]:
        """Handler for finnhub-company-news-universe job"""
        return await self._execute_job(
            job_name="finnhub-company-news-universe",
            request=request,
            handler_func=self._process_finnhub_company_news,
            expected_scope=ScopeType.ENTIRE_WATCHLIST
        )
    
    async def handle_finnhub_company_news_portfolio(self, request: SchedulerRequest) -> Dict[str, Any]:
        """Handler for finnhub-company-news-portfolio job"""
        return await self._execute_job(
            job_name="finnhub-company-news-portfolio",
            request=request,
            handler_func=self._process_finnhub_company_news,
            expected_scope=ScopeType.ACTIVE_SYMBOLS
        )
    
    async def handle_finnhub_fundamentals_earnings(self, request: SchedulerRequest) -> Dict[str, Any]:
        """Handler for finnhub-fundamentals-earnings job"""
        return await self._execute_job(
            job_name="finnhub-fundamentals-earnings",
            request=request,
            handler_func=self._process_finnhub_fundamentals,
            expected_scope=ScopeType.ENTIRE_WATCHLIST
        )
    
    async def _process_finnhub_quotes(
        self,
        tickers: List[str], 
        request: SchedulerRequest
    ) -> Dict[str, Any]:
        """Process Finnhub quotes request"""
        logger.info(f"Processing Finnhub quotes for {len(tickers)} symbols")
        
        response = await self.service_client.fetch_finnhub_quotes(
            tickers=tickers,
            job_id=request.job,
            run_time=request.run_time or datetime.utcnow()
        )
        
        # Log raw response
        fs_logger = await get_firestore_logger()
        await fs_logger.log_raw(
            source="finnhub",
            api_name="quote",
            scope=request.scope,
            request_params={"tickers": tickers},
            response_data=response,
            status_code=200,
            latency_ms=0,
            job_id=request.job
        )
        
        # Process and store intraday quotes
        if response.get("status") == "ok" and response.get("data"):
            processed_count = await self._store_intraday_quotes_data(response["data"])
            return {
                "status": "success",
                "tickers_processed": len(tickers),
                "quotes_stored": processed_count,
                "source": "finnhub"
            }
        else:
            raise Exception(f"Finnhub quotes service error: {response}")
    
    async def _process_finnhub_company_news(
        self,
        tickers: List[str],
        request: SchedulerRequest
    ) -> Dict[str, Any]:
        """Process Finnhub company news request"""
        logger.info(f"Processing Finnhub company news for {len(tickers)} symbols")
        
        response = await self.service_client.fetch_finnhub_company_news(
            tickers=tickers,
            job_id=request.job,
            run_time=request.run_time or datetime.utcnow()
        )
        
        # Log raw response
        fs_logger = await get_firestore_logger()
        await fs_logger.log_raw(
            source="finnhub",
            api_name="company-news",
            scope=request.scope,
            request_params={"tickers": tickers},
            response_data=response,
            status_code=200,
            latency_ms=0,
            job_id=request.job
        )
        
        # Process and store news articles
        if response.get("status") == "ok" and response.get("data"):
            processed_count = await self._store_news_data(response["data"])
            return {
                "status": "success",
                "tickers_processed": len(tickers),
                "articles_stored": processed_count,
                "source": "finnhub"
            }
        else:
            raise Exception(f"Finnhub news service error: {response}")
    
    async def _process_finnhub_fundamentals(
        self,
        tickers: List[str],
        request: SchedulerRequest
    ) -> Dict[str, Any]:
        """Process Finnhub fundamentals request"""
        logger.info(f"Processing Finnhub fundamentals for {len(tickers)} symbols")
        
        # Fetch both fundamentals and earnings
        fundamentals_response = await self.service_client.fetch_finnhub_fundamentals(
            tickers=tickers,
            job_id=request.job,
            run_time=request.run_time or datetime.utcnow()
        )
        
        earnings_response = await self.service_client.fetch_finnhub_earnings(
            tickers=tickers,
            job_id=request.job,
            run_time=request.run_time or datetime.utcnow()
        )
        
        # Log raw responses
        fs_logger = await get_firestore_logger()
        await fs_logger.log_raw(
            source="finnhub",
            api_name="fundamentals",
            scope=request.scope,
            request_params={"tickers": tickers},
            response_data=fundamentals_response,
            status_code=200,
            latency_ms=0,
            job_id=request.job
        )
        
        await fs_logger.log_raw(
            source="finnhub",
            api_name="earnings",
            scope=request.scope,
            request_params={"tickers": tickers},
            response_data=earnings_response,
            status_code=200,
            latency_ms=0,
            job_id=request.job
        )
        
        # Process and store data
        fundamentals_count = 0
        earnings_count = 0
        
        if fundamentals_response.get("status") == "ok" and fundamentals_response.get("data"):
            fundamentals_count = await self._store_fundamentals_data(fundamentals_response["data"])
        
        if earnings_response.get("status") == "ok" and earnings_response.get("data"):
            earnings_count = await self._store_earnings_data(earnings_response["data"])
        
        return {
            "status": "success",
            "tickers_processed": len(tickers),
            "fundamentals_stored": fundamentals_count,
            "earnings_stored": earnings_count,
            "source": "finnhub"
        }
    
    # ===========================================
    # POLYGON HANDLERS
    # ===========================================
    
    async def handle_polygon_news_universe(self, request: SchedulerRequest) -> Dict[str, Any]:
        """Handler for polygon-news-universe job"""
        return await self._execute_job(
            job_name="polygon-news-universe",
            request=request,
            handler_func=self._process_polygon_company_news,
            expected_scope=ScopeType.ENTIRE_WATCHLIST
        )
    
    async def handle_polygon_news_portfolio(self, request: SchedulerRequest) -> Dict[str, Any]:
        """Handler for polygon-news-portfolio job"""
        return await self._execute_job(
            job_name="polygon-news-portfolio",
            request=request,
            handler_func=self._process_polygon_company_news,
            expected_scope=ScopeType.ACTIVE_SYMBOLS
        )
    
    async def handle_polygon_news_market(self, request: SchedulerRequest) -> Dict[str, Any]:
        """Handler for polygon-news-market job"""
        return await self._execute_job(
            job_name="polygon-news-market",
            request=request,
            handler_func=self._process_polygon_market_news,
            expected_scope=ScopeType.NONE
        )
    
    async def _process_polygon_company_news(
        self,
        tickers: List[str],
        request: SchedulerRequest
    ) -> Dict[str, Any]:
        """Process Polygon company news request"""
        logger.info(f"Processing Polygon company news for {len(tickers)} symbols")
        
        response = await self.service_client.fetch_polygon_company_news(
            tickers=tickers,
            job_id=request.job,
            run_time=request.run_time or datetime.utcnow()
        )
        
        # Log raw response
        fs_logger = await get_firestore_logger()
        await fs_logger.log_raw(
            source="polygon",
            api_name="company-news",
            scope=request.scope,
            request_params={"tickers": tickers},
            response_data=response,
            status_code=200,
            latency_ms=0,
            job_id=request.job
        )
        
        # Process and store news articles
        if response.get("status") == "ok" and response.get("data"):
            processed_count = await self._store_news_data(response["data"])
            return {
                "status": "success",
                "tickers_processed": len(tickers),
                "articles_stored": processed_count,
                "source": "polygon"
            }
        else:
            raise Exception(f"Polygon company news service error: {response}")
    
    async def _process_polygon_market_news(
        self,
        tickers: List[str],  # Will be empty for market news
        request: SchedulerRequest
    ) -> Dict[str, Any]:
        """Process Polygon market news request"""
        logger.info("Processing Polygon market news")
        
        response = await self.service_client.fetch_polygon_market_news(
            job_id=request.job,
            run_time=request.run_time or datetime.utcnow()
        )
        
        # Log raw response
        fs_logger = await get_firestore_logger()
        await fs_logger.log_raw(
            source="polygon",
            api_name="market-news",
            scope=request.scope,
            request_params={},
            response_data=response,
            status_code=200,
            latency_ms=0,
            job_id=request.job
        )
        
        # Process and store market news articles
        if response.get("status") == "ok" and response.get("data"):
            processed_count = await self._store_market_news_data(response["data"])
            return {
                "status": "success",
                "articles_stored": processed_count,
                "source": "polygon"
            }
        else:
            raise Exception(f"Polygon market news service error: {response}")
    
    # ===========================================
    # ALPHAVANTAGE HANDLERS
    # ===========================================
    
    async def handle_alphavantage_technical_indicators(self, request: SchedulerRequest) -> Dict[str, Any]:
        """Handler for alpha-vantage-technical-indicators job"""
        return await self._execute_job(
            job_name="alpha-vantage-technical-indicators",
            request=request,
            handler_func=self._process_alphavantage_indicators,
            expected_scope=ScopeType.ENTIRE_WATCHLIST
        )
    
    async def _process_alphavantage_indicators(
        self,
        tickers: List[str],
        request: SchedulerRequest
    ) -> Dict[str, Any]:
        """Process AlphaVantage technical indicators request"""
        logger.info(f"Processing AlphaVantage technical indicators for {len(tickers)} symbols")
        
        response = await self.service_client.fetch_alphavantage_technical_indicators(
            tickers=tickers,
            job_id=request.job,
            run_time=request.run_time or datetime.utcnow()
        )
        
        # Log raw response
        fs_logger = await get_firestore_logger()
        await fs_logger.log_raw(
            source="alphavantage",
            api_name="technical-indicators",
            scope=request.scope,
            request_params={"tickers": tickers},
            response_data=response,
            status_code=200,
            latency_ms=0,
            job_id=request.job
        )
        
        # Process and store technical indicators
        if response.get("status") == "ok" and response.get("data"):
            processed_count = await self._store_technical_indicators_data(response["data"])
            return {
                "status": "success",
                "tickers_processed": len(tickers),
                "indicators_stored": processed_count,
                "source": "alphavantage"
            }
        else:
            raise Exception(f"AlphaVantage service error: {response}")
    
    # ===========================================
    # COMMON EXECUTION LOGIC
    # ===========================================
    
    async def _execute_job(
        self,
        job_name: str,
        request: SchedulerRequest,
        handler_func,
        expected_scope: ScopeType
    ) -> Dict[str, Any]:
        """Common job execution pattern"""
        start_time = datetime.utcnow()
        self.stats["jobs_processed"] += 1
        self.stats["last_job_time"] = start_time.isoformat()
        
        try:
            # Validate scope
            if request.scope != expected_scope:
                logger.warning(f"Scope mismatch for {job_name}: expected {expected_scope}, got {request.scope}")
            
            # Get tickers based on scope
            if request.tickers:
                tickers = request.tickers
            else:
                tickers = await self._get_tickers_for_scope(request.scope)
            
            if not tickers:
                logger.warning(f"No tickers found for scope {request.scope}")
                return {
                    "status": "success",
                    "message": "No tickers to process",
                    "tickers_processed": 0
                }
            
            # Execute the specific handler
            result = await handler_func(tickers, request)
            
            # Calculate duration
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            result["duration_ms"] = duration_ms
            result["job_name"] = job_name
            
            self.stats["jobs_successful"] += 1
            
            logger.info(f"Job {job_name} completed successfully in {duration_ms}ms")
            return result
            
        except Exception as e:
            self.stats["jobs_failed"] += 1
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            logger.error(f"Job {job_name} failed after {duration_ms}ms: {e}")
            
            # Return error response
            return {
                "status": "error",
                "error": str(e),
                "job_name": job_name,
                "duration_ms": duration_ms
            }
    
    async def _get_tickers_for_scope(self, scope: ScopeType) -> List[str]:
        """Get ticker symbols based on scope"""
        fs_logger = await get_firestore_logger()
        
        if scope == ScopeType.ENTIRE_WATCHLIST:
            return await fs_logger.get_watchlist_symbols()
        elif scope == ScopeType.ACTIVE_SYMBOLS:
            return await fs_logger.get_active_symbols()
        elif scope == ScopeType.INDICES:
            return await fs_logger.get_index_symbols()
        elif scope == ScopeType.NONE:
            return []
        else:
            logger.warning(f"Unknown scope: {scope}")
            return []
    
    # ===========================================
    # DATA STORAGE HELPERS
    # ===========================================
    
    async def _store_daily_prices_data(self, data: List[Dict[str, Any]]) -> int:
        """Store daily prices data in Firestore"""
        fs_logger = await get_firestore_logger()
        
        # Flatten ticker data into individual records
        records = []
        for ticker_data in data:
            if "error" in ticker_data:
                continue
            
            ticker_records = ticker_data.get("data", [])
            for record in ticker_records:
                if isinstance(record, dict):
                    records.append(record)
        
        return await fs_logger.write_daily_prices_batch(records)
    
    async def _store_intraday_quotes_data(self, data: List[Dict[str, Any]]) -> int:
        """Store intraday quotes data in Firestore"""
        fs_logger = await get_firestore_logger()
        
        records = []
        for ticker_data in data:
            if "error" in ticker_data:
                continue
            
            quote_data = ticker_data.get("data", {})
            if quote_data:
                ticker = quote_data.get("ticker")
                timestamp = quote_data.get("timestamp")
                if ticker and timestamp:
                    doc_id = f"{ticker}_{datetime.fromtimestamp(timestamp).isoformat()}"
                    records.append({
                        "collection": "prices_intraday",
                        "doc_id": doc_id,
                        "data": quote_data,
                        "merge": False
                    })
        
        return await fs_logger.write_batch(records)
    
    async def _store_news_data(self, data: List[Dict[str, Any]]) -> int:
        """Store news articles data in Firestore"""
        fs_logger = await get_firestore_logger()
        
        # Flatten ticker news data
        articles = []
        for ticker_data in data:
            if "error" in ticker_data:
                continue
            
            ticker_articles = ticker_data.get("data", [])
            for article in ticker_articles:
                if isinstance(article, dict):
                    articles.append(article)
        
        return await fs_logger.write_news_batch(articles)
    
    async def _store_market_news_data(self, data: List[Dict[str, Any]]) -> int:
        """Store market news data in Firestore"""
        fs_logger = await get_firestore_logger()
        return await fs_logger.write_news_batch(data)
    
    async def _store_fundamentals_data(self, data: List[Dict[str, Any]]) -> int:
        """Store fundamentals data in Firestore"""
        fs_logger = await get_firestore_logger()
        
        records = []
        for ticker_data in data:
            if "error" in ticker_data:
                continue
            
            fundamental_data = ticker_data.get("data", {})
            if fundamental_data:
                ticker = fundamental_data.get("ticker")
                report_date = fundamental_data.get("report_date", "current")
                if ticker:
                    doc_id = f"{ticker}_{report_date}"
                    records.append({
                        "collection": "fundamentals",
                        "doc_id": doc_id,
                        "data": fundamental_data,
                        "merge": True
                    })
        
        return await fs_logger.write_batch(records)
    
    async def _store_earnings_data(self, data: List[Dict[str, Any]]) -> int:
        """Store earnings data in Firestore"""
        fs_logger = await get_firestore_logger()
        
        records = []
        for ticker_data in data:
            if "error" in ticker_data:
                continue
            
            earnings_list = ticker_data.get("data", [])
            for earning in earnings_list:
                if isinstance(earning, dict):
                    ticker = earning.get("ticker")
                    earnings_date = earning.get("earnings_date")
                    if ticker and earnings_date:
                        doc_id = f"{ticker}_{earnings_date}"
                        records.append({
                            "collection": "earnings_calendar",
                            "doc_id": doc_id,
                            "data": earning,
                            "merge": True
                        })
        
        return await fs_logger.write_batch(records)
    
    async def _store_technical_indicators_data(self, data: List[Dict[str, Any]]) -> int:
        """Store technical indicators data in Firestore"""
        fs_logger = await get_firestore_logger()
        
        records = []
        for ticker_data in data:
            if "error" in ticker_data:
                continue
            
            ticker = ticker_data.get("ticker")
            indicators = ticker_data.get("data", {})
            
            for indicator_name, indicator_data in indicators.items():
                if isinstance(indicator_data, dict) and "error" not in indicator_data:
                    # Extract date from indicator data
                    date = indicator_data.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
                    
                    # Create flattened record
                    record = {
                        "ticker": ticker,
                        "indicator": indicator_name,
                        "date": date,
                        "value": indicator_data.get("value"),
                        "parameters": indicator_data.get("parameters", {}),
                        "source": "alphavantage",
                        "ingested_at": datetime.utcnow().isoformat()
                    }
                    
                    records.append(record)
        
        return await fs_logger.write_technical_indicators_batch(records)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get handler statistics"""
        return self.stats