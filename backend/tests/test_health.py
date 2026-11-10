"""Unit tests for root and health check endpoints."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root_endpoint():
    """Verify root endpoint returns basic application information."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "RepoPilot AI"
    assert data["status"] == "online"
    assert "version" in data
    assert "health_url" in data


def test_health_check_endpoint():
    """Verify health endpoint returns status 200 and valid schema."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "environment" in data
    assert "timestamp" in data
    assert "subsystems" in data
    assert isinstance(data["subsystems"], dict)

