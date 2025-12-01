"""
Pytest fixtures for bank reconciliation tests.
"""
import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
import tempfile
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.models import (
    BankTransaction, APTransaction, ReconciliationMatch,
    ReconciliationException, TransactionType, MatchStatus, ExceptionType
)


@pytest.fixture
def sample_bank_transaction():
    """Create a sample bank transaction."""
    return BankTransaction(
        id="BANK-001",
        transaction_date=date.today(),
        post_date=date.today(),
        amount=Decimal("-1500.00"),
        description="Check #12345 - Acme Corp",
        reference_number="12345",
        check_number="12345",
        transaction_type=TransactionType.CHECK,
        bank_account_id="CHECKING-001",
        vendor_name="Acme Corp"
    )


@pytest.fixture
def sample_ap_transaction():
    """Create a sample AP transaction."""
    return APTransaction(
        id="AP-001",
        record_number="AP-2024-001",
        vendor_id="V-001",
        vendor_name="Acme Corp",
        bill_number="INV-12345",
        payment_date=date.today(),
        due_date=date.today() - timedelta(days=30),
        amount=Decimal("1500.00"),
        paid_amount=Decimal("1500.00"),
        payment_method="check",
        check_number="12345",
        bank_account_id="CHECKING-001",
        description="Monthly service fee",
        state="Paid"
    )


@pytest.fixture
def sample_bank_transactions():
    """Create a list of sample bank transactions for testing."""
    base_date = date.today()
    return [
        BankTransaction(
            id=f"BANK-{i:03d}",
            transaction_date=base_date - timedelta(days=i),
            post_date=base_date - timedelta(days=i),
            amount=Decimal(f"-{1000 + i * 100}.00"),
            description=f"Check #{50000 + i} - Vendor {i}",
            reference_number=str(50000 + i),
            check_number=str(50000 + i),
            transaction_type=TransactionType.CHECK,
            bank_account_id="CHECKING-001",
            vendor_name=f"Vendor {i}"
        )
        for i in range(10)
    ]


@pytest.fixture
def sample_ap_transactions():
    """Create a list of sample AP transactions for testing."""
    base_date = date.today()
    return [
        APTransaction(
            id=f"AP-{i:03d}",
            record_number=f"AP-2024-{i:03d}",
            vendor_id=f"V-{i:03d}",
            vendor_name=f"Vendor {i}",
            bill_number=f"INV-{i:05d}",
            payment_date=base_date - timedelta(days=i),
            due_date=base_date - timedelta(days=i + 30),
            amount=Decimal(f"{1000 + i * 100}.00"),
            paid_amount=Decimal(f"{1000 + i * 100}.00"),
            payment_method="check",
            check_number=str(50000 + i),
            bank_account_id="CHECKING-001",
            description=f"Invoice {i}",
            state="Paid"
        )
        for i in range(10)
    ]


@pytest.fixture
def sample_match(sample_bank_transaction, sample_ap_transaction):
    """Create a sample reconciliation match."""
    return ReconciliationMatch(
        id="MATCH-001",
        bank_transaction=sample_bank_transaction,
        ap_transactions=[sample_ap_transaction],
        match_status=MatchStatus.MATCHED,
        confidence_score=0.98,
        match_reasons=["Check number exact match", "Amount match"],
        notes=""
    )


@pytest.fixture
def sample_exception(sample_bank_transaction):
    """Create a sample reconciliation exception."""
    return ReconciliationException(
        id="EXC-001",
        exception_type=ExceptionType.MISSING_AP_RECORD,
        bank_transaction=sample_bank_transaction,
        ap_transaction=None,
        description="No AP record found for bank transaction",
        severity="medium",
        suggested_action="Check for unrecorded AP entry",
        created_at=datetime.now(),
        resolved=False,
        resolution_notes=""
    )


@pytest.fixture
def temp_csv_file():
    """Create a temporary CSV file for bank transactions."""
    content = """Date,Description,Amount,Reference,Check Number
2024-01-15,Check #12345 - Acme Corp,-1500.00,12345,12345
2024-01-14,ACH DEBIT - Utility Co,-250.00,ACH123,
2024-01-13,Wire Transfer - Vendor XYZ,-5000.00,WIRE456,
2024-01-12,Card Purchase - Office Depot,-89.99,CARD789,
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    class MockMatchingConfig:
        fuzzy_threshold = 85
        date_tolerance_days = 5
        amount_tolerance_percent = 0.01

    class MockMarketDataConfig:
        fred_api_key = None
        intrinio_api_key = None
        data_priority = "yfinance_first"

        def is_fred_configured(self):
            return False

        def is_intrinio_configured(self):
            return False

    class MockIntacctConfig:
        def is_configured(self):
            return False

    class MockConfig:
        matching = MockMatchingConfig()
        market_data = MockMarketDataConfig()
        intacct = MockIntacctConfig()
        fred_api_key = None

    return MockConfig()
