"""
Tests for API endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from datetime import date, timedelta
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.api import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoints:
    """Tests for health/status endpoints."""

    def test_root_endpoint(self, client):
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Bank Reconciliation API"
        assert data["status"] == "running"

    def test_status_endpoint(self, client):
        """Test status endpoint returns configuration."""
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "intacct_configured" in data
        assert "fred_configured" in data
        assert "fuzzy_threshold" in data
        assert data["fuzzy_threshold"] == 85


class TestReconciliationEndpoints:
    """Tests for reconciliation endpoints."""

    def test_run_demo_reconciliation(self, client):
        """Test running demo reconciliation."""
        response = client.post("/api/reconcile/demo")
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "completed"
        assert data["total_bank_transactions"] > 0
        assert data["matched_count"] >= 0

    def test_get_reconciliation_history(self, client):
        """Test getting reconciliation history."""
        # Run a demo first to have history
        client.post("/api/reconcile/demo")

        response = client.get("/api/reconcile/history?page=1&page_size=5")
        assert response.status_code == 200
        data = response.json()
        # New paginated response format
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert isinstance(data["items"], list)

    def test_get_matches_for_run(self, client):
        """Test getting matches for a specific run."""
        # Run demo first
        demo_response = client.post("/api/reconcile/demo")
        run_id = demo_response.json()["run_id"]

        response = client.get(f"/api/reconcile/{run_id}/matches")
        assert response.status_code == 200
        data = response.json()
        assert "matches" in data
        assert "count" in data

    def test_get_matches_invalid_run(self, client):
        """Test getting matches for invalid run ID."""
        response = client.get("/api/reconcile/invalid-run-id/matches")
        assert response.status_code == 404

    def test_get_exceptions_for_run(self, client):
        """Test getting exceptions for a specific run."""
        demo_response = client.post("/api/reconcile/demo")
        run_id = demo_response.json()["run_id"]

        response = client.get(f"/api/reconcile/{run_id}/exceptions")
        assert response.status_code == 200
        data = response.json()
        assert "exceptions" in data
        assert "count" in data


class TestMarketDataEndpoints:
    """Tests for market data endpoints."""

    def test_get_market_snapshot(self, client):
        """Test getting market snapshot."""
        response = client.get("/api/market/snapshot")
        assert response.status_code == 200
        data = response.json()
        assert "as_of" in data
        assert "market_status" in data

    def test_get_economic_indicators(self, client):
        """Test getting economic indicators."""
        response = client.get("/api/market/economic")
        assert response.status_code == 200
        data = response.json()
        # Should have some indicators if FRED is configured
        assert isinstance(data, dict)


class TestExceptionEndpoints:
    """Tests for exception management endpoints."""

    def test_get_exceptions(self, client):
        """Test getting all exceptions."""
        # Run demo to generate exceptions
        client.post("/api/reconcile/demo")

        response = client.get("/api/exceptions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_exceptions_filtered(self, client):
        """Test getting filtered exceptions."""
        client.post("/api/reconcile/demo")

        response = client.get("/api/exceptions?unresolved_only=true")
        assert response.status_code == 200
        data = response.json()
        # All returned should be unresolved
        for exc in data:
            assert exc["is_resolved"] is False


class TestInputValidation:
    """Tests for input validation."""

    def test_history_pagination(self, client):
        """Test history pagination parameters."""
        response = client.get("/api/reconcile/history?page=1&page_size=5")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5

    def test_history_page_size_max(self, client):
        """Test history page size max value."""
        response = client.get("/api/reconcile/history?page=1&page_size=100")
        assert response.status_code == 200
