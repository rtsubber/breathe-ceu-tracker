"""Curated free CEU opportunities for Respiratory Therapists.

Instead of scraping company landing pages, this module maintains a curated list
of actual free CEU courses with direct links to the course (not the homepage).

Sources are verified manually — each link goes directly to a free course or
a page listing free courses with clear access.
"""
from datetime import date
import logging

logger = logging.getLogger(__name__)

# Curated free CEU courses — direct links, not landing pages
# Each entry is verified to be free and AARC-approved (or state-board-accepted)
FREE_CEU_COURSES = [
    # AARC — free for members
    {
        "title": "AARC CRCE Through the Journal — Monthly Quiz",
        "provider": "AARC",
        "credits": 1.0,
        "url": "https://www.aarc.org/education/crce-through-the-journal/",
        "source": "aarc",
        "category": "clinical",
        "description": "Monthly quiz based on Respiratory Care journal. Free for AARC members. Earn 1 CRCE each month — 12 per year.",
        "cost": "Free for AARC members",
    },
    {
        "title": "AARC JournalCast — Monthly Webcast",
        "provider": "AARC",
        "credits": 1.0,
        "url": "https://www.aarc.org/webcasts/",
        "source": "aarc",
        "category": "clinical",
        "description": "Monthly live webcast discussing Editor's Choice papers from Respiratory Care journal. Free for AARC members.",
        "cost": "Free for AARC members",
    },
    {
        "title": "AARC Adult Acute Care Section Webcast",
        "provider": "AARC",
        "credits": 1.0,
        "url": "https://www.aarc.org/webcasts/adult-acute-care-specialty-section-webcast-march-2026/",
        "source": "aarc",
        "category": "clinical",
        "description": "Specialty section webcast on adaptive support ventilation. Free for AARC members.",
        "cost": "Free for AARC members",
    },
    {
        "title": "AARC Leadership & Management Ethics Webcast",
        "provider": "AARC",
        "credits": 1.0,
        "url": "https://www.aarc.org/webcasts/practical-tools-for-navigating-ethical-decisions-leadership-and-management-specialty-section/",
        "source": "aarc",
        "category": "ethics",
        "description": "Ethical lessons for respiratory care leaders. Counts toward ethics requirement. Free for AARC members.",
        "cost": "Free for AARC members",
    },

    # A&T Respiratory Lectures — free CEUs (no membership required)
    {
        "title": "A&T Respiratory Lectures — Free CEU Courses",
        "provider": "A&T Respiratory Lectures",
        "credits": 5.0,
        "url": "https://atrespiratorylectures.com/free-ceus",
        "source": "at_lectures",
        "category": "clinical",
        "description": "5 free AARC-approved CEU credits. No membership required. Create a free account and start immediately.",
        "cost": "Free (account required)",
    },

    # Medline University — free courses (no membership required)
    {
        "title": "Medline University — Hand Hygiene: Glove Use (1.0 CE)",
        "provider": "Medline University",
        "credits": 1.0,
        "url": "https://www.medlineuniversity.com/viewdocument/hand-hygiene-program-glove-use-1",
        "source": "medline",
        "category": "safety",
        "description": "Free 1.0 CE course on hand hygiene and glove use for nurses and clinicians. No cost, no membership.",
        "cost": "Free",
    },
    {
        "title": "Medline University — National Performance Goals 2026",
        "provider": "Medline University",
        "credits": 0.5,
        "url": "https://www.medlineuniversity.com/viewdocument/national-performance-goals-2026-microlearning",
        "source": "medline",
        "category": "clinical",
        "description": "Microlearning course on 2026 national performance goals. Free, no membership required.",
        "cost": "Free",
    },

    # Passy-Muir — free CE courses (trach/ventilator)
    {
        "title": "Passy-Muir — Self-Study CEU Courses",
        "provider": "Passy-Muir",
        "credits": 1.0,
        "url": "https://www.passy-muir.com/ceu",
        "source": "passy_muir",
        "category": "clinical",
        "description": "Free self-study CEU courses on tracheostomy and ventilator management. AARC-approved.",
        "cost": "Free",
    },
    {
        "title": "Passy-Muir — Remote Live In-Service Webinars",
        "provider": "Passy-Muir",
        "credits": 1.0,
        "url": "https://www.passy-muir.com/remote-live-inservices",
        "source": "passy_muir",
        "category": "clinical",
        "description": "Free live webinars on trach and ventilator management. Scheduled sessions, register online.",
        "cost": "Free",
    },

    # Texas — free human trafficking training (required for TX RTs)
    {
        "title": "Texas HHSC — Human Trafficking Training for Healthcare Practitioners",
        "provider": "Texas HHSC",
        "credits": 1.0,
        "url": "https://www.hhs.texas.gov/services/family-safety-resources/texas-human-trafficking-resource-center/health-care-practitioner-human-trafficking-training",
        "source": "tx_hhsc",
        "category": "ethics",
        "description": "Free human trafficking awareness training. Required for Texas RTs — counts as 1 of 2 required ethics hours.",
        "cost": "Free (required for TX)",
    },

    # Vapotherm — free CE courses
    {
        "title": "Vapotherm Academy — High Flow Nasal Cannula CE Courses",
        "provider": "Vapotherm",
        "credits": 1.0,
        "url": "https://www.vapotherm.com/education/",
        "source": "vapotherm",
        "category": "clinical",
        "description": "Free CE courses on high-flow nasal cannula therapy. AARC-approved. Create free account to access.",
        "cost": "Free (account required)",
    },

    # RTConnection — aggregated free CE list
    {
        "title": "RTConnection — Free CEU Resource List",
        "provider": "RTConnection",
        "credits": 0.0,
        "url": "https://rtconnection.org/2026/03/10/free-ceus/",
        "source": "rtconnection",
        "category": "clinical",
        "description": "Curated list of free RT CEU sources from various providers. Updated regularly with new free courses.",
        "cost": "Free",
    },
]


