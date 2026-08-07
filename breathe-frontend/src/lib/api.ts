/**
 * Breathe API client — talks to the real FastAPI backend.
 * Auth token is automatically injected from localStorage.
 */

const API_BASE = "";

// ─── Types (mirror backend Pydantic schemas) ───────────────────

export type SubscriptionTier = "free" | "pro" | "department";
export type SubscriptionStatus = "active" | "canceled" | "past_due" | "trialing";

export type User = {
  id: number;
  name: string;
  email: string;
  created_at: string;
  subscription_tier: SubscriptionTier;
  subscription_status: SubscriptionStatus;
};

export type Subscription = {
  tier: SubscriptionTier;
  status: SubscriptionStatus;
  stripe_customer_id: string | null;
  subscription_expires: string | null;
};

export type FreeCourseAlert = {
  id: number;
  user_id: number;
  course_title: string;
  provider: string;
  credits: number;
  url: string | null;
  source: string;
  alert_date: string;
  sent: boolean;
};

export type License = {
  id: number;
  user_id: number;
  state: string;
  license_type: string;
  license_number: string;
  issue_date: string | null;
  expiry_date: string;
  cycle_years: number;
  required_ceus: number;
};

export type CEU = {
  id: number;
  user_id: number;
  title: string;
  provider: string;
  credits: number;
  completion_date: string;
  category: string;
  certificate_path: string | null;
  created_at: string;
  ocr_confidence: number;
  cebroker_synced: boolean;
  cebroker_synced_at: string | null;
};

export type CEUCreateInput = {
  title: string;
  provider: string;
  credits: number;
  completion_date: string; // ISO date
  category?: string;
  certificate_path?: string | null;
  ocr_confidence?: number;
};

export type Credential = {
  id: number;
  user_id: number;
  type: string;
  expiry_date: string;
  cycle_years: number;
  issuing_org: string;
};

export type Competency = {
  id: number;
  user_id: number;
  name: string;
  category: string; // "annual" | "unit_specific"
  frequency: string;
  status: string; // "pending" | "completed" | "overdue"
  completed_date: string | null;
  evaluator: string | null;
  notes: string | null;
};

export type Progress = {
  user_id: number;
  total_earned: number;
  required: number;
  remaining: number;
  on_track: boolean;
  days_to_renewal: number;
  cycle_years: number;
  expiry_date: string | null;
  percent_complete: number;
};

export type StateRequirement = {
  id: number;
  state: string;
  profession: string;
  required_ceus: number;
  cycle_years: number;
  mandatory_topics: string[] | null;
  board_name?: string | null;
};

export type OCRResult = {
  title: string;
  provider: string;
  credits: number;
  completion_date: string;
  confidence: number;
  raw_text: string;
  certificate_path: string;
};

// ─── Internal fetch helper ──────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("breathe_token") : null;
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
  });
  if (res.status === 401) {
    // Redirect to login
    if (typeof window !== "undefined") {
      localStorage.removeItem("breathe_token");
      localStorage.removeItem("breathe_user");
      window.location.href = "/login";
    }
    throw new Error("Session expired. Please login again.");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore parse error */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// ─── Auth API functions ─────────────────────────────────────────

/** Export apiFetch for direct use in components that need it (e.g. onboarding). */
export { apiFetch };

export async function loginApi(
  email: string,
  password: string,
): Promise<{ user: User; token: string }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Login failed");
  }
  return res.json();
}

export async function registerApi(
  name: string,
  email: string,
  password: string,
): Promise<{ user: User; token: string }> {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Registration failed");
  }
  return res.json();
}

// ─── Public API functions (all auth-based, no user_id) ─────────

export function getUser(): Promise<User> {
  return apiFetch<User>(`/api/me`);
}

export function getLicenses(): Promise<License[]> {
  return apiFetch<License[]>(`/api/licenses`);
}

export function getCEUs(): Promise<CEU[]> {
  return apiFetch<CEU[]>(`/api/ceus`);
}

