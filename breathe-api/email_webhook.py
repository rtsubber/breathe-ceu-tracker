"""FastAPI router for inbound CEU email webhooks.

Supports Resend Inbound format (and generic SMTP webhook payloads).
POST /api/email/ceu-webhook receives the email, parses CEU data, saves
certificate attachments, and creates a CEU record in the database.
"""
import os
import sys
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
    """
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
    payload: EmailWebhookPayload,
    db: SessionLocal = Depends(get_db),
):
    """Structured POST variant (JSON body validated by Pydantic).

    Same behavior as /ceu-webhook but with a strict schema.
    """
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