def get_free_courses():
    """Return the curated list of free CEU courses."""
    return [
        {
            "title": c["title"],
            "provider": c["provider"],
            "credits": c["credits"],
            "url": c["url"],
            "source": c["source"],
            "category": c["category"],
            "description": c.get("description", ""),
            "cost": c.get("cost", "Free"),
            "alert_date": date.today().isoformat(),
        }
        for c in FREE_CEU_COURSES
    ]


def store_alerts(db_path, courses):
    """Store curated courses in the free_course_alerts table (replaces old data)."""
    import sqlite3
    import json

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Clear old alerts
    c.execute("DELETE FROM free_course_alerts")

    # Ensure table exists
    c.execute("""CREATE TABLE IF NOT EXISTS free_course_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        course_title TEXT NOT NULL,
        provider TEXT NOT NULL,
        credits REAL DEFAULT 0.0,
        url TEXT,
        source TEXT DEFAULT 'aarc',
        alert_date TEXT NOT NULL,
        sent INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    added = 0
    for course in courses:
        c.execute(
            """INSERT INTO free_course_alerts
               (user_id, course_title, provider, credits, url, source, alert_date)
               VALUES (NULL, ?, ?, ?, ?, ?, ?)""",
            (
                course["title"],
                course["provider"],
                course["credits"],
                course["url"],
                course["source"],
                course["alert_date"],
            ),
        )
        added += 1

    conn.commit()
    conn.close()
    logger.info(f"Stored {added} curated free course alerts")
    return added


if __name__ == "__main__":
    courses = get_free_courses()
    print(f"Found {len(courses)} curated free CEU courses:")
    total_credits = 0
    for c in courses:
        print(f"  [{c['credits']} CEU] {c['provider']}: {c['title'][:60]}")
        print(f"    {c['url']}")
        print(f"    Cost: {c['cost']}")
        total_credits += c["credits"]
    print(f"\nTotal free CEU credits available: {total_credits}")