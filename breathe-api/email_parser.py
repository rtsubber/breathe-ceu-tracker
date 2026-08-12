"""Email parser for CEU confirmation emails.

Extracts CEU data (title, provider, credits, completion date) from common
email formats used by CE providers: AARC, Medbridge, and generic providers.

Handles both HTML and plain-text email bodies. Extracts certificate
attachments and saves them to /tmp/breathe/certificates/.
"""
import os
import re
import base64
import hashlib
from datetime import datetime
from typing import Optional
from email.utils import parseaddr

# ─── Known provider domain map ──────────────────────────────────
# Comprehensive list of CE providers that RTs actually use.
# Order matters for substring matching — more specific domains first.
PROVIDER_DOMAINS = {
    # AARC (American Association for Respiratory Care)
    "learning.aarc.org": "AARC",
    "aarc.org": "AARC",
    "aarc.com": "AARC",
    "learnaarc.org": "AARC",
    "rc.jchs.edu": "AARC",
    # Medbridge
    "medbridgeeducation.com": "Medbridge",
    "medbridge.com": "Medbridge",
    # NBRC / AAP / AHA
    "nbrc.org": "NBRC",
    "aap.org": "AAP",
    "heart.org": "AHA",
    # HealthStream
    "healthstream.com": "HealthStream",
    # Relias Learning
    "relias.com": "Relias Learning",
    # Medscape
    "medscape.com": "Medscape",
    # ProCE
    "proce.com": "ProCE",
    # RespLine
    "respline.com": "RespLine",
    # CEUFast
    "ceufast.com": "CEUFast",
    # Respiratory Therapy CE
    "respiratorytherapy.com": "Respiratory Therapy CE",
    # Learning Management
    "learningmanagement.com": "Learning Management",
    # CAPCE
    "capce.org": "CAPCE",
    # CME Zone
    "cmezone.com": "CME Zone",
    # FreeCME
    "freecme.com": "FreeCME",
}


def _strip_html(html: str) -> str:
    """Crude HTML→text: strip tags, decode common entities."""
    # Remove style/script blocks entirely
    html = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    # Replace <br> and </p> with newlines
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</p>", "\n", html, flags=re.I)
    html = re.sub(r"</div>", "\n", html, flags=re.I)
    html = re.sub(r"</tr>", "\n", html, flags=re.I)
    html = re.sub(r"<li[^>]*>", "\n• ", html, flags=re.I)
    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", "", html)
    # Decode entities
    import html as html_mod
    import quopri
    text = html_mod.unescape(text)
    # Collapse blank lines
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def get_text_from_email(html_body: Optional[str], text_body: Optional[str]) -> str:
    """Return the best plain-text representation of an email."""
    if text_body and text_body.strip():
        text = text_body.strip()
        # Decode quoted-printable if detected (=20, =3D, etc.)
        if "=20" in text or "=3D" in text or "=\r\n" in text:
            try:
                text = quopri.decodestring(text.encode()).decode("utf-8", errors="ignore")
            except Exception:
                text = text.replace("=20", " ").replace("=3D", "=").replace("=\r\n", "")
        # Remove quoted reply markers
        text = "\n".join(line.lstrip("> ") for line in text.splitlines())
        return text.strip()
    if html_body and html_body.strip():
        html = html_body.strip()
        # Decode quoted-printable in HTML too
        if "=20" in html or "=3D" in html:
            try:
                html = quopri.decodestring(html.encode()).decode("utf-8", errors="ignore")
            except Exception:
                pass
        return _strip_html(html)
    return ""


def _provider_from_sender(sender_email: str) -> str:
    """Derive provider from the sender's email domain."""
    _, addr = parseaddr(sender_email or "")
    if "@" in addr:
        domain = addr.split("@", 1)[1].lower()
        for known, name in PROVIDER_DOMAINS.items():
            if known in domain:
                return name
        # Use the bare domain as fallback (capitalize first part)
        return domain.split(".")[0].title()
    return "Unknown Provider"


