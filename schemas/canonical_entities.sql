CREATE TABLE IF NOT EXISTS cases (
  case_id TEXT PRIMARY KEY,
  court_id TEXT,
  case_number TEXT,
  jurisdiction TEXT,
  instance TEXT,
  first_seen_at TEXT,
  last_seen_at TEXT,
  source TEXT
);
CREATE INDEX IF NOT EXISTS idx_cases_number ON cases(case_number);
CREATE TABLE IF NOT EXISTS hearings (
  hearing_id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  court_id TEXT,
  scheduled_at TEXT,
  hearing_type TEXT,
  status TEXT,
  source TEXT,
  source_record_hash TEXT,
  FOREIGN KEY(case_id) REFERENCES cases(case_id)
);
CREATE INDEX IF NOT EXISTS idx_hearings_case_time ON hearings(case_id, scheduled_at);
CREATE TABLE IF NOT EXISTS decisions (
  decision_id TEXT PRIMARY KEY,
  case_id TEXT,
  court_id TEXT,
  decision_date TEXT,
  document_type TEXT,
  instance TEXT,
  source TEXT,
  source_record_hash TEXT,
  FOREIGN KEY(case_id) REFERENCES cases(case_id)
);
CREATE INDEX IF NOT EXISTS idx_decisions_case_date ON decisions(case_id, decision_date);
CREATE TABLE IF NOT EXISTS provenance (
  record_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  source_url TEXT,
  retrieved_at TEXT NOT NULL,
  dataset_version TEXT,
  sha256 TEXT,
  record_hash TEXT,
  license TEXT
);
CREATE INDEX IF NOT EXISTS idx_provenance_source ON provenance(source, retrieved_at);
