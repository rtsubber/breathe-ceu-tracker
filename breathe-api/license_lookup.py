"""TMB License Lookup — scrape Texas Medical Board public license search.

Searches the TMB public database at https://profile.tmb.state.tx.us/Search.aspx
for Respiratory Care Practitioner (RCP) licenses and returns structured data.

Flow:
  1. GET Search.aspx → notice/accept page with ASPX hidden fields
  2. POST accept → get actual search form (with session window ID)
  3. POST search criteria → get results page (SearchResults.aspx)
  4. (Optional) Click result → get detail page with issue/expiry dates
"""
import re
import logging
import time
from typing import Optional
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

TMB_BASE = "https://profile.tmb.state.tx.us"
TMB_SEARCH_URL = f"{TMB_BASE}/Search.aspx"
TMB_NOTICE_URL = f"{TMB_BASE}/SearchNotice.aspx"
TMB_RESULTS_URL = f"{TMB_BASE}/SearchResults.aspx"

# RCP = Respiratory Care Practitioner (covers RRTs and CRTs in Texas)
RCP_LICENSE_TYPE = "RCP"

# Cache for lookups (simple in-memory, per-process)
_cache: dict[str, dict] = {}
_CACHE_TTL = 3600  # 1 hour


class TMBSession:
    """Manages a session with the TMB search portal (handles ASPX form flow)."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; Breathe/1.0; +https://breathe.app)"
        })
        self.window_id: Optional[str] = None
        self._search_page_url: Optional[str] = None
        self._viewstate: Optional[str] = None
        self._eventvalidation: Optional[str] = None
        self._viewstategenerator: Optional[str] = None

    def _init_session(self) -> None:
        """Step 1+2: Accept the usage terms and get the search form."""
        # Step 1: GET the notice page
        r1 = self.session.get(TMB_SEARCH_URL, timeout=15)
        if r1.status_code != 200:
            raise RuntimeError(f"TMB notice page returned {r1.status_code}")

        soup1 = BeautifulSoup(r1.text, "html.parser")
        vs = soup1.find("input", {"name": "__VIEWSTATE"})
        ev = soup1.find("input", {"name": "__EVENTVALIDATION"})
        vsg = soup1.find("input", {"name": "__VIEWSTATEGENERATOR"})

        if not vs or not ev:
            raise RuntimeError("Could not find ASPX hidden fields on TMB notice page")

        # Step 2: POST accept
        data = {
            "__VIEWSTATE": vs.get("value", ""),
            "__VIEWSTATEGENERATOR": vsg.get("value", "") if vsg else "",
            "__EVENTVALIDATION": ev.get("value", ""),
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "ctl00$hfWindowID": "",
            "ctl00$BodyContent$btnAccept": "I Accept the Usage Terms",
        }
        r2 = self.session.post(TMB_NOTICE_URL, data=data, timeout=15, allow_redirects=True)
        if r2.status_code != 200:
            raise RuntimeError(f"TMB accept POST returned {r2.status_code}")

        # Parse the search page
        soup2 = BeautifulSoup(r2.text, "html.parser")
        self._viewstate = soup2.find("input", {"name": "__VIEWSTATE"})["value"]
        self._eventvalidation = soup2.find("input", {"name": "__EVENTVALIDATION"})["value"]
        self._viewstategenerator = soup2.find("input", {"name": "__VIEWSTATEGENERATOR"})["value"]
        wid_input = soup2.find("input", {"name": "ctl00$hfWindowID"})
        self.window_id = wid_input["value"] if wid_input else ""
        self._search_page_url = r2.url  # e.g. Search.aspx?{window_id}

        logger.debug(f"TMB session initialized, window_id={self.window_id}")

    def _ensure_session(self) -> None:
        """Initialize session if not already done."""
        if self.window_id is None:
            self._init_session()

    def search(
        self,
        last_name: str = "",
        first_name: str = "",
        license_number: str = "",
        license_type: str = RCP_LICENSE_TYPE,
        active_only: bool = False,
    ) -> str:
        """Submit a search and return the results HTML.

        Returns the HTML of the SearchResults.aspx page.
        """
        self._ensure_session()

        search_url = self._search_page_url or f"{TMB_SEARCH_URL}?{self.window_id}"

        data = {
            "__VIEWSTATE": self._viewstate,
            "__VIEWSTATEGENERATOR": self._viewstategenerator,
            "__EVENTVALIDATION": self._eventvalidation,
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "ctl00$hfWindowID": self.window_id,
            "ctl00$BodyContent$tbLastName": last_name,
            "ctl00$BodyContent$tbFirstName": first_name,
            "ctl00$BodyContent$tbLicense": license_number,
            "ctl00$BodyContent$ddLicenseType": license_type,
            "ctl00$BodyContent$cbActiveLicensesOnly": "on" if active_only else "",
            "ctl00$BodyContent$tbCity": "",
            "ctl00$BodyContent$tbZIP": "",
            "ctl00$BodyContent$tbBADate": "",
            "ctl00$BodyContent$tbBADateRangeEnd": "",
            "ctl00$BodyContent$ddBACategory": "ALL",
            "ctl00$BodyContent$btnSearch": "Search",
        }

        r = self.session.post(search_url, data=data, timeout=20, allow_redirects=True)
        if r.status_code != 200:
            raise RuntimeError(f"TMB search POST returned {r.status_code}")

        # Update hidden fields from the results page for potential follow-up requests
        soup = BeautifulSoup(r.text, "html.parser")
        vs = soup.find("input", {"name": "__VIEWSTATE"})
        ev = soup.find("input", {"name": "__EVENTVALIDATION"})
        vsg = soup.find("input", {"name": "__VIEWSTATEGENERATOR"})
        if vs:
            self._viewstate = vs["value"]
        if ev:
            self._eventvalidation = ev["value"]
        if vsg:
            self._viewstategenerator = vsg["value"]

        return r.text

    def get_detail(self, results_html: str, row_index: int = 0) -> Optional[str]:
        """Click on a search result row and return the detail page HTML.

        row_index is 0-based (first result = 0).
        """
        soup = BeautifulSoup(results_html, "html.parser")
        table = soup.find("table", {"id": "BodyContent_gvSearchResults"})
        if not table:
            return None

        rows = table.find_all("tr")
        if len(rows) <= row_index + 1:
            return None

        target_row = rows[row_index + 1]  # +1 to skip header
        name_link = target_row.find("a", onclick=True)
        if not name_link:
            return None

        # Extract __doPostBack target from onclick
        onclick = name_link.get("onclick", "")
        # Pattern: __doPostBack('ctl00$BodyContent$gvSearchResults$ctl02$ctl00','')
        match = re.search(r"__doPostBack\('([^']+)','([^']*)'\)", onclick)
        if not match:
            # Try href pattern: javascript:__doPostBack(...)
            href = name_link.get("href", "")
            match = re.search(r"__doPostBack\('([^']+)','([^']*)'\)", href)
        if not match:
            return None

        event_target = match.group(1)
        event_arg = match.group(2)

        # The results page URL includes the window ID
        results_url = f"{TMB_RESULTS_URL}?{self.window_id}"

        data = {
            "__VIEWSTATE": self._viewstate,
            "__VIEWSTATEGENERATOR": self._viewstategenerator,
            "__EVENTVALIDATION": self._eventvalidation,
            "__EVENTTARGET": event_target,
            "__EVENTARGUMENT": event_arg,
            "__LASTFOCUS": "",
            "ctl00$hfWindowID": self.window_id,
        }

        r = self.session.post(results_url, data=data, timeout=20, allow_redirects=True)
        if r.status_code != 200:
            return None

        return r.text


# ─── Parsing ──────────────────────────────────────────────────

def parse_search_results(html: str) -> list[dict]:
    """Parse the TMB SearchResults.aspx HTML into a list of match dicts.

    Each match dict contains:
      - name: Licensee name as registered (LAST, FIRST M)
      - license_number: e.g. RCP00075612
      - license_type: e.g. "Respiratory Care Practitioner Certificate"
      - address: Street address (may be empty)
      - city: City (may be empty)
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "BodyContent_gvSearchResults"})
    if not table:
        # No results table → no matches
        return []

    results = []
    rows = table.find_all("tr")

    for row in rows[1:]:  # Skip header
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        name = cells[0].get_text(strip=True)
        license_number = cells[1].get_text(strip=True)
        license_type = cells[2].get_text(strip=True)
        address = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        city = cells[4].get_text(strip=True) if len(cells) > 4 else ""

        # Normalize name from "LAST, FIRST M" to "First Last" format
        display_name = _normalize_name(name)

        results.append({
            "name": display_name,
            "tmb_name": name,  # Keep original TMB format
            "license_number": license_number,
            "license_type": _short_license_type(license_type),
            "license_type_full": license_type,
            "address": address,
            "city": city,
            "status": None,  # Not available in search results
            "issue_date": None,
            "expiry_date": None,
        })

    return results


