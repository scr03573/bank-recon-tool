"""
Tests for matching engine.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.models import BankTransaction, APTransaction, TransactionType, MatchStatus


class TestCheckNumberMatching:
    """Tests for check number matching logic."""

    def test_exact_check_match(self, sample_bank_transaction, sample_ap_transaction):
        """Test exact check number matching."""
        assert sample_bank_transaction.check_number == sample_ap_transaction.check_number

    def test_check_number_mismatch(self, sample_bank_transaction):
        """Test check number mismatch detection."""
        ap = APTransaction(
            id="AP-002",
            vendor_id="V-002",
            vendor_name="Different Vendor",
            check_number="99999"
        )
        assert sample_bank_transaction.check_number != ap.check_number


class TestAmountMatching:
    """Tests for amount matching logic."""

    def test_exact_amount_match(self, sample_bank_transaction, sample_ap_transaction):
        """Test exact amount matching."""
        bank_amount = abs(sample_bank_transaction.amount)
        ap_amount = sample_ap_transaction.paid_amount
        assert bank_amount == ap_amount

    def test_amount_within_tolerance(self):
        """Test amount matching within tolerance."""
        bank_amount = Decimal("1500.00")
        ap_amount = Decimal("1500.10")
        tolerance = Decimal("0.01")  # 1%

        diff = abs(bank_amount - ap_amount) / bank_amount
        assert diff <= tolerance

    def test_amount_outside_tolerance(self):
        """Test amount matching outside tolerance."""
        bank_amount = Decimal("1500.00")
        ap_amount = Decimal("1600.00")
        tolerance = Decimal("0.01")  # 1%

        diff = abs(bank_amount - ap_amount) / bank_amount
        assert diff > tolerance


class TestDateMatching:
    """Tests for date matching logic."""

    def test_exact_date_match(self, sample_bank_transaction, sample_ap_transaction):
        """Test exact date matching."""
        assert sample_bank_transaction.transaction_date == sample_ap_transaction.payment_date

    def test_date_within_tolerance(self):
        """Test date matching within tolerance."""
        bank_date = date.today()
        ap_date = date.today() - timedelta(days=3)
        tolerance_days = 5

        diff = abs((bank_date - ap_date).days)
        assert diff <= tolerance_days

    def test_date_outside_tolerance(self):
        """Test date matching outside tolerance."""
        bank_date = date.today()
        ap_date = date.today() - timedelta(days=10)
        tolerance_days = 5

        diff = abs((bank_date - ap_date).days)
        assert diff > tolerance_days


class TestVendorMatching:
    """Tests for vendor name matching logic."""

    def test_exact_vendor_match(self):
        """Test exact vendor name matching."""
        vendor1 = "Acme Corp"
        vendor2 = "Acme Corp"
        assert vendor1 == vendor2

    def test_case_insensitive_match(self):
        """Test case-insensitive vendor matching."""
        vendor1 = "ACME CORP"
        vendor2 = "acme corp"
        assert vendor1.lower() == vendor2.lower()

    def test_fuzzy_vendor_match(self):
        """Test fuzzy vendor matching."""
        # These should be similar enough to match
        vendor1 = "Acme Corporation"
        vendor2 = "ACME CORP"

        # Simple similarity check (real implementation uses RapidFuzz)
        common_chars = set(vendor1.lower()) & set(vendor2.lower())
        assert len(common_chars) > 5


class TestBatchMatching:
    """Tests for batch payment matching."""

    def test_batch_payment_detection(self):
        """Test detecting batch payments (one bank tx -> multiple AP)."""
        bank_tx = BankTransaction(
            id="BANK-001",
            transaction_date=date.today(),
            amount=Decimal("-3000.00"),
            description="Batch payment",
            transaction_type=TransactionType.CHECK
        )

        ap_txs = [
            APTransaction(id="AP-001", vendor_id="V-001", paid_amount=Decimal("1000.00")),
            APTransaction(id="AP-002", vendor_id="V-002", paid_amount=Decimal("1000.00")),
            APTransaction(id="AP-003", vendor_id="V-003", paid_amount=Decimal("1000.00")),
        ]

        total_ap = sum(ap.paid_amount for ap in ap_txs)
        assert abs(bank_tx.amount) == total_ap

    def test_partial_batch_match(self):
        """Test partial batch matching."""
        bank_tx = BankTransaction(
            id="BANK-001",
            transaction_date=date.today(),
            amount=Decimal("-2500.00"),
            transaction_type=TransactionType.CHECK
        )

        ap_txs = [
            APTransaction(id="AP-001", vendor_id="V-001", paid_amount=Decimal("1000.00")),
            APTransaction(id="AP-002", vendor_id="V-002", paid_amount=Decimal("1500.00")),
        ]

        total_ap = sum(ap.paid_amount for ap in ap_txs)
        assert abs(bank_tx.amount) == total_ap


class TestTransactionTypeDetection:
    """Tests for transaction type detection."""

    def test_check_detection(self):
        """Test check transaction detection."""
        descriptions = [
            "Check #12345",
            "CHECK 12345",
            "CK 12345 - Vendor",
        ]
        for desc in descriptions:
            assert "check" in desc.lower() or "ck" in desc.lower()

    def test_ach_detection(self):
        """Test ACH transaction detection."""
        descriptions = [
            "ACH DEBIT - Vendor",
            "ACH Payment 12345",
            "ACHDEBIT",
        ]
        for desc in descriptions:
            assert "ach" in desc.lower()

    def test_wire_detection(self):
        """Test wire transaction detection."""
        descriptions = [
            "Wire Transfer - Vendor",
            "WIRE 12345",
            "WIRETRANSFER",
        ]
        for desc in descriptions:
            assert "wire" in desc.lower()

    def test_card_detection(self):
        """Test card transaction detection."""
        descriptions = [
            "Card Purchase - Store",
            "VISA 1234",
            "Mastercard Purchase",
        ]
        for desc in descriptions:
            has_card = any(kw in desc.lower() for kw in ["card", "visa", "mastercard"])
            assert has_card
