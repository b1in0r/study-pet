ALTER TABLE documents ADD COLUMN category TEXT NOT NULL DEFAULT 'uncategorized'
    CHECK (category IN ('uncategorized', 'campus_recruitment', 'graduate_research', 'undergraduate', 'work'));
