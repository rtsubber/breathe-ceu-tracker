"""AARC Learning Network Import — Playwright scraper + mock data fallback.

Scrapes completed CE courses from the AARC Learning Network (learn.aarc.org)
using a headless browser. Falls back to realistic mock data when credentials
are unavailable or the AARC site is unreachable.

Usage:
    from aarc_import import AARCImporter
    importer = AARCImporter(email, password)
    courses = await importer.scrape()  # real scrape
    courses = importer.get_mock_courses()  # mock data (sync)
"""
import asyncio
import logging
from dataclasses import dataclass, asdict
from datetime import date
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AARCCourse:
    """A single completed AARC course entry."""
    title: str
    provider: str  # Always "AARC"
    credits: float
    completion_date: str  # ISO format YYYY-MM-DD
    category: str  # clinical/safety/ethics/leadership

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Mock AARC Course Data ─────────────────────────────────────
# 8 realistic AARC courses for demo without real credentials

MOCK_AARC_COURSES: List[AARCCourse] = [
    AARCCourse(
        title="Mechanical Ventilation: Advanced Modes",
        provider="AARC",
        credits=4.0,
        completion_date="2026-01-15",
        category="clinical",
    ),
    AARCCourse(
        title="Neonatal Respiratory Care",
        provider="AARC",
        credits=3.0,
        completion_date="2026-02-20",
        category="clinical",
    ),
    AARCCourse(
        title="Ethics in Respiratory Practice",
        provider="AARC",
        credits=1.0,
        completion_date="2026-03-10",
        category="ethics",
    ),
    AARCCourse(
        title="Pulmonary Function Testing",
        provider="AARC",
        credits=2.0,
        completion_date="2026-03-25",
        category="clinical",
    ),
    AARCCourse(
        title="Airway Management Techniques",
        provider="AARC",
        credits=2.0,
        completion_date="2026-04-12",
        category="clinical",
    ),
    AARCCourse(
        title="Patient Safety and Quality Improvement",
        provider="AARC",
        credits=2.0,
        completion_date="2026-05-01",
        category="safety",
    ),
    AARCCourse(
        title="Leadership in Healthcare",
        provider="AARC",
        credits=1.0,
        completion_date="2026-05-18",
        category="leadership",
    ),
    AARCCourse(
        title="Pediatric Respiratory Disorders",
        provider="AARC",
        credits=3.0,
        completion_date="2026-06-05",
        category="clinical",
    ),
]


