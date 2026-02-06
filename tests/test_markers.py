"""
AKASHI MAM - Markers API Tests
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
def test_list_asset_markers(test_asset_id):
    """Test listing markers for an asset."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/assets/{test_asset_id}/markers",
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


@pytest.mark.integration
def test_create_marker(test_asset_id):
    """Test creating a marker on an asset."""
    marker_data = {
        "marker_type": "comment",
        "name": "Test Marker",
        "start_ms": 2000,
        "duration_ms": 500,
        "note": "This is a test marker",
        "color": "#00FF00",
    }

    response = httpx.post(
        f"{BASE_URL}/api/v1/assets/{test_asset_id}/markers",
        json=marker_data,
        timeout=10
    )
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == marker_data["name"]
    assert data["start_ms"] == marker_data["start_ms"]
    assert data["marker_type"] == marker_data["marker_type"]
    assert data["asset_id"] == test_asset_id


@pytest.mark.integration
def test_create_chapter_marker(test_asset_id):
    """Test creating a chapter marker."""
    marker_data = {
        "marker_type": "chapter",
        "name": "Test Chapter",
        "start_ms": 0,
        "color": "#FF0000",
    }

    response = httpx.post(
        f"{BASE_URL}/api/v1/assets/{test_asset_id}/markers",
        json=marker_data,
        timeout=10
    )
    assert response.status_code == 201

    data = response.json()
    assert data["marker_type"] == "chapter"


@pytest.mark.integration
def test_get_marker():
    """Test getting a specific marker by ID."""
    # First get an asset with markers
    response = httpx.get(f"{BASE_URL}/api/v1/assets?page_size=1", timeout=10)
    assert response.status_code == 200
    data = response.json()

    if not data["items"]:
        pytest.skip("No assets available")

    asset_id = data["items"][0]["id"]

    # Get markers for this asset
    markers_response = httpx.get(
        f"{BASE_URL}/api/v1/assets/{asset_id}/markers",
        timeout=10
    )
    assert markers_response.status_code == 200
    markers_data = markers_response.json()

    if not markers_data["items"]:
        pytest.skip("No markers available for testing")

    marker_id = markers_data["items"][0]["id"]

    # Get the specific marker
    response = httpx.get(
        f"{BASE_URL}/api/v1/markers/{marker_id}",
        timeout=10
    )
    assert response.status_code == 200

    marker = response.json()
    assert marker["id"] == marker_id


@pytest.mark.integration
def test_update_marker():
    """Test updating a marker."""
    # Get an existing marker
    response = httpx.get(f"{BASE_URL}/api/v1/assets?page_size=1", timeout=10)
    data = response.json()

    if not data["items"]:
        pytest.skip("No assets available")

    asset_id = data["items"][0]["id"]
    markers_response = httpx.get(
        f"{BASE_URL}/api/v1/assets/{asset_id}/markers",
        timeout=10
    )
    markers_data = markers_response.json()

    if not markers_data["items"]:
        pytest.skip("No markers available")

    marker_id = markers_data["items"][0]["id"]

    # Update the marker
    update_data = {"note": "Updated note"}
    response = httpx.patch(
        f"{BASE_URL}/api/v1/markers/{marker_id}",
        json=update_data,
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    assert data["note"] == "Updated note"


@pytest.mark.integration
def test_marker_not_found():
    """Test 404 for non-existent marker."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/markers/00000000-0000-0000-0000-000000000000",
        timeout=10
    )
    assert response.status_code == 404


@pytest.mark.integration
def test_asset_response_includes_markers(test_asset_id):
    """Test that asset response includes markers."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/assets/{test_asset_id}",
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    assert "markers" in data
    assert isinstance(data["markers"], list)


@pytest.mark.integration
def test_filter_markers_by_type(test_asset_id):
    """Test filtering markers by type."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/assets/{test_asset_id}/markers?marker_type=chapter",
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    # All returned markers should be chapters
    for marker in data["items"]:
        assert marker["marker_type"] == "chapter"
