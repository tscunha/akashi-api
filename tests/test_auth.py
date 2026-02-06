"""
AKASHI MAM - Authentication API Tests
Integration tests using httpx (synchronous).
"""

import pytest
import httpx
import uuid


BASE_URL = "http://localhost:8000"

# Test user credentials
TEST_EMAIL = f"test_{uuid.uuid4().hex[:8]}@akashi.io"
TEST_PASSWORD = "testpassword123"
TEST_USER_ID = None
TEST_TOKEN = None


@pytest.fixture(scope="module")
def test_user():
    """Create a test user and return credentials."""
    global TEST_USER_ID, TEST_TOKEN

    # Register a new user
    response = httpx.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "full_name": "Test User",
            "role": "user",
        },
        timeout=10
    )

    if response.status_code == 201:
        data = response.json()
        TEST_USER_ID = data["id"]

        # Login to get token
        login_response = httpx.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=10
        )
        if login_response.status_code == 200:
            TEST_TOKEN = login_response.json()["access_token"]

    return {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "user_id": TEST_USER_ID,
        "token": TEST_TOKEN,
    }


@pytest.mark.integration
def test_register_user():
    """Test user registration."""
    unique_email = f"new_{uuid.uuid4().hex[:8]}@akashi.io"
    response = httpx.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "securepassword123",
            "full_name": "New User",
            "role": "user",
        },
        timeout=10
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == unique_email
    assert data["full_name"] == "New User"
    assert data["role"] == "user"
    assert data["is_active"] is True
    assert "id" in data


@pytest.mark.integration
def test_register_duplicate_email():
    """Test that duplicate email registration fails."""
    unique_email = f"dup_{uuid.uuid4().hex[:8]}@akashi.io"

    # First registration
    response1 = httpx.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "password123",
            "full_name": "User One",
        },
        timeout=10
    )
    assert response1.status_code == 201

    # Second registration with same email
    response2 = httpx.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "password456",
            "full_name": "User Two",
        },
        timeout=10
    )
    assert response2.status_code == 400
    assert "already registered" in response2.json()["detail"]


@pytest.mark.integration
def test_login_success(test_user):
    """Test successful login."""
    response = httpx.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={
            "email": test_user["email"],
            "password": test_user["password"],
        },
        timeout=10
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "expires_in" in data
    assert "user" in data
    assert data["user"]["email"] == test_user["email"]


@pytest.mark.integration
def test_login_wrong_password():
    """Test login with wrong password."""
    unique_email = f"wrong_{uuid.uuid4().hex[:8]}@akashi.io"

    # Create user first
    httpx.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={"email": unique_email, "password": "correctpassword"},
        timeout=10
    )

    # Try login with wrong password
    response = httpx.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": unique_email, "password": "wrongpassword"},
        timeout=10
    )

    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]


@pytest.mark.integration
def test_login_nonexistent_user():
    """Test login with non-existent user."""
    response = httpx.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={
            "email": "nonexistent@akashi.io",
            "password": "somepassword",
        },
        timeout=10
    )

    assert response.status_code == 401


@pytest.mark.integration
def test_get_current_user(test_user):
    """Test getting current user info."""
    if not test_user["token"]:
        pytest.skip("No token available")

    response = httpx.get(
        f"{BASE_URL}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {test_user['token']}"},
        timeout=10
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user["email"]
    assert "id" in data
    assert "created_at" in data


@pytest.mark.integration
def test_get_current_user_no_token():
    """Test getting current user without token."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/auth/me",
        timeout=10
    )

    assert response.status_code == 401


@pytest.mark.integration
def test_get_current_user_invalid_token():
    """Test getting current user with invalid token."""
    response = httpx.get(
        f"{BASE_URL}/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid_token_here"},
        timeout=10
    )

    assert response.status_code == 401


@pytest.mark.integration
def test_update_current_user(test_user):
    """Test updating current user profile."""
    if not test_user["token"]:
        pytest.skip("No token available")

    response = httpx.patch(
        f"{BASE_URL}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {test_user['token']}"},
        json={"full_name": "Updated Name"},
        timeout=10
    )

    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Updated Name"


@pytest.mark.integration
def test_change_password():
    """Test changing user password."""
    # Create a new user for this test
    unique_email = f"pwchange_{uuid.uuid4().hex[:8]}@akashi.io"
    old_password = "oldpassword123"
    new_password = "newpassword456"

    # Register
    httpx.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={"email": unique_email, "password": old_password},
        timeout=10
    )

    # Login
    login_resp = httpx.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": unique_email, "password": old_password},
        timeout=10
    )
    token = login_resp.json()["access_token"]

    # Change password
    response = httpx.post(
        f"{BASE_URL}/api/v1/auth/me/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": old_password,
            "new_password": new_password,
        },
        timeout=10
    )

    assert response.status_code == 200
    assert "Password changed" in response.json()["message"]

    # Verify old password no longer works
    old_login = httpx.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": unique_email, "password": old_password},
        timeout=10
    )
    assert old_login.status_code == 401

    # Verify new password works
    new_login = httpx.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": unique_email, "password": new_password},
        timeout=10
    )
    assert new_login.status_code == 200
