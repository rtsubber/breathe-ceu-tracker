"""Breathe API — FastAPI main application.

RT CEU + Competency Tracker API backend for clickable demo prototype.
"""
import os
import sys
import time
import uuid
import logging
from collections import defaultdict, deque

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger(__name__)

# Brute-force protection: track failed login attempts
_login_failures = defaultdict(list)  # email -> list of failure timestamps
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_MINUTES = 15

from datetime import date, datetime
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

from database import init_db, get_db, SessionLocal, DB_PATH, PasswordResetToken
from models import (
    User, License, CEU, Credential, Competency, StateRequirement,
    UserEmailAlias, Subscription, FreeCourseAlert,
    NBRCCredential, NBRCAssessment, NBRCCEPlan,
)
from auth import hash_password, verify_password, create_access_token, get_current_user, get_optional_user
from email_webhook import router as email_router, generate_alias_email
from audit import log_audit

# Initialize DB tables on import
init_db()

app = FastAPI(
    title="Breathe API",
    docs_url=None,       # Disable Swagger UI
    redoc_url=None,      # Disable ReDoc
    openapi_url=None,     # Disable OpenAPI schema exposure
)

# CORS — allow localhost:3000 (Next.js dev), custom domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "https://breathe.brandbooststudio.co",
        "https://breathe.sublettlabs.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include email webhook router
app.include_router(email_router)


# ─── Rate Limiting Middleware ───────────────────────────────────

class RateLimiter:
    """Simple in-memory rate limiter (per-IP, sliding window)."""

    def __init__(self):
        # Key: (ip, endpoint_group) -> deque of timestamps
        self._buckets: dict[tuple[str, str], deque] = defaultdict(deque)

    def check(self, ip: str, group: str, max_requests: int, window_seconds: int) -> bool:
        """Return True if request is allowed, False if rate-limited."""
        key = (ip, group)
        now = time.time()
        cutoff = now - window_seconds

        # Remove expired entries
        bucket = self._buckets[key]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= max_requests:
            return False

        bucket.append(now)
        return True


rate_limiter = RateLimiter()

# Rate limit thresholds
RATE_LIMIT_GENERAL = 60   # requests per minute per IP
RATE_LIMIT_OCR = 10        # requests per minute per IP (heavy operation)
RATE_LIMIT_WINDOW = 60     # seconds


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware: 60 req/min general, 10 req/min for OCR endpoint."""
    client_ip = request.client.host if request.client else "unknown"

    # Identify endpoint group
    path = request.url.path
    if "/ocr" in path:
        group = "ocr"
        max_req = RATE_LIMIT_OCR
    else:
        group = "general"
        max_req = RATE_LIMIT_GENERAL

    if not rate_limiter.check(client_ip, group, max_req, RATE_LIMIT_WINDOW):
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "detail": f"Too many requests. Limit: {max_req} requests per {RATE_LIMIT_WINDOW}s for {group} endpoints.",
                "retry_after": RATE_LIMIT_WINDOW,
            },
        )

    return await call_next(request)


# ─── Pydantic Schemas ──────────────────────────────────────────

class UserCreate(BaseModel):
    name: str
    email: str

class UserLogin(BaseModel):
    email: str

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class AuthResponse(BaseModel):
    user: "UserOut"
    token: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    created_at: datetime
    subscription_tier: str = "free"
    subscription_status: str = "active"
    onboarding_completed: bool = False

    class Config:
        from_attributes = True

class LicenseCreate(BaseModel):
    state: str
    license_type: str  # RRT / CRT / NPS
    license_number: str
    issue_date: Optional[date] = None
    expiry_date: date
    cycle_years: int = 2
    required_ceus: int = 30

class LicenseOut(BaseModel):
    id: int
    user_id: int
    state: str
    license_type: str
    license_number: str
    issue_date: Optional[date]
    expiry_date: date
    cycle_years: int
    required_ceus: int

    class Config:
        from_attributes = True

class CEUCreate(BaseModel):
    title: str
    provider: str
    credits: float
    completion_date: date
    category: str = "clinical"  # clinical/safety/ethics/leadership
    certificate_path: Optional[str] = None
    ocr_confidence: float = 0.0

class CEUOut(BaseModel):
    id: int
    user_id: int
    title: str
    provider: str
    credits: float
    completion_date: date
    category: str
    certificate_path: Optional[str]
    created_at: datetime
    ocr_confidence: float
    cebroker_synced: bool = False
    cebroker_synced_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class CredentialCreate(BaseModel):
    type: str  # RRT/CRT/NPS/ACLS/BLS/PALS/NRP
    expiry_date: date
    cycle_years: int = 2
    issuing_org: str  # NBRC/AHA/AAP

class CredentialOut(BaseModel):
    id: int
    user_id: int
    type: str
    expiry_date: date
    cycle_years: int
    issuing_org: str

    class Config:
        from_attributes = True

class CompetencyCreate(BaseModel):
    name: str
    category: str = "annual"  # annual/unit_specific
    frequency: str = "annual"  # annual/biannual/one_time
    status: str = "pending"  # pending/completed/overdue
    completed_date: Optional[date] = None
    evaluator: Optional[str] = None
    notes: Optional[str] = None

class CompetencyOut(BaseModel):
    id: int
    user_id: int
    name: str
    category: str
    frequency: str
    status: str
    completed_date: Optional[date]
    evaluator: Optional[str]
    notes: Optional[str]

    class Config:
        from_attributes = True

class StateRequirementOut(BaseModel):
    id: int
    state: str
    profession: str
    required_ceus: int
    cycle_years: int
    mandatory_topics: Optional[list]
    board_name: Optional[str] = None

    class Config:
        from_attributes = True

class ProgressOut(BaseModel):
    user_id: int
    total_earned: float
    required: int
    remaining: float
    on_track: bool
    days_to_renewal: int
    cycle_years: int
    expiry_date: Optional[str]
    percent_complete: float

class OCRResult(BaseModel):
    title: str
    provider: str
    credits: float
    completion_date: str
    confidence: float
    raw_text: str
    certificate_path: str


# ─── Feature Gating (Pro/Department tiers) ─────────────────────

PRO_FEATURES = {
    "ocr", "email_forwarding", "aarc_import", "browser_extension",
    "push_notifications", "nbrc_tracking", "multi_state", "sms_reminders",
    "free_course_alerts", "email_alerts",
}


def require_pro(user: User, feature: str):
    """Check if user has Pro access for a feature. Raises 403 if not."""
    if user.subscription_tier not in ("pro", "department"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "pro_required",
                "feature": feature,
                "message": f"{feature} requires Breathe Pro ($25/yr). Upgrade to unlock.",
                "upgrade_url": "/pricing",
            },
        )


# ─── Billing & Subscription Schemas ─────────────────────────────

class CreateCheckoutRequest(BaseModel):
    tier: str  # "pro" or "department"
    billing_cycle: str  # "monthly" or "yearly"

class SubscriptionOut(BaseModel):
    user_id: int
    tier: str
    status: str
    subscription_expires: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None

    class Config:
        from_attributes = True

class CancelSubscriptionRequest(BaseModel):
    user_id: int


# ─── SMS Reminder Schemas ──────────────────────────────────────

class SMSReminderRequest(BaseModel):
    phone: str
    message_type: str  # "renewal_warning", "deadline_approaching", "free_course"


# ─── Free Course Alert Schemas ─────────────────────────────────

class FreeCourseAlertCreate(BaseModel):
    course_title: str
    provider: str
    credits: float = 0.0
    url: Optional[str] = None
    source: str = "aarc"

class FreeCourseAlertOut(BaseModel):
    id: int
    user_id: int
    course_title: str
    provider: str
    credits: float
    url: Optional[str]
    source: str
    alert_date: date
    sent: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ─── AARC Import Schemas ────────────────────────────────────────

class AARCImportRequest(BaseModel):
    """Credentials for AARC Learning Network import."""
    email: Optional[str] = None
    password: Optional[str] = None
    use_mock: bool = True  # Fall back to mock data if scrape fails

class AARCCourseItem(BaseModel):
    """A single AARC course found during import."""
    title: str
    provider: str
    credits: float
    completion_date: str  # ISO YYYY-MM-DD
    category: str
    already_imported: bool = False  # True if CEU already exists in DB

class AARCPreviewResponse(BaseModel):
    """Result of AARC import preview — list of found courses."""
    source: str  # "aarc" or "mock"
    courses: List[AARCCourseItem]
    total_found: int
    new_count: int  # Courses not already in DB
    already_imported_count: int

class AARCConfirmRequest(BaseModel):
    """User selects which courses to import."""
    courses: List[AARCCourseItem]  # Selected courses to save

class AARCConfirmResponse(BaseModel):
    """Result of confirmed import."""
    imported: int  # Number of new CEUs saved
    skipped_duplicates: int  # Number skipped (already in DB)
    total_credits: float  # Total credits imported
    errors: List[str] = []


# ─── Auth Endpoints ─────────────────────────────────────────────

@app.post("/api/auth/register", response_model=AuthResponse, tags=["Auth"])
def register_user(payload: RegisterRequest, db: SessionLocal = Depends(get_db)):
    """Register a new user with email + password."""
    email = payload.email.lower().strip()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    if len(payload.password) < 8 or not any(c.isalpha() for c in payload.password) or not any(c.isdigit() for c in payload.password):
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters and include a letter and a number")

    # ─── Launch period workaround ─────────────────────────────────────
    # During the launch period all new signups receive Pro features for free.
    # Set LAUNCH_FREE_PRO=false (in .env or environment) once we start charging
    # for Pro — new signups will then get the standard free tier instead.
    # Existing users are unaffected by this flag; only new signups respect it.
    launch_free_pro = os.environ.get("LAUNCH_FREE_PRO", "true").lower() == "true"
    if launch_free_pro:
        logger.warning("⚠️ LAUNCH FREE PRO ACTIVE — all new signups get Pro free. Set LAUNCH_FREE_PRO=false when charging begins.")

    signup_tier = "pro" if launch_free_pro else "free"
    user = User(
        name=payload.name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        subscription_tier=signup_tier,
        subscription_status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Auto-create email alias for CEU forwarding
    try:
        from models import UserEmailAlias
        alias_email = generate_alias_email(user.name)
        # Ensure uniqueness
        existing = db.query(UserEmailAlias).filter(UserEmailAlias.email_alias == alias_email).first()
        if not existing:
            alias = UserEmailAlias(user_id=user.id, email_alias=alias_email)
            db.add(alias)
            db.commit()
            print(f"✅ Created email alias for user {user.id}: {alias_email}")
    except Exception as e:
        print(f"⚠️ Failed to create email alias for user {user.id}: {e}")

    # Audit log — register
    try:
        log_audit(db, user_id=user.id, action="register", entity_type="user", entity_id=user.id, details={"email": email, "name": payload.name.strip()})
    except Exception:
        pass

    token = create_access_token(user.id, user.email)
    return AuthResponse(user=UserOut.model_validate(user), token=token)


@app.post("/api/auth/login", response_model=AuthResponse, tags=["Auth"])
def login_user(payload: LoginRequest, db: SessionLocal = Depends(get_db)):
    """Login with email + password."""
    email = payload.email.lower().strip()

    # Brute-force protection: check if account is locked
    now = time.time()
    failures = _login_failures[email]
    # Prune failures older than the lock window
    cutoff = now - (LOGIN_LOCK_MINUTES * 60)
    _login_failures[email] = [t for t in failures if t > cutoff]
    if len(_login_failures[email]) >= LOGIN_MAX_FAILURES:
        remaining = int((_login_failures[email][0] + LOGIN_LOCK_MINUTES * 60 - now) / 60) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {remaining} minutes.",
        )

    user = db.query(User).filter(User.email == email).first()
    if not user or not user.password_hash:
        _login_failures[email].append(now)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(payload.password, user.password_hash):
        _login_failures[email].append(now)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Successful login — reset failure counter
    _login_failures.pop(email, None)

    # Audit log — login
    try:
        log_audit(db, user_id=user.id, action="login", entity_type="user", entity_id=user.id, details={"email": email})
    except Exception:
        pass

    token = create_access_token(user.id, user.email)
    return AuthResponse(user=UserOut.model_validate(user), token=token)


@app.get("/api/auth/me", response_model=UserOut, tags=["Auth"])
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user."""
    return current_user


