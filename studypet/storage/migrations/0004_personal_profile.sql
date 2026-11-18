CREATE TABLE profile_entries (
    id TEXT NOT NULL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('stage', 'experience', 'skill', 'goal', 'constraint')),
    title TEXT NOT NULL,
    details TEXT NOT NULL,
    document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
