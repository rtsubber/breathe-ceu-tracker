"""Add all 50 state + DC RT CEU requirements to the database.

Data sourced from AARC (American Association for Respiratory Care):
https://www.aarc.org/advocacy/state-advocacy/respiratory-therapist-state-licensure-information/
Verified against state board websites for top 10 most populous states (CA, TX, NY, FL, IL, PA, OH, GA, NC, MI).

NOTE: TX is already in the DB with 30 CEUs (the seed.py value). AARC and TX Medical Board
Rule 187.16 confirm TX is actually 24 CEUs/2yr. We skip existing entries per instructions,
but a separate update should fix the TX value.

NOTE: FL is already in the DB with 24 CEUs and mandatory topics. AARC confirms 24 CEUs/2yr
but lists additional mandatory topics (medical errors, laws and rules, human trafficking).
The existing FL entry has ["medical errors", "HIV/AIDS", "domestic violence"] which may
be outdated. A separate update should fix the FL mandatory topics.
"""
import sqlite3
import json

DB_PATH = "/home/ron/.openclaw/workspace/ceu-tracker/breathe-api/breathe.db"

# All states with their RT CEU requirements
# Format: (state_code, profession, required_ceus, cycle_years, mandatory_topics)
# Sources: AARC state licensure information page, verified against state board websites
# For states with no CE requirement, required_ceus=0 and cycle_years=2 (placeholder)
STATE_REQUIREMENTS = [
    # Already in DB — skip these:
    # ("TX", "RRT", 24, 2, ["ethics", "human trafficking"]),
    # ("FL", "RRT", 24, 2, ["medical errors", "laws and rules", "human trafficking"]),

    # Alabama — Biennial, 24 total, min 12 traditional
    ("AL", "RRT", 24, 2, []),

    # Alaska — No licensure (no CE requirement)
    ("AK", "RRT", 0, 2, []),

    # Arizona — Biennial, 20 total, 2 hours ethics, min 5 traditional
    ("AZ", "RRT", 20, 2, ["ethics"]),

    # Arkansas — Annual, 12 total per year (24 per 2yr cycle)
    ("AR", "RRT", 12, 1, []),

    # California — Biennial, 30 total, 3 hrs state-specific laws & professional ethics
    # Verified: rcb.ca.gov/licensees/ce.shtml — 30 hrs, 15 clinical, 10 leadership, 15 live
    ("CA", "RRT", 30, 2, ["state-specific laws and professional ethics", "clinical practice", "leadership"]),

    # Colorado — Biennial, not required for renewal
    ("CO", "RRT", 0, 2, []),

    # Connecticut — Annual, 10 total, min 5 traditional
    ("CT", "RRT", 10, 1, []),

    # Delaware — Biennial, 20 total, min 10 traditional
    ("DE", "RRT", 20, 2, []),

    # District of Columbia — Biennial, 16 total, 2 hrs ethics, 2 hrs LGBTQ CE
    ("DC", "RRT", 16, 2, ["ethics", "LGBTQ continuing education"]),

    # Georgia — Biennial, 30 total
    ("GA", "RRT", 30, 2, []),

    # Hawaii — Triennial, not required for renewal
    ("HI", "RRT", 0, 3, []),

    # Idaho — Annual, 12 total
    ("ID", "RRT", 12, 1, []),

    # Illinois — Biennial, 24 total
    ("IL", "RRT", 24, 2, []),

    # Indiana — Biennial, 15 total
    ("IN", "RRT", 15, 2, []),

    # Iowa — Biennial, 24 total, min 12 traditional
    ("IA", "RRT", 24, 2, []),

    # Kansas — Annual, 12 total, min 6 traditional
    ("KS", "RRT", 12, 1, []),

    # Kentucky — Biennial, 24 total
    ("KY", "RRT", 24, 2, []),

    # Louisiana — Annual, 10 total
    ("LA", "RRT", 10, 1, []),

    # Maine — Annual, not required for renewal
    ("ME", "RRT", 0, 1, []),

    # Maryland — Biennial, 16 total
    ("MD", "RRT", 16, 2, []),

    # Massachusetts — Biennial, 20 total
    ("MA", "RRT", 20, 2, []),

    # Michigan — Biennial, not required for renewal (1 hr implicit bias/yr)
    ("MI", "RRT", 0, 2, ["implicit bias training"]),

    # Minnesota — Annual, 24 total every 2 years
    ("MN", "RRT", 24, 2, []),

    # Mississippi — Biennial, 20 total
    ("MS", "RRT", 20, 2, []),

    # Missouri — Biennial, 24 total, min 12 traditional
    ("MO", "RRT", 24, 2, []),

    # Montana — Annual, 24 total every 2 years (due at renewal on even-numbered years)
    ("MT", "RRT", 24, 2, []),

    # Nebraska — Biennial, 20 total
    ("NE", "RRT", 20, 2, []),

    # Nevada — Biennial, 20 total, 2 hrs ethics
    ("NV", "RRT", 20, 2, ["ethics"]),

    # New Hampshire — Biennial, 24 total
    ("NH", "RRT", 24, 2, []),

    # New Jersey — Biennial, 30 total, 1 hr infection control, 1 hr patient safety/medical errors, 1 hr ethics
    ("NJ", "RRT", 30, 2, ["infection control", "patient safety", "ethics"]),

    # New Mexico — Biennial, 20 total, 1 hr ethics
    ("NM", "RRT", 20, 2, ["ethics"]),

    # New York — Triennial, 30 total, min 15 traditional
    # Verified: op.nysed.gov — 30 contact hours per 3-year registration period
    ("NY", "RRT", 30, 3, []),

    # North Carolina — Annual, 12 total, min 6 traditional (24 per 2yr cycle)
    ("NC", "RRT", 12, 1, []),

    # North Dakota — Annual, 10 total
    ("ND", "RRT", 10, 1, []),

    # Ohio — Biennial, 20 total, 1 hr Ohio RC law or professional ethics
    # Verified: AARC + Ohio Admin Code 4761-9-02
    ("OH", "RRT", 20, 2, ["Ohio RC law or professional ethics"]),

    # Oklahoma — Biennial, 12 total
    ("OK", "RRT", 12, 2, []),

    # Oregon — Annual, 7 total, 2.5 hrs must be directly related to clinical practice
    ("OR", "RRT", 7, 1, ["clinical practice"]),

    # Pennsylvania — Biennial, 30 total, min 10 traditional, 1 hr medical ethics,
    # 1 hr patient safety, 2 hrs child abuse recognition & reporting
    # Verified: pa.gov — 30 hours per biennial period
    ("PA", "RRT", 30, 2, ["ethics", "patient safety", "child abuse recognition and reporting"]),

    # Rhode Island — Biennial, 12 total, max 6 hrs online, 2 hrs ethics
    ("RI", "RRT", 12, 2, ["ethics"]),

    # South Carolina — Biennial, 30 total
    ("SC", "RRT", 30, 2, []),

    # South Dakota — Biennial, 20 total, 2 hrs patient safety
    ("SD", "RRT", 20, 2, ["patient safety"]),

    # Tennessee — Biennial, 12 per year / 24 per cycle, 1 hr patient safety/yr, 1 hr ethics/yr
    ("TN", "RRT", 24, 2, ["patient safety", "ethics"]),

    # Utah — Biennial, not required for renewal
    ("UT", "RRT", 0, 2, []),

    # Vermont — Biennial, 12 total
    ("VT", "RRT", 12, 2, []),

    # Virginia — Biennial, 20 total
    ("VA", "RRT", 20, 2, []),

    # Washington — Biennial, 30 total, max 10 hrs self-study
    ("WA", "RRT", 30, 2, []),

    # West Virginia — Annual, 20 total every 2 years, max 10 hrs self-study
    ("WV", "RRT", 20, 2, []),

    # Wisconsin — Biennial, not required for renewal
    ("WI", "RRT", 0, 2, []),

    # Wyoming — Annual, 8 total
    ("WY", "RRT", 8, 1, []),
]


