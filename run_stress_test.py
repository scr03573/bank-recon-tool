#!/usr/bin/env python3
"""
Stress test script - scale up to thousands of transactions.
"""
import sys
import time
import random
from pathlib import Path
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent))

from src.reconciler import BankReconciler
from src.models import BankTransaction, APTransaction, TransactionType
from src.bank_parser import BankDataParser

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich import box

console = Console()


def generate_large_dataset(
    num_bank_transactions: int = 1000,
    num_ap_transactions: int = 1200,
    match_rate: float = 0.75,  # 75% should match
    batch_payment_rate: float = 0.10,  # 10% are batch payments
    duplicate_rate: float = 0.02,  # 2% duplicates
):
    """Generate a large realistic dataset for stress testing."""

    console.print(f"\n[cyan]Generating {num_bank_transactions:,} bank transactions...[/cyan]")

    vendors = [
        "ACME Corporation", "Office Depot Inc", "Amazon Web Services", "AT&T Mobility",
        "Verizon Wireless", "Dell Technologies", "Microsoft Corp", "Adobe Systems Inc",
        "Staples Business", "FedEx Express", "UPS Ground", "United Airlines",
        "Marriott International", "Enterprise Holdings", "Comcast Business",
        "Pacific Gas & Electric", "City Water Utility", "Waste Management Inc",
        "Grainger Industrial", "HD Supply", "Sysco Corporation", "US Foods Inc",
        "ADP Payroll Services", "Paychex Inc", "Blue Cross Insurance", "Aetna Health",
        "State Farm Insurance", "Progressive Insurance", "Bank of America", "Wells Fargo",
        "Chase Bank", "Capital One", "American Express", "Visa Inc", "Mastercard",
        "Home Depot Pro", "Lowes Commercial", "Fastenal Company", "MSC Industrial",
        "W.W. Grainger", "Uline Shipping", "Global Industrial", "Northern Tool",
        "CDW Corporation", "Insight Direct", "SHI International", "Connection Inc",
    ]

    base_date = date.today() - timedelta(days=90)

    bank_transactions = []
    ap_transactions = []

    # Track for creating matches
    matched_pairs = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:

        # Generate bank transactions
        task1 = progress.add_task("Creating bank transactions...", total=num_bank_transactions)

        for i in range(num_bank_transactions):
            tx_date = base_date + timedelta(days=random.randint(0, 90))
            vendor = random.choice(vendors)
            amount = Decimal(str(round(random.uniform(50, 75000), 2)))

            tx_type = random.choices(
                [TransactionType.CHECK, TransactionType.ACH, TransactionType.WIRE, TransactionType.CARD],
                weights=[0.35, 0.40, 0.10, 0.15]
            )[0]

            if tx_type == TransactionType.CHECK:
                check_num = str(random.randint(10000, 99999))
                description = f"Check #{check_num} - {vendor}"
                reference = check_num
            elif tx_type == TransactionType.ACH:
                description = f"ACH DEBIT - {vendor}"
                reference = f"ACH{random.randint(1000000, 9999999)}"
                check_num = None
            elif tx_type == TransactionType.WIRE:
                description = f"WIRE TRANSFER TO {vendor}"
                reference = f"WIRE{random.randint(1000000, 9999999)}"
                check_num = None
            else:
                description = f"CARD PURCHASE - {vendor}"
                reference = f"CARD{random.randint(1000000, 9999999)}"
                check_num = None

            bank_tx = BankTransaction(
                id=f"BANK-{i+1:06d}",
                transaction_date=tx_date,
                post_date=tx_date,
                amount=-amount,  # Negative for payments
                description=description,
                reference_number=reference,
                check_number=check_num,
                transaction_type=tx_type,
                bank_account_id="CHECKING-001",
                vendor_name=vendor,
            )
            bank_transactions.append(bank_tx)

            # Decide if this should have a match
            if random.random() < match_rate:
                matched_pairs.append((bank_tx, vendor, amount, tx_date, check_num))

            progress.update(task1, advance=1)

        # Generate AP transactions (including matches)
        task2 = progress.add_task("Creating AP transactions...", total=num_ap_transactions)

        ap_count = 0

        # First, create matching AP records
        for bank_tx, vendor, amount, tx_date, check_num in matched_pairs:
            if ap_count >= num_ap_transactions:
                break

            # Introduce some realistic variations
            variation = random.random()

            if variation < 0.85:
                # Exact match
                ap_amount = amount
                ap_date = tx_date
            elif variation < 0.92:
                # Slight date difference (1-3 days)
                ap_amount = amount
                ap_date = tx_date + timedelta(days=random.randint(-3, 3))
            elif variation < 0.97:
                # Small amount difference (rounding)
                ap_amount = amount + Decimal(str(random.uniform(-0.50, 0.50)))
                ap_date = tx_date
            else:
                # Both slightly off
                ap_amount = amount * Decimal(str(random.uniform(0.99, 1.01)))
                ap_date = tx_date + timedelta(days=random.randint(-5, 5))

            ap_tx = APTransaction(
                id=f"AP-{ap_count+1:06d}",
                record_number=f"{ap_count+1:06d}",
                vendor_id=f"V-{hash(vendor) % 10000:04d}",
                vendor_name=vendor,
                payment_date=ap_date,
                amount=ap_amount,
                paid_amount=ap_amount,
                check_number=check_num,
                bank_account_id="CHECKING-001",
                state="Paid"
            )
            ap_transactions.append(ap_tx)
            ap_count += 1
            progress.update(task2, advance=1)

        # Create batch payments (one bank tx = multiple AP)
        num_batches = int(num_bank_transactions * batch_payment_rate)
        for _ in range(num_batches):
            if ap_count >= num_ap_transactions - 3:
                break

            # Create 2-5 small AP transactions that could sum to a bank amount
            batch_vendor = random.choice(vendors)
            batch_date = base_date + timedelta(days=random.randint(0, 90))
            num_in_batch = random.randint(2, 5)

            for j in range(num_in_batch):
                if ap_count >= num_ap_transactions:
                    break
                ap_tx = APTransaction(
                    id=f"AP-{ap_count+1:06d}",
                    record_number=f"{ap_count+1:06d}",
                    vendor_id=f"V-{hash(batch_vendor) % 10000:04d}",
                    vendor_name=batch_vendor,
                    payment_date=batch_date,
                    amount=Decimal(str(round(random.uniform(100, 5000), 2))),
                    paid_amount=Decimal(str(round(random.uniform(100, 5000), 2))),
                    bank_account_id="CHECKING-001",
                    state="Paid"
                )
                ap_transactions.append(ap_tx)
                ap_count += 1
                progress.update(task2, advance=1)

        # Create some duplicates
        num_duplicates = int(num_ap_transactions * duplicate_rate)
        for _ in range(num_duplicates):
            if ap_count >= num_ap_transactions:
                break
            if ap_transactions:
                # Duplicate a random existing AP transaction
                orig = random.choice(ap_transactions[:len(ap_transactions)//2])
                dup = APTransaction(
                    id=f"AP-{ap_count+1:06d}",
                    record_number=f"{ap_count+1:06d}",
                    vendor_id=orig.vendor_id,
                    vendor_name=orig.vendor_name,
                    payment_date=orig.payment_date + timedelta(days=random.randint(1, 5)),
                    amount=orig.amount,
                    paid_amount=orig.paid_amount,
                    bank_account_id="CHECKING-001",
                    state="Paid"
                )
                ap_transactions.append(dup)
                ap_count += 1
                progress.update(task2, advance=1)

        # Fill remaining with unmatched AP
        while ap_count < num_ap_transactions:
            vendor = random.choice(vendors)
            ap_tx = APTransaction(
                id=f"AP-{ap_count+1:06d}",
                record_number=f"{ap_count+1:06d}",
                vendor_id=f"V-{hash(vendor) % 10000:04d}",
                vendor_name=vendor,
                payment_date=base_date + timedelta(days=random.randint(0, 90)),
                amount=Decimal(str(round(random.uniform(50, 50000), 2))),
                paid_amount=Decimal(str(round(random.uniform(50, 50000), 2))),
                bank_account_id="CHECKING-001",
                state="Paid"
            )
            ap_transactions.append(ap_tx)
            ap_count += 1
            progress.update(task2, advance=1)

    return bank_transactions, ap_transactions


def run_stress_test(scale: str = "medium"):
    """Run stress test at different scales."""

    scales = {
        "small": (500, 600),
        "medium": (2000, 2500),
        "large": (5000, 6000),
        "xlarge": (10000, 12000),
    }

    num_bank, num_ap = scales.get(scale, scales["medium"])

    console.print(Panel.fit(
        f"[bold blue]Bank Reconciliation Stress Test[/bold blue]\n"
        f"Scale: [yellow]{scale.upper()}[/yellow] ({num_bank:,} bank / {num_ap:,} AP transactions)",
        border_style="blue"
    ))

    # Generate data
    start_gen = time.time()
    bank_transactions, ap_transactions = generate_large_dataset(
        num_bank_transactions=num_bank,
        num_ap_transactions=num_ap,
        match_rate=0.70,
        batch_payment_rate=0.08,
        duplicate_rate=0.03,
    )
    gen_time = time.time() - start_gen

    console.print(f"\n[green]✓ Generated {len(bank_transactions):,} bank and {len(ap_transactions):,} AP transactions in {gen_time:.2f}s[/green]")

    # Run reconciliation
    console.print("\n[cyan]Running reconciliation engine...[/cyan]")

    reconciler = BankReconciler(use_mock_intacct=True)

    start_recon = time.time()
    result = reconciler.reconcile(
        bank_transactions=bank_transactions,
        ap_transactions=ap_transactions,
        start_date=date.today() - timedelta(days=90),
        end_date=date.today(),
        bank_account_id="CHECKING-001",
        generate_reports=True,
        report_formats=["excel", "html", "json"]
    )
    recon_time = time.time() - start_recon

    # Display results
    console.print("\n")

    # Performance metrics
    perf_table = Table(title="Performance Metrics", box=box.ROUNDED)
    perf_table.add_column("Metric", style="cyan")
    perf_table.add_column("Value", justify="right")

    perf_table.add_row("Data Generation Time", f"{gen_time:.2f}s")
    perf_table.add_row("Reconciliation Time", f"{recon_time:.2f}s")
    perf_table.add_row("Total Time", f"{gen_time + recon_time:.2f}s")
    perf_table.add_row("", "")
    perf_table.add_row("Transactions/Second", f"{(num_bank + num_ap) / recon_time:,.0f}")
    perf_table.add_row("Matches/Second", f"{result.summary.matched_count / recon_time:,.0f}")

    console.print(perf_table)

    # Results summary
    results_table = Table(title="Reconciliation Results", box=box.ROUNDED)
    results_table.add_column("Metric", style="cyan")
    results_table.add_column("Count", justify="right")
    results_table.add_column("Percentage", justify="right")

    total_bank = result.summary.total_bank_transactions
    results_table.add_row("Bank Transactions", f"{total_bank:,}", "100%")
    results_table.add_row("AP Transactions", f"{result.summary.total_ap_transactions:,}", "-")
    results_table.add_row("", "", "")
    results_table.add_row(
        "[green]Matched[/green]",
        f"[green]{result.summary.matched_count:,}[/green]",
        f"[green]{result.summary.matched_count/total_bank*100:.1f}%[/green]"
    )
    results_table.add_row(
        "[yellow]Partial Matches[/yellow]",
        f"[yellow]{result.summary.partial_match_count:,}[/yellow]",
        f"[yellow]{result.summary.partial_match_count/total_bank*100:.1f}%[/yellow]"
    )
    results_table.add_row(
        "[red]Unmatched Bank[/red]",
        f"[red]{result.summary.unmatched_bank_count:,}[/red]",
        f"[red]{result.summary.unmatched_bank_count/total_bank*100:.1f}%[/red]"
    )
    results_table.add_row(
        "[red]Exceptions[/red]",
        f"[red]{result.summary.exception_count:,}[/red]",
        "-"
    )

    console.print(results_table)

    # Exception breakdown
    if result.exceptions:
        exc_types = {}
        for exc in result.exceptions:
            exc_type = exc.exception_type.value
            exc_types[exc_type] = exc_types.get(exc_type, 0) + 1

        exc_table = Table(title="Exception Breakdown", box=box.SIMPLE)
        exc_table.add_column("Type", style="cyan")
        exc_table.add_column("Count", justify="right")

        for exc_type, count in sorted(exc_types.items(), key=lambda x: -x[1]):
            exc_table.add_row(exc_type.replace("_", " ").title(), f"{count:,}")

        console.print(exc_table)

    # Amount summary
    amount_table = Table(title="Amount Summary", box=box.ROUNDED)
    amount_table.add_column("Metric", style="cyan")
    amount_table.add_column("Amount", justify="right")

    amount_table.add_row("Total Bank Amount", f"${float(result.summary.total_bank_amount):,.2f}")
    amount_table.add_row("Total AP Amount", f"${float(result.summary.total_ap_amount):,.2f}")
    amount_table.add_row("Matched Amount", f"[green]${float(result.summary.matched_amount):,.2f}[/green]")
    amount_table.add_row("Unreconciled", f"[yellow]${float(result.summary.unreconciled_amount):,.2f}[/yellow]")

    console.print(amount_table)

    # Reports
    console.print("\n[bold green]Reports Generated:[/bold green]")
    for fmt, path in result.report_paths.items():
        file_size = Path(path).stat().st_size / 1024
        console.print(f"  [cyan]{fmt.upper()}:[/cyan] {path} ({file_size:.1f} KB)")

    reconciler.close()

    console.print(f"\n[bold green]Stress test complete![/bold green]")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stress test the bank reconciliation tool")
    parser.add_argument(
        "--scale", "-s",
        choices=["small", "medium", "large", "xlarge"],
        default="medium",
        help="Test scale (small=500, medium=2000, large=5000, xlarge=10000 transactions)"
    )

    args = parser.parse_args()
    run_stress_test(args.scale)
