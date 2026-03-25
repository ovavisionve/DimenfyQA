-- ============================================================
-- IG DM Engine — SQL completo para Supabase
-- Ejecutar en: Supabase Dashboard → SQL Editor → New query
-- ============================================================

-- Habilitar extensión UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- MIGRACIÓN 001: Tablas base
-- ============================================================

-- 1. CLIENTS
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    business_type VARCHAR(100),
    ig_accounts JSONB DEFAULT '[]',
    settings JSONB DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. CAMPAIGNS
CREATE TABLE campaigns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(id),
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    source_value TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    settings JSONB DEFAULT '{}',
    stats JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. LEADS
CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id),
    client_id UUID NOT NULL REFERENCES clients(id),
    ig_username VARCHAR(255) NOT NULL,
    ig_full_name VARCHAR(500),
    ig_bio TEXT,
    ig_bio_clean TEXT,
    ig_website VARCHAR(500),
    ig_category VARCHAR(255),
    ig_follower_count INTEGER,
    ig_following_count INTEGER,
    ig_is_private BOOLEAN,
    ig_profile_pic_url TEXT,
    score INTEGER,
    score_reason TEXT,
    lead_category VARCHAR(100),
    research_data TEXT,
    research_summary TEXT,
    dm_message TEXT,
    dm_variant_b TEXT,
    status VARCHAR(50) DEFAULT 'scraped',
    is_duplicate BOOLEAN NOT NULL DEFAULT FALSE,
    scraped_at TIMESTAMPTZ,
    scored_at TIMESTAMPTZ,
    researched_at TIMESTAMPTZ,
    dm_generated_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_leads_client_username UNIQUE (client_id, ig_username)
);

CREATE INDEX idx_leads_campaign ON leads(campaign_id);
CREATE INDEX idx_leads_client ON leads(client_id);
CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_score ON leads(score);
CREATE INDEX idx_leads_username ON leads(ig_username);

-- 4. MESSAGES
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID NOT NULL REFERENCES leads(id),
    campaign_id UUID NOT NULL REFERENCES campaigns(id),
    client_id UUID NOT NULL REFERENCES clients(id),
    content TEXT NOT NULL,
    variant VARCHAR(10) DEFAULT 'A',
    status VARCHAR(50) DEFAULT 'generated',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. SCRAPE_JOBS
CREATE TABLE scrape_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id),
    apify_run_id VARCHAR(255),
    apify_dataset_id VARCHAR(255),
    actor_type VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending',
    items_found INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- MIGRACIÓN 003: Phase 2 — Sending fields
-- ============================================================

ALTER TABLE leads ADD COLUMN send_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE leads ADD COLUMN send_error TEXT;
ALTER TABLE leads ADD COLUMN delivery_status VARCHAR(50);
ALTER TABLE leads ADD COLUMN dm_variant_used VARCHAR(10);

CREATE INDEX idx_leads_delivery_status ON leads(delivery_status);
CREATE INDEX idx_leads_send_attempts ON leads(send_attempts);

-- ============================================================
-- MIGRACIÓN 004: Inbox tracking
-- ============================================================

ALTER TABLE leads ADD COLUMN replied_at TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN reply_text TEXT;
ALTER TABLE leads ADD COLUMN reply_classification VARCHAR(50);
ALTER TABLE leads ADD COLUMN conversation_status VARCHAR(50) NOT NULL DEFAULT 'pending';

CREATE INDEX idx_leads_conversation_status ON leads(conversation_status);

-- ============================================================
-- MIGRACIÓN 005: Follow-up system
-- ============================================================

CREATE TABLE follow_up_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id),
    client_id UUID NOT NULL REFERENCES clients(id),
    step_number INTEGER NOT NULL,
    delay_days INTEGER NOT NULL,
    template_prompt TEXT,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_followup_campaign_step UNIQUE (campaign_id, step_number)
);

CREATE INDEX idx_followup_campaign ON follow_up_rules(campaign_id);
CREATE INDEX idx_followup_client ON follow_up_rules(client_id);

ALTER TABLE leads ADD COLUMN follow_up_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE leads ADD COLUMN last_follow_up_at TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN next_follow_up_at TIMESTAMPTZ;

CREATE INDEX idx_leads_next_follow_up_at ON leads(next_follow_up_at);

-- ============================================================
-- MIGRACIÓN 006: Webhooks
-- ============================================================

