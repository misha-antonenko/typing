import sqlite3
import time

import pytest

from tutor import LessonGenerator, LessonSession, LessonWord, StatsManager


@pytest.fixture
def stats_manager(tmp_path):
    db_path = tmp_path / "test_stats.db"
    return StatsManager(str(db_path))


@pytest.fixture
def lesson_generator(stats_manager):
    return LessonGenerator(stats_manager)


def test_initial_lesson_generation(lesson_generator):
    lesson = lesson_generator.generate_lesson()
    assert len(lesson) == 10
    for item in lesson:
        assert hasattr(item, "word_id")
        assert hasattr(item, "display")
        assert hasattr(item, "separator")


def test_weighted_sampling_on_mistakes(stats_manager, lesson_generator):
    # Simulate mistakes on bigram 'th' (displayed as 'th')
    stats_manager.record_mistake("thought", 1, "x")
    stats_manager.record_mistake("think", 1, "y")
    stats_manager.record_mistake("these", 1, "z")
    stats_manager.record_mistake("these", 0, "z")

    weights = stats_manager.get_bigram_weights()
    assert "th" in weights
    assert weights["th"] > 0
    assert weights["^t"] > 0

    # Generate lesson and check for bias
    # Since we only have 3 mistakes, and dictionary is large,
    # we expect at least some words containing 'th'
    lesson = lesson_generator.generate_lesson()
    th_count = sum(1 for w in lesson if "th" in w.original.lower())
    # Given we k=10 from 1 bigram weight, it should be quite high
    assert th_count > 0


