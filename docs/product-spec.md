# Product Spec — RT CEU + Competency Tracker
## Codename: "Breathe"

> "CE Tracker charges you to do the work yourself. We do it for you, for free."

---

## PRODUCT OVERVIEW

**Name:** Breathe (working title — see name options below)
**Tagline:** Your career, organized.
**Target:** 150K-170K licensed RTs in the US, starting with Texas (~20K RTs)
**Platform:** Mobile-first (iOS + Android via React Native/Expo), web dashboard secondary
**Price:** Free for individuals. $149-499/mo for department/team plans.
**Ship target:** 4-6 weeks to MVP

---

## UX PRINCIPLES

### What makes this different from every other healthcare compliance tool:

1. **Compliance shouldn't feel like paperwork.** Every other tool in this space looks like a tax form. Breathe feels like a consumer app — think Linear, Notion, Stripe. Clean, fast, satisfying.

2. **Zero manual data entry.** The #1 complaint about CE Tracker is manually typing everything. Breathe's default is: snap a photo, we extract everything. Type nothing.

3. **Calm, not anxious.** Compliance tools use red warnings and alarmist language. Breathe uses calm, clear status. You're on track. You need 6 more hours. Here's how to get them. No panic.

4. **One number that matters.** The dashboard shows one thing first: are you on track for renewal? Everything else is secondary. CE Tracker buries this. We lead with it.

5. **Feel fast.** Every interaction under 300ms. No loading spinners on common actions. Optimistic updates. The app should feel instant.

6. **Respect the user.** RTs are smart clinicians working 12-hour shifts. Don't condescend. Don't add unnecessary steps. Don't make them confirm obvious things. Just help them get it done.

---

## DESIGN SYSTEM

### Color Palette

```
Primary:       #2563EB (Blue 600) — trust, clinical, calm
Primary Dark:  #1D4ED8 (Blue 700)
Accent:        #7C3AED (Violet 600) — energy, progress, CTAs
Accent Light:  #A78BFA (Violet 400)

Success:       #10B981 (Emerald 500)
Warning:       #F59E0B (Amber 500)
Danger:        #EF4444 (Red 500) — used sparingly, only for true emergencies

Background:    #FAFAFA (Gray 50) — warm, not clinical white
Surface:       #FFFFFF (White)
Surface Dark:  #18181B (Gray 950) — dark mode

Text Primary:  #18181B (Gray 950)
Text Secondary: #71717A (Gray 500)
Text Muted:    #A1A1AA (Gray 400)

Border:        #E4E4E7 (Gray 200)
Border Focus:  #2563EB (Blue 600)
```

### Typography

```
Display:    Inter, 28px/700, letter-spacing -0.5px
H1:         Inter, 24px/700, letter-spacing -0.3px
H2:         Inter, 20px/600
H3:         Inter, 17px/600
Body:       Inter, 16px/400
Body Small:  Inter, 14px/400
Caption:    Inter, 13px/400, Gray 500
Label:      Inter, 12px/500, uppercase, letter-spacing 0.5px

Mono:       JetBrains Mono (for CEU numbers, license IDs)
```

### Spacing & Layout

```
Base unit:   4px
Spacing:     4, 8, 12, 16, 20, 24, 32, 40, 48, 64
Card radius: 16px
Button radius: 12px
Input radius: 12px
Shadow:      0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)
Shadow LG:   0 8px 24px rgba(0,0,0,0.12)

Mobile padding: 20px horizontal
Max content width: 640px (mobile), 1024px (web dashboard)
```

### Components

- **Buttons:** Primary (filled blue), Secondary (outline), Ghost (text only). 52px height on mobile, 44px on web. Rounded 12px.
- **Cards:** White surface, 16px radius, subtle shadow. No borders unless interactive.
- **Inputs:** 12px radius, 52px height on mobile. Label floats above. Focus state = blue ring, no border change.
- **Progress:** Circular progress ring for CEU completion. Linear progress bar for individual courses.
- **Lists:** Swipe to edit/delete. Long-press for quick actions.
- **Empty states:** Friendly illustrations + clear CTA. Never just "No data."
- **Notifications:** In-app toast (top), push notifications (scheduled), email (weekly digest)

---

## APP FLOWS

### Flow 0: Splash / Launch

```
2-second splash → biometric auth check → Dashboard (returning) or Onboarding (new)

Logo: Minimalist lungs formed from two curved lines, right side slightly
higher (like inhalation). Clean, medical-adjacent but not clinical.
Could also work as stylized "B" breath mark.
```

### Flow 1: Onboarding (First 60 Seconds)

**Screen 1.1 — Welcome**
```
[Illustration: RT in scrubs, phone in hand, confident]
"Your career, organized."
"CEUs, credentials, and competencies — all in one place. Free, forever."
[Get Started] →
[Already have an account? Sign in]
```

**Screen 1.2 — Account Creation**
```
"Let's set you up"
"Takes about 60 seconds."

Inputs:
- Full Name
- Email
- Password (or Apple/Google sign-in)

→ Continue
```

