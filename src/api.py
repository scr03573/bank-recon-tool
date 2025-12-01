"""
FastAPI backend for Bank Reconciliation Tool.

Provides REST API endpoints for:
- Running reconciliations
- Viewing market data
- Managing exceptions
- Accessing reconciliation history

Features:
- JWT Authentication (optional, enabled via AUTH_ENABLED=true)
- Rate limiting
- Structured logging
- Input validation
"""
from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import defaultdict
import tempfile
import json
import os
import time

from .reconciler import BankReconciler, create_sample_data
from .market_data import UnifiedMarketDataProvider, DataPriority
from .config import config
from .models import ExceptionType
from .logging_config import setup_logging, get_logger, log_api_request, log_error
from .auth import (
    Token, LoginRequest, User, authenticate_user, create_access_token,
    get_current_user, require_auth, require_permission, ACCESS_TOKEN_EXPIRE_MINUTES
)

# Setup logging
logger = setup_logging(level="INFO")

# Check if auth is enabled
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "false").lower() == "true"

app = FastAPI(
    title="Bank Reconciliation API",
    description="API for bank reconciliation with Sage Intacct integration and market data validation",
    version="1.0.0"
)

# CORS for frontend
ALLOWED_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== Rate Limiting ==============

class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        """Check if request is allowed."""
        now = time.time()
        minute_ago = now - 60

        # Clean old requests
        self.requests[client_id] = [
            t for t in self.requests[client_id] if t > minute_ago
        ]

        # Check limit
        if len(self.requests[client_id]) >= self.requests_per_minute:
            return False

        self.requests[client_id].append(now)
        return True


