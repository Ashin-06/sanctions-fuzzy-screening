-- Every screening, kept as evidence that the party was screened and against which list.
-- result holds the full screening response as returned to the caller.
CREATE TABLE screenings (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    query_id TEXT NOT NULL,
    name TEXT NOT NULL,
    decision TEXT NOT NULL,
    hit_source TEXT NOT NULL,
    sdn_id TEXT,
    list_version TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT NOT NULL
);
CREATE INDEX screenings_queue ON screenings (status, decision, created_at);
CREATE INDEX screenings_query ON screenings (query_id);

-- Analyst decisions on BLOCK and REVIEW results, oldest first; screenings.status is the latest.
CREATE TABLE screening_reviews (
    screening_id TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    status TEXT NOT NULL,
    note TEXT NOT NULL
);
CREATE INDEX screening_reviews_screening ON screening_reviews (screening_id);
