#!/usr/bin/env python3
"""
Demo script to showcase the bank reconciliation tool.

Run this script to see the tool in action with sample data.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import date, timedelta
from decimal import Decimal

from src.reconciler import BankReconciler, create_sample_data
from src.economic_context import EconomicDataProvider, create_sample_economic_data
from src.models import APTransaction

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box


console = Console()


def main():
    console.print(Panel.fit(
        "[bold blue]Bank Reconciliation Tool - Demo[/bold blue]\n"
        "[dim]Automated bank-to-AP matching with economic context[/dim]",
        border_style="blue"
    ))

    # Create sample data
    console.print("\n[cyan]Generating sample data...[/cyan]")
    bank_transactions, ap_transactions = create_sample_data()

    console.print(f"  • Bank transactions: {len(bank_transactions)}")
    console.print(f"  • AP transactions: {len(ap_transactions)}")

    # Initialize reconciler with mock Intacct client
    console.print("\n[cyan]Running reconciliation...[/cyan]")
    reconciler = BankReconciler(use_mock_intacct=True)

    # Run reconciliation
    result = reconciler.reconcile(
        bank_transactions=bank_transactions,
        ap_transactions=ap_transactions,
        start_date=date.today() - timedelta(days=30),
        end_date=date.today(),
        bank_account_id="CHECKING-001",
        generate_reports=True,
        report_formats=["excel", "html", "json"]
    )

    # Display results
    display_summary(result.summary)
    display_matches(result.matches[:10])
    display_exceptions(result.exceptions[:10])
    display_economic_context(result.economic_snapshot)

    # Show report paths
    console.print("\n[bold green]Reports Generated:[/bold green]")
    for fmt, path in result.report_paths.items():
        console.print(f"  [cyan]{fmt.upper()}:[/cyan] {path}")

    # Show history
    console.print("\n[cyan]Reconciliation saved to database[/cyan]")
    history = reconciler.get_reconciliation_history(limit=3)
    if history:
        console.print(f"  Run ID: {history[0]['id'][:8]}...")

    reconciler.close()

    console.print("\n[bold green]Demo complete![/bold green]")
    console.print("\nTo run with your own data:")
    console.print("  1. Copy .env.example to .env and configure credentials")
    console.print("  2. Run: python -m src.cli reconcile --bank-file your_file.csv")


def display_summary(summary):
    """Display reconciliation summary."""
    table = Table(title="\nReconciliation Summary", box=box.ROUNDED)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Bank Transactions", str(summary.total_bank_transactions))
    table.add_row("AP Transactions", str(summary.total_ap_transactions))
    table.add_row("Matched", f"[green]{summary.matched_count}[/green]")
    table.add_row("Partial Matches", f"[yellow]{summary.partial_match_count}[/yellow]")
    table.add_row("Exceptions", f"[red]{summary.exception_count}[/red]")
    table.add_row("", "")
    table.add_row("Auto-Match Rate", f"[bold]{summary.auto_match_rate:.1%}[/bold]")
    table.add_row("Processing Time", f"{summary.processing_time_seconds:.2f}s")

    console.print(table)


def display_matches(matches):
    """Display sample matches."""
    if not matches:
        return

    table = Table(title="\nSample Matches (Top 10)", box=box.ROUNDED)
    table.add_column("Status")
    table.add_column("Confidence")
    table.add_column("Bank Amount")
    table.add_column("Vendor")
    table.add_column("Reasons")

    for match in matches:
        status_color = "green" if match.confidence_score >= 0.9 else "yellow" if match.confidence_score >= 0.7 else "red"
        bank_amt = f"${abs(match.bank_transaction.amount):,.2f}" if match.bank_transaction else "-"
        vendor = match.ap_transactions[0].vendor_name[:20] if match.ap_transactions else "-"

        table.add_row(
            f"[{status_color}]{match.match_status.value}[/{status_color}]",
            f"{match.confidence_score:.0%}",
            bank_amt,
            vendor,
            "; ".join(match.match_reasons[:2])[:40]
        )

    console.print(table)


def display_exceptions(exceptions):
    """Display sample exceptions."""
    if not exceptions:
        console.print("\n[green]✓ No exceptions![/green]")
        return

    table = Table(title="\nExceptions (Top 10)", box=box.ROUNDED)
    table.add_column("Type")
    table.add_column("Severity")
    table.add_column("Description")

    for exc in exceptions:
        sev_color = "red" if exc.severity in ["high", "critical"] else "yellow"
        table.add_row(
            exc.exception_type.value.replace("_", " ").title(),
            f"[{sev_color}]{exc.severity}[/{sev_color}]",
            exc.description[:50]
        )

    console.print(table)


def display_economic_context(snapshot):
    """Display economic context."""
    if not snapshot:
        console.print("\n[yellow]Economic data not available (set FRED_API_KEY)[/yellow]")
        # Use sample data for demo
        snapshot = create_sample_economic_data()
        console.print("[dim](Using sample economic data for demo)[/dim]")

    table = Table(title="\nEconomic Context", box=box.ROUNDED)
    table.add_column("Indicator", style="cyan")
    table.add_column("Value", justify="right")

    if snapshot.fed_funds_rate:
        table.add_row("Fed Funds Rate", f"{snapshot.fed_funds_rate:.2f}%")
    if snapshot.treasury_10y:
        table.add_row("10Y Treasury", f"{snapshot.treasury_10y:.2f}%")
    if snapshot.vix:
        vix_color = "red" if snapshot.vix > 25 else "green"
        table.add_row("VIX", f"[{vix_color}]{snapshot.vix:.1f}[/{vix_color}]")
    if snapshot.cpi_yoy:
        table.add_row("Inflation (YoY)", f"{snapshot.cpi_yoy:.1f}%")

    console.print(table)


if __name__ == "__main__":
    main()
