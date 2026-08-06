"""NBRC CMP (Credential Maintenance Program) tracker.

Calculates CE requirements based on quarterly assessment scores.
Shows overlap between state license CEUs and NBRC requirements.
"""

from datetime import date, timedelta
from typing import Optional
from models import User, License, CEU, NBRCCredential, NBRCAssessment, NBRCCEPlan
from sqlalchemy.orm import Session


def calculate_nbrc_ce_requirement(assessment_scores: list[float]) -> int:
    """Calculate CE requirement based on quarterly assessment scores.

    NBRC rules (from portal):
    - Score is out of 45 points
    - High (≥38/45 = ~85%) → 0 CE needed
    - Mid (30-37/45 = ~67-82%) → 15 CE needed
    - Low (<30/45 = <67%) → 30 CE needed (maximum)
    
    The portal shows the current requirement based on latest assessment.
    """
    if not assessment_scores:
        return 30  # Default if no assessments taken — max CE required
    
    # Use the most recent score (not average — NBRC shows current status)
    latest_score = assessment_scores[-1]
    
    # NBRC scoring thresholds (out of 45)
    if latest_score >= 38:
        return 0   # High — no CE needed
    elif latest_score >= 30:
        return 15  # Mid — 15 CE needed
    else:
        return 30  # Low — 30 CE needed (maximum)


def get_nbrc_status(db: Session, user_id: int) -> dict:
    """Get complete NBRC status for a user.

    Returns:
    - credentials: list of NBRC credentials with cycle end date
    - cycle_progress: days elapsed / total days in 5-year cycle
    - assessments: quarterly scores
    - ce_required: total CE needed for NBRC (0, 15, or 30)
    - ce_from_state: CEUs that count for both state license + NBRC
    - additional_ce_needed: extra CEUs beyond state license
    - overlap_courses: list of CEUs that satisfy both
    """
    # Get NBRC credentials
    nbrc_creds = db.query(NBRCCredential).filter(NBRCCredential.user_id == user_id).all()

    if not nbrc_creds:
        return {
            "has_nbrc": False,
            "credentials": [],
            "message": "No NBRC credentials tracked. Add your RRT/NPS to enable CMP tracking.",
        }

    # Get the primary credential (highest one)
    primary = next((c for c in nbrc_creds if c.is_highest), nbrc_creds[0])
    cycle_end = primary.cmp_cycle_end
    cycle_start = date(cycle_end.year - 5, cycle_end.month, cycle_end.day)

    # Calculate cycle progress
    today = date.today()
    total_days = (cycle_end - cycle_start).days
    elapsed_days = (today - cycle_start).days
    remaining_days = (cycle_end - today).days
    progress_pct = round((elapsed_days / total_days) * 100, 1) if total_days > 0 else 0

    # Get assessment scores
    assessments = db.query(NBRCAssessment).filter(
        NBRCAssessment.user_id == user_id
    ).order_by(NBRCAssessment.quarter).all()

    scores = [a.score for a in assessments if a.score is not None]
    ce_required = calculate_nbrc_ce_requirement(scores)

    # Get state license CEUs — these count toward NBRC too
    state_license = db.query(License).filter(License.user_id == user_id).first()
    if state_license:
        # Get CEUs earned in the NBRC cycle window
        ceus = db.query(CEU).filter(
            CEU.user_id == user_id,
            CEU.completion_date >= cycle_start,
            CEU.completion_date <= cycle_end
        ).all()
        ce_from_state = sum(c.credits for c in ceus)
        overlap_ceus = [{"title": c.title, "credits": c.credits, "date": c.completion_date.isoformat(), "provider": c.provider} for c in ceus]
    else:
        ce_from_state = 0
        overlap_ceus = []

    additional_ce_needed = max(0, ce_required - ce_from_state)

    return {
        "has_nbrc": True,
        "credentials": [{"type": c.credential_type, "earned_date": c.earned_date.isoformat() if c.earned_date else None, "is_highest": c.is_highest} for c in nbrc_creds],
        "cycle_start": cycle_start.isoformat(),
        "cycle_end": cycle_end.isoformat(),
        "cycle_years": 5,
        "days_remaining": remaining_days,
        "progress_pct": progress_pct,
        "assessments": [{"quarter": a.quarter, "score": a.score, "taken": a.taken_date is not None} for a in assessments],
        "ce_required": ce_required,
        "ce_earned": round(ce_from_state, 1),
        "ce_from_state_license": round(ce_from_state, 1),
        "additional_ce_needed": additional_ce_needed,
        "overlap_courses": overlap_ceus,
        "renewal_method": primary.renewal_method,
        "on_track": ce_from_state >= ce_required or remaining_days > 365,
    }


def get_next_assessment_reminder(user_id: int, db: Session) -> Optional[dict]:
    """Get the next quarterly assessment reminder.

    NBRC assessments are quarterly. We need to remind users when the next
    assessment window opens.
    """
    today = date.today()
    # Quarters: Q1 (Jan-Mar), Q2 (Apr-Jun), Q3 (Jul-Sep), Q4 (Oct-Dec)
    current_quarter = (today.month - 1) // 3 + 1
    current_year = today.year

    # Next quarter
    next_quarter = current_quarter + 1
    next_year = current_year
    if next_quarter > 4:
        next_quarter = 1
        next_year += 1

    quarter_start_month = (next_quarter - 1) * 3 + 1
    quarter_start = date(next_year, quarter_start_month, 1)
    days_until = (quarter_start - today).days

    # Check if user has already taken this quarter's assessment
    quarter_key = f"{current_year}-Q{current_quarter}"
    existing = db.query(NBRCAssessment).filter(
        NBRCAssessment.user_id == user_id,
        NBRCAssessment.quarter == quarter_key
    ).first()

    if existing and existing.taken_date:
        return {
            "status": "completed",
            "quarter": quarter_key,
            "score": existing.score,
            "message": f"Q{current_quarter} assessment completed. Score: {existing.score}",
            "next_window": f"{next_year}-Q{next_quarter}",
            "days_until_next": days_until,
        }
    else:
        return {
            "status": "pending",
            "quarter": quarter_key,
            "message": f"Q{current_quarter} {current_year} assessment not yet taken. {days_until} days until next quarter.",
            "next_window": f"{next_year}-Q{next_quarter}",
            "days_until_next": days_until,
        }