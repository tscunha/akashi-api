-- Migration: 003_add_refresh_tokens
-- AKASHI MAM API - Add refresh tokens table for JWT token rotation
-- Date: 2026-02-06

-- =============================================================================
-- Refresh Tokens Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL UNIQUE,

    -- Token metadata
    device_info TEXT,
    ip_address VARCHAR(45),  -- IPv6 compatible
    user_agent TEXT,

    -- Token status
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    revoked_reason VARCHAR(255),

    -- Expiration
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    last_used_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for refresh tokens
CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);
CREATE INDEX idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);
CREATE INDEX idx_refresh_tokens_is_revoked ON refresh_tokens(is_revoked) WHERE is_revoked = FALSE;

-- =============================================================================
-- Comments
-- =============================================================================

COMMENT ON TABLE refresh_tokens IS 'Refresh tokens for JWT token rotation';
COMMENT ON COLUMN refresh_tokens.token_hash IS 'SHA-256 hash of the refresh token (never store plaintext)';
COMMENT ON COLUMN refresh_tokens.device_info IS 'Optional device identifier for multi-device management';
COMMENT ON COLUMN refresh_tokens.ip_address IS 'IP address that created/used the token';
COMMENT ON COLUMN refresh_tokens.user_agent IS 'Browser/client user agent string';
COMMENT ON COLUMN refresh_tokens.is_revoked IS 'Whether the token has been revoked';
COMMENT ON COLUMN refresh_tokens.revoked_reason IS 'Reason for revocation (logout, security, admin, etc)';
COMMENT ON COLUMN refresh_tokens.expires_at IS 'When the token expires';
COMMENT ON COLUMN refresh_tokens.last_used_at IS 'Last time the token was used to refresh';

-- =============================================================================
-- Function to clean up expired tokens
-- =============================================================================

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

COMMENT ON FUNCTION cleanup_expired_refresh_tokens() IS 'Removes expired and old revoked refresh tokens';
