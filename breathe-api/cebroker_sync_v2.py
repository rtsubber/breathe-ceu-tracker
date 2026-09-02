#!/usr/bin/env python3
"""cebroker_sync_v2.py — Breathe → CE Broker automated CEU sync.

Auth chain: OTP → AgentMail (read code) → id.cebroker.com → OAuth2 → app.cebroker.com session
Submit: POST /api/v1/ce-self-report/submissions

Usage:
  python3 cebroker_sync_v2.py --sync          # Sync all unsynced CEUs for a user
  python3 cebroker_sync_v2.py --sync --user-id 15
  python3 cebroker_sync_v2.py --test-auth       # Test auth chain only
  python3 cebroker_sync_v2.py --test-auth --user-id 15
  python3 cebroker_sync_v2.py --status          # Show sync status for all users
"""

import json
import os
import sys
import time
import re
import sqlite3
import argparse
import subprocess
import urllib.request
import http.cookiejar
from datetime import datetime

# === Config ===
WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
BREATHE_DB = f"{WORKSPACE}/ceu-tracker/breathe-api/breathe.db"
AGENTMAIL_CONFIG = f"{WORKSPACE}/.agentmail_config.json"

# CE Broker API
CEB_EMAIL = "ron.sublett@gmail.com"  # Default user; will be per-user once settings page built
ID_BASE = "https://id.cebroker.com"
APP_BASE = "https://app.cebroker.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# Traditional CE config (TX Respiratory Care Practitioner)
PROFESSION_CREDIT_ID = 9488
PK_LICENSE = 26094428  # TX license RCP00075612
ATTACHMENT_MODE = "ELECTRONIC"
COURSE_TYPE = "CD_LIVE"
DELIVERY_METHOD = "WC"  # Web-based Program


