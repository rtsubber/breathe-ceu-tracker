"""Test script for AARC Learning Network import feature.

Tests:
1. Mock data generation
2. AARCImporter class initialization
3. Import endpoint (POST /api/users/{user_id}/import/aarc) — mock mode
4. Preview endpoint (GET /api/users/{user_id}/import/aarc/preview)
5. Confirm endpoint (POST /api/users/{user_id}/import/aarc/confirm)
6. Deduplication — confirm doesn't re-import existing courses
7. Full flow: preview → confirm → verify CEUs in DB

Run:
    cd /home/ron/.openclaw/workspace/ceu-tracker/breathe-api
    python3 test_aarc_import.py
"""
import os
import sys
import json
import requests
import subprocess
import time
import signal
from datetime import date

# Ensure local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_URL = "http://127.0.0.1:8011"
API = f"{BASE_URL}/api"

# ANSI colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

passed = 0
failed = 0
server_proc = None


def log(msg, level="info"):
    colors = {"info": CYAN, "pass": GREEN, "fail": RED, "warn": YELLOW}
    c = colors.get(level, "")
    print(f"{c}{msg}{RESET}")


def assert_eq(actual, expected, label):
    global passed, failed
    if actual == expected:
        log(f"  ✅ {label}: {actual}", "pass")
        passed += 1
    else:
        log(f"  ❌ {label}: expected {expected}, got {actual}", "fail")
        failed += 1


def assert_true(condition, label):
    global passed, failed
    if condition:
        log(f"  ✅ {label}", "pass")
        passed += 1
    else:
        log(f"  ❌ {label}", "fail")
        failed += 1


def assert_gt(value, threshold, label):
    global passed, failed
    if value > threshold:
        log(f"  ✅ {label}: {value} > {threshold}", "pass")
        passed += 1
    else:
        log(f"  ❌ {label}: expected > {threshold}, got {value}", "fail")
        failed += 1


def start_server():
    """Start the FastAPI server in background."""
    global server_proc
    log("\n🚀 Starting Breathe API server...", "info")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8011"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for server to be ready
    for _ in range(15):
        try:
            r = requests.get(f"{API}/health", timeout=2)
            if r.status_code == 200:
                log("  Server ready!", "pass")
                return
        except requests.ConnectionError:
            time.sleep(1)
    raise RuntimeError("Server failed to start within 15 seconds")


def stop_server():
    """Stop the server."""
    global server_proc
    if server_proc:
        server_proc.terminate()
        server_proc.wait(timeout=5)
        log("  Server stopped.", "info")


def test_mock_data():
    """Test 1: Mock AARC course data is correct."""
    log("\n📋 Test 1: Mock AARC course data", "info")
    from aarc_import import MOCK_AARC_COURSES, get_mock_aarc_courses, AARCCourse

    courses = get_mock_aarc_courses()
    assert_eq(len(courses), 8, "8 mock courses")
    assert_eq(courses[0]["title"], "Mechanical Ventilation: Advanced Modes", "First course title")
    assert_eq(courses[0]["provider"], "AARC", "First course provider")
    assert_eq(courses[0]["credits"], 4.0, "First course credits")
    assert_eq(courses[0]["completion_date"], "2026-01-15", "First course date")
    assert_eq(courses[0]["category"], "clinical", "First course category")

    # Verify total credits = 18 (4+3+1+2+2+2+1+3)
    total = sum(c["credits"] for c in courses)
    assert_eq(total, 18.0, "Total mock credits = 18")

    # Verify all providers are AARC
    all_aarc = all(c["provider"] == "AARC" for c in courses)
    assert_true(all_aarc, "All providers are AARC")

    # Verify AARCCourse dataclass
    course_obj = MOCK_AARC_COURSES[0]
    assert_true(isinstance(course_obj, AARCCourse), "MOCK_AARC_COURSES contains AARCCourse objects")


def test_importer_class():
    """Test 2: AARCImporter class works correctly."""
    log("\n📋 Test 2: AARCImporter class", "info")
    from aarc_import import AARCImporter, AARCImportError

    importer = AARCImporter(email=None, password=None)
    mock_courses = importer.get_mock_courses()
    assert_eq(len(mock_courses), 8, "get_mock_courses() returns 8 courses")

    # scrape() without credentials should raise
    try:
        import asyncio
        asyncio.run(importer.scrape())
        assert_true(False, "scrape() should raise without credentials")
    except AARCImportError as e:
        assert_true("credentials required" in str(e).lower(), "scrape() raises AARCImportError without credentials")

    # With email but no password
    importer2 = AARCImporter(email="test@example.com", password=None)
    try:
        import asyncio
        asyncio.run(importer2.scrape())
        assert_true(False, "scrape() should raise without password")
    except AARCImportError:
        assert_true(True, "scrape() raises AARCImportError without password")


