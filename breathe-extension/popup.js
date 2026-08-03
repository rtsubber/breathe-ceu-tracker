// popup.js — Breathe CEU Tracker popup logic

document.addEventListener('DOMContentLoaded', () => {
  const apiUrlInput = document.getElementById('api-url');
  const userIdInput = document.getElementById('user-id');
  const saveBtn = document.getElementById('save-settings');
  const savedNote = document.getElementById('saved-note');
  const detectBtn = document.getElementById('detect-now');
  const statusText = document.getElementById('status-text');
  const statusDot = document.getElementById('status-dot');
  const progressContent = document.getElementById('progress-content');

  // ─── Load saved settings ───
  chrome.storage.sync.get(['apiUrl', 'userId'], (data) => {
    apiUrlInput.value = data.apiUrl || 'http://localhost:8088';
    userIdInput.value = data.userId || '';
    refreshStatus();
  });

  // ─── Save settings ───
  saveBtn.addEventListener('click', () => {
    const apiUrl = apiUrlInput.value.trim().replace(/\/$/, '');
    const userId = userIdInput.value.trim();
    chrome.storage.sync.set({ apiUrl, userId }, () => {
      savedNote.classList.add('show');
      setTimeout(() => savedNote.classList.remove('show'), 2000);
      refreshStatus();
    });
  });

  // ─── Detect CEU on current page ───
  detectBtn.addEventListener('click', () => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs[0]) return;
      chrome.tabs.sendMessage(tabs[0].id, { action: 'triggerCEUDetection' }, (response) => {
        // Content script handles showing the form; close popup
        window.close();
      });
    });
  });

  // ─── Refresh status & progress ───
  async function refreshStatus() {
    const apiUrl = apiUrlInput.value.trim().replace(/\/$/, '');
    const userId = userIdInput.value.trim();

    if (!userId) {
      statusText.textContent = 'Not connected — set User ID';
      statusDot.classList.add('disconnected');
      progressContent.innerHTML = '<div class="progress-loading">Enter your User ID in settings</div>';
      return;
    }

    try {
      // Check API health
      const healthResp = await fetch(`${apiUrl}/api/health`, { method: 'GET' });
      if (!healthResp.ok) throw new Error('API unreachable');
      statusDot.classList.remove('disconnected');
      statusText.textContent = 'Connected';

      // Fetch user info
      const userResp = await fetch(`${apiUrl}/api/users/${userId}`);
      if (!userResp.ok) throw new Error('User not found');
      const user = await userResp.json();
      const userName = user.name || user.email || 'User';
      statusText.textContent = `Connected as ${userName}`;

      // Fetch CEU progress
      await fetchCEUProgress(apiUrl, userId);
    } catch (err) {
      statusDot.classList.add('disconnected');
      statusText.textContent = 'Not connected';
      progressContent.innerHTML = `<div class="progress-error">⚠ ${err.message}</div>`;
    }
  }

  async function fetchCEUProgress(apiUrl, userId) {
    try {
      const resp = await fetch(`${apiUrl}/api/users/${userId}/ceus/progress`);
      if (!resp.ok) throw new Error('Failed to load progress');
      const data = await resp.json();

      const completed = data.completed_credits || data.completed || 0;
      const required = data.required_credits || data.required || 30;
      const cycleEnd = data.cycle_end_date || data.cycle_end || '';
      const percent = Math.min(100, Math.round((completed / required) * 100));

      const cycleInfo = cycleEnd ? `<span>Cycle ends: <strong>${formatDate(cycleEnd)}</strong></span>` : '';

      progressContent.innerHTML = `
        <div class="progress-bar">
          <div class="progress-fill" style="width: ${percent}%"></div>
        </div>
        <div class="progress-text">
          <span><strong>${completed}</strong> / ${required} CEUs</span>
          ${cycleInfo}
        </div>
      `;
    } catch (err) {
      // Fallback: try fetching all CEUs and summing
      try {
        const resp = await fetch(`${apiUrl}/api/users/${userId}/ceus`);
        if (!resp.ok) throw err;
        const ceus = await resp.json();
        const total = Array.isArray(ceus) ? ceus.reduce((sum, c) => sum + (c.credits || 0), 0) : 0;

        progressContent.innerHTML = `
          <div class="progress-bar">
            <div class="progress-fill" style="width: ${Math.min(100, (total / 30) * 100)}%"></div>
          </div>
          <div class="progress-text">
            <span><strong>${total}</strong> CEUs logged</span>
            <span>Goal: 30</span>
          </div>
        `;
      } catch (err2) {
        progressContent.innerHTML = `<div class="progress-error">⚠ Could not load progress</div>`;
      }
    }
  }

  function formatDate(dateStr) {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch {
      return dateStr;
    }
  }
});