class CEBrokerSync:
    """Handles authentication and submission to CE Broker (Propelus)."""

    def __init__(self, email=CEB_EMAIL, pk_license=PK_LICENSE):
        self.email = email
        self.pk_license = pk_license
        self.profession_credit_id = PROFESSION_CREDIT_ID
        self.session = None
        self.jar = http.cookiejar.CookieJar()
        self.opener = None

    def _make_opener(self):
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.opener.addheaders = [
            ('User-Agent', UA), ('Accept', 'application/json')]

        class NR(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        nr = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar), NR())
        nr.addheaders = [('User-Agent', UA), ('Accept', 'application/json')]
        return self.opener, nr

    def send_otp(self, email=None):
        """Step 1 only: ask CE Broker to email a sign-in OTP. Cookie-independent."""
        email = email or self.email
        req = urllib.request.Request(
            f"{ID_BASE}/api/auth/email-otp/send-verification-otp",
            data=json.dumps({'email': email, 'type': 'sign-in'}).encode(),
            headers={'User-Agent': UA, 'Content-Type': 'application/json',
                     'Origin': ID_BASE, 'Referer': f'{ID_BASE}/auth/sign-in'})
        urllib.request.urlopen(req, timeout=20)
        return True

    def poll_agentmail_otp(self):
        """Step 2 (legacy CLI mode): poll AgentMail for the OTP code."""
        from agentmail import AgentMail  # lazy — optional dependency
        cfg = json.load(open(AGENTMAIL_CONFIG))
        client = AgentMail(api_key=cfg['api_key'])
        for attempt in range(18):
            time.sleep(10)
            resp = client.inboxes.messages.list(
                inbox_id=cfg['inbox_id'], limit=10)
            for m in resp.messages:
                subj = getattr(m, 'subject', '') or ''
                if 'propelus' in subj.lower() or 'verification' in subj.lower():
                    preview = getattr(m, 'preview', '') or ''
                    ts = getattr(m, 'timestamp', None)
                    codes = re.findall(r'\b(\d{6})\b', preview)
                    if codes and ts and (time.time() - ts.timestamp()) < 120:
                        print(f"[auth] GOT OTP (age {int(time.time()-ts.timestamp())}s)")
                        return codes[0]
            print(f"[auth] poll {attempt+1}/18...")
        raise Exception("No OTP code received from AgentMail")

    def login_with_otp(self, otp_code):
        """Steps 3-5: login with OTP → OAuth2 bridge → verify app session.

        Raises Exception with a readable message if CE Broker rejects the code.
        """
        opener, nr = self._make_opener()
        self.opener, self.nr = opener, nr

        # Step 3: Login with OTP
        req = urllib.request.Request(
            f"{ID_BASE}/api/auth/sign-in/email-otp",
            data=json.dumps({'email': self.email, 'otp': otp_code}).encode(),
            headers={'Content-Type': 'application/json',
                     'Origin': ID_BASE, 'Referer': f'{ID_BASE}/auth/sign-in'})
        try:
            with opener.open(req, timeout=20) as r:
                data = json.loads(r.read().decode())
                user_name = data.get('user', {}).get('name', 'unknown')
                print(f"[auth] Login: {user_name}")
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            raise Exception(f"CE Broker rejected the OTP (HTTP {e.code}): {body}")

        # Step 4: OAuth2 bridge to app.cebroker.com
        req = urllib.request.Request(
            f'{APP_BASE}/api/auth/sign-in/oauth2',
            data=json.dumps({'providerId': 'passport-auth',
                            'callbackURL': f'{APP_BASE}/credentials'}).encode(),
            headers={'Content-Type': 'application/json',
                     'Origin': APP_BASE, 'Referer': f'{APP_BASE}/credentials'})
        with nr.open(req, timeout=15) as r:
            auth_url = json.loads(r.read().decode()).get('url', '')

        try:
            with nr.open(urllib.request.Request(auth_url, headers={
                'User-Agent': UA, 'Accept': 'text/html',
                'Referer': f'{APP_BASE}/credentials'}), timeout=15) as r:
                pass
        except urllib.error.HTTPError as e:
            cb_url = e.headers.get('Location', '')
            if cb_url:
                with opener.open(urllib.request.Request(cb_url, headers={
                    'User-Agent': UA, 'Accept': 'text/html',
                    'Referer': ID_BASE}), timeout=15) as r:
                    pass

        # Step 5: Verify session
        req = urllib.request.Request(f'{APP_BASE}/api/v1/users/me',
                                     headers={'Accept': 'application/json'})
        try:
            with opener.open(req, timeout=10) as r:
                if r.status == 200:
                    print("[auth] Session verified ✅")
                    return True
        except urllib.error.HTTPError:
            pass
        raise Exception("OAuth2 bridge failed — no app session")

    def save_session(self, path):
        """Save the app-session cookie jar for later reuse (per-user file, 0600)."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mcj = http.cookiejar.MozillaCookieJar(path)
        for c in self.jar:
            mcj.set_cookie(c)
        mcj.save(ignore_discard=True, ignore_expires=True)
        os.chmod(path, 0o600)

    def load_session(self, path):
        """Load a saved cookie jar. Returns True if the app session still validates."""
        if not os.path.exists(path):
            return False
        mcj = http.cookiejar.MozillaCookieJar(path)
        try:
            mcj.load(ignore_discard=True, ignore_expires=True)
        except Exception:
            return False
        self.jar = mcj
        self.opener, self.nr = self._make_opener()
        try:
            req = urllib.request.Request(f'{APP_BASE}/api/v1/users/me',
                                         headers={'Accept': 'application/json'})
            with self.opener.open(req, timeout=10) as r:
                return r.status == 200
        except Exception:
            return False

    def authenticate(self, otp_code=None):
        """Full auth chain. If otp_code is supplied (customer manual entry), use it
        directly. Otherwise poll AgentMail for the code (legacy CLI mode)."""
        if not otp_code:
            print("[auth] Sending OTP to", self.email)
            self.send_otp()
            otp_code = self.poll_agentmail_otp()
        return self.login_with_otp(otp_code)

    def get_licenses(self):
        """Get user's licenses from CE Broker."""
        req = urllib.request.Request(f'{APP_BASE}/api/v1/licenses',
                                     headers={'Accept': 'application/json'})
        with self.opener.open(req, timeout=15) as r:
            return json.loads(r.read().decode())

    def resolve_license(self, license_number=None):
        """After auth, fetch the user's licenses from CE Broker and pick the right one.
        Sets self.pk_license and self.profession_credit_id dynamically.
        If license_number is provided, tries to match it. Else uses the first active license."""
        try:
            licenses = self.get_licenses()
            # Handle both list and dict responses
            if isinstance(licenses, dict) and 'licenses' in licenses:
                licenses = licenses['licenses']
            if not isinstance(licenses, list) or not licenses:
                print("[license] No licenses returned from CE Broker — using defaults")
                return
            # Try to match by license_number if provided
            chosen = None
            if license_number:
                for lic in licenses:
                    lic_num = lic.get('licenseNumber') or lic.get('license_number') or ''
                    if lic_num.lower() == license_number.lower():
                        chosen = lic
                        break
            if not chosen:
                chosen = licenses[0]  # fallback: first license
            # Extract pkLicense and professionCreditId (handle various key names)
            self.pk_license = (chosen.get('pkLicense') or chosen.get('pk_license')
                               or chosen.get('id') or self.pk_license)
            self.profession_credit_id = (chosen.get('professionCreditId')
                                         or chosen.get('profession_credit_id')
                                         or PROFESSION_CREDIT_ID)
            print(f"[license] Resolved: pkLicense={self.pk_license}, "
                  f"professionCreditId={self.profession_credit_id}")
        except Exception as e:
            print(f"[license] Could not fetch licenses (using defaults): {e}")

    def get_form_config(self, profession_credit_id=None):
        """Get form config: subject areas, questions, course types."""
        config = {}

        # Subject areas
        req = urllib.request.Request(
            f'{APP_BASE}/api/v1/ce-self-report/credits/{profession_credit_id}/subject-areas?pkLicense={self.pk_license}',
            headers={'Accept': 'application/json'})
        with self.opener.open(req, timeout=15) as r:
            data = json.loads(r.read().decode())
            config['subject_areas'] = data.get('subjectAreas', [])

        # Questions
        req = urllib.request.Request(
            f'{APP_BASE}/api/v1/ce-self-report/credits/{profession_credit_id}/questions?pkLicense={self.pk_license}',
            headers={'Accept': 'application/json'})
        with self.opener.open(req, timeout=15) as r:
            data = json.loads(r.read().decode())
            config['questions'] = data.get('questions', [])

        # Credits info (course types, attestation, etc.)
        req = urllib.request.Request(
            f'{APP_BASE}/api/v1/ce-self-report/credits/{profession_credit_id}?pkLicense={self.pk_license}',
            headers={'Accept': 'application/json'})
        with self.opener.open(req, timeout=15) as r:
            config['credits'] = json.loads(r.read().decode())

        return config

    def upload_certificate(self, cert_path):
        """Upload a certificate PDF to CE Broker. Returns file token."""
        if not os.path.exists(cert_path):
            print(f"[upload] Certificate not found: {cert_path}")
            return None, None, None

        cookie_str = '; '.join(f'{c.name}={c.value}' for c in self.jar)
        result = subprocess.run([
            'curl', '-s', '-X', 'POST', f'{APP_BASE}/api/v1/files/upload',
            '-H', f'User-Agent: {UA}', '-H', 'Accept: application/json',
            '-F', f'file=@{cert_path};type=application/pdf',
            '-b', cookie_str
        ], capture_output=True, text=True, timeout=30)

        try:
            data = json.loads(result.stdout)
            token = data.get('token')
            size = data.get('size', os.path.getsize(cert_path))
            name = data.get('name', os.path.basename(cert_path))
            print(f"[upload] Certificate uploaded: {name} ({size} bytes)")
            return token, name, size
        except Exception:
            print(f"[upload] Failed: {result.stdout[:200]}")
            return None, None, None

    def validate_submission(self, submission):
        """Validate a submission before final submit. Returns (bool, errors)."""
        payload = json.dumps({'submission': submission}).encode()
        req = urllib.request.Request(
            f'{APP_BASE}/api/v1/ce-self-report/submissions/validate',
            data=payload,
            headers={'Content-Type': 'application/json',
                     'Accept': 'application/json',
                     'Origin': APP_BASE,
                     'Referer': f'{APP_BASE}/report-ce/report/{self.profession_credit_id}?lic={self.pk_license}'})
        try:
            with self.opener.open(req, timeout=20) as r:
                resp = json.loads(r.read().decode())
                valid = resp.get('valid', False)
                errors = resp.get('errors', [])
                if valid:
                    print("[validate] Validation passed ✅")
                else:
                    print(f"[validate] Validation failed: {errors}")
                return valid, errors
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"[validate] HTTP {e.code}: {body[:300]}")
            return False, [body]

    def submit_ceu(self, ceu_data, form_config, cert_path=None):
        """Submit a CEU to CE Broker.

        Args:
            ceu_data: dict with keys: title, provider, approval, completion_date,
                      hours, category, course_name, delivery_method
            form_config: from get_form_config()
            cert_path: path to certificate PDF (optional)

        Returns:
            dict with idPostCeCredit and status, or None on failure
        """
        sa_id = form_config['subject_areas'][0]['id'] if form_config['subject_areas'] else 8790
        questions = form_config['questions']

        # Build answers from questions — ORDER MATTERS!
        # 'provider'/'educational' and 'approval'/'recognized' must be checked BEFORE 'course'
        # because 'course' appears in ALL question texts.
        answers = []
        for q in questions:
            qtext = q['text'].lower()
            if 'provider' in qtext or 'educational' in qtext:
                # "What is the name of the educational provider that presented this course?"
                answers.append({'questionId': q['id'],
                               'answer': ceu_data.get('provider', '')})
            elif 'approval' in qtext or 'recognized' in qtext or 'approved' in qtext:
                # "How was this course recognized or approved?"
                answers.append({'questionId': q['id'],
                               'answer': ceu_data.get('approval', 'Approved by AARC (American Association for Respiratory Care)')})
            elif 'name of the ce' in qtext or 'name of this ce' in qtext or ('course' in qtext and 'name' in qtext and 'provider' not in qtext and 'approved' not in qtext):
                # "What is the name of the CE course?"
                answers.append({'questionId': q['id'],
                               'answer': ceu_data.get('course_name', ceu_data.get('title', ''))})
            else:
                answers.append({'questionId': q['id'], 'answer': 'Yes'})

        # Upload certificate if provided
        attachments = []
        if cert_path and os.path.exists(cert_path):
            token, name, size = self.upload_certificate(cert_path)
            if token:
                attachments.append({
                    'token': token,
                    'fileName': name,
                    'fileSize': size,
                })

        # Convert date to MM/DD/YYYY
        date_str = ceu_data.get('completion_date', '')
        if '-' in date_str:
            # Convert YYYY-MM-DD to MM/DD/YYYY
            parts = date_str.split('-')
            date_str = f"{parts[1]}/{parts[2]}/{parts[0]}"

        # Build submission payload (FLAT — not wrapped in "submission")
        submission = {
            'pkLicense': self.pk_license,
            'professionCreditId': self.profession_credit_id,
            'completionDate': date_str,
            'subjectAreas': [{'id': sa_id, 'hours': float(ceu_data.get('hours', 1.0)), 'answer': True}],
            'answers': answers,
            'course': {
                'id': 1,
                'name': ceu_data.get('course_name', ceu_data.get('title', 'CE Course')),
                'type': ceu_data.get('course_type', COURSE_TYPE),
                'deliveryMethod': ceu_data.get('delivery_method', DELIVERY_METHOD),
            },
            'provider': {
                'id': 1,
                'name': ceu_data.get('provider', ''),
            },
            'attachmentMode': ATTACHMENT_MODE,
            'attachments': attachments,
            'attested': True,  # Must be literally `true` (not "attestation")
        }

        # Validate first
        valid, errors = self.validate_submission(submission)
        if not valid:
            # Check if errors are just warnings (e.g., delivery method)
            if errors and all(e.get('code') != 'DELIVERY_METHOD_REQUIRED' for e in errors):
                print(f"[submit] Validation failed — not submitting")
                return None

        # Submit (flat payload, not wrapped)
        payload = json.dumps(submission).encode()
        req = urllib.request.Request(
            f'{APP_BASE}/api/v1/ce-self-report/submissions',
            data=payload,
            headers={'Content-Type': 'application/json',
                     'Accept': 'application/json',
                     'Origin': APP_BASE,
                     'Referer': f'{APP_BASE}/report-ce/report/{self.profession_credit_id}?lic={self.pk_license}'})
        try:
            with self.opener.open(req, timeout=20) as r:
                resp = json.loads(r.read().decode())
                credit_id = resp.get('idPostCeCredit')
                status = resp.get('status')
                print(f"[submit] ✅ Submitted! Credit ID: {credit_id}, Status: {status}")
                return resp
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"[submit] HTTP {e.code}: {body[:300]}")
            return None


