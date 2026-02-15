-- Create lessons table
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    text_required TEXT NOT NULL,
    text_typed TEXT NOT NULL
);

-- Create lesson_words table
CREATE TABLE IF NOT EXISTS lesson_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL,
    word_id INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    FOREIGN KEY (lesson_id) REFERENCES lessons(id)
);

-- Migrate existing lesson_history to lesson_words
-- We create dummy lessons for existing history entries to maintain referential integrity
INSERT INTO lessons (timestamp, text_required, text_typed)
SELECT timestamp, 'MIGRATED', 'MIGRATED'
FROM lesson_history
WHERE timestamp NOT IN (SELECT timestamp FROM lessons);

INSERT INTO lesson_words (lesson_id, word_id, timestamp)
SELECT l.id, h.word_id, h.timestamp
FROM lesson_history h
JOIN lessons l ON h.timestamp = l.timestamp AND l.text_required = 'MIGRATED'
WHERE NOT EXISTS (
    SELECT 1 FROM lesson_words lw 
    WHERE lw.lesson_id = l.id AND lw.word_id = h.word_id AND lw.timestamp = h.timestamp
);
