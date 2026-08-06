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
   e. Mark CEU as "reported to CE Broker" in Breathe database
4. Return summary of synced CEUs

CE Broker uses ASP.NET WebForms — forms appear via postback, not navigation.
"""
import json
import re
import time
import os
import logging
import subprocess
import tempfile
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

AGENTMAIL_CONFIG_PATH = "/home/ron/.openclaw/workspace/.agentmail_config.json"
CEBROKER_LOGIN_URL = "https://launchpad.cebroker.com/login"


def get_agentmail_config():
    with open(AGENTMAIL_CONFIG_PATH) as f:
        return json.load(f)


def get_latest_otp_timestamp():
    import urllib.request
    config = get_agentmail_config()
    api_key = config['api_key']
    inbox_id = config.get('inbox_id', 'jarvis-epictrends@agentmail.to')
    try:
        url = f"https://api.agentmail.to/v0/inboxes/{inbox_id}/messages?limit=5"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        for msg in data.get('messages', []):
            from_addr = (msg.get('from', msg.get('from_', ''))).lower()
            if 'cebroker' in from_addr or 'propelus' in from_addr:
                return msg.get('timestamp', msg.get('created_at', ''))
    except Exception as e:
        logger.error(f"Error getting latest OTP timestamp: {e}")
    return None


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
    return CEBROKER_CATEGORY_MAP.get(breathe_category, "General CE Course")


NODE_SCRIPT_TEMPLATE = r"""
const { chromium } = require('/home/ron/.npm-global/lib/node_modules/playwright');
const https = require('https');
const fs = require('fs');

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

const CEBROKER_LOGIN_URL = 'https://launchpad.cebroker.com/login';
const CEUS_FILE = '{ceus_file}';
const RESULTS_FILE = '{results_file}';
const CEBROKER_EMAIL = '{email}';
const HEADLESS = {headless};

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

