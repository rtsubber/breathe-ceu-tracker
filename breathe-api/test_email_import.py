"""Test script for the email-forwarding CEU import service.

Posts sample email payloads (AARC, Medbridge, generic) to the webhook
endpoint and verifies CEU creation in the database.

Usage:
    # Start the API first:
    uvicorn main:app --reload --port 8000

    # Then run tests:
    python test_email_import.py

    # Or with a custom base URL:
    python test_email_import.py --base-url http://localhost:8000
"""
import os
import sys
import json
import argparse
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, init_db
from models import User, CEU, UserEmailAlias

BASE_URL_DEFAULT = "http://localhost:8011"
TEST_EMAILS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_emails")

SAMPLE_FILES = [
    "aarc_confirmation.json",
    "medbridge_confirmation.json",
    "generic_confirmation.json",
]


def setup_alias(db, user_id: int, alias_email: str) -> UserEmailAlias:
    """Ensure an email alias exists for the demo user."""
    existing = db.query(UserEmailAlias).filter(
        UserEmailAlias.email_alias == alias_email.lower()
    ).first()
    if existing:
        return existing
    alias = UserEmailAlias(user_id=user_id, email_alias=alias_email.lower())
    db.add(alias)
    db.commit()
    db.refresh(alias)
    return alias


def count_ceus_before(db, user_id: int) -> int:
    return db.query(CEU).filter(CEU.user_id == user_id).count()


