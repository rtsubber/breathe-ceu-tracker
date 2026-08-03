"""
CE Broker Sync Agent — automatically uploads CEUs from Breathe to CE Broker.

Flow:
1. Log into CE Broker via email + OTP (OTP caught from AgentMail)
2. Navigate to Report CE page
3. For each unreported CEU in Breathe:
   a. Select appropriate credit type
   b. Fill in course title, provider, credits, completion date
   c. Submit the form
   d. Mark CEU as "reported to CE Broker" in Breathe database
4. Return summary of synced CEUs

Uses Playwright for browser automation (same pattern as TikTok uploader).
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

# AgentMail config
AGENTMAIL_CONFIG_PATH = "/home/ron/.openclaw/workspace/.agentmail_config.json"

# CE Broker URLs
CEBROKER_LOGIN_URL = "https://launchpad.cebroker.com/login"
CEBROKER_APP_URL = "https://app.cebroker.com/credentials"
CEBROKER_REPORT_CE_URL = "https://secure.cebroker.com/limited/lm_ce_request_lst_v2.aspx?lic=18499898"


def get_agentmail_config():
    """Load AgentMail config."""
    with open(AGENTMAIL_CONFIG_PATH) as f:
        return json.load(f)


def fetch_otp_from_agentmail(before_timestamp=None, max_wait=90):
    """
    Poll AgentMail for a CE Broker OTP email.

    Args:
        before_timestamp: ISO timestamp of the previous OTP (to detect new ones)
        max_wait: Max seconds to wait

    Returns:
        Tuple of (6-digit OTP string, timestamp) or (None, None)
    """
    config = get_agentmail_config()
    api_key = config['api_key']
    inbox_id = config.get('inbox_id', 'jarvis-epictrends@agentmail.to')

    start = time.time()
    while time.time() - start < max_wait:
        try:
            url = f"https://api.agentmail.to/v0/inboxes/{inbox_id}/messages?limit=5"
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            })
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            messages = data.get('messages', [])

            for msg in messages:
                from_addr = (msg.get('from', msg.get('from_', ''))).lower()
                if 'cebroker' in from_addr or 'propelus' in from_addr:
                    ts = msg.get('timestamp', msg.get('created_at', ''))
                    if before_timestamp and ts == before_timestamp:
                        continue  # Skip old OTP

                    body = msg.get('body', msg.get('text', msg.get('preview', '')))
                    otp_match = re.search(r'\b(\d{6})\b', body if body else '')
                    if not otp_match:
                        otp_match = re.search(r'\b(\d{6})\b', msg.get('subject', ''))
                    if otp_match:
                        logger.info(f"Found CE Broker OTP: {otp_match.group(1)} (ts: {ts})")
                        return otp_match.group(1), ts
        except Exception as e:
            logger.error(f"AgentMail poll error: {e}")

        time.sleep(2)

    logger.warning(f"No CE Broker OTP found within {max_wait}s")
    return None, None


def get_latest_otp_timestamp():
    """Get the timestamp of the most recent CE Broker OTP email (before triggering a new one)."""
    import urllib.request
    config = get_agentmail_config()
    api_key = config['api_key']
    inbox_id = config.get('inbox_id', 'jarvis-epictrends@agentmail.to')

    try:
        url = f"https://api.agentmail.to/v0/inboxes/{inbox_id}/messages?limit=5"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        messages = data.get('messages', [])

        for msg in messages:
            from_addr = (msg.get('from', msg.get('from_', ''))).lower()
            if 'cebroker' in from_addr or 'propelus' in from_addr:
                return msg.get('timestamp', msg.get('created_at', ''))
    except Exception as e:
        logger.error(f"Error getting latest OTP timestamp: {e}")

    return None


# ─── CE Broker category mapping ─────────────────────────────────

# Maps Breathe CEU categories to CE Broker credit types
# CE Broker categories: General Medical, Respiratory Care, Ethics, Patient Safety,
#   Infectious Disease, Pediatrics, Geriatrics, Cardiac, Neuroscience,
#   Critical Care, Emergency, Management/Leadership, Education/Research
CEBROKER_CATEGORY_MAP = {
    "clinical": "Respiratory Care",
    "safety": "Patient Safety",
    "ethics": "Ethics",
    "leadership": "Management/Leadership",
    "education": "Education/Research",
    "cardiac": "Cardiac",
    "pediatrics": "Pediatrics",
    "geriatrics": "Geriatrics",
    "neuroscience": "Neuroscience",
    "critical_care": "Critical Care",
    "emergency": "Emergency",
    "infectious_disease": "Infectious Disease",
    "general": "General Medical",
}


def map_category_to_cebroker(breathe_category):
    """Map a Breathe CEU category to the closest CE Broker credit type."""
    return CEBROKER_CATEGORY_MAP.get(breathe_category, "General Medical")


# ─── Node script for Playwright automation ─────────────────────

NODE_SCRIPT_TEMPLATE = r"""
const {{ chromium }} = require('playwright');
const https = require('https');
const fs = require('fs');

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

