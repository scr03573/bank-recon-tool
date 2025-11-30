"""Sage Intacct Web Services API client."""
import hashlib
import time
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
import requests
import xmltodict
from xml.etree import ElementTree as ET

from .config import config, IntacctConfig
from .models import APTransaction, TransactionType


class IntacctAPIError(Exception):
    """Raised when Intacct API returns an error."""
    pass


class IntacctClient:
    """Client for Sage Intacct Web Services API."""

    def __init__(self, cfg: Optional[IntacctConfig] = None):
        self.config = cfg or config.intacct
        self._session_id: Optional[str] = None
        self._session_timestamp: float = 0
        self._session_timeout = 300  # 5 minutes

    def _get_control_block(self) -> str:
        """Generate XML control block."""
        control_id = str(uuid.uuid4())
        return f"""
        <control>
            <senderid>{self.config.sender_id}</senderid>
            <password>{self.config.sender_password}</password>
            <controlid>{control_id}</controlid>
            <uniqueid>false</uniqueid>
            <dtdversion>3.0</dtdversion>
            <includewhitespace>false</includewhitespace>
        </control>
        """

    def _get_authentication_block(self) -> str:
        """Generate XML authentication block."""
        return f"""
        <authentication>
            <login>
                <userid>{self.config.user_id}</userid>
                <companyid>{self.config.company_id}</companyid>
                <password>{self.config.user_password}</password>
            </login>
        </authentication>
        """

    def _build_request(self, function_xml: str) -> str:
        """Build complete XML request."""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
        <request>
            {self._get_control_block()}
            <operation>
                {self._get_authentication_block()}
                <content>
                    <function controlid="{uuid.uuid4()}">
                        {function_xml}
                    </function>
                </content>
            </operation>
        </request>
        """

    def _send_request(self, xml_request: str) -> Dict[str, Any]:
        """Send request to Intacct API."""
        headers = {"Content-Type": "application/xml"}

        try:
            response = requests.post(
                self.config.endpoint,
                data=xml_request,
                headers=headers,
                timeout=60
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise IntacctAPIError(f"HTTP request failed: {e}")

        # Parse XML response
        try:
            result = xmltodict.parse(response.text)
        except Exception as e:
            raise IntacctAPIError(f"Failed to parse XML response: {e}")

        # Check for API errors
        if "response" in result:
            resp = result["response"]
            if "errormessage" in resp.get("control", {}):
                error = resp["control"]["errormessage"]
                raise IntacctAPIError(f"API error: {error}")

            operation = resp.get("operation", {})
            if operation.get("result", {}).get("status") == "failure":
                error = operation["result"].get("errormessage", "Unknown error")
                raise IntacctAPIError(f"Operation failed: {error}")

        return result

    def get_ap_payments(
        self,
        start_date: date,
        end_date: date,
        bank_account_id: Optional[str] = None
    ) -> List[APTransaction]:
        """Fetch AP payment records from Intacct."""

        # Build query filter
        filters = [
            f"<greaterthanorequalto><field>WHENPAID</field><value>{start_date.isoformat()}</value></greaterthanorequalto>",
            f"<lessthanorequalto><field>WHENPAID</field><value>{end_date.isoformat()}</value></lessthanorequalto>",
        ]

        if bank_account_id:
            filters.append(
                f"<equalto><field>BANKACCOUNTID</field><value>{bank_account_id}</value></equalto>"
            )

        filter_xml = "<and>" + "".join(filters) + "</and>" if len(filters) > 1 else filters[0]

        function_xml = f"""
        <readByQuery>
            <object>APPYMT</object>
            <fields>*</fields>
            <query>{filter_xml}</query>
            <pagesize>1000</pagesize>
        </readByQuery>
        """

        request_xml = self._build_request(function_xml)
        result = self._send_request(request_xml)

        return self._parse_ap_payments(result)

    def get_ap_bills(
        self,
        start_date: date,
        end_date: date,
        state: str = "Paid"
    ) -> List[APTransaction]:
        """Fetch AP bill records from Intacct."""

        function_xml = f"""
        <readByQuery>
            <object>APBILL</object>
            <fields>*</fields>
            <query>
                <and>
                    <greaterthanorequalto>
                        <field>WHENDUE</field>
                        <value>{start_date.isoformat()}</value>
                    </greaterthanorequalto>
                    <lessthanorequalto>
                        <field>WHENDUE</field>
                        <value>{end_date.isoformat()}</value>
                    </lessthanorequalto>
                    <equalto>
                        <field>STATE</field>
                        <value>{state}</value>
                    </equalto>
                </and>
            </query>
            <pagesize>1000</pagesize>
        </readByQuery>
        """

        request_xml = self._build_request(function_xml)
        result = self._send_request(request_xml)

        return self._parse_ap_bills(result)

    def get_checking_account_transactions(
        self,
        bank_account_id: str,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """Fetch checking account transactions."""

        function_xml = f"""
        <readByQuery>
            <object>CHECKINGACCOUNT</object>
            <fields>*</fields>
            <query>
                <and>
                    <equalto>
                        <field>BANKACCOUNTID</field>
                        <value>{bank_account_id}</value>
                    </equalto>
                    <greaterthanorequalto>
                        <field>ENTRY_DATE</field>
                        <value>{start_date.isoformat()}</value>
                    </greaterthanorequalto>
                    <lessthanorequalto>
                        <field>ENTRY_DATE</field>
                        <value>{end_date.isoformat()}</value>
                    </lessthanorequalto>
                </and>
            </query>
            <pagesize>1000</pagesize>
        </readByQuery>
        """

        request_xml = self._build_request(function_xml)
        result = self._send_request(request_xml)

        return self._extract_data(result)

    def get_vendors(self) -> Dict[str, str]:
        """Fetch vendor ID to name mapping."""

        function_xml = """
        <readByQuery>
            <object>VENDOR</object>
            <fields>VENDORID,NAME</fields>
            <query></query>
            <pagesize>2000</pagesize>
        </readByQuery>
        """

        request_xml = self._build_request(function_xml)
        result = self._send_request(request_xml)

        vendors = {}
        data = self._extract_data(result)
        for vendor in data:
            if isinstance(vendor, dict):
                vendors[vendor.get("VENDORID", "")] = vendor.get("NAME", "")

        return vendors

    def _parse_ap_payments(self, result: Dict) -> List[APTransaction]:
        """Parse AP payment response into APTransaction objects."""
        transactions = []
        data = self._extract_data(result)

        for record in data:
            if not isinstance(record, dict):
                continue

            tx = APTransaction(
                id=str(record.get("RECORDNO", "")),
                record_number=str(record.get("RECORDNO", "")),
                vendor_id=str(record.get("VENDORID", "")),
                vendor_name=str(record.get("VENDORNAME", "")),
                payment_date=self._parse_date(record.get("WHENPAID")),
                amount=self._parse_decimal(record.get("TOTALENTERED")),
                paid_amount=self._parse_decimal(record.get("TOTALPAID")),
                payment_method=str(record.get("PAYMENTMETHOD", "")),
                check_number=str(record.get("DOCNUMBER", "")) or None,
                bank_account_id=str(record.get("BANKACCOUNTID", "")),
                description=str(record.get("DESCRIPTION", "")),
                state=str(record.get("STATE", ""))
            )
            transactions.append(tx)

        return transactions

    def _parse_ap_bills(self, result: Dict) -> List[APTransaction]:
        """Parse AP bill response into APTransaction objects."""
        transactions = []
        data = self._extract_data(result)

        for record in data:
            if not isinstance(record, dict):
                continue

            tx = APTransaction(
                id=str(record.get("RECORDNO", "")),
                record_number=str(record.get("RECORDNO", "")),
                vendor_id=str(record.get("VENDORID", "")),
                vendor_name=str(record.get("VENDORNAME", "")),
                bill_number=str(record.get("BILLNO", "")) or None,
                due_date=self._parse_date(record.get("WHENDUE")),
                payment_date=self._parse_date(record.get("WHENPAID")),
                amount=self._parse_decimal(record.get("TOTALDUE")),
                paid_amount=self._parse_decimal(record.get("TOTALPAID")),
                bank_account_id=str(record.get("BANKACCOUNTID", "")),
                description=str(record.get("DESCRIPTION", "")),
                state=str(record.get("STATE", ""))
            )
            transactions.append(tx)

        return transactions

    def _extract_data(self, result: Dict) -> List[Dict]:
        """Extract data array from API response."""
        try:
            operation = result.get("response", {}).get("operation", {})
            result_data = operation.get("result", {}).get("data", {})

            # Handle single vs multiple records
            if isinstance(result_data, dict):
                # Check for object wrapper (e.g., {"appymt": [...]})
                for key in result_data:
                    if isinstance(result_data[key], list):
                        return result_data[key]
                    elif isinstance(result_data[key], dict):
                        return [result_data[key]]
                return [result_data] if result_data else []
            elif isinstance(result_data, list):
                return result_data
            else:
                return []
        except (KeyError, TypeError):
            return []

    def _parse_date(self, value: Any) -> Optional[date]:
        """Parse date from various formats."""
        if not value:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError:
            try:
                return datetime.strptime(str(value), "%m/%d/%Y").date()
            except ValueError:
                return None

    def _parse_decimal(self, value: Any) -> Decimal:
        """Parse decimal from various formats."""
        if value is None:
            return Decimal("0")
        try:
            return Decimal(str(value).replace(",", ""))
        except:
            return Decimal("0")


class MockIntacctClient(IntacctClient):
    """Mock client for testing without API access."""

    def __init__(self, cfg: Optional[IntacctConfig] = None):
        super().__init__(cfg)
        self._mock_data: Dict[str, List] = {}

    def load_mock_data(self, ap_transactions: List[APTransaction]):
        """Load mock AP transaction data."""
        self._mock_data["ap_transactions"] = ap_transactions

    def get_ap_payments(
        self,
        start_date: date,
        end_date: date,
        bank_account_id: Optional[str] = None
    ) -> List[APTransaction]:
        """Return mock AP payment data."""
        transactions = self._mock_data.get("ap_transactions", [])

        # Filter by date and bank account
        filtered = []
        for tx in transactions:
            if tx.payment_date and start_date <= tx.payment_date <= end_date:
                if not bank_account_id or tx.bank_account_id == bank_account_id:
                    filtered.append(tx)

        return filtered

    def _send_request(self, xml_request: str) -> Dict[str, Any]:
        """Override to prevent actual API calls."""
        raise IntacctAPIError("Mock client - no API calls allowed. Use load_mock_data().")