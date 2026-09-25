CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('phone', 'telegram')),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    due_at TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'sending', 'sent')),
    created_at TEXT NOT NULL,
    sending_at TEXT,
    sent_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(state, due_at);
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS telegram_updates (
    id INTEGER PRIMARY KEY,
    received_at TEXT NOT NULL
);