def parse_detail_page(html: str) -> dict:
    """Parse the TMB licensee detail page HTML.

    Extracts: name, license number, license type, status, issue date, expiry date.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)

    result = {
        "name": None,
        "tmb_name": None,
        "license_number": None,
        "license_type": None,
        "license_type_full": None,
        "status": None,
        "issue_date": None,
        "expiry_date": None,
    }

    # Extract from the info tables
    tables = soup.find_all("table")

    # Table 1 typically has NAME, LICENSE, INFORMATION CURRENT AS OF, CURRENT STATUS
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            row_text = row.get_text(separator=" ", strip=True)
            # Name
            if "NAME:" in row_text and not result["tmb_name"]:
                match = re.match(r"NAME:\s*(.+)", row_text)
                if match:
                    result["tmb_name"] = match.group(1).strip()
                    result["name"] = _normalize_name(result["tmb_name"])

            # License number (from info table)
            if "LICENSE:" in row_text and not result["license_number"]:
                match = re.match(r"LICENSE:\s*(\S+)", row_text)
                if match:
                    result["license_number"] = match.group(1).strip()

            # Current Status
            if "CURRENT STATUS:" in row_text:
                match = re.match(r"CURRENT STATUS:\s*(\w+)", row_text)
                if match:
                    result["status"] = match.group(1).strip().upper()

    # Table 2 has detailed info: License Number + Type, Issuance Date, Expiration Date
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            row_text = row.get_text(separator=" ", strip=True)

            # License Number + Type: "License Number: RCP00075612 Respiratory Care..."
            if "License Number:" in row_text and not result["license_type_full"]:
                match = re.match(
                    r"License Number:\s*(\S+)\s+(.+)", row_text
                )
                if match:
                    if not result["license_number"]:
                        result["license_number"] = match.group(1).strip()
                    result["license_type_full"] = match.group(2).strip()
                    result["license_type"] = _short_license_type(result["license_type_full"])

            # Issuance Date
            if "Issuance Date:" in row_text and not result["issue_date"]:
                match = re.search(r"Issuance Date:\s*(\d{2}/\d{2}/\d{4})", row_text)
                if match:
                    result["issue_date"] = _normalize_date(match.group(1))

            # Expiration Date
            if "Expiration Date:" in row_text and not result["expiry_date"]:
                match = re.search(r"Expiration Date:\s*(\d{2}/\d{2}/\d{4})", row_text)
                if match:
                    result["expiry_date"] = _normalize_date(match.group(1))

            # Current Status (from detail table)
            if "Current Status:" in row_text and not result["status"]:
                match = re.match(r"Current Status:\s*(\w+)", row_text)
                if match:
                    result["status"] = match.group(1).strip().upper()

    # Fallback: look at the license history table (Table 16)
    # Pattern: "Issue Date: MM/DD/YYYY  Type: LICENSE_NUM Type Name"
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            for cell in cells:
                cell_text = cell.get_text(separator=" ", strip=True)
                if "Issue Date:" in cell_text and not result["issue_date"]:
                    match = re.search(r"Issue Date:\s*(\d{2}/\d{2}/\d{4})", cell_text)
                    if match:
                        result["issue_date"] = _normalize_date(match.group(1))
                if "Type:" in cell_text and not result["license_type_full"]:
                    match = re.search(r"Type:\s*(\S+)\s*(.*)", cell_text)
                    if match:
                        result["license_type_full"] = match.group(2).strip() or match.group(1).strip()
                        result["license_type"] = _short_license_type(result["license_type_full"])

    return result


# ─── Helpers ──────────────────────────────────────────────────

def _normalize_name(tmb_name: str) -> str:
    """Convert various name formats to 'First [Suffix] Last' (title case).

    Handles:
      - TMB: 'LAST, FIRST M' → 'First M Last'
      - Indiana PLA detail: 'FIRST LAST, jr' → 'First Jr Last'
      - Indiana PLA search: 'LAST, FIRST, jr' → 'First Jr Last'
    """
    if not tmb_name:
        return ""
    parts = [p.strip() for p in tmb_name.split(",") if p.strip()]
    if len(parts) >= 3:
        # Format: LAST, FIRST, suffix (Indiana search results)
        last = parts[0].title()
        first = parts[1].title()
        suffix = parts[2].title()
        return f"{first} {suffix} {last}".strip()
    if len(parts) == 2:
        first_part = parts[0]
        second_part = parts[1]
        # Check if second part is a suffix (jr, sr, ii, iii, etc.)
        suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
        if second_part.lower().rstrip(".") in suffixes:
            # Format: FIRST LAST, suffix (Indiana detail page)
            name_words = first_part.split()
            if len(name_words) >= 2:
                first = " ".join(name_words[:-1]).title()
                last = name_words[-1].title()
                suffix = second_part.title()
                return f"{first} {suffix} {last}".strip()
        # Format: LAST, FIRST M (TMB)
        last = first_part.title()
        first = second_part.title()
        return f"{first} {last}".strip()
    return tmb_name.title()


def _short_license_type(full_type: str) -> str:
    """Extract short license type code from full description.

    e.g. "Respiratory Care Practitioner Certificate" → "RCP"
         "Medical Radiological Technologist" → "MRT"
    """
    if not full_type:
        return ""
    full_lower = full_type.lower()
    if "respiratory care" in full_lower:
        return "RCP"
    if "medical radiological" in full_lower:
        return "MRT"
    if "non-certified radiologic" in full_lower:
        return "NCR"
    if "medical physicist" in full_lower:
        return "MP"
    if "perfusionist" in full_lower:
        return "PF"
    if "physician assistant" in full_lower:
        return "PA"
    if "acupuncture" in full_lower:
        return "AC"
    if "acudetox" in full_lower:
        return "AD"
    if "surgical assistant" in full_lower:
        return "SA"
    if "physician" in full_lower:
        return "PHY"
    # If we can't map, return the first word
    return full_type.split()[0].upper() if full_type else ""


def _normalize_date(date_str: str) -> str:
    """Convert MM/DD/YYYY to YYYY-MM-DD (ISO format)."""
    try:
        dt = datetime.strptime(date_str, "%m/%d/%Y")
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return date_str  # Return as-is if parsing fails


# ─── Public API ───────────────────────────────────────────────

def _cache_key(action: str, **kwargs) -> str:
    return f"{action}:{':'.join(f'{k}={v}' for k, v in sorted(kwargs.items()) if v)}"


def lookup_license_by_name(
    first_name: str,
    last_name: str,
    license_type: str = RCP_LICENSE_TYPE,
    fetch_details: bool = True,
) -> list[dict]:
    """Search TMB by licensee name. Returns list of matches.

    If fetch_details=True (default), fetches the detail page for each result
    to get status, issue date, and expiry date. This is slower but complete.
    If fetch_details=False, returns basic info from the results list only.
    """
    cache_key = _cache_key("name", first=first_name, last=last_name, type=license_type, details=fetch_details)

    # Check cache
    if cache_key in _cache:
        entry = _cache[cache_key]
        if time.time() - entry["ts"] < _CACHE_TTL:
            return entry["data"]

    try:
        tmb = TMBSession()
        html = tmb.search(
            last_name=last_name,
            first_name=first_name,
            license_type=license_type,
        )
        results = parse_search_results(html)

        if fetch_details and results:
            # Fetch detail page for each result (limit to first 10 to avoid abuse)
            enriched = []
            for i, result in enumerate(results[:10]):
                try:
                    detail_html = tmb.get_detail(html, row_index=i)
                    if detail_html:
                        detail = parse_detail_page(detail_html)
                        # Merge: detail page has more complete info
                        result["status"] = detail.get("status") or result.get("status")
                        result["issue_date"] = detail.get("issue_date")
                        result["expiry_date"] = detail.get("expiry_date")
                        # Use detail page name if available (more complete)
                        if detail.get("tmb_name"):
                            result["tmb_name"] = detail["tmb_name"]
                            result["name"] = detail.get("name") or result["name"]
                        if detail.get("license_type_full"):
                            result["license_type_full"] = detail["license_type_full"]
                            result["license_type"] = detail.get("license_type") or result["license_type"]
                    enriched.append(result)
                except Exception as e:
                    logger.warning(f"Failed to fetch detail for result {i}: {e}")
                    enriched.append(result)  # Keep basic info
            results = enriched

    except Exception as e:
        logger.error(f"TMB lookup by name failed: {e}")
        return []

    # Cache the result
    _cache[cache_key] = {"ts": time.time(), "data": results}
    return results


def lookup_license_by_number(
    license_number: str,
    license_type: str = RCP_LICENSE_TYPE,
    fetch_details: bool = True,
) -> Optional[dict]:
    """Search TMB by license number. Returns single match or None.

    If fetch_details=True (default), fetches the detail page for complete info.
    """
    cache_key = _cache_key("number", num=license_number, type=license_type, details=fetch_details)

    # Check cache
    if cache_key in _cache:
        entry = _cache[cache_key]
        if time.time() - entry["ts"] < _CACHE_TTL:
            return entry["data"]

    try:
        tmb = TMBSession()
        html = tmb.search(
            license_number=license_number,
            license_type=license_type,
        )
        results = parse_search_results(html)

        if not results:
            _cache[cache_key] = {"ts": time.time(), "data": None}
            return None

        # Take the first match
        result = results[0]

        if fetch_details:
            try:
                detail_html = tmb.get_detail(html, row_index=0)
                if detail_html:
                    detail = parse_detail_page(detail_html)
                    result["status"] = detail.get("status") or result.get("status")
                    result["issue_date"] = detail.get("issue_date")
                    result["expiry_date"] = detail.get("expiry_date")
                    if detail.get("tmb_name"):
                        result["tmb_name"] = detail["tmb_name"]
                        result["name"] = detail.get("name") or result["name"]
                    if detail.get("license_type_full"):
                        result["license_type_full"] = detail["license_type_full"]
                        result["license_type"] = detail.get("license_type") or result["license_type"]
            except Exception as e:
                logger.warning(f"Failed to fetch detail for license {license_number}: {e}")

    except Exception as e:
        logger.error(f"TMB lookup by number failed: {e}")
        return None

    # Cache the result
    _cache[cache_key] = {"ts": time.time(), "data": result}
    return result


def lookup_license(
    first_name: str = "",
    last_name: str = "",
    license_number: str = "",
    license_type: str = RCP_LICENSE_TYPE,
) -> dict:
    """General-purpose lookup. Returns dict with 'results' list and 'error' if any.

    Searches by license number if provided, otherwise by name.
    """
    if license_number:
        result = lookup_license_by_number(license_number, license_type)
        return {
            "results": [result] if result else [],
            "count": 1 if result else 0,
            "error": None,
        }
    elif first_name or last_name:
        results = lookup_license_by_name(first_name, last_name, license_type)
        return {
            "results": results,
            "count": len(results),
            "error": None,
        }
    else:
        return {
            "results": [],
            "count": 0,
            "error": "Provide either name (first+last) or license_number",
        }


# ─── Indiana PLA License Lookup ─────────────────────────────────
#
# Indiana Professional Licensing Agency (PLA)
# Search URL: https://mylicense.in.gov/EVerification/Search.aspx
# Results URL: https://mylicense.in.gov/EVerification/SearchResults.aspx
# Details URL: https://mylicense.in.gov/EVerification/Details.aspx?result=<UUID>
#
# Flow:
#   1. GET Search.aspx → search form with ASPX hidden fields
#   2. POST search criteria → SearchResults.aspx (list of names with detail links)
#   3. GET Details.aspx?result=<UUID> → full license info (name, license #, status, dates)

IN_PLA_BASE = "https://mylicense.in.gov/EVerification"
IN_PLA_SEARCH_URL = f"{IN_PLA_BASE}/Search.aspx"
IN_PLA_RESULTS_URL = f"{IN_PLA_BASE}/SearchResults.aspx"

# Indiana PLA profession name for Respiratory Care
IN_PLA_PROFESSION = "Respiratory Care Committee"


class IndianaPLASession:
    """Manages a session with the Indiana PLA search portal (ASPX form flow)."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; Breathe/1.0; +https://breathe.app)"
        })
        self._viewstate: Optional[str] = None
        self._eventvalidation: Optional[str] = None
        self._viewstategenerator: Optional[str] = None

    def _init_session(self) -> None:
        """GET the search page to capture ASPX hidden fields."""
        r = self.session.get(IN_PLA_SEARCH_URL, timeout=15)
        if r.status_code != 200:
            raise RuntimeError(f"Indiana PLA search page returned {r.status_code}")

        soup = BeautifulSoup(r.text, "html.parser")
        vs = soup.find("input", {"name": "__VIEWSTATE"})
        ev = soup.find("input", {"name": "__EVENTVALIDATION"})
        vsg = soup.find("input", {"name": "__VIEWSTATEGENERATOR"})

        if not vs or not ev:
            raise RuntimeError("Could not find ASPX hidden fields on Indiana PLA search page")

        self._viewstate = vs.get("value", "")
        self._eventvalidation = ev.get("value", "")
        self._viewstategenerator = vsg.get("value", "")
        logger.debug("Indiana PLA session initialized")

    def _ensure_session(self) -> None:
        if self._viewstate is None:
            self._init_session()

    def search(
        self,
        last_name: str = "",
        first_name: str = "",
        license_number: str = "",
        profession: str = IN_PLA_PROFESSION,
    ) -> str:
        """Submit a search and return the results HTML (SearchResults.aspx).

        Returns the HTML of the search results page.
        """
        self._ensure_session()

        data = {
            "__VIEWSTATE": self._viewstate,
            "__VIEWSTATEGENERATOR": self._viewstategenerator,
            "__EVENTVALIDATION": self._eventvalidation,
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "t_web_lookup__profession_name": profession,
            "t_web_lookup__first_name": first_name,
            "t_web_lookup__last_name": last_name,
            "t_web_lookup__license_type_name": "",
            "t_web_lookup__license_no": license_number,
            "t_web_lookup__addr_city": "",
            "t_web_lookup__addr_state": "",
            "t_web_lookup__addr_county": "",
            "t_web_lookup__addr_zipcode": "",
            "t_web_lookup__license_status_name": "",
            "t_web_lookup__attribute_type_name": "",
            "t_web_lookup__doing_business_as": "",
            "sch_button": "Search",
        }

        r = self.session.post(
            IN_PLA_SEARCH_URL, data=data, timeout=20, allow_redirects=True
        )
        if r.status_code != 200:
            raise RuntimeError(f"Indiana PLA search POST returned {r.status_code}")

        # Update hidden fields from the results page
        soup = BeautifulSoup(r.text, "html.parser")
        vs = soup.find("input", {"name": "__VIEWSTATE"})
        ev = soup.find("input", {"name": "__EVENTVALIDATION"})
        vsg = soup.find("input", {"name": "__VIEWSTATEGENERATOR"})
        if vs:
            self._viewstate = vs["value"]
        if ev:
            self._eventvalidation = ev["value"]
        if vsg:
            self._viewstategenerator = vsg["value"]

        return r.text

    def get_detail(self, results_html: str) -> Optional[str]:
        """Follow the first Details.aspx link from the results page and return detail HTML."""
        soup = BeautifulSoup(results_html, "html.parser")
        table = soup.find("table", {"id": "datagrid_results"})
        if not table:
            return None

        # Find the link to Details.aspx (skip javascript:__doPostBack links)
        detail_link = None
        for link in table.find_all("a", href=True):
            href = link.get("href", "")
            if "Details.aspx" in href:
                detail_link = href
                break

        if not detail_link:
            return None

        detail_url = f"{IN_PLA_BASE}/{detail_link}"
        r = self.session.get(detail_url, timeout=15)
        if r.status_code != 200:
            return None

        return r.text


