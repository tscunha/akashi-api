# Sprint 5: Security & Background Processing

## Overview

Implements refresh tokens for secure token rotation and completes the Celery worker infrastructure.

## Migration File

`scripts/migrations/003_add_refresh_tokens.sql`

## Tables Created

### 1. refresh_tokens

Stores hashed refresh tokens for JWT rotation.

```sql
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Token (stored as hash, never plaintext)
    token_hash VARCHAR(255) NOT NULL UNIQUE,

    -- Client metadata
    device_info TEXT,
    ip_address VARCHAR(45),          -- IPv6 compatible
    user_agent TEXT,

    -- Status
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    revoked_reason VARCHAR(255),     -- logout, expired, rotated, security

    -- Expiration
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    last_used_at TIMESTAMP WITH TIME ZONE
);
```

**Indexes:**
- `idx_refresh_tokens_user_id` on `user_id`
- `idx_refresh_tokens_token_hash` on `token_hash`
- `idx_refresh_tokens_expires_at` on `expires_at`
- `idx_refresh_tokens_active` on `is_revoked` WHERE `is_revoked = FALSE`

---

## Token Flow

### Login Flow

```
1. User submits credentials
2. Server validates password
3. Server creates:
   - Access token (JWT, 30 min)
   - Refresh token (random, 7 days)
4. Refresh token hash stored in DB
5. Both tokens returned to client
```

### Refresh Flow

```
1. Client sends refresh token
2. Server hashes token, looks up in DB
3. Validates: not revoked, not expired
4. If token rotation enabled:
   - Revoke old token
   - Create new refresh token
5. Create new access token
6. Return new token pair
```

### Logout Flow

```
1. Client sends refresh token
2. Server marks token as revoked
3. Reason: "logout"
```

---

## Token Security

### Refresh Token Format

```python
import secrets

def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)  # 64 chars base64
```

### Token Hashing

```python
import hashlib

def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
```

### Why Hash?

- Tokens are **never** stored in plaintext
- Even if DB is compromised, tokens can't be used
- SHA-256 is fast enough for lookups with index

---

## Configuration

```python
# app/core/config.py

# Access token: short-lived
jwt_access_token_expire_minutes: int = 30

# Refresh token: longer-lived
jwt_refresh_token_expire_days: int = 7

# Token rotation: issue new refresh on each use
jwt_refresh_token_rotate: bool = True
```

---

## Revocation Reasons

| Reason | Description |
|--------|-------------|
| `logout` | User explicitly logged out |
| `expired` | Token past expiration |
| `rotated` | New token issued (rotation) |
| `logout_all` | User logged out all devices |
| `security` | Admin-initiated revocation |
| `password_change` | Password was changed |

---

## API Endpoints

### Token Management

```
POST /api/v1/auth/login           - Get token pair
POST /api/v1/auth/refresh         - Refresh tokens
POST /api/v1/auth/logout          - Revoke current token
POST /api/v1/auth/logout-all      - Revoke all tokens
```

---

## Cleanup Function

Removes expired and old revoked tokens:

```sql
CREATE OR REPLACE FUNCTION cleanup_expired_refresh_tokens()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM refresh_tokens
    WHERE expires_at < NOW() - INTERVAL '1 day'
       OR (is_revoked = TRUE AND revoked_at < NOW() - INTERVAL '7 days');

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
```

Called by Celery maintenance task.

---

## Rate Limiting

Also implemented in Sprint 5 (not a DB table, uses Redis):

```python
# Redis-based sliding window rate limiter
# Default: 100 requests per 60 seconds per IP/user

# Configuration
rate_limit_enabled: bool = True
rate_limit_requests: int = 100
rate_limit_window_seconds: int = 60
```

### Rate Limit Headers

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 45
Retry-After: 45  (only on 429)
```

---

## Celery Tasks

### Maintenance Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| `cleanup_old_jobs` | Hourly | Remove jobs > 30 days |
| `check_stuck_jobs` | 5 min | Mark stuck jobs failed |
| `health_check` | 1 min | System health check |
| `calculate_storage_stats` | 6 hours | Storage usage stats |

### Processing Tasks

| Task | Queue | Description |
|------|-------|-------------|
| `extract_metadata` | metadata | FFprobe analysis |
| `generate_proxy` | media | H.264 720p proxy |
| `generate_thumbnail` | media | JPEG thumbnail |
| `process_ingest` | ingest | Orchestrate pipeline |

---

## Example: Token Refresh

### Request

```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "abc123..."}'
```

### Response

```json
{
  "access_token": "eyJ...",
  "refresh_token": "xyz789...",
  "token_type": "bearer",
  "expires_in": 1800,
  "refresh_expires_in": 604800
}
```

---

## Security Best Practices

1. **Never log tokens** - Neither access nor refresh
2. **HTTPS only** - Tokens in transit must be encrypted
3. **Short access tokens** - 30 min default
4. **Token rotation** - New refresh token on each use
5. **Revocation on password change** - Invalidate all tokens
6. **Rate limiting** - Prevent brute force attacks
