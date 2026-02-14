import os
import sqlite3
import sys
from collections import Counter


def create_bigram_index(db_path):
    if not os.path.exists(db_path):
        print(f"Error: Database file {db_path} not found.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Creating bigram_frequency table...")
    # Schema according to the user's inspiration script
    cursor.execute("DROP TABLE IF EXISTS bigram_frequency")
    cursor.execute("""
        CREATE TABLE bigram_frequency (
            bigram TEXT(2) NOT NULL,
            count INTEGER NOT NULL,
            word_id INTEGER NOT NULL,
            PRIMARY KEY (bigram, count, word_id)
        ) WITHOUT ROWID
    """)
    conn.commit()

    print("Fetching words from 'articles' table...")
    cursor.execute("SELECT word_id, title FROM articles WHERE title IS NOT NULL")
    rows = cursor.fetchall()

    print(f"Processing {len(rows)} words...")

    batch_size = 10000
    batch = []

    for word_id, title in rows:
        if not title:
            continue

        # Add boundaries according to the inspiration script: '^' || word || '$'
        word_with_boundaries = f"^{title.lower()}$"

        # Extract bigrams and count their occurrences in the current word
        bigrams = [
            word_with_boundaries[i : i + 2]
            for i in range(len(word_with_boundaries) - 1)
        ]
        counts = Counter(bigrams)

        for bigram, count in counts.items():
            batch.append((bigram, count, word_id))

        if len(batch) >= batch_size:
            cursor.executemany(
                "INSERT INTO bigram_frequency (bigram, count, word_id) VALUES (?, ?, ?)",
                batch,
            )
            conn.commit()
            batch = []

    if batch:
        cursor.executemany(
            "INSERT INTO bigram_frequency (bigram, count, word_id) VALUES (?, ?, ?)",
            batch,
        )
        conn.commit()

    print("Bigram index created successfully.")
    conn.close()


if __name__ == "__main__":
    db_path = "dictionaries/en_en.db"
    create_bigram_index(db_path)
