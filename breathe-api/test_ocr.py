"""Test OCR + LLM parsing with realistic certificate text samples.

Simulates OCR output from real CE certificates and verifies that both
the Claude API parser and the regex fallback extract correct fields.

Run: python3 test_ocr.py
"""
import sys
import os
import json

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ocr import parse_with_claude, parse_with_regex, parse_ceu_data, normalize_date


# ─── Simulated OCR output from real certificates ────────────────
# Each sample simulates what easyocr would extract (list of text lines + confidence).

AARC_CERTIFICATE = [
    ("American Association for Respiratory Care", 0.95),
    ("AARC Learning Network", 0.93),
    ("Certificate of Completion", 0.97),
    ("Mechanical Ventilation: Advanced Modes and Management", 0.92),
    ("Presented by: AARC", 0.89),
    ("4.0 CRCE Credits", 0.91),
    ("Completed on 03/15/2026", 0.88),
    ("Participant: John Doe, RRT", 0.85),
    ("Authorized by AARC", 0.82),
]

MEDBRIDGE_CERTIFICATE = [
    ("Medbridge", 0.96),
    ("Certificate of Completion", 0.97),
    ("Airway Management in Critical Care Settings", 0.94),
    ("Provider: Medbridge Education", 0.90),
    ("6 Contact Hours", 0.93),
    ("Date of Completion: January 22, 2026", 0.87),
    ("Awarded 6.0 CEUs", 0.89),
    ("Participant: Jane Smith, CRT", 0.84),
]

HOSPITAL_INSERVICE = [
    ("St. Mary's Regional Medical Center", 0.94),
    ("Department of Respiratory Therapy", 0.91),
    ("In-Service Training Certificate", 0.96),
    ("Title: ECMO Management and Safety Protocols", 0.90),
    ("Sponsored by: St. Mary's Regional Medical Center", 0.86),
    ("2 credit hours", 0.88),
    ("Date: 02/10/2026", 0.85),
    ("Presented by Sarah Johnson, RRT-NPS", 0.80),
    ("Safety Category", 0.78),
]

CEUFAST_CERTIFICATE = [
    ("CEUFast", 0.97),
    ("Certificate of Completion", 0.96),
    ("Neonatal Respiratory Care Fundamentals", 0.93),
    ("Provider: CEUFast, Inc.", 0.90),
    ("8.0 Contact Hours", 0.94),
    ("Completed: 04/05/2026", 0.89),
    ("Awarded 8 CEUs", 0.91),
    ("Category: Clinical", 0.83),
    ("Student: Robert Chen, RRT", 0.85),
]

HEALTHSTREAM_CERTIFICATE = [
    ("HealthStream", 0.96),
    ("Certificate of Completion", 0.97),
    ("Patient Safety: Preventing Medication Errors", 0.92),
    ("Provider: HealthStream, Inc.", 0.89),
    ("1.0 Credit Hour", 0.91),
    ("Date of Completion: 05/18/2026", 0.88),
    ("Category: Safety", 0.84),
    ("Completed by: Michael Torres, RRT", 0.82),
]

RELIAS_CERTIFICATE = [
    ("Relias Learning", 0.95),
    ("Certificate of Achievement", 0.96),
    ("Ethical Decision Making in Healthcare", 0.93),
    ("Provider: Relias Learning", 0.90),
    ("3.0 CEUs", 0.92),
    ("Completed on June 12, 2026", 0.87),
    ("Category: Ethics", 0.85),
    ("Participant: Emily Davis, CRT", 0.83),
]

# ─── Expected results for validation ────────────────────────────

EXPECTED = {
    "AARC": {
        "sample": AARC_CERTIFICATE,
        "title_contains": "Mechanical Ventilation",
        "provider_contains": "AARC",
        "credits": 4.0,
        "date": "2026-03-15",
        "category": "clinical",
    },
    "Medbridge": {
        "sample": MEDBRIDGE_CERTIFICATE,
        "title_contains": "Airway Management",
        "provider_contains": "Medbridge",
        "credits": 6.0,
        "date": "2026-01-22",
        "category": "clinical",
    },
    "Hospital In-Service": {
        "sample": HOSPITAL_INSERVICE,
        "title_contains": "ECMO",
        "provider_contains": "St. Mary",
        "credits": 2.0,
        "date": "2026-02-10",
        "category": "safety",
    },
    "CEUFast": {
        "sample": CEUFAST_CERTIFICATE,
        "title_contains": "Neonatal",
        "provider_contains": "CEUFast",
        "credits": 8.0,
        "date": "2026-04-05",
        "category": "clinical",
    },
    "HealthStream": {
        "sample": HEALTHSTREAM_CERTIFICATE,
        "title_contains": "Patient Safety",
        "provider_contains": "HealthStream",
        "credits": 1.0,
        "date": "2026-05-18",
        "category": "safety",
    },
    "Relias": {
        "sample": RELIAS_CERTIFICATE,
        "title_contains": "Ethical",
        "provider_contains": "Relias",
        "credits": 3.0,
        "date": "2026-06-12",
        "category": "ethics",
    },
}


# ─── Test helpers ───────────────────────────────────────────────

