# Breathe 🫁

> Your career, organized.

A CEU tracker built by an RRT, for RTs. Free for individual respiratory therapists. Pro is $25/year flat.

**Live at:** [breathe.sublettlabs.com](https://breathe.sublettlabs.com)

## Why Breathe?

Starting September 1, 2026, TMB (Texas Medical Board) requires digital CE verification through CE Broker for license renewal (SB 912). CE Broker charges $29-99/year for a paid tier with a web interface from 2008.

Breathe makes it painless — track your CEUs with OCR, auto-import from AARC, and (coming soon) auto-sync to CE Broker so you never have to manually type anything again.

## Features

### Free
- ✅ Manual CEU entry
- ✅ Certificate photo upload
- ✅ Progress tracking (state license + NBRC CMP)
- ✅ TMB report generation (PDF)
- ✅ Email renewal reminders
- ✅ Free CEU course alerts (AARC, A&T Lectures, Medline, Passy-Muir, etc.)
- ✅ License lookup (type your name → auto-fill from TMB)
- ✅ NBRC credential tracking (5-year CMP cycle)
- ✅ Competency tracking (annual + unit-specific)
- ✅ Multi-state license support

### Pro ($25/year flat)
- ✅ Certificate OCR (snap photo → AI extracts everything)
- ✅ Email forwarding (auto-parse CEU emails from 13+ providers)
- ✅ AARC auto-import
- ✅ CE Broker auto-sync (coming soon)
- ✅ SMS reminders
- ✅ Chrome extension (coming soon)

### Department ($99/month, up to 25 RTs)
- ✅ Everything in Pro for each team member
- ✅ Manager dashboard
- ✅ Team competency tracking
- ✅ Compliance reports
- ✅ Bulk CEU import
- ✅ CE Broker auto-sync for all staff

## Tech Stack

- **Frontend:** Next.js 14, React, Tailwind CSS
- **Backend:** FastAPI (Python), SQLite
- **Auth:** JWT (HS256, 30-day tokens), bcrypt password hashing
- **OCR:** easyocr + Claude API (hybrid)
- **Payments:** Stripe (checkout sessions, webhooks)
- **Infrastructure:** Cloudflare Tunnel, systemd services
- **Browser Automation:** Playwright (TikTok uploader, CE Broker sync)

## Project Structure

```
ceu-tracker/
├── breathe-api/           # FastAPI backend
│   ├── main.py            # API endpoints (auth, CEUs, credentials, NBRC, billing, etc.)
│   ├── auth.py            # JWT auth, password hashing
│   ├── database.py        # SQLAlchemy models (User, License, CEU, Credential, etc.)
│   ├── ocr.py             # Certificate OCR (easyocr + Claude API)
│   ├── tmb_report.py      # TMB PDF report generation (WeasyPrint)
│   ├── license_lookup.py  # TMB + Indiana PLA license scraping
│   ├── free_ceu_scanner.py # Curated free CEU course list
│   ├── nbrc_tracker.py    # NBRC CMP 5-year cycle calculator
│   ├── aarc_import.py     # AARC Learning Network scraper
│   ├── email_parser.py    # CEU email parsing (13+ providers)
│   └── email_webhook.py   # Inbound email webhook handler
├── breathe-frontend/      # Next.js frontend
│   └── src/
│       ├── app/           # Pages (dashboard, onboarding, login, register, etc.)
│       ├── components/    # Reusable components (auth-gate, bottom-nav, etc.)
│       └── lib/           # API client, auth context, utilities
├── breathe-signup/        # Landing page (static HTML)
├── breathe-extension/     # Chrome extension (Manifest V3, coming soon)
├── research/              # Competitor analysis, TMB open records research
└── docs/                  # Product spec, CEU requirements by state
```

## Getting Started

### Prerequisites
- Python 3.12+
- Node.js 22+
- SQLite

### Backend Setup
```bash
cd breathe-api
pip install fastapi uvicorn sqlalchemy pydantic python-jose passlib[bcrypt] pyjwt easyocr anthropic weasyprint requests beautifulsoup4
export JWT_SECRET="your-secret-key-here"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8088
```

### Frontend Setup
```bash
cd breathe-frontend
npm install
npx next build
npx next start --port 3000
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `JWT_SECRET` | Yes | Secret key for JWT token signing |
| `STRIPE_SECRET_KEY` | No | Stripe API key for payments |
| `STRIPE_WEBHOOK_SECRET` | No | Stripe webhook verification |
| `STRIPE_PRICE_PRO_MONTHLY` | No | Stripe price ID for Pro monthly |
| `STRIPE_PRICE_PRO_YEARLY` | No | Stripe price ID for Pro yearly |
| `STRIPE_PRICE_DEPT_MONTHLY` | No | Stripe price ID for Department monthly |

## Supported States

All 50 US states + DC have RT CEU requirements seeded in the database. License lookup (auto-fill from state board) is currently supported for:
- **Texas** (TMB — Texas Medical Board)
- **Indiana** (PLA — Professional Licensing Agency)

More states being added.

## CEU Requirements

Texas RT requirements (22 TAC §187.16):
- 24 CE hours per 2-year biennial period
- ≥12 hours must be traditional (live instruction)
- ≥2 hours ethics (including 1 hr human trafficking prevention)
- No carryover between periods
- License expires May 31 or November 30

## Security

- bcrypt password hashing (per-password salt)
- JWT tokens (HS256, 30-day expiry)
- All user data endpoints require authentication
- User data isolation — users can only access their own data
- Rate limiting (60 req/min general, 10 req/min OCR)
- API docs disabled in production (no Swagger/ReDoc/OpenAPI exposure)
- CORS restricted to known origins

## Built By

**Ron Sublett, RRT-NPS** — Respiratory Therapist in the NICU at Driscoll Children's Hospital, Corpus Christi, TX. Victoria College RT program graduate.

## License

Proprietary. © 2026 Sublett Labs. All rights reserved.

## Links

- **Landing page:** [breathe.sublettlabs.com](https://breathe.sublettlabs.com)
- **App:** [app.breathe.sublettlabs.com](https://app.breathe.sublettlabs.com) (propagating — use [breathe.brandbooststudio.co](https://breathe.brandbooststudio.co) temporarily)
- **Company:** [sublettlabs.com](https://sublettlabs.com)

---

*Not affiliated with TMB, CE Broker, AARC, or NBRC.*