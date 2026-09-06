"""OCR module for certificate extraction — local-first pipeline.

Primary path (always available, no API costs):
  Images: deepseek-ocr:3b (Ollama) → glm-5.2:cloud (structured parsing)
  PDFs:   PyMuPDF text extraction → glm-5.2:cloud (structured parsing)

Cloud upgrade path (when credits available):
  Gemini 2.5 Flash via OpenRouter (vision — reads image directly)

Last resort: easyocr + regex parser (fully offline)
"""
import os
import re
import json
import base64
import logging
import time
import urllib.request
from datetime import datetime
from typing import Optional

_reader = None  # lazy-load easyocr only for last-resort fallback

logger = logging.getLogger(__name__)

# ─── Configuration ─────────────────────────────────────────────

# Local Ollama models (primary — always available)
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OCR_MODEL = "deepseek-ocr:3b"           # purpose-built OCR for text extraction
LLM_PARSER_MODEL = "glm-5.2:cloud"      # structured JSON parsing from raw text

# Cloud vision upgrade (when credits available)
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY_PATH = "/home/ron/.openclaw/workspace/.ollama_key"
CLOUD_VISION_MODEL = "google/gemini-2.5-flash"

# FreeLLMAPI fallback
FREELLMAPI_URL = "http://localhost:3002/v1/chat/completions"
FREELLMAPI_KEY_PATH = "/home/ron/.openclaw/workspace/.freellmapi_key"
FREELLMAPI_TEXT_MODEL = "gpt-oss-20b"

LLM_MAX_TOKENS = 1024

