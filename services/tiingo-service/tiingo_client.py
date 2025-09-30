"""
Tiingo API Client
Handles communication with Tiingo API for EOD daily prices
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import aiohttp
from shared.utils.retries import retry_with_backoff, RateLimitError


logger = logging.getLogger(__name__)


class TiingoError(Exception):
    """Custom exception for Tiingo API errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class TiingoClient:
    """
    Async client for Tiingo API
    Handles daily EOD prices, supported tickers, and rate limiting
    """
    
    BASE_URL = "https://api.tiingo.com"
    
    def __init__(self, api_key: str):
        """
        Initialize Tiingo client
        
        Args:
            api_key: Tiingo API key
        """
        if not api_key:
            raise ValueError("Tiingo API key is required")
        
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None
        self.stats = {
            "requests_made": 0,
            "requests_successful": 0,
            "requests_failed": 0,
            "total_duration_ms": 0,
            "rate_limits_hit": 0,
            "last_request_time": None
        }
        
        # Rate limiting (Tiingo allows 1000 requests/hour for free tier)
        self.rate_limit_requests_per_hour = 1000
        self.rate_limit_requests_per_minute = 50  # Conservative estimate
        self.request_timestamps: List[datetime] = []
        
        logger.info("Tiingo client initialized")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "User-Agent": "djh-ingest/1.0",
                    "Accept": "application/json"
                }
            )
        return self.session
    
    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    def _check_rate_limit(self):
        """
        Check if we're hitting rate limits
        
        Raises:
            RateLimitError: If rate limit would be exceeded
        """
        now = datetime.utcnow()
        
        # Clean old timestamps (older than 1 hour)
        cutoff_time = now - timedelta(hours=1)
        self.request_timestamps = [
            ts for ts in self.request_timestamps 
            if ts > cutoff_time
        ]
        
        # Check hourly limit
        if len(self.request_timestamps) >= self.rate_limit_requests_per_hour:
            oldest_request = min(self.request_timestamps)
            retry_after = int((oldest_request + timedelta(hours=1) - now).total_seconds())
            raise RateLimitError(
                f"Hourly rate limit ({self.rate_limit_requests_per_hour}) exceeded",
                retry_after=max(retry_after, 60)
            )
        
        # Check per-minute limit
        minute_cutoff = now - timedelta(minutes=1)
        recent_requests = [ts for ts in self.request_timestamps if ts > minute_cutoff]
        if len(recent_requests) >= self.rate_limit_requests_per_minute:
            raise RateLimitError(
                f"Per-minute rate limit ({self.rate_limit_requests_per_minute}) exceeded",
                retry_after=60
            )
    
    @retry_with_backoff(max_retries=3, base_delay=2.0, max_delay=30.0)
    async def _make_request(
        self, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make authenticated request to Tiingo API
        
        Args:
            endpoint: API endpoint (without base URL)
            params: Query parameters
        
        Returns:
            JSON response data
            
        Raises:
            TiingoError: On API errors
            RateLimitError: On rate limit exceeded
        """
        self._check_rate_limit()
        
        url = f"{self.BASE_URL}{endpoint}"
        request_params = params or {}
        request_params["token"] = self.api_key
        
        start_time = datetime.utcnow()
        self.stats["requests_made"] += 1
        self.stats["last_request_time"] = start_time.isoformat()
        
        try:
            session = await self._get_session()
            
            logger.debug(f"Making request to {url} with params: {request_params}")
            
            async with session.get(url, params=request_params) as response:
                duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                self.stats["total_duration_ms"] += duration_ms
                
                # Track request timestamp for rate limiting
                self.request_timestamps.append(start_time)
                
                # Handle rate limiting
                if response.status == 429:
                    self.stats["rate_limits_hit"] += 1
                    retry_after = int(response.headers.get("Retry-After", 60))
                    raise RateLimitError(
                        "Tiingo API rate limit exceeded",
                        retry_after=retry_after
                    )
                
                # Get response data
                try:
                    data = await response.json()
                except Exception as e:
                    text = await response.text()
                    raise TiingoError(
                        f"Invalid JSON response: {e}. Response: {text[:200]}",
                        status_code=response.status
                    )
                
                # Handle API errors
                if response.status >= 400:
                    self.stats["requests_failed"] += 1
                    error_msg = f"Tiingo API error {response.status}"
                    if isinstance(data, dict) and "detail" in data:
                        error_msg += f": {data['detail']}"
                    elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict) and "detail" in data[0]:
                        error_msg += f": {data[0]['detail']}"
                    else:
                        error_msg += f": {data}"
                    
                    raise TiingoError(
                        error_msg,
                        status_code=response.status,
                        response_data=data
                    )
                
                self.stats["requests_successful"] += 1
                logger.debug(f"Request successful in {duration_ms}ms")
                return data
                
        except (RateLimitError, TiingoError):
            raise
        except Exception as e:
            self.stats["requests_failed"] += 1
            logger.error(f"Request to {url} failed: {e}")
            raise TiingoError(f"Request failed: {str(e)}")
    
    async def health_check(self) -> bool:
        """
        Perform health check by making a minimal API call
        
        Returns:
            True if API is accessible
            
        Raises:
            TiingoError: If health check fails
        """
        try:
            # Simple call to get supported tickers (limited response)
            await self._make_request("/tiingo/utilities/search?query=AAPL")
            return True
        except Exception as e:
            raise TiingoError(f"Health check failed: {str(e)}")
    
    async def get_supported_tickers(self) -> List[str]:
        """
        Get list of supported tickers
        
        Returns:
            List of ticker symbols
            
        Note: This is a simplified implementation. 
        Tiingo doesn't have a direct "all tickers" endpoint.
        In practice, you'd maintain your own list or use their search API.
        """
        try:
            # For now, return a common list of tickers
            # In production, this would be maintained separately or cached
            common_tickers = [
                "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "TSLA", "META", "NVDA",
                "BRK.B", "JNJ", "UNH", "XOM", "JPM", "PG", "CVX", "HD", "MA",
                "PFE", "KO", "ABBV", "BAC", "AVGO", "PEP", "COST", "TMO", "WMT"
            ]
            
            logger.info(f"Returning {len(common_tickers)} supported tickers")
            return common_tickers
            
        except Exception as e:
            raise TiingoError(f"Failed to get supported tickers: {str(e)}")
    
    async def fetch_daily_prices(
        self,
        tickers: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch daily EOD prices for multiple tickers
        
        Args:
            tickers: List of ticker symbols
            start_date: Start date in YYYY-MM-DD format (optional)
            end_date: End date in YYYY-MM-DD format (optional)
        
        Returns:
            List of ticker data dictionaries
        """
        if not tickers:
            return []
        
        # Set default dates if not provided
        if not end_date:
            end_date = datetime.utcnow().strftime("%Y-%m-%d")
        if not start_date:
            # Default to last 30 days if no start date provided
            start_dt = datetime.utcnow() - timedelta(days=30)
            start_date = start_dt.strftime("%Y-%m-%d")
        
        logger.info(f"Fetching daily prices for {len(tickers)} tickers from {start_date} to {end_date}")
        
        results = []
        
        # Process tickers in batches to respect rate limits
        batch_size = 5  # Conservative batch size
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            batch_tasks = []
            
            for ticker in batch:
                task = self._fetch_ticker_daily_prices(ticker, start_date, end_date)
                batch_tasks.append(task)
            
            # Execute batch concurrently
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for ticker, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to fetch data for {ticker}: {result}")
                    results.append({
                        "ticker": ticker,
                        "error": str(result),
                        "data": None
                    })
                else:
                    results.append({
                        "ticker": ticker,
                        "data": result,
                        "count": len(result) if result else 0
                    })
            
            # Small delay between batches to be polite
            if i + batch_size < len(tickers):
                await asyncio.sleep(0.5)
        
        logger.info(f"Completed fetching data for {len(tickers)} tickers")
        return results
    
    async def _fetch_ticker_daily_prices(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch daily prices for a single ticker
        
        Args:
            ticker: Ticker symbol
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        
        Returns:
            List of daily price records
        """
        endpoint = f"/tiingo/daily/{ticker}/prices"
        params = {
            "startDate": start_date,
            "endDate": end_date,
            "format": "json"
        }
        
        try:
            data = await self._make_request(endpoint, params)
            
            # Tiingo returns array of price records
            if not isinstance(data, list):
                raise TiingoError(f"Unexpected response format for {ticker}: expected list, got {type(data)}")
            
            # Process and normalize the data
            processed_data = []
            for record in data:
                try:
                    processed_record = {
                        "ticker": ticker,
                        "date": record.get("date", "").split("T")[0],  # Extract date part
                        "open": float(record.get("open", 0)),
                        "high": float(record.get("high", 0)),
                        "low": float(record.get("low", 0)),
                        "close": float(record.get("close", 0)),
                        "volume": int(record.get("volume", 0)),
                        "adj_open": float(record.get("adjOpen", record.get("open", 0))),
                        "adj_high": float(record.get("adjHigh", record.get("high", 0))),
                        "adj_low": float(record.get("adjLow", record.get("low", 0))),
                        "adj_close": float(record.get("adjClose", record.get("close", 0))),
                        "adj_volume": int(record.get("adjVolume", record.get("volume", 0))),
                        "div_cash": float(record.get("divCash", 0.0)),
                        "split_factor": float(record.get("splitFactor", 1.0)),
                        "source": "tiingo",
                        "ingested_at": datetime.utcnow().isoformat()
                    }
                    processed_data.append(processed_record)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Skipping invalid record for {ticker}: {e}")
                    continue
            
            return processed_data
            
        except TiingoError:
            raise
        except Exception as e:
            raise TiingoError(f"Failed to fetch daily prices for {ticker}: {str(e)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get client statistics
        
        Returns:
            Dictionary of client stats
        """
        avg_duration = 0
        if self.stats["requests_successful"] > 0:
            avg_duration = self.stats["total_duration_ms"] / self.stats["requests_successful"]
        
        return {
            **self.stats,
            "average_duration_ms": round(avg_duration, 2),
            "success_rate": round(
                self.stats["requests_successful"] / max(self.stats["requests_made"], 1) * 100, 
                2
            ),
            "active_session": self.session is not None and not self.session.closed,
            "rate_limit_status": {
                "hourly_requests": len([
                    ts for ts in self.request_timestamps 
                    if ts > datetime.utcnow() - timedelta(hours=1)
                ]),
                "hourly_limit": self.rate_limit_requests_per_hour,
                "recent_requests": len([
                    ts for ts in self.request_timestamps 
                    if ts > datetime.utcnow() - timedelta(minutes=1)
                ]),
                "per_minute_limit": self.rate_limit_requests_per_minute
            }
        }