class AARCImporter:
    """Scraper for AARC Learning Network completed courses.

    Uses Playwright (headless Chromium) to navigate the AARC Learning Network,
    log in with user credentials, and extract completed course data.

    For the prototype, if credentials are missing or scraping fails,
    call get_mock_courses() to return realistic demo data.
    """

    AARC_LOGIN_URL = "https://learn.aarc.org/login"
    AARC_TRANSCRIPT_URL = "https://learn.aarc.org/my-learning"
    AARC_COMPLETED_URL = "https://learn.aarc.org/my-learning/completed"
    # Fallback URLs — AARC has changed domains before
    FALLBACK_URLS = {
        "login": [
            "https://education.aarc.org/login",
            "https://www.aarc.org/login",
        ],
        "transcript": [
            "https://education.aarc.org/my-learning",
            "https://www.aarc.org/my-courses",
        ],
    }

    def __init__(self, email: Optional[str] = None, password: Optional[str] = None):
        self.email = email
        self.password = password
        self._browser = None
        self._playwright = None

    async def scrape(self) -> List[AARCCourse]:
        """Launch headless browser, log into AARC, scrape completed courses.

        Returns:
            List of AARCCourse objects found in the user's transcript.

        Raises:
            AARCImportError: If login fails, site is unreachable, or layout changed.
        """
        if not self.email or not self.password:
            raise AARCImportError(
                "AARC credentials required (email + password). "
                "Use get_mock_courses() for demo mode."
            )

        from playwright.async_api import async_playwright

        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            page = await self._browser.new_page()

            # Step 1: Navigate to AARC login
            logger.info("Navigating to AARC Learning Network: %s", self.AARC_LOGIN_URL)
            await page.goto(self.AARC_LOGIN_URL, wait_until="networkidle", timeout=30000)

            # Step 2: Fill login form
            logger.info("Attempting login with email: %s", self.email)
            login_ok = await self._attempt_login(page)

            if not login_ok:
                raise AARCImportError(
                    "AARC login failed — check credentials or site layout. "
                    "Falling back to mock data recommended."
                )

            # Step 3: Navigate to completed courses / transcript
            logger.info("Navigating to completed courses page")
            await page.goto(self.AARC_COMPLETED_URL, wait_until="networkidle", timeout=30000)

            # Step 4: Extract course entries
            courses = await self._extract_courses(page)
            logger.info("Extracted %d courses from AARC", len(courses))
            return courses

        except AARCImportError:
            raise
        except Exception as e:
            raise AARCImportError(f"AARC scraping failed: {type(e).__name__}: {e}")
        finally:
            await self._cleanup()

    async def _attempt_login(self, page) -> bool:
        """Try to fill and submit the AARC login form.

        Handles common AARC login layouts. Returns True if login appears successful.
        """
        try:
            # Try common email/password field selectors
            email_selectors = [
                'input[name="email"]',
                'input[name="username"]',
                'input[type="email"]',
                'input[id="email"]',
                'input[id="username"]',
            ]
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[id="password"]',
            ]
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Login")',
                'button:has-text("Sign In")',
                'button:has-text("Log In")',
            ]

            email_input = None
            for sel in email_selectors:
                email_input = await page.query_selector(sel)
                if email_input:
                    break

            password_input = None
            for sel in password_selectors:
                password_input = await page.query_selector(sel)
                if password_input:
                    break

            submit_btn = None
            for sel in submit_selectors:
                submit_btn = await page.query_selector(sel)
                if submit_btn:
                    break

            if not email_input or not password_input or not submit_btn:
                raise AARCImportError(
                    "Could not locate AARC login form fields — site layout may have changed."
                )

            await email_input.fill(self.email)
            await password_input.fill(self.password)
            await submit_btn.click()

            # Wait for navigation (successful login redirects away from /login)
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Check if we're still on the login page (login failed)
            current_url = page.url
            if "/login" in current_url:
                # Check for error messages
                error_el = await page.query_selector(".error, .alert-danger, [role='alert']")
                if error_el:
                    error_text = await error_el.text_content()
                    raise AARCImportError(f"AARC login failed: {error_text}")
                raise AARCImportError("AARC login failed — still on login page after submit")

            logger.info("AARC login successful")
            return True

        except AARCImportError:
            raise
        except Exception as e:
            raise AARCImportError(f"Login attempt failed: {type(e).__name__}: {e}")

    async def _extract_courses(self, page) -> List[AARCCourse]:
        """Extract completed course entries from the transcript page.

        Tries multiple selector patterns since AARC's layout may vary.
        """
        courses = []

        # Wait for course list to render
        try:
            await page.wait_for_selector(".course-item, .course-card, .learning-item, table tr", timeout=15000)
        except Exception:
            logger.warning("No course elements found on transcript page")
            return courses

        # Strategy 1: Look for structured course cards/rows
        # AARC Learning Network typically shows courses in a list or table
        course_elements = await page.query_selector_all(
            ".course-item, .course-card, .learning-item, .completed-course, "
            "table tbody tr, .transcript-item"
        )

        for el in course_elements:
            try:
                course = await self._parse_course_element(el)
                if course:
                    courses.append(course)
            except Exception as e:
                logger.debug("Failed to parse course element: %s", e)
                continue

        # Strategy 2: If no courses found, try extracting from page text
        if not courses:
            logger.info("Structured extraction failed, trying text-based extraction")
            courses = await self._extract_from_text(page)

        return courses

    async def _parse_course_element(self, el) -> Optional[AARCCourse]:
        """Parse a single course DOM element into an AARCCourse."""
        text = await el.text_content()
        if not text or not text.strip():
            return None

        # Try to find structured fields within the element
        title_el = await el.query_selector(".title, .course-title, .name, h3, h4, a")
        credits_el = await el.query_selector(".credits, .ceus, .ceu-count, .credit-hours")
        date_el = await el.query_selector(".date, .completed-date, .completion-date, time")
        category_el = await el.query_selector(".category, .topic, .subject")

        title = (await title_el.text_content()).strip() if title_el else text.strip().split("\n")[0]
        credits_text = (await credits_el.text_content()).strip() if credits_el else ""
        date_text = (await date_el.text_content()).strip() if date_el else ""
        category_text = (await category_el.text_content()).strip().lower() if category_el else "clinical"

        # Parse credits (e.g., "4 CEUs", "4.0 credits", "3 CE")
        credits = self._parse_credits(credits_text)
        if credits == 0.0:
            # Try to find credits in the full text
            credits = self._parse_credits(text)

        # Parse date (e.g., "January 15, 2026", "01/15/2026", "2026-01-15")
        completion_date = self._parse_date(date_text)
        if not completion_date:
            # Try to find date in the full text
            completion_date = self._parse_date(text)

        if not title:
            return None

        # Normalize category
        category = self._normalize_category(category_text)

        return AARCCourse(
            title=title[:500],  # Truncate to DB column size
            provider="AARC",
            credits=credits,
            completion_date=completion_date or date.today().isoformat(),
            category=category,
        )

    async def _extract_from_text(self, page) -> List[AARCCourse]:
        """Fallback: extract courses from page text content."""
        courses = []
        try:
            text = await page.text_content("body") or ""
            lines = [l.strip() for l in text.split("\n") if l.strip()]

            # Look for patterns that indicate course entries
            # AARC courses often have patterns like "Course Title - 4.0 CEUs - 01/15/2026"
            import re
            for line in lines:
                # Match: title + credits + date pattern
                match = re.search(
                    r"(.+?)\s*[-–—]\s*(\d+\.?\d*)\s*(?:CEUs?|CE|credits?)\s*[-–—]\s*(.+)",
                    line,
                    re.IGNORECASE,
                )
                if match:
                    title = match.group(1).strip()
                    credits = float(match.group(2))
                    date_str = self._parse_date(match.group(3))
                    if title and credits > 0:
                        courses.append(AARCCourse(
                            title=title[:500],
                            provider="AARC",
                            credits=credits,
                            completion_date=date_str or date.today().isoformat(),
                            category="clinical",
                        ))
        except Exception as e:
            logger.debug("Text extraction failed: %s", e)

        return courses

    @staticmethod
    def _parse_credits(text: str) -> float:
        """Extract credit count from text like '4.0 CEUs' or '3 credits'."""
        import re
        match = re.search(r"(\d+\.?\d*)\s*(?:CEUs?|CE|credits?|hours?)", text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return 0.0
        return 0.0

    @staticmethod
    def _parse_date(text: str) -> Optional[str]:
        """Parse date from various formats, return ISO YYYY-MM-DD."""
        import re
        from datetime import datetime as dt

        # ISO format: 2026-01-15
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        # US format: 01/15/2026
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if m:
            month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return f"{year}-{month:02d}-{day:02d}"

        # Text format: January 15, 2026
        m = re.search(
            r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            r"\s+(\d{1,2}),?\s+(\d{4})",
            text,
            re.IGNORECASE,
        )
        if m:
            month_name = m.group(1)[:3].lower()
            months = {
                "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
            }
            month = months.get(month_name, 1)
            day = int(m.group(2))
            year = int(m.group(3))
            return f"{year}-{month:02d}-{day:02d}"

        return None

    @staticmethod
    def _normalize_category(text: str) -> str:
        """Normalize category text to known buckets."""
        text = text.lower()
        if "ethic" in text:
            return "ethics"
        if "safety" in text or "quality" in text:
            return "safety"
        if "leader" in text or "management" in text:
            return "leadership"
        # Default
        return "clinical"

    def get_mock_courses(self) -> List[AARCCourse]:
        """Return realistic mock AARC courses for demo/prototype mode.

        Use this when real AARC credentials are unavailable or scraping fails.
        Returns 8 realistic courses totaling 18 CEUs.
        """
        return list(MOCK_AARC_COURSES)

    async def _cleanup(self):
        """Close browser and stop playwright."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass


class AARCImportError(Exception):
    """Raised when AARC import fails (bad credentials, site down, layout changed)."""
    pass


# ─── Convenience functions for sync usage ──────────────────────

def get_mock_aarc_courses() -> List[dict]:
    """Return mock AARC courses as list of dicts (for sync API code)."""
    return [c.to_dict() for c in MOCK_AARC_COURSES]


async def scrape_aarc(email: str, password: str) -> List[dict]:
    """Async convenience function: scrape AARC and return list of dicts.

    Falls back to mock data if scraping fails and use_mock_on_failure=True.
    """
    importer = AARCImporter(email, password)
    courses = await importer.scrape()
    return [c.to_dict() for c in courses]


def scrape_aarc_or_mock(email: Optional[str] = None, password: Optional[str] = None,
                        use_mock_on_failure: bool = True) -> List[dict]:
    """Sync wrapper: try real scrape, fall back to mock on failure.

    Returns list of course dicts.
    """
    if not email or not password:
        logger.info("No AARC credentials provided — using mock data")
        return get_mock_aarc_courses()

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            courses = loop.run_until_complete(scrape_aarc(email, password))
            return courses
        finally:
            loop.close()
    except AARCImportError as e:
        logger.warning("AARC scrape failed: %s — falling back to mock", e)
        if use_mock_on_failure:
            return get_mock_aarc_courses()
        raise
    except Exception as e:
        logger.warning("Unexpected error during AARC scrape: %s — falling back to mock", e)
        if use_mock_on_failure:
            return get_mock_aarc_courses()
        raise


if __name__ == "__main__":
    # Demo: print mock courses
    print("AARC Learning Network Import — Mock Data Demo")
    print("=" * 60)
    courses = get_mock_aarc_courses()
    total_credits = 0
    for c in courses:
        print(f"  {c['title']}")
        print(f"    {c['credits']} CEUs | {c['category']} | {c['completion_date']}")
        total_credits += c["credits"]
    print(f"\nTotal: {len(courses)} courses, {total_credits} CEUs")