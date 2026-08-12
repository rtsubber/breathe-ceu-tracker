"use client";

import { useEffect, useState } from "react";
import { BottomNav } from "@/components/bottom-nav";
import { ProgressRing } from "@/components/progress-ring";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import {
  Plus,
  FileText,
  ChevronRight,
  Award,
  CheckCircle2,
  Clock,
  Bell,
  Loader2,
  MapPin,
  AlertTriangle,
  Gift,
  RefreshCw,
  CloudUpload,
  XCircle,
  Mail,
  Copy,
} from "lucide-react";
import {
  getUser,
  getCEUs,
  getProgress,
  getCredentials,
  getPrimaryLicense,
  getStates,
  getFreeCourseAlerts,
  getCEBrokerStatus,
  syncToCEBroker,
  getNBRCStatus,
  getEmailAlias,
  formatDate,
  credStatus,
  type User,
  type CEU,
  type Progress,
  type Credential,
  type License,
  type StateRequirement,
  type FreeCourseAlert,
  type NBRCStatus,
  type SubscriptionTier,
  type CEBrokerSyncResult,
  type CEBrokerStatus,
  type EmailAliasInfo,
} from "@/lib/api";
import { NBRCStatusCard } from "@/components/nbrc-status";
import { LicenseLookup } from "@/components/license-lookup";
import type { LicenseLookupResult } from "@/lib/api";
import { usStates } from "@/lib/mock-data";

