"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/logo";
import { usStates } from "@/lib/mock-data";
import { LicenseLookup } from "@/components/license-lookup";
import type { LicenseLookupResult } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { ChevronRight, ChevronLeft, Calendar, Award, Search, CheckCircle2, BadgeCheck } from "lucide-react";
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
  const { user } = useAuth();
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

  // When expiryDate changes (from TMB lookup or manual entry), estimate NBRC cycle end
  useEffect(() => {
    if (expiryDate) {
      setNbrcCycleEnd(calculateNBRCCycleEnd(expiryDate));
    }
  }, [expiryDate]);

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
  const stateCode = stateNameToCode[state] || "TX";

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
      // Save state license
      if (user && state && licenseType) {
        await apiFetch("/api/licenses", {
          method: "POST",
          body: JSON.stringify({
            state: stateCode,
            license_type: licenseType,
            license_number: licenseNumber || "PENDING",
            expiry_date: expiryDate || "2027-03-31",
            cycle_years: 2,
            required_ceus: 24,
          }),
        });
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

      router.push("/dashboard");
    } catch (err) {
      // Even if save fails, go to dashboard
      console.error("Onboarding save failed:", err);
      router.push("/dashboard");
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
                    if (result.license_type === "RCP") {
                      setLicenseType(licenseType === "RRT" ? "RRT" : "CRT");
                      // Also auto-set NBRC type to match
                      setNbrcType(licenseType === "RRT" ? "RRT" : "CRT");
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

            {/* NBRC Credential Setup card */}
            <div className="bg-surface rounded-card p-5 border border-gray-100 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary">NBRC Credential Setup</h3>

              {/* NBRC Credential Type */}
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

              {/* NBRC Registry Number */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-text-secondary">
                  NBRC Registry Number
                </label>
                <input
                  type="text"
                  value={nbrcRegistryNumber}
                  onChange={(e) => setNbrcRegistryNumber(e.target.value)}
                  placeholder="Enter your NBRC registry number"
                  className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary font-mono text-sm"
                />
                <p className="text-xs text-text-secondary">
                  This is separate from your state license number.
                </p>
              </div>

              {/* CMP Cycle End Date */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-text-secondary">
                  CMP Cycle End Date {nbrcCycleEnd && <span className="text-accent text-xs">(estimated)</span>}
                </label>
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

              {/* Renewal Method */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-text-secondary">Renewal Method</label>
                <select
                  value={nbrcRenewalMethod}
                  onChange={(e) => setNbrcRenewalMethod(e.target.value)}
                  className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary bg-white"
                >
                  <option value="assessments">Quarterly Assessments</option>
                  <option value="exam">Retake Exam</option>
                  <option value="new_credential">New Credential</option>
                </select>
              </div>

              {/* Note */}
              <p className="text-xs text-text-secondary">
                We estimated your CMP cycle end date from your license. Please verify this is correct — your actual NBRC cycle may differ.
              </p>
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
                disabled={!nbrcType || !nbrcCycleEnd}
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