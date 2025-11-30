"""
Command-line interface for the bank reconciliation tool.
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box

from .config import config
from .reconciler import BankReconciler, create_sample_data
from .economic_context import EconomicDataProvider


console = Console()


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """
    Bank Reconciliation Tool for Sage Intacct

    Automates matching of bank transactions with AP records,
    generates exception reports, and provides economic context.
    """
    pass


@cli.command()
@click.option("--bank-file", "-b", type=click.Path(exists=True), help="Path to bank transaction file (CSV, Excel, OFX)")
@click.option("--start-date", "-s", type=click.DateTime(formats=["%Y-%m-%d"]), help="Period start date (YYYY-MM-DD)")
@click.option("--end-date", "-e", type=click.DateTime(formats=["%Y-%m-%d"]), help="Period end date (YYYY-MM-DD)")
@click.option("--bank-account", "-a", default="", help="Bank account ID filter")
@click.option("--output-dir", "-o", type=click.Path(), default="./reports", help="Output directory for reports")
@click.option("--format", "-f", "formats", multiple=True, default=["excel", "html"], help="Report formats (excel, html, json)")
@click.option("--demo", is_flag=True, help="Run with sample demo data")
def reconcile(bank_file, start_date, end_date, bank_account, output_dir, formats, demo):
    """
    Run bank reconciliation.

    Examples:
        recon reconcile --bank-file transactions.csv --start-date 2024-01-01 --end-date 2024-01-31
        recon reconcile --demo
    """
    console.print(Panel.fit(
        "[bold blue]Bank Reconciliation Tool[/bold blue]\n"
        "Sage Intacct Integration",
        border_style="blue"
    ))

    # Set dates
    end_dt = end_date.date() if end_date else date.today()
    start_dt = start_date.date() if start_date else (end_dt - timedelta(days=30))

    console.print(f"\n[cyan]Period:[/cyan] {start_dt} to {end_dt}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Initializing...", total=None)

        # Initialize reconciler
        reconciler = BankReconciler(use_mock_intacct=demo or not config.intacct.is_configured())

        if demo:
            progress.update(task, description="Generating sample data...")
            bank_transactions, ap_transactions = create_sample_data()
            progress.update(task, description="Running reconciliation...")

            result = reconciler.reconcile(
                bank_transactions=bank_transactions,
                ap_transactions=ap_transactions,
                start_date=start_dt,
                end_date=end_dt,
                bank_account_id=bank_account,
                report_formats=list(formats)
            )
        else:
            if not bank_file:
                console.print("[red]Error: --bank-file required (or use --demo)[/red]")
                sys.exit(1)

            progress.update(task, description="Loading bank transactions...")
            progress.update(task, description="Fetching AP data from Intacct...")
            progress.update(task, description="Running matching engine...")

            result = reconciler.reconcile(
                bank_file=Path(bank_file),
                start_date=start_dt,
                end_date=end_dt,
                bank_account_id=bank_account,
                report_formats=list(formats)
            )

        progress.update(task, description="Complete!")

    # Display results
    _display_summary(result.summary)
    _display_economic_context(result.economic_snapshot)
    _display_exceptions_summary(result.exceptions)

    # Show report locations
    if result.report_paths:
        console.print("\n[bold green]Reports Generated:[/bold green]")
        for fmt, path in result.report_paths.items():
            console.print(f"  {fmt.upper()}: {path}")

    reconciler.close()


@cli.command()
@click.option("--limit", "-n", default=10, help="Number of runs to show")
def history(limit):
    """View reconciliation history."""
    reconciler = BankReconciler()
    runs = reconciler.get_reconciliation_history(limit=limit)

    if not runs:
        console.print("[yellow]No reconciliation history found.[/yellow]")
        return

    table = Table(title="Reconciliation History", box=box.ROUNDED)
    table.add_column("ID", style="cyan")
    table.add_column("Date")
    table.add_column("Period")
    table.add_column("Matched")
    table.add_column("Exceptions")
    table.add_column("Match Rate")

    for run in runs:
        run_date = run.get("run_date", "")[:10] if run.get("run_date") else ""
        period = f"{run.get('period_start', '')} to {run.get('period_end', '')}"
        match_rate = f"{run.get('auto_match_rate', 0) * 100:.1f}%"

        table.add_row(
            run.get("id", "")[:8],
            run_date,
            period,
            str(run.get("matched_count", 0)),
            str(run.get("exception_count", 0)),
            match_rate
        )

    console.print(table)
    reconciler.close()


@cli.command()
@click.argument("run_id")
def show(run_id):
    """Show details of a specific reconciliation run."""
    reconciler = BankReconciler()
    details = reconciler.get_run_details(run_id)

    if not details:
        # Try partial match
        runs = reconciler.get_reconciliation_history(limit=100)
        matching = [r for r in runs if r.get("id", "").startswith(run_id)]
        if matching:
            details = reconciler.get_run_details(matching[0]["id"])

    if not details:
        console.print(f"[red]Run not found: {run_id}[/red]")
        return

    console.print(Panel(f"[bold]Run ID:[/bold] {details.get('id')}", title="Reconciliation Details"))

    # Summary info
    info_table = Table(show_header=False, box=box.SIMPLE)
    info_table.add_column("Field", style="cyan")
    info_table.add_column("Value")

    info_table.add_row("Period", f"{details.get('period_start')} to {details.get('period_end')}")
    info_table.add_row("Bank Account", details.get("bank_account_id") or "All")
    info_table.add_row("Bank Transactions", str(details.get("total_bank_transactions")))
    info_table.add_row("AP Transactions", str(details.get("total_ap_transactions")))
    info_table.add_row("Matched", str(details.get("matched_count")))
    info_table.add_row("Exceptions", str(details.get("exception_count")))
    info_table.add_row("Match Rate", f"{details.get('auto_match_rate', 0) * 100:.1f}%")
    info_table.add_row("Unreconciled", f"${details.get('unreconciled_amount', 0):,.2f}")

    console.print(info_table)

    reconciler.close()


@cli.command()
@click.option("--date", "-d", "target_date", type=click.DateTime(formats=["%Y-%m-%d"]), help="Date for snapshot")
def economic(target_date):
    """Show current economic context."""
    target = target_date.date() if target_date else date.today()

    console.print(f"\n[bold]Economic Snapshot for {target}[/bold]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching economic data...", total=None)
        provider = EconomicDataProvider()
        snapshot = provider.get_snapshot(target)
        progress.update(task, description="Complete!")

    _display_economic_context(snapshot)


@cli.command()
@click.option("--check", "-c", is_flag=True, help="Check Intacct API connection")
def status(check):
    """Show configuration status."""
    console.print("\n[bold]Configuration Status[/bold]\n")

    table = Table(show_header=False, box=box.SIMPLE)
    table.add_column("Setting", style="cyan")
    table.add_column("Status")

    # Intacct config
    intacct_ok = config.intacct.is_configured()
    table.add_row(
        "Sage Intacct API",
        "[green]Configured[/green]" if intacct_ok else "[yellow]Not configured[/yellow]"
    )

    # FRED API
    fred_ok = bool(config.fred_api_key)
    table.add_row(
        "FRED API Key",
        "[green]Configured[/green]" if fred_ok else "[yellow]Not configured[/yellow]"
    )

    # Matching settings
    table.add_row("Fuzzy Match Threshold", f"{config.matching.fuzzy_threshold}%")
    table.add_row("Date Tolerance", f"{config.matching.date_tolerance_days} days")
    table.add_row("Amount Tolerance", f"{config.matching.amount_tolerance_percent * 100:.2f}%")

    # Directories
    table.add_row("Data Directory", str(config.data_dir))
    table.add_row("Reports Directory", str(config.reports_dir))

    console.print(table)

    if check and intacct_ok:
        console.print("\n[cyan]Testing Intacct connection...[/cyan]")
        try:
            from .intacct_client import IntacctClient
            client = IntacctClient()
            vendors = client.get_vendors()
            console.print(f"[green]✓ Connected! Found {len(vendors)} vendors.[/green]")
        except Exception as e:
            console.print(f"[red]✗ Connection failed: {e}[/red]")


@cli.command()
@click.argument("exception_id")
@click.option("--notes", "-n", required=True, help="Resolution notes")
def resolve(exception_id, notes):
    """Resolve an exception."""
    reconciler = BankReconciler()
    reconciler.resolve_exception(exception_id, notes)
    console.print(f"[green]Exception {exception_id} marked as resolved.[/green]")
    reconciler.close()


def _display_summary(summary):
    """Display reconciliation summary."""
    console.print("\n")

    # Create summary table
    table = Table(title="Reconciliation Summary", box=box.ROUNDED)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Bank Transactions", str(summary.total_bank_transactions))
    table.add_row("AP Transactions", str(summary.total_ap_transactions))
    table.add_row("Matched", f"[green]{summary.matched_count}[/green]")
    table.add_row("Partial Matches", f"[yellow]{summary.partial_match_count}[/yellow]")
    table.add_row("Unmatched (Bank)", f"[red]{summary.unmatched_bank_count}[/red]")
    table.add_row("Unmatched (AP)", f"[red]{summary.unmatched_ap_count}[/red]")
    table.add_row("Exceptions", f"[red]{summary.exception_count}[/red]")
    table.add_row("", "")
    table.add_row("Bank Total", f"${float(summary.total_bank_amount):,.2f}")
    table.add_row("AP Total", f"${float(summary.total_ap_amount):,.2f}")
    table.add_row("Matched Amount", f"[green]${float(summary.matched_amount):,.2f}[/green]")
    table.add_row("Unreconciled", f"[yellow]${float(summary.unreconciled_amount):,.2f}[/yellow]")
    table.add_row("", "")
    table.add_row("Auto-Match Rate", f"[bold]{summary.auto_match_rate:.1%}[/bold]")
    table.add_row("Processing Time", f"{summary.processing_time_seconds:.2f}s")

    console.print(table)


def _display_economic_context(snapshot):
    """Display economic context."""
    if not snapshot:
        return

    console.print("\n")
    table = Table(title="Economic Context", box=box.ROUNDED)
    table.add_column("Indicator", style="cyan")
    table.add_column("Value", justify="right")

    if snapshot.fed_funds_rate:
        table.add_row("Fed Funds Rate", f"{snapshot.fed_funds_rate:.2f}%")
    if snapshot.prime_rate:
        table.add_row("Prime Rate", f"{snapshot.prime_rate:.2f}%")
    if snapshot.treasury_10y:
        table.add_row("10Y Treasury", f"{snapshot.treasury_10y:.2f}%")
    if snapshot.treasury_2y:
        table.add_row("2Y Treasury", f"{snapshot.treasury_2y:.2f}%")
    if snapshot.yield_curve_spread is not None:
        spread_color = "red" if snapshot.yield_curve_spread < 0 else "green"
        table.add_row("Yield Curve (10Y-2Y)", f"[{spread_color}]{snapshot.yield_curve_spread:.2f}%[/{spread_color}]")
    if snapshot.vix:
        vix_color = "red" if snapshot.vix > 25 else "yellow" if snapshot.vix > 20 else "green"
        table.add_row("VIX", f"[{vix_color}]{snapshot.vix:.1f}[/{vix_color}]")
    if snapshot.sp500_price:
        table.add_row("S&P 500", f"${snapshot.sp500_price:,.0f}")
    if snapshot.cpi_yoy:
        cpi_color = "red" if snapshot.cpi_yoy > 4 else "yellow" if snapshot.cpi_yoy > 2 else "green"
        table.add_row("Inflation (CPI YoY)", f"[{cpi_color}]{snapshot.cpi_yoy:.1f}%[/{cpi_color}]")

    console.print(table)

    # Alerts
    if snapshot.is_inverted_yield_curve():
        console.print("[bold yellow]⚠ Yield curve inverted - potential recession indicator[/bold yellow]")
    if snapshot.is_high_volatility():
        console.print("[bold yellow]⚠ High market volatility (VIX > 25)[/bold yellow]")


def _display_exceptions_summary(exceptions):
    """Display exceptions summary."""
    if not exceptions:
        console.print("\n[green]✓ No exceptions found![/green]")
        return

    console.print(f"\n[bold red]Exceptions Found: {len(exceptions)}[/bold red]")

    # Group by type
    by_type = {}
    for exc in exceptions:
        exc_type = exc.exception_type.value
        by_type[exc_type] = by_type.get(exc_type, 0) + 1

    table = Table(box=box.SIMPLE)
    table.add_column("Type", style="cyan")
    table.add_column("Count", justify="right")

    for exc_type, count in sorted(by_type.items(), key=lambda x: -x[1]):
        table.add_row(exc_type.replace("_", " ").title(), str(count))

    console.print(table)

    # Show top critical/high exceptions
    critical = [e for e in exceptions if e.severity in ["critical", "high"]]
    if critical:
        console.print("\n[bold]Top Priority Exceptions:[/bold]")
        for exc in critical[:5]:
            console.print(f"  [red]•[/red] {exc.description[:70]}")


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
