-- ============================================================================
-- Migration 001: Add Users Table
-- Run this on existing databases to add authentication support
-- ============================================================================

-- Check if table already exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users') THEN

        -- Create users table
        CREATE TABLE users (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id               UUID NOT NULL REFERENCES tenants(id),

            email                   VARCHAR(255) NOT NULL,
            password_hash           VARCHAR(255) NOT NULL,
            full_name               VARCHAR(255),

            role                    VARCHAR(50) DEFAULT 'user'
                                    CHECK (role IN ('admin', 'manager', 'editor', 'viewer', 'user')),

            is_active               BOOLEAN DEFAULT true,
            is_superuser            BOOLEAN DEFAULT false,

            last_login_at           TIMESTAMP WITH TIME ZONE,
            password_changed_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

            created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

            UNIQUE (tenant_id, email)
        );

        -- Indexes
        CREATE INDEX idx_users_email ON users(email);
        CREATE INDEX idx_users_tenant ON users(tenant_id);
        CREATE INDEX idx_users_active ON users(tenant_id, is_active) WHERE is_active = true;

        -- Updated_at trigger
        CREATE TRIGGER trg_users_updated_at
            BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION update_updated_at();

        RAISE NOTICE 'Users table created successfully!';
    ELSE
        RAISE NOTICE 'Users table already exists, skipping...';
    END IF;
END $$;

-- ============================================================================
-- Verification
-- ============================================================================

SELECT
    table_name,
    (SELECT COUNT(*) FROM users) as user_count
FROM information_schema.tables
WHERE table_name = 'users' AND table_schema = 'public';
