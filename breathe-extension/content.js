// content.js — Breathe CEU Tracker content script
// Detects CEU certificates on web pages and shows a floating "Log to Breathe" button

(function () {
  'use strict';

  // Prevent double-injection
  if (window.__breatheCEUInjected) return;
  window.__breatheCEUInjected = true;

  // ─── Detection patterns ───────────────────────────────────────────────

  const CEU_TEXT_PATTERNS = [
    /\bCEU\b/i,
    /\bcontact\s+hours?\b/i,
    /\bcontinuing\s+education\b/i,
    /\bcontinuing\s+professional\s+development\b/i,
    /\bCPD\b/i,
    /\bCME\b/i,
    /\bCNE\b/i,
    /\bCE\s+credit/i,
    /\bCE\s+hours?\b/i,
    /\bprofessional\s+development\s+hours?\b/i,
  ];

  const CERTIFICATE_URL_PATTERNS = [
    /certificate/i,
    /ceu[-_]?cert/i,
    /completion[-_]?cert/i,
    /award/i,
    /diploma/i,
  ];

  const CREDIT_PATTERNS = [
    /(\d+(?:\.\d+)?)\s*CEU[s]?/i,
    /(\d+(?:\.\d+)?)\s*contact\s+hours?/i,
    /(\d+(?:\.\d+)?)\s*continuing\s+education\s+(?:credit|unit|hour)s?/i,
    /(\d+(?:\.\d+)?)\s*CE\s+(?:credit|hour|unit)s?/i,
    /(\d+(?:\.\d+)?)\s*credit\s+hours?/i,
    /(\d+(?:\.\d+)?)\s*credits?/i,
    /(\d+(?:\.\d+)?)\s*hours?\s*(?:of)?\s*(?:CE|CEU|credit|contact)/i,
    /(\d+(?:\.\d+)?)\s*CPD\s*hours?/i,
  ];

  const DATE_PATTERNS = [
    // "August 2, 2026" or "August 2nd, 2026"
    /(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}/i,
    // "2 August 2026"
    /\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}/i,
    // "08/02/2026" or "8/2/2026" or "2026-08-02"
    /\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}/,
    /\d{4}-\d{2}-\d{2}/,
    // "Completed on: ..."
    /completed\s+on[:\s]+(.+)/i,
    /date\s+(?:of\s+)?completion[:\s]+(.+)/i,
    /date\s+awarded[:\s]+(.+)/i,
    /issued\s+on[:\s]+(.+)/i,
  ];

  // ─── Detection logic ──────────────────────────────────────────────────

  function getPageText() {
    // Get visible text from body, prioritizing main content
    const main = document.querySelector('main') || document.querySelector('#content') || document.body;
    return main ? main.innerText : document.body.innerText;
  }

  function getSelectedText() {
    const sel = window.getSelection();
    return sel ? sel.toString().trim() : '';
  }

  function findPdfCertificates() {
    const results = [];
    const links = document.querySelectorAll('a[href]');
    for (const link of links) {
      const href = link.href || '';
      const text = link.textContent || '';
      if (/\.pdf$/i.test(href) && CERTIFICATE_URL_PATTERNS.some(p => p.test(href) || p.test(text))) {
        results.push({ type: 'pdf', url: href, text: text });
      }
    }
    return results;
  }

  function findCertificateImages() {
    const results = [];
    const imgs = document.querySelectorAll('img');
    for (const img of imgs) {
      const src = img.src || '';
      const alt = img.alt || '';
      if (CERTIFICATE_URL_PATTERNS.some(p => p.test(src) || p.test(alt))) {
        results.push({ type: 'image', src, alt });
      }
    }
    return results;
  }

  function findPrintButtons() {
    const printBtns = document.querySelectorAll(
      'button[onclick*="print"], a[onclick*="print"], button[onclick*="Print"], ' +
      'a[href*="javascript:print"], .print-button, .btn-print, ' +
      'button[aria-label*="print" i], a[aria-label*="print" i]'
    );
    return Array.from(printBtns).slice(0, 3);
  }

  function detectCEUContent() {
    const pageText = getPageText();
    return CEU_TEXT_PATTERNS.some(p => p.test(pageText));
  }

  function extractCredits(text) {
    for (const pattern of CREDIT_PATTERNS) {
      const match = text.match(pattern);
      if (match && match[1]) {
        return parseFloat(match[1]);
      }
    }
    return null;
  }

  function extractDate(text) {
    for (const pattern of DATE_PATTERNS) {
      const match = text.match(pattern);
      if (match) {
        // Try to parse the date
        const dateStr = match[0] || match[1] || '';
        const parsed = new Date(dateStr);
        if (!isNaN(parsed.getTime())) {
          return parsed.toISOString().split('T')[0]; // YYYY-MM-DD
        }
        // Try the captured group if full match didn't parse
        if (match[1]) {
          const parsed2 = new Date(match[1]);
          if (!isNaN(parsed2.getTime())) {
            return parsed2.toISOString().split('T')[0];
          }
        }
      }
    }
    return null;
  }

  function extractProvider() {
    // Try meta tags first
    const ogSite = document.querySelector('meta[property="og:site_name"]');
    if (ogSite && ogSite.content) return ogSite.content;

    // Try domain name
    const domain = window.location.hostname.replace(/^www\./, '');
    const niceDomain = domain.split('.')[0];
    if (niceDomain) {
      return niceDomain.charAt(0).toUpperCase() + niceDomain.slice(1);
    }

    return '';
  }

  function extractCourseTitle() {
    // Try page title, clean it up
    let title = document.title || '';
    // Remove common suffixes
    title = title.replace(/\s*[|\-–—]\s*.*$/, '').trim();
    if (title && title.length > 5) return title;

    // Try h1
    const h1 = document.querySelector('h1');
    if (h1 && h1.textContent.trim().length > 3) return h1.textContent.trim();

    return title || 'Unknown Course';
  }

  function extractPageData() {
    const selectedText = getSelectedText();
    const pageText = selectedText || getPageText();

    return {
      title: extractCourseTitle(),
      provider: extractProvider(),
      credits: extractCredits(pageText),
      date: extractDate(pageText) || new Date().toISOString().split('T')[0],
      url: window.location.href,
      selectedText: selectedText.substring(0, 2000),
      detectedAt: new Date().toISOString(),
    };
  }

  function detectCertificate() {
    const pdfCerts = findPdfCertificates();
    const certImages = findCertificateImages();
    const printBtns = findPrintButtons();
    const hasCEUText = detectCEUContent();

    // Detection score
    let score = 0;
    const reasons = [];

    if (pdfCerts.length > 0) { score += 3; reasons.push('PDF certificate link found'); }
    if (certImages.length > 0) { score += 2; reasons.push('Certificate image found'); }
    if (printBtns.length > 0) { score += 1; reasons.push('Print button found'); }
    if (hasCEUText) { score += 2; reasons.push('CEU/continuing education text detected'); }

    // Check URL for certificate indicators
    if (CERTIFICATE_URL_PATTERNS.some(p => p.test(window.location.href))) {
      score += 2;
      reasons.push('URL contains certificate indicator');
    }

    return {
      detected: score >= 2,
      score,
      reasons,
      pdfCerts,
      certImages,
      hasCEUText,
    };
  }

  // ─── UI: Floating button ───────────────────────────────────────────────

  let floatingButton = null;
  let popupForm = null;

  function createFloatingButton() {
    if (floatingButton) return;

    floatingButton = document.createElement('div');
    floatingButton.id = 'breathe-ceu-fab';
    floatingButton.innerHTML = `
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M6.081 16c-1.959-.48-3.081-2.968-3.081-5.5 0-2.485 1-4.5 3-4.5s3 2.015 3 4.5c0 2.532-1.122 5.02-3.081 5.5z"/>
        <path d="M17.919 16c1.959-.48 3.081-2.968 3.081-5.5 0-2.485-1-4.5-3-4.5s-3 2.015-3 4.5c0 2.532 1.122 5.02 3.081 5.5z"/>
        <path d="M12 6v12"/>
        <path d="M9 18h6"/>
      </svg>
      <span>Log to Breathe</span>
    `;

    floatingButton.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      showCeuForm();
    });

    document.body.appendChild(floatingButton);
  }

  function removeFloatingButton() {
    if (floatingButton) {
      floatingButton.remove();
      floatingButton = null;
    }
  }

  // ─── UI: CEU form popup ────────────────────────────────────────────────

  function getCategorySuggestion(title, provider, pageText) {
    const text = ((title || '') + ' ' + (provider || '') + ' ' + (pageText || '')).toLowerCase();
    const categories = [
      { name: 'Respiratory Care', keywords: ['respiratory', 'ventilator', 'oxygen', 'airway', 'intubation', 'cpap', 'bipap'] },
      { name: 'Critical Care', keywords: ['critical', 'icu', 'sepsis', 'shock', 'trauma', 'emergency'] },
      { name: 'Pediatrics', keywords: ['pediatric', 'neonatal', 'infant', 'child', 'pediatrics'] },
      { name: 'Cardiac Care', keywords: ['cardiac', 'ecg', 'ekg', 'heart', 'cardiovascular', 'acls'] },
      { name: 'Infection Control', keywords: ['infection', 'covid', 'ppe', 'hygiene', 'sterile'] },
      { name: 'Pharmacology', keywords: ['pharmacology', 'medication', 'drug', 'dosage', 'prescription'] },
      { name: 'Patient Safety', keywords: ['safety', 'error', 'quality', 'risk management'] },
      { name: 'Ethics', keywords: ['ethics', 'legal', 'compliance', 'hipaa'] },
      { name: 'Leadership', keywords: ['leadership', 'management', 'supervisor', 'admin'] },
      { name: 'General', keywords: [] },
    ];
    for (const cat of categories) {
      if (cat.keywords.some(kw => text.includes(kw))) return cat.name;
    }
    return 'General';
  }

  function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.id = 'breathe-ceu-toast';
    toast.className = `breathe-ceu-toast breathe-ceu-toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    // Trigger animation
    requestAnimationFrame(() => toast.classList.add('breathe-ceu-toast-show'));

    setTimeout(() => {
      toast.classList.remove('breathe-ceu-toast-show');
      setTimeout(() => toast.remove(), 400);
    }, 3500);
  }

  function showCeuForm() {
    // Remove existing form
    if (popupForm) popupForm.remove();

    const data = extractPageData();
    const category = getCategorySuggestion(data.title, data.provider, data.selectedText || getPageText());

    popupForm = document.createElement('div');
    popupForm.id = 'breathe-ceu-modal';
    popupForm.innerHTML = `
      <div class="breathe-ceu-modal-overlay"></div>
      <div class="breathe-ceu-modal-box">
        <div class="breathe-ceu-modal-header">
          <div class="breathe-ceu-modal-logo">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M6.081 16c-1.959-.48-3.081-2.968-3.081-5.5 0-2.485 1-4.5 3-4.5s3 2.015 3 4.5c0 2.532-1.122 5.02-3.081 5.5z"/>
              <path d="M17.919 16c1.959-.48 3.081-2.968 3.081-5.5 0-2.485-1-4.5-3-4.5s-3 2.015-3 4.5c0 2.532 1.122 5.02 3.081 5.5z"/>
              <path d="M12 6v12"/>
              <path d="M9 18h6"/>
            </svg>
            <span>Log CEU to Breathe</span>
          </div>
          <button class="breathe-ceu-close" title="Close">&times;</button>
        </div>
        <form class="breathe-ceu-form" id="breathe-ceu-form">
          <label>
            <span>Course Title</span>
            <input type="text" name="title" value="${escapeHtml(data.title)}" required>
          </label>
          <label>
            <span>Provider</span>
            <input type="text" name="provider" value="${escapeHtml(data.provider)}" required>
          </label>
          <div class="breathe-ceu-form-row">
            <label>
              <span>Credits</span>
              <input type="number" step="0.25" min="0.25" name="credits" value="${data.credits || ''}" placeholder="e.g. 4" required>
            </label>
            <label>
              <span>Completion Date</span>
              <input type="date" name="date" value="${data.date}" required>
            </label>
          </div>
          <label>
            <span>Category</span>
            <select name="category">
              ${['Respiratory Care','Critical Care','Pediatrics','Cardiac Care','Infection Control','Pharmacology','Patient Safety','Ethics','Leadership','General'].map(c =>
                `<option value="${c}" ${c === category ? 'selected' : ''}>${c}</option>`
              ).join('')}
            </select>
          </label>
          <label>
            <span>Source URL</span>
            <input type="url" name="url" value="${escapeHtml(data.url)}" readonly class="breathe-ceu-readonly">
          </label>
          <div class="breathe-ceu-form-actions">
            <button type="button" class="breathe-ceu-btn breathe-ceu-btn-cancel">Cancel</button>
            <button type="submit" class="breathe-ceu-btn breathe-ceu-btn-save">Save to Breathe</button>
          </div>
          <div class="breathe-ceu-detected-info">
            ${data.credits ? `<span>✓ Detected ${data.credits} credits</span>` : '<span class="breathe-ceu-hint">Tip: select text with credit info before clicking</span>'}
          </div>
        </form>
      </div>
    `;

    document.body.appendChild(popupForm);

    // Handle close
    const overlay = popupForm.querySelector('.breathe-ceu-modal-overlay');
    const closeBtn = popupForm.querySelector('.breathe-ceu-close');
    const cancelBtn = popupForm.querySelector('.breathe-ceu-btn-cancel');

    const closeForm = () => {
      if (popupForm) { popupForm.remove(); popupForm = null; }
    };

    overlay.addEventListener('click', closeForm);
    closeBtn.addEventListener('click', closeForm);
    cancelBtn.addEventListener('click', closeForm);

    // Handle submit
    const form = popupForm.querySelector('#breathe-ceu-form');
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      await submitCeu(form);
    });
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  async function submitCeu(form) {
    const formData = new FormData(form);
    const ceuData = {
      title: formData.get('title'),
      provider: formData.get('provider'),
      credits: parseFloat(formData.get('credits')),
      date: formData.get('date'),
      category: formData.get('category'),
      sourceUrl: formData.get('url'),
    };

    // Get settings from storage
    const { apiUrl = 'http://localhost:8088', userId = '' } =
      await chrome.storage.sync.get(['apiUrl', 'userId']);

    if (!userId) {
      showToast('⚠ Set your User ID in extension settings', 'error');
      return;
    }

    const saveBtn = form.querySelector('.breathe-ceu-btn-save');
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving…';

    try {
      const response = await fetch(`${apiUrl}/api/users/${userId}/ceus`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(ceuData),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${await response.text()}`);
      }

      const result = await response.json();
      const credits = ceuData.credits || result.credits || '';
      showToast(`✓ ${credits} CEUs logged to Breathe`);

      if (popupForm) { popupForm.remove(); popupForm = null; }
    } catch (err) {
      console.error('[Breathe] CEU submit error:', err);
      showToast(`✗ Failed: ${err.message}`, 'error');
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save to Breathe';
    }
  }

  // ─── Main detection flow ──────────────────────────────────────────────

  function runDetection() {
    // Don't run on extension pages or chrome pages
    if (window.location.protocol === 'chrome:' || window.location.protocol === 'chrome-extension:') {
      return;
    }

    const result = detectCertificate();
    if (result.detected) {
      console.log('[Breathe] CEU certificate detected:', result.reasons);
      createFloatingButton();
    }
  }

  // Run detection after a short delay to let the page fully render
  setTimeout(runDetection, 1500);

  // Re-run on URL changes (SPA support)
  let lastUrl = window.location.href;
  const urlObserver = new MutationObserver(() => {
    if (window.location.href !== lastUrl) {
      lastUrl = window.location.href;
      removeFloatingButton();
      setTimeout(runDetection, 1500);
    }
  });
  urlObserver.observe(document.body, { childList: true, subtree: true });

  // Listen for manual trigger from background/popup
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.action === 'triggerCEUDetection') {
      const data = extractPageData();
      sendResponse({ detected: true, data });
      showCeuForm();
      return true;
    }
    if (msg.action === 'getPageData') {
      const data = extractPageData();
      const detection = detectCertificate();
      sendResponse({ data, detection });
      return true;
    }
  });
})();