**Screen 1.3 — License Info**
```
"Tell us about your license"

Inputs:
- State (dropdown, default: Texas)
- License Type (RT / RRT / CRT / Other)
- License Number (optional, can add later)
- License Expiry Date (date picker)

Smart default: If state = Texas, pre-fill renewal cycle = 2 years, CEU requirement = 30

→ Finish
```

**Screen 1.4 — Dashboard (First Visit)**
```
Empty state with personality:

"Welcome, [Name]! 👋"
"You need 30 CEUs by [expiry date]."
"You have 0 so far. Let's change that."

[Add your first CEU] → opens camera for certificate OCR
[Browse CE courses] → opens AARC course directory
```

### Flow 2: Logging a CEU (The Core Action)

**This is the most important flow in the app. It must be effortless.**

**Method A — Certificate OCR (preferred path):**
```
1. Tap [+] on dashboard
2. Camera opens immediately
3. Snap photo of certificate
4. Processing indicator (1-2 seconds)
5. Auto-extracted data appears:
   - Course Title: "Mechanical Ventilation Essentials"
   - Provider: "AARC"
   - Credits: 4.0
   - Completion Date: 2026-07-15
   - Category: Clinical
6. User reviews/edits (most fields correct, tap done)
7. "✓ Saved. 4 CEUs added. 26 to go."
8. Dashboard updates instantly

Total time: ~15 seconds
```

**Method B — Manual Entry (fallback):**
```
1. Tap [+] on dashboard
2. Tap "Enter manually"
3. Form appears:
   - Course Title
   - Provider
   - Credits
   - Completion Date
   - Category (auto-suggested based on title)
   - Certificate Photo (optional)
4. Save
5. "✓ Saved. [X] CEUs added. [Y] to go."
```

**Method C — Import from AARC (future):**
```
1. Tap [+] on dashboard
2. Tap "Import from AARC"
3. Sign in to AARC Learning Network
4. Auto-import all completed courses
5. Review and confirm
```

### Flow 3: Dashboard (Home Screen)

```
┌─────────────────────────────┐
│  👋 Hi, Ron                  │
│  RRT · Texas · Expires 03/27 │
│                              │
│  ╭────────────────────────╮  │
│  │   24 / 30              │  │ ← Circular progress ring
│  │   CEUs complete        │  │
│  │   6 to go · 8 months   │  │
│  ╰────────────────────────╯  │
│                              │
│  On track ✓                  │ ← Calm status, not anxious
│                              │
│  ─── Recent Activity ───     │
│  📜 Mechanical Ventilation   │
│     4 CEUs · Jul 15 · AARC   │
│                              │
│  📜 Neonatal Resuscitation   │
│     2 CEUs · Jul 10 · NRP    │
│                              │
│  ─── Credentials ───         │
│  RRT — Renews Dec 2027 ✓    │
│  NPS — Renews Mar 2027 ✓    │
│  ACLS — Renews Jan 2027 ⚠   │ ← Amber if <90 days
│                              │
│  ─── Quick Actions ───       │
│  [+] Add CEU                 │
│  [📋] Generate TMB Report    │
│  [👁] View All CEUs           │
│                              │
└─────────────────────────────┘

Bottom Nav:
[Home] [CEUs] [Credentials] [Profile]
```

### Flow 4: CEU List View

```
Filter bar: All | This Period | By Category
Sort: Recent first

Each row:
- Course title (bold)
- Provider · Credits · Date
- Category badge (color-coded)
- Swipe left → Edit
- Swipe right → Delete (with confirm)

Tap row → Detail view:
- Full course info
- Certificate image
- Category
- Verified status
- Edit button
```

### Flow 5: TMB Submission (Killer Feature)

```
1. Tap "Generate TMB Report" on dashboard
2. App checks: Are all required CEUs logged?
3. Generates submission packet:
   - CEU log (formatted per TMB requirements)
   - Certificate PDFs (all attached)
   - Cover sheet with license info
4. Preview screen:
   "Your TMB renewal packet is ready"
   - 30 CEUs logged
   - All certificates attached
   - Renewal date: March 31, 2027
5. Two options:
   [Download PDF] — for paper/mail submission
   [Open TMB Portal] — deep link to TMB online portal
6. If TMB Portal selected:
   - Opens TMB website in in-app browser
   - Pre-fills as many fields as possible
   - User reviews and submits
7. Confirmation:
   "✓ Packet generated. Don't forget to submit before March 31."
   [Set reminder] — adds to calendar + push notification
```

### Flow 6: Credentials (NBRC + Certifications)

