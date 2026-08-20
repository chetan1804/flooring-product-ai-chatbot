CREATE TABLE IF NOT EXISTS analytics_events (
    event_id UUID PRIMARY KEY,
    site_code TEXT NOT NULL,
    session_id UUID NOT NULL REFERENCES chatbot_sessions(session_id) ON DELETE CASCADE,
    interaction_id UUID,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'session_created',
        'widget_opened',
        'chat_completed',
        'chat_failed',
        'product_clicked'
    )),
    action TEXT,
    recommendation_count INTEGER CHECK (recommendation_count >= 0),
    sku TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_analytics_events_site_time
    ON analytics_events (site_code, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_events_session
    ON analytics_events (session_id, occurred_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_analytics_events_interaction
    ON analytics_events (interaction_id)
    WHERE interaction_id IS NOT NULL AND event_type = 'chat_completed';

CREATE TABLE IF NOT EXISTS recommendation_feedback (
    feedback_id UUID PRIMARY KEY,
    site_code TEXT NOT NULL,
    session_id UUID NOT NULL REFERENCES chatbot_sessions(session_id) ON DELETE CASCADE,
    interaction_id UUID NOT NULL,
    rating TEXT NOT NULL CHECK (rating IN ('helpful', 'not_helpful')),
    reason TEXT CHECK (reason IS NULL OR reason IN (
        'irrelevant',
        'too_expensive',
        'unavailable',
        'other'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (interaction_id)
);

CREATE INDEX IF NOT EXISTS idx_recommendation_feedback_site_time
    ON recommendation_feedback (site_code, created_at DESC);
