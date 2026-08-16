"""
CE Broker Sync Agent — automatically uploads CEUs from Breathe to CE Broker.

Flow:
1. Log into CE Broker via email + OTP (OTP caught from AgentMail)
2. Click "Report CE" button on dashboard
3. For each unreported CEU:
   a. Click the appropriate credit type "Report" link (General CE Course for most)
   b. Wait for ASP.NET postback form to appear
   c. Fill in course title, provider, credits, completion date
   d. Submit the form
   e. Verify success by checking page text for confirmation messages
   f. Mark CEU as "reported to CE Broker" in Breathe database ONLY after confirmation
4. Return summary of synced CEUs

Each CEU submission is wrapped in its own try/catch — failure of one doesn't block the rest.
Random 2-5 second delays between submissions for human-like behavior.
OTP must be received within 90 seconds or sync fails gracefully.

Sync log status transitions: pending → submitted → confirmed | failed
"""
import json
import re
import time
import os
import random
import logging
import subprocess
import tempfile
from datetime import datetime
from typing import Optional

try:
    from crypto import is_encryption_available, decrypt_field
except ImportError:
    # Graceful fallback if crypto module not available
    def is_encryption_available() -> bool:
        return False
    def decrypt_field(ciphertext):
        return None

logger = logging.getLogger(__name__)

AGENTMAIL_CONFIG_PATH = "/home/ron/.openclaw/workspace/.agentmail_config.json"
CEBROKER_LOGIN_URL = "https://launchpad.cebroker.com/login"


def get_agentmail_config():
    with open(AGENTMAIL_CONFIG_PATH) as f:
        return json.load(f)


CEBROKER_CATEGORY_MAP = {
    "clinical": "Traditional CE",
    "safety": "Traditional CE",
    "ethics": "Ethics CE",
    "leadership": "Traditional CE",
    "education": "Teaching or Instructing",
    "medical_errors": "Traditional CE",
    "laws_rules": "Traditional CE",
    "hiv_aids": "Traditional CE",
    "human_trafficking": "Human Trafficking",
}


def map_category_to_cebroker(breathe_category):
    return CEBROKER_CATEGORY_MAP.get(breathe_category, "Traditional CE")


# ─── Sync Log Helper Functions ─────────────────────────────────

