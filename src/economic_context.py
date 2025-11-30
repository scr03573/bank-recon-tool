"""
Economic context integration using FRED API and yfinance.

Provides market context for reconciliation analysis:
- Interest rates (Fed Funds, Treasury yields)
- Market volatility (VIX)
- Economic indicators
- Payment timing analysis based on economic conditions
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List
from decimal import Decimal
import warnings

# Suppress yfinance warnings
warnings.filterwarnings("ignore", category=FutureWarning)

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

try:
    from fredapi import Fred
    FREDAPI_AVAILABLE = True
except ImportError:
    FREDAPI_AVAILABLE = False

import pandas as pd

from .config import config


@dataclass
class EconomicSnapshot:
    """Point-in-time economic data snapshot."""
    snapshot_date: date
    fed_funds_rate: Optional[float] = None
    prime_rate: Optional[float] = None
    treasury_10y: Optional[float] = None
    treasury_2y: Optional[float] = None
    yield_curve_spread: Optional[float] = None  # 10Y - 2Y
    vix: Optional[float] = None
    sp500_price: Optional[float] = None
    sp500_change_pct: Optional[float] = None
    unemployment_rate: Optional[float] = None
    cpi_yoy: Optional[float] = None
    ppi_yoy: Optional[float] = None

    def is_high_volatility(self) -> bool:
        """Check if market is in high volatility regime."""
        return self.vix is not None and self.vix > 25

    def is_inverted_yield_curve(self) -> bool:
        """Check if yield curve is inverted."""
        return self.yield_curve_spread is not None and self.yield_curve_spread < 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_date": self.snapshot_date.isoformat(),
            "fed_funds_rate": self.fed_funds_rate,
            "prime_rate": self.prime_rate,
            "treasury_10y": self.treasury_10y,
            "treasury_2y": self.treasury_2y,
            "yield_curve_spread": self.yield_curve_spread,
            "vix": self.vix,
            "sp500_price": self.sp500_price,
            "sp500_change_pct": self.sp500_change_pct,
            "unemployment_rate": self.unemployment_rate,
            "cpi_yoy": self.cpi_yoy,
            "ppi_yoy": self.ppi_yoy,
        }


@dataclass
class PaymentAnalysis:
    """Analysis of payment patterns in economic context."""
    period_start: date
    period_end: date
    avg_payment_delay_days: float = 0.0
    early_payment_discount_opportunity: Decimal = Decimal("0")
    late_payment_penalty_exposure: Decimal = Decimal("0")
    recommended_payment_timing: str = ""
    economic_conditions_summary: str = ""


class EconomicDataProvider:
    """
    Fetches and caches economic data from FRED and yfinance.
    """

    # FRED series IDs
    FRED_SERIES = {
        "fed_funds": "FEDFUNDS",
        "prime_rate": "DPRIME",
        "treasury_10y": "DGS10",
        "treasury_2y": "DGS2",
        "unemployment": "UNRATE",
        "cpi": "CPIAUCSL",
        "ppi": "PPIACO",
    }

    def __init__(self, fred_api_key: Optional[str] = None):
        self.fred_api_key = fred_api_key or config.fred_api_key
        self._fred: Optional[Fred] = None
        self._cache: Dict[str, pd.DataFrame] = {}
        self._cache_expiry: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(hours=1)

    @property
    def fred(self) -> Optional[Fred]:
        """Lazy-load FRED client."""
        if self._fred is None and FREDAPI_AVAILABLE and self.fred_api_key:
            try:
                self._fred = Fred(api_key=self.fred_api_key)
            except Exception as e:
                print(f"Warning: Could not initialize FRED client: {e}")
        return self._fred

    def get_snapshot(self, target_date: Optional[date] = None) -> EconomicSnapshot:
        """Get economic snapshot for a specific date."""
        target_date = target_date or date.today()
        snapshot = EconomicSnapshot(snapshot_date=target_date)

        # Fetch FRED data
        if self.fred:
            snapshot.fed_funds_rate = self._get_fred_value("fed_funds", target_date)
            snapshot.prime_rate = self._get_fred_value("prime_rate", target_date)
            snapshot.treasury_10y = self._get_fred_value("treasury_10y", target_date)
            snapshot.treasury_2y = self._get_fred_value("treasury_2y", target_date)
            snapshot.unemployment_rate = self._get_fred_value("unemployment", target_date)

            # Calculate yield curve spread
            if snapshot.treasury_10y and snapshot.treasury_2y:
                snapshot.yield_curve_spread = snapshot.treasury_10y - snapshot.treasury_2y

            # CPI year-over-year change
            cpi_current = self._get_fred_value("cpi", target_date)
            cpi_year_ago = self._get_fred_value("cpi", target_date - timedelta(days=365))
            if cpi_current and cpi_year_ago and cpi_year_ago > 0:
                snapshot.cpi_yoy = ((cpi_current - cpi_year_ago) / cpi_year_ago) * 100

        # Fetch market data from yfinance
        if YFINANCE_AVAILABLE:
            snapshot.vix = self._get_yf_price("^VIX", target_date)
            snapshot.sp500_price = self._get_yf_price("^GSPC", target_date)

            # S&P 500 change
            if snapshot.sp500_price:
                prev_price = self._get_yf_price("^GSPC", target_date - timedelta(days=30))
                if prev_price and prev_price > 0:
                    snapshot.sp500_change_pct = ((snapshot.sp500_price - prev_price) / prev_price) * 100

        return snapshot

    def get_historical_rates(
        self,
        start_date: date,
        end_date: date,
        series: str = "fed_funds"
    ) -> pd.DataFrame:
        """Get historical rate data for a date range."""
        if not self.fred:
            return pd.DataFrame()

        cache_key = f"{series}_{start_date}_{end_date}"
        if cache_key in self._cache and datetime.now() < self._cache_expiry.get(cache_key, datetime.min):
            return self._cache[cache_key]

        try:
            series_id = self.FRED_SERIES.get(series, series)
            data = self.fred.get_series(
                series_id,
                observation_start=start_date,
                observation_end=end_date
            )
            df = data.to_frame(name="value")
            df.index.name = "date"

            self._cache[cache_key] = df
            self._cache_expiry[cache_key] = datetime.now() + self._cache_ttl

            return df
        except Exception as e:
            print(f"Warning: Could not fetch FRED series {series}: {e}")
            return pd.DataFrame()

    def get_market_data(
        self,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """Get historical market data from yfinance."""
        if not YFINANCE_AVAILABLE:
            return pd.DataFrame()

        cache_key = f"yf_{symbol}_{start_date}_{end_date}"
        if cache_key in self._cache and datetime.now() < self._cache_expiry.get(cache_key, datetime.min):
            return self._cache[cache_key]

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=end_date)

            self._cache[cache_key] = df
            self._cache_expiry[cache_key] = datetime.now() + self._cache_ttl

            return df
        except Exception as e:
            print(f"Warning: Could not fetch yfinance data for {symbol}: {e}")
            return pd.DataFrame()

    def _get_fred_value(self, series: str, target_date: date) -> Optional[float]:
        """Get single FRED value for a date (uses most recent available)."""
        if not self.fred:
            return None

        try:
            series_id = self.FRED_SERIES.get(series, series)
            # Fetch a range to handle weekends/holidays
            start = target_date - timedelta(days=30)
            data = self.fred.get_series(series_id, observation_start=start, observation_end=target_date)

            if data is not None and len(data) > 0:
                # Return most recent value
                return float(data.iloc[-1])
        except Exception as e:
            print(f"Warning: Could not fetch FRED value for {series}: {e}")

        return None

    def _get_yf_price(self, symbol: str, target_date: date) -> Optional[float]:
        """Get closing price from yfinance for a date."""
        if not YFINANCE_AVAILABLE:
            return None

        try:
            ticker = yf.Ticker(symbol)
            start = target_date - timedelta(days=7)
            end = target_date + timedelta(days=1)
            hist = ticker.history(start=start, end=end)

            if hist is not None and len(hist) > 0:
                return float(hist["Close"].iloc[-1])
        except Exception as e:
            print(f"Warning: Could not fetch yfinance price for {symbol}: {e}")

        return None


class PaymentTimingAnalyzer:
    """
    Analyzes payment timing in context of economic conditions.

    Considers:
    - Early payment discounts vs. holding cash
    - Interest rate environment
    - Vendor relationships
    - Cash flow optimization
    """

    def __init__(self, economic_provider: Optional[EconomicDataProvider] = None):
        self.economic = economic_provider or EconomicDataProvider()

    def analyze_payment_timing(
        self,
        period_start: date,
        period_end: date,
        total_payables: Decimal,
        early_discount_opportunities: List[Dict[str, Any]] = None
    ) -> PaymentAnalysis:
        """Analyze optimal payment timing for a period."""
        analysis = PaymentAnalysis(period_start=period_start, period_end=period_end)

        # Get economic snapshot
        snapshot = self.economic.get_snapshot(period_end)

        # Calculate early payment discount value
        early_discount_opportunities = early_discount_opportunities or []
        total_discount = Decimal("0")
        for opp in early_discount_opportunities:
            discount_pct = Decimal(str(opp.get("discount_pct", 0)))
            amount = Decimal(str(opp.get("amount", 0)))
            total_discount += amount * (discount_pct / 100)

        analysis.early_payment_discount_opportunity = total_discount

        # Determine recommended timing based on conditions
        if snapshot.fed_funds_rate:
            # If rates are high, holding cash may be more valuable
            annualized_discount = self._annualize_discount(2, 10, 30)  # 2/10 net 30
            if snapshot.fed_funds_rate > annualized_discount:
                analysis.recommended_payment_timing = "Pay on due date - holding cash yields more than early discount"
            else:
                analysis.recommended_payment_timing = "Take early payment discounts when available"
        else:
            analysis.recommended_payment_timing = "Consider early payment discounts on case-by-case basis"

        # Economic conditions summary
        conditions = []
        if snapshot.fed_funds_rate:
            conditions.append(f"Fed Funds Rate: {snapshot.fed_funds_rate:.2f}%")
        if snapshot.is_high_volatility():
            conditions.append(f"High market volatility (VIX: {snapshot.vix:.1f})")
        if snapshot.is_inverted_yield_curve():
            conditions.append("Inverted yield curve (recession indicator)")
        if snapshot.cpi_yoy:
            conditions.append(f"Inflation (CPI YoY): {snapshot.cpi_yoy:.1f}%")

        analysis.economic_conditions_summary = "; ".join(conditions) if conditions else "Economic data unavailable"

        return analysis

    def _annualize_discount(
        self,
        discount_pct: float,
        discount_days: int,
        net_days: int
    ) -> float:
        """Annualize an early payment discount rate."""
        # Formula: (discount / (100 - discount)) * (365 / (net_days - discount_days))
        if net_days <= discount_days:
            return 0.0

        numerator = discount_pct / (100 - discount_pct)
        periods_per_year = 365 / (net_days - discount_days)
        return numerator * periods_per_year * 100

    def get_cash_management_recommendations(
        self,
        snapshot: EconomicSnapshot,
        available_cash: Decimal,
        upcoming_payables: Decimal
    ) -> List[str]:
        """Generate cash management recommendations based on conditions."""
        recommendations = []

        coverage_ratio = float(available_cash / upcoming_payables) if upcoming_payables else float('inf')

        if coverage_ratio < 1.0:
            recommendations.append(
                f"⚠️ Cash coverage ratio ({coverage_ratio:.1%}) below 100% - prioritize collections"
            )

        if snapshot.fed_funds_rate and snapshot.fed_funds_rate > 4:
            recommendations.append(
                "Consider money market funds for excess cash - high short-term rates available"
            )

        if snapshot.is_inverted_yield_curve():
            recommendations.append(
                "Yield curve inverted - consider short-term investments over long-term"
            )

        if snapshot.is_high_volatility():
            recommendations.append(
                "High market volatility - maintain adequate cash reserves"
            )

        if snapshot.cpi_yoy and snapshot.cpi_yoy > 4:
            recommendations.append(
                f"Inflation elevated ({snapshot.cpi_yoy:.1f}%) - negotiate fixed-price contracts where possible"
            )

        return recommendations


def create_sample_economic_data() -> EconomicSnapshot:
    """Create sample economic data for testing."""
    return EconomicSnapshot(
        snapshot_date=date.today(),
        fed_funds_rate=5.25,
        prime_rate=8.25,
        treasury_10y=4.50,
        treasury_2y=4.75,
        yield_curve_spread=-0.25,
        vix=18.5,
        sp500_price=4500.0,
        sp500_change_pct=2.3,
        unemployment_rate=3.7,
        cpi_yoy=3.2,
        ppi_yoy=2.1,
    )