export default function DashboardPage() {
  const [user, setUser] = useState<User | null>(null);
  const [ceus, setCEUs] = useState<CEU[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [license, setLicense] = useState<License | null>(null);
  const [licenses, setLicenses] = useState<License[]>([]);
  const [states, setStates] = useState<StateRequirement[]>([]);
  const [freeAlerts, setFreeAlerts] = useState<FreeCourseAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedState, setSelectedState] = useState<string>("");
  const [showAddState, setShowAddState] = useState(false);
  const [showLicenses, setShowLicenses] = useState(false);
  const [cebrokerStatus, setCebrokerStatus] = useState<CEBrokerStatus | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<CEBrokerSyncResult | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [nbrcStatus, setNbrcStatus] = useState<NBRCStatus | null>(null);
  const [addStateSelection, setAddStateSelection] = useState<string>("");
  const [emailAlias, setEmailAlias] = useState<EmailAliasInfo | null>(null);
  const [copiedAlias, setCopiedAlias] = useState(false);

  // Convert full state name to 2-letter code for API
  const stateNameToCode: Record<string, string> = {
    "Texas": "TX", "Indiana": "IN", "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ",
    "Arkansas": "AR", "California": "CA", "Colorado": "CO", "Connecticut": "CT",
    "Delaware": "DE", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI",
    "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
    "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
    "New Mexico": "NM", "New York": "NY", "North Carolina": "NC", "North Dakota": "ND",
    "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
    "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
  };
  const [lookupResult, setLookupResult] = useState<LicenseLookupResult | null>(null);
  const [savingLicense, setSavingLicense] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [u, c, p, creds, lics, stReqs, fa, cbs, nbrc, alias] = await Promise.all([
          getUser(),
          getCEUs(),
          getProgress(),
          getCredentials(),
          (await import("@/lib/api")).getLicenses(),
          getStates(),
          getFreeCourseAlerts().catch(() => [] as FreeCourseAlert[]),
          getCEBrokerStatus().catch(() => null as CEBrokerStatus | null),
          getNBRCStatus().catch(() => null as NBRCStatus | null),
          getEmailAlias().catch(() => null as EmailAliasInfo | null),
        ]);
        if (cancelled) return;
        setUser(u);
        setCEUs(c);
        setProgress(p);
        setCredentials(creds);
        setLicenses(lics);
        setLicense(lics[0] ?? null);
        setStates(stReqs);
        setFreeAlerts(fa);
        setCebrokerStatus(cbs);
        setNbrcStatus(nbrc);
        setEmailAlias(alias);
        if (lics[0]) setSelectedState(lics[0].state);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load dashboard");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSyncCEBroker = async () => {
    setSyncing(true);
    setSyncError(null);
    setSyncResult(null);
    try {
      const result = await syncToCEBroker();
      setSyncResult(result);
      // Refresh CEU list and CE Broker status
      const [updatedCEUs, updatedStatus] = await Promise.all([
        getCEUs(),
        getCEBrokerStatus().catch(() => null),
      ]);
      setCEUs(updatedCEUs);
      setCebrokerStatus(updatedStatus);
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  // Recompute displayed progress ring when state changes
  const stateRequirement = states.find((s) => s.state === selectedState);
  const requiredForState = stateRequirement?.required_ceus ?? license?.required_ceus ?? 30;
  const completed = progress?.total_earned ?? 0;
  const remaining = Math.max(0, requiredForState - completed);

  const recentCEUs = ceus.slice(0, 3);
  const primaryCreds = credentials.slice(0, 3);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-enter min-h-screen pb-20">
        <div className="px-4 pt-12 text-center">
          <AlertTriangle className="mx-auto text-danger mb-3" size={40} />
          <p className="text-danger font-semibold">{error}</p>
          <p className="text-sm text-text-secondary mt-2">
            Make sure the API server is running on port 8088.
          </p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => window.location.reload()}
          >
            Retry
          </Button>
        </div>
        <BottomNav />
      </div>
    );
  }

  return (
    <div className="page-enter min-h-screen pb-20">
      {/* Header */}
      <div className="bg-gradient-to-br from-primary to-accent px-6 pt-12 pb-8 text-white rounded-b-[32px]">
        <div className="flex justify-between items-start mb-2">
          <div>
            <p className="text-white/70 text-sm">Good evening</p>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold">Hi, {user?.name?.split(" ")[0] ?? "there"}</h1>
              {(user?.subscription_tier === "pro" || user?.subscription_tier === "department") && (
                <span className="text-xs bg-accent/30 text-white px-2 py-0.5 rounded-full font-semibold border border-white/20">
                  PRO
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/notifications" aria-label="Notifications">
              <div className="relative w-10 h-10 rounded-full bg-white/20 flex items-center justify-center">
                <Bell size={18} className="text-white" />
                <span className="absolute -top-0.5 -right-0.5 w-3 h-3 rounded-full bg-warning border-2 border-white" />
              </div>
            </Link>
            <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center text-white font-bold">
              {user?.name?.[0] ?? "?"}
            </div>
          </div>
        </div>

        {/* State selector + license info */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 text-sm bg-white/10 rounded-full px-3 py-2">
            <Award size={14} />
            <span className="font-medium">
              {license?.license_type ?? "—"} · {selectedState || "No state"}
              {license ? ` · Expires ${formatDate(license.expiry_date).split(",")[0]}` : ""}
            </span>
          </div>
          {/* NBRC credential badges (show credentials that aren't the license type, hide CRT if RRT+) */}
          {nbrcStatus?.credentials?.filter(c => c.type !== license?.license_type).filter((cred, _i, arr) => {
            const hasRRTOrHigher = arr.some(c => ["RRT", "RRT-NPS", "ACCS", "SDS", "RPFT", "AE-C"].includes(c.type));
            return !(hasRRTOrHigher && cred.type === "CRT");
          }).map((cred) => (
            <span key={cred.type} className="text-xs bg-accent/30 text-white px-2 py-1 rounded-full font-medium border border-white/20">
              {cred.type}
            </span>
          ))}
          <div className="relative">
            <select
              value={selectedState}
              onChange={(e) => setSelectedState(e.target.value)}
              className="appearance-none bg-white/15 text-white text-sm rounded-full pl-3 pr-7 py-2 focus:outline-none cursor-pointer"
              aria-label="Select state"
            >
              {licenses.map((lic) => (
                <option key={lic.id} value={lic.state} className="text-text-primary">
                  {lic.state === licenses[0]?.state ? `${lic.state} (Primary)` : lic.state}
                </option>
              ))}
              {licenses.length === 0 && <option className="text-text-primary">Texas</option>}
              {usStates
                .filter((s) => !licenses.some((l) => l.state === s))
                .map((s) => (
                  <option key={s} value={s} className="text-text-primary">
                    + {s}
                  </option>
                ))}
            </select>
            <MapPin
              size={12}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-white/70 pointer-events-none"
            />
          </div>
          <button
            onClick={() => setShowAddState(!showAddState)}
            className="text-xs bg-white/15 hover:bg-white/25 transition-colors rounded-full px-3 py-1.5 font-medium"
          >
            + Add State License
          </button>
        </div>

        {/* All licenses list with status — collapsible */}
        {licenses.length > 0 && (
          <div className="mt-2">
            <button
              onClick={() => setShowLicenses(!showLicenses)}
              className="text-xs text-white/60 hover:text-white/90 transition-colors flex items-center gap-1"
            >
              <ChevronRight size={12} className={`transition-transform ${showLicenses ? "rotate-90" : ""}`} />
              {showLicenses ? "Hide" : "Show"} all licenses ({licenses.length})
            </button>
            {showLicenses && (
              <div className="mt-2 space-y-2">
            {licenses.map((lic) => {
              const expiry = new Date(lic.expiry_date);
              const now = new Date();
              const isExpired = expiry < now;
              const isPrimary = lic === licenses[0];
              return (
                <div
                  key={lic.id}
                  className={`flex items-center justify-between gap-3 p-3 rounded-card border ${
                    isExpired
                      ? "bg-white/5 border-white/10"
                      : "bg-white/10 border-white/20"
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <Award size={16} className="flex-shrink-0 text-white/70" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white truncate">
                        {lic.state} — {lic.license_number}
                        {isPrimary && <span className="text-xs text-white/60 ml-1">(Primary)</span>}
                      </p>
                      <p className="text-xs text-white/60">
                        {lic.license_type} · Expires {formatDate(lic.expiry_date).split(",")[0]}
                      </p>
                    </div>
                  </div>
                  <span
                    className={`flex-shrink-0 text-xs px-2 py-1 rounded-full font-medium ${
                      isExpired
                        ? "bg-red-500/20 text-red-300 border border-red-500/30"
                        : "bg-green-500/20 text-green-300 border border-green-500/30"
                    }`}
                  >
                    {isExpired ? "Expired" : "Active"}
                  </span>
                </div>
              );
            })}
            </div>
            )}
          </div>
        )}

        {/* Add state license via LicenseLookup */}
        {showAddState && (
          <div className="mt-3 bg-white rounded-card p-4 space-y-3 text-text-primary">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Add State License</h3>
              <button
                type="button"
                onClick={() => {
                  setShowAddState(false);
                  setAddStateSelection("");
                  setLookupResult(null);
                }}
                className="text-xs text-text-secondary hover:text-text-primary"
              >
                ✕
              </button>
            </div>

            {/* Step 1: Select state */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-text-secondary">
                Select state
              </label>
              <select
                value={addStateSelection}
                onChange={(e) => {
                  setAddStateSelection(e.target.value);
                  setLookupResult(null);
                }}
                className="w-full h-11 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary bg-white text-sm"
              >
                <option value="" disabled>Select a state</option>
                {usStates
                  .filter((s) => !licenses.some((l) => l.state === s))
                  .map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
              </select>
            </div>

            {/* Step 2: LicenseLookup once state is selected */}
            {addStateSelection && (
              <div className="pt-2 border-t border-gray-100">
                <LicenseLookup
                  state={stateNameToCode[addStateSelection] || addStateSelection}
                  onSelect={(result: LicenseLookupResult) => {
                    setLookupResult(result);
                  }}
                />
              </div>
            )}

            {/* Step 3: Save button once a license is selected */}
            {lookupResult && (
              <div className="pt-2 border-t border-gray-100 space-y-2">
                <div className="flex items-start gap-2 p-3 bg-green-50 border border-green-200 rounded-button text-sm text-green-700">
                  <CheckCircle2 size={16} className="mt-0.5 flex-shrink-0" />
                  <div className="flex-1">
                    <p className="font-medium">License found!</p>
                    <p className="text-xs text-green-600 mt-0.5">
                      {lookupResult.name} — {lookupResult.license_number}
                      {lookupResult.license_type_full ? ` (${lookupResult.license_type_full})` : ` (${lookupResult.license_type})`}
                      {lookupResult.expiry_date && ` · Expires ${new Date(lookupResult.expiry_date).toLocaleDateString("en-US", { month: "short", year: "numeric" })}`}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  disabled={savingLicense}
                  onClick={async () => {
                    if (!lookupResult.expiry_date) return;
                    setSavingLicense(true);
                    try {
                      const token = localStorage.getItem("breathe_token");
                      // Map lookup license_type to a display type for our system
                      const displayType = lookupResult.license_type === "RCP"
                        ? "RRT"
                        : lookupResult.license_type;
                      const res = await fetch("/api/licenses", {
                        method: "POST",
                        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
                        body: JSON.stringify({
                          state: addStateSelection,
                          license_type: displayType,
                          license_number: lookupResult.license_number,
                          expiry_date: lookupResult.expiry_date,
                          cycle_years: 2,
                          required_ceus: 24,
                        }),
                      });
                      if (res.ok) {
                        setShowAddState(false);
                        setAddStateSelection("");
                        setLookupResult(null);
                        window.location.reload();
                      }
                    } catch (e) {
                      console.error(e);
                    } finally {
                      setSavingLicense(false);
                    }
                  }}
                  className="w-full bg-primary hover:bg-primary/90 text-white text-sm font-medium py-2.5 rounded-button transition-colors disabled:opacity-50"
                >
                  {savingLicense ? "Saving…" : "Save License"}
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Progress Ring */}
      <div className="flex justify-center -mt-6 mb-4">
        <div className="bg-surface rounded-card p-6 shadow-md border border-gray-100">
          <ProgressRing completed={completed} total={requiredForState} size={160} />
          <div className="text-center mt-3">
            {remaining > 0 ? (
              <div className="inline-flex items-center gap-2 bg-warning/10 text-warning px-3 py-1.5 rounded-full text-sm font-medium">
                <Clock size={14} />
                {remaining} to go
                {progress?.days_to_renewal != null && ` · ${Math.round(progress.days_to_renewal / 30)} months`}
              </div>
            ) : (
              <div className="inline-flex items-center gap-2 bg-success/10 text-success px-3 py-1.5 rounded-full text-sm font-medium">
                <CheckCircle2 size={14} />
                On track ✓
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="px-4 mb-6">
        <div className="grid grid-cols-3 gap-3">
          <Link href="/add-ceu">
            <Card className="flex flex-col items-center gap-2 py-3 hover:shadow-md transition-shadow cursor-pointer">
              <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                <Plus size={20} className="text-primary" />
              </div>
              <span className="text-xs font-medium text-text-primary">Add CEU</span>
            </Card>
          </Link>
          <Link href="/ce-report">
            <Card className="flex flex-col items-center gap-2 py-3 hover:shadow-md transition-shadow cursor-pointer">
              <div className="w-10 h-10 rounded-full bg-accent/10 flex items-center justify-center">
                <FileText size={20} className="text-accent" />
              </div>
              <span className="text-xs font-medium text-text-primary text-center">CE Compliance Report</span>
            </Card>
          </Link>
          <Link href="/ceus">
            <Card className="flex flex-col items-center gap-2 py-3 hover:shadow-md transition-shadow cursor-pointer">
              <div className="w-10 h-10 rounded-full bg-success/10 flex items-center justify-center">
                <ChevronRight size={20} className="text-success" />
              </div>
              <span className="text-xs font-medium text-text-primary">View All</span>
            </Card>
          </Link>
        </div>
        {/* Free CEU Courses card */}
        <Link href="/free-courses" className="block mt-3">
          <Card className="flex items-center gap-3 p-4 hover:shadow-md transition-shadow cursor-pointer">
            <div className="w-10 h-10 rounded-full bg-accent/10 flex items-center justify-center">
              <Gift size={20} className="text-accent" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold text-text-primary">Free CEU Courses</p>
              <p className="text-xs text-text-secondary">
                {freeAlerts.length > 0
                  ? `${freeAlerts.length} new course${freeAlerts.length === 1 ? "" : "s"} available`
                  : "Scan for free credit opportunities"}
              </p>
            </div>
            {freeAlerts.length > 0 && (
              <span className="text-xs font-bold bg-accent text-white px-2 py-1 rounded-full">
                {freeAlerts.length}
              </span>
            )}
            <ChevronRight size={18} className="text-text-secondary" />
          </Card>
        </Link>

      {/* Email Forwarding card */}
      {emailAlias?.forwarding_address && (
        <div className="mt-3">
          <Card className="p-4">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-accent/10 flex items-center justify-center">
                <Mail size={20} className="text-accent" />
              </div>
              <div className="flex-1">
                <p className="text-sm font-semibold text-text-primary">Email Forwarding</p>
                <p className="text-xs text-text-secondary">Forward CEU emails to auto-log credits</p>
              </div>
            </div>
            <div className="bg-surface rounded-card p-3 flex items-center gap-2">
              <code className="text-sm text-text-primary flex-1 truncate">{emailAlias.forwarding_address}</code>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(emailAlias.forwarding_address || "");
                  setCopiedAlias(true);
                  setTimeout(() => setCopiedAlias(false), 2000);
                }}
                className="text-text-secondary hover:text-primary flex-shrink-0"
              >
                {copiedAlias ? <CheckCircle2 size={16} className="text-success" /> : <Copy size={16} />}
              </button>
            </div>
            <p className="text-xs text-text-secondary mt-2">
              Forward CEU confirmation emails here. Breathe parses and logs them automatically.
            </p>
          </Card>
        </div>
      )}

      {/* CE Broker Sync card */}
        <div className="mt-3">
          <Card className="p-4">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                <CloudUpload size={20} className="text-primary" />
              </div>
              <div className="flex-1">
                <p className="text-sm font-semibold text-text-primary">CE Broker Sync</p>
                <p className="text-xs text-text-secondary">
                  {cebrokerStatus
                    ? cebrokerStatus.unsynced > 0
                      ? `${cebrokerStatus.unsynced} CEU${cebrokerStatus.unsynced === 1 ? "" : "s"} pending sync`
                      : cebrokerStatus.total_ceus > 0
                        ? "All CEUs synced ✓"
                        : "No CEUs to sync"
                    : "Sync CEUs to CE Broker"}
                </p>
              </div>
              {cebrokerStatus && cebrokerStatus.all_synced && cebrokerStatus.total_ceus > 0 && (
                <CheckCircle2 size={20} className="text-success" />
              )}
            </div>

            {syncResult && (
              <div className={`mb-3 rounded-card p-3 text-sm ${
                syncResult.failed > 0
                  ? "bg-warning/10 text-warning"
                  : syncResult.submitted_unconfirmed > 0
                    ? "bg-accent/10 text-accent"
                    : "bg-success/10 text-success"
              }`}>
                <p className="font-medium">
                  {syncResult.synced > 0 && `✓ ${syncResult.synced} confirmed. `}
                  {syncResult.submitted_unconfirmed > 0 && `⏳ ${syncResult.submitted_unconfirmed} submitted (unconfirmed). `}
                  {syncResult.failed > 0 && `⚠ ${syncResult.failed} failed.`}
                </p>
                {syncResult.message && (
                  <p className="text-xs mt-0.5 opacity-80">{syncResult.message}</p>
                )}
                {syncResult.errors.length > 0 && (
                  <ul className="mt-1 text-xs space-y-0.5">
                    {syncResult.errors.slice(0, 3).map((err, i) => (
                      <li key={i}>• {err}</li>
                    ))}
                    {syncResult.errors.length > 3 && (
                      <li>• ...and {syncResult.errors.length - 3} more</li>
                    )}
                  </ul>
                )}
              </div>
            )}

            {syncError && (
              <div className="mb-3 rounded-card p-3 text-sm bg-danger/10 text-danger flex items-center gap-2">
                <XCircle size={16} />
                <span>{syncError}</span>
              </div>
            )}

            <Button
              onClick={handleSyncCEBroker}
              disabled={syncing || (cebrokerStatus?.unsynced === 0 && cebrokerStatus?.total_ceus > 0)}
              className="w-full"
              variant={cebrokerStatus?.all_synced && cebrokerStatus?.total_ceus > 0 ? "outline" : "primary"}
            >
              {syncing ? (
                <>
                  <Loader2 size={16} className="animate-spin mr-2" />
                  Syncing to CE Broker...
                </>
              ) : cebrokerStatus?.all_synced && cebrokerStatus?.total_ceus > 0 ? (
                <>
                  <CheckCircle2 size={16} className="mr-2" />
                  All Synced
                </>
              ) : (
                <>
                  <RefreshCw size={16} className="mr-2" />
                  Sync to CE Broker
                </>
              )}
            </Button>
          </Card>
        </div>
      </div>

      {/* NBRC CMP Section */}
      <div className="px-4 mb-6">
        <div className="flex justify-between items-center mb-3">
          <h2 className="text-lg font-bold text-text-primary">NBRC Credential</h2>
          <Link href="/nbrc" className="text-sm text-accent font-medium">Details</Link>
        </div>
        <NBRCStatusCard />
      </div>

      {/* Recent Activity */}
      <div className="px-4 mb-6">
        <div className="flex justify-between items-center mb-3">
          <h2 className="text-lg font-bold text-text-primary">Recent Activity</h2>
          <Link href="/ceus" className="text-sm text-primary font-medium">See all</Link>
        </div>
        <div className="space-y-2">
          {recentCEUs.length === 0 ? (
            <Card className="py-6 text-center text-text-secondary text-sm">
              No CEUs yet. Tap “Add CEU” to log your first course.
            </Card>
          ) : (
            recentCEUs.map((ceu) => (
              <Card key={ceu.id} className="flex items-center gap-3 py-3">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary/10 to-accent/10 flex items-center justify-center flex-shrink-0">
                  <FileText size={18} className="text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-text-primary truncate">{ceu.title}</p>
                  <p className="text-xs text-text-secondary">
                    {ceu.provider} · {ceu.credits} CEUs · {formatDate(ceu.completion_date)}
                  </p>
                </div>
                <span className="text-xs font-medium px-2 py-1 rounded-full bg-primary/10 text-primary">
                  +{ceu.credits}
                </span>
              </Card>
            ))
          )}
        </div>
      </div>

      {/* Credentials */}
      <div className="px-4 mb-6">
        <div className="flex justify-between items-center mb-3">
          <h2 className="text-lg font-bold text-text-primary">Credentials</h2>
          <Link href="/credentials" className="text-sm text-primary font-medium">Manage</Link>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {primaryCreds.length === 0 ? (
            <Card className="col-span-3 text-center py-4 text-text-secondary text-sm">
              No credentials loaded.
            </Card>
          ) : (
            primaryCreds.map((cred) => {
              const status = credStatus(cred.expiry_date);
              return (
                <Card key={cred.id} className="text-center py-3">
                  <p className="text-sm font-bold text-text-primary">{cred.type}</p>
                  <div className={`mt-1 inline-flex items-center gap-1 text-xs ${
                    status === "current" ? "text-success" : status === "expiring" ? "text-warning" : "text-danger"
                  }`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${
                      status === "current" ? "bg-success" : status === "expiring" ? "bg-warning" : "bg-danger"
                    }`} />
                    {status === "current" ? "Active" : status === "expiring" ? "Soon" : "Expired"}
                  </div>
                </Card>
              );
            })
          )}
        </div>
      </div>

      <BottomNav />
    </div>
  );
}