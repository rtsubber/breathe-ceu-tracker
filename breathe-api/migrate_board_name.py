"""Idempotent migration: add board_name column to state_requirements table."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "breathe.db")

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cols = [row[1] for row in cur.execute("PRAGMA table_info(state_requirements)")]
    if "board_name" not in cols:
        cur.execute("ALTER TABLE state_requirements ADD COLUMN board_name TEXT;")
        print("✅ Added board_name column to state_requirements")
    else:
        print("⏭️  board_name column already exists — skipping")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate()