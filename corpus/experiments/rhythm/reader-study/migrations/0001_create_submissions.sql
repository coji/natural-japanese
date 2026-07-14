CREATE TABLE submissions (
  participant_id TEXT PRIMARY KEY,
  received_at TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
