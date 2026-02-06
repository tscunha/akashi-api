"""
AKASHI MAM - Search API Tests
Integration tests using httpx (synchronous).
"""

import pytest
import httpx


BASE_URL = "http://localhost:8000"


@pytest.mark.integration
def test_search_basic():
    """Test basic search functionality."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/search?q=test",
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    assert "query" in data
    assert data["query"] == "test"
    assert "total" in data
    assert "results" in data
    assert "search_time_ms" in data
    assert isinstance(data["results"], list)


@pytest.mark.integration
def test_search_with_filters():
    """Test search with type filter."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/search?q=video&asset_type=video",
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    # All results should be videos
    for result in data["results"]:
        assert result["asset_type"] == "video"


@pytest.mark.integration
def test_search_pagination():
    """Test search pagination."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/search?q=test&page=1&page_size=5",
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 5
    assert len(data["results"]) <= 5


@pytest.mark.integration
def test_search_min_query_length():
    """Test that search requires minimum query length."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/search?q=a",
        timeout=10
    )
    # Should fail validation (min length is 2)
    assert response.status_code == 422


@pytest.mark.integration
def test_search_suggestions():
    """Test search suggestions endpoint."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/search/suggestions?q=int",
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    for suggestion in data:
        assert "text" in suggestion
        assert "type" in suggestion


@pytest.mark.integration
def test_advanced_search():
    """Test advanced search with multiple filters."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/search/advanced?asset_type=video&sort_by=created_at&sort_order=desc",
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    assert "results" in data
    assert "total" in data


@pytest.mark.integration
def test_advanced_search_with_duration():
    """Test advanced search with duration filter."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/search/advanced?min_duration_ms=1000&max_duration_ms=60000",
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    # All results should be within duration range
    for result in data["results"]:
        if result["duration_ms"] is not None:
            assert result["duration_ms"] >= 1000
            assert result["duration_ms"] <= 60000


@pytest.mark.integration
def test_search_returns_metadata():
    """Test that search returns proper metadata."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/search?q=test",
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    assert "search_time_ms" in data
    assert isinstance(data["search_time_ms"], int)
    assert data["search_time_ms"] >= 0