def add_state_requirements():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get existing states
    c.execute("SELECT state FROM state_requirements")
    existing = {row[0] for row in c.fetchall()}
    print(f"Existing states in DB: {sorted(existing)}")
    print()

    added = 0
    skipped = 0
    for state, prof, ceus, years, topics in STATE_REQUIREMENTS:
        if state in existing:
            print(f"  ⏭️  {state} already exists, skipping")
            skipped += 1
            continue
        c.execute(
            "INSERT INTO state_requirements (state, profession, required_ceus, cycle_years, mandatory_topics) VALUES (?, ?, ?, ?, ?)",
            (state, prof, ceus, years, json.dumps(topics))
        )
        added += 1
        topic_str = f" [{', '.join(topics)}]" if topics else ""
        print(f"  ✅ Added {state}: {ceus} CEUs / {years}yr{topic_str}")

    conn.commit()

    # Verify
    c.execute("SELECT COUNT(*) FROM state_requirements")
    total = c.fetchone()[0]
    print(f"\n{'='*60}")
    print(f"Total state requirements in DB: {total}")
    print(f"  Added: {added}")
    print(f"  Skipped (already existed): {skipped}")
    print(f"{'='*60}")
    print("\nAll state requirements:")
    print(f"{'State':<6} {'Prof':<6} {'CEUs':<6} {'Cycle':<6} Mandatory Topics")
    print(f"{'-'*60}")
    for row in c.execute(
        "SELECT state, profession, required_ceus, cycle_years, mandatory_topics "
        "FROM state_requirements ORDER BY state"
    ):
        topics = json.loads(row[4]) if row[4] else []
        topic_str = f"[{', '.join(topics)}]" if topics else "—"
        print(f"  {row[0]:<4} {row[1]:<6} {row[2]:<6} {row[3]:<6} {topic_str}")

    conn.close()
    print(f"\n✅ Added {added} new state requirements")


if __name__ == "__main__":
    add_state_requirements()