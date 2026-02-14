import pytest
from tutor import StatsManager, LessonGenerator


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
        assert "word_id" in item
        assert "display" in item
        assert "separator" in item


def test_weighted_sampling_on_mistakes(stats_manager, lesson_generator):
    # Simulate mistakes on bigram 'th'
    # 'thought' -> index 1 is 'th'
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
    th_count = sum(1 for w in lesson if "th" in w["original"].lower())
    # Given we k=10 from 1 bigram weight, it should be quite high
    assert th_count > 0


def test_exclusion_of_recently_typed_words(stats_manager, lesson_generator):
    lesson1 = lesson_generator.generate_lesson()
    first_word_id = lesson1[0]["word_id"]

    # Record as typed
    stats_manager.record_word_typed(first_word_id)

    # Generate new lesson
    lesson2 = lesson_generator.generate_lesson()
    ids2 = [w["word_id"] for w in lesson2]

    assert first_word_id not in ids2