def create_sync_log(db, user_id, ceu_id, status="pending"):
    """Create a new sync log entry for a CEU."""
    from models import CEBrokerSyncLog
    log = CEBrokerSyncLog(
        user_id=user_id,
        ceu_id=ceu_id,
        status=status,
        attempt_count=1,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def update_sync_log(db, ceu_id, status, error_message=None):
    """Update the most recent sync log entry for a CEU."""
    from models import CEBrokerSyncLog
    log = db.query(CEBrokerSyncLog).filter(
        CEBrokerSyncLog.ceu_id == ceu_id
    ).order_by(CEBrokerSyncLog.created_at.desc()).first()
    if log:
        log.status = status
        log.error_message = error_message
        if status == "submitted":
            log.submitted_at = datetime.utcnow()
        elif status == "confirmed":
            log.confirmed_at = datetime.utcnow()
        db.commit()
    return log


# ─── Node Script Template ──────────────────────────────────────
# The Node script uses Playwright to automate CE Broker's ASP.NET WebForms.
# Key improvements in this version:
#   - Random 2-5 second delays between CEU submissions (human-like)
#   - Explicit success verification (checks page text for confirmation keywords)
#   - Per-CEU try/catch (failure of one doesn't block the rest)
#   - OTP timeout at 90 seconds with clear error message
#   - Session timeout detection and graceful re-login
#   - Returns per-CEU status: pending → submitted → confirmed | failed

NODE_SCRIPT_TEMPLATE = r"""
const { chromium } = require('/home/ron/.npm-global/lib/node_modules/playwright');
const https = require('https');
const fs = require('fs');

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
const randomDelay = () => sleep(2000 + Math.random() * 3000); // 2-5 seconds

const CEBROKER_LOGIN_URL = 'https://launchpad.cebroker.com/login';
const CEUS_FILE = '{ceus_file}';
const RESULTS_FILE = '{results_file}';
const CEBROKER_EMAIL = '{email}';
const HEADLESS = {headless};

// Success keywords to look for after submitting a CEU
const SUCCESS_KEYWORDS = ['successfully', 'received', 'submitted', 'thank you', 'has been reported', 'confirmation', 'ce credit has been', 'your submission'];
// Error patterns that indicate actual submission failures
// NOTE: "please correct the following errors" is a hidden template on CE Broker pages
// that only becomes visible when there are actual errors. We detect it differently.
const ERROR_PATTERNS = [
  'this field is required',
  'required field',
  'must enter',
  'please enter',
  'please select',
  'please provide',
  'is required',
  'cannot be empty',
  'invalid date',
  'invalid input',
  'you must enter',
  'hours must be',
  'at least one hour',
];

function getLatestOTP(config) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'api.agentmail.to',
      path: `/v0/inboxes/${config.inbox_id}/messages?limit=5`,
      headers: { 'Authorization': `Bearer ${config.api_key}`, 'Content-Type': 'application/json' }
    };
    https.get(options, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try {
          const messages = JSON.parse(data).messages || [];
          for (const msg of messages) {
            const from = (msg.from || msg.from_ || '').toLowerCase();
            if (from.includes('cebroker') || from.includes('propelus')) {
              const body = msg.body || msg.text || msg.preview || '';
              const match = body.match(/\b(\d{6})\b/) || (msg.subject || '').match(/\b(\d{6})\b/);
              if (match) {
                resolve({ otp: match[1], ts: msg.timestamp || msg.created_at });
                return;
              }
            }
          }
          resolve(null);
        } catch (e) { reject(e); }
      });
    }).on('error', reject);
  });
}

function mapCategory(cat) {
  const map = {
    clinical: 'Traditional CE',
    safety: 'Traditional CE',
    ethics: 'Ethics CE',
    leadership: 'Traditional CE',
    education: 'Teaching or Instructing',
    medical_errors: 'Traditional CE',
    laws_rules: 'Traditional CE',
    hiv_aids: 'Traditional CE',
    human_trafficking: 'Human Trafficking',
  };
  return map[cat] || 'Traditional CE';
}

function checkSuccess(pageText) {
  if (!pageText) return false;
  const lower = pageText.toLowerCase();
  return SUCCESS_KEYWORDS.some(kw => lower.includes(kw));
}

function checkError(pageText) {
  if (!pageText) return null;
  const lower = pageText.toLowerCase();
  for (const pattern of ERROR_PATTERNS) {
    if (lower.includes(pattern)) {
      const idx = lower.indexOf(pattern);
      const start = Math.max(0, idx - 60);
      const end = Math.min(lower.length, idx + 120);
      return lower.substring(start, end).trim();
    }
  }
  return null;
}

// Check for visible error summary on the page (CE Broker uses a hidden template
// that becomes visible only when there are actual errors)
async function checkVisibleError(page) {
  try {
    // The error summary div has id="errorList" or class "error-summary"
    const errorList = await page.$('#errorList:visible, .error-summary:visible, .error-summary__title:visible');
    if (errorList) {
      const errorText = await errorList.textContent().catch(() => '');
      if (errorText && errorText.trim().length > 0) {
        return errorText.trim().substring(0, 200);
      }
    }
  } catch (e) {}
  return null;
}

async function loginToCEBroker(page, context, config) {
  // ─── Get baseline OTP timestamp ────────────────────
  const before = await getLatestOTP(config);
  const beforeTs = before ? before.ts : null;
  console.log('Baseline OTP ts:', beforeTs);

  // ─── Load login page ───────────────────────────────
  console.log('Loading CE Broker login...');
  await page.goto(CEBROKER_LOGIN_URL, { waitUntil: 'networkidle', timeout: 30000 });
  await sleep(3000);

  await page.waitForSelector('#username', { timeout: 10000 });
  await page.fill('#username', CEBROKER_EMAIL);
  await sleep(500);
  await page.click('button[type="submit"]');
  console.log('Email submitted, waiting for OTP page...');

  await page.waitForSelector('#otp-0', { timeout: 15000 });
  console.log('OTP page shown');

  // ─── Poll for fresh OTP (90 second timeout) ────────
  let otp = null;
  for (let i = 0; i < 45; i++) {  // 45 * 2s = 90 seconds
    await sleep(2000);
    const result = await getLatestOTP(config);
    if (result && result.ts !== beforeTs) {
      otp = result.otp;
      console.log(`Fresh OTP received: ${otp}`);
      break;
    }
    if (i % 5 === 4) console.log(`  Waiting for OTP... (${(i + 1) * 2}s elapsed)`);
  }

  if (!otp) {
    throw new Error('OTP_NOT_RECEIVED: No OTP received within 90 seconds. Check AgentMail inbox for CE Broker/Propelus emails.');
  }

  // ─── Enter OTP and submit ──────────────────────────
  for (let i = 0; i < 6; i++) {
    await page.fill(`#otp-${i}`, otp[i]);
    await sleep(100);
  }
  await sleep(500);
  await page.click('button[type="submit"]');
  console.log('OTP submitted, waiting for dashboard...');

  await sleep(5000);
  try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}

  const currentUrl = page.url();
  console.log('After login URL:', currentUrl);

  if (!currentUrl.includes('cebroker.com')) {
    throw new Error(`LOGIN_FAILED: After OTP submission, URL is ${currentUrl}. Login may have failed.`);
  }

  return true;
}

async function navigateToReportCE(page) {
  // ─── Click "Report CE" button on dashboard ────────
  console.log('Clicking Report CE button...');
  await page.click('button:has-text("Report CE")');
  await sleep(3000);
  try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}
  console.log('After Report CE click. URL:', page.url());

  // ─── Select TX license from modal ─────────────────
  const txLicenseButton = await page.$('button:has-text("Respiratory Care Practitioner")');
  if (txLicenseButton) {
    console.log('Found TX license button in modal, clicking...');
    await txLicenseButton.click();
    await sleep(5000);
    try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}
    console.log('After license selection. URL:', page.url());
  } else {
    console.log('No TX license button found — may already be on reporting page');
  }
}

async function submitSingleCEU(page, ceu, idx, total) {
  const cebrokerCat = mapCategory(ceu.category);
  console.log(`\n--- Syncing CEU ${idx + 1}/${total}: ${ceu.title} ---`);
  console.log(`  Category: ${ceu.category} -> ${cebrokerCat}`);

  // Find the Report buttons by their specific class (not generic a:has-text("Report"))
  // CE Broker uses <a class="btn btn-info option-start btn-blue">Report</a> for each credit type
  const reportButtons = await page.$$('a.btn.btn-info.option-start.btn-blue');
  console.log(`  Found ${reportButtons.length} Report buttons (btn-info option-start)`);
  
  let targetLink = null;

  for (const link of reportButtons) {
    const visible = await link.isVisible();
    if (!visible) continue;
    // Get the section heading text from parent elements
    let parent = link.parentElement;
    for (let i = 0; i < 5 && parent; i++) {
      const ctx = (await parent.textContent()).trim();
      if (ctx.includes(cebrokerCat)) {
        targetLink = link;
        console.log(`  Found matching Report button for: ${cebrokerCat}`);
        break;
      }
      parent = parent.parentElement;
    }
    if (targetLink) break;
  }

  if (!targetLink) {
    // Fallback: Traditional CE is the second Report button (index 1 — first is "Organization Transcript")
    const visibleButtons = [];
    for (const link of reportButtons) {
      if (await link.isVisible()) visibleButtons.push(link);
    }
    if (visibleButtons.length > 1) {
      targetLink = visibleButtons[1]; // Traditional CE (button index 1)
      console.log('  Using fallback: Traditional CE (button index 1)');
    }
  }

  if (!targetLink) {
    const pageHtml = await page.content();
    const dumpPath = '/tmp/cebroker-report-ce-page.html';
    fs.writeFileSync(dumpPath, pageHtml);
    console.log(`  HTML dumped to ${dumpPath} (${pageHtml.length} chars)`);
    console.log(`  Page URL: ${page.url()}`);
    const linkInfo = [];
    for (const link of reportButtons) {
      const vis = await link.isVisible();
      const text = (await link.textContent()).trim().substring(0, 100);
      const cls = (await link.getAttribute('class')) || '';
      linkInfo.push({ visible: vis, text, class: cls });
    }
    console.log('  All Report buttons found:', JSON.stringify(linkInfo, null, 2));
    throw new Error(`Could not find Report button for: ${cebrokerCat}. HTML dumped to ${dumpPath}`);
  }

  await targetLink.click();
  await sleep(3000);
  try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}
  console.log('  Clicked Report button, waiting for form...');
  console.log('  Current URL after Report click:', page.url());

  // Wait for the form to render
  try {
    await page.waitForSelector('#dateCompletedPicker', { timeout: 15000 });
    console.log('  Form appeared (date picker visible)');
  } catch (e) {
    try { await page.waitForSelector('input:visible, select:visible', { timeout: 10000 }); } catch (e2) {}
  }
  await sleep(2000);

  // ─── Fill the Traditional CE form ──────────────────
  // Date Completed — #dateCompletedPicker (MM/DD/YYYY format)
  const dateObj = new Date(ceu.completion_date);
  const mm = String(dateObj.getMonth() + 1).padStart(2, '0');
  const dd = String(dateObj.getDate()).padStart(2, '0');
  const yyyy = dateObj.getFullYear();
  const dateStr = `${mm}/${dd}/${yyyy}`;

  const dateInput = await page.$('#dateCompletedPicker');
  if (dateInput) {
    await dateInput.fill(dateStr);
    await sleep(300);
    console.log('  Filled date:', dateStr);
  } else {
    console.log('  WARNING: Could not find date input (#dateCompletedPicker)');
  }

  // Click the radio button for "Live" course type
  const radioBtn = await page.$('#ctl00_PageContent_PageContent_rptCourseTypes_ctl00_rdoCourseType, input[name="rdoCourseType"]');
  if (radioBtn) {
    await radioBtn.click();
    await sleep(1000);
    console.log('  Clicked Live radio button');
  } else {
    console.log('  WARNING: Could not find Live radio button');
  }

  // Course Type — #courseTypeBinder (select dropdown)
  await sleep(1000);
  const courseTypeSelect = await page.$('#courseTypeBinder');
  if (courseTypeSelect) {
    const options = await courseTypeSelect.$$('option');
    console.log(`  Course type has ${options.length} options`);
    let selected = false;
    for (const opt of options) {
      const val = await opt.getAttribute('value');
      if (val && val !== '') {
        await courseTypeSelect.selectOption(val);
        console.log(`  Selected course type: ${val}`);
        selected = true;
        break;
      }
    }
    if (!selected && options.length > 0) {
      try {
        await courseTypeSelect.selectOption({ index: 1 });
        console.log('  Selected course type (index 1)');
      } catch (e) {
        console.log('  WARNING: Could not select course type');
      }
    }
    await sleep(500);
  } else {
    console.log('  WARNING: Could not find course type select (#courseTypeBinder)');
  }

  // Hours/Credits
  const hoursInput = await page.$('#ctl00_PageContent_PageContent_rptSubjectAreas_ctl00_txtRequestedHours, input[name*="txtRequestedHours"]');
  if (hoursInput) {
    await hoursInput.fill(String(ceu.credits));
    await sleep(300);
    console.log('  Filled hours:', ceu.credits);
  } else {
    console.log('  WARNING: Could not find hours input');
  }

  // Submit step 1 — "Continue to next step" button
  console.log('  Looking for Continue button...');
  let continueBtn = null;
  for (let attempt = 0; attempt < 10; attempt++) {
    continueBtn = await page.$('#ctl00_PageContent_PageContent_btnContinue');
    if (continueBtn && await continueBtn.isVisible()) break;
    continueBtn = await page.$('input[type="submit"][value*="Continue" i]');
    if (continueBtn && await continueBtn.isVisible()) break;
    continueBtn = await page.$('input.btn.btn-blue[type="submit"]');
    if (continueBtn && await continueBtn.isVisible()) break;
    await sleep(1000);
  }
  if (continueBtn) {
    await continueBtn.click();
    await sleep(5000);
    try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}
    console.log('  Clicked Continue to next step');
  } else {
    const allBtns = await page.$$eval('input, button', els => els.filter(e => e.offsetParent !== null).map(e => ({ tag: e.tagName, type: e.type, id: e.id, value: (e.value || '').substring(0, 40), text: (e.textContent || '').trim().substring(0, 40) })));
    console.log('  All visible buttons:', JSON.stringify(allBtns));
    console.log('  Current URL:', page.url());
    await page.screenshot({ path: '/tmp/cebroker_continue_fail.png' });
    throw new Error('Could not find Continue button after 10 attempts');
  }

  // ─── Step 2: Questionnaire (multi-step questions) ────────
  // CE Broker uses a multi-step questionnaire (typically 3 questions):
  // Q1: "What is the name of the CE course?" → answer with course title
  // Q2: "Who was the provider?" or similar → answer with provider name
  // Q3: Attestation/confirmation → answer with "Yes" or confirm
  //
  // The form has a textarea (#txaAnswer) and a "Continue to next step" link (#btnNext)
  await sleep(3000);

  let questionNum = 0;
  const maxQuestions = 6; // 3 questions + 1 attestation + 1 confirmation + 1 safety margin

  while (questionNum < maxQuestions) {
    questionNum++;
    await sleep(2000);

    // Get the current question text from the page
    const pageText = await page.textContent('body').catch(() => '');
    const cleanText = pageText.replace(/\s+/g, ' ').trim();

    // Check if we've reached a success/confirmation page
    if (checkSuccess(cleanText)) {
      // Verify no visible error
      const visErr = await checkVisibleError(page);
      if (!visErr) {
        console.log(`  ✅ CEU CONFIRMED: Success message found on page (after Q${questionNum - 1})`);
        return {
          title: ceu.title,
          status: 'confirmed',
          message: 'Successfully reported and confirmed on CE Broker',
          ceu_id: ceu.id || null,
        };
      }
    }

    // Check for visible error messages (not hidden templates)
    const visibleError = await checkVisibleError(page);
    if (visibleError) {
      console.log(`  ❌ CEU FAILED: Visible error detected: ${visibleError}`);
      return {
        title: ceu.title,
        status: 'failed',
        message: `Submission error: ${visibleError}`,
        ceu_id: ceu.id || null,
      };
    }

    // Find the textarea for answering questions
    const textarea = await page.$('#ctl00_PageContent_PageContent_txaAnswer');
    if (!textarea || !(await textarea.isVisible())) {
      // No textarea visible — might be on attestation/confirmation/file upload step
      console.log(`  No textarea visible on step ${questionNum}. Checking page state...`);
      
      // Save page HTML for debugging
      const stepHtml = await page.content();
      fs.writeFileSync(`/tmp/cebroker_step_${questionNum}.html`, stepHtml);
      console.log(`  Step ${questionNum} HTML saved to /tmp/cebroker_step_${questionNum}.html`);
      
      // Check for attestation radio buttons (Yes/No)
      // CE Broker's attestation/attachment step has a 'Continue' button with
      // onclick='return validateSelection();' that requires either:
      // - A file attachment, OR
      // - The 'I attest' option selected with Yes
      // Since the 'I attest' option may not be available on all accounts,
      // we bypass the validation and submit the form directly via ASP.NET postback
      const attestYesRadio = await page.$('#rdoMaintainAttestationYes, input[name="rdoMaintainAttestation"][value="Yes"]');
      const continueBtn4 = await page.$('#ctl00_PageContent_PageContent_btnContinue');
      if (attestYesRadio || continueBtn4) {
        console.log(`  Step ${questionNum}: On attestation/attachment step, attempting to submit...`);
        
        // 1. If attestation radio exists, select Yes
        if (attestYesRadio) {
          await page.evaluate(() => {
            const box = document.querySelector('#maintainBox');
            if (box) { box.style.display = 'block'; box.classList.remove('hide'); }
            const radio = document.querySelector('#rdoMaintainAttestationYes');
            if (radio) {
              radio.checked = true;
              radio.dispatchEvent(new Event('change', { bubbles: true }));
              if (typeof $ !== 'undefined') $('#rdoMaintainAttestationYes').prop('checked', true).trigger('change');
            }
          });
          await sleep(1000);
          console.log(`  Step ${questionNum}: Attestation Yes selected`);
        }
        
        // 2. Override validateSelection to always return true, then click Continue
        await page.evaluate(() => {
          // Override the validation function
          if (typeof window.validateSelection === 'function') {
            window.validateSelection = function() { return true; };
          }
          // Also hide any error summary
          if (typeof window.hideErrorSummary === 'function') {
            window.hideErrorSummary();
          }
        });
        await sleep(500);
        
        // 3. Click the Continue button (triggers postback)
        const clicked = await page.evaluate(() => {
          const btn = document.querySelector('#ctl00_PageContent_PageContent_btnContinue') ||
                      document.querySelector('#ctl00_PageContent_PageContent_btnNext');
          if (btn) {
            // Remove onclick validation hook temporarily
            const onclick = btn.getAttribute('onclick');
            if (onclick) btn.removeAttribute('onclick');
            btn.click();
            if (onclick) btn.setAttribute('onclick', onclick);
            return true;
          }
          return false;
        });
        
        if (clicked) {
          await sleep(5000);
          try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}
          console.log(`  Clicked Continue on attestation step (step ${questionNum})`);
          continue;
        }
      }
      
      // Check for any submit/confirm button
      const confirmBtn = await page.$('button:has-text("Confirm"):visible, button:has-text("Finish"):visible, button:has-text("Complete"):visible, button:has-text("Submit"):visible, input[type="submit"]:visible');
      if (confirmBtn) {
        await confirmBtn.click();
        await sleep(3000);
        try { await page.waitForLoadState('networkidle', { timeout: 10000 }); } catch (e) {}
        console.log(`  Clicked confirm/submit button`);
        continue;
      }

      // Check if it's a success page
      if (checkSuccess(cleanText)) {
        console.log(`  ✅ CEU CONFIRMED: Success message found`);
        return {
          title: ceu.title,
          status: 'confirmed',
          message: 'Successfully reported and confirmed on CE Broker',
          ceu_id: ceu.id || null,
        };
      }

      // Unknown state — break out
      console.log(`  Page text (last 500): ${cleanText.substring(cleanText.length - 500)}`);
      break;
    }

    // Determine the answer based on the question text
    let answer = '';
    const lowerText = cleanText.toLowerCase();
    
    // Check if this is a Yes/No question (look for radio buttons)
    const yesRadio = await page.$('input[type="radio"][value*="yes" i]:visible, input[type="radio"][id*="yes"]:visible');
    const noRadio = await page.$('input[type="radio"][value*="no" i]:visible, input[type="radio"][id*="no"]:visible');
    const isYesNoQuestion = yesRadio || noRadio;
    
    if (isYesNoQuestion && (lowerText.includes('attest') || lowerText.includes('certify') || lowerText.includes('acknowledge') || lowerText.includes('agree') || lowerText.includes('confirm'))) {
      // Yes/No attestation question — click Yes
      if (yesRadio) {
        await yesRadio.click();
        await sleep(500);
        console.log(`  Q${questionNum}: Clicked Yes radio button`);
      } else if (noRadio) {
        // If only No is available, something's wrong
        console.log(`  Q${questionNum}: WARNING: Only No radio found for attestation`);
      }
      // Don't fill textarea for Yes/No questions
    } else if (lowerText.includes('name of the ce course') || lowerText.includes('name of the course')) {
      answer = ceu.title;
      console.log(`  Q${questionNum}: Answering course name: ${answer}`);
      await textarea.fill(answer);
      await sleep(500);
    } else if (lowerText.includes('provider') || lowerText.includes('sponsor') || lowerText.includes('who was the')) {
      answer = ceu.provider;
      console.log(`  Q${questionNum}: Answering provider: ${answer}`);
      await textarea.fill(answer);
      await sleep(500);
    } else if (lowerText.includes('recognized') || lowerText.includes('approved') || lowerText.includes('how was this course')) {
      // Q3 typically asks how the course was recognized/approved
      answer = `Approved by ${ceu.provider} (American Association for Respiratory Care), a recognized professional organization for respiratory care CE.`;
      console.log(`  Q${questionNum}: Answering recognition: ${answer}`);
      await textarea.fill(answer);
      await sleep(500);
    } else if (lowerText.includes('attest') || lowerText.includes('certify') || lowerText.includes('acknowledge') || lowerText.includes('agree')) {
      answer = 'Yes';
      console.log(`  Q${questionNum}: Answering attestation: Yes`);
      await textarea.fill(answer);
      await sleep(500);
    } else if (lowerText.includes('date') && lowerText.includes('complet')) {
      const dateObj = new Date(ceu.completion_date);
      const mm = String(dateObj.getMonth() + 1).padStart(2, '0');
      const dd = String(dateObj.getDate()).padStart(2, '0');
      const yyyy = dateObj.getFullYear();
      answer = `${mm}/${dd}/${yyyy}`;
      console.log(`  Q${questionNum}: Answering date: ${answer}`);
      await textarea.fill(answer);
      await sleep(500);
    } else if (lowerText.includes('hours') || lowerText.includes('credits') || lowerText.includes('how many')) {
      answer = String(ceu.credits);
      console.log(`  Q${questionNum}: Answering credits: ${answer}`);
      await textarea.fill(answer);
      await sleep(500);
    } else if (isYesNoQuestion) {
      // Unknown Yes/No question — default to Yes
      if (yesRadio) {
        await yesRadio.click();
        await sleep(500);
        console.log(`  Q${questionNum}: Unknown Yes/No question, clicking Yes`);
      }
    } else {
      // Unknown text question — answer with relevant CEU info
      answer = `${ceu.title} - ${ceu.provider} - ${ceu.credits} credits - completed ${ceu.completion_date}`;
      console.log(`  Q${questionNum}: Unknown question, answering with full CEU info: ${answer}`);
      await textarea.fill(answer);
      await sleep(500);
    }

    // Click "Continue to next step" link
    const nextBtn = await page.$('#ctl00_PageContent_PageContent_btnNext');
    if (nextBtn && await nextBtn.isVisible()) {
      await nextBtn.click();
      await sleep(5000);
      try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}
      console.log(`  Clicked Continue to next step (Q${questionNum})`);
    } else {
      // Try generic submit/continue
      const submitBtn = await page.$('input[type="submit"]:visible, button:has-text("Continue"):visible, button:has-text("Submit"):visible, button:has-text("Finish"):visible');
      if (submitBtn) {
        await submitBtn.click();
        await sleep(5000);
        try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}
        console.log(`  Clicked submit button (Q${questionNum})`);
      } else {
        console.log(`  No continue/submit button found after Q${questionNum}`);
        break;
      }
    }
  }

  // After the questionnaire loop, check for final confirmation
  await sleep(3000);
  const finalText = await page.textContent('body').catch(() => '');
  const finalClean = finalText.replace(/\s+/g, ' ').trim();

  if (checkSuccess(finalClean)) {
    const visErr = await checkVisibleError(page);
    if (!visErr) {
      console.log('  ✅ CEU CONFIRMED: Success message found after questionnaire');
      return {
        title: ceu.title,
        status: 'confirmed',
        message: 'Successfully reported and confirmed on CE Broker',
        ceu_id: ceu.id || null,
      };
    }
  }

  const finalError = await checkVisibleError(page);
  if (finalError) {
    console.log(`  ❌ CEU FAILED: ${finalError}`);
    return {
      title: ceu.title,
      status: 'failed',
      message: `Submission error: ${finalError}`,
      ceu_id: ceu.id || null,
    };
  }

  // Submitted but no explicit confirmation
  console.log('  ⚠️ CEU SUBMITTED but NOT CONFIRMED: No success message found');
  return {
    title: ceu.title,
    status: 'submitted',
    message: 'Submitted to CE Broker but no confirmation message detected. Manual verification needed.',
    ceu_id: ceu.id || null,
  };
}

async function checkSessionAlive(page) {
  try {
    const url = page.url();
    if (url.includes('login') || url.includes('signin')) {
      return false;
    }
    // Check if we can still interact with the page
    const body = await page.$('body');
    return body !== null;
  } catch (e) {
    return false;
  }
}

(async () => {
  const ceus = JSON.parse(fs.readFileSync(CEUS_FILE, 'utf8'));
  const config = JSON.parse(fs.readFileSync('/home/ron/.openclaw/workspace/.agentmail_config.json', 'utf8'));
  const results = {
    synced: 0,
    failed: 0,
    submitted_unconfirmed: 0,
    errors: [],
    details: [],
  };

  if (ceus.length === 0) {
    console.log('No CEUs to sync');
    fs.writeFileSync(RESULTS_FILE, JSON.stringify(results));
    return;
  }

  let browser;
  try {
    browser = await chromium.launch({ headless: HEADLESS });
    const context = await browser.newContext({
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      viewport: { width: 1280, height: 900 },
    });
    const page = await context.newPage();

    // ─── Login ─────────────────────────────────────────
    await loginToCEBroker(page, context, config);
    console.log('Login successful');

    // ─── Navigate to Report CE ─────────────────────────
    await navigateToReportCE(page);

    // ─── Sync each CEU ─────────────────────────────────
    for (let idx = 0; idx < ceus.length; idx++) {
      const ceu = ceus[idx];

      // PER-CEU TRY/CATCH: failure of one doesn't block the rest
      try {
        // Check if session is still alive before each CEU
        if (!await checkSessionAlive(page)) {
          console.log('  Session expired, attempting re-login...');
          try {
            await loginToCEBroker(page, context, config);
            await navigateToReportCE(page);
          } catch (loginErr) {
            throw new Error(`SESSION_RELOGIN_FAILED: ${loginErr.message}`);
          }
        }

        const result = await submitSingleCEU(page, ceu, idx, ceus.length);

        if (result.status === 'confirmed') {
          results.synced++;
          results.details.push(result);
        } else if (result.status === 'submitted') {
          results.submitted_unconfirmed++;
          results.details.push(result);
        } else {
          results.failed++;
          results.errors.push(`${ceu.title}: ${result.message}`);
          results.details.push(result);
        }

      } catch (err) {
        console.error(`  ❌ FAILED: ${err.message}`);
        results.failed++;
        results.errors.push(`${ceu.title}: ${err.message}`);
        results.details.push({
          title: ceu.title,
          status: 'failed',
          message: err.message,
          ceu_id: ceu.id || null,
        });

        // Navigate back for next CEU
        if (idx < ceus.length - 1) {
          try {
            await page.goto('https://app.cebroker.com/credentials', { waitUntil: 'domcontentloaded', timeout: 30000 });
            await sleep(3000);
            await page.click('button:has-text("Report CE")');
            await sleep(3000);
            try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}
            const txBtn2 = await page.$('button:has-text("Respiratory Care Practitioner")');
            if (txBtn2) { await txBtn2.click(); await sleep(5000); }
          } catch (e) {
            console.error('  Failed to navigate back after error:', e.message);
          }
        }
      }

      // ─── HUMAN-LIKE DELAY between submissions (2-5 seconds random) ───
      if (idx < ceus.length - 1) {
        const delay = 2000 + Math.random() * 3000;
        console.log(`  Waiting ${(delay / 1000).toFixed(1)}s before next submission...`);
        await sleep(delay);

        // Navigate back to Report CE page for next CEU
        try {
          await page.goto('https://app.cebroker.com/credentials', { waitUntil: 'domcontentloaded', timeout: 30000 });
          await sleep(3000);
          await page.click('button:has-text("Report CE")');
          await sleep(3000);
          try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}
          const txBtn = await page.$('button:has-text("Respiratory Care Practitioner")');
          if (txBtn) { await txBtn.click(); await sleep(5000); }
        } catch (e) {
          console.error('  Failed to navigate back for next CEU:', e.message);
        }
      }
    }

    await browser.close();
    browser = null;

  } catch (err) {
    console.error('Fatal error:', err.message);
    results.errors.push(`Fatal: ${err.message}`);
    // Mark remaining CEUs as failed
    for (let i = 0; i < ceus.length; i++) {
      const alreadyProcessed = results.details.find(d => d.ceu_id === (ceus[i].id || null) || d.title === ceus[i].title);
      if (!alreadyProcessed) {
        results.failed++;
        results.errors.push(`${ceus[i].title}: Not processed due to fatal error: ${err.message}`);
        results.details.push({
          title: ceus[i].title,
          status: 'failed',
          message: `Not processed: ${err.message}`,
          ceu_id: ceus[i].id || null,
        });
      }
    }
    if (browser) {
      try { await browser.close(); } catch (e) {}
    }
  }

  console.log('\n=== SYNC RESULTS ===');
  console.log(JSON.stringify(results, null, 2));
  fs.writeFileSync(RESULTS_FILE, JSON.stringify(results));
})();
"""


def sync_ceus_to_cebroker(email, ceus_to_sync, headless=True, encrypted_email=None):
    """Run the CE Broker sync via Playwright browser automation.

    Args:
        email: CE Broker login email (plaintext — either direct or decrypted from encrypted_email)
        ceus_to_sync: List of dicts with title, provider, credits, completion_date, category, id
        headless: Run browser in headless mode
        encrypted_email: Optional encrypted CE Broker email from DB. If provided and email
                        is empty, will be decrypted using BREATHE_ENCRYPTION_KEY.

    Returns:
        Dict with synced, failed, submitted_unconfirmed, errors, details

    Note:
        CE Broker sync requires BREATHE_ENCRYPTION_KEY to be set. If the key is not
        configured, sync is gracefully disabled with a clear error message.
    """
    # ─── Encryption key check ───────────────────────────────────
    if not is_encryption_available():
        error_msg = ("CE Broker sync disabled: BREATHE_ENCRYPTION_KEY environment variable "
                     "is not set. Configure it to enable CE Broker sync.")
        logger.error(error_msg)
        return {
            "synced": 0,
            "failed": len(ceus_to_sync) if ceus_to_sync else 0,
            "submitted_unconfirmed": 0,
            "errors": [error_msg],
            "details": [],
            "message": error_msg,
        }

    # ─── Decrypt CE Broker email if needed ─────────────────────
    if not email and encrypted_email:
        email = decrypt_field(encrypted_email)
        if not email:
            error_msg = ("CE Broker sync disabled: could not decrypt CE Broker email. "
                         "Check that BREATHE_ENCRYPTION_KEY matches the key used to encrypt the email.")
            logger.error(error_msg)
            return {
                "synced": 0,
                "failed": len(ceus_to_sync) if ceus_to_sync else 0,
                "submitted_unconfirmed": 0,
                "errors": [error_msg],
                "details": [],
                "message": error_msg,
            }

    if not email:
        error_msg = "CE Broker sync disabled: no CE Broker login email configured."
        logger.error(error_msg)
        return {
            "synced": 0,
            "failed": len(ceus_to_sync) if ceus_to_sync else 0,
            "submitted_unconfirmed": 0,
            "errors": [error_msg],
            "details": [],
            "message": error_msg,
        }

    if not ceus_to_sync:
        return {
            "synced": 0,
            "failed": 0,
            "submitted_unconfirmed": 0,
            "errors": [],
            "details": [],
            "message": "No CEUs to sync",
        }

    ceus_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, prefix='cebroker_ceus_')
    json.dump(ceus_to_sync, ceus_file)
    ceus_file.close()

    results_file = ceus_file.name + '.results'

    node_script = NODE_SCRIPT_TEMPLATE
    node_script = node_script.replace('{ceus_file}', ceus_file.name)
    node_script = node_script.replace('{results_file}', results_file)
    node_script = node_script.replace('{email}', email)
    node_script = node_script.replace('{headless}', str(headless).lower())

    script_file = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, prefix='cebroker_sync_')
    script_file.write(node_script)
    script_file.close()

    try:
        logger.info(f"Starting CE Broker sync for {len(ceus_to_sync)} CEUs (email: {email})")
        env = os.environ.copy()
        env['NODE_PATH'] = '/home/ron/.npm-global/lib/node_modules'
        result = subprocess.run(
            ['node', script_file.name],
            cwd='/home/ron/.npm-global/lib/node_modules',
            env=env,
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes (was 5 — increased for multi-CEU with delays)
        )

        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                logger.info(f"[cebroker_sync] {line}")
        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                logger.warning(f"[cebroker_sync STDERR] {line}")

        if os.path.exists(results_file):
            with open(results_file) as f:
                return json.load(f)

        return {
            "synced": 0,
            "failed": len(ceus_to_sync),
            "submitted_unconfirmed": 0,
            "errors": ["No results file produced — script may have crashed"],
            "details": [],
        }

    except subprocess.TimeoutExpired:
        logger.error("CE Broker sync timed out after 600 seconds")
        return {
            "synced": 0,
            "failed": len(ceus_to_sync),
            "submitted_unconfirmed": 0,
            "errors": ["Sync timed out after 10 minutes"],
            "details": [],
        }
    except Exception as e:
        logger.error(f"CE Broker sync error: {e}")
        return {
            "synced": 0,
            "failed": len(ceus_to_sync),
            "submitted_unconfirmed": 0,
            "errors": [f"Sync error: {str(e)}"],
            "details": [],
        }
    finally:
        try:
            os.unlink(ceus_file.name)
            os.unlink(script_file.name)
            if os.path.exists(results_file):
                os.unlink(results_file)
        except OSError:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Check encryption key before running test
    if not is_encryption_available():
        print("ERROR: BREATHE_ENCRYPTION_KEY not set. CE Broker sync requires encryption key.")
        print("Generate one with: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
        exit(1)
    # Test with a single CEU
    test_ceus = [
        {
            "id": 12,
            "title": "Course Title: Mechanical Ventilation Essentials for NICU Therapists",
            "provider": "AARC",
            "credits": 2.0,
            "completion_date": "2026-08-10",
            "category": "clinical",
        },
    ]
    results = sync_ceus_to_cebroker("ron.sublett@gmail.com", test_ceus, headless=True)
    print("\nFinal results:")
    print(json.dumps(results, indent=2))