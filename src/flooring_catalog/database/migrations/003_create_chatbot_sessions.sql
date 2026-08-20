CREATE TABLE IF NOT EXISTS chatbot_sessions (
    session_id UUID PRIMARY KEY,
    site_code TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_accessed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chatbot_sessions_expires_at
    ON chatbot_sessions (expires_at);

CREATE INDEX IF NOT EXISTS idx_chatbot_sessions_site_code
    ON chatbot_sessions (site_code);