```
Separate from state CEUs — tracks national credentials:

┌─────────────────────────────┐
│  Credentials                 │
│                              │
│  ─── NBRC ───                │
│  RRT                         │
│  Expires: Dec 2027 · 3yr cycle│
│  Status: On track ✓          │
│  [View renewal requirements] │
│                              │
│  CRT (if applicable)          │
│  NPS                         │
│  Expires: Mar 2027           │
│  [Log CEUs toward renewal]   │
│                              │
│  ─── Certifications ───      │
│  ACLS — Jan 2027 ⚠ 89 days  │
│  BLS — Mar 2027 ✓           │
│  PALS — May 2027 ✓          │
│  NRP — Aug 2027 ✓           │
│                              │
│  [+ Add Credential]          │
└─────────────────────────────┘

Warning colors:
- > 90 days: Green ✓
- 60-90 days: Amber ⚠
- < 60 days: Red (but calm, not alarmist)
```

### Flow 7: Multi-State Support

```
Settings → My Licenses

- Texas (Primary) — 30 CEUs / 2yr — Expires 03/27
- Florida (Secondary) — 24 CEUs / 2yr — Expires 06/27
- [+ Add State License]

Each state tracks independently.
Dashboard shows primary state by default.
Switch between states with dropdown.

"Smart credits" feature: If a CEU counts toward multiple states,
it appears in both trackers automatically. No double-entry.
```

### Flow 8: Competency Tracking (Bonus Feature)

```
Separate tab — "Competencies"

For tracking annual skills, unit-specific checkoffs:

┌─────────────────────────────┐
│  Competencies                │
│                              │
│  ─── Annual (2026) ───       │
│  ✅ Ventilator Management    │
│  ✅ HFOV Competency         │
│  ✅ Airway Management        │
│  ⬜ Code Blue Response       │
│  ⬜ Neonatal Resuscitation   │
│                              │
│  ─── Unit-Specific ───      │
│  ✅ NICU Orientation         │
│  ✅ Charge Nurse Skills      │
│  ⬜ Transport Team Training   │
│                              │
│  [+ Add Competency]          │
│  [📋 Generate Report]        │
└─────────────────────────────┘

Manager view (paid tier): team-wide competency status
Individual view (free): personal tracking only
```

---

## MVP BUILD PLAN

### Week 1 — Foundation
- [ ] Project setup (Next.js + FastAPI + Supabase)
- [ ] Database schema (users, licenses, CEUs, credentials, competencies)
- [ ] Auth (Supabase Auth with Apple/Google sign-in)
- [ ] User onboarding flow (3 screens)
- [ ] Basic dashboard (empty state + progress ring)

### Week 2 — Core CEU Logging
- [ ] Manual CEU entry form
- [ ] Certificate photo upload
- [ ] CEU list view with filter/sort
- [ ] Dashboard with live CEU counter
- [ ] State requirement configuration (Texas first)

### Week 3 — Killer Features
- [ ] Certificate OCR (Tesseract or cloud OCR API)
- [ ] TMB report generation (PDF with WeasyPrint)
- [ ] Push notifications (renewal reminders)
- [ ] Email reminders (Resend)

### Week 4 — Credentials & Competencies
- [ ] NBRC credential tracking
- [ ] Certification tracking (ACLS, BLS, PALS, NRP)
- [ ] Competency tracking (annual + unit-specific)
- [ ] Credential expiry warnings

### Week 5 — Polish & Ship
- [ ] Multi-state support
- [ ] Settings screen
- [ ] Profile screen
- [ ] App store screenshots
- [ ] Landing page
- [ ] Beta TestFlight + Play Store internal testing

### Week 6 — Launch
- [ ] App Store + Play Store submission
- [ ] Landing page live
- [ ] Reddit r/respiratorytherapy post
- [ ] LinkedIn outreach to TX RT directors
- [ ] Product Hunt (optional)

### v2 (Post-Launch)
- AARC auto-import
- CE Broker integration
- Department/manager dashboard (paid tier)
- Stripe billing for teams
- Bulk CSV import
- Custom report builder
- Apple Watch complications

---

## NAME OPTIONS

1. **Breathe** — clean, medical-adjacent, calm. "I use Breathe to track my CEUs."
2. **Airway** — RT-specific, clinical, strong. "Log it in Airway."
3. **Credits** — simple, clear, obvious. "I have 24 credits in Credits."
4. **Vital** — healthcare, essential, energetic. "My CEUs are in Vital."
5. **Keeps** — as in "keeps track." Friendly, casual. "It's all in Keeps."

My favorite: **Breathe** — it's what RTs do, it's calm, it's memorable, and it doesn't sound like a compliance tool.

---

## THE PITCH (For landing page / App Store)

**Headline:** Your career, organized.

**Subhead:** CEUs, credentials, and competencies — all in one place. Free, forever.

**Body:**
Breathe is the CEU tracker built for respiratory therapists, by a respiratory therapist. Snap a photo of your certificate — we extract the credits, date, and provider automatically. Track your NBRC credentials, ACLS/BLS/PALS renewals, and unit competencies in the same app. Generate your TMB submission packet with one tap. Free for individual RTs. No spreadsheets. No manual entry. No stress.

**CTA:** Get Breathe Free

---

*Product spec by Jarvis + Claude Sonnet 4.6*
*Saved: 2026-08-02 18:35 CDT*