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

from database import init_db, get_db, SessionLocal, DB_PATH
from models import (
    User, License, CEU, Credential, Competency, StateRequirement,
    UserEmailAlias, Subscription, FreeCourseAlert,
    NBRCCredential, NBRCAssessment, NBRCCEPlan,
)
from auth import hash_password, verify_password, create_access_token, get_current_user, get_optional_user
from email_webhook import router as email_router, generate_alias_email

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
    "free_course_alerts",
}


def require_pro(user: User, feature: str):
    """Check if user has Pro access for a feature. Raises 403 if not."""
    if user.subscription_tier not in ("pro", "department"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "pro_required",
                "feature": feature,
                "message": f"{feature} requires Breathe Pro ($4.99/mo or $39/yr). Upgrade to unlock.",
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

    user = User(
        name=payload.name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        subscription_tier="pro",  # Launch period: all signups get Pro free
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
    return ceu


@app.delete("/api/ceus/{ceu_id}", tags=["CEUs"])
def delete_ceu(ceu_id: int, current_user: User = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    """Delete a CEU record."""
    ceu = db.query(CEU).filter(CEU.id == ceu_id, CEU.user_id == current_user.id).first()
    if not ceu:
        raise HTTPException(status_code=404, detail="CEU not found")
    db.delete(ceu)
    db.commit()
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
        result = process_certificate(save_path)
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
    
    # Save credentials to DB
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
    
    return result

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
    """
    from cebroker_sync import sync_ceus_to_cebroker, create_sync_log, update_sync_log
    from models import CEBrokerSyncLog

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

    # Run the sync agent (Playwright browser automation via Node subprocess)
    results = sync_ceus_to_cebroker(current_user.email, ceus_to_sync, headless=True)

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)