export function addCEU(data: CEUCreateInput): Promise<CEU> {
  return apiFetch<CEU>(`/api/ceus`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function deleteCEU(ceuId: number): Promise<void> {
  return apiFetch<void>(`/api/ceus/${ceuId}`, {
    method: "DELETE",
  }).then(() => undefined);
}

export function getCredentials(): Promise<Credential[]> {
  return apiFetch<Credential[]>(`/api/credentials`);
}

export function getCompetencies(): Promise<Competency[]> {
  return apiFetch<Competency[]>(`/api/competencies`);
}

export function addCompetency(
  data: Omit<Competency, "id" | "user_id">,
): Promise<Competency> {
  return apiFetch<Competency>(`/api/competencies`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function getProgress(): Promise<Progress> {
  return apiFetch<Progress>(`/api/progress`);
}

export function getStates(): Promise<StateRequirement[]> {
  return apiFetch<StateRequirement[]>(`/api/states`);
}

export async function uploadCertificateOCR(file: File): Promise<OCRResult> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("breathe_token") : null;
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/ceus/ocr`, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: form,
  });
  if (!res.ok) {
    let detail = `OCR upload failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<OCRResult>;
}

// ─── Convenience helpers ───────────────────────────────────────

/** Returns the primary license (first one) or null. */
export async function getPrimaryLicense(): Promise<License | null> {
  const licenses = await getLicenses();
  return licenses[0] ?? null;
}

/** Returns the board name for a given state code (e.g., "TX" → "Texas Medical Board"). */
export async function getBoardName(stateCode: string): Promise<string> {
  const states = await getStates();
  const match = states.find((s) => s.state === stateCode.toUpperCase());
  return match?.board_name ?? "State Licensing Board";
}

/** Format an ISO date string as e.g. "Mar 5, 2026". */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/** Days from today until an ISO date (negative = past). */
export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((d.getTime() - today.getTime()) / 86_400_000);
}

/** Credential status derived from expiry date. */
export function credStatus(
  iso: string | null | undefined,
): "current" | "expiring" | "expired" {
  const days = daysUntil(iso);
  if (days === null) return "current";
  if (days < 0) return "expired";
  if (days <= 60) return "expiring";
  return "current";
}

// ─── License Lookup (TMB) API ──────────────────────────────────

export type LicenseLookupResult = {
  name: string;
  tmb_name: string | null;
  license_number: string;
  license_type: string;
  license_type_full: string | null;
  status: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  address: string | null;
  city: string | null;
};

export type LicenseLookupResponse = {
  results: LicenseLookupResult[];
  count: number;
};

export function lookupLicense(data: {
  first_name?: string;
  last_name?: string;
  license_number?: string;
  license_type?: string;
  state?: string;
}): Promise<LicenseLookupResponse> {
  return apiFetch<LicenseLookupResponse>("/api/license-lookup", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ─── Billing API ────────────────────────────────────────────────

export function createCheckoutSession(
  tier: "pro" | "department",
  billingCycle: "monthly" | "yearly",
): Promise<{ url: string }> {
  return apiFetch<{ url: string }>("/api/billing/checkout", {
    method: "POST",
    body: JSON.stringify({ tier, billing_cycle: billingCycle }),
  });
}

export function getSubscription(): Promise<Subscription> {
  return apiFetch<Subscription>(`/api/subscription`);
}

export function cancelSubscription(): Promise<{ success: boolean }> {
  return apiFetch<{ success: boolean }>("/api/billing/cancel", {
    method: "POST",
  });
}

// ─── Free Course Alerts API ─────────────────────────────────────

export function getFreeCourseAlerts(): Promise<FreeCourseAlert[]> {
  return apiFetch<FreeCourseAlert[]>(`/api/free-course-alerts`);
}

export function scanFreeCourses(): Promise<FreeCourseAlert[]> {
  return apiFetch<FreeCourseAlert[]>(`/api/free-course-alerts/scan`, {
    method: "POST",
  });
}

// ─── Public Free Courses API (no auth needed) ──────────────────

export type FreeCourse = {
  id: number;
  title: string;
  provider: string;
  credits: number;
  url: string | null;
  source: string;
  alert_date: string;
};

export type FreeCoursesResponse = {
  courses: FreeCourse[];
  total: number;
  total_credits: number;
};

export type ScanResponse = {
  scanned: number;
  added: number;
  sources_checked: number;
};

export function getFreeCourses(): Promise<FreeCoursesResponse> {
  return apiFetch<FreeCoursesResponse>(`/api/free-courses`);
}

export function triggerFreeCourseScan(): Promise<ScanResponse> {
  return apiFetch<ScanResponse>(`/api/free-courses/scan`, {
    method: "POST",
  });
}

// ─── Feature Gate Helper ────────────────────────────────────────

export const PRO_FEATURES = {
  ocr: "Certificate OCR",
  email_forwarding: "Email Forwarding",
  aarc_import: "AARC Auto-Import",
  browser_extension: "Browser Extension",
  push_notifications: "Push Notifications",
  nbrc_tracking: "NBRC Credential Tracking",
  multi_state: "Multi-State Support",
  sms_reminders: "SMS Reminders",
  free_course_alerts: "Free CEU Course Alerts",
} as const;

export function isProFeature(
  tier: SubscriptionTier | undefined,
  _feature: keyof typeof PRO_FEATURES,
): boolean {
  return tier === "pro" || tier === "department";
}

// ─── NBRC CMP Types ─────────────────────────────────────────────

export type NBRCCredential = {
  id: number;
  user_id: number;
  credential_type: string;
  earned_date: string | null;
  cmp_cycle_end: string;
  renewal_method: string;
  is_highest: boolean;
};

export type NBRCAssessment = {
  id: number;
  user_id: number;
  quarter: string;
  score: number | null;
  taken_date: string | null;
  credits_required: number;
};

export type NBRCStatus = {
  has_nbrc: boolean;
  credentials: { type: string; earned_date: string | null; is_highest: boolean }[];
  cycle_start: string | null;
  cycle_end: string | null;
  cycle_years: number | null;
  days_remaining: number | null;
  progress_pct: number | null;
  assessments: { quarter: string; score: number | null; taken: boolean }[];
  ce_required: number | null;
  ce_earned: number | null;
  ce_from_state_license: number | null;
  additional_ce_needed: number | null;
  overlap_courses: { title: string; credits: number; date: string; provider: string }[];
  renewal_method: string | null;
  on_track: boolean | null;
};

export type AssessmentReminder = {
  status: string;
  quarter: string;
  score?: number | null;
  message: string;
  next_window: string;
  days_until_next: number;
};

// ─── NBRC CMP API Functions ─────────────────────────────────────

export function getNBRCStatus(): Promise<NBRCStatus> {
  return apiFetch<NBRCStatus>(`/api/nbrc/status`);
}

export function addNBRCCredential(
  data: Omit<NBRCCredential, "id" | "user_id">,
): Promise<NBRCCredential> {
  return apiFetch<NBRCCredential>(`/api/nbrc/credentials`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function listNBRCCredentials(): Promise<NBRCCredential[]> {
  return apiFetch<NBRCCredential[]>(`/api/nbrc/credentials`);
}

export function logAssessment(
  data: { quarter: string; score?: number; taken_date?: string },
): Promise<NBRCAssessment> {
  return apiFetch<NBRCAssessment>(`/api/nbrc/assessments`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function getAssessmentReminder(): Promise<AssessmentReminder> {
  return apiFetch<AssessmentReminder>(`/api/nbrc/assessment-reminder`);
}

// ─── Email Alias API ───────────────────────────────────────────

export type EmailAliasInfo = {
  aliases: { id: number; email_alias: string }[];
  forwarding_address: string | null;
  instructions: string;
};

export function getEmailAlias(): Promise<EmailAliasInfo> {
  return apiFetch<EmailAliasInfo>(`/api/me/email-alias`);
}

// ─── CE Broker Sync API ────────────────────────────────────────

export type CEBrokerSyncResult = {
  synced: number;
  failed: number;
  errors: string[];
  details: { title: string; status: "synced" | "failed"; message: string }[];
  message?: string;
};

export type CEBrokerStatus = {
  total_ceus: number;
  synced: number;
  unsynced: number;
  all_synced: boolean;
};

export function syncToCEBroker(): Promise<CEBrokerSyncResult> {
  return apiFetch<CEBrokerSyncResult>(`/api/cebroker/sync`, {
    method: "POST",
  });
}

export function getCEBrokerStatus(): Promise<CEBrokerStatus> {
  return apiFetch<CEBrokerStatus>(`/api/cebroker/status`);
}