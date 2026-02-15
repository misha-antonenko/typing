-- Add duration column to lessons table
ALTER TABLE lessons ADD COLUMN duration REAL;

-- Update existing lessons with computed duration
UPDATE lessons 
SET duration = (
    SELECT MAX(lw.timestamp) - l.timestamp
    FROM lesson_words lw
    JOIN lessons l ON lw.lesson_id = l.id
    WHERE l.id = lessons.id
)
WHERE duration IS NULL;