EXTRACTION_PROMPT = (
    "You are extracting CEU certificate information from text. "
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

VISION_EXTRACTION_PROMPT = (
    "You are extracting CEU certificate information from a certificate image. "
    "Look at the certificate image carefully and extract the following fields: "
    "1. title — the COURSE NAME or PROGRAM NAME (NOT the student's name) "
    "2. provider — the organization that issued/approved the CEU "
    "3. credits — number of CEU/credit/contact hours (as a float) "
    "4. completion_date — date the certificate was completed (YYYY-MM-DD format) "
    "5. category — one of: clinical, safety, ethics, leadership "
    "6. confidence — your confidence in the extraction (0.0 to 1.0) "
    "IMPORTANT: The 'title' field must be the COURSE NAME, not the student's name. "
    'Return JSON only with keys: title, provider, credits, completion_date, category, confidence. '
    'No markdown, no explanation — just the JSON object.'
)


# ─── Image helpers ─────────────────────────────────────────────

def _encode_image_base64(image_path: str) -> str:
    """Read an image file and return its base64-encoded string."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _get_mime_type(file_path: str) -> str:
    """Guess MIME type from file extension."""
    ext = os.path.splitext(file_path)[1].lower()
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp", ".bmp": "image/bmp",
        ".tiff": "image/tiff", ".tif": "image/tiff",
    }.get(ext, "image/jpeg")


def _compress_image(image_path: str, max_dim: int = 1568, quality: int = 85) -> str:
    """Compress and resize an image for API calls. Returns path to compressed image."""
    try:
        from PIL import Image
        img = Image.open(image_path)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if max(img.size) > max_dim:
            ratio = max_dim / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        compressed_path = image_path + "._compressed.jpg"
        img.save(compressed_path, "JPEG", quality=quality, optimize=True)
        return compressed_path
    except Exception as e:
        logger.warning("Image compression failed (%s) — using original", e)
        return image_path


# ─── File helpers ──────────────────────────────────────────────

def is_pdf(file_path: str) -> bool:
    return file_path.lower().endswith('.pdf')


def _safe_delete_file(file_path: str) -> None:
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass


def save_certificate_image(file_bytes: bytes, filename: str, user_id: int) -> str:
    """Save uploaded certificate to a permanent directory."""
    cert_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certificates", f"user_{user_id}")
    os.makedirs(cert_dir, exist_ok=True)
    safe_name = os.path.basename(filename)
    save_path = os.path.join(cert_dir, safe_name)
    with open(save_path, "wb") as f:
        f.write(file_bytes)
    return save_path


def _read_key_file(path: str) -> str:
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return ""


# ─── Stage 1: Text Extraction ──────────────────────────────────

def extract_text_with_deepseek_ocr(image_path: str) -> str:
    """Use deepseek-ocr:3b via Ollama to extract text from an image.

    This model is purpose-built for OCR and handles certificates well.
    Returns extracted text string.
    """
    try:
        image_b64 = _encode_image_base64(image_path)

        payload = json.dumps({
            "model": OCR_MODEL,
            "prompt": "Extract ALL text from this certificate image. Return only the text, preserving the layout structure.",
            "images": [image_b64],
            "stream": False,
            "options": {"temperature": 0.1},
        }).encode()

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            text = data.get("response", "").strip()

        if text:
            logger.info("deepseek-ocr extracted %d characters", len(text))
        return text

    except Exception as e:
        logger.error("deepseek-ocr extraction failed: %s", e)
        return ""


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF using PyMuPDF (fitz). Returns raw text string."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF not installed — cannot extract text from PDF")
        return ""

    doc = fitz.open(pdf_path)
    text_parts = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            text_parts.append(text.strip())
    doc.close()

    # If digital text extraction yielded nothing, try rendering pages as images
    # and running deepseek-ocr on them (handles scanned PDFs)
    if not text_parts:
        logger.info("PDF has no digital text — trying OCR on rendered pages")
        return _ocr_pdf_pages(pdf_path)

    return "\n".join(text_parts)


def _ocr_pdf_pages(pdf_path: str) -> str:
    """Render PDF pages as images and run deepseek-ocr on each page."""
    try:
        import fitz
        import tempfile
    except ImportError:
        return ""

    doc = fitz.open(pdf_path)
    all_text = []

    for page_num in range(min(len(doc), 5)):  # cap at 5 pages
        page = doc[page_num]
        # Render at 200 DPI for good OCR quality
        mat = fitz.Matrix(200/72, 200/72)
        pix = page.get_pixmap(matrix=mat)
        img_path = tempfile.mktemp(suffix=".png")
        pix.save(img_path)

        text = extract_text_with_deepseek_ocr(img_path)
        if text:
            all_text.append(text)
        _safe_delete_file(img_path)

    doc.close()
    return "\n".join(all_text)


def extract_text_from_image_easyocr(image_path: str) -> list:
    """Fallback: Extract text using easyocr. Returns list of (text, confidence) tuples."""
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(['en'], gpu=False)
    results = _reader.readtext(image_path)
    return [(text, conf) for _, text, conf in results]


# ─── Stage 2: Structured Parsing ───────────────────────────────

def parse_with_ollama_llm(raw_text: str, model: str = LLM_PARSER_MODEL) -> Optional[dict]:
    """Send raw text to an Ollama model for structured CEU parsing.

    Uses the Ollama /api/chat endpoint with JSON mode.
    Returns structured dict or None on failure.
    """
    if not raw_text.strip():
        return None

    try:
        payload = json.dumps({
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": EXTRACTION_PROMPT,
                },
                {
                    "role": "user",
                    "content": f"--- Certificate Text ---\n{raw_text}",
                }
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }).encode()

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            response_text = (
                data.get("message", {})
                .get("content", "")
                .strip()
            )

        return _parse_llm_json(response_text)

    except Exception as e:
        logger.error("Ollama LLM parsing failed (%s): %s", model, e)
        return None


def parse_with_freellmapi(raw_text: str) -> Optional[dict]:
    """Fallback: Parse using FreeLLMAPI (gpt-oss-20b or similar text model)."""
    api_key = _read_key_file(FREELLMAPI_KEY_PATH)
    if not api_key:
        return None

    try:
        payload = json.dumps({
            "model": FREELLMAPI_TEXT_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": f"{EXTRACTION_PROMPT}\n\n--- Certificate Text ---\n{raw_text}",
                }
            ],
            "max_tokens": LLM_MAX_TOKENS,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }).encode()

        req = urllib.request.Request(
            FREELLMAPI_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            response_text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )

        return _parse_llm_json(response_text)

    except Exception as e:
        logger.error("FreeLLMAPI parsing failed: %s", e)
        return None


# ─── Cloud Vision (optional upgrade) ───────────────────────────

def extract_with_cloud_vision(image_path: str) -> Optional[dict]:
    """Send image directly to a cloud vision model. Only used if credits available.

    Tries OpenRouter (Gemini 2.5 Flash) — the best model for document parsing.
    Returns structured dict or None if unavailable.
    """
    api_key = _read_key_file(OPENROUTER_KEY_PATH)
    if not api_key:
        return None

    # Compress image for API call
    compressed_path = _compress_image(image_path)
    use_path = compressed_path if compressed_path != image_path else image_path
    mime_type = _get_mime_type(use_path)
    image_b64 = _encode_image_base64(use_path)
    if compressed_path != image_path:
        _safe_delete_file(compressed_path)

    try:
        payload = json.dumps({
            "model": CLOUD_VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_EXTRACTION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
                    ],
                }
            ],
            "max_tokens": LLM_MAX_TOKENS,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }).encode()

        req = urllib.request.Request(
            OPENROUTER_API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            response_text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )

        result = _parse_llm_json(response_text)
        if result:
            result["raw_text"] = ""
            logger.info("Cloud vision extraction succeeded (confidence: %s)", result.get("confidence"))
        return result

    except urllib.error.HTTPError as e:
        # 402 = no credits, 429 = rate limited — don't log as error, just skip
        if e.code in (402, 429):
            logger.info("Cloud vision unavailable (HTTP %s) — using local pipeline", e.code)
        else:
            logger.error("Cloud vision error: HTTP %s", e.code)
        return None
    except Exception as e:
        logger.error("Cloud vision failed: %s", e)
        return None


# ─── JSON parsing helper ───────────────────────────────────────

def _parse_llm_json(response_text: str) -> Optional[dict]:
    """Extract and validate JSON from an LLM response."""
    if not response_text or not response_text.strip():
        logger.warning("Empty LLM response")
        return None

    response_text = response_text.strip()

    # Strip markdown code fences if present
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        response_text = "\n".join(lines)

    # Find the JSON object in the response
    json_match = re.search(r"\{[^{}]*\}", response_text, re.DOTALL)
    if not json_match:
        logger.warning("Could not find JSON in LLM response: %s", response_text[:200])
        return None

    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM JSON: %s", e)
        return None

    return {
        "title": str(data.get("title", "")).strip() or "Unknown Course",
        "provider": str(data.get("provider", "")).strip() or "Unknown Provider",
        "credits": _safe_float(data.get("credits", 0)),
        "completion_date": _normalize_date_str(str(data.get("completion_date", "")).strip()),
        "category": _validate_category(str(data.get("category", "clinical")).strip().lower()),
        "confidence": _safe_float(data.get("confidence", 0.8), default=0.8),
    }


# ─── Main pipeline ─────────────────────────────────────────────

def process_certificate(image_path: str, cleanup: bool = True) -> dict:
    """Full OCR pipeline: extract CEU data from a certificate image or PDF.

    For images:
      1. Try cloud vision (Gemini 2.5 Flash via OpenRouter) — best quality, needs credits
      2. Local: deepseek-ocr:3b → glm-5.2:cloud for structured parsing
      3. Last resort: easyocr + regex parser (fully offline)

    For PDFs:
      1. PyMuPDF text extraction (digital text) or deepseek-ocr (scanned PDFs)
      2. glm-5.2:cloud for structured parsing
      3. Fallback: FreeLLMAPI (gpt-oss-20b) for parsing
      4. Last resort: regex parser

    By default, deletes the temporary certificate file after processing.
    Set cleanup=False to keep the file.
    """
    try:
        if is_pdf(image_path):
            return _process_pdf(image_path)
        else:
            return _process_image(image_path)
    finally:
        if cleanup:
            _safe_delete_file(image_path)


def _process_image(image_path: str) -> dict:
    """Process an image certificate."""
    # Stage 0: Try cloud vision first (best quality if credits available)
    cloud_result = extract_with_cloud_vision(image_path)
    if cloud_result:
        return cloud_result

    # Stage 1: Extract text with deepseek-ocr (local, purpose-built)
    raw_text = extract_text_with_deepseek_ocr(image_path)

    # Stage 2: Parse with LLM
    if raw_text.strip():
        # Primary: glm-5.2:cloud via Ollama
        result = parse_with_ollama_llm(raw_text)
        if result:
            result["raw_text"] = raw_text
            logger.info("Local pipeline succeeded: deepseek-ocr → %s", LLM_PARSER_MODEL)
            return result

        # Fallback: FreeLLMAPI text model
        result = parse_with_freellmapi(raw_text)
        if result:
            result["raw_text"] = raw_text
            logger.info("Fallback pipeline succeeded: deepseek-ocr → FreeLLMAPI")
            return result

    # Last resort: easyocr + regex (fully offline)
    logger.info("Local LLM unavailable — falling back to easyocr + regex")
    try:
        extracted = extract_text_from_image_easyocr(image_path)
        if extracted:
            return parse_with_regex(extracted)
    except Exception as e:
        logger.error("easyocr fallback failed: %s", e)

    return _empty_result()


def _process_pdf(pdf_path: str) -> dict:
    """Process a PDF certificate."""
    # Stage 1: Extract text (PyMuPDF for digital, deepseek-ocr for scanned)
    raw_text = extract_text_from_pdf(pdf_path)

    if not raw_text.strip():
        logger.warning("No text extracted from PDF")
        return _empty_result()

    # Stage 2: Parse with LLM
    # Primary: glm-5.2:cloud via Ollama
    result = parse_with_ollama_llm(raw_text)
    if result:
        result["raw_text"] = raw_text
        logger.info("PDF pipeline succeeded: PyMuPDF → %s", LLM_PARSER_MODEL)
        return result

    # Fallback: FreeLLMAPI
    result = parse_with_freellmapi(raw_text)
    if result:
        result["raw_text"] = raw_text
        logger.info("PDF fallback pipeline succeeded: PyMuPDF → FreeLLMAPI")
        return result

    # Last resort: regex parser
    logger.info("LLM unavailable — using regex fallback for PDF")
    # Convert to easyocr-style format for regex parser
    extracted = [(raw_text, 1.0)]
    return parse_with_regex(extracted)


def _empty_result() -> dict:
    return {
        "title": "Unknown Course",
        "provider": "Unknown Provider",
        "credits": 0.0,
        "completion_date": "",
        "category": "clinical",
        "confidence": 0.0,
        "raw_text": "",
    }


# ─── Backward-compatible functions ─────────────────────────────

def _raw_text_from_extracted(extracted: list) -> str:
    return ' '.join([text for text, _ in extracted])


def parse_ceu_data(extracted: list) -> dict:
    """Backward-compatible parser. Tries LLM first, falls back to regex."""
    raw_text = _raw_text_from_extracted(extracted)
    if not raw_text.strip():
        return _empty_result()

    result = parse_with_ollama_llm(raw_text)
    if result:
        result["raw_text"] = raw_text
        return result

    result = parse_with_freellmapi(raw_text)
    if result:
        result["raw_text"] = raw_text
        return result

    return parse_with_regex(extracted)


# ─── Regex fallback parser ─────────────────────────────────────

def parse_with_regex(extracted: list) -> dict:
    """Fallback regex-based parser. Extracts CEU fields from easyocr output."""
    raw_text_parts = [t for t, c in extracted]
    raw_text = "\n".join(raw_text_parts)
    avg_conf = sum(c for _, c in extracted) / len(extracted) if extracted else 0.0

    # Parse title
    title = ""
    for i, (text, conf) in enumerate(extracted):
        if re.search(r"(course|certificate|completion|continuing)", text, re.I):
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
        for text, conf in extracted:
            if len(text) > 15 and not re.search(
                r"(provider|date|credit|hour|ceu|authorized|verify|signature)", text, re.I
            ):
                title = text
                break

    if not title:
        title = "Unknown Course"

    title = re.sub(r"^(?:Title|Course|Course Title)\s*[:.]\s*", "", title, flags=re.I).strip()

    # Parse provider
    provider = ""
    for i, (text, conf) in enumerate(extracted):
        if re.search(r"(provider|presented by|sponsored by|approved by|offered by|issued by)", text, re.I):
            after_colon = text.split(":", 1)
            if len(after_colon) > 1 and after_colon[1].strip():
                provider = after_colon[1].strip()
            elif i + 1 < len(extracted):
                next_text = extracted[i + 1][0]
                if not re.search(r"(\d+(?:\.\d+)?)\s*(?:ceu|credit|hour|hr|CRCE|contact)", next_text, re.I) and \
                   not re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", next_text) and \
                   not re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", next_text, re.I):
                    provider = next_text
            break

    if not provider:
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

    # Parse credits
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

    # Parse completion date
    completion_date = ""
    date_patterns = [
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        r"((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
        r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
        r"\d{1,2},?\s+\d{4})",
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
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _normalize_date_str(raw: str) -> str:
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
    return _normalize_date_str(raw)


def _validate_category(category: str) -> str:
    valid = {"clinical", "safety", "ethics", "leadership"}
    if category in valid:
        return category
    for v in valid:
        if v in category:
            return v
    return "clinical"


def _detect_category(text: str) -> str:
    lower = text.lower()
    if any(kw in lower for kw in ["ethic", "bioethic", "professionalism", "integrity"]):
        return "ethics"
    if any(kw in lower for kw in ["safety", "infection", "cpr", "bls", "acls", "pals",
                                   "nrp", "emergency", "disaster", "hazard", "code", "crash"]):
        return "safety"
    if any(kw in lower for kw in ["leader", "management", "supervis", "admin", "director",
                                   "communication", "team", "conflict", "coaching"]):
        return "leadership"
    return "clinical"


# ─── Cleanup ───────────────────────────────────────────────────

def cleanup_old_temp_files(max_age_hours: int = 24) -> None:
    """Delete temporary certificate files older than max_age_hours."""
    import glob
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
    if not os.path.isdir(temp_dir):
        return
    cutoff = time.time() - (max_age_hours * 3600)
    for filepath in glob.glob(os.path.join(temp_dir, "*")):
        try:
            if os.path.getmtime(filepath) < cutoff:
                os.remove(filepath)
        except Exception:
            pass