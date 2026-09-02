"""OCR module for certificate image extraction using easyocr + glm-5.3-flash.

Hybrid approach:
  1. easyocr extracts raw text from the certificate image
  2. glm-5.3-flash (via Ollama API) parses raw text into structured CEU data
  3. Regex fallback parser if the API is unavailable or fails

This gives us the broad text extraction of easyocr combined with the
semantic understanding of an LLM for accurate field extraction.
"""
import os
import re
import json
import logging
import time
import urllib.request
from datetime import datetime
from typing import Optional

# Lazy-load easyocr (heavy import)
_reader = None

logger = logging.getLogger(__name__)

# ─── glm-5.3-flash configuration (via Ollama API) ─────────────

OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "https://openrouter.ai/api/v1/chat/completions")
OLLAMA_API_KEY_PATH = "/home/ron/.openclaw/workspace/.ollama_key"
LLM_MODEL = "openrouter/free"

LLM_SYSTEM_PROMPT = (
    "You are extracting CEU certificate information from OCR text. "
    "IMPORTANT: The 'title' field must be the COURSE NAME or PROGRAM NAME — NOT the student's name. "
    "The student's name is the person who completed the course — do NOT use it as the title. "
    "Look for the course/program title near keywords like 'Course', 'Program', 'CRCE', 'Quiz', 'Seminar', 'Workshop'. "
    "If the text contains a person's name AND a course title, use the COURSE TITLE as the title. "
    "From the following text extracted from a certificate, identify: "
    "course title (NOT person name), provider organization, number of credits/CEUs/contact hours, "
    "completion date, and category (clinical/safety/ethics/leadership). "
    'Return JSON only with keys: title, provider, credits, completion_date, category, confidence. '
    'The credits field must be a number (float). The completion_date must be in YYYY-MM-DD format. '
    'The category must be one of: clinical, safety, ethics, leadership. '
    'The confidence field should be a number between 0 and 1 representing your confidence in the extraction. '
    'Example: if the text says "William Sublett completed The Ethics of Ambiguity: Life and Death in the NICU", '
    'the title should be "The Ethics of Ambiguity: Life and Death in the NICU", NOT "William Sublett".'
)

LLM_MAX_TOKENS = 1024




def extract_text_from_image(image_path: str) -> list:
    """Extract text from an image using easyocr. Returns list of (text, confidence) tuples."""
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(['en'], gpu=False)
    
    results = _reader.readtext(image_path)
    # Return list of (text, confidence) tuples
    return [(text, conf) for _, text, conf in results]

def extract_text_from_pdf(pdf_path: str) -> list:
    """Extract text from a PDF using PyMuPDF (fitz). Returns list of (text, confidence) tuples."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF not installed — cannot extract text from PDF")
        return []
    
    doc = fitz.open(pdf_path)
    extracted = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            extracted.append((text.strip(), 1.0))  # Digital text = 100% confidence
    doc.close()
    return extracted

def _raw_text_from_extracted(extracted: list) -> str:
    """Convert extracted list of (text, confidence) tuples into a single raw text string."""
    return ' '.join([text for text, _ in extracted])

def is_pdf(file_path: str) -> bool:
    """Check if a file is a PDF."""
    return file_path.lower().endswith('.pdf')


def _safe_delete_file(file_path: str) -> None:
    """Safely delete a file, ignoring errors."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass


def save_certificate_image(file_bytes: bytes, filename: str, user_id: int) -> str:
    """Save uploaded certificate image to a permanent directory."""
    cert_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certificates", f"user_{user_id}")
    os.makedirs(cert_dir, exist_ok=True)
    
    safe_name = os.path.basename(filename)
    save_path = os.path.join(cert_dir, safe_name)
    
    with open(save_path, "wb") as f:
        f.write(file_bytes)
    
    return save_path


def _get_ollama_key() -> str:
    """Read the Ollama API key from the key file."""
    try:
        with open(OLLAMA_API_KEY_PATH) as f:
            return f.read().strip()
    except Exception:
        return os.environ.get("OLLAMA_API_KEY", "")


def parse_with_llm(raw_text: str) -> Optional[dict]:
    """Send raw OCR text to glm-5.3-flash (via Ollama API) for semantic parsing.

    Returns dict with keys: title, provider, credits, completion_date,
    category, confidence — or None if the API call fails.
    """
    if not raw_text.strip():
        return None

    api_key = _get_ollama_key()
    if not api_key:
        logger.warning("No Ollama API key — skipping LLM parsing")
        return None

    try:
        payload = json.dumps({
            "model": LLM_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": f"{LLM_SYSTEM_PROMPT}\n\n--- Certificate Text ---\n{raw_text}",
                }
            ],
            "max_tokens": LLM_MAX_TOKENS,
            "temperature": 0.1,
        }).encode()

        req = urllib.request.Request(
            OLLAMA_API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        if not response_text.strip():
            logger.warning("Empty LLM response")
            return None

        # Parse JSON from response (handle markdown code fences)
        response_text = response_text.strip()
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            response_text = "\n".join(lines)

        # Find the JSON object in the response
        json_match = re.search(r"\{[^{}]*\}", response_text, re.DOTALL)
        if not json_match:
            logger.warning("Could not find JSON in LLM response: %s", response_text[:200])
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

    except urllib.error.HTTPError as e:
        logger.error("Ollama API error: HTTP %s — %s", e.code, e.read().decode()[:200])
        return None
    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM JSON response: %s", e)
        return None
    except Exception as e:
        logger.error("Unexpected LLM API failure: %s", e)
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
    llm_result = parse_with_llm(raw_text)

    if llm_result:
        # Merge in raw_text (LLM doesn't return it)
        llm_result["raw_text"] = raw_text
        # Use the higher of Claude confidence vs easyocr avg confidence
        avg_ocr_conf = sum(c for _, c in extracted) / len(extracted) if extracted else 0.0
        llm_result["confidence"] = max(
            llm_result.get("confidence", 0.8),
            round(avg_ocr_conf, 3),
        )
        return llm_result

    # Fall back to regex parser
    logger.info("LLM parsing failed or unavailable — using regex fallback")
    return parse_with_regex(extracted)


def process_certificate(image_path: str, cleanup: bool = True) -> dict:
    """Full OCR pipeline: extract text from image or PDF and parse CEU data.

    1. For images: easyocr extracts raw text
    2. For PDFs: PyMuPDF extracts digital text directly
    3. LLM (glm-5.3-flash) parses raw text into structured CEU data
    4. Falls back to regex parser if Claude fails

    By default, deletes the temporary certificate file after processing
    to avoid leaving PII (name, DOB, license number) on disk.
    Set cleanup=False to keep the file (e.g. when the caller manages lifecycle).
    """
    try:
        if is_pdf(image_path):
            extracted = extract_text_from_pdf(image_path)
        else:
            extracted = extract_text_from_image(image_path)
        return parse_ceu_data(extracted)
    finally:
        if cleanup:
            _safe_delete_file(image_path)