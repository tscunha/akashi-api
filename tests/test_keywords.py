"""
AKASHI MAM - Keywords API Tests
Integration tests using httpx (synchronous).
"""

import pytest
import httpx


BASE_URL = "http://localhost:8000"


@pytest.fixture
def test_asset_id():
    """Get an existing asset ID for testing."""
    response = httpx.get(f"{BASE_URL}/api/v1/assets?page_size=1", timeout=10)
    assert response.status_code == 200
    data = response.json()
    if data["items"]:
        return data["items"][0]["id"]
    pytest.skip("No assets available for testing")


@pytest.mark.integration
def test_list_asset_keywords(test_asset_id):
    """Test listing keywords for an asset."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/assets/{test_asset_id}/keywords",
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


@pytest.mark.integration
def test_create_keyword(test_asset_id):
    """Test creating a keyword on an asset."""
    keyword_data = {
        "keyword": "test_keyword_" + str(hash(test_asset_id))[:8],
        "start_ms": 500,
        "end_ms": 1500,
        "source": "manual",
    }

    response = httpx.post(
        f"{BASE_URL}/api/v1/assets/{test_asset_id}/keywords",
        json=keyword_data,
        timeout=10
    )

    # May fail if keyword already exists
    if response.status_code == 400:
        pytest.skip("Keyword already exists")

    assert response.status_code == 201

    data = response.json()
    assert data["keyword"] == keyword_data["keyword"]
    assert data["start_ms"] == keyword_data["start_ms"]
    assert data["asset_id"] == test_asset_id


@pytest.mark.integration
def test_get_keyword():
    """Test getting a specific keyword by ID."""
    # First get an asset with keywords
    response = httpx.get(f"{BASE_URL}/api/v1/assets?page_size=1", timeout=10)
    assert response.status_code == 200
    data = response.json()

    if not data["items"]:
        pytest.skip("No assets available")

    asset_id = data["items"][0]["id"]

    # Get keywords for this asset
    keywords_response = httpx.get(
        f"{BASE_URL}/api/v1/assets/{asset_id}/keywords",
        timeout=10
    )
    assert keywords_response.status_code == 200
    keywords_data = keywords_response.json()

    if not keywords_data["items"]:
        pytest.skip("No keywords available for testing")

    keyword_id = keywords_data["items"][0]["id"]

    # Get the specific keyword
    response = httpx.get(
        f"{BASE_URL}/api/v1/keywords/{keyword_id}",
        timeout=10
    )
    assert response.status_code == 200

    keyword = response.json()
    assert keyword["id"] == keyword_id


@pytest.mark.integration
def test_search_keywords():
    """Test keyword search functionality."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/keywords/search?q=in",  # Should match 'interview'
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    # Each result should have asset info
    for item in data:
        assert "keyword" in item
        assert "asset_id" in item
        assert "asset_title" in item


@pytest.mark.integration
def test_keyword_not_found():
    """Test 404 for non-existent keyword."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/keywords/00000000-0000-0000-0000-000000000000",
        timeout=10
    )
    assert response.status_code == 404


@pytest.mark.integration
def test_asset_response_includes_keywords(test_asset_id):
    """Test that asset response includes keywords."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/assets/{test_asset_id}",
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    assert "keywords" in data
    assert isinstance(data["keywords"], list)
