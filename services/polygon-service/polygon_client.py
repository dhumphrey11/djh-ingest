"""
Polygon API Client
Handles communication with Polygon API for news data
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import aiohttp
from shared.utils.retries import retry_with_backoff, RateLimitError


logger = logging.getLogger(__name__)


class PolygonError(Exception):
    """Custom exception for Polygon API errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class PolygonClient:
    """
    Async client for Polygon API
    Handles market-wide and company news
    """
    
    BASE_URL = "https://api.polygon.io"
    
    def __init__(self, api_key: str):
        """
        Initialize Polygon client
        
        Args:
            api_key: Polygon API key
        """
        if not api_key:
            raise ValueError("Polygon API key is required")
        
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
        
        # Rate limiting (Polygon free tier: 5 calls/minute)
        self.rate_limit_requests_per_minute = 5
        self.request_timestamps: List[datetime] = []
        
        logger.info("Polygon client initialized")
    
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
        """Check if we're hitting rate limits"""
        now = datetime.utcnow()
        
        # Clean old timestamps (older than 1 minute)
        cutoff_time = now - timedelta(minutes=1)
        self.request_timestamps = [
            ts for ts in self.request_timestamps 
            if ts > cutoff_time
        ]
        
        # Check per-minute limit
        if len(self.request_timestamps) >= self.rate_limit_requests_per_minute:
            raise RateLimitError(
                f"Per-minute rate limit ({self.rate_limit_requests_per_minute}) exceeded",
                retry_after=60
            )
    
    @retry_with_backoff(max_retries=3, base_delay=2.0, max_delay=60.0)
    async def _make_request(
        self, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make authenticated request to Polygon API"""
        self._check_rate_limit()
        
        url = f"{self.BASE_URL}{endpoint}"
        request_params = params or {}
        request_params["apikey"] = self.api_key
        
        start_time = datetime.utcnow()
        self.stats["requests_made"] += 1
        self.stats["last_request_time"] = start_time.isoformat()
        
        try:
            session = await self._get_session()
            
            logger.debug(f"Making request to {url}")
            
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
                        "Polygon API rate limit exceeded",
                        retry_after=retry_after
                    )
                
                # Get response data
                try:
                    data = await response.json()
                except Exception as e:
                    text = await response.text()
                    raise PolygonError(
                        f"Invalid JSON response: {e}. Response: {text[:200]}",
                        status_code=response.status
                    )
                
                # Handle API errors
                if response.status >= 400:
                    self.stats["requests_failed"] += 1
                    error_msg = f"Polygon API error {response.status}"
                    
                    if isinstance(data, dict):
                        if "error" in data:
                            error_msg += f": {data['error']}"
                        elif "message" in data:
                            error_msg += f": {data['message']}"
                        elif "status" in data and data["status"] == "ERROR":
                            error_msg += f": {data.get('error', 'Unknown error')}"
                    
                    raise PolygonError(
                        error_msg,
                        status_code=response.status,
                        response_data=data
                    )
                
                self.stats["requests_successful"] += 1
                logger.debug(f"Request successful in {duration_ms}ms")
                return data
                
        except (RateLimitError, PolygonError):
            raise
        except Exception as e:
            self.stats["requests_failed"] += 1
            logger.error(f"Request to {url} failed: {e}")
            raise PolygonError(f"Request failed: {str(e)}")
    
    async def health_check(self) -> bool:
        """Perform health check by making a minimal API call"""
        try:
            # Simple call to get market news
            await self._make_request("/v2/reference/news", {"limit": 1})
            return True
        except Exception as e:
            raise PolygonError(f"Health check failed: {str(e)}")
    
    async def fetch_company_news(
        self,
        tickers: List[str],
        published_date: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch company news for multiple tickers
        
        Args:
            tickers: List of ticker symbols
            published_date: Published date in YYYY-MM-DD format (optional)
            limit: Number of articles per ticker (optional)
        
        Returns:
            List of news data dictionaries per ticker
        """
        if not tickers:
            return []
        
        logger.info(f"Fetching company news for {len(tickers)} tickers")
        results = []
        
        # Process tickers sequentially to respect rate limits
        for ticker in tickers:
            try:
                news_data = await self._fetch_ticker_news(ticker, published_date, limit)
                results.append({
                    "ticker": ticker,
                    "data": news_data,
                    "count": len(news_data)
                })
            except Exception as e:
                logger.error(f"Failed to fetch news for {ticker}: {e}")
                results.append({
                    "ticker": ticker,
                    "error": str(e),
                    "data": []
                })
            
            # Rate limiting delay
            await asyncio.sleep(12)  # ~5 requests per minute
        
        return results
    
    async def _fetch_ticker_news(
        self,
        ticker: str,
        published_date: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Fetch news for a single ticker"""
        try:
            params = {
                "ticker": ticker,
                "limit": limit or 10
            }
            
            if published_date:
                params["published_utc"] = published_date
            
            data = await self._make_request("/v2/reference/news", params)
            
            if not isinstance(data, dict) or "results" not in data:
                raise PolygonError(f"Unexpected response format for ticker news: expected dict with 'results', got {type(data)}")
            
            articles = data.get("results", [])
            
            # Process news articles
            processed_articles = []
            for article in articles:
                try:
                    processed_article = {
                        "ticker": ticker,
                        "article_id": f"polygon_{article.get('id', datetime.utcnow().timestamp())}",
                        "title": article.get("title", ""),
                        "description": article.get("description", ""),
                        "url": article.get("article_url", ""),
                        "author": article.get("author", ""),
                        "published_utc": article.get("published_utc", ""),
                        "amp_url": article.get("amp_url"),
                        "image_url": article.get("image_url"),
                        "keywords": article.get("keywords", []),
                        "tickers": article.get("tickers", []),
                        "source": "polygon",
                        "ingested_at": datetime.utcnow().isoformat()
                    }
                    processed_articles.append(processed_article)
                except Exception as e:
                    logger.warning(f"Skipping invalid news article for {ticker}: {e}")
                    continue
            
            return processed_articles
            
        except PolygonError:
            raise
        except Exception as e:
            raise PolygonError(f"Failed to fetch news for {ticker}: {str(e)}")
    
    async def fetch_market_news(
        self,
        published_date: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch general market news
        
        Args:
            published_date: Published date in YYYY-MM-DD format (optional)
            limit: Number of articles to return (optional)
        
        Returns:
            List of market news articles
        """
        try:
            params = {
                "limit": limit or 20
            }
            
            if published_date:
                params["published_utc"] = published_date
            
            data = await self._make_request("/v2/reference/news", params)
            
            if not isinstance(data, dict) or "results" not in data:
                raise PolygonError(f"Unexpected response format for market news: expected dict with 'results', got {type(data)}")
            
            articles = data.get("results", [])
            
            # Process market news articles
            processed_articles = []
            for article in articles:
                try:
                    processed_article = {
                        "article_id": f"polygon_market_{article.get('id', datetime.utcnow().timestamp())}",
                        "ticker": None,  # Market news, no specific ticker
                        "title": article.get("title", ""),
                        "description": article.get("description", ""),
                        "url": article.get("article_url", ""),
                        "author": article.get("author", ""),
                        "published_utc": article.get("published_utc", ""),
                        "amp_url": article.get("amp_url"),
                        "image_url": article.get("image_url"),
                        "keywords": article.get("keywords", []),
                        "tickers": article.get("tickers", []),
                        "source": "polygon",
                        "ingested_at": datetime.utcnow().isoformat()
                    }
                    processed_articles.append(processed_article)
                except Exception as e:
                    logger.warning(f"Skipping invalid market news article: {e}")
                    continue
            
            return processed_articles
            
        except PolygonError:
            raise
        except Exception as e:
            raise PolygonError(f"Failed to fetch market news: {str(e)}")
    
    async def search_news(
        self,
        query: str,
        published_date: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Search news articles by keyword
        
        Args:
            query: Search query string
            published_date: Published date in YYYY-MM-DD format (optional)
            limit: Number of articles to return (optional)
        
        Returns:
            List of matching news articles
        """
        try:
            params = {
                "q": query,
                "limit": limit or 10
            }
            
            if published_date:
                params["published_utc"] = published_date
            
            data = await self._make_request("/v2/reference/news", params)
            
            if not isinstance(data, dict) or "results" not in data:
                raise PolygonError(f"Unexpected response format for news search: expected dict with 'results', got {type(data)}")
            
            articles = data.get("results", [])
            
            # Process search results
            processed_articles = []
            for article in articles:
                try:
                    processed_article = {
                        "article_id": f"polygon_search_{article.get('id', datetime.utcnow().timestamp())}",
                        "ticker": None,  # Search results may not have specific ticker
                        "title": article.get("title", ""),
                        "description": article.get("description", ""),
                        "url": article.get("article_url", ""),
                        "author": article.get("author", ""),
                        "published_utc": article.get("published_utc", ""),
                        "amp_url": article.get("amp_url"),
                        "image_url": article.get("image_url"),
                        "keywords": article.get("keywords", []),
                        "tickers": article.get("tickers", []),
                        "query": query,
                        "source": "polygon",
                        "ingested_at": datetime.utcnow().isoformat()
                    }
                    processed_articles.append(processed_article)
                except Exception as e:
                    logger.warning(f"Skipping invalid search result article: {e}")
                    continue
            
            return processed_articles
            
        except PolygonError:
            raise
        except Exception as e:
            raise PolygonError(f"Failed to search news: {str(e)}")
    
    async def get_trending_tickers(self) -> List[Dict[str, Any]]:
        """
        Get trending ticker symbols from recent news coverage
        
        Returns:
            List of trending tickers with mention counts
        """
        try:
            # Get recent market news
            data = await self._make_request("/v2/reference/news", {"limit": 50})
            
            if not isinstance(data, dict) or "results" not in data:
                return []
            
            articles = data.get("results", [])
            
            # Count ticker mentions
            ticker_counts = {}
            for article in articles:
                tickers = article.get("tickers", [])
                for ticker in tickers:
                    ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
            
            # Sort by mention count
            trending = [
                {
                    "ticker": ticker,
                    "mention_count": count,
                    "trend_score": count * 1.0  # Simple scoring, could be enhanced
                }
                for ticker, count in sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)
            ]
            
            return trending[:20]  # Top 20 trending tickers
            
        except PolygonError:
            raise
        except Exception as e:
            raise PolygonError(f"Failed to get trending tickers: {str(e)}")
    
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
                "per_minute_limit": self.rate_limit_requests_per_minute
            }
        }