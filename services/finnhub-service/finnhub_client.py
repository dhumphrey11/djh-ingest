"""
Finnhub API Client
Handles communication with Finnhub API for quotes, news, fundamentals, earnings, insider transactions, analyst ratings
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import aiohttp
from shared.utils.retries import retry_with_backoff, RateLimitError


logger = logging.getLogger(__name__)


class FinnhubError(Exception):
    """Custom exception for Finnhub API errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class FinnhubClient:
    """
    Async client for Finnhub API
    Handles quotes, company news, fundamentals, earnings, insider transactions, analyst ratings
    """

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str):
        """
        Initialize Finnhub client

        Args:
            api_key: Finnhub API token
        """
        if not api_key:
            raise ValueError("Finnhub API key is required")

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

        # Rate limiting (Finnhub free tier: 60 calls/minute)
        self.rate_limit_requests_per_minute = 60
        self.request_timestamps: List[datetime] = []

        logger.info("Finnhub client initialized")

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

    @retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=30.0)
    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make authenticated request to Finnhub API"""
        self._check_rate_limit()

        url = f"{self.BASE_URL}{endpoint}"
        request_params = params or {}
        request_params["token"] = self.api_key

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
                        "Finnhub API rate limit exceeded",
                        retry_after=retry_after
                    )

                # Get response data
                try:
                    data = await response.json()
                except Exception as e:
                    text = await response.text()
                    raise FinnhubError(
                        f"Invalid JSON response: {e}. Response: {text[:200]}",
                        status_code=response.status
                    )

                # Handle API errors
                if response.status >= 400:
                    self.stats["requests_failed"] += 1
                    error_msg = f"Finnhub API error {response.status}"
                    if isinstance(data, dict):
                        if "error" in data:
                            error_msg += f": {data['error']}"
                        elif "message" in data:
                            error_msg += f": {data['message']}"

                    raise FinnhubError(
                        error_msg,
                        status_code=response.status,
                        response_data=data
                    )

                self.stats["requests_successful"] += 1
                logger.debug(f"Request successful in {duration_ms}ms")
                return data

        except (RateLimitError, FinnhubError):
            raise
        except Exception as e:
            self.stats["requests_failed"] += 1
            logger.error(f"Request to {url} failed: {e}")
            raise FinnhubError(f"Request failed: {str(e)}")

    async def health_check(self) -> bool:
        """Perform health check by making a minimal API call"""
        try:
            # Simple call to get quote for a common stock
            await self._make_request("/quote", {"symbol": "AAPL"})
            return True
        except Exception as e:
            raise FinnhubError(f"Health check failed: {str(e)}")

    async def fetch_quotes(self, tickers: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch real-time quotes for multiple tickers

        Args:
            tickers: List of ticker symbols

        Returns:
            List of quote data dictionaries
        """
        if not tickers:
            return []

        logger.info(f"Fetching quotes for {len(tickers)} tickers")
        results = []

        # Process tickers with some concurrency but respect rate limits
        batch_size = 5
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            batch_tasks = []

            for ticker in batch:
                task = self._fetch_ticker_quote(ticker)
                batch_tasks.append(task)

            # Execute batch concurrently
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            for ticker, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to fetch quote for {ticker}: {result}")
                    results.append({
                        "ticker": ticker,
                        "error": str(result),
                        "data": None
                    })
                else:
                    results.append({
                        "ticker": ticker,
                        "data": result
                    })

            # Small delay between batches
            if i + batch_size < len(tickers):
                await asyncio.sleep(0.2)

        logger.info(f"Completed fetching quotes for {len(tickers)} tickers")
        return results

    async def _fetch_ticker_quote(self, ticker: str) -> Dict[str, Any]:
        """Fetch quote for a single ticker"""
        try:
            data = await self._make_request("/quote", {"symbol": ticker})

            # Validate response
            required_fields = ["c", "h", "l", "o", "pc", "t"]
            if not all(field in data for field in required_fields):
                raise FinnhubError(f"Missing required fields in quote response for {ticker}")

            # Process and normalize
            processed_data = {
                "ticker": ticker,
                "current_price": float(data.get("c", 0)),
                "change": float(data.get("d", 0)),
                "percent_change": float(data.get("dp", 0)),
                "high": float(data.get("h", 0)),
                "low": float(data.get("l", 0)),
                "open": float(data.get("o", 0)),
                "previous_close": float(data.get("pc", 0)),
                "timestamp": int(data.get("t", 0)),
                "source": "finnhub",
                "ingested_at": datetime.utcnow().isoformat()
            }

            return processed_data

        except FinnhubError:
            raise
        except Exception as e:
            raise FinnhubError(f"Failed to fetch quote for {ticker}: {str(e)}")

    async def fetch_company_news(
        self,
        tickers: List[str],
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch company news for multiple tickers

        Args:
            tickers: List of ticker symbols
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)

        Returns:
            List of news data dictionaries
        """
        if not tickers:
            return []

        # Set default dates if not provided
        if not to_date:
            to_date = datetime.utcnow().strftime("%Y-%m-%d")
        if not from_date:
            # Default to last 7 days
            from_dt = datetime.utcnow() - timedelta(days=7)
            from_date = from_dt.strftime("%Y-%m-%d")

        logger.info(f"Fetching company news for {len(tickers)} tickers from {from_date} to {to_date}")
        results = []

        # Process tickers sequentially to respect rate limits
        for ticker in tickers:
            try:
                news_data = await self._fetch_ticker_news(ticker, from_date, to_date)
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
            await asyncio.sleep(0.5)

        return results

    async def _fetch_ticker_news(
        self,
        ticker: str,
        from_date: str,
        to_date: str
    ) -> List[Dict[str, Any]]:
        """Fetch news for a single ticker"""
        try:
            data = await self._make_request("/company-news", {
                "symbol": ticker,
                "from": from_date,
                "to": to_date
            })

            if not isinstance(data, list):
                raise FinnhubError(f"Unexpected response format for news: expected list, got {type(data)}")

            # Process news articles
            processed_articles = []
            for article in data:
                try:
                    processed_article = {
                        "ticker": ticker,
                        "article_id": f"finnhub_{article.get('id', datetime.utcnow().timestamp())}",
                        "headline": article.get("headline", ""),
                        "summary": article.get("summary", ""),
                        "url": article.get("url", ""),
                        "original_source": article.get("source", ""),
                        "category": article.get("category", "general"),
                        "datetime": int(article.get("datetime", 0)),
                        "image": article.get("image"),
                        "related": article.get("related"),
                        "source": "finnhub",
                        "ingested_at": datetime.utcnow().isoformat()
                    }
                    processed_articles.append(processed_article)
                except Exception as e:
                    logger.warning(f"Skipping invalid news article for {ticker}: {e}")
                    continue

            return processed_articles

        except FinnhubError:
            raise
        except Exception as e:
            raise FinnhubError(f"Failed to fetch news for {ticker}: {str(e)}")

    async def fetch_fundamentals(self, tickers: List[str]) -> List[Dict[str, Any]]:
        """Fetch basic fundamentals for multiple tickers"""
        if not tickers:
            return []

        logger.info(f"Fetching fundamentals for {len(tickers)} tickers")
        results = []

        for ticker in tickers:
            try:
                fundamentals_data = await self._fetch_ticker_fundamentals(ticker)
                results.append({
                    "ticker": ticker,
                    "data": fundamentals_data
                })
            except Exception as e:
                logger.error(f"Failed to fetch fundamentals for {ticker}: {e}")
                results.append({
                    "ticker": ticker,
                    "error": str(e),
                    "data": None
                })

            await asyncio.sleep(0.5)  # Rate limiting

        return results

    async def _fetch_ticker_fundamentals(self, ticker: str) -> Dict[str, Any]:
        """Fetch fundamentals for a single ticker"""
        try:
            data = await self._make_request("/stock/metric", {
                "symbol": ticker,
                "metric": "all"
            })

            # Extract key metrics from the response
            metric_data = data.get("metric", {})

            processed_data = {
                "ticker": ticker,
                "report_date": datetime.utcnow().strftime(f"%Y-Q{((datetime.utcnow().month - 1) // 3 + 1)}"),
                "market_cap": metric_data.get("marketCapitalization"),
                "shares_outstanding": metric_data.get("shareOutstanding"),
                "pe_ratio": metric_data.get("peBasicExclExtraTTM"),
                "pb_ratio": metric_data.get("pbAnnual"),
                "roe": metric_data.get("roeRfy"),
                "roa": metric_data.get("roaRfy"),
                "debt_to_equity": metric_data.get("totalDebt/totalEquityAnnual"),
                "current_ratio": metric_data.get("currentRatioAnnual"),
                "source": "finnhub",
                "ingested_at": datetime.utcnow().isoformat()
            }

            return processed_data

        except FinnhubError:
            raise
        except Exception as e:
            raise FinnhubError(f"Failed to fetch fundamentals for {ticker}: {str(e)}")

    async def fetch_earnings_calendar(self, tickers: List[str]) -> List[Dict[str, Any]]:
        """Fetch earnings calendar for multiple tickers"""
        if not tickers:
            return []

        logger.info(f"Fetching earnings calendar for {len(tickers)} tickers")
        results = []

        # Finnhub earnings calendar endpoint doesn't filter by symbol,
        # so we'll get the general calendar and filter
        try:
            from_date = datetime.utcnow().strftime("%Y-%m-%d")
            to_date = (datetime.utcnow() + timedelta(days=90)).strftime("%Y-%m-%d")

            data = await self._make_request("/calendar/earnings", {
                "from": from_date,
                "to": to_date
            })

            # Filter earnings for requested tickers
            earnings_list = data.get("earningsCalendar", [])

            for ticker in tickers:
                ticker_earnings = [
                    e for e in earnings_list
                    if e.get("symbol", "").upper() == ticker.upper()
                ]

                processed_earnings = []
                for earning in ticker_earnings:
                    try:
                        processed_earning = {
                            "ticker": ticker,
                            "earnings_date": earning.get("date", ""),
                            "quarter": earning.get("quarter"),
                            "year": earning.get("year"),
                            "eps_estimate": earning.get("epsEstimate"),
                            "eps_actual": earning.get("epsActual"),
                            "revenue_estimate": earning.get("revenueEstimate"),
                            "revenue_actual": earning.get("revenueActual"),
                            "source": "finnhub",
                            "ingested_at": datetime.utcnow().isoformat()
                        }
                        processed_earnings.append(processed_earning)
                    except Exception as e:
                        logger.warning(f"Skipping invalid earnings record for {ticker}: {e}")
                        continue

                results.append({
                    "ticker": ticker,
                    "data": processed_earnings,
                    "count": len(processed_earnings)
                })

        except Exception as e:
            logger.error(f"Failed to fetch earnings calendar: {e}")
            for ticker in tickers:
                results.append({
                    "ticker": ticker,
                    "error": str(e),
                    "data": []
                })

        return results

    async def fetch_insider_transactions(self, tickers: List[str]) -> List[Dict[str, Any]]:
        """Fetch insider transactions for multiple tickers"""
        if not tickers:
            return []

        logger.info(f"Fetching insider transactions for {len(tickers)} tickers")
        results = []

        for ticker in tickers:
            try:
                insider_data = await self._fetch_ticker_insider_transactions(ticker)
                results.append({
                    "ticker": ticker,
                    "data": insider_data,
                    "count": len(insider_data)
                })
            except Exception as e:
                logger.error(f"Failed to fetch insider transactions for {ticker}: {e}")
                results.append({
                    "ticker": ticker,
                    "error": str(e),
                    "data": []
                })

            await asyncio.sleep(0.5)  # Rate limiting

        return results

    async def _fetch_ticker_insider_transactions(self, ticker: str) -> List[Dict[str, Any]]:
        """Fetch insider transactions for a single ticker"""
        try:
            # Get last 3 months of data
            from_date = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")
            to_date = datetime.utcnow().strftime("%Y-%m-%d")

            data = await self._make_request("/stock/insider-transactions", {
                "symbol": ticker,
                "from": from_date,
                "to": to_date
            })

            if not isinstance(data, dict) or "data" not in data:
                return []

            transactions = data.get("data", [])
            processed_transactions = []

            for transaction in transactions:
                try:
                    processed_transaction = {
                        "ticker": ticker,
                        "transaction_id": f"tx_{transaction.get('filingDate', '')}_{len(processed_transactions)}",
                        "person_name": transaction.get("name", ""),
                        "share": int(transaction.get("share", 0)),
                        "change": int(transaction.get("change", 0)),
                        "filing_date": transaction.get("filingDate", ""),
                        "transaction_date": transaction.get("transactionDate", ""),
                        "transaction_price": float(transaction.get("transactionPrice", 0)) if transaction.get("transactionPrice") else None,
                        "transaction_code": transaction.get("transactionCode", ""),
                        "source": "finnhub",
                        "ingested_at": datetime.utcnow().isoformat()
                    }
                    processed_transactions.append(processed_transaction)
                except Exception as e:
                    logger.warning(f"Skipping invalid insider transaction for {ticker}: {e}")
                    continue

            return processed_transactions

        except FinnhubError:
            raise
        except Exception as e:
            raise FinnhubError(f"Failed to fetch insider transactions for {ticker}: {str(e)}")

    async def fetch_analyst_ratings(self, tickers: List[str]) -> List[Dict[str, Any]]:
        """Fetch analyst ratings for multiple tickers"""
        if not tickers:
            return []

        logger.info(f"Fetching analyst ratings for {len(tickers)} tickers")
        results = []

        for ticker in tickers:
            try:
                rating_data = await self._fetch_ticker_analyst_ratings(ticker)
                results.append({
                    "ticker": ticker,
                    "data": rating_data
                })
            except Exception as e:
                logger.error(f"Failed to fetch analyst ratings for {ticker}: {e}")
                results.append({
                    "ticker": ticker,
                    "error": str(e),
                    "data": None
                })

            await asyncio.sleep(0.5)  # Rate limiting

        return results

    async def _fetch_ticker_analyst_ratings(self, ticker: str) -> Dict[str, Any]:
        """Fetch analyst ratings for a single ticker"""
        try:
            data = await self._make_request("/stock/recommendation", {"symbol": ticker})

            if not isinstance(data, list) or len(data) == 0:
                raise FinnhubError(f"No analyst ratings found for {ticker}")

            # Get the most recent rating
            latest_rating = data[0]

            processed_data = {
                "ticker": ticker,
                "date": latest_rating.get("period", ""),
                "buy": int(latest_rating.get("buy", 0)),
                "hold": int(latest_rating.get("hold", 0)),
                "sell": int(latest_rating.get("sell", 0)),
                "strong_buy": int(latest_rating.get("strongBuy", 0)),
                "strong_sell": int(latest_rating.get("strongSell", 0)),
                "source": "finnhub",
                "ingested_at": datetime.utcnow().isoformat()
            }

            return processed_data

        except FinnhubError:
            raise
        except Exception as e:
            raise FinnhubError(f"Failed to fetch analyst ratings for {ticker}: {str(e)}")

    async def fetch_market_news(self, category: str = "general") -> List[Dict[str, Any]]:
        """Fetch general market news"""
        try:
            data = await self._make_request("/news", {"category": category})

            if not isinstance(data, list):
                raise FinnhubError(f"Unexpected response format for market news: expected list, got {type(data)}")

            processed_articles = []
            for article in data:
                try:
                    processed_article = {
                        "article_id": f"finnhub_market_{article.get('id', datetime.utcnow().timestamp())}",
                        "ticker": None,  # Market news, no specific ticker
                        "headline": article.get("headline", ""),
                        "summary": article.get("summary", ""),
                        "url": article.get("url", ""),
                        "original_source": article.get("source", ""),
                        "category": category,
                        "datetime": int(article.get("datetime", 0)),
                        "image": article.get("image"),
                        "related": article.get("related"),
                        "source": "finnhub",
                        "ingested_at": datetime.utcnow().isoformat()
                    }
                    processed_articles.append(processed_article)
                except Exception as e:
                    logger.warning(f"Skipping invalid market news article: {e}")
                    continue

            return processed_articles

        except FinnhubError:
            raise
        except Exception as e:
            raise FinnhubError(f"Failed to fetch market news: {str(e)}")

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
