import sqlite3
import xml.etree.ElementTree as ET
import os
import sys


def process_dictionary(input_file, db_file):
    # Ensure the directory for the database exists
    os.makedirs(os.path.dirname(db_file), exist_ok=True)

    # Connect to SQLite
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # Create table with title and word_id columns
    cursor.execute("DROP TABLE IF EXISTS articles")
    cursor.execute("CREATE TABLE articles (word_id INTEGER PRIMARY KEY, title TEXT)")

    # Use a generator to yield titles from the file
    def get_entries():
        word_id = 1
        with open(input_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    # Each line is an XML document
                    # Using fromstring because each line is a self-contained XML
                    root = ET.fromstring(line.strip())
                    # The title is in the 'd:title' attribute of the root <d:entry> tag
                    # The namespace is http://www.apple.com/DTDs/DictionaryService-1.0.rng
                    title = root.get(
                        "{http://www.apple.com/DTDs/DictionaryService-1.0.rng}title"
                    )
                    if not title:
                        # Fallback if namespaced attribute is not found
                        title = root.get("d:title")

                    if title:
                        if "^" in title or "$" in title:
                            continue
                        yield (word_id, title)
                        word_id += 1
                except ET.ParseError as e:
                    print(f"Error parsing line: {e}", file=sys.stderr)
                    continue

    # Batch insert for performance
    batch_size = 1000
    batch = []
    count = 0

    for entry in get_entries():
        batch.append(entry)
        if len(batch) >= batch_size:
            cursor.executemany(
                "INSERT INTO articles (word_id, title) VALUES (?, ?)", batch
            )
            conn.commit()
            count += len(batch)
            print(f"Processed {count} entries...", end="\r")
            batch = []

    if batch:
        cursor.executemany("INSERT INTO articles (word_id, title) VALUES (?, ?)", batch)
        conn.commit()
        count += len(batch)
        print(f"Processed {count} entries total.")

    # Create index on title
    print("Creating index on 'title'...")
    cursor.execute("CREATE INDEX idx_title ON articles (title)")
    conn.commit()

    conn.close()
    print("Done.")


if __name__ == "__main__":
    input_path = "dictionaries/en_en.txt"
    output_path = "dictionaries/en_en.db"

    if not os.path.exists(input_path):
        print(f"Error: Input file {input_path} not found.")
        sys.exit(1)

    process_dictionary(input_path, output_path)