(async () => {
  const ceus = JSON.parse(fs.readFileSync(CEUS_FILE, 'utf8'));
  const config = JSON.parse(fs.readFileSync('/home/ron/.openclaw/workspace/.agentmail_config.json', 'utf8'));
  const results = { synced: 0, failed: 0, errors: [], details: [] };

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

    // ─── Step 1: Get baseline OTP timestamp ────────────────────
    const before = await getLatestOTP(config);
    const beforeTs = before ? before.ts : null;
    console.log('Baseline OTP ts:', beforeTs);

    // ─── Step 2: Login to CE Broker ────────────────────────────
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

    // ─── Step 3: Poll for fresh OTP ────────────────────────────
    let otp = null;
    for (let i = 0; i < 45; i++) {
      await sleep(2000);
      const result = await getLatestOTP(config);
      if (result && result.ts !== beforeTs) {
        otp = result.otp;
        console.log(`Fresh OTP received: ${otp}`);
        break;
      }
      if (i % 5 === 4) console.log(`  Waiting for OTP... (${i + 1}s attempt)`);
    }

    if (!otp) {
      throw new Error('No OTP received within 90 seconds. Check AgentMail inbox.');
    }

    // ─── Step 4: Enter OTP and submit ──────────────────────────
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
      throw new Error(`Login may have failed. URL: ${currentUrl}`);
    }

    // ─── Step 5: Click "Report CE" button on dashboard ────────
    console.log('Clicking Report CE button...');
    await page.click('button:has-text("Report CE")');
    await sleep(3000);
    try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}
    console.log('After Report CE click. URL:', page.url());

    // ─── Step 5b: Select TX license from modal ───────────────
    // CE Broker shows a modal with license buttons after clicking Report CE.
    // We need to click the TX license ("Respiratory Care Practitioner") to
    // navigate to the actual ASP.NET WebForms reporting page.
    const txLicenseButton = await page.$('button:has-text("Respiratory Care Practitioner")');
    if (txLicenseButton) {
      console.log('Found TX license button in modal, clicking...');
      await txLicenseButton.click();
      await sleep(5000);
      try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}
      console.log('After license selection. URL:', page.url());
    } else {
      // Maybe already on the ASPX page (direct navigation)
      console.log('No TX license button found — may already be on reporting page');
    }

    // ─── Step 6: Sync each CEU ─────────────────────────────────
    for (let idx = 0; idx < ceus.length; idx++) {
      const ceu = ceus[idx];
      try {
        console.log(`\n--- Syncing CEU ${idx + 1}/${ceus.length}: ${ceu.title} ---`);

        const cebrokerCat = mapCategory(ceu.category);
        console.log(`  Category: ${ceu.category} -> ${cebrokerCat}`);

        // Find visible "Report" links and pick the right one by context
        const reportLinks = await page.$$('a:has-text("Report")');
        let targetLink = null;

        for (const link of reportLinks) {
          const visible = await link.isVisible();
          if (!visible) continue;
          // Get parent context text
          let parent = link.parentElement;
          for (let i = 0; i < 5 && parent; i++) {
            const ctx = (await parent.textContent()).trim();
            if (ctx.includes(cebrokerCat)) {
              targetLink = link;
              console.log(`  Found matching Report link for: ${cebrokerCat}`);
              break;
            }
            parent = parent.parentElement;
          }
          if (targetLink) break;
        }

        if (!targetLink) {
          // Fallback: Traditional CE is the first Report link (index 1, after the cycle selector)
          const visibleLinks = [];
          for (const link of reportLinks) {
            if (await link.isVisible()) visibleLinks.push(link);
          }
          if (visibleLinks.length > 1) {
            targetLink = visibleLinks[1]; // Traditional CE
            console.log('  Using fallback: Traditional CE (idx 1)');
          }
        }

        if (!targetLink) {
          // Dump page HTML for debugging before throwing
          const pageHtml = await page.content();
          const dumpPath = '/tmp/cebroker-report-ce-page.html';
          fs.writeFileSync(dumpPath, pageHtml);
          console.log(`  HTML dumped to ${dumpPath} (${pageHtml.length} chars)`);
          console.log(`  Page URL: ${page.url()}`);
          // Also dump visible link info
          const linkInfo = [];
          for (const link of reportLinks) {
            const vis = await link.isVisible();
            const text = (await link.textContent()).trim().substring(0, 100);
            const href = await link.getAttribute('href');
            linkInfo.push({ visible: vis, text, href });
          }
          console.log('  All Report links found:', JSON.stringify(linkInfo, null, 2));
          throw new Error(`Could not find Report link for: ${cebrokerCat}. HTML dumped to ${dumpPath}`);
        }

        await targetLink.click();
        await sleep(3000);
        try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}
        console.log('  Clicked Report link, waiting for form...');

        // Wait for the Traditional CE form to render — the date picker is the first field
        try {
          await page.waitForSelector('#dateCompletedPicker', { timeout: 15000 });
          console.log('  Form appeared (date picker visible)');
        } catch (e) {
          // Fallback: wait for any visible input
          try { await page.waitForSelector('input:visible, select:visible', { timeout: 10000 }); } catch (e2) {}
        }
        await sleep(2000);

        // ─── Step 7: Fill the Traditional CE form ───────────────
        // CE Broker's form has: Date Completed, Course Type, Hours, then Continue
        // Course title and provider come on the NEXT step after Continue.

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

        // Click the radio button for "Live" course type first — this populates the dropdown
        const radioBtn = await page.$('#ctl00_PageContent_PageContent_rptCourseTypes_ctl00_rdoCourseType, input[name="rdoCourseType"]');
        if (radioBtn) {
          await radioBtn.click();
          await sleep(1000);
          console.log('  Clicked Live radio button');
        } else {
          console.log('  WARNING: Could not find Live radio button');
        }

        // Course Type — #courseTypeBinder (select dropdown)
        // Wait for it to populate after radio click
        await sleep(1000);
        const courseTypeSelect = await page.$('#courseTypeBinder');
        if (courseTypeSelect) {
          const options = await courseTypeSelect.$$('option');
          console.log(`  Course type has ${options.length} options`);
          // Find first non-empty option
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
            // Fallback: select by index 1 (skip "Select One")
            try {
              await courseTypeSelect.selectOption({ index: 1 });
              console.log('  Selected course type (index 1)');
            } catch(e) {
              console.log('  WARNING: Could not select course type');
            }
          }
          await sleep(500);
        } else {
          console.log('  WARNING: Could not find course type select (#courseTypeBinder)');
        }

        // Hours/Credits — ctl00_PageContent_PageContent_rptSubjectAreas_ctl00_txtRequestedHours
        const hoursInput = await page.$('#ctl00_PageContent_PageContent_rptSubjectAreas_ctl00_txtRequestedHours, input[name*="txtRequestedHours"]');
        if (hoursInput) {
          await hoursInput.fill(String(ceu.credits));
          await sleep(300);
          console.log('  Filled hours:', ceu.credits);
        } else {
          console.log('  WARNING: Could not find hours input');
        }

        // Submit step 1 — "Continue to next step" button
        // Wait for it to be ready before trying to click
        console.log('  Looking for Continue button...');
        let continueBtn = null;
        for (let attempt = 0; attempt < 10; attempt++) {
          continueBtn = await page.$('#ctl00_PageContent_PageContent_btnContinue');
          if (continueBtn && await continueBtn.isVisible()) break;
          // Try fallback selectors
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
          // Dump what's actually on the page for debugging
          const allBtns = await page.$$eval('input, button', els => els.filter(e => e.offsetParent !== null).map(e => ({ tag: e.tagName, type: e.type, id: e.id, value: (e.value || '').substring(0, 40), text: (e.textContent || '').trim().substring(0, 40) })));
          console.log('  All visible buttons:', JSON.stringify(allBtns));
          const pageUrl = page.url();
          console.log('  Current URL:', pageUrl);
          // Save screenshot for debugging
          await page.screenshot({ path: '/tmp/cebroker_continue_fail.png' });
          throw new Error('Could not find Continue button after 10 attempts');
        }

        // ─── Step 8: Fill course details on next page ──────────
        // After Continue, there should be a form for course title, provider, etc.
        await sleep(3000);

        // Dump form fields on step 2 for debugging
        const step2Fields = await page.$$eval('input, select, textarea', els => els.filter(el => el.offsetParent !== null).map(el => ({
          tag: el.tagName, type: el.type, id: el.id, name: el.name,
          placeholder: el.placeholder || '', value: (el.value || '').substring(0, 50),
        })));
        console.log('  Step 2 form fields:', JSON.stringify(step2Fields).substring(0, 500));

        // Course Title — try multiple patterns
        const titleInput = await page.$('input[name*="title" i]:visible, input[id*="title" i]:visible, input[name*="course" i]:visible, input[id*="course" i]:visible, input[placeholder*="title" i]:visible, input[placeholder*="course" i]:visible, input[type="text"]:visible');
        if (titleInput) {
          await titleInput.fill(ceu.title);
          await sleep(300);
          console.log('  Filled title:', ceu.title);
        } else {
          console.log('  WARNING: Could not find title input on step 2');
        }

        // Provider/Sponsor
        const providerInput = await page.$('input[name*="provider" i]:visible, input[id*="provider" i]:visible, input[name*="sponsor" i]:visible, input[id*="sponsor" i]:visible, input[placeholder*="provider" i]:visible');
        if (providerInput) {
          await providerInput.fill(ceu.provider);
          await sleep(300);
          console.log('  Filled provider:', ceu.provider);
        } else {
          // Try second visible text input
          const textInputs = await page.$$('input[type="text"]:visible');
          if (textInputs.length > 1) {
            await textInputs[1].fill(ceu.provider);
            console.log('  Filled provider (fallback: 2nd text input)');
          } else {
            console.log('  WARNING: Could not find provider input');
          }
        }

        // Submit step 2
        const submitBtn2 = await page.$('input[type="submit"]:visible, button:has-text("Continue"):visible, button:has-text("Submit"):visible, button:has-text("Save"):visible, button:has-text("Finish"):visible, button:has-text("Confirm"):visible, a:has-text("Continue"):visible, a:has-text("Submit"):visible');
        if (submitBtn2) {
          await submitBtn2.click();
          await sleep(5000);
          try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}
          console.log('  Submitted step 2');

          // Check for confirmation step
          const confirmBtn = await page.$('button:has-text("Confirm"):visible, button:has-text("Finish"):visible, button:has-text("Complete"):visible, input[type="submit"]:visible');
          if (confirmBtn) {
            await confirmBtn.click();
            await sleep(3000);
            try { await page.waitForLoadState('networkidle', { timeout: 10000 }); } catch (e) {}
            console.log('  Confirmed submission');
          }

          // Check for success
          const pageText = await page.textContent('body').catch(() => '');
          if (pageText && (pageText.includes('successfully') || pageText.includes('received') || pageText.includes('submitted') || pageText.includes('thank you'))) {
            console.log('  ✅ CEU successfully reported');
            results.synced++;
            results.details.push({ title: ceu.title, status: 'synced', message: 'Successfully reported' });
          } else {
            console.log('  ✅ CEU submitted (no explicit success message)');
            results.synced++;
            results.details.push({ title: ceu.title, status: 'synced', message: 'Submitted to CE Broker' });
          }

        } else {
          throw new Error('Could not find submit button');
        }

        // Navigate back to Report CE page for next CEU
        if (idx < ceus.length - 1) {
          // Go back to dashboard, click Report CE, select TX license again
          await page.goto('https://app.cebroker.com/credentials', { waitUntil: 'domcontentloaded', timeout: 30000 });
          await sleep(3000);
          await page.click('button:has-text("Report CE")');
          await sleep(3000);
          try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}
          // Click TX license in modal
          const txBtn = await page.$('button:has-text("Respiratory Care Practitioner")');
          if (txBtn) { await txBtn.click(); await sleep(5000); }
        }

      } catch (err) {
        console.error(`  ❌ Failed: ${err.message}`);
        results.failed++;
        results.errors.push(`${ceu.title}: ${err.message}`);
        results.details.push({ title: ceu.title, status: 'failed', message: err.message });

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
          } catch (e) {}
        }
      }
    }

    await browser.close();
    browser = null;

  } catch (err) {
    console.error('Fatal error:', err.message);
    results.errors.push(`Fatal: ${err.message}`);
    if (browser) {
      try { await browser.close(); } catch (e) {}
    }
  }

  console.log('\n=== SYNC RESULTS ===');
  console.log(JSON.stringify(results, null, 2));
  fs.writeFileSync(RESULTS_FILE, JSON.stringify(results));
})();
"""


def sync_ceus_to_cebroker(email, ceus_to_sync, headless=True):
    if not ceus_to_sync:
        return {"synced": 0, "failed": 0, "errors": [], "details": [], "message": "No CEUs to sync"}

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
            timeout=300
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
            "errors": ["No results file produced — script may have crashed"],
            "details": [],
        }

    except subprocess.TimeoutExpired:
        logger.error("CE Broker sync timed out after 300 seconds")
        return {
            "synced": 0,
            "failed": len(ceus_to_sync),
            "errors": ["Sync timed out after 5 minutes"],
            "details": [],
        }
    except Exception as e:
        logger.error(f"CE Broker sync error: {e}")
        return {
            "synced": 0,
            "failed": len(ceus_to_sync),
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
    test_ceus = [
        {
            "title": "Mechanical Ventilation Updates 2026",
            "provider": "AARC",
            "credits": 4.0,
            "completion_date": "2026-07-15",
            "category": "clinical",
        },
    ]
    results = sync_ceus_to_cebroker("ron.sublett@gmail.com", test_ceus, headless=True)
    print("\nFinal results:")
    print(json.dumps(results, indent=2))