import sqlite3
import time
import math
import random
import curses
import sys

# Constants
STATS_DB = "stats.db"
DICTIONARY_DB = "dictionaries/en_en.db"
WORDS_PER_LESSON = 10
EXCLUDE_RECENT_MINUTES = 5


class StatsManager:
    def __init__(self, db_path=STATS_DB):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mistakes (
                    word TEXT,
                    char_index INTEGER,
                    typed_char TEXT,
                    timestamp REAL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lesson_history (
                    word_id INTEGER,
                    timestamp REAL
                )
            """)
            conn.commit()

    def record_mistake(self, word, index, typed_char):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO mistakes (word, char_index, typed_char, timestamp) VALUES (?, ?, ?, ?)",
                (word, index, typed_char, time.time()),
            )
            conn.commit()

    def record_word_typed(self, word_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO lesson_history (word_id, timestamp) VALUES (?, ?)",
                (word_id, time.time()),
            )
            conn.commit()

    def get_bigram_weights(self):
        now = time.time()
        one_week = 7 * 24 * 3600

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT word, char_index, timestamp FROM mistakes")
            rows = cursor.fetchall()

        weights = {}
        for word, index, ts in rows:
            # Mistake happened at index. Bigram is word[index-1:index+1]
            # Use boundaries if necessary? The user mentioned bigrams.
            # Usually a typing mistake "ab" typed as "ax" means the transition a->b is hard.
            # So the bigram is word[index-1:index+1] (if index > 0)
            if index > 0:
                bigram = word[index - 1 : index + 1]
            else:
                bigram = f"^{word[0]}"  # Start of word boundary

            t_weeks = (ts - now) / one_week
            weight = math.exp(t_weeks)
            weights[bigram] = weights.get(bigram, 0) + weight

        return weights

    def get_recently_typed_ids(self):
        cutoff = time.time() - (EXCLUDE_RECENT_MINUTES * 60)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT word_id FROM lesson_history WHERE timestamp > ?", (cutoff,)
            )
            return {row[0] for row in cursor.fetchall()}


class LessonGenerator:
    def __init__(self, stats_manager, dict_db_path=DICTIONARY_DB):
        self.stats_manager = stats_manager
        self.dict_db_path = dict_db_path

    def generate_lesson(self):
        bigram_weights = self.stats_manager.get_bigram_weights()
        recently_typed = self.stats_manager.get_recently_typed_ids()

        words = []
        if not bigram_weights:
            # Random sample if no mistakes
            words = self._sample_random(WORDS_PER_LESSON, recently_typed)
        else:
            # Weighted sample
            words = self._sample_weighted(
                WORDS_PER_LESSON, bigram_weights, recently_typed
            )

        # If we couldn't get enough words (e.g. dictionary too small or all excluded)
        if len(words) < WORDS_PER_LESSON:
            more = self._sample_random(
                WORDS_PER_LESSON - len(words), recently_typed | {w[0] for w in words}
            )
            words.extend(more)

        return self._format_lesson(words)

    def _sample_random(self, count, exclude_ids):
        with sqlite3.connect(self.dict_db_path) as conn:
            cursor = conn.cursor()
            query = "SELECT word_id, title FROM articles"
            if exclude_ids:
                placeholders = ",".join(["?"] * len(exclude_ids))
                query += f" WHERE word_id NOT IN ({placeholders})"
            query += " ORDER BY RANDOM() LIMIT ?"

            params = list(exclude_ids) + [count]
            cursor.execute(query, params)
            return cursor.fetchall()

    def _sample_weighted(self, count, bigram_weights, exclude_ids):
        # Select bigrams to target
        bigrams = list(bigram_weights.keys())
        weights = list(bigram_weights.values())

        sampled_words = []
        used_word_ids = set(exclude_ids)

        # We need 10 words. We'll pick bigrams proportional to weights.
        target_bigrams = random.choices(bigrams, weights=weights, k=count)

        with sqlite3.connect(self.dict_db_path) as conn:
            cursor = conn.cursor()
            for bg in target_bigrams:
                # Find a word containing this bigram that isn't excluded
                query = """
                    SELECT b.word_id, a.title 
                    FROM bigram_frequency b
                    JOIN articles a ON b.word_id = a.word_id
                    WHERE b.bigram = ? 
                """
                if used_word_ids:
                    placeholders = ",".join(["?"] * len(used_word_ids))
                    query += f" AND b.word_id NOT IN ({placeholders})"
                query += " ORDER BY RANDOM() LIMIT 1"

                params = [bg] + list(used_word_ids)
                cursor.execute(query, params)
                row = cursor.fetchone()
                if row:
                    sampled_words.append(row)
                    used_word_ids.add(row[0])
                else:
                    # Fallback to random if no word found for this bigram
                    fallback = self._sample_random(1, used_word_ids)
                    if fallback:
                        sampled_words.append(fallback[0])
                        used_word_ids.add(fallback[0][0])

        return sampled_words

    def _format_lesson(self, words):
        # words is list of (word_id, title)
        lesson_data = []
        punctuations = [",", ".", ";", ":", "!", "?"]

        for i, (word_id, title) in enumerate(words):
            # Random capitalization
            mode = random.choice(["lower", "capitalize", "upper"])
            if mode == "capitalize":
                processed = title.capitalize()
            elif mode == "upper":
                processed = title.upper()
            else:
                processed = title.lower()

            # Random punctuation
            sep = ""
            if i < len(words) - 1:
                if random.random() < 0.3:
                    sep = random.choice(punctuations) + " "
                else:
                    sep = " "

            lesson_data.append(
                {
                    "word_id": word_id,
                    "original": title,
                    "display": processed,
                    "separator": sep,
                }
            )
        return lesson_data


class TutorTUI:
    def __init__(self, stats_manager, lesson_generator):
        self.stats_manager = stats_manager
        self.lesson_generator = lesson_generator

    def run(self):
        curses.wrapper(self._main)

    def _main(self, stdscr):
        curses.start_color()
        curses.use_default_colors()
        # Define colors
        curses.init_pair(1, curses.COLOR_GREEN, -1)  # Correct (Green on default)
        curses.init_pair(
            2, curses.COLOR_WHITE, curses.COLOR_RED
        )  # Mistake (White on Red)
        curses.init_pair(3, curses.COLOR_CYAN, -1)  # Remaining (Cyan on default)

        stdscr.nodelay(False)
        curses.curs_set(1)

        while True:
            lesson = self.lesson_generator.generate_lesson()
            if not self._run_lesson(stdscr, lesson):
                break  # User exit or error

    def _run_lesson(self, stdscr, lesson):
        # Construct full lesson string
        full_text = ""
        word_mapping = []  # (char_idx_start, char_idx_end, word_obj)

        for w in lesson:
            start = len(full_text)
            full_text += w["display"]
            end = len(full_text)
            word_mapping.append((start, end, w))
            full_text += w["separator"]

        typed_text = ""
        completed_word_ids = set()
        start_time = time.time()
        mistakes_count = 0

        while len(typed_text) < len(full_text):
            stdscr.erase()
            h, w = stdscr.getmaxyx()

            # Draw stats
            elapsed = time.time() - start_time
            wpm = (len(typed_text) / 5) / (elapsed / 60) if elapsed > 0 else 0
            accuracy = (
                ((len(typed_text) - mistakes_count) / len(typed_text) * 100)
                if typed_text
                else 100
            )

            stats_str = f" WPM: {wpm:3.0f} | Accuracy: {accuracy:3.0f}% "
            try:
                stdscr.addstr(
                    0, max(0, w - len(stats_str) - 2), stats_str, curses.A_REVERSE
                )
                stdscr.addstr(0, 0, " [Ctrl-C] Next Lesson | [ESC] Exit ", curses.A_DIM)
            except curses.error:
                pass

            # Calculate wrapped lines
            max_text_width = min(w - 4, 80)  # Bound width for readability
            x_offset = (w - max_text_width) // 2
            y_offset = h // 3

            current_y = y_offset
            current_x = x_offset

            # Draw text with wrapping
            for i, char in enumerate(full_text):
                color = curses.color_pair(3)
                if i < len(typed_text):
                    if typed_text[i] == full_text[i]:
                        color = curses.color_pair(1)
                    else:
                        color = curses.color_pair(2)

                # Highlight cursor position
                attr = color
                if i == len(typed_text):
                    attr |= curses.A_UNDERLINE | curses.A_BOLD

                try:
                    stdscr.addch(current_y, current_x, char, attr)
                except curses.error:
                    pass

                current_x += 1
                if current_x >= x_offset + max_text_width:
                    current_x = x_offset
                    current_y += 1

            stdscr.refresh()

            try:
                ch = stdscr.getch()
            except KeyboardInterrupt:
                return True  # Loop back to next lesson

            if ch == 27:  # ESC
                sys.exit(0)

            if ch == curses.KEY_RESIZE:
                continue

            if ch in (curses.KEY_BACKSPACE, 127, 8):
                if typed_text:
                    typed_text = typed_text[:-1]
                continue

            if ch < 0 or ch > 255:
                continue

            char_typed = chr(ch)
            current_idx = len(typed_text)

            # Check for mistake
            if char_typed != full_text[current_idx]:
                mistakes_count += 1
                # Find which word this belongs to
                target_word = None
                for start, end, wo in word_mapping:
                    if start <= current_idx < end:
                        target_word = wo
                        break

                if target_word:
                    self.stats_manager.record_mistake(
                        target_word["original"], current_idx - start, char_typed
                    )

            typed_text += char_typed

            # Check for word completion
            for start, end, wo in word_mapping:
                if len(typed_text) == end and wo["word_id"] not in completed_word_ids:
                    self.stats_manager.record_word_typed(wo["word_id"])
                    completed_word_ids.add(wo["word_id"])
                    break

        return True


def main():
    stats_mgr = StatsManager()
    lesson_gen = LessonGenerator(stats_mgr)
    tui = TutorTUI(stats_mgr, lesson_gen)
    tui.run()


if __name__ == "__main__":
    main()
