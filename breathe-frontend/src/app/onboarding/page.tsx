"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/logo";
import { usStates } from "@/lib/mock-data";
import { LicenseLookup } from "@/components/license-lookup";
import type { LicenseLookupResult } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { ChevronRight, ChevronLeft, Calendar, Award, Search, CheckCircle2, BadgeCheck, Eye, EyeOff, Loader2, AlertTriangle } from "lucide-react";
import { useRouter } from "next/navigation";

// If we have a license expiry date, estimate NBRC cycle end.
// NBRC cycle is 5 years. Texas requires NBRC credential to maintain license,
// so the NBRC CMP cycle and license expiry are typically aligned.
function calculateNBRCCycleEnd(licenseExpiryDate: string): string {
  if (!licenseExpiryDate) return "";
  return licenseExpiryDate;
}

export default function OnboardingPage() {
  const router = useRouter();
  const { user, updateUser } = useAuth();
  const [step, setStep] = useState(0);
  const [state, setState] = useState("");
  const [licenseType, setLicenseType] = useState("");
  const [licenseNumber, setLicenseNumber] = useState("");
  const [expiryDate, setExpiryDate] = useState("");
  const [showLicenseLookup, setShowLicenseLookup] = useState(false);
  const [lookupStatus, setLookupStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // NBRC credential state
  const [nbrcType, setNbrcType] = useState(""); // Pre-filled from license type
  const [nbrcRegistryNumber, setNbrcRegistryNumber] = useState("");
  const [nbrcCycleEnd, setNbrcCycleEnd] = useState(""); // Calculated from license expiry
  const [nbrcRenewalMethod, setNbrcRenewalMethod] = useState("assessments");

  // NBRC portal login state
  const [nbrcEmail, setNbrcEmail] = useState("");
  const [nbrcPassword, setNbrcPassword] = useState("");
  const [showNbrcPassword, setShowNbrcPassword] = useState(false);
  const [nbrcScraping, setNbrcScraping] = useState(false);
  const [nbrcScrapeError, setNbrcScrapeError] = useState<string | null>(null);
  const [nbrcScrapeSuccess, setNbrcScrapeSuccess] = useState(false);

  // When expiryDate changes (from TMB lookup or manual entry), estimate NBRC cycle end
  useEffect(() => {
    if (expiryDate) {
      setNbrcCycleEnd(calculateNBRCCycleEnd(expiryDate));
    }
  }, [expiryDate]);

  // Pre-fill NBRC email with the user's account email
  useEffect(() => {
    if (user?.email) setNbrcEmail(user.email);
  }, [user?.email]);

  const handleNbrcScrape = async () => {
    setNbrcScrapeError(null);
    setNbrcScrapeSuccess(false);
    setNbrcScraping(true);
    try {
      const result = await apiFetch<any>("/api/nbrc/scrape", {
        method: "POST",
        body: JSON.stringify({ email: nbrcEmail, password: nbrcPassword }),
      });
      if (result.success) {
        setNbrcScrapeSuccess(true);
        // Auto-fill credential type from scraped data
        if (result.credentials?.length > 0) {
          const highest = result.credentials.find((c: any) => c.type === "RRT") || result.credentials[0];
          setNbrcType(highest.type);
        }
        // Auto-fill cycle end from scraped data
        if (result.credentials?.length > 0) {
          const expires = result.credentials[0].expires; // MM/DD/YYYY
          const parts = expires.split("/");
          if (parts.length === 3) {
            setNbrcCycleEnd(`${parts[2]}-${parts[0]}-${parts[1]}`);
          }
        }
      }
    } catch (err) {
      setNbrcScrapeError(err instanceof Error ? err.message : "Failed to pull NBRC data");
    } finally {
      setNbrcScraping(false);
    }
  };

  // Convert full state name to 2-letter code for API
  const stateNameToCode: Record<string, string> = {
    "Texas": "TX",
    "Indiana": "IN",
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY",
    "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA",
    "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO",
    "Montana": "MT", "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH",
    "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
  };
  // Do NOT default to TX — if no state is selected, stateCode is empty.
  // The TX default caused non-TX users to silently get Texas license data.
  const stateCode = stateNameToCode[state] || "";

  const steps = [
    {
      title: "License Information",
      subtitle: "We'll track your CEUs and renewals",
    },
    {
      title: "NBRC Credential",
      subtitle: "Let's set up your NBRC tracking",
    },
    {
      title: "You're all set! 🎉",
      subtitle: "Welcome to Breathe",
    },
  ];

  const handleFinish = async () => {
    setError(null);
    setSaving(true);
    try {
      // Determine state — use dropdown value, or derive from stateCode
      const finalState = state || (stateCode === "TX" ? "Texas" : "");
      const finalStateCode = stateNameToCode[finalState] || stateCode || "TX";
      
      // Save state license
      if (user && finalState && licenseType) {
        await apiFetch("/api/licenses", {
          method: "POST",
          body: JSON.stringify({
            state: finalStateCode,
            license_type: licenseType,
            license_number: licenseNumber || "PENDING",
            expiry_date: expiryDate || "2027-03-31",
            cycle_years: 2,
            required_ceus: 24,
          }),
        });
      } else {
        console.error("Missing onboarding data:", { finalState, licenseType, licenseNumber });
      }

      // Save NBRC credential (if user entered it)
      if (user && nbrcType && nbrcCycleEnd) {
        await apiFetch("/api/nbrc/credentials", {
          method: "POST",
          body: JSON.stringify({
            credential_type: nbrcType,
            earned_date: null,
            cmp_cycle_end: nbrcCycleEnd,
            renewal_method: nbrcRenewalMethod,
            is_highest: nbrcType === "RRT", // RRT is typically the highest
          }),
        });
      }

      // Mark onboarding as complete — MUST succeed before navigating.
      // Update BOTH localStorage AND the auth context so AuthGate sees
      // onboarding_completed=true immediately on the next route change.
      // Without updating the context, AuthGate reads stale user state
      // and bounces the user back to /onboarding (infinite loop).
      const freshUser = await apiFetch<any>("/api/user/onboarding-complete", { method: "POST" });
      
      if (freshUser) {
        // Update auth context synchronously — this is the critical fix.
        // AuthGate reads from context, not localStorage directly.
        updateUser(freshUser);
      }

      // Small delay to let React context propagate before router.push
      // triggers AuthGuard's useEffect on the /dashboard route.
      await new Promise(resolve => setTimeout(resolve, 100));
      
      router.push("/dashboard");
    } catch (err) {
      // If onboarding-complete fails, do NOT push to dashboard —
      // AuthGate would bounce the user back to /onboarding, creating a loop.
      console.error("Onboarding save failed:", err);
      setError("Failed to save your onboarding data. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  // Split full name into first/last for the license lookup component
  const nameParts = (user?.name || "").trim().split(/\s+/);
  const initialFirstName = nameParts[0] || "";
  const initialLastName = nameParts.slice(1).join(" ") || "";

  return (
    <div className="page-enter min-h-screen flex flex-col">
      {/* Progress dots */}
      <div className="flex gap-2 justify-center pt-8 pb-4">
        {steps.map((_, i) => (
          <span
            key={i}
            className={`h-2 rounded-full transition-all ${
              i === step ? "w-8 bg-primary" : i < step ? "w-2 bg-primary/40" : "w-2 bg-gray-200"
            }`}
          />
        ))}
      </div>

      <div className="flex-1 flex flex-col px-6 pb-8">
        {step === 0 && (
          <div className="flex-1 flex flex-col justify-center space-y-6">
            <div className="text-center space-y-2 mb-4">
              <div className="flex justify-center mb-6">
                <div className="w-16 h-16 rounded-card bg-accent/10 flex items-center justify-center">
                  <Award size={32} className="text-accent" />
                </div>
              </div>
              <h1 className="text-2xl font-bold text-text-primary">{steps[0].title}</h1>
              <p className="text-text-secondary">{steps[0].subtitle}</p>
            </div>

            {/* License lookup section — available for all states */}
            {!showLicenseLookup && (
              <div className="p-3 bg-accent/5 border border-accent/20 rounded-button">
                <button
                  type="button"
                  onClick={() => setShowLicenseLookup(true)}
                  className="w-full flex items-center justify-center gap-2 text-sm font-medium text-accent hover:text-accent/80 transition-colors"
                >
                  <Search size={16} />
                  Look Up My License
                </button>
                <p className="text-xs text-text-secondary text-center mt-1">
                  Auto-fill from state licensing board records
                </p>
              </div>
            )}

            {/* License lookup component */}
            {showLicenseLookup && (
              <div className="p-4 bg-gray-50 rounded-card border border-gray-100 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-text-primary">License Lookup</h3>
                  <button
                    type="button"
                    onClick={() => {
                      setShowLicenseLookup(false);
                      setLookupStatus(null);
                    }}
                    className="text-xs text-text-secondary hover:text-text-primary"
                  >
                    Cancel
                  </button>
                </div>
                <LicenseLookup
                  initialFirstName={initialFirstName}
                  initialLastName={initialLastName}
                  state={stateCode}
                  onSelect={(result: LicenseLookupResult) => {
                    setLicenseNumber(result.license_number);
                    // Always set licenseType from lookup result
                    if (result.license_type === "RCP") {
                      setLicenseType("RRT");
                      setNbrcType("RRT");
                    } else {
                      setLicenseType(result.license_type || "RRT");
                    }
                    // CRITICAL: set state from the current stateCode if not already set
                    if (!state) {
                      setState(stateCode === "TX" ? "Texas" : stateCode);
                    }
                    if (result.expiry_date) {
                      setExpiryDate(result.expiry_date);
                    }
                    setShowLicenseLookup(false);
                    setLookupStatus(
                      `Found: ${result.name} — ${result.license_number} (${result.status || "Status unknown"})`,
                    );
                  }}
                />
              </div>
            )}

            {/* Success message after lookup */}
            {lookupStatus && !showLicenseLookup && (
              <div className="flex items-start gap-2 p-3 bg-green-50 border border-green-200 rounded-button text-sm text-green-700">
                <CheckCircle2 size={16} className="mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="font-medium">License found!</p>
                  <p className="text-xs text-green-600 mt-0.5">{lookupStatus}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setLookupStatus(null)}
                  className="text-green-400 hover:text-green-600 text-xs"
                >
                  ✕
                </button>
              </div>
            )}

            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-text-secondary">State</label>
                <select
                  value={state}
                  onChange={(e) => {
                    setState(e.target.value);
                    setShowLicenseLookup(false);
                    setLookupStatus(null);
                  }}
                  className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary bg-white"
                >
                  <option value="" disabled>Select your state</option>
                  {usStates.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-text-secondary">License Type</label>
                <select
                  value={licenseType}
                  onChange={(e) => {
                    setLicenseType(e.target.value);
                    // Auto-fill NBRC type to match license type
                    setNbrcType(e.target.value);
                  }}
                  className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary bg-white"
                >
                  <option value="" disabled>Select license type</option>
                  <option value="RRT">RRT — Registered Respiratory Therapist</option>
                  <option value="CRT">CRT — Certified Respiratory Therapist</option>
                  <option value="CPFT">CPFT — Certified Pulmonary Function Technologist</option>
                  <option value="RPFT">RPFT — Registered Pulmonary Function Technologist</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-text-secondary">
                  License Number {licenseNumber && <span className="text-accent text-xs">(auto-filled)</span>}
                </label>
                <input
                  type="text"
                  value={licenseNumber}
                  onChange={(e) => setLicenseNumber(e.target.value)}
                  placeholder="RCP00075612"
                  className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary font-mono text-sm"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-text-secondary">
                  License Expiry Date {expiryDate && <span className="text-accent text-xs">(auto-filled)</span>}
                </label>
                <div className="relative">
                  <Calendar size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary" />
                  <input
                    type="date"
                    value={expiryDate}
                    onChange={(e) => setExpiryDate(e.target.value)}
                    className="w-full h-12 pl-10 pr-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary"
                  />
                </div>
              </div>
            </div>
            <Button
              size="lg"
              className="w-full"
              onClick={() => setStep(1)}
              disabled={!state || !licenseType}
            >
              Continue <ChevronRight size={20} className="ml-1" />
            </Button>
          </div>
        )}

        {step === 1 && (
          <div className="flex-1 flex flex-col justify-center space-y-6">
            <div className="text-center space-y-2 mb-4">
              <div className="flex justify-center mb-6">
                <div className="w-16 h-16 rounded-card bg-primary/10 flex items-center justify-center">
                  <BadgeCheck size={32} className="text-primary" />
                </div>
              </div>
              <h1 className="text-2xl font-bold text-text-primary">{steps[1].title}</h1>
              <p className="text-text-secondary">{steps[1].subtitle}</p>
            </div>

            {/* NBRC Portal Login — Pro Feature */}
            <div className="bg-gradient-to-br from-primary/5 to-accent/5 rounded-card p-5 border border-primary/20 space-y-4">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <BadgeCheck size={20} className="text-primary" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-text-primary">Auto-sync from NBRC Portal</h3>
                  <p className="text-xs text-text-secondary mt-1">
                    Enter your NBRC login and we&apos;ll pull your real credentials, CMP cycle dates, assessment scores, and CE requirements automatically.
                  </p>
                  <div className="flex items-center gap-1 mt-2">
                    <span className="text-xs font-medium text-accent bg-accent/10 px-2 py-0.5 rounded-full">Pro Feature</span>
                    <span className="text-xs text-text-secondary">· Free during launch</span>
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-text-secondary">NBRC Portal Email</label>
                  <input
                    type="email"
                    value={nbrcEmail}
                    onChange={(e) => setNbrcEmail(e.target.value)}
                    placeholder="ron@example.com"
                    className="w-full h-11 px-3 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary text-sm"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-text-secondary">NBRC Portal Password</label>
                  <div className="relative">
                    <input
                      type={showNbrcPassword ? "text" : "password"}
                      value={nbrcPassword}
                      onChange={(e) => setNbrcPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full h-11 px-3 pr-10 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary text-sm"
                    />
                    <button
                      type="button"
                      onClick={() => setShowNbrcPassword(!showNbrcPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-text-secondary hover:text-text-primary"
                      tabIndex={-1}
                    >
                      {showNbrcPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>
                <Button
                  size="sm"
                  className="w-full"
                  onClick={handleNbrcScrape}
                  disabled={!nbrcEmail || !nbrcPassword || nbrcScraping}
                >
                  {nbrcScraping ? (
                    <>
                      <Loader2 size={16} className="mr-1 animate-spin" /> Pulling from NBRC...
                    </>
                  ) : (
                    "Pull My NBRC Data"
                  )}
                </Button>
                {nbrcScrapeError && (
                  <div className="flex items-center gap-2 bg-danger/10 text-danger rounded-button px-3 py-2 text-xs">
                    <AlertTriangle size={14} />
                    <span>{nbrcScrapeError}</span>
                  </div>
                )}
                {nbrcScrapeSuccess && (
                  <div className="flex items-center gap-2 bg-success/10 text-success rounded-button px-3 py-2 text-xs">
                    <CheckCircle2 size={14} />
                    <span>NBRC data synced! Credentials, CMP cycle, and assessment scores pulled.</span>
                  </div>
                )}
              </div>
            </div>

            {/* Skip / Manual entry divider */}
            <div className="flex items-center gap-3">
              <div className="flex-1 h-px bg-gray-200" />
              <span className="text-xs text-text-secondary">or enter manually</span>
              <div className="flex-1 h-px bg-gray-200" />
            </div>

            {/* Manual NBRC Credential Setup card */}
            <div className="bg-surface rounded-card p-4 border border-gray-100 space-y-3">
              <h3 className="text-sm font-semibold text-text-primary">Manual Entry</h3>

              <div className="space-y-2">
                <label className="text-sm font-medium text-text-secondary">Credential Type</label>
                <select
                  value={nbrcType}
                  onChange={(e) => setNbrcType(e.target.value)}
                  className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary bg-white"
                >
                  <option value="" disabled>Select credential type</option>
                  <option value="RRT">RRT — Registered Respiratory Therapist</option>
                  <option value="CRT">CRT — Certified Respiratory Therapist</option>
                  <option value="NPS">NPS — Neonatal/Pediatric Specialist</option>
                  <option value="ACCS">ACCS — Adult Critical Care Specialist</option>
                  <option value="SDS">SDS — Sleep Disorders Specialist</option>
                </select>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-text-secondary">CMP Cycle End Date {nbrcCycleEnd && <span className="text-accent text-xs">(estimated)</span>}</label>
                <div className="relative">
                  <Calendar size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary" />
                  <input
                    type="date"
                    value={nbrcCycleEnd}
                    onChange={(e) => setNbrcCycleEnd(e.target.value)}
                    className="w-full h-12 pl-10 pr-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary"
                  />
                </div>
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 bg-danger/10 text-danger rounded-button px-3 py-2 text-sm">
                {error}
              </div>
            )}

            <div className="flex gap-3">
              <Button variant="outline" size="lg" onClick={() => setStep(0)}>
                <ChevronLeft size={20} />
              </Button>
              <Button
                size="lg"
                className="flex-1"
                onClick={() => setStep(2)}
                disabled={!nbrcType && !nbrcScrapeSuccess}
              >
                Save &amp; Continue <ChevronRight size={20} className="ml-1" />
              </Button>
            </div>

            {/* Skip NBRC setup */}
            <div className="text-center">
              <button
                type="button"
                onClick={() => setStep(2)}
                className="text-sm text-text-secondary hover:text-text-primary transition-colors underline"
              >
                Skip NBRC setup
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="flex-1 flex flex-col justify-center space-y-6">
            <div className="text-center space-y-4">
              <div className="flex justify-center mb-4">
                <div className="w-24 h-24 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center text-white text-4xl font-bold">
                  {user?.name?.[0]?.toUpperCase() ?? "R"}
                </div>
              </div>
              <h1 className="text-2xl font-bold text-text-primary">{steps[2].title}</h1>
              <p className="text-text-secondary">{steps[2].subtitle}</p>
              <div className="bg-surface rounded-card p-4 border border-gray-100 text-left space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-text-secondary">Name</span>
                  <span className="font-medium">{user?.name ?? "—"}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-text-secondary">Email</span>
                  <span className="font-medium text-xs">{user?.email ?? "—"}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-text-secondary">License</span>
                  <span className="font-medium">{licenseType} · {state}</span>
                </div>
                {licenseNumber && (
                  <div className="flex justify-between text-sm">
                    <span className="text-text-secondary">License #</span>
                    <span className="font-medium font-mono text-xs">{licenseNumber}</span>
                  </div>
                )}
                {nbrcType && (
                  <div className="flex justify-between text-sm">
                    <span className="text-text-secondary">NBRC</span>
                    <span className="font-medium">{nbrcType}{nbrcCycleEnd ? ` · CMP ends ${nbrcCycleEnd}` : ""}</span>
                  </div>
                )}
                <div className="flex justify-between text-sm">
                  <span className="text-text-secondary">Required CEUs</span>
                  <span className="font-medium">30 per cycle</span>
                </div>
              </div>
              <p className="text-sm text-text-secondary px-4">
                We&apos;ll remind you before deadlines and help you stay on track.
              </p>
            </div>
            {error && (
              <div className="flex items-center gap-2 bg-danger/10 text-danger rounded-button px-3 py-2 text-sm">
                {error}
              </div>
            )}
            <div className="flex gap-3">
              <Button variant="outline" size="lg" onClick={() => setStep(1)}>
                <ChevronLeft size={20} />
              </Button>
              <Button
                size="lg"
                className="flex-1"
                onClick={handleFinish}
                disabled={saving}
              >
                {saving ? "Saving..." : "Go to Dashboard"} <ChevronRight size={20} className="ml-1" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}