def run_test(base_url: str, sample_file: str, expected_alias: str) -> dict:
    """Post a sample email to the webhook and verify the result."""
    print(f"\n{'='*60}")
    print(f"Testing: {sample_file}")
    print(f"{'='*60}")

    # Load sample payload
    path = os.path.join(TEST_EMAILS_DIR, sample_file)
    with open(path, "r") as f:
        payload = json.load(f)

    # Ensure 'to' matches the alias we set up
    payload["to"] = expected_alias

    print(f"  From: {payload.get('from')}")
    print(f"  To:   {payload.get('to')}")
    print(f"  Subj: {payload.get('subject')}")

    # POST to webhook
    url = f"{base_url}/api/email/ceu-webhook"
    try:
        resp = requests.post(url, json=payload, timeout=30)
    except requests.ConnectionError:
        print(f"  ❌ Cannot connect to {url}")
        print(f"     Make sure the API is running: uvicorn main:app --port 8000")
        return {"success": False, "error": "connection_failed"}

    print(f"  HTTP Status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"  ❌ Unexpected status: {resp.status_code}")
        print(f"  Body: {resp.text[:500]}")
        return {"success": False, "error": f"status_{resp.status_code}", "body": resp.text}

    try:
        result = resp.json()
    except json.JSONDecodeError:
        print(f"  ❌ Invalid JSON response: {resp.text[:200]}")
        return {"success": False, "error": "invalid_json"}

    print(f"  Success: {result.get('success')}")
    print(f"  Message: {result.get('message')}")

    if result.get("success"):
        print(f"  CEU ID:          {result.get('ceu_id')}")
        print(f"  Title:           {result.get('title')}")
        print(f"  Provider:        {result.get('provider')}")
        print(f"  Credits:         {result.get('credits')}")
        print(f"  Completion Date: {result.get('completion_date')}")
        print(f"  Category:        {result.get('category')}")
        print(f"  Certificate:     {result.get('certificate_path') or 'None'}")
    else:
        print(f"  ❌ Import failed: {result.get('message')}")

    return result


def verify_db(db, user_id: int, count_before: int, expected_new: int) -> bool:
    """Verify that the expected number of new CEUs were created."""
    count_after = count_ceus_before(db, user_id)
    actual_new = count_after - count_before
    if actual_new == expected_new:
        print(f"  ✅ DB check: {actual_new} new CEU(s) created (was {count_before}, now {count_after})")
        return True
    else:
        print(f"  ❌ DB check: expected {expected_new} new CEU(s), got {actual_new} (was {count_before}, now {count_after})")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test email-forwarding CEU import")
    parser.add_argument("--base-url", default=BASE_URL_DEFAULT, help="API base URL")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    # Ensure DB is initialized
    init_db()
    db = SessionLocal()

    try:
        # Find the demo user (Ron Sublett)
        user = db.query(User).filter(User.email == "ron.sublett@gmail.com").first()
        if not user:
            print("❌ Demo user (ron.sublett@gmail.com) not found.")
            print("   Run `python seed.py` first to seed the database.")
            sys.exit(1)

        print(f"Demo user: {user.name} (id={user.id})")

        # Set up email alias
        alias_email = "ron.sublett@breathe.ceu"
        alias = setup_alias(db, user.id, alias_email)
        print(f"Email alias: {alias.email_alias} (id={alias.id})")

        # Count CEUs before
        count_before = count_ceus_before(db, user.id)
        print(f"CEUs before test: {count_before}")

        # Run each test
        results = []
        for sample in SAMPLE_FILES:
            result = run_test(base_url, sample, alias_email)
            results.append({"sample": sample, **result})

        # Verify DB state
        print(f"\n{'='*60}")
        print("Verification")
        print(f"{'='*60}")

        all_passed = True
        for r in results:
            if r.get("success"):
                ok = verify_db(db, user.id, count_before, len([x for x in results if x.get("success")]))
                if not ok:
                    all_passed = False
                break  # one DB check is enough since we check cumulative

        # Print summary
        print(f"\n{'='*60}")
        print("Summary")
        print(f"{'='*60}")
        for r in results:
            status = "✅ PASS" if r.get("success") else "❌ FAIL"
            print(f"  {status}  {r['sample']}")
            if not r.get("success"):
                print(f"         Error: {r.get('message') or r.get('error')}")

        # Print final CEU list
        print(f"\nFinal CEU list for user {user.id}:")
        ceus = db.query(CEU).filter(CEU.user_id == user.id).order_by(CEU.completion_date.desc()).all()
        for c in ceus:
            print(f"  [{c.id}] {c.title} | {c.provider} | {c.credits} cr | {c.completion_date} | {c.category}")

        # Verify specific expectations
        print(f"\n{'='*60}")
        print("Expected vs Actual")
        print(f"{'='*60}")

        expectations = {
            "aarc_confirmation.json": {
                "title_contains": "Advanced Mechanical Ventilation",
                "provider": "AARC",
                "credits": 4.0,
            },
            "medbridge_confirmation.json": {
                "title_contains": "Neonatal Resuscitation",
                "provider": "Medbridge",
                "credits": 3.0,
            },
            "generic_confirmation.json": {
                "title_contains": "Pulmonary Function Testing",
                "provider": "CEUFast",
                "credits": 2.5,
            },
        }

        all_expectations_met = True
        for sample, exp in expectations.items():
            r = next((x for x in results if x["sample"] == sample), None)
            if not r or not r.get("success"):
                print(f"  ❌ {sample}: webhook failed, cannot verify")
                all_expectations_met = False
                continue

            title_ok = exp["title_contains"].lower() in (r.get("title") or "").lower()
            provider_ok = (r.get("provider") or "") == exp["provider"]
            credits_ok = (r.get("credits") or 0) == exp["credits"]

            if title_ok and provider_ok and credits_ok:
                print(f"  ✅ {sample}: title, provider, credits all correct")
            else:
                print(f"  ❌ {sample}: mismatch")
                if not title_ok:
                    print(f"     Title: expected '{exp['title_contains']}' in '{r.get('title')}'")
                if not provider_ok:
                    print(f"     Provider: expected '{exp['provider']}', got '{r.get('provider')}'")
                if not credits_ok:
                    print(f"     Credits: expected {exp['credits']}, got {r.get('credits')}")
                all_expectations_met = False

        if all_expectations_met:
            print(f"\n🎉 All tests passed!")
            sys.exit(0)
        else:
            print(f"\n⚠️  Some tests failed — see output above")
            sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    main()