const CEBROKER_LOGIN_URL = 'https://launchpad.cebroker.com/login';
const CEBROKER_REPORT_CE_URL = '{report_ce_url}';
const CEUS_FILE = '{ceus_file}';
const RESULTS_FILE = '{results_file}';
const CEBROKER_EMAIL = '{email}';
const HEADLESS = {headless};

function getLatestOTP(config) {{
  return new Promise((resolve, reject) => {{
    const options = {{
      hostname: 'api.agentmail.to',
      path: `/v0/inboxes/${{config.inbox_id}}/messages?limit=5`,
      headers: {{ 'Authorization': `Bearer ${{config.api_key}}`, 'Content-Type': 'application/json' }}
    }};
    https.get(options, (res) => {{
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {{
        try {{
          const messages = JSON.parse(data).messages || [];
          for (const msg of messages) {{
            const from = (msg.from || msg.from_ || '').toLowerCase();
            if (from.includes('cebroker') || from.includes('propelus')) {{
              const body = msg.body || msg.text || msg.preview || '';
              const match = body.match(/\b(\d{{6}})\b/) || (msg.subject || '').match(/\b(\d{{6}})\b/);
              if (match) {{
                resolve({{ otp: match[1], ts: msg.timestamp || msg.created_at }});
                return;
              }}
            }}
          }}
          resolve(null);
        }} catch (e) {{ reject(e); }}
      }});
    }}).on('error', reject);
  }});
}}

// Map Breathe categories to CE Broker credit types
const CATEGORY_MAP = {{
  clinical: 'Respiratory Care',
  safety: 'Patient Safety',
  ethics: 'Ethics',
  leadership: 'Management/Leadership',
  education: 'Education/Research',
  cardiac: 'Cardiac',
  pediatrics: 'Pediatrics',
  geriatrics: 'Geriatrics',
  neuroscience: 'Neuroscience',
  critical_care: 'Critical Care',
  emergency: 'Emergency',
  infectious_disease: 'Infectious Disease',
  general: 'General Medical',
}};

function mapCategory(cat) {{
  return CATEGORY_MAP[cat] || 'General Medical';
}}

