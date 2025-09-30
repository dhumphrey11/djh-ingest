"""
Firestore logger utility for writing raw responses and processed data
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union

from google.cloud import firestore
from google.cloud.firestore import AsyncClient, AsyncDocumentReference
from shared.models import RawLogEntry, RawLogRequest, RawLogResponse, ScopeType
from shared.utils.env import get_config


logger = logging.getLogger(__name__)
config = get_config()


class FirestoreLogger:
    """
    Handles logging raw API responses and processed data to Firestore
    """
    
    def __init__(self):
        """Initialize Firestore client"""
        if config.firestore_emulator_host:
            # Use emulator for local development
            import os
            os.environ["FIRESTORE_EMULATOR_HOST"] = config.firestore_emulator_host
            logger.info(f"Using Firestore emulator at {config.firestore_emulator_host}")
        
        self.client = AsyncClient(project=config.gcp_project)
        self.stats = {
            "raw_logs_written": 0,
            "processed_docs_written": 0,
            "batch_writes": 0,
            "write_errors": 0,
            "last_write_time": None
        }
        
        logger.info("FirestoreLogger initialized")
    
    def close(self):
        """Close the Firestore client"""
        if self.client and hasattr(self.client, 'close'):
            self.client.close()
    
    def generate_log_id(self) -> str:
        """Generate a unique ID for raw log entries"""
        return str(uuid.uuid4())
    
    async def log_raw(
        self,
        source: str,
        api_name: str,
        scope: ScopeType,
        request_params: Dict[str, Any],
        response_data: Any,
        status_code: int,
        latency_ms: int,
        job_id: Optional[str] = None,
        tickers: Optional[List[str]] = None,
        error_flag: bool = False
    ) -> str:
        """
        Log raw API response to Firestore
        
        Args:
            source: Data source (tiingo, finnhub, polygon, alphavantage)
            api_name: API endpoint name
            scope: Request scope
            request_params: Request parameters (sensitive data should be removed)
            response_data: Raw response data
            status_code: HTTP status code
            latency_ms: Request latency in milliseconds
            job_id: Optional job ID for tracking
            tickers: List of tickers requested
            error_flag: Whether this was an error response
        
        Returns:
            Log entry ID
        """
        try:
            # Generate unique log ID
            log_id = self.generate_log_id()
            
            # Create document path - must have even number of path segments
            today = datetime.utcnow().strftime("%Y-%m-%d")
            doc_path = f"api_usage_logs/{log_id}"
            
            # Remove sensitive data from params
            clean_params = self._clean_sensitive_data(request_params)
            
            # Create log entry
            log_entry = {
                "request": {
                    "url": clean_params.get("url", ""),
                    "params": {k: v for k, v in clean_params.items() if k != "url"},
                    "headers": clean_params.get("headers", {}),
                    "scope": scope.value if isinstance(scope, ScopeType) else scope,
                    "timestamp": datetime.utcnow().isoformat()
                },
                "response": {
                    "data": response_data,
                    "status_code": status_code,
                    "latency_ms": latency_ms,
                    "error_flag": error_flag
                },
                "metadata": {
                    "job_id": job_id,
                    "tickers_requested": tickers,
                    "source": source,
                    "api_name": api_name,
                    "date": today,
                    "log_id": log_id,
                    "ingested_at": datetime.utcnow().isoformat()
                }
            }
            
            # Write to Firestore
            doc_ref = self.client.document(doc_path)
            await doc_ref.set(log_entry)
            
            self.stats["raw_logs_written"] += 1
            self.stats["last_write_time"] = datetime.utcnow().isoformat()
            
            logger.debug(f"Raw log written: {doc_path}")
            return log_id
            
        except Exception as e:
            self.stats["write_errors"] += 1
            logger.error(f"Failed to write raw log: {e}")
            # Don't raise - logging failures shouldn't break the pipeline
            return ""
    
    async def write_processed(
        self,
        collection_name: str,
        doc_id: str,
        doc_body: Dict[str, Any],
        merge: bool = False
    ) -> bool:
        """
        Write processed data to Firestore collection
        
        Args:
            collection_name: Target collection name
            doc_id: Document ID
            doc_body: Document data
            merge: Whether to merge with existing document
        
        Returns:
            True if successful, False otherwise
        """
        try:
            doc_ref = self.client.document(f"{collection_name}/{doc_id}")
            
            if merge:
                await doc_ref.set(doc_body, merge=True)
            else:
                await doc_ref.set(doc_body)
            
            self.stats["processed_docs_written"] += 1
            self.stats["last_write_time"] = datetime.utcnow().isoformat()
            
            logger.debug(f"Processed document written: {collection_name}/{doc_id}")
            return True
            
        except Exception as e:
            self.stats["write_errors"] += 1
            logger.error(f"Failed to write processed document {collection_name}/{doc_id}: {e}")
            return False
    
    async def write_batch(
        self,
        writes: List[Dict[str, Any]]
    ) -> int:
        """
        Write multiple documents in a batch
        
        Args:
            writes: List of write operations, each containing:
                - collection: Collection name
                - doc_id: Document ID
                - data: Document data
                - merge: Whether to merge (optional)
        
        Returns:
            Number of successful writes
        """
        if not writes:
            return 0
        
        try:
            batch = self.client.batch()
            
            for write_op in writes:
                collection_name = write_op["collection"]
                doc_id = write_op["doc_id"]
                doc_data = write_op["data"]
                merge = write_op.get("merge", False)
                
                doc_ref = self.client.document(f"{collection_name}/{doc_id}")
                
                if merge:
                    batch.set(doc_ref, doc_data, merge=True)
                else:
                    batch.set(doc_ref, doc_data)
            
            # Commit batch
            await batch.commit()
            
            self.stats["batch_writes"] += 1
            self.stats["processed_docs_written"] += len(writes)
            self.stats["last_write_time"] = datetime.utcnow().isoformat()
            
            logger.info(f"Batch write completed: {len(writes)} documents")
            return len(writes)
            
        except Exception as e:
            self.stats["write_errors"] += 1
            logger.error(f"Failed to write batch: {e}")
            return 0
    
    async def write_daily_prices_batch(
        self,
        price_data: List[Dict[str, Any]]
    ) -> int:
        """
        Write daily price data in batches for better performance
        
        Args:
            price_data: List of daily price records
        
        Returns:
            Number of successful writes
        """
        if not price_data:
            return 0
        
        writes = []
        for record in price_data:
            ticker = record.get("ticker")
            date = record.get("date")
            if not ticker or not date:
                continue
            
            doc_id = f"{ticker}_{date}"
            writes.append({
                "collection": "prices_daily",
                "doc_id": doc_id,
                "data": record,
                "merge": False
            })
        
        return await self.write_batch(writes)
    
    async def write_news_batch(
        self,
        news_data: List[Dict[str, Any]]
    ) -> int:
        """
        Write news articles in batches
        
        Args:
            news_data: List of news article records
        
        Returns:
            Number of successful writes
        """
        if not news_data:
            return 0
        
        writes = []
        for record in news_data:
            article_id = record.get("article_id")
            ticker = record.get("ticker", "market")
            
            if not article_id:
                continue
            
            doc_id = f"{ticker}_{article_id}"
            writes.append({
                "collection": "news_articles",
                "doc_id": doc_id,
                "data": record,
                "merge": False
            })
        
        return await self.write_batch(writes)
    
    async def write_technical_indicators_batch(
        self,
        indicators_data: List[Dict[str, Any]]
    ) -> int:
        """
        Write technical indicators in batches
        
        Args:
            indicators_data: List of technical indicator records
        
        Returns:
            Number of successful writes
        """
        if not indicators_data:
            return 0
        
        writes = []
        for record in indicators_data:
            ticker = record.get("ticker")
            indicator = record.get("indicator")
            date = record.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
            
            if not ticker or not indicator:
                continue
            
            doc_id = f"{ticker}_{indicator}_{date}"
            writes.append({
                "collection": "technical_indicators",
                "doc_id": doc_id,
                "data": record,
                "merge": True  # Allow updates for technical indicators
            })
        
        return await self.write_batch(writes)
    
    async def get_watchlist_symbols(self) -> List[str]:
        """
        Get the complete watchlist from Firestore
        
        Returns:
            List of ticker symbols
        """
        try:
            doc_ref = self.client.document("react_universeSymbols/config")
            doc = await doc_ref.get()
            
            if not doc.exists:
                logger.warning("Universe symbols config not found")
                return []
            
            data = doc.to_dict()
            if not data:
                logger.warning("Universe symbols config document is empty")
                return []
            symbols = data.get("symbols", [])
            
            # Extract ticker symbols
            tickers = []
            for symbol in symbols:
                if isinstance(symbol, dict) and "ticker" in symbol:
                    ticker = symbol["ticker"]
                    # Only include active symbols
                    if symbol.get("active", True):
                        tickers.append(ticker)
                elif isinstance(symbol, str):
                    tickers.append(symbol)
            
            logger.info(f"Retrieved {len(tickers)} symbols from watchlist")
            return tickers
            
        except Exception as e:
            logger.error(f"Failed to get watchlist symbols: {e}")
            return []
    
    async def get_active_symbols(self) -> List[str]:
        """
        Get currently active positions from Firestore
        
        Returns:
            List of active ticker symbols
        """
        try:
            doc_ref = self.client.document("react_activeSymbols/positions")
            doc = await doc_ref.get()
            
            if not doc.exists:
                logger.warning("Active symbols config not found")
                return []
            
            data = doc.to_dict()
            if not data:
                logger.warning("Active symbols positions document is empty")
                return []
            positions = data.get("positions", [])
            
            # Extract ticker symbols from positions
            tickers = []
            for position in positions:
                if isinstance(position, dict) and "ticker" in position:
                    ticker = position["ticker"]
                    # Only include positions with quantity > 0
                    if position.get("quantity", 0) > 0:
                        tickers.append(ticker)
            
            logger.info(f"Retrieved {len(tickers)} active symbols")
            return tickers
            
        except Exception as e:
            logger.error(f"Failed to get active symbols: {e}")
            return []
    
    async def get_index_symbols(self) -> List[str]:
        """
        Get market index symbols from Firestore
        
        Returns:
            List of index symbols
        """
        try:
            doc_ref = self.client.document("react_universeSymbols/config")
            doc = await doc_ref.get()
            
            if not doc.exists:
                return ["SPY", "QQQ", "IWM", "DIA"]  # Default indices
            
            data = doc.to_dict()
            if not data:
                logger.warning("Universe symbols config document is empty for indices")
                return ["SPY", "QQQ", "IWM", "DIA"]  # Default fallback
            indices = data.get("indices", [])
            
            # Extract index symbols
            symbols = []
            for index in indices:
                if isinstance(index, dict) and "symbol" in index:
                    symbols.append(index["symbol"])
                elif isinstance(index, str):
                    symbols.append(index)
            
            logger.info(f"Retrieved {len(symbols)} index symbols")
            return symbols
            
        except Exception as e:
            logger.error(f"Failed to get index symbols: {e}")
            return ["SPY", "QQQ", "IWM", "DIA"]  # Default fallback
    
    def _clean_sensitive_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove sensitive data from request parameters before logging
        
        Args:
            params: Original request parameters
        
        Returns:
            Cleaned parameters
        """
        clean_params = params.copy()
        
        # List of sensitive keys to remove or mask
        sensitive_keys = [
            "token", "apikey", "api_key", "key", "password", "secret",
            "authorization", "auth", "bearer"
        ]
        
        for key in list(clean_params.keys()):
            if key.lower() in sensitive_keys:
                clean_params[key] = "[REDACTED]"
            elif isinstance(clean_params[key], dict):
                clean_params[key] = self._clean_sensitive_data(clean_params[key])
        
        # Also clean headers if present
        if "headers" in clean_params and isinstance(clean_params["headers"], dict):
            headers = clean_params["headers"].copy()
            for key in list(headers.keys()):
                if key.lower() in ["authorization", "x-api-key", "api-key"]:
                    headers[key] = "[REDACTED]"
            clean_params["headers"] = headers
        
        return clean_params
    
    def get_stats(self) -> Dict[str, Any]:
        """Get logging statistics"""
        return {
            **self.stats,
            "client_project": config.gcp_project,
            "emulator_mode": config.firestore_emulator_host is not None
        }


# Global instance
_logger_instance: Optional[FirestoreLogger] = None


async def get_firestore_logger() -> FirestoreLogger:
    """Get or create the global FirestoreLogger instance"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = FirestoreLogger()
    return _logger_instance