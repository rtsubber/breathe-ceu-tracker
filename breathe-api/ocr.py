"""OCR module for certificate image extraction using easyocr + Claude API.

Hybrid approach:
  1. easyocr extracts raw text from the certificate image
  2. Claude API (claude-sonnet-4-6) parses raw text into structured CEU data
  3. Regex fallback parser if Claude API is unavailable or fails

This gives us the broad text extraction of easyocr combined with the
semantic understanding of an LLM for accurate field extraction.
"""
import os
import re
import json
import logging
from datetime import datetime
from typing import Optional

# Lazy-load easyocr (heavy import)
_reader = None

logger = logging.getLogger(__name__)

# ─── Anthropic / Claude configuration ──────────────────────────

ANTHROPIC_KEY_PATH = "/home/ron/.openclaw/workspace/.anthropic_key"
CLAUDE_MODEL = "claude-sonnet-4-20250514"  # Valid Anthropic model ID

CLAUDE_SYSTEM_PROMPT = (
    "You are extracting CEU certificate information. "
    "From the following text extracted from a certificate image, identify: "
    "course title, provider organization, number of credits/CEUs/contact hours, "
    "completion date, and category (clinical/safety/ethics/leadership). "
    'Return JSON only with keys: title, provider, credits, completion_date, category, confidence. '
    'The credits field must be a number (float). The completion_date must be in YYYY-MM-DD format. '
    'The category must be one of: clinical, safety, ethics, leadership. '
    'The confidence field should be a number between 0 and 1 representing your confidence in the extraction.'
)

CLAUDE_MAX_TOKENS = 1024


def _get_anthropic_key() -> str:
    """Read the Anthropic API key from the shared key file."""
    try:
        with open(ANTHROPIC_KEY_PATH, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning("Anthropic key file not found at %s", ANTHROPIC_KEY_PATH)
        return ""


def _get_reader():
    """Lazy-load easyocr Reader singleton."""
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _reader


# ─── Image handling ─────────────────────────────────────────────

def save_certificate_image(file_bytes: bytes, filename: str, user_id: int) -> str:
    """Save uploaded certificate image to /tmp/breathe/certificates/."""
    cert_dir = f"/tmp/breathe/certificates/user_{user_id}"
    os.makedirs(cert_dir, exist_ok=True)
    safe_name = os.path.basename(filename)
    save_path = os.path.join(cert_dir, safe_name)
    with open(save_path, "wb") as f:
        f.write(file_bytes)
    return save_path


def extract_text_from_image(image_path: str) -> list:
    """Extract text from image using easyocr. Returns list of (text, confidence) tuples."""
    reader = _get_reader()
    results = reader.readtext(image_path)
    extracted = []
    for bbox, text, conf in results:
        extracted.append((text.strip(), float(conf)))
    return extracted


# ─── Claude API semantic parser ────────────────────────────────

def _raw_text_from_extracted(extracted: list) -> str:
    """Join easyocr results into a single text blob."""
    return "\n".join(t for t, c in extracted)


def parse_with_claude(raw_text: str) -> Optional[dict]:
    """Send raw OCR text to Claude API for semantic parsing.

    Returns dict with keys: title, provider, credits, completion_date,
    category, confidence — or None if the API call fails.
    """
    if not raw_text.strip():
        return None

    api_key = _get_anthropic_key()
    if not api_key:
        logger.warning("No Anthropic API key — skipping Claude parsing")
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed — skipping Claude parsing")
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            messages=[
                {
                    "role": "user",
                    "content": f"{CLAUDE_SYSTEM_PROMPT}\n\n--- Certificate Text ---\n{raw_text}",
                }
            ],
        )

        # Extract text from response
        response_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                response_text += block.text

        # Parse JSON from response (handle markdown code fences)
        response_text = response_text.strip()
        if response_text.startswith("```"):
            # Remove markdown code fences
            lines = response_text.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            response_text = "\n".join(lines)

        # Find the JSON object in the response
        json_match = re.search(r"\{[^{}]*\}", response_text, re.DOTALL)
        if not json_match:
            logger.warning("Could not find JSON in Claude response: %s", response_text[:200])
            return None

        data = json.loads(json_match.group(0))

        # Normalize and validate fields
        result = {
            "title": str(data.get("title", "")).strip() or "Unknown Course",
            "provider": str(data.get("provider", "")).strip() or "Unknown Provider",
            "credits": _safe_float(data.get("credits", 0)),
            "completion_date": _normalize_date_str(str(data.get("completion_date", "")).strip()),
            "category": _validate_category(str(data.get("category", "clinical")).strip().lower()),
            "confidence": _safe_float(data.get("confidence", 0.8), default=0.8),
        }
        return result

    except anthropic.APIError as e:
        logger.error("Claude API error: %s", e)
        return None
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Claude JSON response: %s", e)
        return None
    except Exception as e:
        logger.error("Unexpected Claude API failure: %s", e)
        return None


