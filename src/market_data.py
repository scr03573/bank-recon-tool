"""
Unified market data provider integrating Intrinio and yfinance.

Provides real-time and historical market data for vendor validation,
economic context, and transaction verification.

Data Sources:
- Intrinio: Premium financial data (company fundamentals, real-time quotes)
- yfinance: Free market data (stock prices, indices, historical data)
- FRED: Economic indicators (rates, yields, inflation)
"""
import os
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
import warnings

import pandas as pd

# Suppress warnings
warnings.filterwarnings("ignore", category=FutureWarning)
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

logger = logging.getLogger(__name__)


class DataSource(Enum):
    """Available market data sources."""
    INTRINIO = "intrinio"
    YFINANCE = "yfinance"
    FRED = "fred"


class DataPriority(Enum):
    """Priority for data source selection."""
    INTRINIO_FIRST = "intrinio_first"  # Use Intrinio, fallback to yfinance
    YFINANCE_FIRST = "yfinance_first"  # Use yfinance, fallback to Intrinio
    INTRINIO_ONLY = "intrinio_only"
    YFINANCE_ONLY = "yfinance_only"
    BEST_AVAILABLE = "best_available"  # Use whichever returns data first


@dataclass
class StockQuote:
    """Stock quote data."""
    ticker: str
    price: float
    change: float = 0.0
    change_percent: float = 0.0
    volume: int = 0
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)
    source: DataSource = DataSource.YFINANCE


@dataclass
class CompanyInfo:
    """Company fundamental information."""
    ticker: str
    name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    employees: Optional[int] = None
    market_cap: Optional[float] = None
    revenue: Optional[float] = None
    is_active: bool = True
    exchange: Optional[str] = None
    source: DataSource = DataSource.YFINANCE


@dataclass
class EconomicIndicator:
    """Economic indicator data point."""
    name: str
    value: float
    date: date
    unit: str = ""
    source: DataSource = DataSource.FRED


@dataclass
class MarketSnapshot:
    """Complete market data snapshot."""
    timestamp: datetime
    indices: Dict[str, StockQuote] = field(default_factory=dict)
    economic_indicators: Dict[str, EconomicIndicator] = field(default_factory=dict)
    vix: Optional[float] = None
    yield_curve_spread: Optional[float] = None
    market_status: str = "unknown"  # open, closed, pre-market, after-hours


class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""

    @abstractmethod
    def get_quote(self, ticker: str) -> Optional[StockQuote]:
        """Get current stock quote."""
        pass

    @abstractmethod
    def get_company_info(self, ticker: str) -> Optional[CompanyInfo]:
        """Get company fundamental information."""
        pass

    @abstractmethod
    def get_historical_prices(
        self, ticker: str, start_date: date, end_date: date
    ) -> Optional[pd.DataFrame]:
        """Get historical price data."""
        pass

    @abstractmethod
    def batch_get_quotes(self, tickers: List[str]) -> Dict[str, StockQuote]:
        """Get quotes for multiple tickers efficiently."""
        pass


