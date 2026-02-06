"""
AKASHI MAM - Health Check Tests
Simple integration tests using httpx (synchronous).
"""

import pytest
import httpx


BASE_URL = "http://localhost:8000"


@pytest.mark.integration
def test_health_check():
    """Test the health check endpoint returns OK."""
    response = httpx.get(f"{BASE_URL}/api/v1/health", timeout=10)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert "database" in data
    assert "storage" in data


@pytest.mark.integration
def test_root_endpoint():
    """Test the root endpoint."""
    response = httpx.get(f"{BASE_URL}/", timeout=10)
    assert response.status_code == 200

    data = response.json()
    assert "name" in data
    assert "AKASHI" in data["name"]


@pytest.mark.integration
def test_assets_list():
    """Test the assets list endpoint."""
    response = httpx.get(f"{BASE_URL}/api/v1/assets", timeout=10)
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


@pytest.mark.integration
def test_jobs_list():
    """Test the jobs list endpoint."""
    response = httpx.get(f"{BASE_URL}/api/v1/jobs", timeout=10)
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)


@pytest.mark.integration
def test_asset_not_found():
    """Test 404 for non-existent asset."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/assets/00000000-0000-0000-0000-000000000000",
        timeout=10
    )
    assert response.status_code == 404
