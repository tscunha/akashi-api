# Sprint 3: Authentication

## Overview

Implements JWT-based authentication with user management and role-based access control.

## Migration File

`scripts/migrations/001_add_users_table.sql`

## Tables Created

### 1. users

User account storage with tenant isolation.

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    -- Credentials
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),

    -- Role & permissions
    role VARCHAR(50) NOT NULL DEFAULT 'user',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,

    -- Tracking
    last_login_at TIMESTAMP WITH TIME ZONE,
    password_changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    -- Constraints
    UNIQUE (tenant_id, email)
);
```

**Indexes:**
- `idx_users_tenant_id` on `tenant_id`
- `idx_users_email` on `email`
- `idx_users_is_active` on `is_active`

---

## Role System

### Available Roles

| Role | Description | Permissions |
|------|-------------|-------------|
| `admin` | Full access | All operations |
| `manager` | Team management | CRUD + user management |
| `editor` | Content editing | Create, edit, delete assets |
| `viewer` | Read-only | View assets only |
| `user` | Basic access | View + basic operations |

### Superuser

The `is_superuser` flag grants cross-tenant access for system administrators.

---

## Password Security

### Hashing

Passwords are hashed using **bcrypt** with auto-generated salt:

```python
import bcrypt

def get_password_hash(password: str) -> str:
    password_bytes = password.encode("utf-8")[:72]  # bcrypt limit
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(
        plain.encode("utf-8")[:72],
        hashed.encode("utf-8")
    )
```

### Password Requirements

- Minimum 8 characters
- Stored as bcrypt hash (60 chars)
- Password change tracking via `password_changed_at`

---

## JWT Configuration

### Access Token

```python
# Default configuration
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Token payload
{
    "sub": "user_id",
    "tenant_id": "tenant_uuid",
    "role": "admin",
    "exp": 1234567890,
    "iat": 1234567800,
    "type": "access"
}
```

### Token Generation

```python
from jose import jwt
from datetime import datetime, timedelta, timezone

def create_access_token(subject: str, tenant_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    payload = {
        "sub": subject,
        "tenant_id": tenant_id,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
```

---

## API Endpoints

### Authentication

```
POST /api/v1/auth/register     - Create new user
POST /api/v1/auth/login        - Get JWT token
GET  /api/v1/auth/me           - Current user info
PATCH /api/v1/auth/me          - Update profile
POST /api/v1/auth/me/change-password - Change password
```

### User Management (Admin)

```
GET    /api/v1/auth/users           - List users
GET    /api/v1/auth/users/{id}      - Get user
PATCH  /api/v1/auth/users/{id}      - Update user
DELETE /api/v1/auth/users/{id}      - Deactivate user
```

---

## Example Usage

### Register

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123",
    "full_name": "John Doe",
    "role": "editor"
  }'
```

### Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123"
  }'
```

Response:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "role": "editor"
  }
}
```

### Authenticated Request

```bash
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer eyJ..."
```

---

## Security Notes

1. **Email Uniqueness**: Per tenant, not global
2. **Soft Delete**: Users are deactivated, not deleted
3. **Password Truncation**: bcrypt has 72-byte limit
4. **Token Validation**: Checks expiration and type