rate_limiter = RateLimiter(requests_per_minute=100)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware."""
    client_ip = request.client.host if request.client else "unknown"

    if not rate_limiter.is_allowed(client_ip):
        logger.warning(f"Rate limit exceeded for {client_ip}")
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please try again later."}
        )

    # Log request timing
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000

    log_api_request(
        logger,
        request.method,
        str(request.url.path),
        response.status_code,
        duration_ms,
        client_ip
    )

    return response

# Global instances (lazy loaded)
_reconciler: Optional[BankReconciler] = None
_market_provider: Optional[UnifiedMarketDataProvider] = None


def get_reconciler() -> BankReconciler:
    global _reconciler
    if _reconciler is None:
        _reconciler = BankReconciler(use_mock_intacct=True)
    return _reconciler


def get_market_provider() -> UnifiedMarketDataProvider:
    global _market_provider
    if _market_provider is None:
        _market_provider = UnifiedMarketDataProvider(
            intrinio_api_key=config.market_data.intrinio_api_key,
            fred_api_key=config.market_data.fred_api_key or config.fred_api_key,
            priority=DataPriority.YFINANCE_FIRST
        )
    return _market_provider


# ============== Pydantic Models ==============

class ReconciliationRequest(BaseModel):
    start_date: str
    end_date: str
    bank_account_id: Optional[str] = "CHECKING-001"


class ReconciliationSummary(BaseModel):
    run_id: str
    status: str
    total_bank_transactions: int
    total_ap_transactions: int
    matched_count: int
    exception_count: int
    match_rate: float
    total_matched_amount: float
    start_date: str
    end_date: str
    created_at: str


class MatchDetail(BaseModel):
    match_id: str
    bank_transaction_id: str
    bank_date: str
    bank_amount: float
    bank_description: str
    ap_transaction_ids: List[str]
    vendor_name: str
    confidence: float
    match_type: str
    match_reasons: List[str]


class ExceptionDetail(BaseModel):
    exception_id: str
    exception_type: str
    severity: str
    transaction_id: str
    transaction_date: str
    amount: float
    description: str
    suggested_action: str
    is_resolved: bool
    resolution_notes: Optional[str] = None


class MarketSnapshot(BaseModel):
    as_of: str
    vix: Optional[float] = None
    sp500: Optional[float] = None
    sp500_change: Optional[float] = None
    fed_funds_rate: Optional[float] = None
    treasury_2y: Optional[float] = None
    treasury_10y: Optional[float] = None
    yield_curve_spread: Optional[float] = None
    yield_curve_inverted: bool = False
    market_status: str = "NORMAL"
    data_sources: List[str] = []


class StockQuoteResponse(BaseModel):
    ticker: str
    price: float
    change: float
    change_percent: float
    volume: int
    source: str


class VendorValidation(BaseModel):
    vendor_name: str
    ticker: Optional[str] = None
    is_public: bool = False
    is_active: bool = False
    price: Optional[float] = None
    company_name: Optional[str] = None


class ResolveExceptionRequest(BaseModel):
    resolution_notes: str


class ConfigStatus(BaseModel):
    intacct_configured: bool
    fred_configured: bool
    intrinio_configured: bool
    market_data_priority: str
    fuzzy_threshold: int
    date_tolerance_days: int
    amount_tolerance_percent: float


# ============== API Endpoints ==============

@app.get("/")
async def root():
    return {
        "name": "Bank Reconciliation API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "auth_enabled": AUTH_ENABLED
    }


# ------------ Authentication Endpoints ------------

@app.post("/api/auth/login", response_model=Token)
async def login(request: LoginRequest):
    """Authenticate user and return JWT token."""
    user = authenticate_user(request.username, request.password)
    if not user:
        logger.warning(f"Failed login attempt for user: {request.username}")
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    logger.info(f"User logged in: {user['username']}")

    return Token(
        access_token=access_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "username": user["username"],
            "role": user["role"],
            "full_name": user["full_name"]
        }
    )


@app.get("/api/auth/me")
async def get_current_user_info(user: User = Depends(require_auth)):
    """Get current authenticated user info."""
    return {
        "username": user.username,
        "role": user.role,
        "full_name": user.full_name
    }


@app.get("/api/status", response_model=ConfigStatus)
async def get_status():
    """Get current configuration status."""
    return ConfigStatus(
        intacct_configured=config.intacct.is_configured(),
        fred_configured=config.market_data.is_fred_configured(),
        intrinio_configured=config.market_data.is_intrinio_configured(),
        market_data_priority=config.market_data.data_priority,
        fuzzy_threshold=config.matching.fuzzy_threshold,
        date_tolerance_days=config.matching.date_tolerance_days,
        amount_tolerance_percent=config.matching.amount_tolerance_percent
    )


# ------------ Reconciliation Endpoints ------------

# Store recent reconciliation results in memory for quick access
_recent_results: Dict[str, Any] = {}


@app.post("/api/reconcile/demo", response_model=ReconciliationSummary)
async def run_demo_reconciliation():
    """Run a demo reconciliation with sample data."""
    try:
        from datetime import timedelta

        # Generate sample data like the demo script does
        bank_transactions, ap_transactions = create_sample_data()

        reconciler = get_reconciler()
        result = reconciler.reconcile(
            bank_transactions=bank_transactions,
            ap_transactions=ap_transactions,
            start_date=date.today() - timedelta(days=30),
            end_date=date.today(),
            bank_account_id="CHECKING-001",
            generate_reports=True,
            report_formats=["excel", "html", "json"]
        )

        # Store result for later retrieval
        run_id = result.summary.id
        _recent_results[run_id] = result

        return ReconciliationSummary(
            run_id=run_id,
            status="completed",
            total_bank_transactions=result.summary.total_bank_transactions,
            total_ap_transactions=result.summary.total_ap_transactions,
            matched_count=result.summary.matched_count,
            exception_count=len(result.exceptions),
            match_rate=result.summary.auto_match_rate,
            total_matched_amount=float(result.summary.matched_amount),
            start_date=result.summary.period_start.isoformat() if result.summary.period_start else "",
            end_date=result.summary.period_end.isoformat() if result.summary.period_end else "",
            created_at=datetime.now().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reconcile/upload", response_model=ReconciliationSummary)
async def run_reconciliation_with_file(
    file: UploadFile = File(...),
    start_date: str = Query(...),
    end_date: str = Query(...),
    bank_account_id: str = Query("CHECKING-001")
):
    """Run reconciliation with uploaded bank file."""
    try:
        # Save uploaded file temporarily
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            reconciler = get_reconciler()
            result = reconciler.reconcile(
                bank_file=tmp_path,
                start_date=date.fromisoformat(start_date),
                end_date=date.fromisoformat(end_date),
                bank_account_id=bank_account_id
            )

            return ReconciliationSummary(
                run_id=result.run_id,
                status=result.status.value,
                total_bank_transactions=result.summary.total_bank_transactions,
                total_ap_transactions=result.summary.total_ap_transactions,
                matched_count=result.summary.matched_count,
                exception_count=len(result.exceptions),
                match_rate=result.summary.match_rate,
                total_matched_amount=float(result.summary.total_matched_amount),
                start_date=result.summary.start_date.isoformat(),
                end_date=result.summary.end_date.isoformat(),
                created_at=datetime.now().isoformat()
            )
        finally:
            os.unlink(tmp_path)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


@app.get("/api/reconcile/history")
async def get_reconciliation_history(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    start_date: Optional[str] = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter by end date (YYYY-MM-DD)")
):
    """
    Get reconciliation history with pagination.

    Returns paginated list of reconciliation runs.
    """
    try:
        reconciler = get_reconciler()

        # Get total count (we'd need to add this to reconciler, for now estimate)
        all_history = reconciler.get_reconciliation_history(limit=1000)

        # Filter by date if specified
        if start_date or end_date:
            filtered = []
            for h in all_history:
                run_date = h.get('run_date', '')
                if start_date and run_date < start_date:
                    continue
                if end_date and run_date > end_date:
                    continue
                filtered.append(h)
            all_history = filtered

        total = len(all_history)
        total_pages = (total + page_size - 1) // page_size

        # Apply pagination
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated = all_history[start_idx:end_idx]

        items = [
            ReconciliationSummary(
                run_id=h.get('id', ''),
                status=h.get('status', 'completed'),
                total_bank_transactions=h.get('total_bank_transactions', 0),
                total_ap_transactions=h.get('total_ap_transactions', 0),
                matched_count=h.get('matched_count', 0),
                exception_count=h.get('exception_count', 0),
                match_rate=h.get('auto_match_rate', 0.0),
                total_matched_amount=h.get('total_bank_amount', 0.0),
                start_date=h.get('period_start', ''),
                end_date=h.get('period_end', ''),
                created_at=h.get('run_date', datetime.now().isoformat())
            )
            for h in paginated
        ]

        return {
            "items": [item.dict() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    except Exception as e:
        log_error(logger, e, "get_reconciliation_history")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reconcile/{run_id}", response_model=Dict[str, Any])
async def get_reconciliation_detail(run_id: str):
    """Get detailed results for a reconciliation run."""
    try:
        reconciler = get_reconciler()
        result = reconciler.get_run_details(run_id)

        if not result:
            raise HTTPException(status_code=404, detail="Run not found")

        # Result is a dict from the database
        return {
            "run_id": result.get('id', run_id),
            "status": result.get('status', 'completed'),
            "summary": {
                "total_bank_transactions": result.get('total_bank_transactions', 0),
                "total_ap_transactions": result.get('total_ap_transactions', 0),
                "matched_count": result.get('matched_count', 0),
                "match_rate": result.get('auto_match_rate', 0.0),
                "total_matched_amount": result.get('total_bank_amount', 0.0),
                "unmatched_bank_count": 0,
                "unmatched_ap_count": 0
            },
            "matches": result.get('matches', []),
            "exceptions": result.get('exceptions', []),
            "report_paths": {}
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------ Market Data Endpoints ------------

@app.get("/api/market/snapshot", response_model=MarketSnapshot)
async def get_market_snapshot():
    """Get current market data snapshot."""
    try:
        provider = get_market_provider()
        snapshot = provider.get_market_snapshot()

        # Get S&P 500 from indices if available
        sp500 = None
        sp500_change = None
        if '^GSPC' in snapshot.indices:
            sp_quote = snapshot.indices['^GSPC']
            sp500 = sp_quote.price
            sp500_change = sp_quote.change_percent

        # Get economic indicators
        fed_funds = None
        treasury_2y = None
        treasury_10y = None
        if 'fed_funds_rate' in snapshot.economic_indicators:
            fed_funds = snapshot.economic_indicators['fed_funds_rate'].value
        if 'treasury_2y' in snapshot.economic_indicators:
            treasury_2y = snapshot.economic_indicators['treasury_2y'].value
        if 'treasury_10y' in snapshot.economic_indicators:
            treasury_10y = snapshot.economic_indicators['treasury_10y'].value

        # Calculate yield curve inversion
        yield_curve_inverted = False
        if treasury_2y and treasury_10y:
            yield_curve_inverted = treasury_10y < treasury_2y

        # Collect data sources
        data_sources = set()
        for quote in snapshot.indices.values():
            if quote.source:
                data_sources.add(quote.source.value if hasattr(quote.source, 'value') else str(quote.source))
        for indicator in snapshot.economic_indicators.values():
            if indicator.source:
                data_sources.add(indicator.source)

        return MarketSnapshot(
            as_of=datetime.now().isoformat(),
            vix=snapshot.vix,
            sp500=sp500,
            sp500_change=sp500_change,
            fed_funds_rate=fed_funds,
            treasury_2y=treasury_2y,
            treasury_10y=treasury_10y,
            yield_curve_spread=snapshot.yield_curve_spread,
            yield_curve_inverted=yield_curve_inverted,
            market_status=snapshot.market_status,
            data_sources=list(data_sources)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/market/quote/{ticker}", response_model=StockQuoteResponse)
async def get_stock_quote(ticker: str):
    """Get stock quote for a ticker."""
    try:
        provider = get_market_provider()
        quote = provider.get_quote(ticker.upper())

        if not quote:
            raise HTTPException(status_code=404, detail=f"Quote not found for {ticker}")

        return StockQuoteResponse(
            ticker=quote.ticker,
            price=quote.price,
            change=quote.change,
            change_percent=quote.change_percent,
            volume=quote.volume,
            source=quote.source.value if hasattr(quote.source, 'value') else str(quote.source)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/market/economic")
async def get_economic_indicators():
    """Get current economic indicators from FRED."""
    try:
        provider = get_market_provider()
        indicators = provider.get_economic_indicators()

        result = {}
        for key, indicator in indicators.items():
            result[key] = {
                "name": indicator.name,
                "value": indicator.value,
                "unit": indicator.unit,
                "date": indicator.date.isoformat() if indicator.date else None,
                "source": indicator.source
            }

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/market/validate-vendor/{vendor_name}", response_model=VendorValidation)
async def validate_vendor(vendor_name: str):
    """Validate a vendor by looking up stock ticker."""
    try:
        provider = get_market_provider()
        validation = provider.validate_vendor(vendor_name)

        return VendorValidation(
            vendor_name=vendor_name,
            ticker=validation.get('ticker'),
            is_public=validation.get('is_public', False),
            is_active=validation.get('is_active', False),
            price=validation.get('price'),
            company_name=validation.get('company_name')
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------ Exception Endpoints ------------

@app.get("/api/reconcile/{run_id}/matches")
async def get_matches_for_run(run_id: str):
    """Get matches for a specific reconciliation run."""
    try:
        if run_id not in _recent_results:
            raise HTTPException(status_code=404, detail="Run not found or expired. Run a new reconciliation.")

        result = _recent_results[run_id]
        matches = []

        for m in result.matches:
            match_data = {
                "match_id": m.id,  # Using 'id' from ReconciliationMatch model
                "confidence_score": m.confidence_score,
                "match_status": m.match_status.value if hasattr(m.match_status, 'value') else str(m.match_status),
                "match_reasons": m.match_reasons,
                "bank_transaction": None,
                "ap_transactions": []
            }

            if m.bank_transaction:
                bt = m.bank_transaction
                match_data["bank_transaction"] = {
                    "id": bt.id,
                    "date": bt.transaction_date.isoformat() if bt.transaction_date else "",
                    "amount": float(bt.amount),
                    "description": bt.description or "",
                    "reference": bt.reference_number or "",
                    "check_number": bt.check_number or "",
                    "vendor_name": bt.vendor_name or ""
                }

            for ap in m.ap_transactions:
                match_data["ap_transactions"].append({
                    "id": ap.id,
                    "date": ap.payment_date.isoformat() if ap.payment_date else "",
                    "amount": float(ap.amount),
                    "paid_amount": float(ap.paid_amount),
                    "vendor_name": ap.vendor_name or "",
                    "bill_number": ap.bill_number or "",
                    "check_number": ap.check_number or ""
                })

            matches.append(match_data)

        return {"run_id": run_id, "matches": matches, "count": len(matches)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reconcile/{run_id}/exceptions")
async def get_exceptions_for_run(run_id: str):
    """Get exceptions for a specific reconciliation run."""
    try:
        if run_id not in _recent_results:
            raise HTTPException(status_code=404, detail="Run not found or expired. Run a new reconciliation.")

        result = _recent_results[run_id]
        exceptions = []

        for e in result.exceptions:
            exc_data = {
                "exception_id": e.id,  # Using 'id' from ReconciliationException model
                "exception_type": e.exception_type.value if hasattr(e.exception_type, 'value') else str(e.exception_type),
                "severity": e.severity,
                "description": e.description,
                "suggested_action": e.suggested_action or "",
                "is_resolved": e.resolved,  # Using 'resolved' not 'is_resolved'
                "resolution_notes": e.resolution_notes,
                "created_at": e.created_at.isoformat() if e.created_at else ""
            }

            # Check for bank_transaction
            if e.bank_transaction:
                bt = e.bank_transaction
                exc_data["bank_transaction"] = {
                    "id": bt.id,
                    "date": bt.transaction_date.isoformat() if bt.transaction_date else "",
                    "amount": float(bt.amount),
                    "description": bt.description or "",
                    "vendor_name": bt.vendor_name or ""
                }

            # Check for ap_transaction
            if e.ap_transaction:
                ap = e.ap_transaction
                exc_data["ap_transaction"] = {
                    "id": ap.id,
                    "date": ap.payment_date.isoformat() if ap.payment_date else "",
                    "amount": float(ap.amount),
                    "vendor_name": ap.vendor_name or "",
                    "bill_number": ap.bill_number or ""
                }

            exceptions.append(exc_data)

        return {"run_id": run_id, "exceptions": exceptions, "count": len(exceptions)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/exceptions", response_model=List[ExceptionDetail])
async def get_exceptions(
    run_id: Optional[str] = None,
    exception_type: Optional[str] = None,
    unresolved_only: bool = False
):
    """Get exceptions, optionally filtered."""
    try:
        # Try to get from recent results first
        if run_id and run_id in _recent_results:
            result = _recent_results[run_id]
            exceptions = result.exceptions
        elif _recent_results:
            # Get from most recent result
            run_id = list(_recent_results.keys())[-1]
            exceptions = _recent_results[run_id].exceptions
        else:
            return []

        # Filter
        if exception_type:
            exceptions = [e for e in exceptions if (e.exception_type.value if hasattr(e.exception_type, 'value') else str(e.exception_type)) == exception_type]
        if unresolved_only:
            exceptions = [e for e in exceptions if not e.resolved]

        result_list = []
        for e in exceptions:
            # Get transaction info - could be bank or ap transaction
            txn = e.bank_transaction or e.ap_transaction
            txn_id = ""
            txn_date = ""
            txn_amount = 0.0

            if e.bank_transaction:
                txn_id = e.bank_transaction.id
                txn_date = e.bank_transaction.transaction_date.isoformat() if e.bank_transaction.transaction_date else ""
                txn_amount = float(e.bank_transaction.amount)
            elif e.ap_transaction:
                txn_id = e.ap_transaction.id
                txn_date = e.ap_transaction.payment_date.isoformat() if e.ap_transaction.payment_date else ""
                txn_amount = float(e.ap_transaction.amount)

            result_list.append(ExceptionDetail(
                exception_id=e.id,
                exception_type=e.exception_type.value if hasattr(e.exception_type, 'value') else str(e.exception_type),
                severity=e.severity if isinstance(e.severity, str) else (e.severity.value if hasattr(e.severity, 'value') else str(e.severity)),
                transaction_id=txn_id,
                transaction_date=txn_date,
                amount=txn_amount,
                description=e.description,
                suggested_action=e.suggested_action or "",
                is_resolved=e.resolved,
                resolution_notes=e.resolution_notes
            ))

        return result_list
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/exceptions/{exception_id}/resolve")
async def resolve_exception(exception_id: str, request: ResolveExceptionRequest):
    """Resolve an exception."""
    try:
        reconciler = get_reconciler()
        success = reconciler.resolve_exception(exception_id, request.resolution_notes)

        if not success:
            raise HTTPException(status_code=404, detail="Exception not found")

        return {"status": "resolved", "exception_id": exception_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------ Report Endpoints ------------

@app.get("/api/reports/{run_id}/{format}")
async def get_report(run_id: str, format: str):
    """Download a report file."""
    try:
        # First check in-memory results
        if run_id in _recent_results:
            result = _recent_results[run_id]
            if hasattr(result, 'report_paths') and format in result.report_paths:
                path = result.report_paths[format]
                if Path(path).exists():
                    return FileResponse(
                        path,
                        filename=Path(path).name,
                        media_type="application/octet-stream"
                    )

        # Fall back to database lookup
        reconciler = get_reconciler()
        run_details = reconciler.get_run_details(run_id)

        if not run_details:
            raise HTTPException(status_code=404, detail="Run not found")

        # Check for report paths in the details
        report_paths = run_details.get('report_paths', {})
        if format not in report_paths:
            raise HTTPException(status_code=404, detail=f"Report format '{format}' not found")

        path = report_paths[format]
        if not Path(path).exists():
            raise HTTPException(status_code=404, detail="Report file not found")

        return FileResponse(
            path,
            filename=Path(path).name,
            media_type="application/octet-stream"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Run with: uvicorn src.api:app --reload --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
