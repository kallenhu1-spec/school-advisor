CREATE TABLE IF NOT EXISTS bootstrap_payload (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS school_evidence_cache (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  school_name TEXT NOT NULL,
  query_text TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  snippet TEXT NOT NULL DEFAULT '',
  source_type TEXT NOT NULL DEFAULT 'web',
  published_at TEXT,
  fetched_at TEXT NOT NULL,
  UNIQUE(school_name, query_text, url)
);
