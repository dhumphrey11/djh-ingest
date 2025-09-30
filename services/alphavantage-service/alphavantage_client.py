"""
AlphaVantage API Client
Handles communication with AlphaVantage API for technical indicators with advanced throttling
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import aiohttp
from shared.utils.retries import retry_with_backoff, RateLimitError


logger = logging.getLogger(__name__)


class AlphaVantageError(Exception):
    """Custom exception for AlphaVantage API errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class AlphaVantageClient:
    """
    Async client for AlphaVantage API with advanced rate limiting and throttling
    Handles technical indicators with intelligent request batching
    """
    
    BASE_URL = "https://www.alphavantage.co"
    
    # Default indicators to fetch
    DEFAULT_INDICATORS = [
        "RSI",      # Relative Strength Index
        "SMA",      # Simple Moving Average
        "EMA",      # Exponential Moving Average
        "MACD",     # MACD
        "BBANDS",   # Bollinger Bands
        "STOCH",    # Stochastic Oscillator
        "ADX"       # Average Directional Index
    ]
    
    def __init__(self, api_key: str):
        """
        Initialize AlphaVantage client
        
        Args:
            api_key: AlphaVantage API key
        """
        if not api_key:
            raise ValueError("AlphaVantage API key is required")
        
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None
        self.stats = {
            "requests_made": 0,
            "requests_successful": 0,
            "requests_failed": 0,
            "total_duration_ms": 0,
            "rate_limits_hit": 0,
            "last_request_time": None,
            "indicators_fetched": 0
        }
        
        # Advanced rate limiting (AlphaVantage free tier: 5 calls/minute, 500 calls/day)
        self.rate_limit_requests_per_minute = 5
        self.rate_limit_requests_per_day = 500
        self.request_timestamps: List[datetime] = []
        
        # Throttling state
        self.current_delay = 12.0  # Start with 12 seconds between requests
        self.max_delay = 60.0
        self.min_delay = 10.0
        self.adaptive_throttling = True
        
        logger.info("AlphaVantage client initialized with adaptive throttling")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=60, connect=15)  # Longer timeout for AlphaVantage
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
        """Advanced rate limiting check with daily limits"""
        now = datetime.utcnow()
        
        # Clean old timestamps
        minute_cutoff = now - timedelta(minutes=1)
        day_cutoff = now - timedelta(days=1)
        
        self.request_timestamps = [
            ts for ts in self.request_timestamps 
            if ts > day_cutoff
        ]
        
        # Check per-minute limit
        recent_requests = [ts for ts in self.request_timestamps if ts > minute_cutoff]
        if len(recent_requests) >= self.rate_limit_requests_per_minute:
            raise RateLimitError(
                f"Per-minute rate limit ({self.rate_limit_requests_per_minute}) exceeded",
                retry_after=60
            )
        
        # Check daily limit
        if len(self.request_timestamps) >= self.rate_limit_requests_per_day:
            oldest_request = min(self.request_timestamps)
            retry_after = int((oldest_request + timedelta(days=1) - now).total_seconds())
            raise RateLimitError(
                f"Daily rate limit ({self.rate_limit_requests_per_day}) exceeded",
                retry_after=max(retry_after, 3600)
            )
    
    def _adjust_throttling(self, success: bool, response_time_ms: int):
        """Adjust throttling based on response success and timing"""
        if not self.adaptive_throttling:
            return
        
        if success:
            # Success - slightly reduce delay
            if response_time_ms < 2000:  # Fast response
                self.current_delay = max(self.min_delay, self.current_delay * 0.95)
            elif response_time_ms > 10000:  # Slow response
                self.current_delay = min(self.max_delay, self.current_delay * 1.1)
        else:
            # Failure - increase delay significantly
            self.current_delay = min(self.max_delay, self.current_delay * 1.5)
        
        logger.debug(f"Adjusted throttling delay to {self.current_delay:.2f}s")
    
    @retry_with_backoff(max_retries=3, base_delay=5.0, max_delay=120.0)
    async def _make_request(
        self, 
        function: str, 
        symbol: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make authenticated request to AlphaVantage API with advanced throttling"""
        self._check_rate_limit()
        
        url = f"{self.BASE_URL}/query"
        request_params = params or {}
        request_params.update({
            "function": function,
            "symbol": symbol,
            "apikey": self.api_key
        })
        
        start_time = datetime.utcnow()
        self.stats["requests_made"] += 1
        self.stats["last_request_time"] = start_time.isoformat()
        
        try:
            session = await self._get_session()
            
            logger.debug(f"Making request to {url} for {function}/{symbol} with delay {self.current_delay:.2f}s")
            
            async with session.get(url, params=request_params) as response:
                duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                self.stats["total_duration_ms"] += duration_ms
                
                # Track request timestamp for rate limiting
                self.request_timestamps.append(start_time)
                
                # Handle rate limiting
                if response.status == 429:
                    self.stats["rate_limits_hit"] += 1
                    self._adjust_throttling(False, duration_ms)
                    retry_after = int(response.headers.get("Retry-After", 60))
                    raise RateLimitError(
                        "AlphaVantage API rate limit exceeded",
                        retry_after=retry_after
                    )
                
                # Get response data
                try:
                    data = await response.json()
                except Exception as e:
                    text = await response.text()
                    raise AlphaVantageError(
                        f"Invalid JSON response: {e}. Response: {text[:200]}",
                        status_code=response.status
                    )
                
                # Handle API-level errors (AlphaVantage specific)
                if isinstance(data, dict):
                    # Check for API limit messages
                    error_message = data.get("Error Message", "")
                    note = data.get("Note", "")
                    
                    if "API call frequency" in error_message or "API call frequency" in note:
                        self.stats["rate_limits_hit"] += 1
                        self._adjust_throttling(False, duration_ms)
                        raise RateLimitError(
                            "AlphaVantage API call frequency limit exceeded",
                            retry_after=60
                        )
                    
                    if error_message:
                        raise AlphaVantageError(f"API Error: {error_message}")
                    
                    if note and "higher API call frequency" in note:
                        logger.warning(f"AlphaVantage API usage warning: {note}")
                
                # Handle HTTP errors
                if response.status >= 400:
                    self.stats["requests_failed"] += 1
                    self._adjust_throttling(False, duration_ms)
                    error_msg = f"AlphaVantage API HTTP error {response.status}"
                    
                    raise AlphaVantageError(
                        error_msg,
                        status_code=response.status,
                        response_data=data
                    )
                
                self.stats["requests_successful"] += 1
                self._adjust_throttling(True, duration_ms)
                logger.debug(f"Request successful in {duration_ms}ms")
                
                # Apply throttling delay after successful request
                await asyncio.sleep(self.current_delay)
                
                return data
                
        except (RateLimitError, AlphaVantageError):
            raise
        except Exception as e:
            self.stats["requests_failed"] += 1
            self._adjust_throttling(False, 30000)  # Assume slow failure
            logger.error(f"Request to {url} failed: {e}")
            raise AlphaVantageError(f"Request failed: {str(e)}")
    
    async def health_check(self) -> bool:
        """Perform health check by making a minimal API call"""
        try:
            # Simple call to get RSI for AAPL
            await self._make_request("RSI", "AAPL", {"interval": "daily", "time_period": 14})
            return True
        except Exception as e:
            raise AlphaVantageError(f"Health check failed: {str(e)}")
    
    async def fetch_technical_indicators(
        self,
        tickers: List[str],
        indicators: Optional[List[str]] = None,
        interval: str = "daily",
        time_period: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch technical indicators for multiple tickers
        
        Args:
            tickers: List of ticker symbols
            indicators: List of indicators to fetch (or None for defaults)
            interval: Time interval (daily, weekly, monthly)
            time_period: Time period for applicable indicators
        
        Returns:
            List of indicator data dictionaries per ticker
        """
        if not tickers:
            return []
        
        indicators_to_fetch = indicators or self.DEFAULT_INDICATORS
        
        logger.info(f"Fetching {len(indicators_to_fetch)} indicators for {len(tickers)} tickers")
        results = []
        
        # Process tickers sequentially with aggressive throttling
        for ticker in tickers:
            try:
                ticker_indicators = await self._fetch_ticker_indicators(
                    ticker, indicators_to_fetch, interval, time_period
                )
                results.append({
                    "ticker": ticker,
                    "data": ticker_indicators,
                    "indicators_count": len(ticker_indicators)
                })
                self.stats["indicators_fetched"] += len(ticker_indicators)
            except Exception as e:
                logger.error(f"Failed to fetch indicators for {ticker}: {e}")
                results.append({
                    "ticker": ticker,
                    "error": str(e),
                    "data": {}
                })
        
        return results
    
    async def _fetch_ticker_indicators(
        self,
        ticker: str,
        indicators: List[str],
        interval: str,
        time_period: Optional[int]
    ) -> Dict[str, Any]:
        """Fetch all indicators for a single ticker"""
        ticker_data = {}
        
        for indicator in indicators:
            try:
                indicator_data = await self.fetch_single_indicator(
                    ticker, indicator, interval, time_period
                )
                ticker_data[indicator] = indicator_data
            except Exception as e:
                logger.error(f"Failed to fetch {indicator} for {ticker}: {e}")
                ticker_data[indicator] = {"error": str(e)}
        
        return ticker_data
    
    async def fetch_single_indicator(
        self,
        ticker: str,
        indicator: str,
        interval: str = "daily",
        time_period: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Fetch a single technical indicator for a ticker
        
        Args:
            ticker: Stock symbol
            indicator: Technical indicator name
            interval: Time interval
            time_period: Time period for the indicator
        
        Returns:
            Processed indicator data
        """
        params = {"interval": interval}
        
        # Add time_period for indicators that support it
        if time_period and indicator in ["RSI", "SMA", "EMA", "WMA", "ADX", "CCI", "ROC"]:
            params["time_period"] = time_period
        elif indicator in ["RSI"]:
            params["time_period"] = time_period or 14
        elif indicator in ["SMA", "EMA"]:
            params["time_period"] = time_period or 20
        elif indicator in ["ADX"]:
            params["time_period"] = time_period or 14
        
        # Special parameters for specific indicators
        if indicator == "BBANDS":
            params.update({
                "time_period": time_period or 20,
                "nbdevup": 2,
                "nbdevdn": 2,
                "matype": 0
            })
        elif indicator == "MACD":
            params.update({
                "fastperiod": 12,
                "slowperiod": 26,
                "signalperiod": 9
            })
        elif indicator == "STOCH":
            params.update({
                "fastkperiod": 14,
                "slowkperiod": 3,
                "slowdperiod": 3,
                "slowkmatype": 0,
                "slowdmatype": 0
            })
        
        try:
            data = await self._make_request(indicator, ticker, params)
            
            # Process the response based on indicator type
            processed_data = self._process_indicator_response(indicator, data)
            
            return {
                "ticker": ticker,
                "indicator": indicator,
                "interval": interval,
                "parameters": params,
                "data": processed_data,
                "source": "alphavantage",
                "ingested_at": datetime.utcnow().isoformat()
            }
            
        except AlphaVantageError:
            raise
        except Exception as e:
            raise AlphaVantageError(f"Failed to fetch {indicator} for {ticker}: {str(e)}")
    
    def _process_indicator_response(self, indicator: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process AlphaVantage indicator response into standardized format"""
        if not isinstance(data, dict):
            raise AlphaVantageError(f"Invalid response format for {indicator}")
        
        # Find the time series data key
        time_series_key = None
        for key in data.keys():
            if "Time Series" in key or indicator in key:
                time_series_key = key
                break
        
        if not time_series_key:
            # No time series found, might be an error
            raise AlphaVantageError(f"No time series data found for {indicator}")
        
        time_series = data[time_series_key]
        if not time_series:
            raise AlphaVantageError(f"Empty time series data for {indicator}")
        
        # Get the most recent data point
        latest_date = max(time_series.keys())
        latest_data = time_series[latest_date]
        
        # Process based on indicator type
        processed_data = {
            "date": latest_date,
            "raw_data": latest_data
        }
        
        # Standardize field names
        if indicator == "RSI":
            processed_data["value"] = float(latest_data.get("RSI", 0))
        elif indicator in ["SMA", "EMA", "WMA"]:
            processed_data["value"] = float(latest_data.get(indicator, 0))
        elif indicator == "MACD":
            processed_data["value"] = {
                "macd": float(latest_data.get("MACD", 0)),
                "signal": float(latest_data.get("MACD_Signal", 0)),
                "histogram": float(latest_data.get("MACD_Hist", 0))
            }
        elif indicator == "BBANDS":
            processed_data["value"] = {
                "upper_band": float(latest_data.get("Real Upper Band", 0)),
                "middle_band": float(latest_data.get("Real Middle Band", 0)),
                "lower_band": float(latest_data.get("Real Lower Band", 0))
            }
        elif indicator == "STOCH":
            processed_data["value"] = {
                "slow_k": float(latest_data.get("SlowK", 0)),
                "slow_d": float(latest_data.get("SlowD", 0))
            }
        elif indicator == "ADX":
            processed_data["value"] = float(latest_data.get("ADX", 0))
        else:
            # Generic processing for other indicators
            processed_data["value"] = latest_data
        
        return processed_data
    
    def get_throttling_recommendations(self) -> Dict[str, Any]:
        """Get throttling recommendations based on current usage"""
        recent_requests = len([
            ts for ts in self.request_timestamps 
            if ts > datetime.utcnow() - timedelta(minutes=1)
        ])
        
        daily_requests = len(self.request_timestamps)
        
        recommendations = {
            "current_delay": self.current_delay,
            "recommended_batch_size": max(1, min(5, self.rate_limit_requests_per_minute - recent_requests)),
            "daily_quota_used": round(daily_requests / self.rate_limit_requests_per_day * 100, 1),
            "status": "healthy"
        }
        
        if daily_requests > self.rate_limit_requests_per_day * 0.8:
            recommendations["status"] = "approaching_limit"
            recommendations["recommendation"] = "Reduce request frequency to stay within daily limit"
        elif recent_requests > self.rate_limit_requests_per_minute * 0.8:
            recommendations["status"] = "approaching_rate_limit"
            recommendations["recommendation"] = "Wait before making more requests"
        else:
            recommendations["recommendation"] = "Normal operation"
        
        return recommendations
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
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
                "recent_requests": len([
                    ts for ts in self.request_timestamps 
                    if ts > datetime.utcnow() - timedelta(minutes=1)
                ]),
                "per_minute_limit": self.rate_limit_requests_per_minute,
                "daily_requests": len(self.request_timestamps),
                "per_day_limit": self.rate_limit_requests_per_day,
                "current_throttle_delay": self.current_delay
            },
            "throttling": {
                "adaptive_enabled": self.adaptive_throttling,
                "current_delay": self.current_delay,
                "min_delay": self.min_delay,
                "max_delay": self.max_delay
            }
        }