def get_unsynced_ceus(db_path, user_id):
    """Get CEUs from Breathe DB that haven't been synced to CE Broker."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get CEUs where cebroker_synced=0 and have a sync_log entry with status != 'confirmed'
    rows = cur.execute(
        """SELECT id, title, provider, credits, completion_date, category,
                  certificate_path, cebroker_synced
           FROM ceus WHERE user_id = ? AND cebroker_synced = 0
           ORDER BY completion_date ASC""", (user_id,)).fetchall()

    ceus = []
    for row in rows:
        ceus.append({
            'id': row['id'],
            'title': row['title'],
            'provider': row['provider'],
            'hours': row['credits'],
            'completion_date': row['completion_date'],
            'category': row['category'],
            'certificate_path': row['certificate_path'],
            'cebroker_synced': row['cebroker_synced'],
        })

    conn.close()
    return ceus


def update_sync_log(db_path, user_id, ceu_id, status, credit_id=None, error_message=None):
    """Update the cebroker_sync_log and mark CEU as synced."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Update sync log
    existing = cur.execute(
        "SELECT id FROM cebroker_sync_log WHERE ceu_id = ? AND user_id = ?",
        (ceu_id, user_id)).fetchone()

    now = datetime.now().isoformat()
    if existing:
        cur.execute(
            """UPDATE cebroker_sync_log
               SET status = ?, error_message = ?, updated_at = ?,
                   submitted_at = ?, confirmed_at = ?
               WHERE ceu_id = ? AND user_id = ?""",
            (status, error_message, now,
             now if status in ('submitted', 'confirmed') else None,
             now if status == 'confirmed' else None,
             ceu_id, user_id))
    else:
        cur.execute(
            """INSERT INTO cebroker_sync_log
               (user_id, ceu_id, status, attempt_count, error_message, created_at, updated_at)
               VALUES (?, ?, ?, 1, ?, ?, ?)""",
            (user_id, ceu_id, status, error_message, now, now))

    # Mark CEU as synced if confirmed
    if status in ('submitted', 'confirmed'):
        cur.execute(
            "UPDATE ceus SET cebroker_synced = 1, cebroker_synced_at = ? WHERE id = ?",
            (now, ceu_id))

    conn.commit()
    conn.close()