# ─── Indiana Parsing ───────────────────────────────────────────

def parse_indiana_search_results(html: str) -> list[dict]:
    """Parse the Indiana PLA SearchResults.aspx HTML into a list of match dicts.

    The search results page only shows name links — license details are on the
    detail page. This returns a list with name and detail_href for each result.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "datagrid_results"})
    if not table:
        return []

    results = []
    seen_hrefs = set()
    for link in table.find_all("a", href=True):
        href = link.get("href", "")
        if "Details.aspx" not in href or href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        name_raw = link.get_text(strip=True)
        display_name = _normalize_name(name_raw)

        results.append({
            "name": display_name,
            "pla_name": name_raw,
            "license_number": None,  # Only on detail page
            "license_type": None,
            "status": None,
            "issue_date": None,
            "expiry_date": None,
            "detail_href": href,
        })

    return results


def parse_indiana_detail_page(html: str) -> dict:
    """Parse the Indiana PLA licensee detail page HTML.

    Extracts: name, license number, license type, status, issue date, expiry date.
    """
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "name": None,
        "pla_name": None,
        "license_number": None,
        "license_type": None,
        "license_type_full": None,
        "status": None,
        "issue_date": None,
        "expiry_date": None,
        "city": None,
        "state": None,
    }

    # Find all label spans (id contains "label") and extract label→value pairs
    labels = soup.find_all("span", {"id": True})
    for label in labels:
        lid = label.get("id", "")
        if "label" not in lid.lower():
            continue
        if any(x in lid for x in ("pagetitle", "pinfo", "addrinfo")):
            continue

        label_text = label.get_text(strip=True).rstrip(":")
        parent_td = label.find_parent("td")
        if not parent_td:
            continue
        next_td = parent_td.find_next_sibling("td")
        if not next_td:
            continue
        value = next_td.get_text(strip=True)

        if not value:
            continue

        key = label_text.lower()

        if key == "name":
            result["pla_name"] = value
            result["name"] = _normalize_name(value)

        elif key == "lic #":
            result["license_number"] = value

        elif key == "profession":
            # e.g. "Respiratory Care Committee"
            pass  # Not needed for our purposes

        elif key == "type":
            result["license_type_full"] = value
            result["license_type"] = _indiana_short_license_type(value)

        elif key == "status":
            result["status"] = value.upper()

        elif key == "issued":
            result["issue_date"] = _normalize_date(value)

        elif key == "expiration":
            result["expiry_date"] = _normalize_date(value)

        elif key.startswith("city"):
            # "City/State/Zip: beeville TX  78102"
            parts = value.split()
            if len(parts) >= 2:
                result["city"] = parts[0]
                result["state"] = parts[1] if len(parts) > 1 else None

    return result


def _indiana_short_license_type(full_type: str) -> str:
    """Map Indiana license type descriptions to short codes.

    e.g. "Respiratory Care Practitioner" → "RCP"
    """
    if not full_type:
        return ""
    full_lower = full_type.lower()
    if "respiratory care" in full_lower:
        return "RCP"
    # Fallback: first word uppercased
    return full_type.split()[0].upper() if full_type else ""


# ─── Indiana Public API ───────────────────────────────────────

def lookup_indiana_license(
    first_name: str = "",
    last_name: str = "",
    license_number: str = "",
    fetch_details: bool = True,
) -> list[dict]:
    """Search Indiana PLA for respiratory therapist licenses.

    Searches by license number if provided, otherwise by name.
    Returns a list of match dicts with license details.

    Set fetch_details=False to return only the search results list
    (without license number, status, dates — those are on the detail page).
    """
    cache_key = _cache_key(
        "in_name",
        first=first_name,
        last=last_name,
        num=license_number,
        details=fetch_details,
    )

    # Check cache
    if cache_key in _cache:
        entry = _cache[cache_key]
        if time.time() - entry["ts"] < _CACHE_TTL:
            return entry["data"]

    try:
        pla = IndianaPLASession()
        html = pla.search(
            last_name=last_name,
            first_name=first_name,
            license_number=license_number,
        )
        results = parse_indiana_search_results(html)

        if fetch_details and results:
            enriched = []
            for result in results:
                try:
                    detail_html = pla.get_detail(html)
                    if detail_html:
                        detail = parse_indiana_detail_page(detail_html)
                        # Merge detail info into result
                        result["name"] = detail.get("name") or result["name"]
                        result["pla_name"] = detail.get("pla_name") or result.get("pla_name")
                        result["license_number"] = detail.get("license_number")
                        result["license_type"] = detail.get("license_type")
                        result["license_type_full"] = detail.get("license_type_full")
                        result["status"] = detail.get("status")
                        result["issue_date"] = detail.get("issue_date")
                        result["expiry_date"] = detail.get("expiry_date")
                        result["city"] = detail.get("city")
                        result["state"] = detail.get("state")
                    enriched.append(result)
                except Exception as e:
                    logger.warning(f"Failed to fetch Indiana detail: {e}")
                    enriched.append(result)
            results = enriched

    except Exception as e:
        logger.error(f"Indiana PLA lookup failed: {e}")
        return []

    # Cache the result
    _cache[cache_key] = {"ts": time.time(), "data": results}
    return results


# ─── Florida MQA License Lookup ──────────────────────────────────
#
# Florida Department of Health MQA (Division of Medical Quality Assurance)
# Search URL: https://mqa-internet.doh.state.fl.us/MQASearchServices/HealthCareProviders
# Detail URL: https://mqa-internet.doh.state.fl.us/MQASearchServices/HealthcareProviders/LicenseVerification?LicInd=<ID>&Procde=<CODE>
#
# Flow:
#   1. GET search page → captures __RequestVerificationToken (CSRF)
#   2. POST search criteria → either:
#      a) Redirects to LicenseVerification detail page (single match), or
#      b) Returns results table with links to detail pages (multiple matches), or
#      c) Returns "No records found" (no matches)
#   3. GET detail page → <dl> with <dt>/<dd> pairs for license info

FL_MQA_BASE = "https://mqa-internet.doh.state.fl.us"
FL_MQA_SEARCH_URL = f"{FL_MQA_BASE}/MQASearchServices/HealthCareProviders"

# Board of Respiratory Care (dropdown value)
FL_MQA_BOARD_RESPIRATORY = "57"

# Profession codes for Respiratory Therapists
FL_MQA_PROFESSION_RRT = "5701"   # Registered Respiratory Therapist
FL_MQA_PROFESSION_CRT = "5702"   # Certified Respiratory Therapist
FL_MQA_PROFESSION_RCP_EXAM = "5703"  # Respiratory Care Practitioner by Exam
FL_MQA_PROFESSION_RCP_CC = "5704"   # Respiratory Care Practitioner Critical Care
FL_MQA_PROFESSION_RCP_NCC = "5705"  # Respiratory Care Practitioner Non-Critical Care


class FloridaMQASession:
    """Manages a session with the Florida MQA search portal.

    Unlike TMB (ASP.NET) and Indiana PLA (ASP.NET), the FL MQA site uses
    a plain HTML POST form with a __RequestVerificationToken (CSRF token).
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; Breathe/1.0; +https://breathe.app)"
        })
        self._token: Optional[str] = None

    def _init_session(self) -> None:
        """GET the search page to capture the CSRF token."""
        r = self.session.get(FL_MQA_SEARCH_URL, timeout=15)
        if r.status_code != 200:
            raise RuntimeError(f"Florida MQA search page returned {r.status_code}")

        soup = BeautifulSoup(r.text, "html.parser")
        token_input = soup.find("input", {"name": "__RequestVerificationToken"})
        if not token_input:
            raise RuntimeError("Could not find __RequestVerificationToken on FL MQA search page")

        self._token = token_input.get("value", "")
        logger.debug("Florida MQA session initialized")

    def _ensure_session(self) -> None:
        if self._token is None:
            self._init_session()

    def search(
        self,
        last_name: str = "",
        first_name: str = "",
        license_number: str = "",
        board: str = FL_MQA_BOARD_RESPIRATORY,
    ) -> requests.Response:
        """Submit a search and return the response.

        Returns the requests.Response object. The response URL tells us:
        - If redirected to LicenseVerification → single result (detail page)
        - If stayed on search page → either results table or "No records found"
        """
        self._ensure_session()

        data = {
            "__RequestVerificationToken": self._token,
            "SearchDto.Board": board,
            "SearchDto.Profession": "",
            "SearchDto.LicenseNumber": license_number,
            "SearchDto.BusinessName": "",
            "SearchDto.LastName": last_name,
            "SearchDto.FirstName": first_name,
            "SearchDto.City": "",
            "SearchDto.County": "",
            "SearchDto.ZipCode": "",
            "SearchDto.LicenseStatus": "ALL",
        }

        r = self.session.post(
            FL_MQA_SEARCH_URL, data=data, timeout=20, allow_redirects=True
        )
        if r.status_code != 200:
            raise RuntimeError(f"Florida MQA search POST returned {r.status_code}")

        return r

    def get_detail(self, detail_url: str) -> Optional[str]:
        """GET a detail page by URL and return its HTML."""
        if detail_url.startswith("/"):
            detail_url = f"{FL_MQA_BASE}{detail_url}"

        r = self.session.get(detail_url, timeout=15)
        if r.status_code != 200:
            return None
        return r.text


