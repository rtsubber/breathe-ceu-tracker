"""Database setup for Breathe API — SQLite for prototype."""
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Date, JSON, ForeignKey, Text, Boolean, CheckConstraint
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "breathe.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    # nullable=False — password must always be set; no NULL or empty hashes allowed.
    # NOTE: This constraint is enforced on new SQLite tables only. For existing DBs,
    # run a migration to backfill/remove NULL rows before applying the constraint.
    # See: alembic or manual `ALTER TABLE` + `CREATE TABLE` with the check.
    password_hash = Column(String(255), nullable=False)
    __table_args__ = (
        CheckConstraint("length(password_hash) > 0", name="password_hash_not_empty"),
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    # Subscription fields
    subscription_tier = Column(String(20), default="free")  # free/pro/department
    subscription_status = Column(String(20), default="active")  # active/canceled/past_due
    stripe_customer_id = Column(String(255), nullable=True)
    subscription_expires = Column(DateTime, nullable=True)
    onboarding_completed = Column(Boolean, default=False)  # False until user completes onboarding
    cebroker_email_encrypted = Column(String(500), nullable=True)  # Encrypted CE Broker login email (via crypto.py)

    licenses = relationship("License", back_populates="user", cascade="all, delete-orphan")
    ceus = relationship("CEU", back_populates="user", cascade="all, delete-orphan")
    credentials = relationship("Credential", back_populates="user", cascade="all, delete-orphan")
    competencies = relationship("Competency", back_populates="user", cascade="all, delete-orphan")


class License(Base):
    __tablename__ = "licenses"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    state = Column(String(10), nullable=False)
    license_type = Column(String(20), nullable=False)  # RRT/CRT/NPS
    license_number = Column(String(50), nullable=False)
    issue_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=False)
    cycle_years = Column(Integer, default=2)
    required_ceus = Column(Integer, default=30)

    user = relationship("User", back_populates="licenses")


class CEU(Base):
    __tablename__ = "ceus"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(500), nullable=False)
    provider = Column(String(255), nullable=False)
    credits = Column(Float, nullable=False)
    completion_date = Column(Date, nullable=False)
    category = Column(String(50), default="clinical")  # clinical/safety/ethics/leadership
    certificate_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    ocr_confidence = Column(Float, default=0.0)
    cebroker_synced = Column(Boolean, default=False)  # True after successfully synced to CE Broker
    cebroker_synced_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="ceus")


class Credential(Base):
    __tablename__ = "credentials"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String(20), nullable=False)  # RRT/CRT/NPS/ACLS/BLS/PALS/NRP
    expiry_date = Column(Date, nullable=False)
    cycle_years = Column(Integer, default=2)
    issuing_org = Column(String(50), nullable=False)  # NBRC/AHA/AAP

    user = relationship("User", back_populates="credentials")


class Competency(Base):
    __tablename__ = "competencies"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    category = Column(String(30), default="annual")  # annual/unit_specific
    frequency = Column(String(20), default="annual")  # annual/biannual/one_time
    status = Column(String(20), default="pending")  # pending/completed/overdue
    completed_date = Column(Date, nullable=True)
    evaluator = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)

    user = relationship("User", back_populates="competencies")


class Subscription(Base):
    """Tracks Stripe subscription details for a user."""
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    tier = Column(String(20), nullable=False)  # free/pro/department
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    status = Column(String(20), default="active")  # active/canceled/past_due/trialing
    current_period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="subscription")


class FreeCourseAlert(Base):
    """Free CEU course alerts for Pro users.

    user_id=NULL means it's a general alert (available to all users from scanning).
    user_id=<int> means it's a per-user alert.
    """
    __tablename__ = "free_course_alerts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)  # NULL = general alert from scanner
    course_title = Column(String(500), nullable=False)
    provider = Column(String(255), nullable=False)
    credits = Column(Float, default=0.0)
    url = Column(String(1000), nullable=True)
    source = Column(String(50), default="aarc")  # aarc/nbrc/other
    alert_date = Column(Date, nullable=False)
    sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)




class StateRequirement(Base):
    __tablename__ = "state_requirements"
    id = Column(Integer, primary_key=True, index=True)
    state = Column(String(10), nullable=False)
    profession = Column(String(20), nullable=False)
    required_ceus = Column(Integer, nullable=False)
    cycle_years = Column(Integer, default=2)
    mandatory_topics = Column(JSON, nullable=True)
    board_name = Column(String(255), nullable=True)


class UserEmailAlias(Base):
    """Maps inbound email aliases to users for CEU email forwarding."""
    __tablename__ = "user_email_aliases"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    email_alias = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="email_aliases")


class NBRCCredential(Base):
    """NBRC credentials — all share same 5-year expiry."""
    __tablename__ = "nbrc_credentials"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    credential_type = Column(String(20), nullable=False)  # RRT/CRT/NPS/ACCS/SDS/RPFT/AE-C
    earned_date = Column(Date, nullable=True)  # When passed the exam
    cmp_cycle_end = Column(Date, nullable=False)  # 5-year cycle end date
    renewal_method = Column(String(30), default="assessments")  # assessments/exam/new_credential
    is_highest = Column(Boolean, default=False)  # Highest credential held
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="nbrc_credentials")


class NBRCAssessment(Base):
    """Quarterly assessment scores for CMP tracking."""
    __tablename__ = "nbrc_assessments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    quarter = Column(String(10), nullable=False)  # "2026-Q3", "2026-Q4", etc.
    score = Column(Float, nullable=True)  # Score (0-100), NULL if not taken yet
    taken_date = Column(Date, nullable=True)
    credits_required = Column(Integer, default=30)  # 0 if high score, 15 if mid, 30 if low/skipped

    user = relationship("User", backref="nbrc_assessments")


class NBRCCEPlan(Base):
    """Calculated CE plan based on assessment scores."""
    __tablename__ = "nbrc_ce_plan"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    cycle_start = Column(Date, nullable=False)
    cycle_end = Column(Date, nullable=False)
    total_ce_needed = Column(Integer, default=30)  # 0, 15, or 30 based on assessments
    ce_from_state_license = Column(Integer, default=0)  # CEUs that count for both state + NBRC
    additional_ce_needed = Column(Integer, default=0)  # CEUs needed beyond state license
    last_calculated = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="nbrc_ce_plan")


class AuditLog(Base):
    """Audit log for tracking user actions across the API.
    
    Records key actions like CEU create/update/delete, login, register,
    license create/update for compliance and security tracking.
    """
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)  # ceu_create, ceu_update, ceu_delete, login, register, license_create, license_update
    entity_type = Column(String(30), nullable=False)  # ceu, license, credential
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)  # JSON dump of relevant data
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="audit_logs")


class CEBrokerSyncLog(Base):
    """Sync attempt log for CE Broker submissions.
    
    Tracks each CEU sync attempt through states:
    pending → submitted → confirmed | failed
    """
    __tablename__ = "cebroker_sync_log"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ceu_id = Column(Integer, ForeignKey("ceus.id"), nullable=False)
    status = Column(String(20), default="pending")  # pending/submitted/confirmed/failed
    attempt_count = Column(Integer, default=1)
    error_message = Column(Text, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="cebroker_sync_logs")
    ceu = relationship("CEU", backref="sync_logs")


def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency for FastAPI to get DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()