# ─── Regex fallback parser ──────────────────────────────────────

def parse_with_regex(extracted: list) -> dict:
    """Fallback regex-based parser. Extracts CEU fields from easyocr output.

    Returns dict with: title, provider, credits, completion_date,
    category, confidence, raw_text.
    """
    raw_text_parts = [t for t, c in extracted]
    raw_text = "\n".join(raw_text_parts)
    avg_conf = sum(c for _, c in extracted) / len(extracted) if extracted else 0.0

    # Parse title — look for keywords like "Course", "Certificate", "Certificate of Completion"
    title = ""
    for i, (text, conf) in enumerate(extracted):
        if re.search(r"(course|certificate|completion|continuing)", text, re.I):
            # Look at the next few lines for the actual title
            for j in range(i + 1, min(i + 5, len(extracted))):
                t = extracted[j][0]
                if len(t) > 5 and not re.search(
                    r"(provider|date|credit|hour|ceu|authorized|verify)", t, re.I
                ):
                    title = t
                    break
            if title:
                break

    if not title:
        # Try to find a long text line that looks like a title
        for text, conf in extracted:
            if len(text) > 15 and not re.search(
                r"(provider|date|credit|hour|ceu|authorized|verify|signature)", text, re.I
            ):
                title = text
                break

    if not title:
        title = "Unknown Course"

    # Strip common prefixes from title
    title = re.sub(r"^(?:Title|Course|Course Title)\s*[:.]\s*", "", title, flags=re.I).strip()

    # Parse provider — look for "Provider", "Presented by", "Sponsored by", "Approved by"
    provider = ""
    for i, (text, conf) in enumerate(extracted):
        if re.search(r"(provider|presented by|sponsored by|approved by|offered by|issued by)", text, re.I):
            # First try to extract from same line after colon
            parts = re.split(r"[:\s]+", text, 1)
            after_colon = text.split(":", 1)
            if len(after_colon) > 1 and after_colon[1].strip():
                provider = after_colon[1].strip()
            elif i + 1 < len(extracted):
                # Only use next line if it doesn't look like credits/date
                next_text = extracted[i + 1][0]
                if not re.search(r"(\d+(?:\.\d+)?)\s*(?:ceu|credit|hour|hr|CRCE|contact)", next_text, re.I) and \
                   not re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", next_text) and \
                   not re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", next_text, re.I):
                    provider = next_text
            break

    if not provider:
        # Fallback: look for known provider patterns
        for text, conf in extracted:
            if re.search(
                r"(AARC|NBRC|AHA|AAP|Medical|Hospital|University|College|Institute|"
                r"HealthStream|Relias|Medbridge|Medscape|CEUFast|CAPCE|ProCE|RespLine|"
                r"CME Zone|Learning Management)",
                text, re.I,
            ):
                provider = text
                break

    if not provider:
        provider = "Unknown Provider"

    # Parse credits — comprehensive patterns
    credits = 0.0
    credit_patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:ceu|ceus|credit|credits|credit\s*hour|credit\s*hours)\b",
        r"(\d+(?:\.\d+)?)\s*contact\s*hour(?:s)?\b",
        r"(\d+(?:\.\d+)?)\s*(?:credit|ceu)\s*hour(?:s)?\b",
        r"(\d+(?:\.\d+)?)\s*(?:ceu|credit|hour|hr)s?\b",
        r"(?:contact\s*)?hours?\s*[:.]?\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*(?:CRCE|AMA PRA Category 1)\s*credit(?:s)?\b",
    ]
    for text, conf in extracted:
        for pat in credit_patterns:
            m = re.search(pat, text, re.I)
            if m:
                credits = float(m.group(1))
                break
        if credits > 0:
            break

    # Parse completion date — comprehensive patterns
    completion_date = ""
    date_patterns = [
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",  # MM/DD/YYYY or M/D/YY
        r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})",  # YYYY-MM-DD
        r"((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
        r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
        r"\d{1,2},?\s+\d{4})",  # Month DD, YYYY
    ]

    for text, conf in extracted:
        for pattern in date_patterns:
            m = re.search(pattern, text, re.I)
            if m:
                raw_date = m.group(0)
                parsed = normalize_date(raw_date)
                if parsed:
                    completion_date = parsed
                    break
        if completion_date:
            break

    # Category detection
    category = _detect_category(raw_text)

    return {
        "title": title,
        "provider": provider,
        "credits": credits,
        "completion_date": completion_date,
        "category": category,
        "confidence": round(avg_conf, 3),
        "raw_text": raw_text,
    }


