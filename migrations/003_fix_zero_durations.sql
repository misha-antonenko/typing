-- Fix existing 0 durations in lessons table
UPDATE lessons SET duration = NULL WHERE duration = 0;
