"""
Intelligent transaction matching engine with fuzzy logic.

Matches bank transactions to AP records using multiple strategies:
1. Exact match (check number, amount, date)
2. Fuzzy vendor name matching
3. Amount tolerance matching
4. Reference/ACH code matching
5. Batch payment detection
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict

from rapidfuzz import fuzz, process
import jellyfish

from .config import config, MatchingConfig
from .models import (
    BankTransaction, APTransaction, ReconciliationMatch,
    ReconciliationException, MatchStatus, ExceptionType, TransactionType
)


@dataclass
class MatchCandidate:
    """A potential match between bank and AP transactions."""
    bank_transaction: BankTransaction
    ap_transactions: List[APTransaction]
    score: float = 0.0
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    match_reasons: List[str] = field(default_factory=list)
    is_batch_match: bool = False


class MatchingEngine:
    """
    Intelligent matching engine for bank reconciliation.

    Uses a multi-pass approach:
    1. Exact matches (check numbers, wire references)
    2. Strong matches (amount + date + vendor)
    3. Fuzzy matches (similar amounts, dates, vendor names)
    4. Batch detection (one bank tx -> multiple AP txs)
    """

    def __init__(self, cfg: Optional[MatchingConfig] = None):
        self.config = cfg or config.matching
        self._vendor_name_cache: Dict[str, str] = {}

    def match_transactions(
        self,
        bank_transactions: List[BankTransaction],
        ap_transactions: List[APTransaction]
    ) -> Tuple[List[ReconciliationMatch], List[ReconciliationException]]:
        """
        Match bank transactions to AP transactions.

        Returns:
            Tuple of (matches, exceptions)
        """
        matches: List[ReconciliationMatch] = []
        exceptions: List[ReconciliationException] = []

        # Index AP transactions for efficient lookup
        ap_by_check = self._index_by_check_number(ap_transactions)
        ap_by_amount = self._index_by_amount(ap_transactions)
        ap_by_vendor = self._index_by_vendor(ap_transactions)

        # Track which transactions have been matched
        matched_bank_ids: Set[str] = set()
        matched_ap_ids: Set[str] = set()

        # Filter to payment transactions only
        bank_payments = [tx for tx in bank_transactions if tx.is_payment()]

        # Pass 1: Exact check number matches
        for bank_tx in bank_payments:
            if bank_tx.id in matched_bank_ids:
                continue

            if bank_tx.check_number and bank_tx.check_number in ap_by_check:
                candidates = ap_by_check[bank_tx.check_number]
                for ap_tx in candidates:
                    if ap_tx.id in matched_ap_ids:
                        continue

                    # Verify amount matches
                    if self._amounts_match(abs(bank_tx.amount), ap_tx.paid_amount):
                        match = self._create_match(
                            bank_tx, [ap_tx],
                            confidence=0.98,
                            reasons=["Check number exact match", "Amount match"]
                        )
                        matches.append(match)
                        matched_bank_ids.add(bank_tx.id)
                        matched_ap_ids.add(ap_tx.id)
                        break

        # Pass 2: Strong matches (amount + date + vendor similarity)
        for bank_tx in bank_payments:
            if bank_tx.id in matched_bank_ids:
                continue

            best_candidate = self._find_best_match(
                bank_tx, ap_transactions, matched_ap_ids
            )

            if best_candidate and best_candidate.score >= self.config.fuzzy_threshold / 100:
                match = self._create_match(
                    bank_tx,
                    best_candidate.ap_transactions,
                    confidence=best_candidate.score,
                    reasons=best_candidate.match_reasons
                )
                matches.append(match)
                matched_bank_ids.add(bank_tx.id)
                for ap_tx in best_candidate.ap_transactions:
                    matched_ap_ids.add(ap_tx.id)

        # Pass 3: Batch payment detection
        batch_matches, batch_ap_ids = self._detect_batch_payments(
            bank_payments, ap_transactions, matched_bank_ids, matched_ap_ids
        )
        matches.extend(batch_matches)
        matched_ap_ids.update(batch_ap_ids)
        for m in batch_matches:
            matched_bank_ids.add(m.bank_transaction.id)

        # Pass 4: Generate exceptions for unmatched transactions
        for bank_tx in bank_payments:
            if bank_tx.id not in matched_bank_ids:
                exception = self._create_exception(
                    bank_tx=bank_tx,
                    exception_type=ExceptionType.MISSING_AP_RECORD,
                    description=f"No AP record found for bank transaction: {bank_tx.description}",
                    severity="medium"
                )
                exceptions.append(exception)

        for ap_tx in ap_transactions:
            if ap_tx.id not in matched_ap_ids and ap_tx.is_paid():
                exception = self._create_exception(
                    ap_tx=ap_tx,
                    exception_type=ExceptionType.MISSING_BANK_RECORD,
                    description=f"No bank record found for AP payment: {ap_tx.vendor_name} - ${ap_tx.paid_amount}",
                    severity="high"
                )
                exceptions.append(exception)

        # Check for duplicate payments
        dup_exceptions = self._detect_duplicates(ap_transactions)
        exceptions.extend(dup_exceptions)

        # Check for stale checks
        stale_exceptions = self._detect_stale_checks(bank_transactions)
        exceptions.extend(stale_exceptions)

        return matches, exceptions

    def _find_best_match(
        self,
        bank_tx: BankTransaction,
        ap_transactions: List[APTransaction],
        excluded_ids: Set[str]
    ) -> Optional[MatchCandidate]:
        """Find the best matching AP transaction for a bank transaction."""
        candidates: List[MatchCandidate] = []
        bank_amount = abs(bank_tx.amount)

        for ap_tx in ap_transactions:
            if ap_tx.id in excluded_ids:
                continue

            if not ap_tx.is_paid():
                continue

            # Calculate match score
            score, breakdown, reasons = self._calculate_match_score(bank_tx, ap_tx)

            if score > 0.5:  # Minimum threshold to be considered
                candidates.append(MatchCandidate(
                    bank_transaction=bank_tx,
                    ap_transactions=[ap_tx],
                    score=score,
                    score_breakdown=breakdown,
                    match_reasons=reasons
                ))

        if not candidates:
            return None

        # Return highest scoring candidate
        return max(candidates, key=lambda c: c.score)

    def _calculate_match_score(
        self,
        bank_tx: BankTransaction,
        ap_tx: APTransaction
    ) -> Tuple[float, Dict[str, float], List[str]]:
        """Calculate match score between bank and AP transaction."""
        scores = {}
        reasons = []
        bank_amount = abs(bank_tx.amount)

        # Amount score (most important)
        amount_diff = abs(bank_amount - ap_tx.paid_amount)
        amount_pct_diff = float(amount_diff / bank_amount) if bank_amount else 1.0

        if amount_pct_diff == 0:
            scores["amount"] = 1.0
            reasons.append("Exact amount match")
        elif amount_pct_diff <= self.config.amount_tolerance_percent:
            scores["amount"] = 1.0 - (amount_pct_diff / self.config.amount_tolerance_percent) * 0.1
            reasons.append(f"Amount within tolerance (${amount_diff:.2f} diff)")
        elif amount_pct_diff <= 0.05:
            scores["amount"] = 0.7
            reasons.append(f"Amount close (${amount_diff:.2f} diff)")
        else:
            scores["amount"] = max(0, 1.0 - amount_pct_diff)

        # Date score
        if bank_tx.transaction_date and ap_tx.payment_date:
            date_diff = abs((bank_tx.transaction_date - ap_tx.payment_date).days)

            if date_diff == 0:
                scores["date"] = 1.0
                reasons.append("Same date")
            elif date_diff <= self.config.date_tolerance_days:
                scores["date"] = 1.0 - (date_diff / self.config.date_tolerance_days) * 0.3
                reasons.append(f"Date within {date_diff} days")
            elif date_diff <= 14:
                scores["date"] = 0.5
            else:
                scores["date"] = 0.2
        else:
            scores["date"] = 0.5

        # Vendor name score
        if bank_tx.vendor_name and ap_tx.vendor_name:
            vendor_score = self._vendor_similarity(bank_tx.vendor_name, ap_tx.vendor_name)
            scores["vendor"] = vendor_score

            if vendor_score >= 0.9:
                reasons.append("Strong vendor name match")
            elif vendor_score >= 0.7:
                reasons.append("Similar vendor name")
        else:
            scores["vendor"] = 0.5

        # Reference score
        if bank_tx.reference_number and ap_tx.ach_reference:
            if bank_tx.reference_number == ap_tx.ach_reference:
                scores["reference"] = 1.0
                reasons.append("Reference number match")
            elif bank_tx.reference_number in ap_tx.ach_reference or ap_tx.ach_reference in bank_tx.reference_number:
                scores["reference"] = 0.8
                reasons.append("Partial reference match")
            else:
                scores["reference"] = 0.0
        else:
            scores["reference"] = 0.5

        # Calculate weighted total
        total_score = (
            scores.get("amount", 0) * self.config.weight_amount +
            scores.get("date", 0) * self.config.weight_date +
            scores.get("vendor", 0) * self.config.weight_vendor +
            scores.get("reference", 0) * self.config.weight_reference
        )

        return total_score, scores, reasons

    def _vendor_similarity(self, name1: str, name2: str) -> float:
        """Calculate vendor name similarity using multiple algorithms."""
        # Normalize names
        n1 = self._normalize_vendor_name(name1)
        n2 = self._normalize_vendor_name(name2)

        if not n1 or not n2:
            return 0.0

        # Exact match after normalization
        if n1 == n2:
            return 1.0

        # Use multiple similarity metrics
        scores = []

        # Token set ratio (handles word order differences)
        scores.append(fuzz.token_set_ratio(n1, n2) / 100)

        # Partial ratio (handles substrings)
        scores.append(fuzz.partial_ratio(n1, n2) / 100)

        # Jaro-Winkler (good for typos)
        scores.append(jellyfish.jaro_winkler_similarity(n1, n2))

        # Return weighted average, favoring token set ratio
        return scores[0] * 0.5 + scores[1] * 0.3 + scores[2] * 0.2

    def _normalize_vendor_name(self, name: str) -> str:
        """Normalize vendor name for comparison."""
        if not name:
            return ""

        # Use cache
        cache_key = name.lower()
        if cache_key in self._vendor_name_cache:
            return self._vendor_name_cache[cache_key]

        normalized = name.upper()

        # Remove common suffixes
        suffixes = [
            " INC", " LLC", " LTD", " CORP", " CORPORATION", " COMPANY", " CO",
            " LP", " LLP", " PC", " PLLC", " NA", " N.A.", " FSB", " INTL",
        ]
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]

        # Remove punctuation
        import re
        normalized = re.sub(r'[^\w\s]', '', normalized)

        # Remove extra whitespace
        normalized = ' '.join(normalized.split())

        self._vendor_name_cache[cache_key] = normalized
        return normalized

    def _amounts_match(self, amount1: Decimal, amount2: Decimal, tolerance: float = None) -> bool:
        """Check if two amounts match within tolerance."""
        if tolerance is None:
            tolerance = self.config.amount_tolerance_percent

        if amount1 == amount2:
            return True

        if amount1 == 0:
            return False

        diff_pct = abs(float((amount1 - amount2) / amount1))
        return diff_pct <= tolerance

    def _detect_batch_payments(
        self,
        bank_transactions: List[BankTransaction],
        ap_transactions: List[APTransaction],
        excluded_bank_ids: Set[str],
        excluded_ap_ids: Set[str]
    ) -> Tuple[List[ReconciliationMatch], Set[str]]:
        """Detect batch payments (one bank transaction = multiple AP payments)."""
        matches = []
        matched_ap_ids = set()

        # Get unmatched transactions
        unmatched_bank = [tx for tx in bank_transactions if tx.id not in excluded_bank_ids]
        unmatched_ap = [tx for tx in ap_transactions if tx.id not in excluded_ap_ids and tx.is_paid()]

        # Group AP by vendor and payment date
        ap_by_vendor_date: Dict[Tuple[str, date], List[APTransaction]] = defaultdict(list)
        for ap_tx in unmatched_ap:
            if ap_tx.vendor_name and ap_tx.payment_date:
                key = (self._normalize_vendor_name(ap_tx.vendor_name), ap_tx.payment_date)
                ap_by_vendor_date[key].append(ap_tx)

        for bank_tx in unmatched_bank:
            bank_amount = abs(bank_tx.amount)

            # Try to find AP combinations that sum to bank amount
            if bank_tx.vendor_name and bank_tx.transaction_date:
                # Look for same vendor, nearby dates
                for days_offset in range(-self.config.date_tolerance_days, self.config.date_tolerance_days + 1):
                    check_date = bank_tx.transaction_date + timedelta(days=days_offset)
                    key = (self._normalize_vendor_name(bank_tx.vendor_name), check_date)

                    if key in ap_by_vendor_date:
                        ap_group = [ap for ap in ap_by_vendor_date[key] if ap.id not in matched_ap_ids]
                        if not ap_group:
                            continue

                        # Check if sum matches
                        ap_total = sum(ap.paid_amount for ap in ap_group)
                        if self._amounts_match(bank_amount, ap_total):
                            match = self._create_match(
                                bank_tx, ap_group,
                                confidence=0.85,
                                reasons=[
                                    "Batch payment detected",
                                    f"Sum of {len(ap_group)} AP payments matches bank amount",
                                    "Same vendor"
                                ]
                            )
                            matches.append(match)
                            for ap in ap_group:
                                matched_ap_ids.add(ap.id)
                            break

            # Also try subset sum for larger batches (limited for performance)
            if bank_tx.id not in [m.bank_transaction.id for m in matches]:
                subset_match = self._find_subset_sum_match(
                    bank_tx, unmatched_ap, matched_ap_ids, max_items=5
                )
                if subset_match:
                    matches.append(subset_match)
                    for ap in subset_match.ap_transactions:
                        matched_ap_ids.add(ap.id)

        return matches, matched_ap_ids

    def _find_subset_sum_match(
        self,
        bank_tx: BankTransaction,
        ap_transactions: List[APTransaction],
        excluded_ids: Set[str],
        max_items: int = 5
    ) -> Optional[ReconciliationMatch]:
        """Find a subset of AP transactions that sum to bank amount."""
        bank_amount = abs(bank_tx.amount)
        candidates = [
            ap for ap in ap_transactions
            if ap.id not in excluded_ids and ap.is_paid() and ap.paid_amount <= bank_amount
        ]

        if len(candidates) > 20:
            # Sort by amount descending and take top candidates
            candidates = sorted(candidates, key=lambda x: x.paid_amount, reverse=True)[:20]

        # Try combinations up to max_items
        from itertools import combinations

        for size in range(2, min(max_items + 1, len(candidates) + 1)):
            for combo in combinations(candidates, size):
                total = sum(ap.paid_amount for ap in combo)
                if self._amounts_match(bank_amount, total, tolerance=0.001):
                    return self._create_match(
                        bank_tx, list(combo),
                        confidence=0.80,
                        reasons=[
                            "Batch payment detected via subset sum",
                            f"Sum of {len(combo)} AP payments matches bank amount"
                        ]
                    )

        return None

    def _detect_duplicates(self, ap_transactions: List[APTransaction]) -> List[ReconciliationException]:
        """Detect potential duplicate payments."""
        exceptions = []

        # Group by vendor + amount + date range
        grouped: Dict[Tuple[str, Decimal], List[APTransaction]] = defaultdict(list)
        for ap_tx in ap_transactions:
            if ap_tx.is_paid():
                key = (self._normalize_vendor_name(ap_tx.vendor_name), ap_tx.paid_amount)
                grouped[key].append(ap_tx)

        for key, group in grouped.items():
            if len(group) > 1:
                # Check if payments are within a short time window
                group_sorted = sorted(group, key=lambda x: x.payment_date or date.min)
                for i in range(len(group_sorted) - 1):
                    if group_sorted[i].payment_date and group_sorted[i + 1].payment_date:
                        days_diff = abs((group_sorted[i + 1].payment_date - group_sorted[i].payment_date).days)
                        if days_diff <= 7:
                            exception = self._create_exception(
                                ap_tx=group_sorted[i],
                                exception_type=ExceptionType.DUPLICATE_PAYMENT,
                                description=f"Potential duplicate payment: {group_sorted[i].vendor_name} "
                                           f"${group_sorted[i].paid_amount} on {group_sorted[i].payment_date} "
                                           f"and {group_sorted[i + 1].payment_date}",
                                severity="high"
                            )
                            exceptions.append(exception)

        return exceptions

    def _detect_stale_checks(self, bank_transactions: List[BankTransaction]) -> List[ReconciliationException]:
        """Detect stale/old checks that cleared late."""
        exceptions = []
        stale_threshold_days = 90

        for bank_tx in bank_transactions:
            if bank_tx.transaction_type == TransactionType.CHECK and bank_tx.check_number:
                # This would require check issue date from AP - simplified version
                # checks raw_data for original issue date if available
                issue_date_str = bank_tx.raw_data.get("issue_date") or bank_tx.raw_data.get("ISSUE_DATE")
                if issue_date_str:
                    try:
                        from datetime import datetime
                        issue_date = datetime.strptime(str(issue_date_str), "%Y-%m-%d").date()
                        if bank_tx.transaction_date:
                            days_outstanding = (bank_tx.transaction_date - issue_date).days
                            if days_outstanding > stale_threshold_days:
                                exception = self._create_exception(
                                    bank_tx=bank_tx,
                                    exception_type=ExceptionType.STALE_CHECK,
                                    description=f"Stale check #{bank_tx.check_number} cleared after "
                                               f"{days_outstanding} days",
                                    severity="low"
                                )
                                exceptions.append(exception)
                    except:
                        pass

        return exceptions

    def _create_match(
        self,
        bank_tx: BankTransaction,
        ap_transactions: List[APTransaction],
        confidence: float,
        reasons: List[str]
    ) -> ReconciliationMatch:
        """Create a ReconciliationMatch object."""
        match = ReconciliationMatch(
            bank_transaction=bank_tx,
            ap_transactions=ap_transactions,
            confidence_score=confidence,
            match_reasons=reasons
        )

        # Determine status based on confidence
        if confidence >= 0.95:
            match.match_status = MatchStatus.MATCHED
        elif confidence >= 0.80:
            match.match_status = MatchStatus.PARTIAL_MATCH
        else:
            match.match_status = MatchStatus.MANUAL_REVIEW

        # Check for variance
        if match.variance != 0:
            match.exceptions.append(ExceptionType.AMOUNT_MISMATCH)

        return match

    def _create_exception(
        self,
        exception_type: ExceptionType,
        description: str,
        severity: str,
        bank_tx: Optional[BankTransaction] = None,
        ap_tx: Optional[APTransaction] = None
    ) -> ReconciliationException:
        """Create a ReconciliationException object."""
        # Suggest action based on exception type
        suggested_actions = {
            ExceptionType.AMOUNT_MISMATCH: "Review source documents and adjust if necessary",
            ExceptionType.DUPLICATE_PAYMENT: "Verify if duplicate - request refund if confirmed",
            ExceptionType.MISSING_AP_RECORD: "Check for unrecorded AP entry or misclassification",
            ExceptionType.MISSING_BANK_RECORD: "Verify payment was sent - may be timing difference",
            ExceptionType.VENDOR_MISMATCH: "Verify vendor information in both systems",
            ExceptionType.STALE_CHECK: "Consider voiding and reissuing if needed",
            ExceptionType.REVERSAL: "Investigate reason for reversal",
        }

        return ReconciliationException(
            exception_type=exception_type,
            bank_transaction=bank_tx,
            ap_transaction=ap_tx,
            description=description,
            severity=severity,
            suggested_action=suggested_actions.get(exception_type, "Review manually")
        )

    def _index_by_check_number(self, transactions: List[APTransaction]) -> Dict[str, List[APTransaction]]:
        """Index AP transactions by check number."""
        index = defaultdict(list)
        for tx in transactions:
            if tx.check_number:
                index[tx.check_number].append(tx)
        return index

    def _index_by_amount(self, transactions: List[APTransaction]) -> Dict[Decimal, List[APTransaction]]:
        """Index AP transactions by amount."""
        index = defaultdict(list)
        for tx in transactions:
            if tx.paid_amount:
                index[tx.paid_amount].append(tx)
        return index

    def _index_by_vendor(self, transactions: List[APTransaction]) -> Dict[str, List[APTransaction]]:
        """Index AP transactions by normalized vendor name."""
        index = defaultdict(list)
        for tx in transactions:
            if tx.vendor_name:
                key = self._normalize_vendor_name(tx.vendor_name)
                index[key].append(tx)
        return index
