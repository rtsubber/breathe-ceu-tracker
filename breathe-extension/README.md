# Breathe — CEU Tracker (Chrome Extension)

A Chrome browser extension (Manifest V3) that auto-detects CEU certificates on web pages and offers one-click logging to the Breathe API.

## Features

- **Auto-detection** — Scans pages for CEU certificates (PDF links, certificate images, CEU text, print buttons)
- **Floating button** — Shows a "Log to Breathe" button when a certificate is detected
- **One-click logging** — Extracts course title, provider, credits, date, and category automatically
- **Pre-filled form** — Review and edit before saving
- **Popup dashboard** — View CEU progress, connection status, and settings
- **Toast notifications** — Green success / red error feedback

## Installation (Load Unpacked)

1. Open Chrome (or any Chromium browser: Edge, Brave, etc.)
2. Navigate to `chrome://extensions`
3. Toggle **Developer mode** on (top-right corner)
4. Click **Load unpacked**
5. Select the `breathe-extension` folder (this directory)
6. The Breathe lung icon should appear in your toolbar

## Configuration

1. Click the extension icon in your toolbar
2. In **Settings**:
   - **API URL**: `http://localhost:8088` (default)
   - **User ID**: Enter your Breathe user ID
3. Click **Save Settings**
4. The popup should show "Connected as [your name]" and your CEU progress

## How It Works

### Automatic Detection
The content script runs on every page after it loads (`document_idle`). It looks for:

| Signal | Score |
|--------|-------|
| PDF link with "certificate" in URL/text | +3 |
| Certificate image (alt/src contains "certificate") | +2 |
| CEU / continuing education / contact hours text | +2 |
| URL contains "certificate" | +2 |
| Print button on page | +1 |

If the total score is ≥ 2, the floating "Log to Breathe" button appears in the bottom-right corner.

### One-Click Logging
1. Click the floating button (or use "Detect CEU on This Page" in the popup)
2. A modal opens with a pre-filled form:
   - **Course Title** — from page `<title>` or `<h1>`
   - **Provider** — from `og:site_name` or domain
   - **Credits** — extracted via regex ("4 CEUs", "4 contact hours", "4 credits", etc.)
   - **Completion Date** — extracted from page text or defaults to today
   - **Category** — auto-suggested based on page content keywords
3. Review and edit as needed
4. Click **Save to Breathe**
5. A toast notification confirms: `✓ [X] CEUs logged to Breathe`

### Manual Trigger
You can also click the extension icon and use **Detect CEU on This Page** to trigger detection manually on any page.

## File Structure

```
breathe-extension/
├── manifest.json     — Extension manifest (V3)
├── content.js        — Content script (page detection + UI)
├── styles.css        — Floating button & modal styles
├── popup.html        — Extension popup dashboard
├── popup.js          — Popup logic (status, progress, settings)
├── background.js     — Service worker
├── icons/
│   ├── icon16.png    — 16×16 toolbar icon
│   ├── icon48.png    — 48×48 toolbar icon
│   └── icon128.png   — 128×128 store icon
└── README.md         — This file
```

## API Endpoints Used

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET`  | `/api/health` | Connection check |
| `GET`  | `/api/users/{id}` | Get user info |
| `GET`  | `/api/users/{id}/ceus/progress` | CEU progress |
| `GET`  | `/api/users/{id}/ceus` | List all CEUs (fallback) |
| `POST` | `/api/users/{id}/ceus` | Log a new CEU |

## Design

- **Primary color**: `#2563EB` (blue)
- **Accent color**: `#7C3AED` (purple)
- **Success**: `#059669` (green)
- **Error**: `#DC2626` (red)
- **Font**: Inter (from Google Fonts)

## Troubleshooting

- **Floating button not appearing**: The page might not have enough CEU indicators. Use "Detect CEU on This Page" in the popup to force it.
- **"Not connected" status**: Make sure the Breathe API is running at `http://localhost:8088` and your User ID is set in settings.
- **Credits not auto-filled**: Select text on the page containing the credit info (e.g. "4 CEUs") before clicking the button.
- **Toast not showing**: The page might have aggressive CSP policies. Try a different page.

## Privacy

- The extension only sends data to your configured Breathe API URL (default: `localhost:8088`)
- No data is sent to any external servers
- Page content is processed locally in the browser