"""
Tests for data models.
"""
import pytest
from datetime import date, datetime
from decimal import Decimal

from src.models import (
    BankTransaction, APTransaction, ReconciliationMatch,
    ReconciliationException, TransactionType, MatchStatus, ExceptionType
)


class TestBankTransaction:
    """Tests for BankTransaction model."""

    def test_create_bank_transaction(self, sample_bank_transaction):
        """Test creating a bank transaction."""
        assert sample_bank_transaction.id == "BANK-001"
        assert sample_bank_transaction.amount == Decimal("-1500.00")
        assert sample_bank_transaction.check_number == "12345"

    def test_is_payment(self, sample_bank_transaction):
        """Test payment detection."""
        assert sample_bank_transaction.is_payment() is True

    def test_is_deposit(self, sample_bank_transaction):
        """Test deposit detection."""
        assert sample_bank_transaction.is_deposit() is False

    def test_deposit_transaction(self):
        """Test a deposit transaction."""
        deposit = BankTransaction(
            id="DEP-001",
            transaction_date=date.today(),
            amount=Decimal("5000.00"),
            description="Customer payment",
            transaction_type=TransactionType.DEPOSIT
        )
        assert deposit.is_deposit() is True
        assert deposit.is_payment() is False


class TestAPTransaction:
    """Tests for APTransaction model."""

    def test_create_ap_transaction(self, sample_ap_transaction):
        """Test creating an AP transaction."""
        assert sample_ap_transaction.id == "AP-001"
        assert sample_ap_transaction.vendor_name == "Acme Corp"
        assert sample_ap_transaction.paid_amount == Decimal("1500.00")

    def test_is_paid(self, sample_ap_transaction):
        """Test paid status."""
        assert sample_ap_transaction.is_paid() is True

    def test_unpaid_transaction(self):
        """Test unpaid AP transaction."""
        unpaid = APTransaction(
            id="AP-002",
            vendor_id="V-002",
            vendor_name="Test Vendor",
            amount=Decimal("500.00"),
            state="Posted"
        )
        assert unpaid.is_paid() is False


class TestReconciliationMatch:
    """Tests for ReconciliationMatch model."""

    def test_create_match(self, sample_match):
        """Test creating a reconciliation match."""
        assert sample_match.id == "MATCH-001"
        assert sample_match.confidence_score == 0.98
        assert sample_match.match_status == MatchStatus.MATCHED

    def test_bank_amount(self, sample_match):
        """Test bank amount property."""
        assert sample_match.bank_amount == Decimal("1500.00")

    def test_ap_total(self, sample_match):
        """Test AP total property."""
        assert sample_match.ap_total == Decimal("1500.00")

    def test_variance(self, sample_match):
        """Test variance calculation."""
        assert sample_match.variance == Decimal("0.00")

    def test_variance_with_mismatch(self, sample_bank_transaction):
        """Test variance with amount mismatch."""
        ap = APTransaction(
            id="AP-002",
            vendor_id="V-002",
            vendor_name="Test",
            paid_amount=Decimal("1400.00")
        )
        match = ReconciliationMatch(
            bank_transaction=sample_bank_transaction,
            ap_transactions=[ap]
        )
        assert match.variance == Decimal("100.00")


class TestReconciliationException:
    """Tests for ReconciliationException model."""

    def test_create_exception(self, sample_exception):
        """Test creating an exception."""
        assert sample_exception.id == "EXC-001"
        assert sample_exception.exception_type == ExceptionType.MISSING_AP_RECORD
        assert sample_exception.severity == "medium"
        assert sample_exception.resolved is False

    def test_exception_types(self):
        """Test all exception types exist."""
        assert ExceptionType.AMOUNT_MISMATCH.value == "amount_mismatch"
        assert ExceptionType.DATE_MISMATCH.value == "date_mismatch"
        assert ExceptionType.DUPLICATE_PAYMENT.value == "duplicate_payment"
        assert ExceptionType.MISSING_AP_RECORD.value == "missing_ap_record"
        assert ExceptionType.MISSING_BANK_RECORD.value == "missing_bank_record"


class TestTransactionType:
    """Tests for TransactionType enum."""

    def test_transaction_types(self):
        """Test all transaction types exist."""
        assert TransactionType.CHECK.value == "check"
        assert TransactionType.ACH.value == "ach"
        assert TransactionType.WIRE.value == "wire"
        assert TransactionType.CARD.value == "card"
        assert TransactionType.DEPOSIT.value == "deposit"


class TestMatchStatus:
    """Tests for MatchStatus enum."""

    def test_match_statuses(self):
        """Test all match statuses exist."""
        assert MatchStatus.MATCHED.value == "matched"
        assert MatchStatus.PARTIAL_MATCH.value == "partial_match"
        assert MatchStatus.UNMATCHED.value == "unmatched"
        assert MatchStatus.EXCEPTION.value == "exception"