def test_import_endpoint_mock():
    """Test 3: POST /api/users/{user_id}/import/aarc returns mock courses."""
    log("\n📋 Test 3: POST import/aarc (mock mode)", "info")

    # Create a test user first
    r = requests.post(f"{API}/auth/register", json={
        "name": "AARC Test User",
        "email": f"aarc_test_{int(time.time())}@test.com",
    })
    if r.status_code == 409:
        # User exists, login
        r = requests.post(f"{API}/auth/login", json={"email": r.json().get("detail", "").split("'")[1] if "'" in str(r.json()) else ""})
    assert_true(r.status_code in (200, 201), f"Create/login user: status {r.status_code}")
    user_id = r.json()["id"]
    log(f"  Test user id: {user_id}", "info")

    # POST import with no credentials → mock data
    r = requests.post(f"{API}/users/{user_id}/import/aarc", json={
        "email": None,
        "password": None,
        "use_mock": True,
    })
    assert_eq(r.status_code, 200, f"Import endpoint status: {r.status_code}")
    data = r.json()
    assert_eq(data["source"], "mock", "Source is 'mock'")
    assert_eq(data["total_found"], 8, "Total found: 8 courses")
    assert_eq(data["new_count"], 8, "New count: 8 (nothing in DB yet)")
    assert_eq(data["already_imported_count"], 0, "Already imported: 0")

    # Verify course structure
    courses = data["courses"]
    assert_true(len(courses) == 8, "8 courses in response")
    assert_true("title" in courses[0], "Course has title field")
    assert_true("provider" in courses[0], "Course has provider field")
    assert_true("credits" in courses[0], "Course has credits field")
    assert_true("completion_date" in courses[0], "Course has completion_date field")
    assert_true("category" in courses[0], "Course has category field")
    assert_true("already_imported" in courses[0], "Course has already_imported field")

    return user_id


def test_preview_endpoint(user_id):
    """Test 4: GET /api/users/{user_id}/import/aarc/preview."""
    log("\n📋 Test 4: GET import/aarc/preview (mock mode)", "info")

    r = requests.get(f"{API}/users/{user_id}/import/aarc/preview")
    assert_eq(r.status_code, 200, f"Preview endpoint status: {r.status_code}")
    data = r.json()
    assert_eq(data["source"], "mock", "Preview source is 'mock'")
    assert_eq(data["total_found"], 8, "Preview total_found: 8")
    assert_eq(data["new_count"], 8, "Preview new_count: 8")


def test_confirm_endpoint(user_id):
    """Test 5: POST /api/users/{user_id}/import/aarc/confirm saves courses."""
    log("\n📋 Test 5: POST import/aarc/confirm", "info")

    # First get preview
    r = requests.get(f"{API}/users/{user_id}/import/aarc/preview")
    preview = r.json()
    courses = preview["courses"]

    # Confirm all 8 courses
    r = requests.post(f"{API}/users/{user_id}/import/aarc/confirm", json={
        "courses": courses,
    })
    assert_eq(r.status_code, 200, f"Confirm endpoint status: {r.status_code}")
    data = r.json()
    assert_eq(data["imported"], 8, "Imported 8 courses")
    assert_eq(data["skipped_duplicates"], 0, "Skipped 0 duplicates")
    assert_eq(data["total_credits"], 18.0, "Total credits imported: 18")
    assert_eq(len(data["errors"]), 0, "No errors")

    # Verify CEUs are now in the database
    r = requests.get(f"{API}/users/{user_id}/ceus")
    ceus = r.json()
    aarc_ceus = [c for c in ceus if c["provider"] == "AARC"]
    assert_eq(len(aarc_ceus), 8, "8 AARC CEUs now in DB")

    return courses