# ─── Florida Parsing ───────────────────────────────────────────

def parse_florida_search_results(html: str) -> list[dict]:
    """Parse the FL MQA search results table into a list of match dicts.

    When there are multiple results, the page stays on the search URL and
    shows a table with columns: License, Name, Profession, City, License Status.
    Each license number is a link to the detail page.
    """
    soup = BeautifulSoup(html, "html.parser")

    # The results table has classes: table-striped, table-condensed, table-hover
    # Find the table that contains license links
    results_table = None
    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if header_row:
            headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
            if "License" in headers and "Name" in headers:
                results_table = table
                break

    if not results_table:
        return []

    results = []
    rows = results_table.find_all("tr")

    for row in rows[1:]:  # Skip header
        cells = row.find_all("td")
        if len(cells) < 5:
            continue

        # Cell 0: License number (link to detail page)
        license_link = cells[0].find("a", href=True)
        license_number = cells[0].get_text(strip=True)
        detail_href = license_link.get("href", "") if license_link else ""

        # Cell 1: Name (format: "LAST, FIRST MIDDLE")
        name_raw = cells[1].get_text(strip=True)
        display_name = _normalize_name(name_raw)

        # Cell 2: Profession
        profession = cells[2].get_text(strip=True)

        # Cell 3: City
        city = cells[3].get_text(strip=True)

        # Cell 4: License Status
        status_raw = cells[4].get_text(strip=True)
        status = _florida_normalize_status(status_raw)

        results.append({
            "name": display_name,
            "fl_name": name_raw,
            "license_number": license_number,
            "license_type": _florida_short_license_type(profession),
            "license_type_full": profession,
            "status": status,
            "issue_date": None,  # Only on detail page
            "expiry_date": None,  # Only on detail page
            "city": city,
            "state": "FL",
            "detail_href": detail_href,
        })

    return results


