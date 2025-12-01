# Bank Reconciliation Tool for Sage Intacct

Automated bank reconciliation tool that matches bank transactions with AP records from Sage Intacct, using fuzzy matching algorithms and real-time market data validation via Intrinio, yfinance, and FRED.

## Features

- **Multi-format Bank Import**: CSV, Excel, OFX/QFX files
- **Sage Intacct Integration**: Direct API connection for AP data
- **Intelligent Matching**:
  - Exact check number matching
  - Fuzzy vendor name matching (RapidFuzz + Jellyfish)
  - Amount tolerance matching
  - Batch payment detection
  - ACH/wire reference matching
- **Market Data Integration**:
  - **Intrinio**: Premium financial data (optional)
  - **yfinance**: Free market data (default)
  - **FRED**: Economic indicators
- **Exception Detection**:
  - Missing AP records
  - Duplicate payments
  - Amount mismatches
  - Stale checks
- **Economic Validation**: Vendor verification via stock tickers, market condition flags
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

# Market Data APIs
INTRINIO_API_KEY=your_intrinio_key    # Optional: premium data
FRED_API_KEY=your_fred_key            # Free: https://fred.stlouisfed.org/docs/api/api_key.html

# Market Data Settings
MARKET_DATA_PRIORITY=yfinance_first   # Options: intrinio_first, yfinance_first, best_available
MARKET_DATA_CACHE_MINUTES=15
ENABLE_ECONOMIC_VALIDATION=true

# Matching thresholds
FUZZY_MATCH_THRESHOLD=85
DATE_TOLERANCE_DAYS=5
AMOUNT_TOLERANCE_PERCENT=0.01
```

## Market Data Architecture

The tool uses a unified market data provider that combines multiple data sources:

```
Bank Transaction → Matching Engine → Economic Validator
                                          ↓
                   UnifiedMarketDataProvider
                   /          |           \
            Intrinio     yfinance        FRED
            (premium)     (free)     (economic)
```

### Data Sources

| Source | Data Type | Cost | Use Case |
|--------|-----------|------|----------|
| **Intrinio** | Real-time quotes, company fundamentals, financials | Paid | Premium data needs |
| **yfinance** | Stock prices, indices, historical data | Free | Default fallback |
| **FRED** | Interest rates, Treasury yields, inflation, unemployment | Free | Economic indicators |

### Data Priority Options

- `intrinio_first`: Use Intrinio, fall back to yfinance
- `yfinance_first`: Use yfinance, fall back to Intrinio (default)
- `intrinio_only`: Only use Intrinio
- `yfinance_only`: Only use yfinance
- `best_available`: Use whichever returns data first

### Economic Validation

The matching engine validates transactions using market data:

1. **Vendor Verification**: Maps vendor names to stock tickers (70+ companies)
   - Microsoft → MSFT, Amazon → AMZN, FedEx → FDX, etc.
   - Adds confidence boost (+2-3%) for verified public companies

2. **Market Condition Flags**:
   - High VIX (>30): Warning flag, confidence adjustment
   - Inverted yield curve: Economic risk warning
   - Weekend transactions: Posting date verification flag

3. **Large Payment Validation** (>$100K):
   - S&P 500 context during market declines
   - Wire transfer authorization flags (>$500K)

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

### Using Market Data Directly

```python
from src.market_data import UnifiedMarketDataProvider, DataPriority

# Initialize provider
provider = UnifiedMarketDataProvider(
    intrinio_api_key="your_key",  # Optional
    fred_api_key="your_fred_key",
    priority=DataPriority.YFINANCE_FIRST
)

# Get stock quote
quote = provider.get_quote("MSFT")
print(f"Microsoft: ${quote.price} ({quote.change_percent:+.2f}%)")

# Get economic indicators
indicators = provider.get_economic_indicators()
print(f"Fed Funds Rate: {indicators['fed_funds_rate'].value}%")

# Validate a vendor
validation = provider.validate_vendor("Amazon Web Services")
print(f"Ticker: {validation['ticker']}, Active: {validation['is_active']}")

# Get market snapshot
snapshot = provider.get_market_snapshot()
print(f"VIX: {snapshot.vix}, Market: {snapshot.market_status}")
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
4. **Pass 4 - Economic Validation**: Market data verification
5. **Pass 5 - Exceptions**: Flag unmatched items

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
- **Treasury Yields**: 2Y, 5Y, 10Y, 30Y rates
- **Yield Curve Spread**: Recession indicator if inverted
- **VIX**: Market volatility index
- **S&P 500**: Market performance context
- **CPI**: Inflation rate
- **Unemployment**: Employment data

This helps with:
- Vendor verification via public company data
- Early payment discount decisions
- Cash management recommendations
- Understanding timing anomalies
- Large payment validation

## Project Structure

```
bank-recon-tool/
├── src/
│   ├── __init__.py
│   ├── config.py          # Configuration management
│   ├── models.py          # Data models
│   ├── intacct_client.py  # Sage Intacct API client
│   ├── bank_parser.py     # Bank file parser
│   ├── matching_engine.py # Fuzzy matching + economic validation
│   ├── market_data.py     # Unified market data provider
│   ├── economic_context.py# FRED/yfinance integration
│   ├── reporting.py       # Report generation
│   ├── reconciler.py      # Main orchestrator
│   └── cli.py             # Command-line interface
├── reports/               # Generated reports
├── data/                  # Data files
├── requirements.txt
├── setup.py
├── run_demo.py
├── run_stress_test.py
└── README.md
```

## Troubleshooting

**No Intacct connection**: Use `--demo` flag or import bank files without API

**Market data unavailable**:
- Markets closed on weekends (limited data)
- Check API keys are configured correctly
- Try switching `MARKET_DATA_PRIORITY`

**FRED data unavailable**: Get free API key from [FRED website](https://fred.stlouisfed.org/docs/api/api_key.html)

**Low match rate**: Adjust thresholds in `.env`:
- Lower `FUZZY_MATCH_THRESHOLD` (default 85)
- Increase `DATE_TOLERANCE_DAYS` (default 5)

**Memory issues with large files**: Process in date batches

## Performance

Tested with stress test (`python run_stress_test.py`):

| Scale | Transactions | Time | Rate |
|-------|-------------|------|------|
| Small | 500 bank / 600 AP | ~15s | 74 tx/sec |
| Medium | 2000 bank / 2400 AP | ~60s | 70 tx/sec |
| Large | 5000 bank / 6000 AP | ~150s | 65 tx/sec |

Economic validation adds ~10s for initial market data fetch (cached thereafter).
