"""Configuration management for the reconciliation tool."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class IntacctConfig:
    """Sage Intacct API configuration."""
    sender_id: str = field(default_factory=lambda: os.getenv("INTACCT_SENDER_ID", ""))
    sender_password: str = field(default_factory=lambda: os.getenv("INTACCT_SENDER_PASSWORD", ""))
    user_id: str = field(default_factory=lambda: os.getenv("INTACCT_USER_ID", ""))
    user_password: str = field(default_factory=lambda: os.getenv("INTACCT_USER_PASSWORD", ""))
    company_id: str = field(default_factory=lambda: os.getenv("INTACCT_COMPANY_ID", ""))
    endpoint: str = "https://api.intacct.com/ia/xml/xmlgw.phtml"

    def is_configured(self) -> bool:
        return all([
            self.sender_id, self.sender_password,
            self.user_id, self.user_password, self.company_id
        ])


@dataclass
class MatchingConfig:
    """Matching engine configuration."""
    fuzzy_threshold: int = field(
        default_factory=lambda: int(os.getenv("FUZZY_MATCH_THRESHOLD", "85"))
    )
    date_tolerance_days: int = field(
        default_factory=lambda: int(os.getenv("DATE_TOLERANCE_DAYS", "5"))
    )
    amount_tolerance_percent: float = field(
        default_factory=lambda: float(os.getenv("AMOUNT_TOLERANCE_PERCENT", "0.01"))
    )
    # Weights for scoring matches (must sum to 1.0)
    weight_amount: float = 0.40
    weight_date: float = 0.25
    weight_vendor: float = 0.25
    weight_reference: float = 0.10


@dataclass
class Config:
    """Main application configuration."""
    intacct: IntacctConfig = field(default_factory=IntacctConfig)
    matching: MatchingConfig = field(default_factory=MatchingConfig)
    fred_api_key: str = field(default_factory=lambda: os.getenv("FRED_API_KEY", ""))
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./reconciliation.db")
    )
    data_dir: Path = field(default_factory=lambda: Path("./data"))
    reports_dir: Path = field(default_factory=lambda: Path("./reports"))

    def __post_init__(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


# Global config instance
config = Config()