def get_user_license_number(db_path, user_id):
    """Read the user's license number from the Breathe DB for CE Broker matching."""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        row = cur.execute(
            'SELECT license_number FROM licenses WHERE user_id = ? ORDER BY id DESC LIMIT 1',
            (user_id,)).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None

def sync_user_ceus(user_id=15, email=CEB_EMAIL, pk_license=PK_LICENSE, dry_run=False, otp_code=None, session_file=None):
    """Sync all unsynced CEUs for a user."""
    print(f"\n{'='*60}")
    print(f"CE Broker Sync — User ID: {user_id}")
    print(f"Email: {email} | License: {pk_license}")
    print(f"{'='*60}")

    # Get unsynced CEUs
    ceus = get_unsynced_ceus(BREATHE_DB, user_id)
    if not ceus:
        print("No unsynced CEUs found.")
        return

    # Filter out already-failed ones (Bunnell + Tunnel already submitted today)
    print(f"Found {len(ceus)} unsynced CEU(s):")
    for ceu in ceus:
        print(f"  #{ceu['id']} | {ceu['provider']} | {ceu['hours']}hr | {ceu['completion_date']} | {ceu['title']}")

    if dry_run:
        print("\n[DRY RUN] Would sync the above CEUs. Use --sync to actually submit.")
        return

    # Authenticate: prefer a saved session, then a manual OTP, then AgentMail (legacy).
    # If session_file is set and the session is dead without a manual OTP, print the
    # REAUTH_REQUIRED marker so callers (API) can prompt the user to reconnect.
    sync = CEBrokerSync(email=email, pk_license=pk_license)
    try:
        authed = False
        if session_file and os.path.exists(session_file):
            if sync.load_session(session_file):
                print("[auth] Using saved CE Broker session ✅")
                authed = True
            else:
                print("[auth] Saved session invalid or expired")
        if not authed:
            if session_file and not otp_code:
                print("REAUTH_REQUIRED")
                return
            sync.authenticate(otp_code=otp_code)
        if session_file:
            sync.save_session(session_file)
    except Exception as e:
        print(f"Authentication failed: {e}")
        return

    # Resolve the user's license dynamically from CE Broker (per-user, not hardcoded)
    user_license = get_user_license_number(BREATHE_DB, user_id)
    sync.resolve_license(license_number=user_license)

    # Get form config
    form_config = sync.get_form_config()
    print(f"\nForm config loaded: {len(form_config['subject_areas'])} subject areas, {len(form_config['questions'])} questions")

    # Submit each CEU
    results = []
    for ceu in ceus:
        print(f"\n--- Syncing CEU #{ceu['id']}: {ceu['provider']} ---")

        # Check if certificate exists
        cert_path = ceu['certificate_path']
        if cert_path and not os.path.exists(cert_path):
            # Try workspace copy
            alt_path = f"{WORKSPACE}/ceu-tracker/breathe-api/certificates/user_15/CRCE_Quiz_William_Sublett_08-04-2026.pdf"
            if os.path.exists(alt_path):
                cert_path = alt_path
            else:
                print(f"  Certificate not found: {cert_path} — submitting without attachment")
                cert_path = None

        # Build CEU data for submission
        ceu_data = {
            'course_name': ceu['title'],
            'provider': ceu['provider'],
            'approval': 'Approved by AARC (American Association for Respiratory Care)',
            'completion_date': ceu['completion_date'],
            'hours': ceu['hours'],
            'course_type': COURSE_TYPE,
            'delivery_method': DELIVERY_METHOD,
        }

        # Update sync log to pending
        update_sync_log(BREATHE_DB, user_id, ceu['id'], 'pending')

        # Submit
        result = sync.submit_ceu(ceu_data, form_config, cert_path)
        if result and result.get('idPostCeCredit'):
            credit_id = result['idPostCeCredit']
            status = result.get('status', 'APPLIED')
            # Update sync log to submitted
            update_sync_log(BREATHE_DB, user_id, ceu['id'], 'submitted', credit_id=credit_id)
            results.append({'ceu_id': ceu['id'], 'credit_id': credit_id, 'status': status})
            print(f"  ✅ CEU #{ceu['id']} synced! Credit ID: {credit_id}")
        else:
            update_sync_log(BREATHE_DB, user_id, ceu['id'], 'failed',
                           error_message='Submission returned no credit ID')
            results.append({'ceu_id': ceu['id'], 'credit_id': None, 'status': 'failed'})
            print(f"  ❌ CEU #{ceu['id']} failed")

        # Delay between submissions
        time.sleep(5)

    # Summary
    print(f"\n{'='*60}")
    print("Sync Summary")
    print(f"{'='*60}")
    synced = sum(1 for r in results if r['status'] != 'failed')
    failed = sum(1 for r in results if r['status'] == 'failed')
    print(f"Total: {len(results)} | Synced: {synced} | Failed: {failed}")
    for r in results:
        status_icon = "✅" if r['status'] != 'failed' else "❌"
        print(f"  {status_icon} CEU #{r['ceu_id']} → Credit ID: {r['credit_id']} ({r['status']})")