def _check(name: str, field: str, expected, actual, results: list) -> bool:
    """Check a field and record pass/fail."""
    if isinstance(expected, float):
        ok = abs((actual or 0) - expected) < 0.01
    elif field == "title_contains":
        ok = expected.lower() in (actual or "").lower()
    elif field == "provider_contains":
        ok = expected.lower() in (actual or "").lower()
    else:
        ok = actual == expected

    status = "✅" if ok else "❌"
    results.append((name, field, status, expected, actual))
    return ok


def run_regex_tests() -> dict:
    """Run regex fallback parser on all samples."""
    print("\n" + "=" * 60)
    print("TEST 1: Regex Fallback Parser")
    print("=" * 60)

    all_pass = True
    summary = {}

    for cert_name, expected in EXPECTED.items():
        print(f"\n--- {cert_name} Certificate ---")
        result = parse_with_regex(expected["sample"])

        results = []
        title_ok = _check(cert_name, "title_contains", expected["title_contains"], result["title"], results)
        provider_ok = _check(cert_name, "provider_contains", expected["provider_contains"], result["provider"], results)
        credits_ok = _check(cert_name, "credits", expected["credits"], result["credits"], results)
        date_ok = _check(cert_name, "date", expected["date"], result["completion_date"], results)
        cat_ok = _check(cert_name, "category", expected["category"], result["category"], results)

        cert_pass = title_ok and provider_ok and credits_ok and date_ok and cat_ok
        all_pass = all_pass and cert_pass

        for name, field, status, exp, act in results:
            print(f"  {status} {field}: expected={exp!r}, got={act!r}")

        print(f"  {'✅ ALL PASS' if cert_pass else '❌ SOME FAILED'}")
        summary[cert_name] = {"pass": cert_pass, "result": result}

    return {"all_pass": all_pass, "summary": summary}


def run_claude_tests() -> dict:
    """Run Claude API parser on all samples."""
    print("\n" + "=" * 60)
    print("TEST 2: Claude API Parser")
    print("=" * 60)

    all_pass = True
    summary = {}

    for cert_name, expected in EXPECTED.items():
        print(f"\n--- {cert_name} Certificate ---")
        raw_text = "\n".join(t for t, c in expected["sample"])
        result = parse_with_claude(raw_text)

        if result is None:
            print("  ⚠️  Claude API not available or failed — skipping")
            summary[cert_name] = {"pass": None, "result": None, "skipped": True}
            continue

        results = []
        title_ok = _check(cert_name, "title_contains", expected["title_contains"], result.get("title", ""), results)
        provider_ok = _check(cert_name, "provider_contains", expected["provider_contains"], result.get("provider", ""), results)
        credits_ok = _check(cert_name, "credits", expected["credits"], result.get("credits", 0), results)
        date_ok = _check(cert_name, "date", expected["date"], result.get("completion_date", ""), results)
        cat_ok = _check(cert_name, "category", expected["category"], result.get("category", ""), results)

        cert_pass = title_ok and provider_ok and credits_ok and date_ok and cat_ok
        all_pass = all_pass and cert_pass

        for name, field, status, exp, act in results:
            print(f"  {status} {field}: expected={exp!r}, got={act!r}")

        print(f"  {'✅ ALL PASS' if cert_pass else '❌ SOME FAILED'}")
        summary[cert_name] = {"pass": cert_pass, "result": result, "skipped": False}

    return {"all_pass": all_pass, "summary": summary}


def run_hybrid_tests() -> dict:
    """Run hybrid pipeline (parse_ceu_data) on all samples."""
    print("\n" + "=" * 60)
    print("TEST 3: Hybrid Pipeline (Claude → Regex fallback)")
    print("=" * 60)

    all_pass = True
    summary = {}

    for cert_name, expected in EXPECTED.items():
        print(f"\n--- {cert_name} Certificate ---")
        result = parse_ceu_data(expected["sample"])

        results = []
        title_ok = _check(cert_name, "title_contains", expected["title_contains"], result["title"], results)
        provider_ok = _check(cert_name, "provider_contains", expected["provider_contains"], result["provider"], results)
        credits_ok = _check(cert_name, "credits", expected["credits"], result["credits"], results)
        date_ok = _check(cert_name, "date", expected["date"], result["completion_date"], results)
        cat_ok = _check(cert_name, "category", expected["category"], result["category"], results)

        cert_pass = title_ok and provider_ok and credits_ok and date_ok and cat_ok
        all_pass = all_pass and cert_pass

        for name, field, status, exp, act in results:
            print(f"  {status} {field}: expected={exp!r}, got={act!r}")

        # Show which parser was used (if confidence > 0.7 and clean fields, likely Claude)
        print(f"  Confidence: {result.get('confidence', 0):.3f}")
        print(f"  {'✅ ALL PASS' if cert_pass else '❌ SOME FAILED'}")
        summary[cert_name] = {"pass": cert_pass, "result": result}

    return {"all_pass": all_pass, "summary": summary}


