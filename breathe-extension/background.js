// background.js — Breathe CEU Tracker service worker

// Listen for installation
chrome.runtime.onInstalled.addListener(() => {
  console.log('[Breathe] Extension installed');

  // Set default settings
  chrome.storage.sync.get(['apiUrl', 'userId'], (data) => {
    if (!data.apiUrl) {
      chrome.storage.sync.set({ apiUrl: 'http://localhost:8088' });
    }
  });
});

// Handle extension action click when no popup (shouldn't happen with popup set,
// but this is a fallback for keyboard shortcuts)
chrome.action.onClicked.addListener((tab) => {
  // Popup handles this; nothing to do
});

// Listen for messages from content scripts
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'logCEU') {
    // Forward to storage or API as needed
    console.log('[Breathe] CEU logged:', msg.data);
    sendResponse({ success: true });
  }
  return true;
});