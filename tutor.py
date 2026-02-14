import curses
import math
import random
import sqlite3
import sys
import time
from dataclasses import dataclass
from typing import Any

# Constants
STATS_DB = "stats.db"
DICTIONARY_DB = "dictionaries/en_en.db"
WORDS_PER_LESSON = 10
EXCLUDE_RECENT_MINUTES = 5


@dataclass(frozen=True)
class LessonWord:
    word_id: int
    original: str
    display: str
    separator: str


class StatsManager:
    def __init__(self, db_path: str = STATS_DB) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
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

    def record_mistake(self, word: str, index: int, typed_char: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO mistakes (word, char_index, typed_char, timestamp) VALUES (?, ?, ?, ?)",
                (word, index, typed_char, time.time()),
            )
            conn.commit()

    def record_word_typed(self, word_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO lesson_history (word_id, timestamp) VALUES (?, ?)",
                (word_id, time.time()),
            )
            conn.commit()

    def get_bigram_weights(self) -> dict[str, float]:
        now = time.time()
        one_week = 7 * 24 * 3600

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Retrieve the display word, the index of the mistake, and the character the user typed
            cursor.execute(
                "SELECT word, char_index, typed_char, timestamp FROM mistakes"
            )
            rows = cursor.fetchall()

        weights: dict[str, float] = {}
        for display_word, index, _, ts in rows:
            # Reconstruct the expected character from the displayed word at the recorded index.
            # This is why we store the displayed word.
            if index > 0:
                bigram = display_word[index - 1 : index + 1].lower()
            else:
                bigram = f"^{display_word[0].lower()}"

            t_weeks = (ts - now) / one_week
            weight = math.exp(t_weeks)
            weights[bigram] = weights.get(bigram, 0) + weight

        return weights

    def get_recently_typed_ids(self) -> set[int]:
        cutoff = time.time() - (EXCLUDE_RECENT_MINUTES * 60)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT word_id FROM lesson_history WHERE timestamp > ?", (cutoff,)
            )
            return {row[0] for row in cursor.fetchall()}


class LessonGenerator:
    def __init__(
        self, stats_manager: StatsManager, dict_db_path: str = DICTIONARY_DB
    ) -> None:
        self.stats_manager = stats_manager
        self.dict_db_path = dict_db_path

    def generate_lesson(self) -> list[LessonWord]:
        bigram_weights = self.stats_manager.get_bigram_weights()
        recently_typed = self.stats_manager.get_recently_typed_ids()

        words: list[tuple[int, str]] = []
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

    def _sample_random(
        self, count: int, exclude_ids: set[int]
    ) -> list[tuple[int, str]]:
        with sqlite3.connect(self.dict_db_path) as conn:
            cursor = conn.cursor()
            query = "SELECT word_id, title FROM articles"
            params: list[Any] = []
            if exclude_ids:
                placeholders = ",".join(["?"] * len(exclude_ids))
                query += f" WHERE word_id NOT IN ({placeholders})"
                params.extend(exclude_ids)
            query += " ORDER BY RANDOM() LIMIT ?"
            params.append(count)

            cursor.execute(query, params)
            return cursor.fetchall()

    def _sample_weighted(
        self, count: int, bigram_weights: dict[str, float], exclude_ids: set[int]
    ) -> list[tuple[int, str]]:
        # Select bigrams to target
        bigrams = list(bigram_weights.keys())
        weights = list(bigram_weights.values())

        sampled_words: list[tuple[int, str]] = []
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
                params: list[Any] = [bg]
                if used_word_ids:
                    placeholders = ",".join(["?"] * len(used_word_ids))
                    query += f" AND b.word_id NOT IN ({placeholders})"
                    params.extend(used_word_ids)
                query += " ORDER BY RANDOM() LIMIT 1"

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

    def _format_lesson(self, words: list[tuple[int, str]]) -> list[LessonWord]:
        # words is list of (word_id, title)
        lesson_data: list[LessonWord] = []
        punctuations = ["", ",", ".", ";", ":", "!", "?"]

        for word_id, title in words:
            # Random capitalization
            mode = random.randint(0, 3)
            if mode == 0:
                processed = title.capitalize()
            elif mode == 1:
                processed = title.upper()
            elif mode == 2:
                processed = title.lower()
            else:
                processed = title

            # Random punctuation
            sep = random.choice(punctuations) + " "

            lesson_data.append(
                LessonWord(
                    word_id=word_id,
                    original=title,
                    display=processed,
                    separator=sep,
                )
            )
        return lesson_data


