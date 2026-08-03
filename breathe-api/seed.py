"""Seed script to populate Breathe DB with demo data."""
import os
import sys

# Ensure local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import init_db, SessionLocal, DB_PATH
from models import User, License, CEU, Credential, Competency, StateRequirement, UserEmailAlias, NBRCCredential
from datetime import date


def seed():
    """Populate database with demo data."""
    # Remove old DB for fresh start
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    init_db()
    db = SessionLocal()

    try:
        # --- Demo User ---
        user = User(name="Ron Sublett", email="ron.sublett@gmail.com")
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"✅ Created user: {user.name} (id={user.id})")

        # --- Email Alias for CEU forwarding ---
        from email_webhook import generate_alias_email
        alias_email = generate_alias_email(user.name)
        alias = UserEmailAlias(user_id=user.id, email_alias=alias_email)
        db.add(alias)
        db.commit()
        db.refresh(alias)
        print(f"✅ Created email alias: {alias.email_alias} → user {user.id}")

        # --- Texas License ---
        tx_license = License(
            user_id=user.id,
            state="TX",
            license_type="RRT",
            license_number="12345",
            issue_date=date(2025, 4, 1),
            expiry_date=date(2027, 3, 31),
            cycle_years=2,
            required_ceus=30,
        )
        db.add(tx_license)
        db.commit()
        print(f"✅ Created TX license: RRT #12345")

        # --- 6 Sample CEUs (totaling 16 CEUs) ---
        ceus_data = [
            {
                "title": "Advanced Mechanical Ventilation Strategies",
                "provider": "AARC",
                "credits": 4.0,
                "completion_date": date(2025, 6, 15),
                "category": "clinical",
            },
            {
                "title": "Neonatal Resuscitation Program Update",
                "provider": "AAP",
                "credits": 3.0,
                "completion_date": date(2025, 8, 22),
                "category": "clinical",
            },
            {
                "title": "Patient Safety in Respiratory Care",
                "provider": "AARC",
                "credits": 2.0,
                "completion_date": date(2025, 10, 5),
                "category": "safety",
            },
            {
                "title": "Ethics in Healthcare Decision Making",
                "provider": "AARC",
                "credits": 2.0,
                "completion_date": date(2026, 1, 12),
                "category": "ethics",
            },
            {
                "title": "Leadership in Respiratory Therapy",
                "provider": "NBRC",
                "credits": 3.0,
                "completion_date": date(2026, 3, 8),
                "category": "leadership",
            },
            {
                "title": "Pulmonary Function Testing Advanced",
                "provider": "AARC",
                "credits": 2.0,
                "completion_date": date(2026, 5, 18),
                "category": "clinical",
            },
        ]

        for ceu_data in ceus_data:
            ceu = CEU(user_id=user.id, ocr_confidence=0.0, **ceu_data)
            db.add(ceu)
        db.commit()
        total = sum(c["credits"] for c in ceus_data)
        print(f"✅ Created {len(ceus_data)} CEUs totaling {total:.1f} credits")

        # --- Credentials ---
        credentials_data = [
            {"type": "RRT", "expiry_date": date(2027, 12, 31), "cycle_years": 2, "issuing_org": "NBRC"},
            {"type": "NPS", "expiry_date": date(2027, 3, 31), "cycle_years": 2, "issuing_org": "NBRC"},
            {"type": "ACLS", "expiry_date": date(2027, 1, 31), "cycle_years": 2, "issuing_org": "AHA"},
            {"type": "BLS", "expiry_date": date(2027, 3, 31), "cycle_years": 2, "issuing_org": "AHA"},
            {"type": "PALS", "expiry_date": date(2027, 5, 31), "cycle_years": 2, "issuing_org": "AHA"},
            {"type": "NRP", "expiry_date": date(2027, 8, 31), "cycle_years": 2, "issuing_org": "AAP"},
        ]

        for cred_data in credentials_data:
            cred = Credential(user_id=user.id, **cred_data)
            db.add(cred)
        db.commit()
        print(f"✅ Created {len(credentials_data)} credentials")

        # --- Competencies ---
        competencies_data = [
            {"name": "Annual Competency - Mechanical Ventilation", "category": "annual", "frequency": "annual", "status": "completed", "completed_date": date(2025, 6, 1), "evaluator": "Sarah Johnson, RRT", "notes": "Passed all checkpoints"},
            {"name": "Annual Competency - Airway Management", "category": "annual", "frequency": "annual", "status": "completed", "completed_date": date(2025, 6, 1), "evaluator": "Sarah Johnson, RRT", "notes": "Excellent performance"},
            {"name": "Unit Specific - NICU Ventilation Protocols", "category": "unit_specific", "frequency": "annual", "status": "pending", "completed_date": None, "evaluator": None, "notes": "Scheduled for Q3 2026"},
            {"name": "Annual Competency - Code Blue Response", "category": "annual", "frequency": "annual", "status": "overdue", "completed_date": None, "evaluator": None, "notes": "Was due 06/2026 — needs immediate scheduling"},
            {"name": "One-Time - New Equipment Training (Hamilton C3)", "category": "unit_specific", "frequency": "one_time", "status": "completed", "completed_date": date(2025, 9, 15), "evaluator": "Mike Chen, RRT", "notes": "Completed during onboarding"},
        ]

        for comp_data in competencies_data:
            comp = Competency(user_id=user.id, **comp_data)
            db.add(comp)
        db.commit()
        print(f"✅ Created {len(competencies_data)} competencies")

        # --- State Requirements ---
        tx_req = StateRequirement(
            state="TX",
            profession="RRT",
            required_ceus=30,
            cycle_years=2,
            mandatory_topics=[],  # No mandatory topics for Texas
        )
        db.add(tx_req)

        fl_req = StateRequirement(
            state="FL",
            profession="RRT",
            required_ceus=24,
            cycle_years=2,
            mandatory_topics=["medical errors", "HIV/AIDS", "domestic violence"],
        )
        db.add(fl_req)

        db.commit()
        print("✅ Created state requirements: TX, FL")

        # --- NBRC Credentials (5-year CMP cycle) ---
        nbrc_creds_data = [
            {
                "credential_type": "RRT",
                "earned_date": date(2012, 1, 15),
                "cmp_cycle_end": date(2027, 1, 15),
                "renewal_method": "assessments",
                "is_highest": True,
            },
            {
                "credential_type": "NPS",
                "earned_date": date(2013, 3, 20),
                "cmp_cycle_end": date(2027, 1, 15),  # Same as RRT — shared expiry
                "renewal_method": "assessments",
                "is_highest": False,
            },
        ]

        for nbrc_data in nbrc_creds_data:
            nbrc_cred = NBRCCredential(user_id=user.id, **nbrc_data)
            db.add(nbrc_cred)
        db.commit()
        print(f"✅ Created {len(nbrc_creds_data)} NBRC credentials (RRT + NPS)")

        print("\n" + "=" * 50)
        print("Breathe DB seeded successfully!")
        print(f"  User: {user.name} (id={user.id})")
        print(f"  Email Alias: {alias.email_alias}")
        print(f"  License: TX RRT #12345 (expires 03/31/2027)")
        print(f"  CEUs: {len(ceus_data)} entries, {total:.1f} credits total")
        print(f"  Credentials: {len(credentials_data)}")
        print(f"  NBRC Credentials: {len(nbrc_creds_data)} (RRT + NPS, CMP cycle ends 01/15/2027)")
        print(f"  Competencies: {len(competencies_data)}")
        print(f"  State Requirements: TX + FL")
        print("=" * 50)

    finally:
        db.close()


if __name__ == "__main__":
    seed()