"""
AKASHI MAM - Collections API Tests
Integration tests using httpx (synchronous).
"""

import pytest
import httpx
import uuid


BASE_URL = "http://localhost:8000"


@pytest.fixture
def auth_token():
    """Get an auth token for testing."""
    # Create a test user
    unique_email = f"coll_test_{uuid.uuid4().hex[:8]}@akashi.io"
    httpx.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={"email": unique_email, "password": "testpassword123"},
        timeout=10
    )

    # Login
    response = httpx.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": unique_email, "password": "testpassword123"},
        timeout=10
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    pytest.skip("Could not get auth token")


@pytest.fixture
def test_asset_id():
    """Get an existing asset ID for testing."""
    response = httpx.get(f"{BASE_URL}/api/v1/assets?page_size=1", timeout=10)
    if response.status_code == 200 and response.json()["items"]:
        return response.json()["items"][0]["id"]
    pytest.skip("No assets available for testing")


@pytest.mark.integration
def test_list_collections_public():
    """Test listing public collections without auth."""
    response = httpx.get(f"{BASE_URL}/api/v1/collections", timeout=10)
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


@pytest.mark.integration
def test_create_collection(auth_token):
    """Test creating a collection."""
    response = httpx.post(
        f"{BASE_URL}/api/v1/collections",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "name": f"Test Collection {uuid.uuid4().hex[:8]}",
            "description": "A test collection",
            "collection_type": "manual",
            "is_public": True,
        },
        timeout=10
    )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["collection_type"] == "manual"
    assert data["is_public"] is True
    assert data["item_count"] == 0


@pytest.mark.integration
def test_create_collection_without_auth():
    """Test that creating collection requires auth."""
    response = httpx.post(
        f"{BASE_URL}/api/v1/collections",
        json={"name": "Should Fail", "collection_type": "manual"},
        timeout=10
    )
    assert response.status_code == 401


@pytest.mark.integration
def test_get_collection(auth_token):
    """Test getting a specific collection."""
    # Create a collection first
    create_response = httpx.post(
        f"{BASE_URL}/api/v1/collections",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"name": f"Get Test {uuid.uuid4().hex[:8]}", "is_public": True},
        timeout=10
    )
    assert create_response.status_code == 201
    collection_id = create_response.json()["id"]

    # Get the collection
    response = httpx.get(
        f"{BASE_URL}/api/v1/collections/{collection_id}",
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == collection_id
    assert "items" in data


@pytest.mark.integration
def test_update_collection(auth_token):
    """Test updating a collection."""
    # Create a collection
    create_response = httpx.post(
        f"{BASE_URL}/api/v1/collections",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"name": "Original Name", "is_public": True},
        timeout=10
    )
    collection_id = create_response.json()["id"]

    # Update it
    response = httpx.patch(
        f"{BASE_URL}/api/v1/collections/{collection_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"name": "Updated Name", "description": "New description"},
        timeout=10
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "New description"


@pytest.mark.integration
def test_delete_collection(auth_token):
    """Test deleting a collection."""
    # Create a collection
    create_response = httpx.post(
        f"{BASE_URL}/api/v1/collections",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"name": f"Delete Test {uuid.uuid4().hex[:8]}"},
        timeout=10
    )
    collection_id = create_response.json()["id"]

    # Delete it
    response = httpx.delete(
        f"{BASE_URL}/api/v1/collections/{collection_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=10
    )
    assert response.status_code == 200

    # Verify it's gone
    get_response = httpx.get(
        f"{BASE_URL}/api/v1/collections/{collection_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=10
    )
    assert get_response.status_code == 404


@pytest.mark.integration
def test_add_item_to_collection(auth_token, test_asset_id):
    """Test adding an asset to a collection."""
    # Create a collection
    create_response = httpx.post(
        f"{BASE_URL}/api/v1/collections",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"name": f"Items Test {uuid.uuid4().hex[:8]}"},
        timeout=10
    )
    collection_id = create_response.json()["id"]

    # Add an item
    response = httpx.post(
        f"{BASE_URL}/api/v1/collections/{collection_id}/items",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"asset_id": test_asset_id},
        timeout=10
    )
    assert response.status_code == 201

    data = response.json()
    assert data["asset_id"] == test_asset_id
    assert data["collection_id"] == collection_id


@pytest.mark.integration
def test_remove_item_from_collection(auth_token, test_asset_id):
    """Test removing an asset from a collection."""
    # Create a collection and add an item
    create_response = httpx.post(
        f"{BASE_URL}/api/v1/collections",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"name": f"Remove Test {uuid.uuid4().hex[:8]}"},
        timeout=10
    )
    collection_id = create_response.json()["id"]

    httpx.post(
        f"{BASE_URL}/api/v1/collections/{collection_id}/items",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"asset_id": test_asset_id},
        timeout=10
    )

    # Remove the item
    response = httpx.delete(
        f"{BASE_URL}/api/v1/collections/{collection_id}/items/{test_asset_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=10
    )
    assert response.status_code == 200


@pytest.mark.integration
def test_collection_item_count(auth_token, test_asset_id):
    """Test that item_count is updated correctly."""
    # Create a collection
    create_response = httpx.post(
        f"{BASE_URL}/api/v1/collections",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"name": f"Count Test {uuid.uuid4().hex[:8]}", "is_public": True},
        timeout=10
    )
    collection_id = create_response.json()["id"]
    assert create_response.json()["item_count"] == 0

    # Add an item
    httpx.post(
        f"{BASE_URL}/api/v1/collections/{collection_id}/items",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"asset_id": test_asset_id},
        timeout=10
    )

    # Check count
    get_response = httpx.get(
        f"{BASE_URL}/api/v1/collections/{collection_id}",
        timeout=10
    )
    assert get_response.json()["item_count"] == 1