class LessonSession:
    def __init__(
        self,
        lesson: list[LessonWord],
        stats_manager: StatsManager,
        start_time: float | None = None,
    ) -> None:
        self.lesson = lesson
        self.stats_manager = stats_manager
        self.full_text = ""
        self.word_mapping: list[tuple[int, int, LessonWord]] = []
        self._build_mapping()

        self.typed_text = ""
        self.completed_word_ids: set[int] = set()
        self.start_time = start_time if start_time is not None else time.time()
        self.mistakes_count = 0
        self.total_typed_count = 0

    def _build_mapping(self) -> None:
        text = ""
        for w in self.lesson:
            start = len(text)
            text += w.display
            end = len(text)
            self.word_mapping.append((start, end, w))
            text += w.separator
        self.full_text = text

    def handle_key(self, ch: int) -> bool:
        """Returns True if the lesson should continue, False if it's finished."""
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            if self.typed_text:
                self.typed_text = self.typed_text[:-1]
            return True

        if ch < 0 or ch > 255:
            return True

        char_typed = chr(ch)
        current_idx = len(self.typed_text)

        if current_idx >= len(self.full_text):
            return False

        self.total_typed_count += 1

        # Check for mistake
        if char_typed != self.full_text[current_idx]:
            self.mistakes_count += 1
            # Find which word this belongs to
            target_word: LessonWord | None = None
            word_start = 0
            for start, end, wo in self.word_mapping:
                if start <= current_idx < end:
                    target_word = wo
                    word_start = start
                    break

            if target_word:
                self.stats_manager.record_mistake(
                    target_word.display, current_idx - word_start, char_typed
                )

        self.typed_text += char_typed

        # Check for word completion
        for _, end, wo in self.word_mapping:
            if (
                len(self.typed_text) == end
                and wo.word_id not in self.completed_word_ids
            ):
                self.stats_manager.record_word_typed(wo.word_id)
                self.completed_word_ids.add(wo.word_id)
                break

        return len(self.typed_text) < len(self.full_text)

    def get_stats(self) -> tuple[float, float]:
        """Returns (cps, accuracy)."""
        elapsed = time.time() - self.start_time
        cps = len(self.typed_text) / elapsed if elapsed > 0 else 0
        accuracy = (
            (
                (self.total_typed_count - self.mistakes_count)
                / self.total_typed_count
                * 100
            )
            if self.total_typed_count > 0
            else 100.0
        )
        return cps, accuracy


class TutorTUI:
    def __init__(
        self, stats_manager: StatsManager, lesson_generator: LessonGenerator
    ) -> None:
        self.stats_manager = stats_manager
        self.lesson_generator = lesson_generator

    def run(self) -> None:
        curses.wrapper(self._main)

    def _main(self, stdscr: Any) -> None:
        curses.start_color()
        curses.use_default_colors()
        # Define colors
        curses.init_pair(1, curses.COLOR_GREEN, -1)  # Correct (Green on default)
        curses.init_pair(
            2, curses.COLOR_WHITE, curses.COLOR_RED
        )  # Mistake (White on Red)
        curses.init_pair(3, curses.COLOR_CYAN, -1)  # Remaining (Cyan on default)

        stdscr.nodelay(False)  # noqa: FBT003
        curses.curs_set(1)

        while True:
            lesson = self.lesson_generator.generate_lesson()
            if not self._run_lesson(stdscr, lesson):
                break  # User exit or error

    def _run_lesson(self, stdscr: Any, lesson: list[LessonWord]) -> bool:
        session = LessonSession(lesson, self.stats_manager)

        while True:
            stdscr.erase()
            h, w = stdscr.getmaxyx()

            # Draw stats
            cps, accuracy = session.get_stats()
            stats_str = f" CPS: {cps:4.1f} | Accuracy: {accuracy:3.0f}% "
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
            for i, char in enumerate(session.full_text):
                color = curses.color_pair(3)
                if i < len(session.typed_text):
                    if session.typed_text[i] == session.full_text[i]:
                        color = curses.color_pair(1)
                    else:
                        color = curses.color_pair(2)

                # Highlight cursor position
                attr = color
                if i == len(session.typed_text):
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
                return True  # Next lesson

            if ch == 27:  # ESC
                sys.exit(0)

            if ch == curses.KEY_RESIZE:
                continue

            if not session.handle_key(ch):
                break

        return True


def main() -> None:
    stats_mgr = StatsManager()
    lesson_gen = LessonGenerator(stats_mgr)
    tui = TutorTUI(stats_mgr, lesson_gen)
    tui.run()


if __name__ == "__main__":
    main()