def test_mistake_recording_uses_display_word(stats_manager):
    # If the system expects 'T' and user types 'x', it should record 'T'.
    stats_manager.record_mistake("Test", 0, "x")
    with sqlite3.connect(stats_manager.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT word, typed_char FROM mistakes")
        row = cursor.fetchone()
        assert row == ("Test", "x")


def test_exclusion_of_recently_typed_words(stats_manager, lesson_generator):
    lesson1 = lesson_generator.generate_lesson()
    first_word_id = lesson1[0].word_id

    # Record as typed
    lesson_id = stats_manager.record_lesson(time.time(), "test", "test", 1.0)
    stats_manager.record_lesson_words(lesson_id, [first_word_id])

    # Generate new lesson
    lesson2 = lesson_generator.generate_lesson()
    ids2 = [w.word_id for w in lesson2]

    assert first_word_id not in ids2


def test_lesson_session_accuracy_with_backspace(stats_manager):
    lesson = [LessonWord(word_id=1, original="test", display="Test", separator=" ")]
    session = LessonSession(lesson, stats_manager)

    # Type correctly 'T'
    session.handle_key(ord("T"))
    stats = session.get_stats()
    assert stats.accuracy == 100.0
    assert session.total_typed_count == 1

    # Type mistake 'x' instead of 'e'
    session.handle_key(ord("x"))
    stats = session.get_stats()
    assert stats.accuracy == 50.0  # 1 correct, 1 mistake. Total 2. (2-1)/2 * 100 = 50.
    assert session.total_typed_count == 2
    assert session.mistakes_count == 1

    # Backspace
    session.handle_key(127)  # Backspace
    assert len(session.typed_text) == 1
    assert session.total_typed_count == 2  # Backspace shouldn't increment total

    # Type mistake again 'y' instead of 'e'
    session.handle_key(ord("y"))
    stats = session.get_stats()
    # Total typed: 1 ('T') + 1 ('x') + 1 ('y') = 3
    # Mistakes: 1 ('x') + 1 ('y') = 2
    # Accuracy: (3-2)/3 * 100 = 33.33...
    assert stats.accuracy == pytest.approx(33.33, rel=1e-2)
    assert session.total_typed_count == 3
    assert session.mistakes_count == 2

    # Backspace
    session.handle_key(8)  # Another backspace variant

    # Type correctly 'e'
    session.handle_key(ord("e"))
    stats = session.get_stats()
    # Total typed: 4
    # Mistakes: 2
    # Accuracy: (4-2)/4 * 100 = 50.0
    assert stats.accuracy == 50.0
    assert session.total_typed_count == 4
    assert session.mistakes_count == 2


def test_lesson_session_mistake_recording_after_backspace(stats_manager):
    lesson = [LessonWord(word_id=1, original="abc", display="abc", separator=" ")]
    session = LessonSession(lesson, stats_manager)

    # Type 'a', then mistake 'x' for 'b'
    session.handle_key(ord("a"))
    session.handle_key(ord("x"))

    # Backspace and type mistake 'y' for 'b'
    session.handle_key(127)
    session.handle_key(ord("y"))

    with sqlite3.connect(stats_manager.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT typed_char FROM mistakes WHERE char_index = 1")
        rows = cursor.fetchall()
        assert len(rows) == 2
        assert rows[0][0] == "x"
        assert rows[1][0] == "y"


def test_lesson_full_storage(stats_manager):
    lesson = [
        LessonWord(word_id=1, original="apple", display="Apple", separator=", "),
        LessonWord(word_id=2, original="banana", display="Banana", separator="."),
    ]
    session = LessonSession(lesson, stats_manager)

    # Full text: "Apple, Banana."
    # Type "App"
    for c in "App":
        session.handle_key(ord(c))

    # Error "o" instead of "l"
    session.handle_key(ord("o"))

    # Backspace
    session.handle_key(127)

    # Correct "le, Banana."
    for c in "le, Banana.":
        session.handle_key(ord(c))

    # Record lesson is recorded
    # We simulate what TutorTUI._run_lesson does
    stats = session.get_stats()
    lesson_id = stats_manager.record_lesson(
        session.start_time, session.full_text, session.raw_typed_text, stats.duration
    )
    stats_manager.record_lesson_words(lesson_id, session.completed_word_ids_ordered)

    with sqlite3.connect(stats_manager.db_path) as conn:
        cursor = conn.cursor()

        # Check lessons table
        cursor.execute("SELECT timestamp, text_required, text_typed FROM lessons")
        row = cursor.fetchone()
        assert row[1] == "Apple, Banana."
        # "App" + "o" + "\b" + "le, Banana."
        assert row[2] == "Appo\ble, Banana."

        # Check lesson_words table
        cursor.execute(
            "SELECT word_id FROM lesson_words WHERE lesson_id = ? ORDER BY id",
            (lesson_id,),
        )
        words = [r[0] for r in cursor.fetchall()]
        assert words == [1, 2]


def test_ascii_only_sampling(tmp_path):
    # Create a dummy dictionary DB with ASCII and non-ASCII words
    dict_db_path = tmp_path / "test_dict.db"
    with sqlite3.connect(dict_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE articles (word_id INTEGER PRIMARY KEY, title TEXT)"
        )
        cursor.execute("CREATE INDEX idx_title ON articles (title)")
        cursor.execute(
            "INSERT INTO articles (word_id, title) VALUES (1, 'apple'), (2, 'abbé'), (3, 'banana'), (4, 'açai')"
        )
        conn.commit()

    stats_manager = StatsManager(str(tmp_path / "test_stats.db"))
    generator = LessonGenerator(stats_manager, dict_db_path=str(dict_db_path))

    # Sample many times to be sure
    for _ in range(10):
        lesson = generator.generate_lesson()
        for word in lesson:
            # Check if any word contains non-ASCII characters
            assert word.original.isascii(), f"Word '{word.original}' is not ASCII"
            assert word.original in ("apple", "banana")


def test_ema_calculation(stats_manager):
    # Record two lessons
    now = time.time()
    # Lesson 1: 100% accuracy, 10 CPS, 1 week ago
    one_week = 7 * 24 * 3600
    stats_manager.record_lesson(now - one_week, "abc", "abc", 0.3)  # CPS = 3/0.3 = 10
    # Lesson 2: 50% accuracy, 20 CPS, now
    stats_manager.record_lesson(now, "abcd", "axcy", 0.2)  # CPS = 4/0.2 = 20

    ema_cps, ema_acc = stats_manager.get_ema_stats()

    # Weight for lesson 1: exp(-1) = 0.367879
    # Weight for lesson 2: exp(0) = 1.0
    # Expected EMA CPS: (10 * 0.367879 + 20 * 1) / (0.367879 + 1) = 23.67879 / 1.367879 = 17.31
    # Expected EMA Acc: (100 * 0.367879 + 50 * 1) / (0.367879 + 1) = 86.7879 / 1.367879 = 63.45

    assert ema_cps == pytest.approx(17.31, rel=1e-2)
    assert ema_acc == pytest.approx(63.45, rel=1e-2)


def test_lesson_session_delayed_start_time(stats_manager):
    lesson = [LessonWord(word_id=1, original="a", display="a", separator=" ")]
    session = LessonSession(lesson, stats_manager)

    # Initially start_time should be None
    assert session.start_time is None

    # Stats should raise ValueError before session starts
    with pytest.raises(ValueError, match="session was not started"):
        session.get_stats()

    # Type first key
    time.sleep(0.01)  # Ensure some time passes
    session.handle_key(ord("a"))

    # Now start_time should be set
    assert session.start_time is not None
    assert session.start_time <= time.time()

    # Duration should now be > 0
    stats = session.get_stats()
    assert stats.duration > 0