# ─── Helper functions ───────────────────────────────────────────

def _safe_float(val, default=0.0) -> float:
    """Convert value to float safely."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _normalize_date_str(raw: str) -> str:
    """Try to parse a date string and return ISO format (YYYY-MM-DD)."""
    if not raw:
        return ""
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
    # Try extracting a date substring
    for pat in [
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        r"((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
        r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
        r"\d{1,2},?\s+\d{4})",
    ]:
        m = re.search(pat, raw, re.I)
        if m:
            return _normalize_date_str(m.group(1))
    return ""


def normalize_date(raw: str) -> str:
    """Public alias for _normalize_date_str (kept for backwards compat)."""
    return _normalize_date_str(raw)


def _validate_category(category: str) -> str:
    """Ensure category is one of the allowed values."""
    valid = {"clinical", "safety", "ethics", "leadership"}
    if category in valid:
        return category
    # Partial match
    for v in valid:
        if v in category:
            return v
    return "clinical"


def _detect_category(text: str) -> str:
    """Detect CEU category from keyword matching."""
    lower = text.lower()
    # Check ethics first (most specific)
    if any(kw in lower for kw in ["ethic", "moral", "professional bound", "code of conduct"]):
        return "ethics"
    # Safety
    if any(kw in lower for kw in ["safety", "medication error", "patient safety", "infection", "error reduction", "quality improvement"]):
        return "safety"
    # Leadership — only if clearly about management/leadership, not just containing "management" in course title
    if any(kw in lower for kw in ["leadership", "management skill", "admin", "supervisor", "director", "nurse manager"]):
        return "leadership"
    return "clinical"


# ─── Main pipeline ──────────────────────────────────────────────

def parse_ceu_data(extracted: list) -> dict:
    """Parse extracted text for CEU-relevant fields.

    Hybrid approach: try Claude API first, fall back to regex.
    Always includes raw_text from the easyocr extraction.
    """
    raw_text = _raw_text_from_extracted(extracted)

    if not raw_text.strip():
        return {
            "title": "Unknown Course",
            "provider": "Unknown Provider",
            "credits": 0.0,
            "completion_date": "",
            "category": "clinical",
            "confidence": 0.0,
            "raw_text": "",
        }

    # Try Claude API first
    claude_result = parse_with_claude(raw_text)

    if claude_result:
        # Merge in raw_text (Claude doesn't return it)
        claude_result["raw_text"] = raw_text
        # Use the higher of Claude confidence vs easyocr avg confidence
        avg_ocr_conf = sum(c for _, c in extracted) / len(extracted) if extracted else 0.0
        claude_result["confidence"] = max(
            claude_result.get("confidence", 0.8),
            round(avg_ocr_conf, 3),
        )
        return claude_result

    # Fall back to regex parser
    logger.info("Claude parsing failed or unavailable — using regex fallback")
    return parse_with_regex(extracted)


def process_certificate(image_path: str) -> dict:
    """Full OCR pipeline: extract text from image and parse CEU data.

    1. easyocr extracts raw text
    2. Claude API parses raw text into structured CEU data
    3. Falls back to regex parser if Claude fails
    """
    extracted = extract_text_from_image(image_path)
    return parse_ceu_data(extracted)