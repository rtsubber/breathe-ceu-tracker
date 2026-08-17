"""FastAPI router for inbound CEU email webhooks.

Supports Resend Inbound format (and generic SMTP webhook payloads).
POST /api/email/ceu-webhook receives the email, parses CEU data, saves
certificate attachments, and creates a CEU record in the database.

All webhook endpoints are protected with HMAC-SHA256 signature verification
using BREATHE_WEBHOOK_SECRET. Resend uses Svix under the hood, so we verify
svix-signature headers. We also accept a simple resend-signature header for
non-Svix webhook configurations.
"""
import os
import sys
import hmac
import hashlib
import base64
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, get_db
from models import User, CEU, UserEmailAlias
from email_parser import parse_resend_inbound, save_attachments, parse_ceu_email
from datetime import datetime, date as date_type

logger = logging.getLogger("breathe.email_webhook")

router = APIRouter(prefix="/api/email", tags=["Email CEU Import"])


# ─── Webhook Signature Verification ─────────────────────────────

def _verify_webhook_signature(request: Request, raw_body: bytes) -> None:
    """Verify the HMAC-SHA256 signature of an incoming webhook request.

    Supports two signature schemes:
    1. Svix (used by Resend): headers svix-id, svix-timestamp, svix-signature
       Signature is HMAC-SHA256 of "{svix-id}.{svix-timestamp}.{raw_body}"
       encoded as base64, prefixed with "v1,".
    2. Simple resend-signature header: HMAC-SHA256 of raw_body as hex.

    Raises HTTPException(401) if signature is missing or invalid.
    Raises HTTPException(503) if BREATHE_WEBHOOK_SECRET is not configured.
    """
    secret = os.environ.get("BREATHE_WEBHOOK_SECRET")
    if not secret:
        logger.error("BREATHE_WEBHOOK_SECRET not set — rejecting webhook")
        raise HTTPException(
            status_code=503,
            detail="Webhook secret not configured. Set BREATHE_WEBHOOK_SECRET environment variable.",
        )

    secret_bytes = secret.encode("utf-8") if not secret.startswith("whsec_") else secret.encode("utf-8")

    # --- Try Svix-style verification (Resend's default) ---
    svix_signature = request.headers.get("svix-signature")
    svix_id = request.headers.get("svix-id", "")
    svix_timestamp = request.headers.get("svix-timestamp", "")

    if svix_signature:
        # Svix format: "v1,<base64-encoded-hmac>"
        # The signed message is: "{svix-id}.{svix-timestamp}.{raw_body}"
        signed_content = f"{svix_id}.{svix_timestamp}.".encode("utf-8") + raw_body

        # Extract all v1 signatures (there can be multiple, separated by spaces)
        signatures = []
        for part in svix_signature.split():
            if part.startswith("v1,"):
                signatures.append(part[3:])

        if not signatures:
            logger.warning("svix-signature present but no v1, prefix found")
            raise HTTPException(status_code=401, detail="Invalid signature format")

        # Compute expected HMAC-SHA256
        expected = base64.b64encode(
            hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
        ).decode("utf-8")

        # Compare against any provided signature using constant-time comparison
        verified = any(hmac.compare_digest(expected, sig) for sig in signatures)

        if not verified:
            logger.warning("Svix signature verification failed")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

        return  # Verified via Svix

    # --- Try simple resend-signature header ---
    simple_sig = request.headers.get("resend-signature")
    if simple_sig:
        expected = hmac.new(
            secret_bytes, raw_body, hashlib.sha256
        ).hexdigest()

        if hmac.compare_digest(expected, simple_sig):
            return  # Verified via simple signature

        logger.warning("resend-signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # --- No signature header at all ---
    logger.warning("No signature header found on webhook request")
    raise HTTPException(
        status_code=401,
        detail="Missing webhook signature. Expected svix-signature or resend-signature header.",
    )


# ─── Pydantic schemas ───────────────────────────────────────────

class AttachmentSchema(BaseModel):
    filename: Optional[str] = None
    name: Optional[str] = None
    content_type: Optional[str] = None
    contentType: Optional[str] = None
    content: Optional[str] = None
    data: Optional[str] = None

    class Config:
        from_attributes = True
        extra = "allow"  # accept unknown fields from various providers


class EmailWebhookPayload(BaseModel):
    """Resend Inbound / generic email webhook payload."""
    from_: Optional[str] = Field(None, alias="from")
    to: Optional[str] = None
    subject: Optional[str] = None
    text: Optional[str] = None
    html: Optional[str] = None
    attachments: Optional[list[AttachmentSchema]] = None

    class Config:
        from_attributes = True
        extra = "allow"  # accept unknown fields (headers, reply-to, etc.)


class CEUEmailResult(BaseModel):
    success: bool
    message: str
    ceu_id: Optional[int] = None
    user_id: Optional[int] = None
    title: Optional[str] = None
    provider: Optional[str] = None
    credits: Optional[float] = None
    completion_date: Optional[str] = None
    category: Optional[str] = None
    certificate_path: Optional[str] = None


class AliasCreate(BaseModel):
    """Create an email alias for a user."""
    user_id: int
    email_alias: str


class AliasOut(BaseModel):
    id: int
    user_id: int
    email_alias: str
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Helpers ────────────────────────────────────────────────────

def _resolve_user_by_alias(db: SessionLocal, to_email: str) -> Optional[User]:
    """Look up a user by their email alias (the 'to' address)."""
    if not to_email:
        return None
    # Normalize: strip, lowercase
    addr = to_email.strip().lower()
    alias = db.query(UserEmailAlias).filter(
        UserEmailAlias.email_alias == addr
    ).first()
    if alias:
        return alias.user
    return None


def _create_ceu_from_parsed(
    db: SessionLocal,
    user: User,
    parsed: dict,
    cert_paths: list[str],
) -> CEU:
    """Create and persist a CEU record from parsed email data."""
    # Parse completion date
    comp_date_str = parsed.get("completion_date")
    if comp_date_str:
        try:
            comp_date = datetime.strptime(comp_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            comp_date = date_type.today()
    else:
        comp_date = date_type.today()

    # Use first certificate path if available
    cert_path = cert_paths[0] if cert_paths else None

    ceu = CEU(
        user_id=user.id,
        title=parsed.get("title") or "Email-Imported CEU",
        provider=parsed.get("provider") or "Unknown Provider",
        credits=parsed.get("credits") or 0.0,
        completion_date=comp_date,
        category=parsed.get("category") or "clinical",
        certificate_path=cert_path,
        ocr_confidence=0.0,  # email import — no OCR
    )
    db.add(ceu)
    db.commit()
    db.refresh(ceu)
    return ceu


# ─── Endpoints ──────────────────────────────────────────────────

@router.post("/ceu-webhook", response_model=CEUEmailResult)
async def ceu_email_webhook(
    request: Request,
    db: SessionLocal = Depends(get_db),
):
    """Receive an inbound CEU email via Resend Inbound / SMTP webhook.

    Accepts JSON with: from, to, subject, text, html, attachments.

    The 'to' address is matched against user_email_aliases to find the
    owner. CEU data is parsed from the email body and a CEU record is
    created automatically.

    **Protected**: Requires valid HMAC-SHA256 signature in svix-signature
    or resend-signature header, verified against BREATHE_WEBHOOK_SECRET.
    """
    # Read raw body first for signature verification
    raw_body = await request.body()

    # Verify webhook signature (raises 401/503 on failure)
    _verify_webhook_signature(request, raw_body)

    # Parse JSON body (accept extra fields gracefully)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not payload:
        raise HTTPException(status_code=400, detail="Empty payload")

    # Normalize payload through our parser
    parsed = parse_resend_inbound(payload)

    to_email = parsed.get("recipient_email") or ""
    from_email = parsed.get("sender_email") or ""

    # Resolve user by alias
    user = _resolve_user_by_alias(db, to_email)
    if not user:
        logger.warning(f"No user found for alias: {to_email}")
        return CEUEmailResult(
            success=False,
            message=f"No user found for email alias: {to_email}",
        )

    # AARC-ONLY FILTER — only accept emails from AARC domains
    from_domain = from_email.split("@")[-1].lower() if "@" in from_email else ""
    AARC_DOMAINS = {"aarc.org", "aarc.com", "learning.aarc.org", "learnaarc.org", "rc.jchs.edu"}
    if from_domain not in AARC_DOMAINS:
        logger.info(f"Email import rejected — sender {from_email} not an AARC domain")
        return CEUEmailResult(
            success=False,
            message=f"Email import is currently limited to AARC emails. Sender domain '{from_domain}' is not recognized as AARC.",
            user_id=user.id,
        )

    # Pro tier check — email forwarding is a Pro feature
    if user.subscription_tier not in ("pro", "department"):
        logger.info(f"User {user.id} on '{user.subscription_tier}' tier — email forwarding requires Pro")
        return CEUEmailResult(
            success=False,
            message=(
                "Email forwarding requires Breathe Pro ($25/yr). "
                "Upgrade to unlock automatic CEU import from emails."
            ),
            user_id=user.id,
        )

    # Save certificate attachments
    attachments = payload.get("attachments") or []
    cert_paths = save_attachments(
        [att.model_dump() if hasattr(att, "model_dump") else dict(att) for att in attachments],
        user.id,
    )

    # Create the CEU record
    try:
        ceu = _create_ceu_from_parsed(db, user, parsed, cert_paths)
    except Exception as e:
        logger.error(f"Failed to create CEU: {e}", exc_info=True)
        db.rollback()
        return CEUEmailResult(
            success=False,
            message=f"Failed to create CEU: {str(e)}",
            user_id=user.id,
        )

    logger.info(
        f"CEU imported via email for user {user.id}: "
        f"'{ceu.title}' ({ceu.credits} cr) from {ceu.provider}"
    )

    return CEUEmailResult(
        success=True,
        message=f"CEU imported: {ceu.title} ({ceu.credits} credits)",
        ceu_id=ceu.id,
        user_id=user.id,
        title=ceu.title,
        provider=ceu.provider,
        credits=ceu.credits,
        completion_date=ceu.completion_date.isoformat() if ceu.completion_date else None,
        category=ceu.category,
        certificate_path=ceu.certificate_path,
    )


@router.post("/ceu-webhook/structured", response_model=CEUEmailResult)
async def ceu_email_webhook_structured(
    request: Request,
    db: SessionLocal = Depends(get_db),
):
    """Structured POST variant (JSON body validated by Pydantic).

    Same behavior as /ceu-webhook but with a strict schema.

    **Protected**: Requires valid HMAC-SHA256 signature in svix-signature
    or resend-signature header, verified against BREATHE_WEBHOOK_SECRET.
    """
    # Read raw body first for signature verification
    raw_body = await request.body()

    # Verify webhook signature (raises 401/503 on failure)
    _verify_webhook_signature(request, raw_body)

    # Parse and validate with Pydantic
    try:
        import json
        payload_dict = json.loads(raw_body)
        payload = EmailWebhookPayload.model_validate(payload_dict)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    raw = payload.model_dump(by_alias=True, exclude_none=True)
    parsed = parse_resend_inbound(raw)

    to_email = parsed.get("recipient_email") or ""
    user = _resolve_user_by_alias(db, to_email)
    if not user:
        return CEUEmailResult(
            success=False,
            message=f"No user found for email alias: {to_email}",
        )

    # Pro tier check — email forwarding is a Pro feature
    if user.subscription_tier not in ("pro", "department"):
        return CEUEmailResult(
            success=False,
            message=(
                "Email forwarding requires Breathe Pro ($25/yr). "
                "Upgrade to unlock automatic CEU import from emails."
            ),
            user_id=user.id,
        )

    atts_raw = []
    if payload.attachments:
        for a in payload.attachments:
            atts_raw.append(a.model_dump(exclude_none=True))

    cert_paths = save_attachments(atts_raw, user.id)

    try:
        ceu = _create_ceu_from_parsed(db, user, parsed, cert_paths)
    except Exception as e:
        db.rollback()
        return CEUEmailResult(
            success=False,
            message=f"Failed to create CEU: {str(e)}",
            user_id=user.id,
        )

    return CEUEmailResult(
        success=True,
        message=f"CEU imported: {ceu.title} ({ceu.credits} credits)",
        ceu_id=ceu.id,
        user_id=user.id,
        title=ceu.title,
        provider=ceu.provider,
        credits=ceu.credits,
        completion_date=ceu.completion_date.isoformat() if ceu.completion_date else None,
        category=ceu.category,
        certificate_path=ceu.certificate_path,
    )


@router.post("/aliases", response_model=AliasOut)
def create_email_alias(payload: AliasCreate, db: SessionLocal = Depends(get_db)):
    """Create an email alias for a user."""
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    alias = payload.email_alias.strip().lower()
    existing = db.query(UserEmailAlias).filter(
        UserEmailAlias.email_alias == alias
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Alias already exists")

    record = UserEmailAlias(user_id=payload.user_id, email_alias=alias)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/aliases", response_model=list[AliasOut])
def list_aliases(db: SessionLocal = Depends(get_db)):
    """List all email aliases."""
    return db.query(UserEmailAlias).all()


@router.get("/aliases/{user_id}", response_model=list[AliasOut])
def get_user_aliases(user_id: int, db: SessionLocal = Depends(get_db)):
    """Get email aliases for a specific user."""
    return db.query(UserEmailAlias).filter(UserEmailAlias.user_id == user_id).all()


def generate_alias_email(name: str) -> str:
    """Generate a unique email alias from a user's name.

    Format: firstname.lastname@sublettlabs.com
    """
    parts = name.lower().split()
    if len(parts) >= 2:
        local = f"{parts[0]}.{parts[-1]}"
    else:
        local = parts[0] if parts else "user"
    # Sanitize
    local = "".join(c for c in local if c.isalnum() or c == ".")
    return f"{local}@sublettlabs.com"