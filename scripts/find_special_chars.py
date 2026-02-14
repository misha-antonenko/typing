import os
import sqlite3


def find_special_words():
    db_path = os.path.join(os.path.dirname(__file__), "..", "dictionaries", "en_en.db")

    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Use LIKE and COLLATE NOCASE for robustness, although ^ and $ are usually literal
        query = "SELECT title FROM articles WHERE title LIKE '%^%' OR title LIKE '%$%'"

        cursor.execute(query)
        words = cursor.fetchall()

        if not words:
            print("No words found containing '^' or '$'.")
        else:
            print(f"Found {len(words)} words:")
            for row in words:
                print(row[0])

        conn.close()
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")


if __name__ == "__main__":
    find_special_words()
