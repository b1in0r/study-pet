-- DESIGN ONLY: additive schema for a temporary database initialized by v1 TaskStore.
-- Not imported by the application. Does not change PRAGMA user_version.
-- Enable foreign keys on every connection before starting a transaction.
PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE conversations (
    id TEXT NOT NULL PRIMARY KEY,
    title TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT 'general',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE TABLE messages (
    id TEXT NOT NULL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    seq INTEGER NOT NULL CHECK (seq > 0),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('streaming', 'complete', 'failed', 'cancelled', 'deleted')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    run_id TEXT REFERENCES agent_runs(id),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (conversation_id, seq)
);

CREATE TABLE documents (
    id TEXT NOT NULL PRIMARY KEY,
    title TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    storage_relpath TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    state TEXT NOT NULL CHECK (state IN ('importing', 'ready', 'failed', 'deleted')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE sources (
    id TEXT NOT NULL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('message', 'manual_memory', 'task', 'task_event', 'document', 'external_web')),
    record_id TEXT NOT NULL,
    source_version TEXT NOT NULL,
    locator_json TEXT NOT NULL DEFAULT '{}',
    state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'excluded', 'deleted')),
    processing_scope TEXT NOT NULL DEFAULT 'local_only' CHECK (processing_scope IN ('local_only', 'cloud_allowed')),
    captured_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE (kind, record_id, source_version)
);

CREATE TABLE memory_claims (
    id TEXT NOT NULL PRIMARY KEY,
    scope TEXT NOT NULL CHECK (scope IN ('profile', 'learning', 'career', 'income', 'general')),
    claim_key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('candidate', 'active', 'superseded', 'rejected', 'expired', 'deleted')),
    evidence_kind TEXT NOT NULL CHECK (evidence_kind IN ('user_statement', 'user_confirmation', 'document', 'inference')),
    source_id TEXT NOT NULL REFERENCES sources(id),
    supersedes_id TEXT REFERENCES memory_claims(id),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    valid_from TEXT NOT NULL,
    valid_until TEXT,
    confirmed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (status <> 'active' OR confirmed_at IS NOT NULL),
    CHECK (valid_until IS NULL OR valid_until > valid_from)
);
CREATE UNIQUE INDEX memory_claims_one_active_key
    ON memory_claims(scope, claim_key) WHERE status = 'active';
CREATE INDEX memory_claims_context ON memory_claims(scope, status, valid_until);

CREATE TABLE document_chunks (
    id TEXT NOT NULL PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    document_revision INTEGER NOT NULL CHECK (document_revision > 0),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    source_id TEXT NOT NULL REFERENCES sources(id),
    text_content TEXT NOT NULL,
    locator_json TEXT NOT NULL DEFAULT '{}',
    content_sha256 TEXT NOT NULL,
    UNIQUE (document_id, document_revision, ordinal)
);

CREATE TABLE agent_runs (
    id TEXT NOT NULL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    input_message_id TEXT NOT NULL REFERENCES messages(id),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    context_policy_version TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('running', 'waiting_confirmation', 'succeeded', 'failed', 'cancelled', 'interrupted')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_code TEXT
);
CREATE INDEX agent_runs_conversation ON agent_runs(conversation_id, started_at);
CREATE UNIQUE INDEX agent_runs_one_running
    ON agent_runs(conversation_id) WHERE state = 'running';

CREATE TABLE context_items (
    run_id TEXT NOT NULL REFERENCES agent_runs(id),
    call_no INTEGER NOT NULL CHECK (call_no > 0),
    position INTEGER NOT NULL CHECK (position >= 0),
    item_kind TEXT NOT NULL,
    record_id TEXT NOT NULL,
    record_version TEXT NOT NULL,
    source_id TEXT REFERENCES sources(id),
    selection_reason TEXT NOT NULL,
    token_count INTEGER NOT NULL CHECK (token_count >= 0),
    token_count_kind TEXT NOT NULL CHECK (token_count_kind IN ('estimated', 'tokenizer')),
    PRIMARY KEY (run_id, call_no, position)
);

CREATE TABLE conversation_summaries (
    id TEXT NOT NULL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    from_seq INTEGER NOT NULL CHECK (from_seq > 0),
    through_seq INTEGER NOT NULL CHECK (through_seq >= from_seq),
    summary_json TEXT NOT NULL,
    source_versions_json TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('active', 'stale', 'deleted')),
    created_at TEXT NOT NULL
);
CREATE INDEX conversation_summaries_coverage ON conversation_summaries(conversation_id, state, through_seq);

CREATE TABLE plan_proposals (
    id TEXT NOT NULL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(id),
    actions_json TEXT NOT NULL,
    base_versions_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('draft', 'accepted', 'applied', 'rejected', 'stale', 'expired')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    confirmed_at TEXT,
    applied_at TEXT,
    applied_result_json TEXT,
    CHECK (state NOT IN ('accepted', 'applied') OR confirmed_at IS NOT NULL),
    CHECK (state <> 'applied' OR (applied_at IS NOT NULL AND applied_result_json IS NOT NULL)),
    CHECK (expires_at > created_at)
);

CREATE TABLE tool_calls (
    id TEXT NOT NULL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(id),
    call_no INTEGER NOT NULL CHECK (call_no > 0),
    provider_call_id TEXT,
    tool_name TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    result_json TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    proposal_id TEXT REFERENCES plan_proposals(id),
    state TEXT NOT NULL CHECK (state IN ('proposed', 'approved', 'running', 'succeeded', 'failed', 'rejected', 'cancelled', 'unknown')),
    started_at TEXT,
    finished_at TEXT,
    error_code TEXT
);
CREATE INDEX tool_calls_run ON tool_calls(run_id, call_no);

CREATE TABLE usage_records (
    id TEXT NOT NULL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(id),
    call_no INTEGER NOT NULL CHECK (call_no > 0),
    input_tokens INTEGER CHECK (input_tokens >= 0),
    cached_input_tokens INTEGER CHECK (cached_input_tokens >= 0),
    output_tokens INTEGER CHECK (output_tokens >= 0),
    cost_amount TEXT,
    currency TEXT,
    measurement TEXT NOT NULL CHECK (measurement IN ('provider', 'estimated', 'unavailable')),
    created_at TEXT NOT NULL,
    UNIQUE (run_id, call_no),
    CHECK (cached_input_tokens IS NULL OR input_tokens IS NULL OR cached_input_tokens <= input_tokens)
);

COMMIT;
