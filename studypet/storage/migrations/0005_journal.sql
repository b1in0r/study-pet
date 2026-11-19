CREATE TABLE journal_entries (
    id TEXT NOT NULL PRIMARY KEY,
    day TEXT NOT NULL,
    body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 4000),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX journal_by_day ON journal_entries(day DESC, created_at DESC);