class IntrinioProvider(MarketDataProvider):
    """
    Intrinio market data provider.

    Provides premium financial data including:
    - Real-time and delayed stock quotes
    - Company fundamentals
    - Financial statements
    - News and filings
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("INTRINIO_API_KEY", "")
        self._client = None
        self._cache: Dict[str, Any] = {}
        self._cache_expiry: Dict[str, datetime] = {}
        self._cache_duration = timedelta(minutes=15)

    def _get_client(self):
        """Lazy load Intrinio client."""
        if self._client is None and self.api_key:
            try:
                import intrinio_sdk as intrinio
                intrinio.ApiClient().set_api_key('api_key', self.api_key)
                self._client = intrinio
            except ImportError:
                logger.warning("intrinio_sdk not installed. Run: pip install intrinio-sdk")
            except Exception as e:
                logger.error(f"Failed to initialize Intrinio client: {e}")
        return self._client

    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached data is still valid."""
        if key not in self._cache_expiry:
            return False
        return datetime.now() < self._cache_expiry[key]

    def _set_cache(self, key: str, value: Any):
        """Set cached data with expiry."""
        self._cache[key] = value
        self._cache_expiry[key] = datetime.now() + self._cache_duration

    def get_quote(self, ticker: str) -> Optional[StockQuote]:
        """Get real-time stock quote from Intrinio."""
        cache_key = f"quote_{ticker}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        client = self._get_client()
        if not client:
            return None

        try:
            security_api = client.SecurityApi()
            quote = security_api.get_security_realtime_price(ticker)

            result = StockQuote(
                ticker=ticker,
                price=float(quote.last_price or 0),
                change=float(quote.change or 0),
                change_percent=float(quote.change_percent or 0) * 100,
                volume=int(quote.volume or 0),
                timestamp=datetime.now(),
                source=DataSource.INTRINIO
            )

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.debug(f"Intrinio quote failed for {ticker}: {e}")
            return None

    def get_company_info(self, ticker: str) -> Optional[CompanyInfo]:
        """Get company fundamentals from Intrinio."""
        cache_key = f"company_{ticker}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        client = self._get_client()
        if not client:
            return None

        try:
            company_api = client.CompanyApi()
            company = company_api.get_company(ticker)

            result = CompanyInfo(
                ticker=ticker,
                name=company.name or ticker,
                sector=company.sector,
                industry=company.industry_group,
                employees=company.employees,
                market_cap=float(company.market_cap) if company.market_cap else None,
                is_active=True,
                exchange=company.stock_exchange,
                source=DataSource.INTRINIO
            )

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.debug(f"Intrinio company info failed for {ticker}: {e}")
            return None

    def get_historical_prices(
        self, ticker: str, start_date: date, end_date: date
    ) -> Optional[pd.DataFrame]:
        """Get historical stock prices from Intrinio."""
        client = self._get_client()
        if not client:
            return None

        try:
            security_api = client.SecurityApi()
            prices = security_api.get_security_stock_prices(
                ticker,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                frequency='daily',
                page_size=500
            )

            if not prices.stock_prices:
                return None

            data = []
            for p in prices.stock_prices:
                data.append({
                    'Date': p.date,
                    'Open': p.open,
                    'High': p.high,
                    'Low': p.low,
                    'Close': p.close,
                    'Volume': p.volume
                })

            df = pd.DataFrame(data)
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
            return df.sort_index()

        except Exception as e:
            logger.debug(f"Intrinio historical prices failed for {ticker}: {e}")
            return None

    def batch_get_quotes(self, tickers: List[str]) -> Dict[str, StockQuote]:
        """Get quotes for multiple tickers."""
        results = {}
        for ticker in tickers:
            quote = self.get_quote(ticker)
            if quote:
                results[ticker] = quote
        return results

    def get_company_financials(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get company financial statements."""
        client = self._get_client()
        if not client:
            return None

        try:
            fundamentals_api = client.FundamentalsApi()

            # Get latest annual filing
            fundamentals = fundamentals_api.get_company_fundamentals(
                ticker,
                statement_code='income_statement',
                fiscal_year=date.today().year - 1,
                page_size=1
            )

            if fundamentals.fundamentals:
                f = fundamentals.fundamentals[0]
                return {
                    'ticker': ticker,
                    'fiscal_year': f.fiscal_year,
                    'fiscal_period': f.fiscal_period,
                    'revenue': f.value if hasattr(f, 'value') else None,
                    'source': DataSource.INTRINIO.value
                }

        except Exception as e:
            logger.debug(f"Intrinio financials failed for {ticker}: {e}")

        return None


class YFinanceProvider(MarketDataProvider):
    """
    Yahoo Finance market data provider.

    Provides free market data including:
    - Stock quotes and historical prices
    - Company information
    - Market indices
    - Options data
    """

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_expiry: Dict[str, datetime] = {}
        self._cache_duration = timedelta(minutes=5)
        self._batch_cache: Dict[str, pd.DataFrame] = {}

    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached data is still valid."""
        if key not in self._cache_expiry:
            return False
        return datetime.now() < self._cache_expiry[key]

    def _set_cache(self, key: str, value: Any):
        """Set cached data with expiry."""
        self._cache[key] = value
        self._cache_expiry[key] = datetime.now() + self._cache_duration

    def get_quote(self, ticker: str) -> Optional[StockQuote]:
        """Get stock quote from Yahoo Finance."""
        cache_key = f"quote_{ticker}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            info = stock.info

            if not info or 'regularMarketPrice' not in info:
                # Try getting from history
                hist = stock.history(period='1d')
                if hist.empty:
                    return None

                result = StockQuote(
                    ticker=ticker,
                    price=float(hist['Close'].iloc[-1]),
                    volume=int(hist['Volume'].iloc[-1]) if 'Volume' in hist else 0,
                    timestamp=datetime.now(),
                    source=DataSource.YFINANCE
                )
            else:
                result = StockQuote(
                    ticker=ticker,
                    price=float(info.get('regularMarketPrice', 0)),
                    change=float(info.get('regularMarketChange', 0)),
                    change_percent=float(info.get('regularMarketChangePercent', 0)) * 100,
                    volume=int(info.get('regularMarketVolume', 0)),
                    market_cap=float(info.get('marketCap', 0)) if info.get('marketCap') else None,
                    pe_ratio=float(info.get('trailingPE', 0)) if info.get('trailingPE') else None,
                    high_52w=float(info.get('fiftyTwoWeekHigh', 0)) if info.get('fiftyTwoWeekHigh') else None,
                    low_52w=float(info.get('fiftyTwoWeekLow', 0)) if info.get('fiftyTwoWeekLow') else None,
                    timestamp=datetime.now(),
                    source=DataSource.YFINANCE
                )

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.debug(f"yfinance quote failed for {ticker}: {e}")
            return None

    def get_company_info(self, ticker: str) -> Optional[CompanyInfo]:
        """Get company information from Yahoo Finance."""
        cache_key = f"company_{ticker}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            info = stock.info

            if not info:
                return None

            result = CompanyInfo(
                ticker=ticker,
                name=info.get('longName', info.get('shortName', ticker)),
                sector=info.get('sector'),
                industry=info.get('industry'),
                employees=info.get('fullTimeEmployees'),
                market_cap=float(info.get('marketCap', 0)) if info.get('marketCap') else None,
                revenue=float(info.get('totalRevenue', 0)) if info.get('totalRevenue') else None,
                is_active=True,
                exchange=info.get('exchange'),
                source=DataSource.YFINANCE
            )

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.debug(f"yfinance company info failed for {ticker}: {e}")
            return None

    def get_historical_prices(
        self, ticker: str, start_date: date, end_date: date
    ) -> Optional[pd.DataFrame]:
        """Get historical stock prices from Yahoo Finance."""
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            df = stock.history(start=start_date, end=end_date)

            if df.empty:
                return None

            return df[['Open', 'High', 'Low', 'Close', 'Volume']]

        except Exception as e:
            logger.debug(f"yfinance historical prices failed for {ticker}: {e}")
            return None

    def batch_get_quotes(self, tickers: List[str]) -> Dict[str, StockQuote]:
        """Get quotes for multiple tickers efficiently using batch download."""
        if not tickers:
            return {}

        results = {}

        try:
            import yfinance as yf

            # Batch download
            tickers_str = " ".join(tickers)
            data = yf.download(tickers_str, period='5d', progress=False, threads=True)

            if data is None or data.empty:
                return results

            for ticker in tickers:
                try:
                    # Handle both single and multi-ticker formats
                    if isinstance(data.columns, pd.MultiIndex):
                        if ('Close', ticker) in data.columns:
                            close_prices = data[('Close', ticker)]
                            volume = data[('Volume', ticker)] if ('Volume', ticker) in data.columns else None
                        elif ticker in data['Close'].columns:
                            close_prices = data['Close'][ticker]
                            volume = data['Volume'][ticker] if ticker in data['Volume'].columns else None
                        else:
                            continue
                    else:
                        close_prices = data['Close']
                        volume = data['Volume'] if 'Volume' in data.columns else None

                    if close_prices is not None and len(close_prices.dropna()) > 0:
                        prices = close_prices.dropna()
                        last_price = float(prices.iloc[-1])

                        change = 0.0
                        change_pct = 0.0
                        if len(prices) >= 2:
                            prev_price = float(prices.iloc[-2])
                            if prev_price > 0:
                                change = last_price - prev_price
                                change_pct = (change / prev_price) * 100

                        results[ticker] = StockQuote(
                            ticker=ticker,
                            price=round(last_price, 2),
                            change=round(change, 2),
                            change_percent=round(change_pct, 2),
                            volume=int(volume.iloc[-1]) if volume is not None and len(volume) > 0 else 0,
                            timestamp=datetime.now(),
                            source=DataSource.YFINANCE
                        )

                except Exception as e:
                    logger.debug(f"Failed to process {ticker}: {e}")
                    continue

        except Exception as e:
            logger.debug(f"Batch download failed: {e}")

        return results

    def get_market_indices(self) -> Dict[str, StockQuote]:
        """Get major market indices."""
        indices = ['^GSPC', '^DJI', '^IXIC', '^VIX', '^TNX']  # S&P 500, Dow, Nasdaq, VIX, 10Y Treasury
        return self.batch_get_quotes(indices)


class FREDProvider:
    """
    FRED (Federal Reserve Economic Data) provider.

    Provides economic indicators including:
    - Interest rates (Fed Funds, Treasury yields)
    - Inflation data (CPI, PCE)
    - Employment data
    - GDP and economic growth
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FRED_API_KEY", "")
        self._fred = None
        self._cache: Dict[str, EconomicIndicator] = {}
        self._cache_expiry: Dict[str, datetime] = {}
        self._cache_duration = timedelta(hours=1)

    def _get_client(self):
        """Lazy load FRED client."""
        if self._fred is None and self.api_key:
            try:
                from fredapi import Fred
                self._fred = Fred(api_key=self.api_key)
            except ImportError:
                logger.warning("fredapi not installed. Run: pip install fredapi")
            except Exception as e:
                logger.error(f"Failed to initialize FRED client: {e}")
        return self._fred

    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached data is still valid."""
        if key not in self._cache_expiry:
            return False
        return datetime.now() < self._cache_expiry[key]

    def _set_cache(self, key: str, value: EconomicIndicator):
        """Set cached data with expiry."""
        self._cache[key] = value
        self._cache_expiry[key] = datetime.now() + self._cache_duration

    def get_indicator(self, series_id: str, name: str = None) -> Optional[EconomicIndicator]:
        """Get a specific economic indicator."""
        cache_key = f"indicator_{series_id}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        fred = self._get_client()
        if not fred:
            return None

        try:
            data = fred.get_series(series_id, observation_start=date.today() - timedelta(days=30))

            if data is None or len(data) == 0:
                return None

            result = EconomicIndicator(
                name=name or series_id,
                value=float(data.iloc[-1]),
                date=data.index[-1].date(),
                source=DataSource.FRED
            )

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.debug(f"FRED indicator failed for {series_id}: {e}")
            return None

    def get_fed_funds_rate(self) -> Optional[EconomicIndicator]:
        """Get current Federal Funds Rate."""
        return self.get_indicator('FEDFUNDS', 'Federal Funds Rate')

    def get_treasury_yield(self, maturity: str = '10Y') -> Optional[EconomicIndicator]:
        """Get Treasury yield for specified maturity."""
        series_map = {
            '1M': 'DGS1MO',
            '3M': 'DGS3MO',
            '6M': 'DGS6MO',
            '1Y': 'DGS1',
            '2Y': 'DGS2',
            '5Y': 'DGS5',
            '10Y': 'DGS10',
            '30Y': 'DGS30'
        }
        series_id = series_map.get(maturity, 'DGS10')
        return self.get_indicator(series_id, f'{maturity} Treasury Yield')

    def get_cpi(self) -> Optional[EconomicIndicator]:
        """Get Consumer Price Index (CPI)."""
        return self.get_indicator('CPIAUCSL', 'CPI')

    def get_unemployment_rate(self) -> Optional[EconomicIndicator]:
        """Get unemployment rate."""
        return self.get_indicator('UNRATE', 'Unemployment Rate')

    def get_all_indicators(self) -> Dict[str, EconomicIndicator]:
        """Get all key economic indicators."""
        indicators = {}

        # Interest rates
        fed_funds = self.get_fed_funds_rate()
        if fed_funds:
            indicators['fed_funds_rate'] = fed_funds

        t2y = self.get_treasury_yield('2Y')
        if t2y:
            indicators['treasury_2y'] = t2y

        t10y = self.get_treasury_yield('10Y')
        if t10y:
            indicators['treasury_10y'] = t10y

        # Calculate yield curve spread
        if t2y and t10y:
            spread = t10y.value - t2y.value
            indicators['yield_curve_spread'] = EconomicIndicator(
                name='Yield Curve Spread (10Y-2Y)',
                value=spread,
                date=date.today(),
                unit='%',
                source=DataSource.FRED
            )

        # Inflation
        cpi = self.get_cpi()
        if cpi:
            indicators['cpi'] = cpi

        # Employment
        unemployment = self.get_unemployment_rate()
        if unemployment:
            indicators['unemployment_rate'] = unemployment

        return indicators


class UnifiedMarketDataProvider:
    """
    Unified market data provider that combines Intrinio, yfinance, and FRED.

    Features:
    - Automatic fallback between data sources
    - Intelligent caching
    - Batch operations for efficiency
    - Configurable priority
    """

    # Extended vendor ticker mapping
    VENDOR_TICKERS = {
        # Tech
        "AMAZON": "AMZN", "AMAZON WEB SERVICES": "AMZN", "AWS": "AMZN",
        "MICROSOFT": "MSFT", "AZURE": "MSFT",
        "GOOGLE": "GOOGL", "ALPHABET": "GOOGL", "GCP": "GOOGL",
        "APPLE": "AAPL",
        "ADOBE": "ADBE",
        "SALESFORCE": "CRM",
        "ORACLE": "ORCL",
        "IBM": "IBM",
        "DELL": "DELL",
        "HP": "HPQ", "HEWLETT PACKARD": "HPQ",
        "CISCO": "CSCO",
        "INTEL": "INTC",
        "NVIDIA": "NVDA",
        "AMD": "AMD",
        "QUALCOMM": "QCOM",
        "SAP": "SAP",
        "VMWARE": "VMW",
        "SERVICENOW": "NOW",
        "WORKDAY": "WDAY",
        "ZOOM": "ZM",
        "SLACK": "CRM",  # Now part of Salesforce
        "DOCUSIGN": "DOCU",
        "DROPBOX": "DBX",
        "ATLASSIAN": "TEAM",
        "SPLUNK": "CSCO",  # Now part of Cisco

        # Telecom
        "AT&T": "T", "ATT": "T",
        "VERIZON": "VZ",
        "T-MOBILE": "TMUS", "TMOBILE": "TMUS",
        "COMCAST": "CMCSA",

        # Shipping/Logistics
        "FEDEX": "FDX",
        "UPS": "UPS",
        "DHL": "DPSGY",

        # Airlines
        "UNITED AIRLINES": "UAL", "UNITED": "UAL",
        "AMERICAN AIRLINES": "AAL",
        "DELTA": "DAL",
        "SOUTHWEST": "LUV",

        # Hotels
        "MARRIOTT": "MAR",
        "HILTON": "HLT",
        "HYATT": "H",
        "IHG": "IHG",

        # Retail
        "HOME DEPOT": "HD",
        "LOWES": "LOW", "LOWE'S": "LOW",
        "STAPLES": "SPLS",
        "OFFICE DEPOT": "ODP",
        "BEST BUY": "BBY",
        "TARGET": "TGT",
        "WALMART": "WMT",
        "COSTCO": "COST",

        # Industrial
        "GRAINGER": "GWW",
        "FASTENAL": "FAST",
        "CATERPILLAR": "CAT",
        "DEERE": "DE", "JOHN DEERE": "DE",
        "3M": "MMM",
        "HONEYWELL": "HON",
        "GENERAL ELECTRIC": "GE", "GE": "GE",

        # Food/Beverage
        "SYSCO": "SYY",
        "US FOODS": "USFD",
        "COCA COLA": "KO", "COKE": "KO",
        "PEPSI": "PEP", "PEPSICO": "PEP",
        "STARBUCKS": "SBUX",
        "MCDONALD'S": "MCD", "MCDONALDS": "MCD",

        # Financial Services
        "BANK OF AMERICA": "BAC", "BOFA": "BAC",
        "WELLS FARGO": "WFC",
        "CHASE": "JPM", "JPMORGAN": "JPM", "JP MORGAN": "JPM",
        "CITIBANK": "C", "CITI": "C",
        "CAPITAL ONE": "COF",
        "AMERICAN EXPRESS": "AXP", "AMEX": "AXP",
        "VISA": "V",
        "MASTERCARD": "MA",
        "PAYPAL": "PYPL",
        "SQUARE": "SQ",
        "STRIPE": None,  # Private

        # Insurance
        "BLUE CROSS": "ANTM", "ANTHEM": "ELV",
        "AETNA": "CVS",
        "UNITED HEALTH": "UNH", "UNITEDHEALTH": "UNH",
        "CIGNA": "CI",
        "HUMANA": "HUM",
        "STATE FARM": None,  # Private
        "PROGRESSIVE": "PGR",
        "ALLSTATE": "ALL",
        "GEICO": "BRK-B",  # Berkshire subsidiary

        # Payroll/HR
        "ADP": "ADP",
        "PAYCHEX": "PAYX",
        "WORKDAY": "WDAY",
        "CERIDIAN": "CDAY",

        # Professional Services
        "DELOITTE": None,  # Private
        "KPMG": None,  # Private
        "PWC": None,  # Private
        "ERNST & YOUNG": None, "EY": None,  # Private
        "ACCENTURE": "ACN",
        "MCKINSEY": None,  # Private
    }

    def __init__(
        self,
        intrinio_api_key: Optional[str] = None,
        fred_api_key: Optional[str] = None,
        priority: DataPriority = DataPriority.YFINANCE_FIRST
    ):
        self.priority = priority

        # Initialize providers
        self.intrinio = IntrinioProvider(intrinio_api_key)
        self.yfinance = YFinanceProvider()
        self.fred = FREDProvider(fred_api_key)

        # Unified cache
        self._quote_cache: Dict[str, StockQuote] = {}
        self._company_cache: Dict[str, CompanyInfo] = {}
        self._economic_cache: Dict[str, EconomicIndicator] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._cache_duration = timedelta(minutes=15)

    def _is_cache_fresh(self) -> bool:
        """Check if cache is still fresh."""
        if self._cache_timestamp is None:
            return False
        return datetime.now() - self._cache_timestamp < self._cache_duration

    def refresh_cache(self):
        """Force refresh all cached data."""
        self._cache_timestamp = None
        self._quote_cache.clear()
        self._company_cache.clear()
        self._economic_cache.clear()

    def lookup_ticker(self, vendor_name: str) -> Optional[str]:
        """Look up stock ticker for a vendor name."""
        if not vendor_name:
            return None

        normalized = vendor_name.upper()
        for suffix in [' INC', ' LLC', ' LTD', ' CORP', ' CORPORATION', ' CO', ' LP']:
            normalized = normalized.replace(suffix, '')
        normalized = normalized.strip()

        # Direct lookup
        if normalized in self.VENDOR_TICKERS:
            return self.VENDOR_TICKERS[normalized]

        # Partial match
        for vendor_key, ticker in self.VENDOR_TICKERS.items():
            if vendor_key in normalized or normalized in vendor_key:
                return ticker

        return None

    def get_quote(self, ticker: str) -> Optional[StockQuote]:
        """Get stock quote with fallback between providers."""
        # Check cache first
        if ticker in self._quote_cache and self._is_cache_fresh():
            return self._quote_cache[ticker]

        quote = None

        if self.priority == DataPriority.INTRINIO_FIRST:
            quote = self.intrinio.get_quote(ticker)
            if not quote:
                quote = self.yfinance.get_quote(ticker)
        elif self.priority == DataPriority.YFINANCE_FIRST:
            quote = self.yfinance.get_quote(ticker)
            if not quote:
                quote = self.intrinio.get_quote(ticker)
        elif self.priority == DataPriority.INTRINIO_ONLY:
            quote = self.intrinio.get_quote(ticker)
        else:  # YFINANCE_ONLY or default
            quote = self.yfinance.get_quote(ticker)

        if quote:
            self._quote_cache[ticker] = quote
            self._cache_timestamp = datetime.now()

        return quote

    def get_company_info(self, ticker: str) -> Optional[CompanyInfo]:
        """Get company info with fallback between providers."""
        if ticker in self._company_cache and self._is_cache_fresh():
            return self._company_cache[ticker]

        info = None

        if self.priority in [DataPriority.INTRINIO_FIRST, DataPriority.INTRINIO_ONLY]:
            info = self.intrinio.get_company_info(ticker)
            if not info and self.priority == DataPriority.INTRINIO_FIRST:
                info = self.yfinance.get_company_info(ticker)
        else:
            info = self.yfinance.get_company_info(ticker)
            if not info and self.priority == DataPriority.YFINANCE_FIRST:
                info = self.intrinio.get_company_info(ticker)

        if info:
            self._company_cache[ticker] = info

        return info

    def batch_get_quotes(self, tickers: List[str]) -> Dict[str, StockQuote]:
        """Get quotes for multiple tickers efficiently."""
        # Filter out already cached tickers
        needed = [t for t in tickers if t not in self._quote_cache or not self._is_cache_fresh()]

        if needed:
            # Use yfinance for batch (more efficient)
            new_quotes = self.yfinance.batch_get_quotes(needed)

            # Fall back to Intrinio for missing ones if available
            if self.priority in [DataPriority.INTRINIO_FIRST, DataPriority.BEST_AVAILABLE]:
                missing = [t for t in needed if t not in new_quotes]
                if missing:
                    intrinio_quotes = self.intrinio.batch_get_quotes(missing)
                    new_quotes.update(intrinio_quotes)

            # Update cache
            self._quote_cache.update(new_quotes)
            self._cache_timestamp = datetime.now()

        return {t: self._quote_cache[t] for t in tickers if t in self._quote_cache}

    def get_economic_indicators(self) -> Dict[str, EconomicIndicator]:
        """Get all economic indicators from FRED."""
        if self._economic_cache and self._is_cache_fresh():
            return self._economic_cache

        self._economic_cache = self.fred.get_all_indicators()

        # Add VIX from yfinance
        try:
            import yfinance as yf
            vix = yf.Ticker('^VIX')
            hist = vix.history(period='1d')
            if hist is not None and len(hist) > 0:
                self._economic_cache['vix'] = EconomicIndicator(
                    name='VIX',
                    value=float(hist['Close'].iloc[-1]),
                    date=date.today(),
                    source=DataSource.YFINANCE
                )
        except Exception:
            pass

        self._cache_timestamp = datetime.now()
        return self._economic_cache

    def get_market_snapshot(self) -> MarketSnapshot:
        """Get complete market snapshot."""
        snapshot = MarketSnapshot(timestamp=datetime.now())

        # Get indices
        index_tickers = ['^GSPC', '^DJI', '^IXIC']
        indices = self.batch_get_quotes(index_tickers)
        snapshot.indices = indices

        # Get economic indicators
        snapshot.economic_indicators = self.get_economic_indicators()

        # VIX
        vix_indicator = snapshot.economic_indicators.get('vix')
        if vix_indicator:
            snapshot.vix = vix_indicator.value

        # Yield curve spread
        spread_indicator = snapshot.economic_indicators.get('yield_curve_spread')
        if spread_indicator:
            snapshot.yield_curve_spread = spread_indicator.value

        # Market status (simplified)
        now = datetime.now()
        if now.weekday() >= 5:
            snapshot.market_status = 'closed'
        elif 9 <= now.hour < 16:
            snapshot.market_status = 'open'
        elif now.hour < 9:
            snapshot.market_status = 'pre-market'
        else:
            snapshot.market_status = 'after-hours'

        return snapshot

    def validate_vendor(self, vendor_name: str) -> Dict[str, Any]:
        """Validate a vendor and return market data."""
        result = {
            'vendor_name': vendor_name,
            'ticker': None,
            'is_public': False,
            'is_active': False,
            'quote': None,
            'company_info': None
        }

        ticker = self.lookup_ticker(vendor_name)
        if not ticker:
            return result

        result['ticker'] = ticker
        result['is_public'] = True

        quote = self.get_quote(ticker)
        if quote:
            result['quote'] = quote
            result['is_active'] = True

        company = self.get_company_info(ticker)
        if company:
            result['company_info'] = company

        return result

    def get_historical_comparison(
        self,
        ticker: str,
        start_date: date,
        end_date: date
    ) -> Optional[pd.DataFrame]:
        """Get historical prices with fallback."""
        df = None

        if self.priority in [DataPriority.INTRINIO_FIRST, DataPriority.INTRINIO_ONLY]:
            df = self.intrinio.get_historical_prices(ticker, start_date, end_date)
            if df is None and self.priority == DataPriority.INTRINIO_FIRST:
                df = self.yfinance.get_historical_prices(ticker, start_date, end_date)
        else:
            df = self.yfinance.get_historical_prices(ticker, start_date, end_date)
            if df is None and self.priority == DataPriority.YFINANCE_FIRST:
                df = self.intrinio.get_historical_prices(ticker, start_date, end_date)

        return df
