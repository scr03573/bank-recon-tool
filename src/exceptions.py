"""
Custom exceptions for the bank reconciliation tool.

Provides structured error handling with specific exception types
for different error scenarios.
"""


class BankReconError(Exception):
    """Base exception for bank reconciliation errors."""

    def __init__(self, message: str, code: str = None, details: dict = None):
        self.message = message
        self.code = code or "BANK_RECON_ERROR"
        self.details = details or {}
        super().__init__(self.message)


# ============== Configuration Errors ==============

class ConfigurationError(BankReconError):
    """Error in configuration settings."""

    def __init__(self, message: str, setting: str = None):
        super().__init__(
            message,
            code="CONFIG_ERROR",
            details={"setting": setting}
        )


class MissingCredentialsError(ConfigurationError):
    """Missing required credentials."""

    def __init__(self, service: str):
        super().__init__(
            f"Missing credentials for {service}",
            setting=f"{service}_credentials"
        )
        self.code = "MISSING_CREDENTIALS"


# ============== Data Errors ==============

class DataError(BankReconError):
    """Error in data processing."""

    def __init__(self, message: str, field: str = None, value: str = None):
        super().__init__(
            message,
            code="DATA_ERROR",
            details={"field": field, "value": value}
        )


class InvalidTransactionError(DataError):
    """Invalid transaction data."""

    def __init__(self, transaction_id: str, reason: str):
        super().__init__(
            f"Invalid transaction {transaction_id}: {reason}",
            field="transaction_id",
            value=transaction_id
        )
        self.code = "INVALID_TRANSACTION"


class ParseError(DataError):
    """Error parsing file or data."""

    def __init__(self, filename: str, line: int = None, reason: str = None):
        message = f"Failed to parse {filename}"
        if line:
            message += f" at line {line}"
        if reason:
            message += f": {reason}"

        super().__init__(
            message,
            field="filename",
            value=filename
        )
        self.code = "PARSE_ERROR"
        self.details["line"] = line


class ValidationError(DataError):
    """Data validation error."""

    def __init__(self, field: str, value: str, constraint: str):
        super().__init__(
            f"Validation failed for {field}: {constraint}",
            field=field,
            value=value
        )
        self.code = "VALIDATION_ERROR"
        self.details["constraint"] = constraint


# ============== Matching Errors ==============

class MatchingError(BankReconError):
    """Error during transaction matching."""

    def __init__(self, message: str, bank_id: str = None, ap_id: str = None):
        super().__init__(
            message,
            code="MATCHING_ERROR",
            details={"bank_transaction_id": bank_id, "ap_transaction_id": ap_id}
        )


class DuplicateMatchError(MatchingError):
    """Transaction already matched."""

    def __init__(self, transaction_id: str, existing_match_id: str):
        super().__init__(
            f"Transaction {transaction_id} already matched to {existing_match_id}",
            bank_id=transaction_id
        )
        self.code = "DUPLICATE_MATCH"
        self.details["existing_match_id"] = existing_match_id


class NoMatchFoundError(MatchingError):
    """No matching transaction found."""

    def __init__(self, transaction_id: str, transaction_type: str = "bank"):
        super().__init__(
            f"No match found for {transaction_type} transaction {transaction_id}",
            bank_id=transaction_id if transaction_type == "bank" else None,
            ap_id=transaction_id if transaction_type == "ap" else None
        )
        self.code = "NO_MATCH_FOUND"


# ============== API Errors ==============

class APIError(BankReconError):
    """Error from external API."""

    def __init__(self, service: str, message: str, status_code: int = None):
        super().__init__(
            f"{service} API error: {message}",
            code="API_ERROR",
            details={"service": service, "status_code": status_code}
        )


class IntacctAPIError(APIError):
    """Error from Sage Intacct API."""

    def __init__(self, message: str, error_code: str = None, status_code: int = None):
        super().__init__("Sage Intacct", message, status_code)
        self.code = "INTACCT_API_ERROR"
        self.details["error_code"] = error_code


class MarketDataError(APIError):
    """Error fetching market data."""

    def __init__(self, provider: str, message: str):
        super().__init__(provider, message)
        self.code = "MARKET_DATA_ERROR"


class FREDAPIError(MarketDataError):
    """Error from FRED API."""

    def __init__(self, message: str, series_id: str = None):
        super().__init__("FRED", message)
        self.code = "FRED_API_ERROR"
        self.details["series_id"] = series_id


# ============== Database Errors ==============

class DatabaseError(BankReconError):
    """Database operation error."""

    def __init__(self, operation: str, message: str):
        super().__init__(
            f"Database {operation} failed: {message}",
            code="DATABASE_ERROR",
            details={"operation": operation}
        )


class RecordNotFoundError(DatabaseError):
    """Record not found in database."""

    def __init__(self, table: str, record_id: str):
        super().__init__(
            "query",
            f"Record {record_id} not found in {table}"
        )
        self.code = "RECORD_NOT_FOUND"
        self.details["table"] = table
        self.details["record_id"] = record_id


# ============== Authentication Errors ==============

class AuthenticationError(BankReconError):
    """Authentication error."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, code="AUTH_ERROR")


class InvalidTokenError(AuthenticationError):
    """Invalid or expired token."""

    def __init__(self, reason: str = "Token is invalid or expired"):
        super().__init__(reason)
        self.code = "INVALID_TOKEN"


class InsufficientPermissionsError(AuthenticationError):
    """User lacks required permissions."""

    def __init__(self, required_permission: str):
        super().__init__(f"Permission '{required_permission}' required")
        self.code = "INSUFFICIENT_PERMISSIONS"
        self.details["required_permission"] = required_permission


# ============== Report Errors ==============

class ReportError(BankReconError):
    """Error generating report."""

    def __init__(self, report_type: str, message: str):
        super().__init__(
            f"Failed to generate {report_type} report: {message}",
            code="REPORT_ERROR",
            details={"report_type": report_type}
        )


class ReportNotFoundError(ReportError):
    """Report file not found."""

    def __init__(self, run_id: str, format: str):
        super().__init__(
            format,
            f"Report not found for run {run_id}"
        )
        self.code = "REPORT_NOT_FOUND"
        self.details["run_id"] = run_id
