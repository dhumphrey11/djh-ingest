"""
Shared Pydantic models for the ingestion pipeline
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime as dt
from enum import Enum


class ScopeType(str, Enum):
    """Defines the scope of data ingestion"""
    ENTIRE_WATCHLIST = "entire_watchlist"
    ACTIVE_SYMBOLS = "active_symbols"
    INDICES = "indices"
    NONE = "none"


class DataSource(str, Enum):
    """Data provider sources"""
    TIINGO = "tiingo"
    FINNHUB = "finnhub"
    POLYGON = "polygon"
    ALPHAVANTAGE = "alphavantage"


class SchedulerRequest(BaseModel):
    """Request payload from Cloud Scheduler"""
    scope: ScopeType
    job: str
    run_time: Optional[dt] = None
    tickers: Optional[List[str]] = None


class ServiceRequest(BaseModel):
    """Request to individual microservices"""
    tickers: List[str]
    scope: ScopeType
    job_id: str
    run_time: dt


class ServiceResponse(BaseModel):
    """Response from individual microservices"""
    status: str
    fetched: int
    data: Optional[List[Dict[str, Any]]] = None
    errors: Optional[List[str]] = None
    duration_ms: Optional[int] = None


class SchedulerResponse(BaseModel):
    """Response to Cloud Scheduler requests"""
    status: str = Field(..., description="Status of the job execution: ok, error")
    job: str = Field(..., description="Job name that was executed")
    message: str = Field(..., description="Human readable message")
    data: Optional[Dict[str, Any]] = Field(None, description="Job execution details")
    timestamp: Optional[dt] = Field(default_factory=dt.utcnow)


class RawLogRequest(BaseModel):
    """Request metadata for raw logging"""
    url: str
    params: Dict[str, Any] = {}
    headers: Dict[str, str] = {}  # No secrets
    scope: ScopeType
    timestamp: dt


class RawLogResponse(BaseModel):
    """Response metadata for raw logging"""
    data: Dict[str, Any]
    status_code: int
    latency_ms: int
    error_flag: bool = False


class RawLogEntry(BaseModel):
    """Complete raw log entry"""
    request: RawLogRequest
    response: RawLogResponse
    metadata: Dict[str, Any] = {}


# Tiingo Models

class TiingoDailyPrice(BaseModel):
    """Tiingo daily price data"""
    ticker: str
    date: str
    close: float
    high: float
    low: float
    open: float
    volume: int
    adj_close: float = Field(alias="adjClose")
    adj_high: float = Field(alias="adjHigh")
    adj_low: float = Field(alias="adjLow")
    adj_open: float = Field(alias="adjOpen")
    adj_volume: int = Field(alias="adjVolume")
    div_cash: float = Field(alias="divCash", default=0.0)
    split_factor: float = Field(alias="splitFactor", default=1.0)
    ingested_at: dt = Field(default_factory=dt.utcnow)


# Finnhub Models

class FinnhubQuote(BaseModel):
    """Finnhub real-time quote"""
    ticker: str
    current_price: float = Field(alias="c")
    change: float = Field(alias="d")
    percent_change: float = Field(alias="dp")
    high: float = Field(alias="h")
    low: float = Field(alias="l")
    open: float = Field(alias="o")
    previous_close: float = Field(alias="pc")
    timestamp: int = Field(alias="t")
    ingested_at: dt = Field(default_factory=dt.utcnow)


class FinnhubNews(BaseModel):
    """Finnhub news article"""
    ticker: Optional[str] = None
    article_id: str = Field(alias="id")
    headline: str
    summary: str
    url: str
    source: str
    category: str
    datetime: int
    image: Optional[str] = None
    related: Optional[str] = None
    ingested_at: dt = Field(default_factory=dt.utcnow)


class FinnhubFundamentals(BaseModel):
    """Finnhub company fundamentals"""
    ticker: str
    report_date: str
    market_cap: Optional[float] = Field(alias="marketCap")
    shares_outstanding: Optional[float] = Field(alias="shareOutstanding")
    pe_ratio: Optional[float] = Field(alias="peBasicExclExtraTTM")
    pb_ratio: Optional[float] = Field(alias="pbAnnual")
    roe: Optional[float] = Field(alias="roeRfy")
    roa: Optional[float] = Field(alias="roaRfy")
    debt_to_equity: Optional[float] = Field(alias="totalDebt/totalEquityAnnual")
    current_ratio: Optional[float] = Field(alias="currentRatioAnnual")
    ingested_at: dt = Field(default_factory=dt.utcnow)


class FinnhubEarnings(BaseModel):
    """Finnhub earnings calendar"""
    ticker: str = Field(alias="symbol")
    earnings_date: str = Field(alias="date")
    quarter: Optional[int] = None
    year: Optional[int] = None
    eps_estimate: Optional[float] = Field(alias="epsEstimate")
    eps_actual: Optional[float] = Field(alias="epsActual")
    revenue_estimate: Optional[float] = Field(alias="revenueEstimate")
    revenue_actual: Optional[float] = Field(alias="revenueActual")
    ingested_at: dt = Field(default_factory=dt.utcnow)


class FinnhubInsiderTransaction(BaseModel):
    """Finnhub insider transaction"""
    ticker: str = Field(alias="symbol")
    transaction_id: str = Field(default_factory=lambda: str(dt.utcnow().timestamp()))
    person_name: str = Field(alias="name")
    share: int
    change: int
    filing_date: str = Field(alias="filingDate")
    transaction_date: str = Field(alias="transactionDate")
    transaction_price: Optional[float] = Field(alias="transactionPrice")
    transaction_code: str = Field(alias="transactionCode")
    ingested_at: dt = Field(default_factory=dt.utcnow)


class FinnhubAnalystRating(BaseModel):
    """Finnhub analyst recommendation"""
    ticker: str = Field(alias="symbol")
    date: str = Field(alias="period")
    buy: int
    hold: int
    sell: int
    strong_buy: int = Field(alias="strongBuy")
    strong_sell: int = Field(alias="strongSell")
    ingested_at: dt = Field(default_factory=dt.utcnow)


# Polygon Models

class PolygonNews(BaseModel):
    """Polygon news article"""
    ticker: Optional[str] = None
    article_id: str = Field(alias="id")
    title: str
    description: str
    url: str
    author: str
    published_utc: str
    amp_url: Optional[str] = None
    image_url: Optional[str] = None
    keywords: List[str] = []
    tickers: List[str] = []
    ingested_at: dt = Field(default_factory=dt.utcnow)


# AlphaVantage Models

class TechnicalIndicator(BaseModel):
    """Generic technical indicator"""
    ticker: str
    indicator: str
    date: str
    value: Union[float, Dict[str, float]]  # Single value or multiple (e.g., MACD)
    parameters: Dict[str, Any] = {}
    ingested_at: dt = Field(default_factory=dt.utcnow)


# Index/Economic Models

class MarketIndex(BaseModel):
    """Market index data"""
    symbol: str
    date: str
    close: float
    high: float
    low: float
    open: float
    volume: Optional[int] = None
    change_percent: Optional[float] = None
    ingested_at: dt = Field(default_factory=dt.utcnow)


class EconomicIndicator(BaseModel):
    """Economic indicator data"""
    indicator: str
    date: str
    value: float
    unit: Optional[str] = None
    frequency: Optional[str] = None  # daily, weekly, monthly, etc.
    source: Optional[str] = None
    ingested_at: dt = Field(default_factory=dt.utcnow)


# Signal Models (for frontend API)

class TechnicalSignal(BaseModel):
    """Combined technical indicator signal"""
    ticker: str
    date: str
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    rsi: Optional[float] = None
    macd: Optional[Dict[str, float]] = None
    bollinger_bands: Optional[Dict[str, float]] = None
    signal_strength: Optional[str] = None  # strong_buy, buy, hold, sell, strong_sell
    last_updated: dt


class NewsSentiment(BaseModel):
    """News sentiment analysis"""
    ticker: str
    sentiment_score: float  # -1 to 1
    article_count: int
    timeframe: str  # 24h, 7d, 30d
    latest_headline: Optional[str] = None
    last_updated: dt


class LatestSignals(BaseModel):
    """Combined signals for frontend"""
    ticker: str
    technical: Optional[TechnicalSignal] = None
    news: Optional[NewsSentiment] = None
    price: Optional[FinnhubQuote] = None
    last_updated: dt