def run_email_parser_tests():
    """Test email_parser with provider domain map and credit patterns."""
    print("\n" + "=" * 60)
    print("TEST 4: Email Parser — Provider Domains + Credit Patterns")
    print("=" * 60)

    from email_parser import (
        PROVIDER_DOMAINS, _extract_credits, _provider_from_sender,
        parse_ceu_email,
    )

    all_pass = True

    # Test provider domain lookup
    print("\n--- Provider Domain Lookup ---")
    test_domains = {
        "noreply@healthstream.com": "HealthStream",
        "alerts@relias.com": "Relias Learning",
        "support@learnaarc.org": "AARC",
        "info@aarc.org": "AARC",
        "noreply@medbridgeeducation.com": "Medbridge",
        "noreply@medscape.com": "Medscape",
        "support@proce.com": "ProCE",
        "info@respline.com": "RespLine",
        "noreply@ceufast.com": "CEUFast",
        "support@respiratorytherapy.com": "Respiratory Therapy CE",
        "info@learningmanagement.com": "Learning Management",
        "noreply@capce.org": "CAPCE",
        "support@cmezone.com": "CME Zone",
    }

    for email, expected_provider in test_domains.items():
        actual = _provider_from_sender(email)
        ok = actual == expected_provider
        status = "✅" if ok else "❌"
        print(f"  {status} {email} → {actual!r} (expected {expected_provider!r})")
        all_pass = all_pass and ok

    # Test credit extraction patterns
    print("\n--- Credit Extraction Patterns ---")
    credit_tests = [
        ("4 contact hours", 4.0),
        ("4.0 contact hour", 4.0),
        ("Contact Hours: 6.0", 6.0),
        ("6 CEUs", 6.0),
        ("Awarded 8 CEUs", 8.0),
        ("3 credit hours", 3.0),
        ("3.0 credit hour", 3.0),
        ("2.5 AMA PRA Category 1 Credit", 2.5),
        ("4 CRCE credits", 4.0),
        ("4.0 CRCE credit", 4.0),
        ("1.0 Credit Hour", 1.0),
        ("Credits: 5.0", 5.0),
        ("Earned 10 credits", 10.0),
    ]

    for text, expected_credits in credit_tests:
        actual = _extract_credits(text)
        ok = abs(actual - expected_credits) < 0.01
        status = "✅" if ok else "❌"
        print(f"  {status} {text!r} → {actual!r} (expected {expected_credits!r})")
        all_pass = all_pass and ok

    # Test full email parse with a HealthStream-style email
    print("\n--- Full Email Parse (HealthStream sample) ---")
    email_result = parse_ceu_email(
        from_email="noreply@healthstream.com",
        to_email="rt@example.com",
        subject="Certificate of Completion: Patient Safety Course",
        text=(
            "Dear John,\n\n"
            "Congratulations on completing the following course:\n\n"
            "Course Title: Patient Safety: Preventing Medication Errors\n"
            "Provider: HealthStream, Inc.\n"
            "Contact Hours: 1.0\n"
            "Date of Completion: 05/18/2026\n\n"
            "Your certificate is attached.\n\n"
            "Thank you,\nHealthStream Support"
        ),
        html=None,
    )

    checks = [
        ("provider", "HealthStream", email_result["provider"]),
        ("credits", 1.0, email_result["credits"]),
        ("date", "2026-05-18", email_result["completion_date"]),
    ]
    for field, exp, act in checks:
        if field == "provider":
            ok = exp.lower() in act.lower()
        else:
            ok = act == exp
        status = "✅" if ok else "❌"
        print(f"  {status} {field}: expected={exp!r}, got={act!r}")
        all_pass = all_pass and ok

    return {"all_pass": all_pass}


# ─── Main ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Breathe OCR + LLM Vision Test Suite")
    print("=" * 60)

    # Test 1: Regex fallback parser
    regex_results = run_regex_tests()

    # Test 2: Claude API parser
    claude_results = run_claude_tests()

    # Test 3: Hybrid pipeline
    hybrid_results = run_hybrid_tests()

    # Test 4: Email parser
    email_results = run_email_parser_tests()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(f"\nRegex Parser:     {'✅ ALL PASS' if regex_results['all_pass'] else '❌ FAILURES'}")
    
    claude_skipped = all(s.get("skipped") for s in claude_results["summary"].values())
    if claude_skipped:
        print(f"Claude Parser:   ⚠️  SKIPPED (API not available)")
    else:
        print(f"Claude Parser:    {'✅ ALL PASS' if claude_results['all_pass'] else '❌ FAILURES'}")

    print(f"Hybrid Pipeline:  {'✅ ALL PASS' if hybrid_results['all_pass'] else '❌ FAILURES'}")
    print(f"Email Parser:     {'✅ ALL PASS' if email_results['all_pass'] else '❌ FAILURES'}")

    # Exit code
    overall_pass = (
        regex_results["all_pass"]
        and hybrid_results["all_pass"]
        and email_results["all_pass"]
        and (claude_skipped or claude_results["all_pass"])
    )

    print("\n" + "=" * 60)
    if overall_pass:
        print("🎉 ALL TESTS PASSED")
    else:
        print("💥 SOME TESTS FAILED")
    print("=" * 60)

    sys.exit(0 if overall_pass else 1)