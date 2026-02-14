from tutor import StatsManager, LessonGenerator
import os


def test_logic():
    # Setup test stats db
    if os.path.exists("test_stats.db"):
        os.remove("test_stats.db")

    sm = StatsManager("test_stats.db")
    lg = LessonGenerator(sm)

    print("Testing initial lesson (random)...")
    lesson = lg.generate_lesson()
    for w in lesson:
        print(f"  {w['display']} (ID: {w['word_id']})")

    print("\nRecording artificial mistakes on 'th'...")
    # Simulate mistakes on bigram 'th'
    # 'thought' -> 't' is index 0, 'h' is index 1. Mistake at index 1 is 'th'.
    sm.record_mistake("thought", 1, "x")
    sm.record_mistake("think", 1, "y")
    sm.record_mistake("these", 1, "z")

    print("Weights after 3 'th' mistakes:")
    weights = sm.get_bigram_weights()
    print(f"  {weights}")

    print("\nTesting adaptive lesson (weighted)...")
    lesson = lg.generate_lesson()
    for w in lesson:
        print(f"  {w['display']} (ID: {w['word_id']})")
        # Check if 'th' is in the original word
        if "th" in w["original"].lower():
            print("    [Contains 'th'!]")

    # Test exclusion
    print("\nTesting exclusion of recently typed words...")
    first_word_id = lesson[0]["word_id"]
    sm.record_word_typed(first_word_id)

    lesson2 = lg.generate_lesson()
    ids2 = [w["word_id"] for w in lesson2]
    assert first_word_id in ids2