@app.post("/api/auth/logout", tags=["Auth"])
def logout():
    """Logout — client just discards the token."""
    return {"success": True}


# ─── Password Reset ──────────────────────────────────────────────

@app.post("/api/auth/forgot-password", tags=["Auth"])
def forgot_password(payload: dict, db: SessionLocal = Depends(get_db)):
    """Send a password reset email if the account exists.
    
    Always returns 200 (no email enumeration). Rate limited: 3 resets/hr per email.
    """
    import hashlib, secrets, time as _time
    from datetime import timedelta
    
    email = (payload.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    
    # Rate limit: 3 resets per hour per email
    now = _time.time()
    key = f"pwreset:{email}"
    if key not in _login_failures:
        _login_failures[key] = []
    recent = [t for t in _login_failures[key] if now - t < 3600]
    if len(recent) >= 3:
        raise HTTPException(status_code=429, detail="Too many reset requests. Try again later.")
    _login_failures[key] = recent + [now]
    
    user = db.query(User).filter(User.email == email).first()
    
    # Always return success — no email enumeration
    if not user:
        return {"success": True, "message": "If an account with that email exists, a reset link has been sent."}
    
    # Generate token
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.utcnow() + timedelta(hours=1)
    
    # Invalidate old tokens for this user
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None)
    ).update({"used_at": datetime.utcnow()})
    
    # Store new token
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(reset_token)
    db.commit()
    
    # Send reset email via Resend
    resend_api_key = os.environ.get("RESEND_API_KEY")
    if resend_api_key:
        import requests as req
        reset_url = f"https://breathe.sublettlabs.com/reset-password?token={raw_token}"
        html = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px;">
          <h2 style="color: #1a1a1a;">Reset your Breathe password</h2>
          <p style="color: #666; font-size: 15px;">Hi {user.name},</p>
          <p style="color: #666; font-size: 15px;">We received a request to reset your password. Click the button below to set a new one:</p>
          <div style="text-align: center; margin: 32px 0;">
            <a href="{reset_url}" style="background: #6366f1; color: white; padding: 12px 32px; border-radius: 8px; text-decoration: none; font-weight: 600; display: inline-block;">Reset Password</a>
          </div>
          <p style="color: #999; font-size: 13px;">This link expires in 1 hour. If you didn't request this, you can safely ignore this email.</p>
          <p style="color: #999; font-size: 13px; margin-top: 24px;">— Breathe Team</p>
        </div>
        """
        text = f"Hi {user.name},\n\nReset your Breathe password: {reset_url}\n\nThis link expires in 1 hour. If you didn't request this, you can safely ignore this email.\n\n— Breathe Team"
        try:
            req.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": "Breathe <noreply@brandbooststudio.co>",
                    "to": [user.email],
                    "subject": "Reset your Breathe password",
                    "html": html,
                    "text": text,
                },
                timeout=10,
            )
        except Exception as e:
            logger.error(f"Failed to send reset email: {e}")
    
    return {"success": True, "message": "If an account with that email exists, a reset link has been sent."}


@app.post("/api/auth/reset-password", tags=["Auth"])
def reset_password(payload: dict, db: SessionLocal = Depends(get_db)):
    """Reset password using a token from the forgot-password email."""
    import hashlib
    
    token = (payload.get("token") or "").strip()
    new_password = (payload.get("new_password") or "")
    
    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Token and new password are required")
    
    if len(new_password) < 8 or not any(c.isalpha() for c in new_password) or not any(c.isdigit() for c in new_password):
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters and include a letter and a number")
    
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.used_at.is_(None),
    ).first()
    
    if not reset_token:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    if reset_token.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Reset token has expired")
    
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    
    # Update password
    user.password_hash = hash_password(new_password)
    reset_token.used_at = datetime.utcnow()
    db.commit()
    
    # Auto-login: return a fresh token
    jwt_token = create_access_token(user.id, user.email)
    return {
        "success": True,
        "message": "Password reset successfully",
        "token": jwt_token,
        "user": {"id": user.id, "name": user.name, "email": user.email},
    }


@app.post("/api/user/onboarding-complete", tags=["User"])
def complete_onboarding(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Mark onboarding as completed for the authenticated user."""
    current_user.onboarding_completed = True
    db.commit()
    db.refresh(current_user)
    return UserOut.model_validate(current_user)


# ─── User Endpoints ─────────────────────────────────────────────

@app.get("/api/me", response_model=UserOut, tags=["Users"])
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Get current user's profile (authenticated)."""
    return current_user