def test_deduplication(user_id, imported_courses):
    """Test 6: Confirm endpoint skips duplicates (re-import same courses)."""
    log("\n📋 Test 6: Deduplication (re-import same courses)", "info")

    # Try to re-import the same courses
    r = requests.post(f"{API}/users/{user_id}/import/aarc/confirm", json={
        "courses": imported_courses,
    })
    assert_eq(r.status_code, 200, f"Re-import status: {r.status_code}")
    data = r.json()
    assert_eq(data["imported"], 0, "Re-imported 0 (all dupes)")
    assert_eq(data["skipped_duplicates"], 8, "Skipped 8 duplicates")
    assert_eq(data["total_credits"], 0.0, "0 credits (all dupes)")

    # Verify CEU count didn't change
    r = requests.get(f"{API}/users/{user_id}/ceus")
    ceus = r.json()
    aarc_ceus = [c for c in ceus if c["provider"] == "AARC"]
    assert_eq(len(aarc_ceus), 8, "Still 8 AARC CEUs in DB (no dupes)")

    # Now preview should show all as already_imported
    r = requests.get(f"{API}/users/{user_id}/import/aarc/preview")
    data = r.json()
    assert_eq(data["already_imported_count"], 8, "Preview shows 8 already_imported")
    assert_eq(data["new_count"], 0, "Preview shows 0 new")


def test_partial_import(user_id, all_courses):
    """Test 7: Import only selected courses (partial confirm)."""
    log("\n📋 Test 7: Partial import (select subset)", "info")

    # Create a new user for clean test
    r = requests.post(f"{API}/auth/register", json={
        "name": "Partial Import Test",
        "email": f"partial_{int(time.time())}@test.com",
    })
    assert_true(r.status_code in (200, 201), f"Create partial test user: {r.status_code}")
    partial_user_id = r.json()["id"]

    # Import only 3 courses
    selected = all_courses[:3]
    r = requests.post(f"{API}/users/{partial_user_id}/import/aarc/confirm", json={
        "courses": selected,
    })
    assert_eq(r.status_code, 200, f"Partial import status: {r.status_code}")
    data = r.json()
    assert_eq(data["imported"], 3, "Imported 3 courses")
    assert_eq(data["skipped_duplicates"], 0, "Skipped 0 (new user)")
    assert_eq(data["total_credits"], 8.0, "Total credits: 8 (4+3+1)")

    # Verify in DB
    r = requests.get(f"{API}/users/{partial_user_id}/ceus")
    ceus = r.json()
    assert_eq(len(ceus), 3, "3 CEUs in DB for partial user")


def test_error_handling():
    """Test 8: Error handling — invalid user_id, empty confirm."""
    log("\n📋 Test 8: Error handling", "info")

    # Import for non-existent user
    r = requests.post(f"{API}/users/99999/import/aarc", json={
        "email": None,
        "password": None,
        "use_mock": True,
    })
    assert_eq(r.status_code, 404, "Import for invalid user → 404")

    # Confirm for non-existent user
    r = requests.post(f"{API}/users/99999/import/aarc/confirm", json={
        "courses": [],
    })
    assert_eq(r.status_code, 404, "Confirm for invalid user → 404")

    # Empty confirm (no courses selected)
    r = requests.post(f"{API}/auth/register", json={
        "name": "Empty Confirm Test",
        "email": f"empty_{int(time.time())}@test.com",
    })
    user_id = r.json()["id"]
    r = requests.post(f"{API}/users/{user_id}/import/aarc/confirm", json={
        "courses": [],
    })
    assert_eq(r.status_code, 200, "Empty confirm → 200")
    data = r.json()
    assert_eq(data["imported"], 0, "Empty confirm → 0 imported")
    assert_eq(len(data["errors"]), 1, "Empty confirm → 1 error message")


def main():
    """Run all tests."""
    log("=" * 60, "info")
    log("  AARC Learning Network Import — Test Suite", "info")
    log("=" * 60, "info")

    # Unit tests (no server needed)
    test_mock_data()
    test_importer_class()

    # Integration tests (need server)
    start_server()
    try:
        user_id = test_import_endpoint_mock()
        test_preview_endpoint(user_id)
        imported_courses = test_confirm_endpoint(user_id)
        test_deduplication(user_id, imported_courses)
        test_partial_import(user_id, imported_courses)
        test_error_handling()
    finally:
        stop_server()

    # Results
    log("\n" + "=" * 60, "info")
    total = passed + failed
    log(f"  Results: {passed}/{total} passed", "info")
    if failed == 0:
        log("  ✅ ALL TESTS PASSED!", "pass")
    else:
        log(f"  ❌ {failed} test(s) failed!", "fail")
    log("=" * 60, "info")

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()