def parse_florida_detail_page(html: str) -> dict:
    """Parse the FL MQA licensee detail page HTML.

    The detail page uses a <dl> with <dt>/<dd> pairs:
      Profession, License, License Status, License Expiration Date,
      License Original Issue Date, Address of Record, etc.

    Also extracts the name from the page header.
    """
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "name": None,
        "fl_name": None,
        "license_number": None,
        "license_type": None,
        "license_type_full": None,
        "status": None,
        "issue_date": None,
        "expiry_date": None,
        "city": None,
        "state": "FL",
    }

    # Extract name from the page header (appears near "License Number:")
    # Pattern in the page: "WILLIAM  SUBLETT JR\nLicense Number: RT22974"
    # Look for the name before "License Number:"
    full_text = soup.get_text(separator="\n", strip=True)
    name_match = re.search(
        r"License\s*Verification\s*Printer\s*Friendly.*?\n(.*?)\nLicense\s*Number:",
        full_text, re.DOTALL
    )
    if name_match:
        name_raw = name_match.group(1).strip()
        result["fl_name"] = name_raw
        result["name"] = _normalize_name(name_raw)

    # Parse the <dl> definition list
    dl = soup.find("dl")
    if dl:
        current_dt = None
        for child in dl.children:
            if not hasattr(child, "name") or not child.name:
                continue
            if child.name == "dt":
                current_dt = child.get_text(strip=True).rstrip(":").strip()
            elif child.name == "dd" and current_dt:
                value = child.get_text(strip=True)
                if not value:
                    continue

                key = current_dt.lower()

                if key == "profession":
                    result["license_type_full"] = value
                    result["license_type"] = _florida_short_license_type(value)

                elif key == "license":
                    result["license_number"] = value

                elif key == "license status":
                    result["status"] = _florida_normalize_status(value)

                elif key == "license expiration date":
                    result["expiry_date"] = _normalize_date(value)

                elif key == "license original issue date":
                    result["issue_date"] = _normalize_date(value)

                elif key == "address of record":
                    # Address spans multiple <dd> tags; city/state/zip is in a later one
                    # Format: "CITY, ST ZIP"
                    if not result["city"]:
                        # Try to parse city from this address line
                        pass

                current_dt = None

    # Try to extract city from the address block
    # The address <dd> tags contain: street, then "CITY, ST ZIP"
    if dl:
        dd_texts = [dd.get_text(strip=True) for dd in dl.find_all("dd")]
        for dd_text in dd_texts:
            # Match "CITY, ST ZIP" pattern (e.g. "INDIANAPOLIS, IN 46202")
            city_match = re.search(
                r"^([A-Z][A-Z\s]+?),\s*([A-Z]{2})\s+(\d{5})", dd_text
            )
            if city_match:
                result["city"] = city_match.group(1).strip().title()
                result["state"] = city_match.group(2)
                break

    # If name not found from header, try the <h3> or similar
    if not result["name"]:
        for tag in soup.find_all(["h3", "h4", "h2"]):
            text = tag.get_text(strip=True)
            if text and "License Number" not in text and "License Verification" not in text:
                result["fl_name"] = text
                result["name"] = _normalize_name(text)
                break

    return result


