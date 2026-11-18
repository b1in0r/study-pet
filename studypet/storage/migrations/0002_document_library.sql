CREATE TABLE documents (
    id TEXT NOT NULL PRIMARY KEY,
    title TEXT NOT NULL,
    original_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    storage_relpath TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK(size_bytes > 0),
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
    state TEXT NOT NULL CHECK(state IN ('importing','ready','needs_text','failed','deleted')),
    message TEXT NOT NULL DEFAULT '',
    char_count INTEGER NOT NULL DEFAULT 0 CHECK(char_count >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX documents_active_hash ON documents(content_sha256) WHERE state <> 'deleted';
CREATE TABLE sources (
    id TEXT NOT NULL PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('message','manual_memory','task','task_event','document','external_web')),
    record_id TEXT NOT NULL,
    source_version TEXT NOT NULL,
    locator_json TEXT NOT NULL DEFAULT '{}',
    state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active','excluded','deleted')),
    processing_scope TEXT NOT NULL DEFAULT 'local_only' CHECK(processing_scope IN ('local_only','cloud_allowed')),
    captured_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE(kind,record_id,source_version)
);
CREATE TABLE document_chunks (
    id TEXT NOT NULL PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    document_revision INTEGER NOT NULL CHECK(document_revision > 0),
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    source_id TEXT NOT NULL REFERENCES sources(id),
    text_content TEXT NOT NULL,
    locator_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    UNIQUE(document_id,document_revision,ordinal)
);
CREATE INDEX document_chunks_source ON document_chunks(source_id);