# ─── Regex patterns ─────────────────────────────────────────────
# Comprehensive credit extraction patterns covering CE, CRCE, AMA, and more.
# Order matters! More specific patterns (AMA, CRCE) must come BEFORE generic ones.
CREDITS_PATTERNS = [
    # X AMA PRA Category 1 Credit(s) (physician format, some RT courses) — MUST be before generic credit
    r"(\d+(?:\.\d+)?)\s*AMA\s*PRA\s*Category\s*1\s*[Cc]redit(?:s)?\b",
    r"AMA\s*PRA\s*Category\s*1\s*[Cc]redit(?:s)?\s*[:.]?\s*(\d+(?:\.\d+)?)",
    # X CRCE credit(s) (AARC-specific term) — MUST be before generic credit
    r"(\d+(?:\.\d+)?)\s*CRCE\s*credit(?:s)?\b",
    r"CRCE\s*credit(?:s)?\s*[:.]?\s*(\d+(?:\.\d+)?)",
    # X contact hour(s)
    r"(\d+(?:\.\d+)?)\s*contact\s*hour(?:s)?\b",
    r"contact\s*hour(?:s)?\s*[:.]?\s*(\d+(?:\.\d+)?)",
    # X CEU(s)
    r"(\d+(?:\.\d+)?)\s*ceu(?:s)?\b",
    r"ceu(?:s)?\s*[:.]?\s*(\d+(?:\.\d+)?)",
    # X credit hour(s)
    r"(\d+(?:\.\d+)?)\s*credit\s*hour(?:s)?\b",
    r"credit\s*hour(?:s)?\s*[:.]?\s*(\d+(?:\.\d+)?)",
    # X credit(s) — generic, after specific patterns
    r"(\d+(?:\.\d+)?)\s*credit(?:s)?\b",
    r"credit(?:s)?\s*[:.]?\s*(\d+(?:\.\d+)?)",
    # X CE / CE hours
    r"(\d+(?:\.\d+)?)\s*(?:ce|ce\s*hour)(?:s)?\b",
    r"(?:ce\s*hour)(?:s)?\s*[:.]?\s*(\d+(?:\.\d+)?)",
    # Generic hour(s) / hr(s)
    r"(\d+(?:\.\d+)?)\s*(?:hour|hr)(?:s)?\b",
    r"awarded\s*(\d+(?:\.\d+)?)\s*(?:ceu|credit|hour)",
    r"(\d+(?:\.\d+)?)\s*(?:ceu|credit|hour)\s*(?:awarded|earned|completed)",
    r"earned\s*(\d+(?:\.\d+)?)\s*(?:ceu|credit|hour)",
    r"(\d+(?:\.\d+)?)\s*(?:ceu|credit|hour)\s*(?:earned|awarded)",
]

DATE_PATTERNS = [
    # "Completed on DATE" / "Completed: DATE" / "Date of Completion: DATE"
    r"(?:completed(?:\s+on)?|date\s+of\s+completion|completion\s+date)\s*[:.]?\s*(.+?)(?:\n|$)",
    # "Date: DATE"
    r"(?:date)\s*[:.]\s*(.+?)(?:\n|$)",
    # Standalone dates near keywords
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})",
    r"((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4})",
]

TITLE_PATTERNS = [
    # "Course Title: XYZ" at start of line
    r"^(?:course(?:\s+title)?|title)\s*[:.]\s*(.+?)(?:\n|$)",
    # "Course: XYZ" at start of line
    r"^Course:\s*(.+?)(?:\n|$)",
    # "Course Name: XYZ" at start of line
    r"^Course\s+Name\s*[:.]\s*(.+?)(?:\n|$)",
    # "Webinar: XYZ" / "Seminar: XYZ" / "Module: XYZ" at start of line
    r"^(?:webinar|seminar|module|session|program)\s*[:.]\s*(.+?)(?:\n|$)",
    # "You have completed: XYZ"
    r"(?:completed|finished)\s*[:.]\s*(.+?)(?:\n|$)",
    # " XYZ has been completed"
    r"(.+?)\s+has\s+been\s+(?:successfully\s+)?completed",
]

PROVIDER_PATTERNS = [
    r"(?:provider|presented\s+by|sponsored\s+by|issued\s+by|approved\s+by|offered\s+by)\s*[:.]\s*(.+?)(?:\n|$)",
]


