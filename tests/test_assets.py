"""
AKASHI MAM - Asset API Tests
Simple integration tests using httpx (synchronous).
"""

import pytest
import httpx


BASE_URL = "http://localhost:8000"


@pytest.mark.integration
def test_list_assets():
    """Test listing assets."""
    response = httpx.get(f"{BASE_URL}/api/v1/assets", timeout=10)
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


@pytest.mark.integration
def test_list_assets_with_filters():
    """Test listing assets with filters."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/assets?status=available&asset_type=video",
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    # All returned items should match filters
    for item in data["items"]:
        assert item["status"] == "available"
        assert item["asset_type"] == "video"


@pytest.mark.integration
def test_get_asset_not_found():
    """Test getting non-existent asset returns 404."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/assets/00000000-0000-0000-0000-000000000000",
        timeout=10
    )
    assert response.status_code == 404


@pytest.mark.integration
def test_asset_pagination():
    """Test asset list pagination parameters."""
    response = httpx.get(f"{BASE_URL}/api/v1/assets?page=1&page_size=5", timeout=10)
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert data["page"] == 1
    assert data["page_size"] == 5


@pytest.mark.integration
def test_get_existing_asset():
    """Test getting an existing asset (if any)."""
    # First get the list
    list_response = httpx.get(f"{BASE_URL}/api/v1/assets", timeout=10)
    assert list_response.status_code == 200

    data = list_response.json()
    if data["items"]:
        # Get the first asset
        asset_id = data["items"][0]["id"]
        response = httpx.get(f"{BASE_URL}/api/v1/assets/{asset_id}", timeout=10)
        assert response.status_code == 200

        asset = response.json()
        assert asset["id"] == asset_id
        assert "title" in asset
        assert "status" in asset
        assert "storage_locations" in asset
