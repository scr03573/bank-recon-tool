"""
Main reconciliation orchestrator.

Coordinates all components to perform bank reconciliation:
1. Fetch/parse data from sources
2. Run matching engine
3. Generate reports
4. Track audit history
"""
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import sqlite3
import json

from .config import config
from .models import (
    BankTransaction, APTransaction, ReconciliationMatch,
    ReconciliationException, ReconciliationSummary, MatchStatus
)
from .intacct_client import IntacctClient, MockIntacctClient
from .bank_parser import BankDataParser
from .matching_engine import MatchingEngine
from .economic_context import EconomicDataProvider, EconomicSnapshot
from .reporting import ReportGenerator


@dataclass
class ReconciliationResult:
    """Complete result of a reconciliation run."""
    summary: ReconciliationSummary
    matches: List[ReconciliationMatch]
    exceptions: List[ReconciliationException]
    economic_snapshot: Optional[EconomicSnapshot]
    report_paths: Dict[str, Path]


class BankReconciler:
    """
    Main reconciliation engine that orchestrates all components.

    Usage:
        reconciler = BankReconciler()
        result = reconciler.reconcile(
            bank_file="bank_transactions.csv",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31)
        )
    """

    def __init__(
        self,
        intacct_client: Optional[IntacctClient] = None,
        use_mock_intacct: bool = False
    ):
        self.intacct = intacct_client or (MockIntacctClient() if use_mock_intacct else IntacctClient())
        self.bank_parser = BankDataParser()
        self.matching_engine = MatchingEngine()
        self.economic_provider = EconomicDataProvider()
        self.report_generator = ReportGenerator()

        # Initialize database
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database for audit trail."""
        db_path = Path(config.database_url.replace("sqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self.db = sqlite3.connect(str(db_path))
        self._create_tables()

    def _create_tables(self):
        """Create database tables for reconciliation history."""
        cursor = self.db.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reconciliation_runs (
                id TEXT PRIMARY KEY,
                run_date TIMESTAMP,
                period_start DATE,
                period_end DATE,
                bank_account_id TEXT,
                total_bank_transactions INTEGER,
                total_ap_transactions INTEGER,
                matched_count INTEGER,
                exception_count INTEGER,
                auto_match_rate REAL,
                total_bank_amount REAL,
                total_ap_amount REAL,
                unreconciled_amount REAL,
                processing_time_seconds REAL,
                status TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS match_history (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                bank_transaction_id TEXT,
                ap_transaction_ids TEXT,
                match_status TEXT,
                confidence_score REAL,
                variance REAL,
                match_reasons TEXT,
                reviewed INTEGER DEFAULT 0,
                reviewed_by TEXT,
                reviewed_at TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES reconciliation_runs(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exception_history (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                exception_type TEXT,
                severity TEXT,
                description TEXT,
                bank_transaction_id TEXT,
                ap_transaction_id TEXT,
                resolved INTEGER DEFAULT 0,
                resolution_notes TEXT,
                created_at TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES reconciliation_runs(id)
            )
        """)

        self.db.commit()

    def reconcile(
        self,
        bank_file: Optional[Path] = None,
        bank_transactions: Optional[List[BankTransaction]] = None,
        ap_transactions: Optional[List[APTransaction]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        bank_account_id: str = "",
        generate_reports: bool = True,
        report_formats: List[str] = None
    ) -> ReconciliationResult:
        """
        Perform bank reconciliation.

        Args:
            bank_file: Path to bank transaction file (CSV, Excel, OFX)
            bank_transactions: Pre-loaded bank transactions (alternative to file)
            ap_transactions: Pre-loaded AP transactions (skips Intacct fetch)
            start_date: Period start date
            end_date: Period end date
            bank_account_id: Bank account identifier
            generate_reports: Whether to generate reports
            report_formats: Report formats to generate ("excel", "json", "html")

        Returns:
            ReconciliationResult with summary, matches, exceptions, and report paths
        """
        start_time = time.time()

        # Default dates
        end_date = end_date or date.today()
        start_date = start_date or (end_date - timedelta(days=30))
        report_formats = report_formats or ["excel", "html"]

        # Initialize summary
        summary = ReconciliationSummary(
            period_start=start_date,
            period_end=end_date,
            bank_account_id=bank_account_id
        )

        # Step 1: Load bank transactions
        if bank_transactions is None:
            if bank_file:
                bank_transactions = self.bank_parser.parse_file(Path(bank_file))
                bank_transactions = self.bank_parser.normalize_transactions(bank_transactions)
            else:
                bank_transactions = []

        # Filter by date range
        bank_transactions = [
            tx for tx in bank_transactions
            if tx.transaction_date and start_date <= tx.transaction_date <= end_date
        ]

        summary.total_bank_transactions = len(bank_transactions)
        summary.total_bank_amount = sum(abs(tx.amount) for tx in bank_transactions if tx.is_payment())

        # Step 2: Load AP transactions
        if ap_transactions is None:
            if config.intacct.is_configured():
                ap_transactions = self.intacct.get_ap_payments(
                    start_date=start_date,
                    end_date=end_date,
                    bank_account_id=bank_account_id if bank_account_id else None
                )
            else:
                ap_transactions = []

        summary.total_ap_transactions = len(ap_transactions)
        summary.total_ap_amount = sum(tx.paid_amount for tx in ap_transactions if tx.is_paid())

        # Step 3: Run matching engine
        matches, exceptions = self.matching_engine.match_transactions(
            bank_transactions, ap_transactions
        )

        # Calculate summary metrics
        summary.matched_count = len([m for m in matches if m.match_status == MatchStatus.MATCHED])
        summary.partial_match_count = len([m for m in matches if m.match_status == MatchStatus.PARTIAL_MATCH])
        summary.exception_count = len(exceptions)

        matched_bank_ids = {m.bank_transaction.id for m in matches if m.bank_transaction}
        matched_ap_ids = {ap.id for m in matches for ap in m.ap_transactions}

        summary.unmatched_bank_count = len([
            tx for tx in bank_transactions
            if tx.id not in matched_bank_ids and tx.is_payment()
        ])
        summary.unmatched_ap_count = len([
            tx for tx in ap_transactions
            if tx.id not in matched_ap_ids and tx.is_paid()
        ])

        summary.matched_amount = sum(
            abs(m.bank_transaction.amount)
            for m in matches
            if m.bank_transaction and m.match_status in [MatchStatus.MATCHED, MatchStatus.PARTIAL_MATCH]
        )

        summary.unreconciled_amount = summary.total_bank_amount - summary.matched_amount

        if summary.total_bank_transactions > 0:
            summary.auto_match_rate = summary.matched_count / summary.total_bank_transactions

        # Step 4: Get economic context
        economic_snapshot = None
        try:
            economic_snapshot = self.economic_provider.get_snapshot(end_date)
            summary.fed_funds_rate = economic_snapshot.fed_funds_rate
            summary.treasury_yield_10y = economic_snapshot.treasury_10y
            summary.market_volatility = economic_snapshot.vix
        except Exception as e:
            print(f"Warning: Could not fetch economic data: {e}")

        # Calculate processing time
        summary.processing_time_seconds = time.time() - start_time

        # Step 5: Generate reports
        report_paths = {}
        if generate_reports:
            if "excel" in report_formats:
                report_paths["excel"] = self.report_generator.generate_excel_report(
                    summary, matches, exceptions, economic_snapshot
                )

            if "json" in report_formats:
                report_paths["json"] = self.report_generator.generate_json_report(
                    summary, matches, exceptions
                )

            if "html" in report_formats:
                report_paths["html"] = self.report_generator.generate_html_report(
                    summary, matches, exceptions, economic_snapshot
                )

        # Step 6: Save to database
        self._save_run(summary, matches, exceptions)

        return ReconciliationResult(
            summary=summary,
            matches=matches,
            exceptions=exceptions,
            economic_snapshot=economic_snapshot,
            report_paths=report_paths
        )

    def reconcile_from_dataframes(
        self,
        bank_df,
        ap_df,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        **kwargs
    ) -> ReconciliationResult:
        """
        Reconcile from pandas DataFrames.

        Useful for Jupyter notebooks or when data is already loaded.
        """
        import pandas as pd

        # Parse bank transactions
        bank_transactions = self.bank_parser.parse_dataframe(bank_df)
        bank_transactions = self.bank_parser.normalize_transactions(bank_transactions)

        # Parse AP transactions (simplified)
        ap_transactions = []
        for _, row in ap_df.iterrows():
            ap_tx = APTransaction(
                id=str(row.get("id", row.name)),
                vendor_id=str(row.get("vendor_id", "")),
                vendor_name=str(row.get("vendor_name", row.get("vendor", ""))),
                payment_date=pd.to_datetime(row.get("payment_date", row.get("date"))).date()
                    if pd.notna(row.get("payment_date", row.get("date"))) else None,
                paid_amount=Decimal(str(row.get("amount", row.get("paid_amount", 0)))),
                check_number=str(row.get("check_number", "")) if pd.notna(row.get("check_number")) else None,
                state="Paid"
            )
            ap_transactions.append(ap_tx)

        return self.reconcile(
            bank_transactions=bank_transactions,
            ap_transactions=ap_transactions,
            start_date=start_date,
            end_date=end_date,
            **kwargs
        )

    def get_reconciliation_history(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent reconciliation run history."""
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT * FROM reconciliation_runs
            ORDER BY run_date DESC
            LIMIT ?
        """, (limit,))

        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_run_details(self, run_id: str) -> Dict[str, Any]:
        """Get details of a specific reconciliation run."""
        cursor = self.db.cursor()

        # Get run summary
        cursor.execute("SELECT * FROM reconciliation_runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        if not row:
            return {}

        columns = [desc[0] for desc in cursor.description]
        result = dict(zip(columns, row))

        # Get matches
        cursor.execute("SELECT * FROM match_history WHERE run_id = ?", (run_id,))
        match_columns = [desc[0] for desc in cursor.description]
        result["matches"] = [dict(zip(match_columns, r)) for r in cursor.fetchall()]

        # Get exceptions
        cursor.execute("SELECT * FROM exception_history WHERE run_id = ?", (run_id,))
        exc_columns = [desc[0] for desc in cursor.description]
        result["exceptions"] = [dict(zip(exc_columns, r)) for r in cursor.fetchall()]

        return result

    def mark_match_reviewed(
        self,
        match_id: str,
        reviewed_by: str,
        notes: str = ""
    ):
        """Mark a match as manually reviewed."""
        cursor = self.db.cursor()
        cursor.execute("""
            UPDATE match_history
            SET reviewed = 1, reviewed_by = ?, reviewed_at = ?
            WHERE id = ?
        """, (reviewed_by, datetime.now(), match_id))
        self.db.commit()

    def resolve_exception(
        self,
        exception_id: str,
        resolution_notes: str
    ):
        """Mark an exception as resolved."""
        cursor = self.db.cursor()
        cursor.execute("""
            UPDATE exception_history
            SET resolved = 1, resolution_notes = ?
            WHERE id = ?
        """, (resolution_notes, exception_id))
        self.db.commit()

    def _save_run(
        self,
        summary: ReconciliationSummary,
        matches: List[ReconciliationMatch],
        exceptions: List[ReconciliationException]
    ):
        """Save reconciliation run to database."""
        cursor = self.db.cursor()

        # Save summary
        cursor.execute("""
            INSERT INTO reconciliation_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            summary.id,
            summary.run_date,
            summary.period_start,
            summary.period_end,
            summary.bank_account_id,
            summary.total_bank_transactions,
            summary.total_ap_transactions,
            summary.matched_count,
            summary.exception_count,
            summary.auto_match_rate,
            float(summary.total_bank_amount),
            float(summary.total_ap_amount),
            float(summary.unreconciled_amount),
            summary.processing_time_seconds,
            "completed"
        ))

        # Save matches
        for match in matches:
            cursor.execute("""
                INSERT INTO match_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                match.id,
                summary.id,
                match.bank_transaction.id if match.bank_transaction else None,
                json.dumps([ap.id for ap in match.ap_transactions]),
                match.match_status.value,
                match.confidence_score,
                float(match.variance),
                json.dumps(match.match_reasons),
                0,
                None,
                None
            ))

        # Save exceptions
        for exc in exceptions:
            cursor.execute("""
                INSERT INTO exception_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                exc.id,
                summary.id,
                exc.exception_type.value,
                exc.severity,
                exc.description,
                exc.bank_transaction.id if exc.bank_transaction else None,
                exc.ap_transaction.id if exc.ap_transaction else None,
                0,
                "",
                exc.created_at
            ))

        self.db.commit()

    def close(self):
        """Close database connection."""
        if self.db:
            self.db.close()


def create_sample_data() -> Tuple[List[BankTransaction], List[APTransaction]]:
    """Create sample data for testing."""
    from .bank_parser import create_sample_bank_data
    from decimal import Decimal
    import random

    # Generate bank transactions
    bank_df = create_sample_bank_data(30)
    parser = BankDataParser()
    bank_transactions = parser.parse_dataframe(bank_df)
    bank_transactions = parser.normalize_transactions(bank_transactions)

    # Generate corresponding AP transactions (with some matches and some mismatches)
    ap_transactions = []
    vendors = ["ACME Corp", "Office Depot", "Amazon Web Services", "AT&T", "Verizon"]

    for i, bank_tx in enumerate(bank_transactions[:20]):  # Create matches for 20 transactions
        ap_tx = APTransaction(
            id=f"AP-{i+1000}",
            record_number=f"{i+1000}",
            vendor_id=f"V-{i}",
            vendor_name=bank_tx.vendor_name or random.choice(vendors),
            payment_date=bank_tx.transaction_date,
            paid_amount=abs(bank_tx.amount) if random.random() > 0.1 else abs(bank_tx.amount) * Decimal("0.99"),
            check_number=bank_tx.check_number,
            state="Paid"
        )
        ap_transactions.append(ap_tx)

    # Add some unmatched AP transactions
    for i in range(5):
        ap_tx = APTransaction(
            id=f"AP-{i+2000}",
            record_number=f"{i+2000}",
            vendor_id=f"V-{i+100}",
            vendor_name=random.choice(vendors),
            payment_date=date.today() - timedelta(days=random.randint(1, 30)),
            paid_amount=Decimal(str(random.uniform(100, 5000))),
            state="Paid"
        )
        ap_transactions.append(ap_tx)

    return bank_transactions, ap_transactions