def _normalize_date(raw: str) -> Optional[str]:
    """Try to parse a date string and return ISO format (YYYY-MM-DD)."""
    if not raw:
        return None
    raw = raw.strip().rstrip(",.").strip()
    formats = [
        "%m/%d/%Y", "%m/%d/%y",
        "%Y-%m-%d",
        "%B %d, %Y", "%b %d, %Y",
        "%B %d %Y", "%b %d %Y",
        "%m-%d-%Y", "%m-%d-%y",
        "%d %B %Y", "%d %b %Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Try extracting a date substring from the raw text
    for pat in [
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        r"((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4})",
    ]:
        m = re.search(pat, raw, re.I)
        if m:
            return _normalize_date(m.group(1))
    return None


def _extract_credits(text: str) -> float:
    """Extract CEU credits from text using comprehensive patterns."""
    for pat in CREDITS_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return 0.0


def _extract_date(text: str) -> Optional[str]:
    """Extract completion date from text."""
    # First pass: labeled date patterns
    for pat in DATE_PATTERNS[:3]:
        m = re.search(pat, text, re.I)
        if m:
            iso = _normalize_date(m.group(1))
            if iso:
                return iso
    # Second pass: standalone date patterns
    for pat in DATE_PATTERNS[3:]:
        m = re.search(pat, text, re.I)
        if m:
            iso = _normalize_date(m.group(1))
            if iso:
                return iso
    return None


def _extract_title(text: str, subject: str = "") -> str:
    """Extract course title from text or subject line."""
    # 1. Try labeled patterns in body (MULTILINE so ^ matches line starts)
    for pat in TITLE_PATTERNS:
        m = re.search(pat, text, re.I | re.MULTILINE)
        if m:
            title = m.group(1).strip()
            # Strip leading "Course:" or "Title:" labels that may be captured
            title = re.sub(r"^(?:course|title)\s*[:.]\s*", "", title, flags=re.I).strip()
            if title:
                return title
    # 2. Use subject line if it looks like a course title
    if subject:
        subj = subject.strip()
        # Remove "Confirmation" / "Certificate" boilerplate
        cleaned = re.sub(
            r"\b(?:confirmation|certificate|of\s+completion|ceu|course|webinar|seminar)\b",
            "", subj, flags=re.I,
        ).strip(" :-|")
        if cleaned and len(cleaned) > 5:
            return cleaned
    # 3. Fallback: look for a line that looks like a course title
    # Skip boilerplate lines (greetings, signatures, disclaimers, etc.)
    skip_patterns = re.compile(
        r"^(?:dear|hello|hi|thank|congratulations|please|this\s+is|you\s+have|"
        r"your\s+ceu|for\s+questions|if\s+you|please\s+(?:reach|contact|call)|"
        r"please\s+do\s+not|please\s+note|please\s+keep|for\s+more\s+info|"
        r"to\s+view|to\s+access|click\s+(?:here|the)|you\s+can\s+(?:view|access|download)|"
        r"this\s+email|this\s+is\s+an\s+auto|do\s+not\s+reply|reply\s+to|"
        r"for\s+any\s+questions|feel\s+free|best\s+regards|sincerely|regards|"
        r"warmly|cheers|thanks\s+again|thank\s+you\s+for|congratulations\s+on|"
        r"your\s+certificate|you\s+have\s+successfully|you\s+have\s+completed|"
        r"has\s+been\s+(?:completed|submitted|processed)|we\s+hope|we\s+are\s+happy|"
        r"info@|support@|contact\s+us|call\s+us|hotline|\d{3}[.-]\d{3}[.-]\d{4}|"
        r"http|www\.|©|all\s+rights|privacy|terms\s+of|unsubscribe)",
        re.I
    )
    for line in text.splitlines():
        ln = line.strip()
        if len(ln) < 5 or len(ln) > 200:
            continue
        if skip_patterns.search(ln):
            continue
        # Skip lines that are mostly URLs or email addresses
        if re.match(r"^(?:https?://|www\.|[\w.]+@[\w.]+)", ln, re.I):
            continue
        # Skip lines that are just numbers or dates
        if re.match(r"^[\d/\-:.,\s]+$", ln):
            continue
        # Skip lines with too many special characters
        if sum(1 for c in ln if not c.isalnum() and c not in " .,;:'-") > len(ln) * 0.3:
            continue
        return ln
    return "Unknown Course"


def _extract_provider(text: str, sender_email: str) -> str:
    """Extract provider from text or sender domain."""
    for pat in PROVIDER_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1).strip()
    return _provider_from_sender(sender_email)


