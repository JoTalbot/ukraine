-- Entity linkage schema: cross-dataset identity graph for Ukrainian open data.
-- Entities are public identifiers (ЄДРПОУ, ІПН) or normalized names.
-- Edges connect entities co-referenced by one source record.
--
-- Privacy: identifiers and names are taken only from lawfully published
-- registers; source anonymization is never reversed (no_deanonymization).

CREATE TABLE IF NOT EXISTS entities (
    entity_id INTEGER PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('edrpou', 'ipn', 'name')),
    value TEXT NOT NULL,          -- normalized identifier or UPPERCASE name
    title TEXT,                   -- human-readable name from the spine register
    UNIQUE(type, value)
);

CREATE TABLE IF NOT EXISTS mentions (
    mention_id INTEGER PRIMARY KEY,
    entity_id INTEGER NOT NULL REFERENCES entities(entity_id),
    dataset TEXT NOT NULL,        -- e.g. edr, vat_payers, edrsr, notaries
    record_ref TEXT,              -- source row key (EDRPOU, case number, reg num)
    name TEXT,                    -- name as written in that source
    extra TEXT                    -- JSON: dates, status, share etc.
);
CREATE INDEX IF NOT EXISTS idx_mentions_entity ON mentions(entity_id, dataset);

CREATE TABLE IF NOT EXISTS edges (
    a INTEGER NOT NULL REFERENCES entities(entity_id),   -- min(entity_id)
    b INTEGER NOT NULL REFERENCES entities(entity_id),   -- max(entity_id)
    kind TEXT NOT NULL,          -- founder | signer | co_litigant | works_at | linked
    dataset TEXT NOT NULL,       -- provenance of the edge
    weight INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (a, b, kind, dataset)
);
CREATE INDEX IF NOT EXISTS idx_edges_a ON edges(a);
CREATE INDEX IF NOT EXISTS idx_edges_b ON edges(b);

-- Example queries:
--  Entity card by ЄДРПОУ:
--    SELECT * FROM entities WHERE type='edrpou' AND value='14359609';
--  All bases mentioning one entity:
--    SELECT dataset, COUNT(*) FROM mentions WHERE entity_id = ? GROUP BY dataset;
--  Strongest company ties from court co-mentions:
--    SELECT b.value, SUM(weight) w FROM edges WHERE kind='co_litigant' AND a=? GROUP BY b ORDER BY w DESC;