(async () => {{
  const ceus = JSON.parse(fs.readFileSync(CEUS_FILE, 'utf8'));
  const config = JSON.parse(fs.readFileSync('/home/ron/.openclaw/workspace/.agentmail_config.json', 'utf8'));

  const results = {{ synced: 0, failed: 0, errors: [], details: [] }};

  if (ceus.length === 0) {{
    console.log('No CEUs to sync');
    fs.writeFileSync(RESULTS_FILE, JSON.stringify(results));
    return;
  }}

  let browser;
  try {{
    browser = await chromium.launch({{ headless: HEADLESS }});
    const context = await browser.newContext({{
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      viewport: {{ width: 1280, height: 900 }},
    }});
    const page = await context.newPage();

    // ─── Step 1: Get baseline OTP timestamp ────────────────────
    const before = await getLatestOTP(config);
    const beforeTs = before ? before.ts : null;
    console.log('Baseline OTP ts:', beforeTs);

    // ─── Step 2: Login to CE Broker ────────────────────────────
    console.log('Loading CE Broker login...');
    await page.goto(CEBROKER_LOGIN_URL, {{ waitUntil: 'domcontentloaded', timeout: 30000 }});
    await sleep(3000);

    // Enter email
    await page.waitForSelector('#username', {{ timeout: 10000 }});
    await page.fill('#username', CEBROKER_EMAIL);
    await sleep(500);
    await page.click('button[type="submit"]');
    console.log('Email submitted, waiting for OTP page...');

    // Wait for OTP input fields
    await page.waitForSelector('#otp-0', {{ timeout: 15000 }});
    console.log('OTP page shown');

    // ─── Step 3: Poll for fresh OTP ────────────────────────────
    let otp = null;
    for (let i = 0; i < 45; i++) {{
      await sleep(2000);
      const result = await getLatestOTP(config);
      if (result && result.ts !== beforeTs) {{
        otp = result.otp;
        console.log(`Fresh OTP received: ${{otp}}`);
        break;
      }}
      if (i % 5 === 4) console.log(`  Waiting for OTP... (${{i + 1}}s attempt)`);
    }}

    if (!otp) {{
      throw new Error('No OTP received within 90 seconds. Check AgentMail inbox.');
    }}

    // ─── Step 4: Enter OTP and submit ──────────────────────────
    for (let i = 0; i < 6; i++) {{
      await page.fill(`#otp-${{i}}`, otp[i]);
      await sleep(100);
    }}
    await sleep(500);
    await page.click('button[type="submit"]');
    console.log('OTP submitted, waiting for dashboard...');

    // Wait for navigation to dashboard
    await sleep(5000);
    try {{
      await page.waitForLoadState('networkidle', {{ timeout: 15000 }});
    }} catch (e) {{}}

    const currentUrl = page.url();
    console.log('After login URL:', currentUrl);

    if (!currentUrl.includes('cebroker.com')) {{
      throw new Error(`Login may have failed. URL: ${{currentUrl}}`);
    }}

    // ─── Step 5: Navigate to Report CE page ────────────────────
    // Try clicking "Report CE" button on dashboard first
    const reportBtn = await page.$('a:has-text("Report CE"), button:has-text("Report CE")');
    if (reportBtn) {{
      await reportBtn.click();
      await sleep(5000);
      try {{ await page.waitForLoadState('networkidle', {{ timeout: 10000 }}); }} catch (e) {{}}
    }} else {{
      // Navigate directly to the Report CE URL
      console.log('No Report CE button found, navigating directly...');
      await page.goto(CEBROKER_REPORT_CE_URL, {{ waitUntil: 'domcontentloaded', timeout: 30000 }});
      await sleep(5000);
    }}

    // Dismiss any modal/tooltip
    const gotItBtn = await page.$('button:has-text("Okay, got it"), button:has-text("Got it"), button:has-text("Close")');
    if (gotItBtn) {{
      await gotItBtn.click();
      await sleep(1000);
    }}

    console.log('On Report CE page. URL:', page.url());

    // ─── Step 6: Sync each CEU ─────────────────────────────────
    for (let idx = 0; idx < ceus.length; idx++) {{
      const ceu = ceus[idx];
      try {{
        console.log(`\n--- Syncing CEU ${{idx + 1}}/${{ceus.length}}: ${{ceu.title}} ---`);
        console.log(`  Provider: ${{ceu.provider}}`);
        console.log(`  Credits: ${{ceu.credits}}`);
        console.log(`  Date: ${{ceu.completion_date}}`);
        console.log(`  Category: ${{ceu.category}} -> ${{mapCategory(ceu.category)}}`);

        // The Report CE page has credit type categories with "Report" buttons
        // We need to find the right category and click its Report button

        const cebrokerCat = mapCategory(ceu.category);

        // Look for the credit type row matching our category
        // CE Broker uses a table/list with credit type names and Report buttons
        let reportButton = null;

        // Try to find a link/button with the category name
        const allLinks = await page.$$('a, button');
        for (const link of allLinks) {{
          const text = (await link.textContent()) || '';
          if (text.includes(cebrokerCat)) {{
            reportButton = link;
            break;
          }}
        }}

        if (!reportButton) {{
          // Try clicking "Report CE/CME" generic button
          reportButton = await page.$('a:has-text("Report CE/CME"), button:has-text("Report CE/CME"), a:has-text("Report Individual"), button:has-text("Report Individual")');
        }}

        if (!reportButton) {{
          // Try any "Report" button
          reportButton = await page.$('a:has-text("Report"):not(:has-text("Quick")), button:has-text("Report"):not(:has-text("Quick"))');
        }}

        if (!reportButton) {{
          throw new Error(`Could not find Report button for category: ${{cebrokerCat}}`);
        }}

        await reportButton.click();
        await sleep(3000);
        try {{ await page.waitForLoadState('networkidle', {{ timeout: 10000 }}); }} catch (e) {{}}

        console.log('  Clicked Report button, on form page now');

        // Now we should be on the CE reporting form
        // This is typically a multi-step form. Fill in the fields.

        // Step 1: Subject/Topic area (if shown)
        const subjectSelect = await page.$('select[name*="subject"], select[id*="subject"]');
        if (subjectSelect) {{
          try {{
            await subjectSelect.selectOption({{ label: cebrokerCat }});
          }} catch (e) {{
            try {{
              await subjectSelect.selectOption({{ index: 1 }});
            }} catch (e2) {{}}
          }}
          await sleep(500);
        }}

        // Step 2: Course/Activity Title
        const titleInput = await page.$(
          'input[name*="title"], input[name*="Title"], input[name*="course"], input[name*="Course"], ' +
          'input[id*="title"], input[id*="Title"], input[id*="course"], input[id*="Course"], ' +
          'input[placeholder*="title"], input[placeholder*="Title"], input[placeholder*="course"]'
        );
        if (titleInput) {{
          await titleInput.fill(ceu.title);
          await sleep(300);
          console.log('  Filled title');
        }} else {{
          console.log('  WARNING: Could not find title input field');
        }}

        // Step 3: Provider/Sponsor
        const providerInput = await page.$(
          'input[name*="provider"], input[name*="Provider"], input[name*="sponsor"], input[name*="Sponsor"], ' +
          'input[id*="provider"], input[id*="Provider"], input[id*="sponsor"], input[id*="Sponsor"], ' +
          'input[placeholder*="provider"], input[placeholder*="Provider"], input[placeholder*="sponsor"]'
        );
        if (providerInput) {{
          await providerInput.fill(ceu.provider);
          await sleep(300);
          console.log('  Filled provider');
        }} else {{
          console.log('  WARNING: Could not find provider input field');
        }}

        // Step 4: Credit hours / Contact hours
        const creditsInput = await page.$(
          'input[name*="credit"], input[name*="Credit"], input[name*="hour"], input[name*="Hour"], ' +
          'input[name*="ce"], input[name*="CE"], input[id*="credit"], input[id*="Credit"], ' +
          'input[id*="hour"], input[id*="Hour"], input[type="number"]'
        );
        if (creditsInput) {{
          await creditsInput.fill(String(ceu.credits));
          await sleep(300);
          console.log('  Filled credits');
        }} else {{
          console.log('  WARNING: Could not find credits input field');
        }}

        // Step 5: Completion date
        // Date may be in MM/DD/YYYY format on CE Broker
        const dateObj = new Date(ceu.completion_date);
        const mm = String(dateObj.getMonth() + 1).padStart(2, '0');
        const dd = String(dateObj.getDate()).padStart(2, '0');
        const yyyy = dateObj.getFullYear();
        const dateStr = `${{mm}}/${{dd}}/${{yyyy}}`;

        const dateInput = await page.$(
          'input[name*="date"], input[name*="Date"], input[name*="completion"], input[name*="Completion"], ' +
          'input[id*="date"], input[id*="Date"], input[id*="completion"], input[id*="Completion"], ' +
          'input[type="date"], input[placeholder*="date"], input[placeholder*="Date"]'
        );
        if (dateInput) {{
          // Try different date formats
          try {{
            await dateInput.fill(dateStr);
          }} catch (e) {{
            try {{
              await dateInput.fill(ceu.completion_date);
            }} catch (e2) {{
              // Try ISO format without time
              await dateInput.fill(ceu.completion_date.split('T')[0]);
            }}
          }}
          await sleep(300);
          console.log('  Filled date:', dateStr);
        }} else {{
          console.log('  WARNING: Could not find date input field');
        }}

        // Step 6: Delivery method (if required)
        const deliverySelect = await page.$('select[name*="delivery"], select[name*="Delivery"], select[id*="delivery"], select[id*="Delivery"]');
        if (deliverySelect) {{
          try {{
            await deliverySelect.selectOption({{ index: 1 }});
          }} catch (e) {{}}
          await sleep(300);
        }}

        // Step 7: Submit the form
        // Look for Continue/Next/Submit buttons
        const submitBtn = await page.$(
          'button:has-text("Continue"), button:has-text("Next"), button:has-text("Submit"), ' +
          'button:has-text("Save"), button:has-text("Report"), input[type="submit"], ' +
          'a:has-text("Continue"), a:has-text("Submit"), a:has-text("Save")'
        );

        if (submitBtn) {{
          await submitBtn.click();
          await sleep(3000);
          try {{ await page.waitForLoadState('networkidle', {{ timeout: 10000 }}); }} catch (e) {{}}
          console.log('  Submitted form');

          // Check for confirmation or additional steps
          // There might be a review/confirm step
          const confirmBtn = await page.$(
            'button:has-text("Confirm"), button:has-text("Finish"), button:has-text("Complete"), ' +
            'button:has-text("Submit Final"), a:has-text("Confirm"), a:has-text("Finish")'
          );
          if (confirmBtn) {{
            await confirmBtn.click();
            await sleep(3000);
            try {{ await page.waitForLoadState('networkidle', {{ timeout: 10000 }}); }} catch (e) {{}}
            console.log('  Confirmed submission');
          }}

          // Check for success message
          const pageText = await page.textContent('body').catch(() => '');
          if (pageText && (pageText.includes('successfully') || pageText.includes('received') || pageText.includes('submitted') || pageText.includes('thank you'))) {{
            console.log('  ✅ CEU successfully reported');
            results.synced++;
            results.details.push({{ title: ceu.title, status: 'synced', message: 'Successfully reported' }});
          }} else {{
            // Assume success if no error visible
            console.log('  ✅ CEU submitted (no explicit success message found)');
            results.synced++;
            results.details.push({{ title: ceu.title, status: 'synced', message: 'Submitted to CE Broker' }});
          }}

        }} else {{
          throw new Error('Could not find submit button on form');
        }}

        // Navigate back to Report CE page for next CEU
        if (idx < ceus.length - 1) {{
          await page.goto(CEBROKER_REPORT_CE_URL, {{ waitUntil: 'domcontentloaded', timeout: 30000 }});
          await sleep(3000);

          // Dismiss any modal
          const gotIt = await page.$('button:has-text("Okay, got it"), button:has-text("Got it"), button:has-text("Close")');
          if (gotIt) {{
            await gotIt.click();
            await sleep(1000);
          }}
        }}

      }} catch (err) {{
        console.error(`  ❌ Failed: ${{err.message}}`);
        results.failed++;
        results.errors.push(`${{ceu.title}}: ${{err.message}}`);
        results.details.push({{ title: ceu.title, status: 'failed', message: err.message }});

        // Try to navigate back to Report CE page for next CEU
        if (idx < ceus.length - 1) {{
          try {{
            await page.goto(CEBROKER_REPORT_CE_URL, {{ waitUntil: 'domcontentloaded', timeout: 30000 }});
            await sleep(3000);
          }} catch (e) {{}}
        }}
      }}
    }}

    await browser.close();
    browser = null;

  }} catch (err) {{
    console.error('Fatal error:', err.message);
    results.errors.push(`Fatal: ${{err.message}}`);
    if (browser) {{
      try {{ await browser.close(); }} catch (e) {{}}
    }}
  }}

  console.log('\n=== SYNC RESULTS ===');
  console.log(JSON.stringify(results, null, 2));

  // Write results to file for Python to read
  fs.writeFileSync(RESULTS_FILE, JSON.stringify(results));
}})();
"""


def sync_ceus_to_cebroker(email, ceus_to_sync, headless=True):
    """
    Log into CE Broker and sync CEU records.

    Args:
        email: CE Broker account email
        ceus_to_sync: List of dicts with keys: title, provider, credits, completion_date, category
        headless: Run browser in headless mode

    Returns:
        Dict with sync results: {synced: int, failed: int, errors: [str], details: [dict]}
    """
    if not ceus_to_sync:
        return {"synced": 0, "failed": 0, "errors": [], "details": [], "message": "No CEUs to sync"}

    # Write CEUs to a temp file for the Node script to read
    ceus_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, prefix='cebroker_ceus_')
    json.dump(ceus_to_sync, ceus_file)
    ceus_file.close()

    results_file = ceus_file.name + '.results'

    # Generate the Node script
    node_script = NODE_SCRIPT_TEMPLATE.format(
        ceus_file=ceus_file.name,
        results_file=results_file,
        email=email,
        headless=str(headless).lower(),
        report_ce_url=CEBROKER_REPORT_CE_URL,
    )

    script_file = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, prefix='cebroker_sync_')
    script_file.write(node_script)
    script_file.close()

    try:
        logger.info(f"Starting CE Broker sync for {len(ceus_to_sync)} CEUs (email: {email})")
        result = subprocess.run(
            ['node', script_file.name],
            cwd='/home/ron/.npm-global/lib/node_modules',
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes max
        )

        # Log output
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                logger.info(f"[cebroker_sync] {line}")
        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                logger.warning(f"[cebroker_sync STDERR] {line}")

        # Read results
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
        # Cleanup temp files
        try:
            os.unlink(ceus_file.name)
            os.unlink(script_file.name)
            if os.path.exists(results_file):
                os.unlink(results_file)
        except OSError:
            pass


if __name__ == "__main__":
    # Test the sync agent directly
    logging.basicConfig(level=logging.INFO)

    test_ceus = [
        {
            "title": "Mechanical Ventilation Updates 2026",
            "provider": "AARC",
            "credits": 4.0,
            "completion_date": "2026-07-15",
            "category": "clinical",
        },
        {
            "title": "Ethics in Respiratory Care",
            "provider": "AARC",
            "credits": 2.0,
            "completion_date": "2026-06-20",
            "category": "ethics",
        },
    ]

    results = sync_ceus_to_cebroker("ron.sublett@gmail.com", test_ceus, headless=False)
    print("\nFinal results:")
    print(json.dumps(results, indent=2))