def _florida_normalize_status(status_raw: str) -> str:
    """Normalize FL MQA status strings to uppercase codes.

    FL statuses: Clear/Active, Delinquent, Expired, Null and Void, Retired, etc.
    """
    if not status_raw:
        return None
    status_upper = status_raw.strip().upper()
    # Remove trailing slash (some statuses have "DELINQUENT/")
    status_upper = status_upper.rstrip("/")
    return status_upper


def _florida_short_license_type(full_type: str) -> str:
    """Map FL MQA profession names to short license type codes.

    e.g. "Registered Respiratory Therapist" → "RRT"
         "Certified Respiratory Therapist" → "CRT"
    """
    if not full_type:
        return ""
    full_lower = full_type.lower()
    if "registered respiratory" in full_lower:
        return "RRT"
    if "certified respiratory" in full_lower:
        return "CRT"
    if "respiratory care" in full_lower:
        return "RCP"
    # Fallback: first word uppercased
    return full_type.split()[0].upper() if full_type else ""


# ─── Florida Public API ───────────────────────────────────────

def lookup_florida_license(
    first_name: str = "",
    last_name: str = "",
    license_number: str = "",
    license_type: str = "RCP",
    fetch_details: bool = True,
) -> list[dict]:
    """Search Florida MQA for respiratory therapist licenses.

    Searches by license number if provided, otherwise by name.
    Returns a list of match dicts with license details.

    Set fetch_details=False to return only the search results list
    (without issue/expiry dates — those are on the detail page).
    """
    cache_key = _cache_key(
        "fl_name",
        first=first_name,
        last=last_name,
        num=license_number,
        type=license_type,
        details=fetch_details,
    )

    # Check cache
    if cache_key in _cache:
        entry = _cache[cache_key]
        if time.time() - entry["ts"] < _CACHE_TTL:
            return entry["data"]

    try:
        mqa = FloridaMQASession()

        # Search by license number if provided, otherwise by name
        response = mqa.search(
            last_name=last_name,
            first_name=first_name,
            license_number=license_number,
        )

        # Check if redirected to a detail page (single match)
        if "LicenseVerification" in response.url:
            # Single match: the response is the detail page
            detail = parse_florida_detail_page(response.text)
            # If we searched by license number, ensure it's in the result
            if license_number and not detail.get("license_number"):
                detail["license_number"] = license_number
            results = [detail]
        else:
            # Multiple matches or no matches
            results = parse_florida_search_results(response.text)

            if fetch_details and results:
                # Fetch detail page for each result
                enriched = []
                for result in results:
                    detail_href = result.pop("detail_href", "")
                    if detail_href:
                        try:
                            detail_html = mqa.get_detail(detail_href)
                            if detail_html:
                                detail = parse_florida_detail_page(detail_html)
                                # Merge detail info into result
                                result["name"] = detail.get("name") or result["name"]
                                result["fl_name"] = detail.get("fl_name") or result.get("fl_name")
                                result["license_number"] = detail.get("license_number") or result["license_number"]
                                result["license_type"] = detail.get("license_type") or result["license_type"]
                                result["license_type_full"] = detail.get("license_type_full") or result["license_type_full"]
                                result["status"] = detail.get("status") or result["status"]
                                result["issue_date"] = detail.get("issue_date")
                                result["expiry_date"] = detail.get("expiry_date")
                                result["city"] = detail.get("city") or result.get("city")
                                result["state"] = detail.get("state") or "FL"
                            enriched.append(result)
                        except Exception as e:
                            logger.warning(f"Failed to fetch FL detail: {e}")
                            enriched.append(result)
                    else:
                        enriched.append(result)
                results = enriched

    except Exception as e:
        logger.error(f"Florida MQA lookup failed: {e}")
        return []

    # Cache the result
    _cache[cache_key] = {"ts": time.time(), "data": results}
    return results


if __name__ == "__main__":
    # Quick test
    import json

    print("Testing Texas lookup by name: Sublett")
    results = lookup_license_by_name("", "Sublett")
    print(json.dumps(results, indent=2))

    print("\n---\nTesting Indiana lookup by name: Sublett")
    in_results = lookup_indiana_license(last_name="Sublett")
    print(json.dumps(in_results, indent=2))

    print("\n---\nTesting Florida lookup by license: RT22974")
    fl_results = lookup_florida_license(license_number="RT22974")
    print(json.dumps(fl_results, indent=2))

    print("\n---\nTesting Florida lookup by name: Sublett")
    fl_name_results = lookup_florida_license(last_name="Sublett")
    print(json.dumps(fl_name_results, indent=2))