-- ============================================================================
-- IG DM Engine — Complete PostgreSQL/Supabase Schema
-- Generated from Alembic migrations 001-013 + SQLAlchemy models
-- ============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 1. CLIENTS
-- ============================================================================
CREATE TABLE clients (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(255) NOT NULL,
    business_type VARCHAR(100),
    ig_accounts JSONB DEFAULT '[]'::jsonb,
    settings    JSONB DEFAULT '{}'::jsonb,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- 2. CAMPAIGNS
-- ============================================================================
CREATE TABLE campaigns (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id       UUID NOT NULL REFERENCES clients(id),
    name            VARCHAR(255) NOT NULL,
    source_type     VARCHAR(50) NOT NULL,
    source_value    TEXT NOT NULL,
    status          VARCHAR(50) DEFAULT 'pending',
    settings        JSONB DEFAULT '{}'::jsonb,
    stats           JSONB DEFAULT '{}'::jsonb,
    celery_task_id  VARCHAR(255),
    last_phase      VARCHAR(50),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ix_campaigns_celery_task_id ON campaigns (celery_task_id);

-- ============================================================================
-- 3. USERS
-- ============================================================================
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    role            VARCHAR(50) NOT NULL DEFAULT 'viewer',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    permissions     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_email ON users (email);

-- ============================================================================
-- 4. LEADS
-- ============================================================================
CREATE TABLE leads (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    campaign_id             UUID NOT NULL REFERENCES campaigns(id),
    client_id               UUID NOT NULL REFERENCES clients(id),

    -- Instagram data
    ig_username             VARCHAR(255) NOT NULL,
    ig_full_name            VARCHAR(500),
    ig_bio                  TEXT,
    ig_bio_clean            TEXT,
    ig_website              VARCHAR(500),
    ig_category             VARCHAR(255),
    ig_follower_count       INTEGER,
    ig_following_count      INTEGER,
    ig_is_private           BOOLEAN,
    ig_profile_pic_url      TEXT,
    ig_posts                JSONB,
    ig_post_analysis        JSONB,

    -- Scoring
    score                   INTEGER,
    score_reason            TEXT,
    lead_category           VARCHAR(100),

    -- Research
    research_data           TEXT,
    research_summary        TEXT,

    -- Generated DM
    dm_message              TEXT,
    dm_variant_b            TEXT,

    -- Status
    status                  VARCHAR(50) DEFAULT 'scraped',
    is_duplicate            BOOLEAN NOT NULL DEFAULT FALSE,

    -- Phase 2 — DM Sending
    send_attempts           INTEGER NOT NULL DEFAULT 0,
    send_error              TEXT,
    delivery_status         VARCHAR(50),
    dm_variant_used         VARCHAR(10),

    -- Phase 3 — Inbox Monitoring & Reply Tracking
    replied_at              TIMESTAMPTZ,
    reply_text              TEXT,
    reply_classification    VARCHAR(50),
    conversation_status     VARCHAR(50) NOT NULL DEFAULT 'pending',

    -- Phase 3 — Follow-up Automation
    follow_up_count         INTEGER NOT NULL DEFAULT 0,
    last_follow_up_at       TIMESTAMPTZ,
    next_follow_up_at       TIMESTAMPTZ,

    -- Phase 6 — CRM Stage
    crm_stage               VARCHAR(50) NOT NULL DEFAULT 'new',

    -- Phase 5 — Post Commenting
    comment_message         TEXT,
    comment_variant_b       TEXT,
    comment_status          VARCHAR(50),
    comment_variant_used    VARCHAR(10),
    commented_post_shortcode VARCHAR(100),
    comment_sent_at         TIMESTAMPTZ,
    comment_error           TEXT,
    comment_attempts        INTEGER NOT NULL DEFAULT 0,

    -- Timestamps
    scraped_at              TIMESTAMPTZ,
    scored_at               TIMESTAMPTZ,
    researched_at           TIMESTAMPTZ,
    dm_generated_at         TIMESTAMPTZ,
    sent_at                 TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Constraints
    CONSTRAINT uq_leads_client_username UNIQUE (client_id, ig_username)
);

-- Indexes on leads
CREATE INDEX idx_leads_campaign ON leads (campaign_id);
CREATE INDEX idx_leads_client ON leads (client_id);
CREATE INDEX idx_leads_status ON leads (status);
CREATE INDEX idx_leads_score ON leads (score);
CREATE INDEX idx_leads_username ON leads (ig_username);
CREATE INDEX idx_leads_delivery_status ON leads (delivery_status);
CREATE INDEX idx_leads_send_attempts ON leads (send_attempts);
CREATE INDEX idx_leads_conversation_status ON leads (conversation_status);
CREATE INDEX idx_leads_next_follow_up_at ON leads (next_follow_up_at);
CREATE INDEX idx_leads_crm_stage ON leads (crm_stage);
CREATE INDEX idx_leads_comment_status ON leads (comment_status);

-- ============================================================================
-- 5. MESSAGES
-- ============================================================================
CREATE TABLE messages (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id     UUID NOT NULL REFERENCES leads(id),
    campaign_id UUID NOT NULL REFERENCES campaigns(id),
    client_id   UUID NOT NULL REFERENCES clients(id),
    content     TEXT NOT NULL,
    variant     VARCHAR(10) DEFAULT 'A',
    status      VARCHAR(50) DEFAULT 'generated',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- 6. SCRAPE_JOBS
-- ============================================================================
CREATE TABLE scrape_jobs (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    campaign_id       UUID NOT NULL REFERENCES campaigns(id),
    apify_run_id      VARCHAR(255),
    apify_dataset_id  VARCHAR(255),
    actor_type        VARCHAR(100),
    status            VARCHAR(50) DEFAULT 'pending',
    items_found       INTEGER DEFAULT 0,
    error_message     TEXT,
    started_at        TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- 7. FOLLOW_UP_RULES
-- ============================================================================
CREATE TABLE follow_up_rules (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    campaign_id     UUID NOT NULL REFERENCES campaigns(id),
    client_id       UUID NOT NULL REFERENCES clients(id),
    step_number     INTEGER NOT NULL,
    delay_days      INTEGER NOT NULL,
    template_prompt TEXT,
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_followup_campaign_step UNIQUE (campaign_id, step_number)
);

CREATE INDEX idx_followup_campaign ON follow_up_rules (campaign_id);
CREATE INDEX idx_followup_client ON follow_up_rules (client_id);

-- ============================================================================
-- 8. WEBHOOKS
-- ============================================================================
CREATE TABLE webhooks (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id           UUID NOT NULL REFERENCES clients(id),
    url                 VARCHAR(500) NOT NULL,
    secret              VARCHAR(255),
    events              TEXT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    last_triggered_at   TIMESTAMPTZ,
    last_status_code    INTEGER,
    failure_count       INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_webhook_client ON webhooks (client_id);
CREATE INDEX idx_webhook_active ON webhooks (is_active);

-- ============================================================================
-- 9. AUDIT_LOGS
-- ============================================================================
CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID,
    user_email      VARCHAR(255),
    action          VARCHAR(100) NOT NULL,
    resource_type   VARCHAR(50),
    resource_id     VARCHAR(100),
    details         JSONB,
    ip_address      VARCHAR(45),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_logs_action ON audit_logs (action);
CREATE INDEX idx_audit_logs_created_at ON audit_logs (created_at);

-- ============================================================================
-- 10. NOTIFICATIONS
-- ============================================================================
CREATE TABLE notifications (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID,
    title       VARCHAR(255) NOT NULL,
    message     TEXT NOT NULL,
    level       VARCHAR(20) NOT NULL DEFAULT 'info',
    is_read     BOOLEAN NOT NULL DEFAULT FALSE,
    link        VARCHAR(500),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- 11. CONVERSATION_MESSAGES (Unibox)
-- ============================================================================
CREATE TABLE conversation_messages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id),
    campaign_id     UUID NOT NULL REFERENCES campaigns(id),
    client_id       UUID NOT NULL REFERENCES clients(id),
    direction       VARCHAR(20) NOT NULL,
    message_type    VARCHAR(30) NOT NULL,
    content         TEXT NOT NULL,
    ig_account_used VARCHAR(255),
    variant_used    VARCHAR(10),
    sent_at         TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_convmsg_lead ON conversation_messages (lead_id);
CREATE INDEX idx_convmsg_campaign ON conversation_messages (campaign_id);
CREATE INDEX idx_convmsg_sent_at ON conversation_messages (sent_at);

-- ============================================================================
-- 12. REPLY_SUGGESTIONS (Unibox AI)
-- ============================================================================
CREATE TABLE reply_suggestions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id),
    suggestions     JSONB NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL,
    was_used        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_replysugg_lead ON reply_suggestions (lead_id);

-- ============================================================================
-- 13. LEAD_NOTES (CRM)
-- ============================================================================
CREATE TABLE lead_notes (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id     UUID NOT NULL REFERENCES leads(id),
    user_id     UUID REFERENCES users(id),
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_leadnotes_lead ON lead_notes (lead_id);

-- ============================================================================
-- 14. SCORE_HISTORY (CRM Dynamic Scoring)
-- ============================================================================
CREATE TABLE score_history (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id     UUID NOT NULL REFERENCES leads(id),
    old_score   INTEGER NOT NULL,
    new_score   INTEGER NOT NULL,
    delta       INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_scorehist_lead ON score_history (lead_id);
CREATE INDEX idx_scorehist_created ON score_history (created_at);

-- ============================================================================
-- 15. SYSTEM_CONFIG (Key-Value Settings)
-- ============================================================================
CREATE TABLE system_config (
    key         VARCHAR(255) PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- ============================================================================
-- OPTIONAL: Alembic version tracking table
-- (Supabase does not need this, but included for completeness if you
--  want to track which migration version the schema corresponds to)
-- ============================================================================
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

INSERT INTO alembic_version (version_num) VALUES ('013')
ON CONFLICT (version_num) DO NOTHING;
