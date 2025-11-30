# Bank Reconciliation Tool for Sage Intacct

Automated bank reconciliation tool that matches bank transactions with AP records from Sage Intacct, using fuzzy matching algorithms and providing economic context via FRED and yfinance.

## Features

- **Multi-format Bank Import**: CSV, Excel, OFX/QFX files
- **Sage Intacct Integration**: Direct API connection for AP data
- **Intelligent Matching**:
  - Exact check number matching
  - Fuzzy vendor name matching (RapidFuzz + Jellyfish)
  - Amount tolerance matching
  - Batch payment detection
  - ACH/wire reference matching
- **Exception Detection**:
  - Missing AP records
  - Duplicate payments
  - Amount mismatches
  - Stale checks
- **Economic Context**: FRED API + yfinance for rates, VIX, market data
- **Reports**: Excel, HTML, JSON formats
- **Audit Trail**: SQLite database for history

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run demo with sample data
python run_demo.py

# Or use CLI
python -m src.cli reconcile --demo
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Sage Intacct (optional - can use file imports)
INTACCT_SENDER_ID=your_sender_id
INTACCT_SENDER_PASSWORD=your_sender_password
INTACCT_USER_ID=your_user_id
INTACCT_USER_PASSWORD=your_user_password
INTACCT_COMPANY_ID=your_company_id

# FRED API (free at https://fred.stlouisfed.org/docs/api/api_key.html)
FRED_API_KEY=your_api_key

# Matching thresholds
FUZZY_MATCH_THRESHOLD=85
DATE_TOLERANCE_DAYS=5
AMOUNT_TOLERANCE_PERCENT=0.01
```

## Usage

### CLI Commands

```bash
# Reconcile with bank file
python -m src.cli reconcile --bank-file transactions.csv \
    --start-date 2024-01-01 \
    --end-date 2024-01-31

# Run demo mode
python -m src.cli reconcile --demo

# View reconciliation history
python -m src.cli history

# Show run details
python -m src.cli show <run_id>

# Check economic conditions
python -m src.cli economic

# Check configuration status
python -m src.cli status --check

# Resolve an exception
python -m src.cli resolve <exception_id> --notes "Verified with vendor"
```

### Python API

```python
from src.reconciler import BankReconciler
from datetime import date

# Initialize
reconciler = BankReconciler()

# Run reconciliation
result = reconciler.reconcile(
    bank_file="bank_export.csv",
    start_date=date(2024, 1, 1),
    end_date=date(2024, 1, 31),
    bank_account_id="CHECKING-001"
)

# Access results
print(f"Matched: {result.summary.matched_count}")
print(f"Exceptions: {len(result.exceptions)}")
print(f"Reports: {result.report_paths}")
```

### From DataFrames (Jupyter)

```python
import pandas as pd
from src.reconciler import BankReconciler

bank_df = pd.read_csv("bank.csv")
ap_df = pd.read_csv("ap_payments.csv")

reconciler = BankReconciler(use_mock_intacct=True)
result = reconciler.reconcile_from_dataframes(bank_df, ap_df)
```

## Bank File Format

The tool auto-detects columns, but these are recognized:

| Column | Aliases |
|--------|---------|
| Date | date, transaction_date, post_date |
| Amount | amount, debit, credit |
| Description | description, memo, payee |
| Reference | reference, check_number, ref |
| Type | type, transaction_type |

## Matching Logic

1. **Pass 1 - Exact Match**: Check number + amount
2. **Pass 2 - Strong Match**: Weighted score of:
   - Amount (40%)
   - Date proximity (25%)
   - Vendor name similarity (25%)
   - Reference match (10%)
3. **Pass 3 - Batch Detection**: Multiple AP = one bank transaction
4. **Pass 4 - Exceptions**: Flag unmatched items

## Exception Types

| Type | Description | Severity |
|------|-------------|----------|
| `missing_ap_record` | Bank transaction with no AP match | Medium |
| `missing_bank_record` | AP payment not in bank | High |
| `duplicate_payment` | Same vendor/amount within 7 days | High |
| `amount_mismatch` | Matched but amounts differ | Medium |
| `stale_check` | Check cleared >90 days after issue | Low |

## Economic Context

The tool fetches real-time economic data to provide context:

- **Fed Funds Rate**: Current interest rate environment
- **Treasury Yields**: 2Y and 10Y rates
- **Yield Curve**: Spread (recession indicator if inverted)
- **VIX**: Market volatility index
- **CPI**: Inflation rate

This helps with:
- Early payment discount decisions
- Cash management recommendations
- Understanding timing anomalies

## Project Structure

```
bank-recon-tool/
├── src/
│   ├── __init__.py
│   ├── config.py          # Configuration management
│   ├── models.py          # Data models
│   ├── intacct_client.py  # Sage Intacct API client
│   ├── bank_parser.py     # Bank file parser
│   ├── matching_engine.py # Fuzzy matching logic
│   ├── economic_context.py# FRED/yfinance integration
│   ├── reporting.py       # Report generation
│   ├── reconciler.py      # Main orchestrator
│   └── cli.py             # Command-line interface
├── reports/               # Generated reports
├── data/                  # Data files
├── requirements.txt
├── setup.py
├── run_demo.py
└── README.md
```

## Troubleshooting

**No Intacct connection**: Use `--demo` flag or import bank files without API

**FRED data unavailable**: Get free API key from FRED website

**Low match rate**: Adjust thresholds in `.env`:
- Lower `FUZZY_MATCH_THRESHOLD` (default 85)
- Increase `DATE_TOLERANCE_DAYS` (default 5)

**Memory issues with large files**: Process in date batches
