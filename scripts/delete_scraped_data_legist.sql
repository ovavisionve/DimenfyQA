-- Delete all scraped customer data (leads + related tables + scrape_jobs)
-- for the two Legist clients. Preserves the clients themselves and their
-- campaigns/config (follow_up_rules, settings, etc.).
--
-- Targets:
--   26fb1eb8-78f7-4432-b881-d7035fa7d199  (Legist)
--   01369b8b-9c18-432f-a854-b61914725032  (LegistAI)
--
-- Run inside a transaction so we can roll back if anything looks off.

BEGIN;

WITH target_clients (id) AS (
    VALUES
        ('26fb1eb8-78f7-4432-b881-d7035fa7d199'::uuid),
        ('01369b8b-9c18-432f-a854-b61914725032'::uuid)
),
target_leads AS (
    SELECT l.id
    FROM public.leads l
    JOIN target_clients tc ON tc.id = l.client_id
),
target_campaigns AS (
    SELECT c.id
    FROM public.campaigns c
    JOIN target_clients tc ON tc.id = c.client_id
)

-- 1. Lead-scoped tables (FK -> leads.id)
DELETE FROM public.lead_notes        WHERE lead_id IN (SELECT id FROM target_leads);
DELETE FROM public.score_history     WHERE lead_id IN (SELECT id FROM target_leads);
DELETE FROM public.reply_suggestions WHERE lead_id IN (SELECT id FROM target_leads);

-- 2. Client-scoped conversation/message tables
DELETE FROM public.conversation_messages WHERE client_id IN (SELECT id FROM target_clients);
DELETE FROM public.messages              WHERE client_id IN (SELECT id FROM target_clients);

-- 3. Scrape jobs tied to those campaigns
DELETE FROM public.scrape_jobs WHERE campaign_id IN (SELECT id FROM target_campaigns);

-- 4. Finally the leads themselves
DELETE FROM public.leads WHERE client_id IN (SELECT id FROM target_clients);

-- Sanity check before committing.
SELECT
    (SELECT COUNT(*) FROM public.leads                 WHERE client_id IN (SELECT id FROM target_clients)) AS leads_left,
    (SELECT COUNT(*) FROM public.messages              WHERE client_id IN (SELECT id FROM target_clients)) AS messages_left,
    (SELECT COUNT(*) FROM public.conversation_messages WHERE client_id IN (SELECT id FROM target_clients)) AS convo_msgs_left,
    (SELECT COUNT(*) FROM public.scrape_jobs           WHERE campaign_id IN (SELECT id FROM target_campaigns)) AS scrape_jobs_left,
    (SELECT COUNT(*) FROM public.campaigns             WHERE client_id IN (SELECT id FROM target_clients)) AS campaigns_kept,
    (SELECT COUNT(*) FROM public.clients               WHERE id IN (SELECT id FROM target_clients))           AS clients_kept;

COMMIT;
-- If the sanity check shows non-zero "left" counts, run ROLLBACK; instead.
