CREATE TABLE IF NOT EXISTS shared_memories (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  items TEXT NOT NULL DEFAULT '[]',
  version INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO shared_memories (id, items, version) VALUES (1, '[]', 0);
