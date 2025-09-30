"""
Service client for orchestrating calls to all microservices
"""

import logging
import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
import aiohttp
import google.auth
import google.auth.transport.requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from shared.models import ServiceRequest, ServiceResponse, ScopeType
from shared.utils.env import get_config
from shared.utils.retries import retry_with_backoff

logger = logging.getLogger(__name__)
config = get_config()


class ServiceClient:
    """
    Client for orchestrating calls to all microservices
    """

    def __init__(self):
        # Use Cloud Run URLs - these are the actual service URLs we need to authenticate to
        self.base_urls = {
            "tiingo": "https://tiingo-service-974427192502.us-central1.run.app",
            "finnhub": "https://finnhub-service-974427192502.us-central1.run.app",
            "polygon": "https://polygon-service-974427192502.us-central1.run.app",
            "alphavantage": "https://alphavantage-service-974427192502.us-central1.run.app"
        }
        self.session: Optional[aiohttp.ClientSession] = None
        self.timeout = aiohttp.ClientTimeout(total=300)  # 5 minutes
        self._credentials = None
        self._id_token_cache = {}  # Cache ID tokens by target URL

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self.session

    async def close(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _get_id_token(self, target_url: str) -> Optional[str]:
        """
        Get an OIDC ID token for authenticating to Cloud Run services

        Args:
            target_url: The URL of the target service

        Returns:
            ID token string or None if authentication fails
        """
        try:
            # Check cache first
            if target_url in self._id_token_cache:
                return self._id_token_cache[target_url]

            # Get default credentials if needed (though we use metadata service)
            if self._credentials is None:
                self._credentials, project = google.auth.default()

            # Create a request object for getting the ID token
            auth_req = google.auth.transport.requests.Request()

            # Use metadata service approach for all credential types in Cloud Run
            # This is the most reliable approach for getting ID tokens
            try:
                import urllib.request
                import urllib.parse

                # Request ID token from metadata service
                metadata_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
                audience = target_url

                req = urllib.request.Request(
                    f"{metadata_url}?audience={urllib.parse.quote(audience)}&format=full",
                    headers={"Metadata-Flavor": "Google"}
                )

                with urllib.request.urlopen(req) as response:
                    id_token = response.read().decode('utf-8')
                    self._id_token_cache[target_url] = id_token
                    return id_token

            except Exception as e:
                logger.warning(f"Failed to get ID token from metadata service: {e}")
                return None

        except Exception as e:
            logger.warning(f"Failed to get OIDC token for {target_url}: {e}")
            return None

    def _clear_token_cache(self):
        """Clear the ID token cache to force token refresh"""
        self._id_token_cache.clear()

    # ===========================================
    # TIINGO SERVICE CALLS
    # ===========================================

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def fetch_tiingo_daily_prices(
        self,
        tickers: List[str],
        job_id: str,
        run_time: datetime
    ) -> Dict[str, Any]:
        """Fetch daily prices from Tiingo service"""
        url = f"{self.base_urls['tiingo']}/fetch"

        request_data = ServiceRequest(
            scope=ScopeType.ENTIRE_WATCHLIST,
            tickers=tickers,
            job_id=job_id,
            run_time=run_time
        )

        return await self._make_request("POST", url, request_data)

    # ===========================================
    # FINNHUB SERVICE CALLS
    # ===========================================

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def fetch_finnhub_quotes(
        self,
        tickers: List[str],
        job_id: str,
        run_time: datetime
    ) -> Dict[str, Any]:
        """Fetch intraday quotes from Finnhub service"""
        url = f"{self.base_urls['finnhub']}/fetch"

        request_data = ServiceRequest(
            scope=ScopeType.ACTIVE_SYMBOLS,
            tickers=tickers,
            job_id=job_id,
            run_time=run_time
        )

        return await self._make_request("POST", url, request_data)

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def fetch_finnhub_company_news(
        self,
        tickers: List[str],
        job_id: str,
        run_time: datetime
    ) -> Dict[str, Any]:
        """Fetch company news from Finnhub service"""
        url = f"{self.base_urls['finnhub']}/fetch/news"

        request_data = ServiceRequest(
            scope=ScopeType.ENTIRE_WATCHLIST,
            tickers=tickers,
            job_id=job_id,
            run_time=run_time
        )

        return await self._make_request("POST", url, request_data)

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def fetch_finnhub_fundamentals(
        self,
        tickers: List[str],
        job_id: str,
        run_time: datetime
    ) -> Dict[str, Any]:
        """Fetch fundamentals from Finnhub service"""
        url = f"{self.base_urls['finnhub']}/fetch/fundamentals"

        request_data = ServiceRequest(
            scope=ScopeType.ENTIRE_WATCHLIST,
            tickers=tickers,
            job_id=job_id,
            run_time=run_time
        )

        return await self._make_request("POST", url, request_data)

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def fetch_finnhub_earnings(
        self,
        tickers: List[str],
        job_id: str,
        run_time: datetime
    ) -> Dict[str, Any]:
        """Fetch earnings from Finnhub service"""
        url = f"{self.base_urls['finnhub']}/fetch/earnings"

        request_data = ServiceRequest(
            scope=ScopeType.ENTIRE_WATCHLIST,
            tickers=tickers,
            job_id=job_id,
            run_time=run_time
        )

        return await self._make_request("POST", url, request_data)

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def fetch_finnhub_insider_transactions(
        self,
        tickers: List[str],
        job_id: str,
        run_time: datetime
    ) -> Dict[str, Any]:
        """Fetch insider transactions from Finnhub service"""
        url = f"{self.base_urls['finnhub']}/fetch/insider-transactions"

        request_data = ServiceRequest(
            scope=ScopeType.ENTIRE_WATCHLIST,
            tickers=tickers,
            job_id=job_id,
            run_time=run_time
        )

        return await self._make_request("POST", url, request_data)

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def fetch_finnhub_analyst_ratings(
        self,
        tickers: List[str],
        job_id: str,
        run_time: datetime
    ) -> Dict[str, Any]:
        """Fetch analyst ratings from Finnhub service"""
        url = f"{self.base_urls['finnhub']}/fetch/analyst-ratings"

        request_data = ServiceRequest(
            scope=ScopeType.ENTIRE_WATCHLIST,
            tickers=tickers,
            job_id=job_id,
            run_time=run_time
        )

        return await self._make_request("POST", url, request_data)

    # ===========================================
    # POLYGON SERVICE CALLS
    # ===========================================

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def fetch_polygon_company_news(
        self,
        tickers: List[str],
        job_id: str,
        run_time: datetime
    ) -> Dict[str, Any]:
        """Fetch company news from Polygon service"""
        url = f"{self.base_urls['polygon']}/fetch"

        request_data = ServiceRequest(
            scope=ScopeType.ENTIRE_WATCHLIST,
            tickers=tickers,
            job_id=job_id,
            run_time=run_time
        )

        return await self._make_request("POST", url, request_data)

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def fetch_polygon_market_news(
        self,
        job_id: str,
        run_time: datetime
    ) -> Dict[str, Any]:
        """Fetch market news from Polygon service"""
        url = f"{self.base_urls['polygon']}/fetch/market"

        request_data = ServiceRequest(
            scope=ScopeType.NONE,
            tickers=[],
            job_id=job_id,
            run_time=run_time
        )

        return await self._make_request("POST", url, request_data)

    # ===========================================
    # ALPHAVANTAGE SERVICE CALLS
    # ===========================================

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def fetch_alphavantage_technical_indicators(
        self,
        tickers: List[str],
        job_id: str,
        run_time: datetime
    ) -> Dict[str, Any]:
        """Fetch technical indicators from AlphaVantage service"""
        url = f"{self.base_urls['alphavantage']}/fetch"

        request_data = ServiceRequest(
            scope=ScopeType.ENTIRE_WATCHLIST,
            tickers=tickers,
            job_id=job_id,
            run_time=run_time
        )

        return await self._make_request("POST", url, request_data)

    # ===========================================
    # HEALTH CHECKS
    # ===========================================

    async def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """Health check all services"""
        results = {}

        # Create tasks for parallel health checks
        tasks = []
        for service_name, base_url in self.base_urls.items():
            task = asyncio.create_task(
                self._health_check_service(service_name, base_url),
                name=f"health_check_{service_name}"
            )
            tasks.append(task)

        # Wait for all health checks to complete
        health_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for i, result in enumerate(health_results):
            service_name = list(self.base_urls.keys())[i]
            if isinstance(result, Exception):
                results[service_name] = {
                    "status": "error",
                    "error": str(result),
                    "healthy": False
                }
            else:
                results[service_name] = result

        return results

    async def _health_check_service(self, service_name: str, base_url: str) -> Dict[str, Any]:
        """Health check individual service"""
        url = f"{base_url}/health"
        start_time = datetime.utcnow()

        try:
            session = await self._get_session()
            async with session.get(url) as response:
                response_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

                if response.status == 200:
                    data = await response.json()
                    return {
                        "status": "ok",
                        "healthy": True,
                        "response_time_ms": response_time_ms,
                        "details": data
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "healthy": False,
                        "response_time_ms": response_time_ms,
                        "status_code": response.status,
                        "error": await response.text()
                    }
        except Exception as e:
            response_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return {
                "status": "error",
                "healthy": False,
                "response_time_ms": response_time_ms,
                "error": str(e)
            }

    # ===========================================
    # HELPER METHODS
    # ===========================================

    async def _make_request(self, method: str, url: str, data: Any) -> Dict[str, Any]:
        """Make HTTP request to service"""
        session = await self._get_session()

        # Handle both dict and Pydantic model data
        if hasattr(data, 'model_dump_json'):
            # Pydantic model - serialize to JSON string then parse back to dict
            json_str = data.model_dump_json()
            json_data = json.loads(json_str)
        else:
            json_data = data

        # Prepare headers with OIDC authentication
        headers = {
            "Content-Type": "application/json"
        }

        # Add OIDC ID token for Cloud Run authentication
        id_token = self._get_id_token(url)
        if id_token:
            headers["Authorization"] = f"Bearer {id_token}"
        else:
            logger.warning(f"No OIDC token available for {url}, proceeding without authentication")

        try:
            async with session.request(method, url, json=json_data, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status in (401, 403) and id_token and url in self._id_token_cache:
                    # Clear cached token and retry once
                    logger.info(f"Authentication failed for {url}, clearing token cache and retrying")
                    self._id_token_cache.pop(url, None)

                    # Get fresh token and retry
                    fresh_token = self._get_id_token(url)
                    if fresh_token:
                        headers["Authorization"] = f"Bearer {fresh_token}"
                        async with session.request(method, url, json=json_data, headers=headers) as retry_response:
                            if retry_response.status == 200:
                                return await retry_response.json()
                            else:
                                retry_error_text = await retry_response.text()
                                logger.error(f"Service request failed after retry: {method} {url} - {retry_response.status}: {retry_error_text}")
                                return {
                                    "status": "error",
                                    "error": f"HTTP {retry_response.status}: {retry_error_text}",
                                    "status_code": retry_response.status
                                }

                    # If we couldn't get a fresh token, fall through to error handling

                error_text = await response.text()
                logger.error(f"Service request failed: {method} {url} - {response.status}: {error_text}")
                return {
                    "status": "error",
                    "error": f"HTTP {response.status}: {error_text}",
                    "status_code": response.status
                }
        except asyncio.TimeoutError:
            logger.error(f"Service request timeout: {method} {url}")
            return {
                "status": "error",
                "error": "Request timeout",
                "status_code": 408
            }
        except Exception as e:
            logger.error(f"Service request exception: {method} {url} - {e}")
            return {
                "status": "error",
                "error": str(e),
                "status_code": 500
            }

    def get_service_urls(self) -> Dict[str, str]:
        """Get configured service URLs"""
        return self.base_urls.copy()