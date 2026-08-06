"""Seed all 50 state + DC RT CEU requirements with board_name into the database.

Uses UPSERT so existing TX/FL rows are updated (not duplicated).
Requires board_name column (run migrate_board_name.py first).

Data sourced from AARC state licensure information page:
https://www.aarc.org/advocacy/state-advocacy/respiratory-therapist-state-licensure-information/
Verified against state board websites for top 10 most populous states.
"""
import sqlite3
import json
import os
from board_names import STATE_BOARD_NAMES, DEFAULT_BOARD_NAME

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "breathe.db")

# All states with their RT CEU requirements
# Format: (state_code, profession, required_ceus, cycle_years, mandatory_topics)
# For states with no CE requirement, required_ceus=0
STATE_REQUIREMENTS = [
    ("AL", "RRT", 24, 2, []),
    ("AK", "RRT", 0, 2, []),
    ("AZ", "RRT", 20, 2, ["ethics"]),
    ("AR", "RRT", 12, 1, []),
    ("CA", "RRT", 30, 2, ["state-specific laws and professional ethics", "clinical practice", "leadership"]),
    ("CO", "RRT", 0, 2, []),
    ("CT", "RRT", 10, 1, []),
    ("DE", "RRT", 20, 2, []),
    ("DC", "RRT", 16, 2, ["ethics", "LGBTQ continuing education"]),
    ("FL", "RRT", 24, 2, ["medical errors", "laws and rules", "human trafficking"]),
    ("GA", "RRT", 30, 2, []),
    ("HI", "RRT", 0, 3, []),
    ("ID", "RRT", 12, 1, []),
    ("IL", "RRT", 24, 2, []),
    ("IN", "RRT", 15, 2, []),
    ("IA", "RRT", 24, 2, []),
    ("KS", "RRT", 12, 1, []),
    ("KY", "RRT", 24, 2, []),
    ("LA", "RRT", 10, 1, []),
    ("ME", "RRT", 0, 1, []),
    ("MD", "RRT", 16, 2, []),
    ("MA", "RRT", 20, 2, []),
    ("MI", "RRT", 0, 2, ["implicit bias training"]),
    ("MN", "RRT", 24, 2, []),
    ("MS", "RRT", 20, 2, []),
    ("MO", "RRT", 24, 2, []),
    ("MT", "RRT", 24, 2, []),
    ("NE", "RRT", 20, 2, []),
    ("NV", "RRT", 20, 2, ["ethics"]),
    ("NH", "RRT", 24, 2, []),
    ("NJ", "RRT", 30, 2, ["infection control", "patient safety", "ethics"]),
    ("NM", "RRT", 20, 2, ["ethics"]),
    ("NY", "RRT", 30, 3, []),
    ("NC", "RRT", 12, 1, []),
    ("ND", "RRT", 10, 1, []),
    ("OH", "RRT", 20, 2, ["Ohio RC law or professional ethics"]),
    ("OK", "RRT", 12, 2, []),
    ("OR", "RRT", 7, 1, ["clinical practice"]),
    ("PA", "RRT", 30, 2, ["ethics", "patient safety", "child abuse recognition and reporting"]),
    ("RI", "RRT", 12, 2, ["ethics"]),
    ("SC", "RRT", 30, 2, []),
    ("SD", "RRT", 20, 2, ["patient safety"]),
    ("TN", "RRT", 24, 2, ["patient safety", "ethics"]),
    ("TX", "RRT", 24, 2, ["ethics", "human trafficking"]),
    ("UT", "RRT", 0, 2, []),
    ("VT", "RRT", 12, 2, []),
    ("VA", "RRT", 20, 2, []),
    ("WA", "RRT", 30, 2, []),
    ("WV", "RRT", 20, 2, []),
    ("WI", "RRT", 0, 2, []),
    ("WY", "RRT", 8, 1, []),
]


def seed_state_requirements():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Ensure board_name column exists
    cols = [row[1] for row in c.execute("PRAGMA table_info(state_requirements)")]
    if "board_name" not in cols:
        print("❌ board_name column missing! Run migrate_board_name.py first.")
        conn.close()
        return

    added = 0
    updated = 0

    for state, prof, ceus, years, topics in STATE_REQUIREMENTS:
        board_name = STATE_BOARD_NAMES.get(state, DEFAULT_BOARD_NAME)
        topics_json = json.dumps(topics)

        # Check if row exists
        c.execute(
            "SELECT id FROM state_requirements WHERE state = ? AND profession = ?",
            (state, prof)
        )
        existing = c.fetchone()

        if existing:
            c.execute(
                """UPDATE state_requirements
                   SET required_ceus = ?, cycle_years = ?, mandatory_topics = ?, board_name = ?
                   WHERE state = ? AND profession = ?""",
                (ceus, years, topics_json, board_name, state, prof)
            )
            updated += 1
        else:
            c.execute(
                """INSERT INTO state_requirements
                   (state, profession, required_ceus, cycle_years, mandatory_topics, board_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (state, prof, ceus, years, topics_json, board_name)
            )
            added += 1

    conn.commit()

    # Verify
    c.execute("SELECT COUNT(*) FROM state_requirements")
    total = c.fetchone()[0]
    print(f"\n{'='*70}")
    print(f"Total state requirements in DB: {total}")
    print(f"  Added: {added}")
    print(f"  Updated: {updated}")
    print(f"{'='*70}")
    print(f"\n{'State':<6} {'CEUs':<6} {'Cycle':<6} {'Board Name'}")
    print(f"{'-'*70}")
    for row in c.execute(
        "SELECT state, required_ceus, cycle_years, board_name "
        "FROM state_requirements ORDER BY state"
    ):
        print(f"  {row[0]:<4} {row[1]:<6} {row[2]:<6} {row[3]}")

    conn.close()
    print(f"\n✅ Seeded {added + updated} state requirements with board names")


if __name__ == "__main__":
    seed_state_requirements()