def _extract_category(text: str) -> str:
    """Try to detect CEU category from keywords."""
    lower = text.lower()
    if any(kw in lower for kw in ["ethic", "moral", "professional bound", "code of conduct"]):
        return "ethics"
    if any(kw in lower for kw in ["safety", "error", "quality", "patient safety", "infection", "safety"]):
        return "safety"
    if any(kw in lower for kw in ["leadership", "management", "admin", "supervisor", "director"]):
        return "leadership"
    return "clinical"


# ─── Attachment handling ─────────────────────────────────────────

CERTIFICATE_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}


def save_attachment(attachment: dict, user_id: int) -> Optional[str]:
    """Save a single attachment dict to /tmp/breathe/certificates/user_{id}/.

    Expected attachment dict shape (Resend Inbound format):
      { "filename": str, "content_type": str, "content": base64_str }

    Returns the saved file path or None if not a certificate.
    """
    filename = attachment.get("filename") or attachment.get("name") or "attachment"
    content_type = attachment.get("content_type") or attachment.get("contentType") or ""
    ext = os.path.splitext(filename)[1].lower()

    # Only save certificate-like attachments
    if ext not in CERTIFICATE_EXTS and "pdf" not in content_type and "image" not in content_type:
        return None

    cert_dir = f"/tmp/breathe/certificates/user_{user_id}"
    os.makedirs(cert_dir, exist_ok=True)

    # Avoid name collisions
    safe_name = os.path.basename(filename)
    dest = os.path.join(cert_dir, safe_name)
    if os.path.exists(dest):
        stem, e = os.path.splitext(safe_name)
        dest = os.path.join(cert_dir, f"{stem}_{hashlib.md5(safe_name.encode()).hexdigest()[:6]}{e}")

    content = attachment.get("content") or attachment.get("data") or ""
    # Content may be base64-encoded
    try:
        raw = base64.b64decode(content) if content else b""
    except Exception:
        raw = content.encode() if isinstance(content, str) else b""

    if not raw:
        return None

    with open(dest, "wb") as f:
        f.write(raw)
    return dest


def save_attachments(attachments: list, user_id: int) -> list[str]:
    """Save all certificate-like attachments. Returns list of saved paths."""
    saved = []
    for att in (attachments or []):
        path = save_attachment(att, user_id)
        if path:
            saved.append(path)
    return saved


# ─── Main parse function ─────────────────────────────────────────

def parse_ceu_email(
    *,
    from_email: str = "",
    to_email: str = "",
    subject: str = "",
    text: Optional[str] = None,
    html: Optional[str] = None,
    attachments: Optional[list] = None,
) -> dict:
    """Parse an inbound CEU confirmation email.

    Returns a dict:
      {
        "title": str,
        "provider": str,
        "credits": float,
        "completion_date": str | None (ISO YYYY-MM-DD),
        "category": str,
        "certificate_path": str | None,
        "sender_email": str,
        "recipient_email": str,
        "subject": str,
        "raw_text": str,
      }
    """
    body_text = get_text_from_email(html, text)

    title = _extract_title(body_text, subject)
    provider = _extract_provider(body_text, from_email)
    credits = _extract_credits(body_text)
    completion_date = _extract_date(body_text)
    category = _extract_category(body_text)

    return {
        "title": title,
        "provider": provider,
        "credits": credits,
        "completion_date": completion_date,
        "category": category,
        "certificate_path": None,  # set by caller after saving attachments
        "sender_email": from_email,
        "recipient_email": to_email,
        "subject": subject,
        "raw_text": body_text[:2000],  # truncate for storage/debugging
    }


def parse_resend_inbound(payload: dict) -> dict:
    """Parse a Resend Inbound webhook payload.

    Expected shape (Resend Inbound):
      {
        "from": "sender@example.com",
        "to": "user@breathe.ceu",
        "subject": "Course Confirmation",
        "text": "plain text body" | null,
        "html": "<html>..." | null,
        "attachments": [
          {"filename": "cert.pdf", "content_type": "application/pdf", "content": "<base64>"},
          ...
        ]
      }
    """
    from_email = payload.get("from") or ""
    to_email = payload.get("to") or ""
    subject = payload.get("subject") or ""
    text = payload.get("text")
    html = payload.get("html")
    attachments = payload.get("attachments") or []

    return parse_ceu_email(
        from_email=from_email,
        to_email=to_email,
        subject=subject,
        text=text,
        html=html,
        attachments=attachments,
    )