"""Bank transaction data parser and normalizer."""
import csv
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd

from .models import BankTransaction, TransactionType


class BankParserError(Exception):
    """Raised when bank data parsing fails."""
    pass


class BankDataParser:
    """
    Parser for bank transaction data.

    Supports multiple formats:
    - CSV exports from major banks
    - Intacct bank feed format
    - OFX/QFX files (simplified)
    - Excel files
    """

    # Common column name mappings
    COLUMN_MAPPINGS = {
        "date": ["date", "transaction_date", "trans_date", "posting_date", "post_date", "value_date", "txn_date"],
        "amount": ["amount", "transaction_amount", "trans_amount", "debit", "credit", "value"],
        "description": ["description", "memo", "narrative", "details", "transaction_description", "payee", "name"],
        "reference": ["reference", "ref", "reference_number", "check_number", "cheque_number", "trace_number"],
        "type": ["type", "transaction_type", "trans_type", "category"],
        "balance": ["balance", "running_balance", "available_balance"],
    }

    # Transaction type detection patterns
    TYPE_PATTERNS = {
        TransactionType.CHECK: [
            r"\bcheck\b", r"\bcheque\b", r"\bchk\b", r"check\s*#?\s*\d+",
        ],
        TransactionType.ACH: [
            r"\bach\b", r"ach\s*(credit|debit)", r"electronic\s*(payment|transfer)",
            r"direct\s*(deposit|debit)", r"autopay", r"auto\s*pay",
        ],
        TransactionType.WIRE: [
            r"\bwire\b", r"wire\s*(transfer|in|out)", r"incoming\s*wire", r"outgoing\s*wire",
        ],
        TransactionType.CARD: [
            r"\bcard\b", r"visa\b", r"mastercard\b", r"amex\b", r"debit\s*card",
            r"pos\b", r"point\s*of\s*sale", r"purchase\b",
        ],
        TransactionType.FEE: [
            r"\bfee\b", r"service\s*charge", r"maintenance\s*fee", r"overdraft",
            r"nsf\b", r"returned\s*item",
        ],
        TransactionType.INTEREST: [
            r"\binterest\b", r"int\s*(paid|earned)", r"interest\s*(credit|debit)",
        ],
        TransactionType.TRANSFER: [
            r"\btransfer\b", r"xfer\b", r"internal\s*transfer", r"account\s*transfer",
        ],
        TransactionType.DEPOSIT: [
            r"\bdeposit\b", r"dep\b", r"remote\s*deposit", r"mobile\s*deposit",
        ],
    }

    # Vendor extraction patterns
    VENDOR_PATTERNS = [
        r"(?:payee|to|from|vendor)[:\s]+([A-Za-z0-9\s&.,'-]+)",
        r"(?:payment\s+to|paid\s+to)[:\s]+([A-Za-z0-9\s&.,'-]+)",
        r"^([A-Z][A-Za-z0-9\s&.,'-]{2,30})(?:\s+\d|$)",  # Starting vendor name
    ]

    def __init__(self):
        self._vendor_cache: Dict[str, str] = {}

    def parse_file(self, file_path: Path, format_hint: Optional[str] = None) -> List[BankTransaction]:
        """
        Parse a bank transaction file.

        Args:
            file_path: Path to the file
            format_hint: Optional format hint ("csv", "xlsx", "ofx", "intacct")

        Returns:
            List of BankTransaction objects
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise BankParserError(f"File not found: {file_path}")

        # Determine format
        suffix = file_path.suffix.lower()
        format_type = format_hint or self._detect_format(file_path, suffix)

        if format_type == "csv":
            return self._parse_csv(file_path)
        elif format_type == "xlsx":
            return self._parse_excel(file_path)
        elif format_type == "ofx":
            return self._parse_ofx(file_path)
        elif format_type == "intacct":
            return self._parse_intacct_export(file_path)
        else:
            raise BankParserError(f"Unsupported file format: {suffix}")

    def parse_dataframe(self, df: pd.DataFrame, bank_account_id: str = "") -> List[BankTransaction]:
        """Parse bank transactions from a pandas DataFrame."""
        # Normalize column names
        df.columns = [self._normalize_column_name(col) for col in df.columns]

        # Map columns
        column_map = self._map_columns(df.columns.tolist())

        transactions = []
        for idx, row in df.iterrows():
            try:
                tx = self._row_to_transaction(row, column_map, bank_account_id)
                if tx:
                    transactions.append(tx)
            except Exception as e:
                print(f"Warning: Failed to parse row {idx}: {e}")

        return transactions

    def normalize_transactions(self, transactions: List[BankTransaction]) -> List[BankTransaction]:
        """Apply normalization rules to transactions."""
        for tx in transactions:
            # Detect transaction type if not set
            if tx.transaction_type == TransactionType.OTHER:
                tx.transaction_type = self._detect_transaction_type(tx.description)

            # Extract check number if present
            if not tx.check_number and tx.transaction_type == TransactionType.CHECK:
                tx.check_number = self._extract_check_number(tx.description)

            # Extract vendor name
            if not tx.vendor_name:
                tx.vendor_name = self._extract_vendor(tx.description)

            # Normalize description
            tx.description = self._normalize_description(tx.description)

        return transactions

    def _parse_csv(self, file_path: Path) -> List[BankTransaction]:
        """Parse CSV bank export."""
        # Try different encodings
        for encoding in ["utf-8", "latin-1", "cp1252"]:
            try:
                df = pd.read_csv(file_path, encoding=encoding)
                return self.parse_dataframe(df, bank_account_id=file_path.stem)
            except UnicodeDecodeError:
                continue
            except Exception as e:
                raise BankParserError(f"Failed to parse CSV: {e}")

        raise BankParserError("Could not decode CSV file with any supported encoding")

    def _parse_excel(self, file_path: Path) -> List[BankTransaction]:
        """Parse Excel bank export."""
        try:
            df = pd.read_excel(file_path)
            return self.parse_dataframe(df, bank_account_id=file_path.stem)
        except Exception as e:
            raise BankParserError(f"Failed to parse Excel file: {e}")

    def _parse_ofx(self, file_path: Path) -> List[BankTransaction]:
        """Parse OFX/QFX file (simplified parser)."""
        transactions = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read()

        # Extract STMTTRN blocks
        tx_pattern = r"<STMTTRN>(.*?)</STMTTRN>"
        matches = re.findall(tx_pattern, content, re.DOTALL | re.IGNORECASE)

        for match in matches:
            tx = BankTransaction()

            # Extract fields
            fields = {
                "TRNTYPE": r"<TRNTYPE>([^<\n]+)",
                "DTPOSTED": r"<DTPOSTED>([^<\n]+)",
                "TRNAMT": r"<TRNAMT>([^<\n]+)",
                "NAME": r"<NAME>([^<\n]+)",
                "MEMO": r"<MEMO>([^<\n]+)",
                "FITID": r"<FITID>([^<\n]+)",
                "CHECKNUM": r"<CHECKNUM>([^<\n]+)",
            }

            for field, pattern in fields.items():
                field_match = re.search(pattern, match, re.IGNORECASE)
                if field_match:
                    value = field_match.group(1).strip()
                    if field == "DTPOSTED":
                        tx.transaction_date = self._parse_ofx_date(value)
                        tx.post_date = tx.transaction_date
                    elif field == "TRNAMT":
                        tx.amount = self._parse_amount(value)
                    elif field == "NAME":
                        tx.description = value
                        tx.vendor_name = value
                    elif field == "MEMO":
                        tx.memo = value
                    elif field == "FITID":
                        tx.id = value
                    elif field == "CHECKNUM":
                        tx.check_number = value

            if tx.transaction_date and tx.amount:
                transactions.append(tx)

        return self.normalize_transactions(transactions)

    def _parse_intacct_export(self, file_path: Path) -> List[BankTransaction]:
        """Parse Intacct bank feed export."""
        # Intacct exports are typically CSV with specific column names
        df = pd.read_csv(file_path)

        # Intacct-specific column mapping
        intacct_map = {
            "ENTRY_DATE": "date",
            "AMOUNT": "amount",
            "DESCRIPTION": "description",
            "REFERENCENO": "reference",
            "DOCNUMBER": "check_number",
            "BANKACCOUNTID": "bank_account_id",
        }

        df.rename(columns=intacct_map, inplace=True)
        return self.parse_dataframe(df)

    def _detect_format(self, file_path: Path, suffix: str) -> str:
        """Detect file format from extension and content."""
        format_map = {
            ".csv": "csv",
            ".xlsx": "xlsx",
            ".xls": "xlsx",
            ".ofx": "ofx",
            ".qfx": "ofx",
        }

        if suffix in format_map:
            return format_map[suffix]

        # Check content
        try:
            with open(file_path, 'r', errors='ignore') as f:
                first_lines = f.read(1000)
                if "<OFX>" in first_lines.upper():
                    return "ofx"
                if "INTACCT" in first_lines.upper():
                    return "intacct"
        except:
            pass

        return "csv"  # Default

    def _normalize_column_name(self, name: str) -> str:
        """Normalize column name for matching."""
        return re.sub(r'[^a-z0-9]', '_', str(name).lower().strip())

    def _map_columns(self, columns: List[str]) -> Dict[str, str]:
        """Map file columns to standard fields."""
        mapping = {}

        for standard_field, variations in self.COLUMN_MAPPINGS.items():
            for col in columns:
                normalized = self._normalize_column_name(col)
                if normalized in variations or any(v in normalized for v in variations):
                    mapping[standard_field] = col
                    break

        return mapping

    def _row_to_transaction(
        self,
        row: pd.Series,
        column_map: Dict[str, str],
        bank_account_id: str
    ) -> Optional[BankTransaction]:
        """Convert a DataFrame row to a BankTransaction."""
        tx = BankTransaction(bank_account_id=bank_account_id)

        # Date
        if "date" in column_map:
            tx.transaction_date = self._parse_date(row.get(column_map["date"]))
            tx.post_date = tx.transaction_date

        if not tx.transaction_date:
            return None

        # Amount
        if "amount" in column_map:
            tx.amount = self._parse_amount(row.get(column_map["amount"]))
        elif "debit" in column_map and "credit" in column_map:
            # Separate debit/credit columns
            debit = self._parse_amount(row.get(column_map.get("debit", ""), 0))
            credit = self._parse_amount(row.get(column_map.get("credit", ""), 0))
            tx.amount = credit - debit

        if tx.amount == Decimal("0"):
            return None

        # Description
        if "description" in column_map:
            tx.description = str(row.get(column_map["description"], "")).strip()

        # Reference
        if "reference" in column_map:
            ref = row.get(column_map["reference"])
            if pd.notna(ref):
                tx.reference_number = str(ref).strip()

        # Store raw data
        tx.raw_data = row.to_dict()

        return tx

    def _parse_date(self, value: Any) -> Optional[date]:
        """Parse date from various formats."""
        if value is None or pd.isna(value):
            return None

        if isinstance(value, (date, datetime)):
            return value.date() if isinstance(value, datetime) else value

        value_str = str(value).strip()

        date_formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%m/%d/%y",
            "%d/%m/%Y",
            "%Y%m%d",
            "%m-%d-%Y",
            "%d-%m-%Y",
            "%b %d, %Y",
            "%B %d, %Y",
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(value_str, fmt).date()
            except ValueError:
                continue

        return None

    def _parse_ofx_date(self, value: str) -> Optional[date]:
        """Parse OFX date format (YYYYMMDDHHMMSS)."""
        try:
            # Take first 8 characters (YYYYMMDD)
            date_part = value[:8]
            return datetime.strptime(date_part, "%Y%m%d").date()
        except:
            return None

    def _parse_amount(self, value: Any) -> Decimal:
        """Parse amount from various formats."""
        if value is None or pd.isna(value):
            return Decimal("0")

        if isinstance(value, (int, float)):
            return Decimal(str(value))

        value_str = str(value).strip()

        # Remove currency symbols and whitespace
        value_str = re.sub(r'[$€£¥\s]', '', value_str)

        # Handle parentheses for negative (accounting format)
        if value_str.startswith('(') and value_str.endswith(')'):
            value_str = '-' + value_str[1:-1]

        # Remove commas
        value_str = value_str.replace(',', '')

        try:
            return Decimal(value_str)
        except InvalidOperation:
            return Decimal("0")

    def _detect_transaction_type(self, description: str) -> TransactionType:
        """Detect transaction type from description."""
        desc_lower = description.lower()

        for tx_type, patterns in self.TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, desc_lower):
                    return tx_type

        return TransactionType.OTHER

    def _extract_check_number(self, description: str) -> Optional[str]:
        """Extract check number from description."""
        patterns = [
            r"check\s*#?\s*(\d+)",
            r"chk\s*#?\s*(\d+)",
            r"cheque\s*#?\s*(\d+)",
            r"#(\d{3,})",  # Generic number with at least 3 digits
        ]

        for pattern in patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _extract_vendor(self, description: str) -> Optional[str]:
        """Extract vendor name from description."""
        for pattern in self.VENDOR_PATTERNS:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                vendor = match.group(1).strip()
                # Clean up vendor name
                vendor = re.sub(r'\s+', ' ', vendor)
                vendor = vendor.strip('.,- ')
                if len(vendor) > 2:
                    return vendor

        # Fallback: use first significant part of description
        parts = description.split()
        if parts:
            vendor = ' '.join(parts[:3])
            return vendor.strip('.,- ')

        return None

    def _normalize_description(self, description: str) -> str:
        """Normalize transaction description."""
        # Remove extra whitespace
        description = ' '.join(description.split())

        # Remove common prefixes
        prefixes_to_remove = [
            r"^(debit|credit|withdrawal|deposit)\s*[-:]\s*",
            r"^(pos|ach|wire)\s*[-:]\s*",
        ]

        for prefix in prefixes_to_remove:
            description = re.sub(prefix, '', description, flags=re.IGNORECASE)

        return description.strip()


def create_sample_bank_data(num_records: int = 50) -> pd.DataFrame:
    """Generate sample bank transaction data for testing."""
    import random
    from datetime import timedelta

    vendors = [
        "ACME Corp", "Office Depot", "Amazon Web Services", "AT&T",
        "Verizon", "Dell Technologies", "Microsoft", "Adobe Systems",
        "Staples", "FedEx", "UPS", "United Airlines", "Marriott Hotels",
        "Enterprise Rent-A-Car", "Comcast Business", "PG&E", "Water Utility Co",
    ]

    records = []
    base_date = date.today() - timedelta(days=30)

    for i in range(num_records):
        tx_date = base_date + timedelta(days=random.randint(0, 30))
        vendor = random.choice(vendors)
        amount = round(random.uniform(-50000, -50), 2)

        tx_type = random.choice(["CHECK", "ACH", "WIRE", "CARD"])

        if tx_type == "CHECK":
            check_num = str(random.randint(10000, 99999))
            description = f"Check #{check_num} - {vendor}"
            reference = check_num
        elif tx_type == "ACH":
            description = f"ACH DEBIT - {vendor}"
            reference = f"ACH{random.randint(100000, 999999)}"
        elif tx_type == "WIRE":
            description = f"WIRE TRANSFER TO {vendor}"
            reference = f"WIRE{random.randint(100000, 999999)}"
        else:
            description = f"CARD PURCHASE - {vendor}"
            reference = f"CARD{random.randint(100000, 999999)}"

        records.append({
            "Date": tx_date.strftime("%m/%d/%Y"),
            "Description": description,
            "Amount": amount,
            "Reference": reference,
            "Type": tx_type,
        })

    return pd.DataFrame(records)