@app.get("/api/me/email-alias", tags=["Users"])
def get_my_email_alias(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Get the user's CEU forwarding email alias."""
    from models import UserEmailAlias
    aliases = db.query(UserEmailAlias).filter(UserEmailAlias.user_id == current_user.id).all()
    if not aliases:
        # Auto-create one if missing
        alias_email = generate_alias_email(current_user.name)
        existing = db.query(UserEmailAlias).filter(UserEmailAlias.email_alias == alias_email).first()
        if not existing:
            alias = UserEmailAlias(user_id=current_user.id, email_alias=alias_email)
            db.add(alias)
            db.commit()
            db.refresh(alias)
            aliases = [alias]
    return {
        "aliases": [{"id": a.id, "email_alias": a.email_alias} for a in aliases],
        "forwarding_address": aliases[0].email_alias if aliases else None,
        "instructions": "Forward your CEU confirmation emails to this address. Breathe will automatically parse and log them."
    }


# ─── License Endpoints ──────────────────────────────────────────

@app.post("/api/licenses", response_model=LicenseOut, tags=["Licenses"])
def add_license(payload: LicenseCreate, current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Add a license for the authenticated user."""
    user_id = current_user.id

    # Multi-state is a Pro feature: check if user already has a license in a different state
    existing_licenses = db.query(License).filter(License.user_id == user_id).all()
    if existing_licenses and any(l.state != payload.state for l in existing_licenses):
        require_pro(current_user, "multi_state")

    lic = License(user_id=user_id, **payload.model_dump())
    db.add(lic)
    db.commit()
    db.refresh(lic)

    # Audit log — license_create
    try:
        log_audit(db, user_id=user_id, action="license_create", entity_type="license", entity_id=lic.id, details={"state": payload.state, "license_type": payload.license_type, "license_number": payload.license_number})
    except Exception:
        pass

    return lic


@app.get("/api/licenses", response_model=List[LicenseOut], tags=["Licenses"])
def list_licenses(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """List all licenses for the authenticated user."""
    return db.query(License).filter(License.user_id == current_user.id).all()


# ─── CEU Endpoints ──────────────────────────────────────────────

@app.get("/api/ceus", response_model=List[CEUOut], tags=["CEUs"])
def list_ceus(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """List all CEUs for the authenticated user."""
    return db.query(CEU).filter(CEU.user_id == current_user.id).order_by(CEU.completion_date.desc()).all()


@app.post("/api/ceus", response_model=CEUOut, tags=["CEUs"])
def add_ceu(payload: CEUCreate, current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Add a CEU manually."""
    ceu = CEU(user_id=current_user.id, **payload.model_dump())
    db.add(ceu)
    db.commit()
    db.refresh(ceu)

    # Audit log — ceu_create
    try:
        log_audit(db, user_id=current_user.id, action="ceu_create", entity_type="ceu", entity_id=ceu.id, details={"title": ceu.title, "provider": ceu.provider, "credits": ceu.credits, "category": ceu.category})
    except Exception:
        pass

    return ceu


@app.delete("/api/ceus/{ceu_id}", tags=["CEUs"])
def delete_ceu(ceu_id: int, current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Delete a CEU record."""
    ceu = db.query(CEU).filter(CEU.id == ceu_id, CEU.user_id == current_user.id).first()
    if not ceu:
        raise HTTPException(status_code=404, detail="CEU not found")
    # Capture title before deletion for audit log
    ceu_title = ceu.title
    # Delete associated sync_log entries first to avoid NOT NULL constraint violation
    from models import CEBrokerSyncLog
    db.query(CEBrokerSyncLog).filter(CEBrokerSyncLog.ceu_id == ceu_id).delete()
    db.delete(ceu)
    db.commit()

    # Audit log — ceu_delete
    try:
        log_audit(db, user_id=current_user.id, action="ceu_delete", entity_type="ceu", entity_id=ceu_id, details={"title": ceu_title})
    except Exception:
        pass

    return {"success": True, "id": ceu_id}

@app.post("/api/ceus/ocr", response_model=OCRResult, tags=["CEUs"])
async def upload_certificate_ocr(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db),
):
    """Upload certificate image, run OCR, return extracted CEU data."""
    # OCR is a Pro feature
    require_pro(current_user, "ocr")

    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: JPEG, PNG, WebP, GIF, TIFF, PDF")

    # Read uploaded file
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    # Validate actual file bytes (magic numbers) — don't trust content-type header
    import filetype
    kind = filetype.guess(file_bytes)
    if kind is None:
        raise HTTPException(status_code=400, detail="Could not determine file type. Allowed: JPEG, PNG, WebP, GIF, PDF")
    allowed_mimes = {"image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"}
    if kind.mime not in allowed_mimes:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: JPEG, PNG, WebP, GIF, PDF")

    # Validate file size (10MB max)
    max_size = 10 * 1024 * 1024
    if len(file_bytes) > max_size:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")

    # Sanitize filename: strip path, generate safe name with uuid
    original_name = os.path.basename(file.filename or "certificate.png")
    ext = os.path.splitext(original_name)[1] or ".png"
    safe_filename = f"{uuid.uuid4().hex}{ext}"

    # Save certificate image
    from ocr import save_certificate_image, process_certificate
    save_path = save_certificate_image(file_bytes, safe_filename, current_user.id)

    # Run OCR
    try:
        result = process_certificate(save_path, cleanup=False)  # Don't delete the saved cert!
    except Exception as e:
        logger.exception("OCR processing failed")
        raise HTTPException(status_code=500, detail="OCR processing failed. Please try again with a clearer image.")

    result["certificate_path"] = save_path
    return result


# ─── Certificate File Serving ──────────────────────────────────

@app.get("/api/ceus/{ceu_id}/certificate", tags=["CEUs"])
def get_certificate_file(
    ceu_id: int,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db),
):
    """Serve the certificate file attached to a CEU."""
    ceu = db.query(CEU).filter(CEU.id == ceu_id, CEU.user_id == current_user.id).first()
    if not ceu:
        raise HTTPException(status_code=404, detail="CEU not found")
    if not ceu.certificate_path:
        raise HTTPException(status_code=404, detail="No certificate attached to this CEU")
    if not os.path.exists(ceu.certificate_path):
        raise HTTPException(status_code=404, detail="Certificate file not found on disk")
    
    ext = os.path.splitext(ceu.certificate_path)[1].lower()
    content_types = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    content_type = content_types.get(ext, "application/octet-stream")
    
    with open(ceu.certificate_path, "rb") as f:
        file_bytes = f.read()
    
    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{os.path.basename(ceu.certificate_path)}"'},
    )


# ─── Credential Endpoints ───────────────────────────────────────

@app.get("/api/credentials", response_model=List[CredentialOut], tags=["Credentials"])
def list_credentials(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """List credentials (NBRC + certifications) for the authenticated user."""
    return db.query(Credential).filter(Credential.user_id == current_user.id).all()


@app.post("/api/credentials", response_model=CredentialOut, tags=["Credentials"])
def add_credential(payload: CredentialCreate, current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Add a credential for the authenticated user."""
    cred = Credential(user_id=current_user.id, **payload.model_dump())
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred


@app.put("/api/credentials/{cred_id}", response_model=CredentialOut, tags=["Credentials"])
def update_credential(cred_id: int, payload: CredentialCreate, current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Update a credential for the authenticated user."""
    cred = db.query(Credential).filter(Credential.id == cred_id, Credential.user_id == current_user.id).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    for key, value in payload.model_dump().items():
        setattr(cred, key, value)
    db.commit()
    db.refresh(cred)
    return cred


@app.delete("/api/credentials/{cred_id}", tags=["Credentials"])
def delete_credential(cred_id: int, current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Delete a credential for the authenticated user."""
    cred = db.query(Credential).filter(Credential.id == cred_id, Credential.user_id == current_user.id).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    db.delete(cred)
    db.commit()
    return {"success": True, "id": cred_id}


# ─── Competency Endpoints ───────────────────────────────────────

@app.get("/api/competencies", response_model=List[CompetencyOut], tags=["Competencies"])
def list_competencies(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """List competencies for the authenticated user."""
    return db.query(Competency).filter(Competency.user_id == current_user.id).all()


@app.post("/api/competencies", response_model=CompetencyOut, tags=["Competencies"])
def add_competency(payload: CompetencyCreate, current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Add a competency for the authenticated user."""
    comp = Competency(user_id=current_user.id, **payload.model_dump())
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


# ─── Progress Endpoint ──────────────────────────────────────────

@app.get("/api/progress", tags=["Progress"])
def get_progress(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Calculate CEU progress for the authenticated user."""
    user_id = current_user.id

    # Get primary license for required CEUs / cycle
    lic = db.query(License).filter(License.user_id == user_id).first()
    if not lic:
        # No license yet — return empty progress so dashboard doesn't crash
        return {
            "user_id": user_id,
            "total_earned": 0.0,
            "required": 0,
            "remaining": 0.0,
            "on_track": True,
            "days_to_renewal": 0,
            "cycle_years": 2,
            "expiry_date": None,
            "percent_complete": 0.0,
        }

    # Sum all CEU credits
    ceus = db.query(CEU).filter(CEU.user_id == user_id).all()
    total_earned = sum(c.credits for c in ceus)
    required = lic.required_ceus
    remaining = max(0.0, required - total_earned)

    # Days to renewal
    today = date.today()
    days_to_renewal = (lic.expiry_date - today).days if lic.expiry_date else 0

    # On-track: need to earn remaining CEUs in remaining time
    # Calculate required pace: should have earned proportional to time elapsed in cycle
    cycle_start = lic.issue_date or lic.expiry_date.replace(year=lic.expiry_date.year - lic.cycle_years)
    total_cycle_days = (lic.expiry_date - cycle_start).days
    elapsed_days = (today - cycle_start).days
    elapsed_fraction = max(0.0, min(1.0, elapsed_days / total_cycle_days)) if total_cycle_days > 0 else 0.0
    expected_earned = required * elapsed_fraction
    on_track = total_earned >= expected_earned

    percent_complete = round((total_earned / required * 100), 1) if required > 0 else 0.0

    return ProgressOut(
        user_id=user_id,
        total_earned=round(total_earned, 1),
        required=required,
        remaining=round(remaining, 1),
        on_track=on_track,
        days_to_renewal=days_to_renewal,
        cycle_years=lic.cycle_years,
        expiry_date=lic.expiry_date.isoformat() if lic.expiry_date else None,
        percent_complete=percent_complete,
    )


# ─── CE Compliance Report Endpoint ─────────────────────────────

@app.get("/api/ce-report", tags=["Reports"])
def generate_ce_report_endpoint(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Generate CE Compliance Report PDF for the authenticated user.

    Dynamically shows the correct state licensing board name based on the
    user's primary license state. Works for all 50 states + DC.
    """
    user_id = current_user.id
    from ce_report import generate_ce_report as gen_report
    try:
        pdf_bytes = gen_report(db, user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

    filename = f"ce_compliance_report_user_{user_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── Legacy TMB Report Endpoint (redirects to CE Report) ───────

@app.get("/api/tmb-report", tags=["Reports"], include_in_schema=False)
def tmb_report_legacy_redirect(current_user: User = Depends(get_current_user)):
    """Backward compatibility: redirect old TMB report endpoint to CE report."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/api/ce-report", status_code=307)


# ─── State Requirements Endpoint ────────────────────────────────

@app.get("/api/states", response_model=List[StateRequirementOut], tags=["States"])
def list_state_requirements(db: SessionLocal = Depends(get_db)):
    """List all state requirements."""
    return db.query(StateRequirement).all()


# ─── AARC Import Endpoints ─────────────────────────────────────

@app.post(
    "/api/import/aarc",
    response_model=AARCPreviewResponse,
    tags=["Import"],
    summary="Import CE courses from AARC Learning Network",
    description=(
        "Scrapes completed courses from AARC Learning Network using provided credentials. "
        "Falls back to mock data if credentials are missing or scraping fails (use_mock=True). "
        "Returns preview of found courses with duplicate detection."
    ),
)
def import_aarc(
    payload: AARCImportRequest,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db),
):
    """Scrape AARC Learning Network for completed CE courses (authenticated)."""
    user_id = current_user.id

    # AARC import is a Pro feature
    require_pro(current_user, "aarc_import")

    from aarc_import import scrape_aarc_or_mock, get_mock_aarc_courses

    source = "aarc"
    courses_data: list[dict] = []

    if payload.email and payload.password:
        # Attempt real scrape
        try:
            courses_data = scrape_aarc_or_mock(
                email=payload.email,
                password=payload.password,
                use_mock_on_failure=payload.use_mock,
            )
            # If we fell back to mock, source might be "mock"
            if not payload.email:
                source = "mock"
        except Exception as e:
            if payload.use_mock:
                courses_data = get_mock_aarc_courses()
                source = "mock"
            else:
                raise HTTPException(
                    status_code=502,
                    detail=f"AARC scraping failed: {str(e)}",
                )
    else:
        # No credentials — use mock data
        courses_data = get_mock_aarc_courses()
        source = "mock"

    # Get existing CEUs for this user to detect duplicates
    existing_ceus = db.query(CEU).filter(CEU.user_id == user_id).all()
    existing_titles = {
        ceu.title.strip().lower() for ceu in existing_ceus
    }

    # Build response with duplicate detection
    course_items: list[AARCCourseItem] = []
    for c in courses_data:
        already = c["title"].strip().lower() in existing_titles
        course_items.append(AARCCourseItem(
            title=c["title"],
            provider=c["provider"],
            credits=c["credits"],
            completion_date=c["completion_date"],
            category=c["category"],
            already_imported=already,
        ))

    new_count = sum(1 for c in course_items if not c.already_imported)
    already_count = sum(1 for c in course_items if c.already_imported)

    return AARCPreviewResponse(
        source=source,
        courses=course_items,
        total_found=len(course_items),
        new_count=new_count,
        already_imported_count=already_count,
    )


@app.get(
    "/api/import/aarc/preview",
    response_model=AARCPreviewResponse,
    tags=["Import"],
    summary="Preview AARC courses (mock or real)",
    description=(
        "Returns a preview of AARC courses available for import. "
        "Without credentials, returns mock data. Pass email/password as query params "
        "to attempt a real AARC scrape."
    ),
)
def preview_aarc(
    email: Optional[str] = Query(None, description="AARC account email"),
    password: Optional[str] = Query(None, description="AARC account password"),
    use_mock: bool = Query(True, description="Fall back to mock if scrape fails"),
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db),
):
    """Preview AARC import — GET version for frontend convenience (authenticated)."""
    payload = AARCImportRequest(email=email, password=password, use_mock=use_mock)
    return import_aarc(payload, current_user, db)


@app.post(
    "/api/import/aarc/confirm",
    response_model=AARCConfirmResponse,
    tags=["Import"],
    summary="Confirm and save selected AARC courses as CEUs",
    description=(
        "Saves the user-selected AARC courses as CEU records in the database. "
        "Skips duplicates (courses already in DB by title match). "
        "Returns count of imported, skipped, and total credits added."
    ),
)
def confirm_aarc_import(
    payload: AARCConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db),
):
    """Save confirmed AARC courses as CEUs in the database (authenticated)."""
    user_id = current_user.id

    # AARC import is a Pro feature
    require_pro(current_user, "aarc_import")

    if not payload.courses:
        return AARCConfirmResponse(
            imported=0,
            skipped_duplicates=0,
            total_credits=0.0,
            errors=["No courses selected for import"],
        )

    # Get existing CEU titles for this user (case-insensitive dedup)
    existing_ceus = db.query(CEU).filter(CEU.user_id == user_id).all()
    existing_titles = {ceu.title.strip().lower() for ceu in existing_ceus}

    imported = 0
    skipped = 0
    total_credits = 0.0
    errors: list[str] = []

    for course in payload.courses:
        try:
            title_key = course.title.strip().lower()
            if title_key in existing_titles:
                skipped += 1
                continue

            # Parse date from ISO string
            from datetime import date as date_type
            try:
                comp_date = date_type.fromisoformat(course.completion_date)
            except (ValueError, TypeError):
                comp_date = date_type.today()

            ceu = CEU(
                user_id=user_id,
                title=course.title,
                provider=course.provider,
                credits=course.credits,
                completion_date=comp_date,
                category=course.category,
                certificate_path=None,
                ocr_confidence=0.0,
            )
            db.add(ceu)
            existing_titles.add(title_key)  # Prevent dup within same batch
            imported += 1
            total_credits += course.credits

        except Exception as e:
            errors.append(f"Failed to import '{course.title}': {str(e)}")

    db.commit()

    return AARCConfirmResponse(
        imported=imported,
        skipped_duplicates=skipped,
        total_credits=round(total_credits, 1),
        errors=errors,
    )


# ─── Stripe Billing Endpoints ─────────────────────────────────

@app.post("/api/billing/checkout", tags=["Billing"])
def create_checkout_session(payload: CreateCheckoutRequest, current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Create Stripe Checkout session for Pro/Department subscription."""
    stripe_secret_key = os.environ.get("STRIPE_SECRET_KEY")
    if not stripe_secret_key:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "billing_not_configured",
                "message": "Stripe is not configured on this server. Set STRIPE_SECRET_KEY environment variable.",
            },
        )

    try:
        import stripe
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="stripe package not installed. Run: pip install stripe",
        )

    stripe.api_key = stripe_secret_key

    # Determine price ID based on tier and billing cycle
    # Department is monthly only — force monthly if yearly requested
    billing_cycle = payload.billing_cycle
    if payload.tier == "department":
        billing_cycle = "monthly"  # Department is monthly only

    price_map = {
        ("pro", "monthly"): os.environ.get("STRIPE_PRICE_PRO_MONTHLY"),
        ("pro", "yearly"): os.environ.get("STRIPE_PRICE_PRO_YEARLY"),
        ("department", "monthly"): os.environ.get("STRIPE_PRICE_DEPT_MONTHLY"),
    }

    price_key = (payload.tier, billing_cycle)
    price_id = price_map.get(price_key)

    if not price_id:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier/billing cycle combination: {payload.tier}/{payload.billing_cycle}",
        )

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=os.environ.get(
                "STRIPE_SUCCESS_URL",
                "https://breathe.sublettlabs.com/billing/success",
            ),
            cancel_url=os.environ.get(
                "STRIPE_CANCEL_URL",
                "https://breathe.sublettlabs.com/pricing",
            ),
            client_reference_id=str(current_user.id),
            customer_email=current_user.email,
            metadata={"tier": payload.tier, "billing_cycle": billing_cycle, "user_id": str(current_user.id)},
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe checkout failed: {str(e)}")


@app.post("/api/billing/webhook", tags=["Billing"])
async def stripe_webhook(request: Request, db: SessionLocal = Depends(get_db)):
    """Handle Stripe webhooks: checkout.session.completed, customer.subscription.updated, customer.subscription.deleted."""
    stripe_secret_key = os.environ.get("STRIPE_SECRET_KEY")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

    if not stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    try:
        import stripe
    except ImportError:
        raise HTTPException(status_code=503, detail="stripe package not installed")

    stripe.api_key = stripe_secret_key

    body = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(body, sig_header, webhook_secret)
        else:
            # No webhook secret configured — reject all webhooks
            raise HTTPException(status_code=503, detail="Stripe webhook secret not configured")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid webhook payload: {str(e)}")

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        # Extract tier and user_id from metadata/client_reference_id
        tier = data.get("metadata", {}).get("tier", "pro")
        customer_id = data.get("customer")
        subscription_id = data.get("subscription")
        client_ref_id = data.get("client_reference_id")
        
        # Find the user by ID from client_reference_id
        user_id = int(client_ref_id) if client_ref_id else 0
        user = db.query(User).filter(User.id == user_id).first() if user_id else None
        
        if user:
            # Upgrade the user's subscription tier
            user.subscription_tier = tier
            user.subscription_status = "active"
            user.stripe_customer_id = customer_id
            
            # Create/update subscription record
            existing_sub = db.query(Subscription).filter(
                Subscription.user_id == user.id,
                Subscription.status == "active",
            ).first()
            if existing_sub:
                existing_sub.stripe_customer_id = customer_id
                existing_sub.stripe_subscription_id = subscription_id
                existing_sub.tier = tier
            else:
                sub = Subscription(
                    user_id=user.id,
                    tier=tier,
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=subscription_id,
                    status="active",
                )
                db.add(sub)
            db.commit()

    elif event_type == "customer.subscription.updated":
        subscription_id = data.get("id")
        status = data.get("status", "active")
        current_period_end = data.get("current_period_end")

        sub = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == subscription_id
        ).first()
        if sub:
            sub.status = status
            if current_period_end:
                sub.current_period_end = datetime.utcfromtimestamp(current_period_end)
            db.commit()

    elif event_type == "customer.subscription.deleted":
        subscription_id = data.get("id")
        sub = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == subscription_id
        ).first()
        if sub:
            sub.status = "canceled"
            # Downgrade user to free
            user = db.query(User).filter(User.id == sub.user_id).first()
            if user:
                user.subscription_tier = "free"
                user.subscription_status = "canceled"
            db.commit()

    return {"received": True}


@app.get("/api/subscription", response_model=SubscriptionOut, tags=["Billing"])
def get_subscription(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Get current subscription status for the authenticated user."""
    return SubscriptionOut(
        user_id=current_user.id,
        tier=current_user.subscription_tier or "free",
        status=current_user.subscription_status or "active",
        subscription_expires=current_user.subscription_expires,
        stripe_customer_id=current_user.stripe_customer_id,
    )


@app.post("/api/billing/cancel", tags=["Billing"])
def cancel_subscription(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Cancel subscription for the authenticated user (downgrade to free at period end)."""
    user = current_user

    stripe_secret_key = os.environ.get("STRIPE_SECRET_KEY")

    if stripe_secret_key and user.stripe_customer_id:
        try:
            import stripe
            stripe.api_key = stripe_secret_key

            # Find active subscription for customer
            subs = stripe.Subscription.list(customer=user.stripe_customer_id, status="active")
            for s in subs.data:
                stripe.Subscription.modify(s.id, cancel_at_period_end=True)
        except Exception:
            # Log but don't fail — we still update local state
            pass

    # Update local state
    user.subscription_status = "canceled"
    if user.subscription_expires:
        # Will downgrade at expiry
        pass
    else:
        # No expiry info — downgrade now
        user.subscription_tier = "free"

    # Update subscription record
    sub = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status == "active",
    ).first()
    if sub:
        sub.status = "canceled"

    db.commit()
    return {"success": True, "message": "Subscription canceled. You'll be downgraded to Free at period end."}


# ─── SMS Reminder Endpoint (Pro feature) ───────────────────────

@app.post("/api/sms-reminder", tags=["SMS"])
def send_sms_reminder(payload: SMSReminderRequest, current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Send SMS reminder (Pro only). Uses Twilio."""
    user = current_user
    user_id = user.id

    require_pro(user, "sms_reminders")

    # Twilio credentials from env
    twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
    twilio_from = os.environ.get("TWILIO_PHONE_NUMBER")

    if not all([twilio_sid, twilio_token, twilio_from]):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "sms_not_configured",
                "message": "Twilio is not configured on this server. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER environment variables.",
            },
        )

    # Build message based on type
    message_templates = {
        "renewal_warning": f"Hi {user.name}, your RT license renewal deadline is approaching. Check your CEU progress in Breathe.",
        "deadline_approaching": f"Hi {user.name}, you have a CEU deadline coming soon. Log in to Breathe to check your progress.",
        "free_course": f"Hi {user.name}, a new free CEU course was found! Check the Breathe app for details.",
    }

    message_body = message_templates.get(payload.message_type, f"Breathe reminder: {payload.message_type}")

    try:
        from twilio.rest import Client
        client = Client(twilio_sid, twilio_token)
        message = client.messages.create(
            body=message_body,
            from_=twilio_from,
            to=payload.phone,
        )
        return {"success": True, "message_sid": message.sid, "message_type": payload.message_type}
    except ImportError:
        raise HTTPException(status_code=503, detail="twilio package not installed. Run: pip install twilio")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SMS send failed: {str(e)}")


# ─── Email Alert Endpoint (Pro feature) ────────────────────────

@app.post("/api/email-alert", tags=["Email"])
def send_email_alert(payload: dict, current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Send email alert (Pro only). Uses Resend API."""
    user = current_user
    require_pro(user, "email_alerts")

    alert_type = payload.get("alert_type", "deadline_approaching")
    recipient = payload.get("email", user.email)
    license_state = payload.get("license_state", "")
    license_expiry = payload.get("license_expiry", "")
    ceus_completed = payload.get("ceus_completed", 0)
    ceus_required = payload.get("ceus_required", 0)
    ceus_remaining = ceus_required - ceus_completed

    # Build email content based on alert type
    if alert_type == "renewal_warning":
        subject = f"⏰ Breathe Alert: Your {license_state} RT license expires {license_expiry}"
        html_body = f"""
        <div style="font-family: sans-serif; max-width: 560px; margin: 0 auto;">
            <h2 style="color: #003e54;">⏰ License Renewal Warning</h2>
            <p>Hi {user.name},</p>
            <p>Your <strong>{license_state} RT license</strong> expires on <strong>{license_expiry}</strong>.</p>
            <p>Here's your CEU progress:</p>
            <table style="border-collapse: collapse; margin: 16px 0;">
                <tr><td style="padding: 8px 16px; background: #f0f0f0;">Completed</td><td style="padding: 8px 16px;">{ceus_completed} CEUs</td></tr>
                <tr><td style="padding: 8px 16px; background: #f0f0f0;">Required</td><td style="padding: 8px 16px;">{ceus_required} CEUs</td></tr>
                <tr><td style="padding: 8px 16px; background: #fff3cd; font-weight: bold;">Remaining</td><td style="padding: 8px 16px; font-weight: bold; color: {'#dc3545' if ceus_remaining > 0 else '#28a745'};">{ceus_remaining} CEUs</td></tr>
            </table>
            <p>{'You still need ' + str(ceus_remaining) + ' more CEUs before renewal. Do not wait!' if ceus_remaining > 0 else 'You have met your CEU requirement. You are ready to renew!'}</p>
            <p><a href="https://breathe.sublettlabs.com" style="display: inline-block; padding: 12px 24px; background: #003e54; color: white; text-decoration: none; border-radius: 6px;">View Your Progress</a></p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
            <p style="color: #999; font-size: 12px;">Breathe — CEU Tracker for Respiratory Therapists<br>breathe.sublettlabs.com</p>
        </div>
        """
        text_body = f"Hi {user.name},\n\nYour {license_state} RT license expires on {license_expiry}.\n\nCEU Progress:\n- Completed: {ceus_completed}\n- Required: {ceus_required}\n- Remaining: {ceus_remaining}\n\n{'You still need ' + str(ceus_remaining) + ' more CEUs. Do not wait!' if ceus_remaining > 0 else 'You have met your CEU requirement. Ready to renew!'}\n\nView your progress: https://breathe.sublettlabs.com\n\nBreathe — CEU Tracker for Respiratory Therapists"

    elif alert_type == "deadline_approaching":
        subject = f"📢 Breathe: CEU deadline approaching for {license_state}"
        html_body = f"""
        <div style="font-family: sans-serif; max-width: 560px; margin: 0 auto;">
            <h2 style="color: #003e54;">📢 CEU Deadline Approaching</h2>
            <p>Hi {user.name},</p>
            <p>Your CEU deadline for <strong>{license_state}</strong> is approaching. Your license expires <strong>{license_expiry}</strong>.</p>
            <p>You have <strong>{ceus_remaining} CEUs</strong> remaining to complete.</p>
            <p>Log in to Breathe to track your progress and find free CEU courses.</p>
            <p><a href="https://breathe.sublettlabs.com" style="display: inline-block; padding: 12px 24px; background: #003e54; color: white; text-decoration: none; border-radius: 6px;">Check Your Progress</a></p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
            <p style="color: #999; font-size: 12px;">Breathe — CEU Tracker for Respiratory Therapists<br>breathe.sublettlabs.com</p>
        </div>
        """
        text_body = f"Hi {user.name},\n\nYour CEU deadline for {license_state} is approaching. License expires {license_expiry}.\n\nYou have {ceus_remaining} CEUs remaining.\n\nCheck your progress: https://breathe.sublettlabs.com\n\nBreathe — CEU Tracker for Respiratory Therapists"

    elif alert_type == "free_course":
        course_title = payload.get("course_title", "")
        course_provider = payload.get("course_provider", "")
        course_credits = payload.get("course_credits", "")
        course_url = payload.get("course_url", "https://breathe.sublettlabs.com")
        subject = f"🎓 Breathe: New free CEU course available!"
        html_body = f"""
        <div style="font-family: sans-serif; max-width: 560px; margin: 0 auto;">
            <h2 style="color: #003e54;">🎓 Free CEU Course Found!</h2>
            <p>Hi {user.name},</p>
            <p>A new free CEU course is available:</p>
            <div style="background: #f8f9fa; padding: 16px; border-radius: 8px; margin: 16px 0;">
                <p style="margin: 0 0 8px; font-weight: bold; font-size: 16px;">{course_title}</p>
                <p style="margin: 0 0 4px; color: #666;">Provider: {course_provider}</p>
                <p style="margin: 0; color: #666;">Credits: {course_credits}</p>
            </div>
            <p><a href="{course_url}" style="display: inline-block; padding: 12px 24px; background: #003e54; color: white; text-decoration: none; border-radius: 6px;">View Course</a></p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
            <p style="color: #999; font-size: 12px;">Breathe — CEU Tracker for Respiratory Therapists<br>breathe.sublettlabs.com</p>
        </div>
        """
        text_body = f"Hi {user.name},\n\nFree CEU course available:\n\n{course_title}\nProvider: {course_provider}\nCredits: {course_credits}\n\nView course: {course_url}\n\nBreathe — CEU Tracker for Respiratory Therapists"

    else:
        subject = f"Breathe Alert: {alert_type}"
        html_body = f"<p>Hi {user.name},</p><p>You have a Breathe alert: {alert_type}</p><p><a href=\"https://breathe.sublettlabs.com\">View your dashboard</a></p>"
        text_body = f"Hi {user.name},\n\nBreathe alert: {alert_type}\n\nhttps://breathe.sublettlabs.com"

    # Send via Resend API
    resend_api_key = os.environ.get("RESEND_API_KEY")
    if not resend_api_key:
        raise HTTPException(status_code=503, detail={
            "error": "email_not_configured",
            "message": "Resend API key not set. Set RESEND_API_KEY environment variable."
        })

    try:
        import requests as req
        resp = req.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": "Breathe <alerts@brandbooststudio.co>",
                "to": [recipient],
                "subject": subject,
                "html": html_body,
                "text": text_body,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return {"success": True, "message_id": resp.json().get("id", ""), "alert_type": alert_type, "sent_to": recipient}
        else:
            raise HTTPException(status_code=502, detail=f"Email send failed: {resp.text[:200]}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Email send failed: {str(e)}")


@app.post("/api/admin/send-deadline-alerts", tags=["Admin"])
def send_deadline_alerts_cron(api_key: str = Query(None)):
    """Cron-friendly endpoint: check all users for upcoming license deadlines and send email alerts.

    Sends alerts at: 90 days, 60 days, 30 days, 14 days, and 7 days before expiry.
    Only sends to Pro users with email_alerts feature access.
    Skips users who already received an alert for the same deadline window.

    Call via cron: curl -s 'http://localhost:8000/api/admin/send-deadline-alerts?api_key=...'
    """
    ADMIN_KEY = os.environ.get("BREATHE_ADMIN_KEY", "")
    if ADMIN_KEY and api_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    from datetime import date, timedelta
    import sqlite3 as sq

    conn = sq.connect(DB_PATH)
    conn.row_factory = sq.Row
    today = date.today()
    alert_windows = [90, 60, 30, 14, 7]
    alerts_sent = 0
    errors = 0

    # Get all Pro users with active licenses
    users = conn.execute("""
        SELECT u.id, u.name, u.email, u.subscription_tier,
               l.id as license_id, l.state, l.expiry_date, l.required_ceus, l.license_type
        FROM users u
        JOIN licenses l ON u.id = l.user_id
        WHERE u.subscription_tier IN ('pro', 'department')
          AND u.subscription_status = 'active'
    """).fetchall()

    for u in users:
        expiry = date.fromisoformat(u["expiry_date"])
        days_until = (expiry - today).days

        # Check if we're in an alert window
        if days_until not in alert_windows:
            continue

        # Count completed CEUs for this license's cycle
        cycle_start = expiry - timedelta(days=365 * 2)  # approximate cycle
        ceus = conn.execute("""
            SELECT SUM(credits) as total FROM ceus
            WHERE user_id = ? AND completion_date >= ? AND completion_date <= ?
        """, (u["id"], cycle_start.isoformat(), expiry.isoformat())).fetchone()
        ceus_completed = int(ceus["total"] or 0)
        ceus_required = u["required_ceus"] or 30
        ceus_remaining = max(0, ceus_required - ceus_completed)

        alert_type = "renewal_warning" if days_until <= 30 else "deadline_approaching"

        try:
            # Call the email alert logic directly
            resend_api_key = os.environ.get("RESEND_API_KEY")
            if not resend_api_key:
                errors += 1
                continue

            if days_until <= 30:
                subject = f"⏰ Breathe: Your {u['state']} RT license expires in {days_until} days"
            else:
                subject = f"📢 Breathe: CEU deadline approaching for {u['state']} ({days_until} days)"

            html_body = f"""
            <div style="font-family: sans-serif; max-width: 560px; margin: 0 auto;">
                <h2 style="color: #003e54;">{"⏰ License Renewal Warning" if days_until <= 30 else "📢 CEU Deadline Approaching"}</h2>
                <p>Hi {u["name"]},</p>
                <p>Your <strong>{u["state"]} {u["license_type"]} license</strong> expires on <strong>{u["expiry_date"]}</strong> — that's <strong>{days_until} days</strong> from now.</p>
                <table style="border-collapse: collapse; margin: 16px 0;">
                    <tr><td style="padding: 8px 16px; background: #f0f0f0;">Completed</td><td style="padding: 8px 16px;">{ceus_completed} CEUs</td></tr>
                    <tr><td style="padding: 8px 16px; background: #f0f0f0;">Required</td><td style="padding: 8px 16px;">{ceus_required} CEUs</td></tr>
                    <tr><td style="padding: 8px 16px; background: {'#fff3cd' if ceus_remaining > 0 else '#d4edda'}; font-weight: bold;">Remaining</td><td style="padding: 8px 16px; font-weight: bold; color: {'#dc3545' if ceus_remaining > 0 else '#28a745'};">{ceus_remaining} CEUs</td></tr>
                </table>
                <p>{f"You still need <strong>{ceus_remaining} CEUs</strong> before renewal. Do not wait!" if ceus_remaining > 0 else "You have met your CEU requirement. You are ready to renew!"}</p>
                <p><a href="https://breathe.sublettlabs.com" style="display: inline-block; padding: 12px 24px; background: #003e54; color: white; text-decoration: none; border-radius: 6px;">View Your Progress</a></p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
                <p style="color: #999; font-size: 12px;">Breathe — CEU Tracker for Respiratory Therapists<br>breathe.sublettlabs.com</p>
            </div>
            """
            text_body = f"Hi {u['name']},\n\nYour {u['state']} {u['license_type']} license expires {u['expiry_date']} ({days_until} days).\n\nCEU Progress:\n- Completed: {ceus_completed}\n- Required: {ceus_required}\n- Remaining: {ceus_remaining}\n\n{'You still need ' + str(ceus_remaining) + ' more CEUs. Do not wait!' if ceus_remaining > 0 else 'You have met your CEU requirement. Ready to renew!'}\n\nhttps://breathe.sublettlabs.com\n\nBreathe — CEU Tracker for Respiratory Therapists"

            import requests as req
            resp = req.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": "Breathe <alerts@brandbooststudio.co>",
                    "to": [u["email"]],
                    "subject": subject,
                    "html": html_body,
                    "text": text_body,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                alerts_sent += 1
                logger.info("Breathe alert sent to %s (%s, %d days, %d CEUs remaining)",
                            u["email"], u["state"], days_until, ceus_remaining)
            else:
                errors += 1
                logger.error("Breathe alert failed for %s: %s", u["email"], resp.text[:200])
        except Exception as e:
            errors += 1
            logger.error("Breathe alert error for %s: %s", u["email"], str(e))

    conn.close()
    return {
        "status": "ok",
        "alerts_sent": alerts_sent,
        "errors": errors,
        "users_checked": len(users),
        "date": today.isoformat(),
    }


# ─── Free CEU Course Alerts Endpoints (Pro feature) ────────────

@app.get("/api/free-course-alerts", response_model=List[FreeCourseAlertOut], tags=["Alerts"])
def list_free_course_alerts(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """List free CEU course alerts for the authenticated user (Pro only)."""
    require_pro(current_user, "free_course_alerts")

    return db.query(FreeCourseAlert).filter(
        FreeCourseAlert.user_id == current_user.id
    ).order_by(FreeCourseAlert.alert_date.desc()).all()


@app.post("/api/free-course-alerts", response_model=FreeCourseAlertOut, tags=["Alerts"])
def create_free_course_alert(payload: FreeCourseAlertCreate, current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Create a free course alert for the authenticated user (Pro only)."""
    require_pro(current_user, "free_course_alerts")

    alert = FreeCourseAlert(
        user_id=current_user.id,
        course_title=payload.course_title,
        provider=payload.provider,
        credits=payload.credits,
        url=payload.url,
        source=payload.source,
        alert_date=date.today(),
        sent=False,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


@app.post("/api/free-course-alerts/scan", tags=["Alerts"])
def scan_free_courses_endpoint(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Scan AARC/NBRC for free CEU opportunities (Pro only)."""
    user_id = current_user.id

    require_pro(current_user, "free_course_alerts")

    from free_course_scanner import scan_free_courses, format_course_for_alert

    courses = scan_free_courses()

    # Optionally save as alerts
    saved = []
    for course in courses:
        alert_data = format_course_for_alert(course)
        alert = FreeCourseAlert(
            user_id=user_id,
            course_title=alert_data["course_title"],
            provider=alert_data["provider"],
            credits=alert_data["credits"],
            url=alert_data["url"],
            source=alert_data["source"],
            alert_date=date.today(),
            sent=False,
        )
        db.add(alert)
        saved.append(alert)

    db.commit()

    return {
        "found": len(courses),
        "alerts_created": len(saved),
        "courses": courses,
    }


# ─── Public Free Courses Endpoints ───────────────────────────

@app.get("/api/free-courses", tags=["Free Courses"])
def list_free_courses():
    """List all available free CEU opportunities (public, no auth needed)."""
    import sqlite3
    from database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    rows = c.execute("""
        SELECT id, course_title, provider, credits, url, source, alert_date
        FROM free_course_alerts
        ORDER BY credits DESC, provider
    """).fetchall()
    conn.close()

    courses = []
    for row in rows:
        courses.append({
            "id": row[0],
            "title": row[1],
            "provider": row[2],
            "credits": row[3],
            "url": row[4],
            "source": row[5],
            "alert_date": row[6],
        })

    return {
        "courses": courses,
        "total": len(courses),
        "total_credits": sum(c.get("credits", 0) for c in courses),
    }


@app.post("/api/free-courses/scan", tags=["Free Courses"])
def scan_free_courses_public(current_user: User = Depends(get_current_user)):
    """Reload curated free CEU courses into the database (requires auth)."""
    from free_ceu_scanner import get_free_courses, store_alerts
    from database import DB_PATH
    courses = get_free_courses()
    added = store_alerts(DB_PATH, courses)
    return {
        "scanned": len(courses),
        "added": added,
        "sources_checked": len(courses),
    }


# ─── License Lookup (Multi-State) ─────────────────────────────

class LicenseLookupRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    license_number: Optional[str] = None
    license_type: str = "RCP"  # Default to Respiratory Care Practitioner
    state: str = "TX"  # State code: TX, IN, etc.

class LicenseLookupResult(BaseModel):
    name: str
    tmb_name: Optional[str] = None
    pla_name: Optional[str] = None
    license_number: str
    license_type: str
    license_type_full: Optional[str] = None
    status: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None


@app.post("/api/license-lookup", tags=["License Lookup"])
def lookup_license_endpoint(payload: LicenseLookupRequest):
    """Look up an RT license from the appropriate state board.

    Currently supports:
      - TX: Texas Medical Board (TMB)
      - IN: Indiana Professional Licensing Agency (PLA)

    For other states, returns an empty results list with a helpful message.
    Provide either a name (first + last) or a license number.
    """
    if not payload.license_number and not (payload.first_name or payload.last_name):
        raise HTTPException(
            status_code=400,
            detail="Provide either name (first+last) or license_number",
        )

    state_code = (payload.state or "TX").upper()

    if state_code == "TX":
        from license_lookup import lookup_license

        result = lookup_license(
            first_name=payload.first_name or "",
            last_name=payload.last_name or "",
            license_number=payload.license_number or "",
            license_type=payload.license_type,
        )

        if result.get("error"):
            logger.error("License lookup failed for TX: %s", result["error"])
            raise HTTPException(status_code=400, detail="License lookup failed. Please try again or enter your license info manually.")

        return {
            "results": result["results"],
            "count": result["count"],
        }

    elif state_code == "IN":
        from license_lookup import lookup_indiana_license

        results = lookup_indiana_license(
            first_name=payload.first_name or "",
            last_name=payload.last_name or "",
            license_number=payload.license_number or "",
        )

        return {
            "results": results,
            "count": len(results),
        }

    elif state_code == "FL":
        from license_lookup import lookup_florida_license

        results = lookup_florida_license(
            first_name=payload.first_name or "",
            last_name=payload.last_name or "",
            license_number=payload.license_number or "",
            license_type=payload.license_type,
        )

        return {
            "results": results,
            "count": len(results),
        }

    else:
        # State not yet supported — return empty results with message
        return {
            "results": [],
            "count": 0,
            "message": f"License lookup not yet supported for {state_code}. Please enter your license info manually.",
        }


# ─── NBRC CMP Endpoints ─────────────────────────────────────────

class NBRCCredentialCreate(BaseModel):
    credential_type: str  # RRT/CRT/NPS/ACCS/SDS/RPFT/AE-C
    earned_date: Optional[str] = None  # ISO date
    cmp_cycle_end: str  # ISO date — 5-year cycle end
    renewal_method: str = "assessments"  # assessments/exam/new_credential
    is_highest: bool = False

class NBRCCredentialOut(BaseModel):
    id: int
    user_id: int
    credential_type: str
    earned_date: Optional[date]
    cmp_cycle_end: date
    renewal_method: str
    is_highest: bool

    class Config:
        from_attributes = True

class NBRCAssessmentCreate(BaseModel):
    quarter: str  # "2026-Q3"
    score: Optional[float] = None
    taken_date: Optional[str] = None

class NBRCAssessmentOut(BaseModel):
    id: int
    user_id: int
    quarter: str
    score: Optional[float]
    taken_date: Optional[date]
    credits_required: int

    class Config:
        from_attributes = True

class NBRCStatusOut(BaseModel):
    has_nbrc: bool
    credentials: list
    cycle_start: Optional[str] = None
    cycle_end: Optional[str] = None
    cycle_years: Optional[int] = None
    days_remaining: Optional[int] = None
    progress_pct: Optional[float] = None
    assessments: Optional[list] = None
    ce_required: Optional[int] = None
    ce_earned: Optional[float] = None
    ce_from_state_license: Optional[float] = None
    additional_ce_needed: Optional[int] = None
    overlap_courses: Optional[list] = None
    renewal_method: Optional[str] = None
    on_track: Optional[bool] = None


@app.get("/api/nbrc/status", tags=["NBRC"])
def get_nbrc_status_endpoint(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Get NBRC CMP status for the authenticated user."""
    from nbrc_tracker import get_nbrc_status
    return get_nbrc_status(db, current_user.id)


@app.post("/api/nbrc/scrape", tags=["NBRC"])
def scrape_nbrc_endpoint(payload: dict, current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Log into NBRC portal and pull real CMP data (credentials, cycle, assessments, CE hours).
    
    This is a Pro feature — keeps NBRC tracking up to date automatically.
    
    Runs synchronously. The NBRC portal takes ~30-40 seconds to scrape.
    If the proxy (Next.js rewrites / Cloudflare Tunnel) times out before
    the scrape finishes, the frontend gets a 500. The frontend should use
    the async version (/api/nbrc/scrape-async) to avoid timeout issues.
    """
    require_pro(current_user, "nbrc_sync")
    
    email = payload.get("email")
    password = payload.get("password")
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    
    from nbrc_scraper import scrape_nbrc_portal
    result = scrape_nbrc_portal(email, password)
    
    if not result.get("success"):
        logger.error("NBRC scrape failed: %s", result.get("error", "unknown"))
        raise HTTPException(status_code=400, detail="NBRC lookup failed. Please try again or enter your credentials manually.")
    
    _save_nbrc_scrape_result(result, current_user, db)
    return result


# ─── Async NBRC Scrape (avoids 30s proxy timeout) ─────────────

import threading

# In-memory store for async scrape jobs: {job_id: {status, result, error, user_id} }
_nbrc_scrape_jobs: dict = {}
_NBRC_JOB_TTL = 300  # 5 minutes


def _run_nbrc_scrape_async(job_id: str, email: str, password: str, user_id: int):
    """Background worker that runs the NBRC scrape and stores the result."""
    try:
        from nbrc_scraper import scrape_nbrc_portal
        result = scrape_nbrc_portal(email, password)
        
        if result.get("success"):
            # Save to DB in a new session (background thread can't share the request session)
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    _save_nbrc_scrape_result(result, user, db)
            finally:
                db.close()
            
            _nbrc_scrape_jobs[job_id] = {"status": "done", "result": result, "error": None, "ts": time.time()}
        else:
            _nbrc_scrape_jobs[job_id] = {"status": "error", "result": None, "error": result.get("error", "Scrape failed"), "ts": time.time()}
    except Exception as e:
        logger.error("Async NBRC scrape failed: %s", e)
        _nbrc_scrape_jobs[job_id] = {"status": "error", "result": None, "error": str(e), "ts": time.time()}


def _save_nbrc_scrape_result(result, current_user, db):
    """Save NBRC scrape results to the database. Shared between sync and async endpoints."""
    from datetime import date as date_type
    from models import NBRCCredential, NBRCAssessment
    
    # Clear old NBRC data
    db.query(NBRCCredential).filter(NBRCCredential.user_id == current_user.id).delete()
    db.query(NBRCAssessment).filter(NBRCAssessment.user_id == current_user.id).delete()
    
    # Add scraped credentials - but skip CRT if user has RRT or higher
    has_rrt_or_higher = any(c["type"] in ("RRT", "RRT-NPS", "ACCS", "SDS", "RPFT", "AE-C") for c in result.get("credentials", []))
    for cred in result.get("credentials", []):
        if has_rrt_or_higher and cred["type"] == "CRT":
            continue  # Skip CRT — RRT or higher supersedes it
        # Convert MM/DD/YYYY to YYYY-MM-DD
        parts = cred["earned_date"].split("/")
        earned_iso = f"{parts[2]}-{parts[0]}-{parts[1]}" if len(parts) == 3 else None
        parts = cred["expires"].split("/")
        expires_iso = f"{parts[2]}-{parts[0]}-{parts[1]}" if len(parts) == 3 else None
        
        is_highest = cred["type"] in ("RRT", "RRT-NPS") and cred["type"] == "RRT"
        
        nbrc_cred = NBRCCredential(
            user_id=current_user.id,
            credential_type=cred["type"],
            earned_date=date_type.fromisoformat(earned_iso) if earned_iso else None,
            cmp_cycle_end=date_type.fromisoformat(expires_iso) if expires_iso else date_type.today(),
            renewal_method="assessments",
            is_highest=is_highest,
        )
        db.add(nbrc_cred)
    
    # Add assessment score
    for assess in result.get("assessments", []):
        score = float(assess.get("score", 0))
        ce_required = 0 if score >= 38 else (15 if score >= 30 else 30)
        nbrc_assess = NBRCAssessment(
            user_id=current_user.id,
            quarter=f"{date_type.today().year}-Q{(date_type.today().month - 1) // 3 + 1}",
            score=score,
            taken_date=date_type.today(),
            credits_required=ce_required,
        )
        db.add(nbrc_assess)
    
    db.commit()


@app.post("/api/nbrc/scrape-async", tags=["NBRC"])
def scrape_nbrc_async(payload: dict, current_user: User = Depends(get_current_user)):
    """Start an async NBRC scrape job. Returns a job_id immediately.
    
    The NBRC portal takes ~30-40 seconds to scrape, which exceeds the
    30-second proxy timeout (Next.js rewrites + Cloudflare Tunnel). This
    endpoint starts the scrape in a background thread and returns a 202
    with a job_id. The frontend polls GET /api/nbrc/scrape-status/{job_id}
    until the job is done.
    """
    require_pro(current_user, "nbrc_sync")
    
    email = payload.get("email")
    password = payload.get("password")
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    
    job_id = str(uuid.uuid4())
    _nbrc_scrape_jobs[job_id] = {"status": "pending", "result": None, "error": None, "ts": time.time()}
    
    thread = threading.Thread(
        target=_run_nbrc_scrape_async,
        args=(job_id, email, password, current_user.id),
        daemon=True,
    )
    thread.start()
    
    return {"job_id": job_id, "status": "pending"}


@app.get("/api/nbrc/scrape-status/{job_id}", tags=["NBRC"])
def scrape_nbrc_status(job_id: str, current_user: User = Depends(get_current_user)):
    """Poll for the status of an async NBRC scrape job."""
    # Clean up old jobs
    now = time.time()
    expired = [k for k, v in _nbrc_scrape_jobs.items() if now - v.get("ts", 0) > _NBRC_JOB_TTL]
    for k in expired:
        del _nbrc_scrape_jobs[k]
    
    job = _nbrc_scrape_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    
    return job

@app.post("/api/nbrc/credentials", response_model=NBRCCredentialOut, tags=["NBRC"])
def add_nbrc_credential(payload: NBRCCredentialCreate, current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Add an NBRC credential (RRT, NPS, etc.) with 5-year CMP cycle."""
    from datetime import date as date_type
    cred = NBRCCredential(
        user_id=current_user.id,
        credential_type=payload.credential_type,
        earned_date=date_type.fromisoformat(payload.earned_date) if payload.earned_date else None,
        cmp_cycle_end=date_type.fromisoformat(payload.cmp_cycle_end),
        renewal_method=payload.renewal_method,
        is_highest=payload.is_highest,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred

@app.get("/api/nbrc/credentials", response_model=list[NBRCCredentialOut], tags=["NBRC"])
def list_nbrc_credentials(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """List NBRC credentials for the authenticated user."""
    return db.query(NBRCCredential).filter(NBRCCredential.user_id == current_user.id).all()

@app.post("/api/nbrc/assessments", response_model=NBRCAssessmentOut, tags=["NBRC"])
def log_assessment(payload: NBRCAssessmentCreate, current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Log a quarterly assessment score for the authenticated user."""
    from datetime import date as date_type
    # Calculate credits required based on score
    score = payload.score
    if score is None:
        credits_req = 30
    elif score >= 75:
        credits_req = 0
    elif score >= 50:
        credits_req = 15
    else:
        credits_req = 30

    assessment = NBRCAssessment(
        user_id=current_user.id,
        quarter=payload.quarter,
        score=score,
        taken_date=date_type.fromisoformat(payload.taken_date) if payload.taken_date else date_type.today(),
        credits_required=credits_req,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment

@app.get("/api/nbrc/assessment-reminder", tags=["NBRC"])
def get_assessment_reminder(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Get next quarterly assessment reminder for the authenticated user."""
    from nbrc_tracker import get_next_assessment_reminder
    return get_next_assessment_reminder(current_user.id, db)


# ─── CE Broker Sync Endpoints ─────────────────────────────────

class CEBrokerSyncResult(BaseModel):
    synced: int  # confirmed successes
    failed: int
    submitted_unconfirmed: int = 0  # submitted but no confirmation detected
    errors: List[str] = []
    details: List[dict] = []
    message: Optional[str] = None


class CEBrokerEmailSettings(BaseModel):
    """CE Broker login email settings — stored encrypted in DB."""
    cebroker_email: Optional[str] = None  # Plaintext email (encrypted before storage)


class CEBrokerEmailOut(BaseModel):
    """CE Broker email settings response — email is masked for security."""
    has_cebroker_email: bool
    cebroker_email_masked: Optional[str] = None  # e.g. "r***@gmail.com"
    encryption_enabled: bool


class CEBrokerSyncLogOut(BaseModel):
    id: int
    ceu_id: int
    status: str  # pending/submitted/confirmed/failed
    attempt_count: int
    error_message: Optional[str] = None
    submitted_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    created_at: datetime
    ceu_title: Optional[str] = None

    class Config:
        from_attributes = True


@app.post("/api/cebroker/sync", response_model=CEBrokerSyncResult, tags=["CE Broker Sync"])
def sync_to_cebroker(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Sync all unreported CEUs to CE Broker.

    Logs into CE Broker via email + OTP (caught from AgentMail), then uploads
    each CEU record that hasn't been synced yet. Only marks CEUs as
    cebroker_synced=True after explicit confirmation is detected on the
    CE Broker page (success message like "successfully", "received", "submitted").

    Each CEU submission is wrapped in its own try/catch — failure of one
    doesn't block the rest. Random 2-5 second delays between submissions
    for human-like behavior.

    Requires BREATHE_ENCRYPTION_KEY environment variable to be set for
    credential encryption. If not configured, sync is gracefully disabled.
    """
    from cebroker_sync import create_sync_log, update_sync_log
    from crypto import is_encryption_available, decrypt_field
    from models import CEBrokerSyncLog
    import subprocess as _subproc
    import json as _json
    import os as _os

    # ─── Encryption key check ───────────────────────────────────
    if not is_encryption_available():
        return CEBrokerSyncResult(
            synced=0, failed=0, errors=[], details=[],
            message=("CE Broker sync disabled: BREATHE_ENCRYPTION_KEY environment variable "
                     "is not set. Configure it to enable CE Broker sync.")
        )

    # Get all CEUs for this user that haven't been synced to CE Broker yet
    ceus = db.query(CEU).filter(
        CEU.user_id == current_user.id,
        CEU.cebroker_synced == False
    ).all()

    if not ceus:
        return CEBrokerSyncResult(
            synced=0, failed=0, errors=[], details=[],
            message="No CEUs to sync — all CEUs are already reported to CE Broker."
        )

    # ─── Resolve CE Broker login email ──────────────────────────
    # Use encrypted CE Broker email if set, otherwise fall back to user's Breathe email
    cebroker_email = None
    if current_user.cebroker_email_encrypted:
        cebroker_email = decrypt_field(current_user.cebroker_email_encrypted)
        if not cebroker_email:
            return CEBrokerSyncResult(
                synced=0, failed=0, errors=[], details=[],
                message=("CE Broker sync disabled: could not decrypt CE Broker email. "
                         "Check that BREATHE_ENCRYPTION_KEY matches the key used to encrypt it.")
            )
    if not cebroker_email:
        cebroker_email = current_user.email  # Fall back to Breathe account email

    # Create sync log entries (status=pending) for each CEU
    sync_log_map = {}  # ceu_id -> log_id
    for ceu in ceus:
        log = create_sync_log(db, current_user.id, ceu.id, status="pending")
        sync_log_map[ceu.id] = log.id

    ceus_to_sync = [
        {
            "id": ceu.id,
            "title": ceu.title,
            "provider": ceu.provider,
            "credits": ceu.credits,
            "completion_date": ceu.completion_date.isoformat(),
            "category": ceu.category,
        }
        for ceu in ceus
    ]

    # Run the sync via cebroker_sync_v2.py (OTP → AgentMail → OAuth2 → API submit)
    # Build CEU data for the v2 script
    sync_script = _os.path.join(_os.path.expanduser('~/.openclaw/workspace'), 'scripts', 'cebroker_sync_v2.py')
    
    # Call the v2 sync script which handles auth + submission internally
    # We pass the CEU data via environment variable to avoid exposing it in command line
    ceu_data_for_script = _json.dumps({
        'email': cebroker_email,
        'pk_license': 26094428,  # TX license — TODO: make per-user configurable
        'ceus': ceus_to_sync,
    })
    
    try:
        proc = _subproc.run(
            ['python3', sync_script, '--sync', '--user-id', str(current_user.id)],
            capture_output=True, text=True, timeout=300,
            cwd=_os.path.dirname(sync_script)
        )
        # Parse results from the script output
        results = {'details': [], 'synced': 0, 'failed': 0, 'errors': []}
        # The v2 script prints results — parse the summary
        output = proc.stdout
        for line in output.splitlines():
            if '✅' in line and 'Credit ID' in line:
                # Parse: '  ✅ CEU #51 synced! Credit ID: 38421361'
                parts = line.split('CEU #')
                if len(parts) > 1:
                    ceu_id_str = parts[1].split(' ')[0].rstrip(':')
                    try:
                        ceu_id = int(ceu_id_str)
                        credit_parts = line.split('Credit ID:')
                        credit_id = int(credit_parts[1].strip()) if len(credit_parts) > 1 else None
                        results['details'].append({'ceu_id': ceu_id, 'status': 'submitted', 'credit_id': credit_id})
                        results['synced'] += 1
                    except:
                        pass
            elif '❌' in line and 'failed' in line.lower():
                parts = line.split('CEU #')
                if len(parts) > 1:
                    try:
                        ceu_id = int(parts[1].split(' ')[0].rstrip(':'))
                        results['details'].append({'ceu_id': ceu_id, 'status': 'failed'})
                        results['failed'] += 1
                    except:
                        pass
    except Exception as e:
        results = {'details': [], 'synced': 0, 'failed': len(ceus), 'errors': [str(e)]}
    
    # Also run the old-style result processing for compatibility

    # Process results: only mark synced=True for CONFIRMED successes
    # "submitted" status means it was submitted but no confirmation detected — don't mark as synced
    confirmed_ceu_ids = set()
    submitted_ceu_ids = set()
    failed_ceu_ids = set()

    for detail in results.get("details", []):
        ceu_id = detail.get("ceu_id")
        status = detail.get("status")

        if ceu_id and ceu_id in sync_log_map:
            if status == "confirmed":
                update_sync_log(db, ceu_id, "confirmed")
                confirmed_ceu_ids.add(ceu_id)
            elif status == "submitted":
                update_sync_log(db, ceu_id, "submitted")
                submitted_ceu_ids.add(ceu_id)
            elif status == "failed":
                update_sync_log(db, ceu_id, "failed", detail.get("message"))
                failed_ceu_ids.add(ceu_id)

    # Only mark CEUs as synced after CONFIRMED success
    if confirmed_ceu_ids:
        for ceu in ceus:
            if ceu.id in confirmed_ceu_ids:
                ceu.cebroker_synced = True
                ceu.cebroker_synced_at = datetime.utcnow()
        db.commit()

    return CEBrokerSyncResult(
        synced=results.get("synced", 0),
        failed=results.get("failed", 0),
        submitted_unconfirmed=results.get("submitted_unconfirmed", 0),
        errors=results.get("errors", []),
        details=results.get("details", []),
    )


# ─── CE Broker Email Settings (Encrypted) ─────────────────────

@app.put("/api/cebroker/email", tags=["CE Broker Sync"])
def set_cebroker_email(
    payload: CEBrokerEmailSettings,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db),
):
    """Set the CE Broker login email for the authenticated user.

    The email is encrypted using Fernet (via crypto.py) before being stored
    in the database. Requires BREATHE_ENCRYPTION_KEY environment variable.
    """
    from crypto import is_encryption_available, encrypt_field

    if not is_encryption_available():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "encryption_not_configured",
                "message": ("BREATHE_ENCRYPTION_KEY environment variable is not set. "
                            "Configure it to enable CE Broker credential storage."),
            },
        )

    email = (payload.cebroker_email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required")

    encrypted = encrypt_field(email)
    if not encrypted:
        raise HTTPException(
            status_code=500,
            detail="Failed to encrypt CE Broker email. Check BREATHE_ENCRYPTION_KEY.",
        )

    current_user.cebroker_email_encrypted = encrypted
    db.commit()

    # Return masked email for confirmation
    parts = email.split("@")
    masked = f"{parts[0][:1]}***@{parts[1]}" if len(parts) == 2 else "***"

    return {
        "success": True,
        "message": "CE Broker email saved (encrypted)",
        "cebroker_email_masked": masked,
    }


@app.get("/api/cebroker/email", response_model=CEBrokerEmailOut, tags=["CE Broker Sync"])
def get_cebroker_email_settings(
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db),
):
    """Get CE Broker email settings for the authenticated user.

    Returns a masked email for security — the full email is never returned
    via API. CE Broker sync uses the encrypted email internally.
    """
    from crypto import is_encryption_available, decrypt_field

    encryption_enabled = is_encryption_available()
    has_email = bool(current_user.cebroker_email_encrypted)
    masked = None

    if has_email and encryption_enabled:
        email = decrypt_field(current_user.cebroker_email_encrypted)
        if email:
            parts = email.split("@")
            masked = f"{parts[0][:1]}***@{parts[1]}" if len(parts) == 2 else "***"

    return CEBrokerEmailOut(
        has_cebroker_email=has_email,
        cebroker_email_masked=masked,
        encryption_enabled=encryption_enabled,
    )


@app.delete("/api/cebroker/email", tags=["CE Broker Sync"])
def delete_cebroker_email(
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db),
):
    """Remove the stored CE Broker login email for the authenticated user."""
    current_user.cebroker_email_encrypted = None
    db.commit()
    return {"success": True, "message": "CE Broker email removed"}


@app.put("/api/cebroker/password", tags=["CE Broker Sync"])
def set_cebroker_password(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db),
):
    """Set the CE Broker password for the authenticated user.

    The password is encrypted using Fernet (via crypto.py) before storage.
    Note: CE Broker (Propelus) uses email OTP login, not password — this is
    stored for future use if password-based auth is restored, or for
    reference by the user.
    """
    from crypto import is_encryption_available, encrypt_field

    if not is_encryption_available():
        raise HTTPException(status_code=503, detail="Encryption not configured")

    password = (payload.get("cebroker_password") or "").strip()
    if not password or len(password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")

    encrypted = encrypt_field(password)
    if not encrypted:
        raise HTTPException(status_code=500, detail="Failed to encrypt password")

    # Add column if missing
    try:
        db.execute(text("UPDATE users SET cebroker_password_encrypted = :enc WHERE id = :uid"),
                   {"enc": encrypted, "uid": current_user.id})
        db.commit()
    except Exception:
        # Column doesn't exist — add it
        db.execute(text("ALTER TABLE users ADD COLUMN cebroker_password_encrypted TEXT"))
        db.commit()
        db.execute(text("UPDATE users SET cebroker_password_encrypted = :enc WHERE id = :uid"),
                   {"enc": encrypted, "uid": current_user.id})
        db.commit()

    return {"success": True, "message": "CE Broker password saved (encrypted)", "has_password": True}


@app.get("/api/cebroker/settings", tags=["CE Broker Sync"])
def get_cebroker_settings(
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db),
):
    """Get all CE Broker integration settings for the authenticated user.

    Returns masked email, password existence, license info, and sync status.
    """
    from crypto import is_encryption_available, decrypt_field

    encryption_enabled = is_encryption_available()

    # Email (masked)
    has_email = bool(current_user.cebroker_email_encrypted)
    email_masked = None
    if has_email and encryption_enabled:
        email = decrypt_field(current_user.cebroker_email_encrypted)
        if email:
            parts = email.split("@")
            email_masked = f"{parts[0][:1]}***@{parts[1]}" if len(parts) == 2 else "***"

    # Password (existence only)
    has_password = False
    try:
        row = db.execute(text("SELECT cebroker_password_encrypted FROM users WHERE id = :uid"),
                        {"uid": current_user.id}).fetchone()
        has_password = bool(row and row[0])
    except Exception:
        pass  # Column doesn't exist yet

    # Licenses
    licenses = db.query(License).filter(License.user_id == current_user.id).all()
    license_info = [{
        "id": lic.id,
        "state": lic.state,
        "license_type": lic.license_type,
        "license_number": lic.license_number,
        "expiry_date": lic.expiry_date.isoformat() if lic.expiry_date else None,
    } for lic in licenses]

    # Sync status
    total_ceus = db.query(CEU).filter(CEU.user_id == current_user.id).count()
    synced_count = db.query(CEU).filter(
        CEU.user_id == current_user.id, CEU.cebroker_synced == True
    ).count()

    return {
        "encryption_enabled": encryption_enabled,
        "cebroker_email": {
            "has_email": has_email,
            "email_masked": email_masked,
        },
        "cebroker_password": {
            "has_password": has_password,
        },
        "licenses": license_info,
        "sync_status": {
            "total_ceus": total_ceus,
            "synced": synced_count,
            "unsynced": total_ceus - synced_count,
            "all_synced": (total_ceus - synced_count) == 0 and total_ceus > 0,
        },
    }


@app.get("/api/cebroker/status", tags=["CE Broker Sync"])
def get_cebroker_status(current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Get CE Broker sync status for the authenticated user.

    Returns counts of synced and unsynced CEUs.
    """
    total_ceus = db.query(CEU).filter(CEU.user_id == current_user.id).count()
    synced_count = db.query(CEU).filter(
        CEU.user_id == current_user.id,
        CEU.cebroker_synced == True
    ).count()
    unsynced_count = total_ceus - synced_count

    return {
        "total_ceus": total_ceus,
        "synced": synced_count,
        "unsynced": unsynced_count,
        "all_synced": unsynced_count == 0 and total_ceus > 0,
    }


@app.get("/api/cebroker/sync-log", tags=["CE Broker Sync"])
def get_cebroker_sync_log(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db),
):
    """Get sync attempt log entries for the authenticated user.

    Returns the most recent sync log entries with CEU titles for context.
    Each entry tracks status: pending → submitted → confirmed | failed.
    """
    from models import CEBrokerSyncLog

    logs = db.query(CEBrokerSyncLog).filter(
        CEBrokerSyncLog.user_id == current_user.id
    ).order_by(
        CEBrokerSyncLog.created_at.desc()
    ).limit(min(limit, 200)).all()

    result = []
    for log in logs:
        ceu = db.query(CEU).filter(CEU.id == log.ceu_id).first()
        result.append({
            "id": log.id,
            "ceu_id": log.ceu_id,
            "ceu_title": ceu.title if ceu else "(deleted)",
            "status": log.status,
            "attempt_count": log.attempt_count,
            "error_message": log.error_message,
            "submitted_at": log.submitted_at.isoformat() if log.submitted_at else None,
            "confirmed_at": log.confirmed_at.isoformat() if log.confirmed_at else None,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })

    return {"logs": result, "count": len(result)}


# ─── Health Check ───────────────────────────────────────────────

@app.get("/api/health", tags=["Health"])
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "Breathe API", "version": "1.0.0"}


@app.get("/", tags=["Health"])
def root():
    """Root endpoint."""
    return {"service": "Breathe API", "health": "/api/health"}


# ─── Waitlist / Signup ─────────────────────────────────────────

class WaitlistEntry(BaseModel):
    name: str
    email: str
    state: str = "TX"
    license_type: str = "RRT"

@app.post("/api/waitlist", tags=["Waitlist"])
def join_waitlist(payload: WaitlistEntry):
    """Join the Breathe waitlist for early access notification."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO waitlist (name, email, state, license_type) VALUES (?, ?, ?, ?)",
            (payload.name.strip(), payload.email.strip().lower(), payload.state, payload.license_type),
        )
        conn.commit()
        return {"status": "ok", "message": "You're on the list!"}
    except sqlite3.IntegrityError:
        return {"status": "ok", "message": "You're already on the list!"}
    finally:
        conn.close()


@app.get("/api/waitlist/count", tags=["Waitlist"])
def waitlist_count():
    """Get waitlist signup count (public, for social proof)."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    count = c.execute("SELECT COUNT(*) FROM waitlist").fetchone()[0]
    conn.close()
    return {"count": count}


@app.post("/api/admin/cleanup-temp", tags=["Admin"])
def cleanup_temp_files():
    """Cron-friendly endpoint to delete stale temp certificate files.

    Scans /tmp/breathe/certificates/ and removes any files older than 1 hour.
    This is a backstop — process_certificate() already deletes files via try/finally,
    but crashes or killed processes can leave orphaned files containing PII.

    Can be called via cron, curl, or any scheduler. No auth required since it
    only deletes temp files (no user data, no DB access).
    """
    from ocr import cleanup_old_temp_files
    result = cleanup_old_temp_files()
    logger.info("Temp cleanup: deleted %d files, %d dirs, %d errors",
                result["deleted_files"], result["deleted_dirs"], result["errors"])
    return {"status": "ok", **result}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)