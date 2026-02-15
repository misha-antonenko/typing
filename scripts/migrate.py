import os
import sqlite3
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

STATS_DB = "stats.db"
MIGRATION_DIR = "migrations"


def run_migrations():
    if not os.path.exists(MIGRATION_DIR):
        logger.warning(f"Migration directory '{MIGRATION_DIR}' not found.")
        return

    migrations = sorted([f for f in os.listdir(MIGRATION_DIR) if f.endswith(".sql")])

    if not migrations:
        logger.info("No migration files found.")
        return

    logger.info(f"Found {len(migrations)} migration(s).")

    try:
        with sqlite3.connect(STATS_DB) as conn:
            # Create migrations table if not exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    name TEXT PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Get already applied migrations
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM _migrations")
            applied_migrations = {row[0] for row in cursor.fetchall()}

            for m in migrations:
                if m in applied_migrations:
                    logger.info(f"Migration already applied: {m}")
                    continue

                migration_path = os.path.join(MIGRATION_DIR, m)
                logger.info(f"Running migration: {m}")
                with open(migration_path) as f:
                    sql = f.read()
                    conn.executescript(sql)

                conn.execute("INSERT INTO _migrations (name) VALUES (?)", (m,))
                conn.commit()

            logger.info("Migration check completed.")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        # sqlite3 will auto-rollback on exception within the context manager for transaction-based commands,
        # but executescript might have multiple statements.
        # Standard sqlite3 context manager handles commit/rollback for the transaction.
        raise


if __name__ == "__main__":
    run_migrations()