def show_status():
    """Show sync status for all users with CEUs."""
    conn = sqlite3.connect(BREATHE_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    users = cur.execute(
        """SELECT u.id, u.name, u.email, COUNT(c.id) as ceu_count,
              SUM(CASE WHEN c.cebroker_synced = 1 THEN 1 ELSE 0 END) as synced_count,
              SUM(CASE WHEN c.cebroker_synced = 0 THEN 1 ELSE 0 END) as unsynced_count
           FROM users u LEFT JOIN ceus c ON c.user_id = u.id
           GROUP BY u.id ORDER BY ceu_count DESC""").fetchall()

    print("\nCE Broker Sync Status")
    print("=" * 60)
    for u in users:
        print(f"User #{u['id']} | {u['name']} | {u['email']}")
        print(f"  CEUs: {u['ceu_count']} total | {u['synced_count']} synced | {u['unsynced_count']} unsynced")

    # Recent sync log entries
    log_entries = cur.execute(
        """SELECT l.id, l.user_id, l.ceu_id, l.status, l.error_message,
                  l.submitted_at, c.provider, c.title
           FROM cebroker_sync_log l
           LEFT JOIN ceus c ON c.id = l.ceu_id
           ORDER BY l.updated_at DESC LIMIT 10""").fetchall()

    if log_entries:
        print("\nRecent Sync Log:")
        for l in log_entries:
            print(f"  #{l['id']} | CEU #{l['ceu_id']} ({l['provider']}) | {l['status']} | {l['submitted_at'] or ''}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Breathe → CE Broker CEU sync")
    parser.add_argument('--sync', action='store_true', help='Sync unsynced CEUs')
    parser.add_argument('--test-auth', action='store_true', help='Test auth chain only')
    parser.add_argument('--status', action='store_true', help='Show sync status')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be synced without submitting')
    parser.add_argument('--user-id', type=int, default=15, help='Breathe user ID (default: 15)')
    parser.add_argument('--otp', type=str, default=None, help='Manual OTP code (skips AgentMail polling)')
    parser.add_argument('--session-file', type=str, default=None, help='Reuse/validate a saved session jar')
    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.test_auth:
        sync = CEBrokerSync()
        try:
            sync.authenticate()
            print("\nAuth test passed ✅")
            # Also test form config
            config = sync.get_form_config()
            print(f"Subject areas: {len(config['subject_areas'])}")
            print(f"Questions: {len(config['questions'])}")
        except Exception as e:
            print(f"\nAuth test failed ❌: {e}")
    elif args.sync or args.dry_run:
        sync_user_ceus(user_id=args.user_id, dry_run=args.dry_run, otp_code=args.otp, session_file=args.session_file)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()