CREATE TABLE webhooks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(id),
    url VARCHAR(500) NOT NULL,
    secret VARCHAR(255),
    events TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_triggered_at TIMESTAMPTZ,
    last_status_code INTEGER,
    failure_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_webhook_client ON webhooks(client_id);
CREATE INDEX idx_webhook_active ON webhooks(is_active);

-- ============================================================
-- MIGRACIÓN 007: Lead posts & analysis
-- ============================================================

ALTER TABLE leads ADD COLUMN ig_posts JSONB;
ALTER TABLE leads ADD COLUMN ig_post_analysis JSONB;

-- ============================================================
-- MIGRACIÓN 008: Users, Audit Logs, Notifications
-- ============================================================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    permissions JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    user_email VARCHAR(255),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(100),
    details JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_created ON audit_logs(created_at);

CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    level VARCHAR(20) NOT NULL DEFAULT 'info',
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    link VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- MIGRACIÓN 009: Comment fields
-- ============================================================

ALTER TABLE leads ADD COLUMN comment_message TEXT;
ALTER TABLE leads ADD COLUMN comment_variant_b TEXT;
ALTER TABLE leads ADD COLUMN comment_status VARCHAR(50);
ALTER TABLE leads ADD COLUMN comment_variant_used VARCHAR(10);
ALTER TABLE leads ADD COLUMN commented_post_shortcode VARCHAR(100);
ALTER TABLE leads ADD COLUMN comment_sent_at TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN comment_error TEXT;
ALTER TABLE leads ADD COLUMN comment_attempts INTEGER NOT NULL DEFAULT 0;

CREATE INDEX idx_leads_comment_status ON leads(comment_status);

-- ============================================================
-- MIGRACIÓN 010: Campaign task tracking
-- ============================================================

ALTER TABLE campaigns ADD COLUMN celery_task_id VARCHAR(255);
ALTER TABLE campaigns ADD COLUMN last_phase VARCHAR(50);

CREATE UNIQUE INDEX ix_campaigns_celery_task_id ON campaigns(celery_task_id);

-- ============================================================
-- MIGRACIÓN 011: Unibox tables
-- ============================================================

CREATE TABLE conversation_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID NOT NULL REFERENCES leads(id),
    campaign_id UUID NOT NULL REFERENCES campaigns(id),
    client_id UUID NOT NULL REFERENCES clients(id),
    direction VARCHAR(20) NOT NULL,
    message_type VARCHAR(30) NOT NULL,
    content TEXT NOT NULL,
    ig_account_used VARCHAR(255),
    variant_used VARCHAR(10),
    sent_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_convmsg_lead ON conversation_messages(lead_id);
CREATE INDEX idx_convmsg_campaign ON conversation_messages(campaign_id);
CREATE INDEX idx_convmsg_sent_at ON conversation_messages(sent_at);

CREATE TABLE reply_suggestions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID NOT NULL REFERENCES leads(id),
    suggestions JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    was_used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_replysugg_lead ON reply_suggestions(lead_id);

-- ============================================================
-- MIGRACIÓN 012: CRM tables
-- ============================================================

ALTER TABLE leads ADD COLUMN crm_stage VARCHAR(50) NOT NULL DEFAULT 'new';

CREATE INDEX idx_leads_crm_stage ON leads(crm_stage);

CREATE TABLE lead_notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID NOT NULL REFERENCES leads(id),
    user_id UUID REFERENCES users(id),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_leadnotes_lead ON lead_notes(lead_id);

CREATE TABLE score_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID NOT NULL REFERENCES leads(id),
    old_score INTEGER NOT NULL,
    new_score INTEGER NOT NULL,
    delta INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_scorehist_lead ON score_history(lead_id);
CREATE INDEX idx_scorehist_created ON score_history(created_at);

-- ============================================================
-- Alembic version tracking (para compatibilidad)
-- ============================================================

CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

INSERT INTO alembic_version (version_num) VALUES ('012');

-- ============================================================
-- ¡LISTO! 13 tablas creadas + todos los índices
-- ============================================================
-- Tablas: clients, campaigns, leads, messages, scrape_jobs,
--         follow_up_rules, webhooks, users, audit_logs,
--         notifications, conversation_messages, reply_suggestions,
--         lead_notes, score_history, alembic_version
-- ============================================================
