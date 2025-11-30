"""Data models for bank reconciliation."""
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List
import uuid


class TransactionType(Enum):
    """Transaction type classification."""
    CHECK = "check"
    ACH = "ach"
    WIRE = "wire"
    CARD = "card"
    DEPOSIT = "deposit"
    FEE = "fee"
    INTEREST = "interest"
    TRANSFER = "transfer"
    OTHER = "other"


class MatchStatus(Enum):
    """Reconciliation match status."""
    MATCHED = "matched"
    PARTIAL_MATCH = "partial_match"
    UNMATCHED = "unmatched"
    EXCEPTION = "exception"
    MANUAL_REVIEW = "manual_review"


class ExceptionType(Enum):
    """Types of reconciliation exceptions."""
    AMOUNT_MISMATCH = "amount_mismatch"
    DATE_MISMATCH = "date_mismatch"
    DUPLICATE_PAYMENT = "duplicate_payment"
    MISSING_AP_RECORD = "missing_ap_record"
    MISSING_BANK_RECORD = "missing_bank_record"
    VENDOR_MISMATCH = "vendor_mismatch"
    STALE_CHECK = "stale_check"
    REVERSAL = "reversal"


@dataclass
class BankTransaction:
    """Represents a bank transaction from the feed."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    transaction_date: date = None
    post_date: date = None
    amount: Decimal = Decimal("0")
    description: str = ""
    reference_number: Optional[str] = None
    check_number: Optional[str] = None
    transaction_type: TransactionType = TransactionType.OTHER
    bank_account_id: str = ""
    raw_data: dict = field(default_factory=dict)

    # Extracted/normalized fields
    vendor_name: Optional[str] = None
    memo: Optional[str] = None

    # Reconciliation status
    match_status: MatchStatus = MatchStatus.UNMATCHED
    matched_ap_ids: List[str] = field(default_factory=list)
    match_confidence: float = 0.0

    def is_payment(self) -> bool:
        """Check if this is an outgoing payment."""
        return self.amount < 0

    def is_deposit(self) -> bool:
        """Check if this is incoming money."""
        return self.amount > 0


@dataclass
class APTransaction:
    """Represents an AP transaction from Sage Intacct."""
    id: str = ""
    record_number: str = ""
    vendor_id: str = ""
    vendor_name: str = ""
    bill_number: Optional[str] = None
    payment_date: Optional[date] = None
    due_date: Optional[date] = None
    amount: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    payment_method: Optional[str] = None
    check_number: Optional[str] = None
    ach_reference: Optional[str] = None
    bank_account_id: str = ""
    description: str = ""
    state: str = ""  # e.g., "Paid", "Posted", "Void"

    # Reconciliation status
    match_status: MatchStatus = MatchStatus.UNMATCHED
    matched_bank_ids: List[str] = field(default_factory=list)
    match_confidence: float = 0.0

    def is_paid(self) -> bool:
        return self.state.lower() == "paid"


@dataclass
class ReconciliationMatch:
    """Represents a matched pair of transactions."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    bank_transaction: BankTransaction = None
    ap_transactions: List[APTransaction] = field(default_factory=list)
    match_status: MatchStatus = MatchStatus.UNMATCHED
    confidence_score: float = 0.0
    match_reasons: List[str] = field(default_factory=list)
    exceptions: List[ExceptionType] = field(default_factory=list)
    notes: str = ""
    reviewed: bool = False
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None

    @property
    def bank_amount(self) -> Decimal:
        return abs(self.bank_transaction.amount) if self.bank_transaction else Decimal("0")

    @property
    def ap_total(self) -> Decimal:
        return sum(ap.paid_amount for ap in self.ap_transactions)

    @property
    def variance(self) -> Decimal:
        return self.bank_amount - self.ap_total


@dataclass
class ReconciliationException:
    """An exception requiring manual review."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    exception_type: ExceptionType = ExceptionType.AMOUNT_MISMATCH
    bank_transaction: Optional[BankTransaction] = None
    ap_transaction: Optional[APTransaction] = None
    description: str = ""
    severity: str = "medium"  # low, medium, high, critical
    suggested_action: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    resolved: bool = False
    resolution_notes: str = ""


@dataclass
class ReconciliationSummary:
    """Summary of a reconciliation run."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_date: datetime = field(default_factory=datetime.now)
    period_start: date = None
    period_end: date = None
    bank_account_id: str = ""

    # Counts
    total_bank_transactions: int = 0
    total_ap_transactions: int = 0
    matched_count: int = 0
    partial_match_count: int = 0
    unmatched_bank_count: int = 0
    unmatched_ap_count: int = 0
    exception_count: int = 0

    # Amounts
    total_bank_amount: Decimal = Decimal("0")
    total_ap_amount: Decimal = Decimal("0")
    matched_amount: Decimal = Decimal("0")
    unreconciled_amount: Decimal = Decimal("0")

    # Economic context
    fed_funds_rate: Optional[float] = None
    treasury_yield_10y: Optional[float] = None
    market_volatility: Optional[float] = None

    # Performance
    auto_match_rate: float = 0.0
    processing_time_seconds: float = 0.0