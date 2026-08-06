"""NBRC Portal Scraper — pulls CMP status from practitionerportal.nbrc.org.

Uses Playwright to log in and extract:
- Credentials (CRT, RRT, NPS, etc.) with earned dates and expiry
- CMP cycle dates
- Assessment scores
- CE hours required/completed
- Renewal method

Same pattern as CE Broker sync — Node script with Playwright.
"""
import json
import os
import logging
import subprocess
import tempfile

logger = logging.getLogger(__name__)

NODE_SCRIPT = r"""
const { chromium } = require('/home/ron/.npm-global/lib/node_modules/playwright');
const fs = require('fs');
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  const email = process.argv[2];
  const password = process.argv[3];
  const outputFile = process.argv[4];

  const result = { success: false, credentials: [], cycle: null, assessments: [], ce_hours: {}, error: null };

  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();

    // Login
    await page.goto('https://practitionerportal.nbrc.org/auth', { waitUntil: 'networkidle', timeout: 30000 });
    await sleep(3000);
    await page.fill('#email', email);
    await page.fill('#password', password);
    await page.click('input[type="submit"]');
    await sleep(8000);
    try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch(e) {}

    // Wait for spinner
    for (let i = 0; i < 10; i++) {
      const spinner = await page.$('.spinner');
      if (!spinner || !(await spinner.isVisible())) break;
      await sleep(2000);
    }
    await sleep(2000);

    if (page.url().includes('/auth')) {
      result.error = 'Login failed — check email/password';
      fs.writeFileSync(outputFile, JSON.stringify(result));
      await browser.close();
      return;
    }

    result.success = true;

    // Parse dashboard for credentials
    const bodyText = await page.textContent('body');
    
    // Extract earned credentials from dashboard text
    // Pattern: "CRTEarned05/16/2012Expires10/31/2030"
    const credMatches = bodyText.matchAll(/(CRT|RRT-NPS|RRT|RPFT|CPFT|ACCS|SDS|AE-C)Earned(\d{2}\/\d{2}\/\d{4})Expires(\d{2}\/\d{2}\/\d{4})/g);
    for (const m of credMatches) {
      result.credentials.push({
        type: m[1],
        earned_date: m[2],
        expires: m[3],
      });
    }

    // Extract registry number
    const regMatch = bodyText.match(/Registry #(\d+)/);
    if (regMatch) result.registry_number = regMatch[1];

    // Navigate to Credential Maintenance page for CMP details
    const ceuLink = await page.$('a:has-text("Enter my CEUs")');
    if (ceuLink) {
      await ceuLink.click();
      await sleep(5000);
      try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch(e) {}
      for (let i = 0; i < 10; i++) {
        const spinner = await page.$('.spinner');
        if (!spinner || !(await spinner.isVisible())) break;
        await sleep(2000);
      }
      await sleep(2000);

      const ceuText = await page.textContent('body');
      
      // Extract CMP cycle dates — "November 1, 2025 – October 31, 2030"
      const cycleMatch = ceuText.match(/(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+,\s+\d{4}\s*[–-]\s*(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+,\s+\d{4}/);
      if (cycleMatch) {
        result.cycle = cycleMatch[0].replace(/[–-]/, '-').trim();
      }

      // Extract CE hours — "General Hours  0 / 15" and "Neonatal/Pediatric  0 / 15"
      const generalMatch = ceuText.match(/General Hours\s+(\d+)\s*\/\s*(\d+)/);
      if (generalMatch) {
        result.ce_hours.general = { completed: parseInt(generalMatch[1]), required: parseInt(generalMatch[2]) };
      }

      const neoMatch = ceuText.match(/Neonatal\/Pediatric\s+(\d+)\s*\/\s*(\d+)/);
      if (neoMatch) {
        result.ce_hours.neonatal_pediatric = { completed: parseInt(neoMatch[1]), required: parseInt(neoMatch[2]) };
      }
    }

    // Navigate to Assessments page for CMP assessment scores
    await page.goto('https://practitionerportal.nbrc.org/', { waitUntil: 'networkidle', timeout: 30000 });
    await sleep(3000);
    const assessLink = await page.$('a:has-text("Go to Assessments")');
    if (assessLink) {
      await assessLink.click();
      await sleep(5000);
      try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch(e) {}
      for (let i = 0; i < 10; i++) {
        const spinner = await page.$('.spinner');
        if (!spinner || !(await spinner.isVisible())) break;
        await sleep(2000);
      }
      await sleep(2000);

      const assessText = await page.textContent('body');
      
      // Extract assessment score — "Assessment Score24 / 45"
      const scoreMatch = assessText.match(/Assessment Score\s*(\d+)\s*\/\s*(\d+)/);
      if (scoreMatch) {
        result.assessments.push({
          score: parseInt(scoreMatch[1]),
          max: parseInt(scoreMatch[2]),
          range: assessText.match(/(Low|Mid|High)/)?.[1] || null,
        });
      }

      // Extract CEUs due date
      const dueMatch = assessText.match(/(\d+)\s*CEUs?\s*likely\s*due\s*(\d{2}\/\d{2}\/\d{4})/);
      if (dueMatch) {
        result.ce_due = { ceus: parseInt(dueMatch[1]), date: dueMatch[2] };
      }
    }

    await browser.close();
    browser = null;
  } catch (err) {
    result.error = err.message;
    if (browser) { try { await browser.close(); } catch(e) {} }
  }

  fs.writeFileSync(outputFile, JSON.stringify(result, null, 2));
})();
"""


def scrape_nbrc_portal(email: str, password: str) -> dict:
    """Log into NBRC portal and extract CMP data.
    
    Returns dict with:
    - success: bool
    - credentials: list of {type, earned_date, expires}
    - cycle: str (e.g., "November 1, 2025 - October 31, 2030")
    - assessments: list of {score, max, range}
    - ce_hours: {general: {completed, required}, neonatal_pediatric: {completed, required}}
    - ce_due: {ceus, date}
    - registry_number: str
    - error: str or null
    """
    script_file = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, prefix='nbrc_scrape_')
    script_file.write(NODE_SCRIPT)
    script_file.close()

    output_file = script_file.name + '.json'

    try:
        env = os.environ.copy()
        env['NODE_PATH'] = '/home/ron/.npm-global/lib/node_modules'
        result = subprocess.run(
            ['node', script_file.name, email, password, output_file],
            cwd='/home/ron/.npm-global/lib/node_modules',
            env=env,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                logger.warning(f"[nbrc_scrape STDERR] {line}")

        if os.path.exists(output_file):
            with open(output_file) as f:
                return json.load(f)

        return {"success": False, "error": "No output file produced", "credentials": [], "assessments": []}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Scrape timed out after 120 seconds", "credentials": [], "assessments": []}
    except Exception as e:
        return {"success": False, "error": str(e), "credentials": [], "assessments": []}
    finally:
        try:
            os.unlink(script_file.name)
            if os.path.exists(output_file):
                os.unlink(output_file)
        except OSError:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = scrape_nbrc_portal("ron.sublett@gmail.com", "Subber2023!")
    print(json.dumps(result, indent=2))