"""Scanner for free CEU courses from AARC, NBRC, and other providers.

AARC offers free CEU courses to members. NBRC has free assessment tools.
Other providers: Medbridge free trials, Relias free courses, etc.

In production, this module would scrape AARC/NBRC websites for current free
courses. For now, it returns a curated static list that can be enriched later.
"""
from datetime import date
from typing import Optional

FREE_COURSE_SOURCES = {
    "aarc": {
        "url": "https://www.aarc.org/education/",
        "courses": [
            {
                "title": "AARC Free Webinar Series",
                "provider": "AARC",
                "credits": 1.0,
                "url": "https://www.aarc.org/education/",
            },
            {
                "title": "AARC Patient Safety Series",
                "provider": "AARC",
                "credits": 0.5,
                "url": "https://www.aarc.org/education/",
            },
            {
                "title": "AARC Ventilator Bootcamp",
                "provider": "AARC",
                "credits": 2.0,
                "url": "https://www.aarc.org/education/",
            },
        ],
    },
    "nbrc": {
        "url": "https://www.nbrc.org/",
        "courses": [
            {
                "title": "NBRC Self-Assessment Exam",
                "provider": "NBRC",
                "credits": 0.0,
                "url": "https://www.nbrc.org/",
            },
        ],
    },
    "other": {
        "url": "https://www.medbridge.com/free-trial",
        "courses": [
            {
                "title": "Medbridge Free Trial Course",
                "provider": "Medbridge",
                "credits": 1.0,
                "url": "https://www.medbridge.com/free-trial",
            },
        ],
    },
}


def scan_free_courses(source: Optional[str] = None) -> list[dict]:
    """Return list of free CEU courses available.

    Args:
        source: Optional filter ("aarc", "nbrc", "other"). If None, returns all.

    Returns:
        List of course dicts with: title, provider, credits, url, source
    """
    courses = []
    sources = [source] if source else FREE_COURSE_SOURCES.keys()

    for src in sources:
        data = FREE_COURSE_SOURCES.get(src)
        if not data:
            continue
        for course in data["courses"]:
            courses.append({**course, "source": src})

    return courses


def get_free_courses_by_provider(provider: str) -> list[dict]:
    """Return free courses from a specific provider (case-insensitive)."""
    provider_lower = provider.lower()
    courses = scan_free_courses()
    return [c for c in courses if c["provider"].lower() == provider_lower]


def format_course_for_alert(course: dict) -> dict:
    """Format a course dict for storage as a FreeCourseAlert."""
    return {
        "course_title": course["title"],
        "provider": course["provider"],
        "credits": course.get("credits", 0.0),
        "url": course.get("url"),
        "source": course.get("source", "other"),
        "alert_date": date.today().isoformat(),
    }