"use client";

import { useEffect, useState } from "react";
import { BottomNav } from "@/components/bottom-nav";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Award,
  Calendar,
  Clock,
  CheckCircle2,
  AlertCircle,
  TrendingUp,
  Target,
  Plus,
  ChevronLeft,
  Loader2,
  Trash2,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";
import {
  getNBRCStatus,
  addNBRCCredential,
  logAssessment,
  getAssessmentReminder,
  formatDate,
  type NBRCStatus,
  type AssessmentReminder,
} from "@/lib/api";

const CREDENTIAL_TYPES = ["RRT", "CRT", "NPS", "ACCS", "SDS", "RPFT", "AE-C"];
const RENEWAL_METHODS = [
  { value: "assessments", label: "Quarterly Assessments" },
  { value: "exam", label: "Retake Exam" },
  { value: "new_credential", label: "Earn New Credential" },
];
const QUARTERS = [
  { value: "2026-Q1", label: "2026 Q1" },
  { value: "2026-Q2", label: "2026 Q2" },
  { value: "2026-Q3", label: "2026 Q3" },
  { value: "2026-Q4", label: "2026 Q4" },
  { value: "2027-Q1", label: "2027 Q1" },
  { value: "2027-Q2", label: "2027 Q2" },
  { value: "2027-Q3", label: "2027 Q3" },
  { value: "2027-Q4", label: "2027 Q4" },
];

export default function NBRCPage() {
  const [status, setStatus] = useState<NBRCStatus | null>(null);
  const [reminder, setReminder] = useState<AssessmentReminder | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add credential form state
  const [showAddCred, setShowAddCred] = useState(false);
  const [credType, setCredType] = useState("RRT");
  const [earnedDate, setEarnedDate] = useState("");
  const [cycleEnd, setCycleEnd] = useState("");
  const [renewalMethod, setRenewalMethod] = useState("assessments");
  const [isHighest, setIsHighest] = useState(false);
  const [saving, setSaving] = useState(false);

  // Assessment form state
  const [showAddAssessment, setShowAddAssessment] = useState(false);
  const [assessmentQuarter, setAssessmentQuarter] = useState("");
  const [assessmentScore, setAssessmentScore] = useState("");
  const [assessmentDate, setAssessmentDate] = useState("");
  const [savingAssessment, setSavingAssessment] = useState(false);

  const loadData = async () => {
    try {
      const [s, r] = await Promise.all([
        getNBRCStatus(),
        getAssessmentReminder(),
      ]);
      setStatus(s);
      setReminder(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load NBRC data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleAddCredential = async () => {
    if (!cycleEnd) return;
    setSaving(true);
    try {
      await addNBRCCredential({
        credential_type: credType,
        earned_date: earnedDate || null,
        cmp_cycle_end: cycleEnd,
        renewal_method: renewalMethod,
        is_highest: isHighest,
      });
      setShowAddCred(false);
      setCredType("RRT");
      setEarnedDate("");
      setCycleEnd("");
      setRenewalMethod("assessments");
      setIsHighest(false);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add credential");
    } finally {
      setSaving(false);
    }
  };

  const handleLogAssessment = async () => {
    if (!assessmentQuarter) return;
    setSavingAssessment(true);
    try {
      await logAssessment({
        quarter: assessmentQuarter,
        score: assessmentScore ? parseFloat(assessmentScore) : undefined,
        taken_date: assessmentDate || undefined,
      });
      setShowAddAssessment(false);
      setAssessmentQuarter("");
      setAssessmentScore("");
      setAssessmentDate("");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to log assessment");
    } finally {
      setSavingAssessment(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  const daysLeft = status?.days_remaining ?? 0;
  const progressPct = status?.progress_pct ?? 0;
  const ceRequired = status?.ce_required ?? 30;
  const ceEarned = status?.ce_from_state_license ?? 0;
  const additionalCe = status?.additional_ce_needed ?? 0;
  const onTrack = status?.on_track ?? false;

  // Progress ring for NBRC cycle
  const ringSize = 140;
  const ringStroke = 12;
  const radius = (ringSize - ringStroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const ringOffset = circumference * (1 - progressPct / 100);

  return (
    <div className="page-enter min-h-screen pb-20">
      {/* Header */}
      <div className="bg-gradient-to-br from-accent to-primary px-6 pt-10 pb-6 text-white rounded-b-[32px]">
        <div className="flex items-center gap-3 mb-4">
          <Link href="/dashboard" className="text-white/80 hover:text-white">
            <ChevronLeft size={22} />
          </Link>
          <h1 className="text-xl font-bold">NBRC CMP Tracker</h1>
        </div>
        <p className="text-sm text-white/80">
          Credential Maintenance Program · 5-year renewal cycle
        </p>
      </div>

      <div className="px-4 py-6 space-y-4">
        {error && (
          <Card className="py-3 border-danger/30 bg-danger/5">
            <div className="flex items-center gap-2 text-sm text-danger">
              <AlertCircle size={16} />
              {error}
            </div>
          </Card>
        )}

        {/* No NBRC credentials */}
        {status && !status.has_nbrc && (
          <Card className="p-6 text-center">
            <Award size={40} className="mx-auto text-accent mb-3" />
            <h2 className="text-lg font-bold text-text-primary mb-1">Track Your NBRC Credentials</h2>
            <p className="text-sm text-text-secondary mb-4">
              Add your NBRC credentials (RRT, NPS, etc.) to track your 5-year CMP cycle,
              quarterly assessments, and CE requirements.
            </p>
            <Button onClick={() => setShowAddCred(true)} className="w-full">
              <Plus size={16} className="mr-2" />
              Add Your First Credential
            </Button>
          </Card>
        )}

        {/* NBRC Status Overview */}
        {status && status.has_nbrc && (
          <>
            {/* Progress Ring + Credentials */}
            <Card className="p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-base font-bold text-text-primary">CMP Cycle Progress</h2>
                <Button variant="outline" size="sm" onClick={loadData}>
                  <RefreshCw size={14} className="mr-1" />
                  Refresh
                </Button>
              </div>

              <div className="flex items-center gap-4">
                {/* Progress ring */}
                <div className="relative flex-shrink-0" style={{ width: ringSize, height: ringSize }}>
                  <svg width={ringSize} height={ringSize} className="transform -rotate-90">
                    <circle
                      cx={ringSize / 2}
                      cy={ringSize / 2}
                      r={radius}
                      fill="none"
                      stroke="#E5E7EB"
                      strokeWidth={ringStroke}
                    />
                    <circle
                      className="transition-all duration-1000 ease-in-out"
                      cx={ringSize / 2}
                      cy={ringSize / 2}
                      r={radius}
                      fill="none"
                      stroke="url(#nbrcPageGradient)"
                      strokeWidth={ringStroke}
                      strokeLinecap="round"
                      strokeDasharray={circumference}
                      strokeDashoffset={ringOffset}
                    />
                    <defs>
                      <linearGradient id="nbrcPageGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor="#7C3AED" />
                        <stop offset="100%" stopColor="#2563EB" />
                      </linearGradient>
                    </defs>
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-2xl font-bold text-text-primary">
                      {Math.round(progressPct)}%
                    </span>
                    <span className="text-[10px] text-text-secondary">complete</span>
                  </div>
                </div>

                {/* Details */}
                <div className="flex-1 space-y-2">
                  {/* Credential badges */}
                  <div className="flex flex-wrap gap-1.5">
                    {status.credentials.map((cred, i) => (
                      <span
                        key={i}
                        className={`text-xs font-semibold px-2 py-1 rounded-full ${
                          cred.is_highest
                            ? "bg-accent/15 text-accent border border-accent/20"
                            : "bg-gray-100 text-text-secondary"
                        }`}
                      >
                        {cred.type}
                      </span>
                    ))}
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                    <Calendar size={12} />
                    <span>Ends {formatDate(status.cycle_end)}</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs">
                    <Clock size={12} className={onTrack ? "text-success" : "text-warning"} />
                    <span className={onTrack ? "text-success font-medium" : "text-warning font-medium"}>
                      {daysLeft > 0 ? `${daysLeft} days remaining` : "Expired"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Renewal method */}
              <div className="mt-4 pt-3 border-t border-gray-100">
                <p className="text-xs text-text-secondary mb-1">Renewal Method</p>
                <p className="text-sm font-medium text-text-primary capitalize">
                  {status.renewal_method?.replace("_", " ")}
                </p>
              </div>
            </Card>

            {/* ⭐ CE Overlap Insight — The Killer Feature */}
            <Card className="p-5 border-2 border-accent/20 bg-gradient-to-br from-accent/5 to-primary/5">
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp size={18} className="text-accent" />
                <h2 className="text-base font-bold text-text-primary">CE Overlap Savings</h2>
              </div>

              {ceRequired > 0 ? (
                <>
                  <p className="text-sm text-text-primary mb-3">
                    Your <span className="font-bold text-accent">{ceEarned.toFixed(1)} state CEUs</span>{" "}
                    count toward your NBRC{" "}
                    <span className="font-bold">{ceRequired} CE</span> requirement.
                  </p>

                  {/* Visual: state CE → NBRC CE */}
                  <div className="flex items-center gap-2 mb-3">
                    <div className="flex-1 bg-primary/10 rounded-card p-2 text-center">
                      <p className="text-xs text-text-secondary">State License CE</p>
                      <p className="text-lg font-bold text-primary">{ceEarned.toFixed(1)}</p>
                    </div>
                    <div className="text-text-secondary text-xl">→</div>
                    <div className="flex-1 bg-accent/10 rounded-card p-2 text-center">
                      <p className="text-xs text-text-secondary">NBRC Required</p>
                      <p className="text-lg font-bold text-accent">{ceRequired}</p>
                    </div>
                  </div>

                  {additionalCe > 0 ? (
                    <div className="bg-warning/10 rounded-card p-3">
                      <p className="text-sm font-medium text-warning">
                        ⚡ You need {additionalCe} more CE beyond your state license
                      </p>
                    </div>
                  ) : (
                    <div className="bg-success/10 rounded-card p-3">
                      <p className="text-sm font-medium text-success">
                        ✓ You\u2019re fully covered — no extra CE needed!
                      </p>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-sm text-text-primary">
                  High assessment scores — no additional CE needed this cycle! ✓
                </p>
              )}
            </Card>

            {/* Quarterly Assessments */}
            <Card className="p-5">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Target size={18} className="text-primary" />
                  <h2 className="text-base font-bold text-text-primary">Quarterly Assessments</h2>
                </div>
                <Button variant="outline" size="sm" onClick={() => setShowAddAssessment(!showAddAssessment)}>
                  <Plus size={14} className="mr-1" />
                  Log
                </Button>
              </div>

              {/* Assessment reminder */}
              {reminder && (
                <div
                  className={`rounded-card p-3 mb-3 ${
                    reminder.status === "completed" ? "bg-success/10" : "bg-warning/10"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {reminder.status === "completed" ? (
                      <CheckCircle2 size={16} className="text-success" />
                    ) : (
                      <Clock size={16} className="text-warning" />
                    )}
                    <p className="text-xs font-medium text-text-primary">{reminder.message}</p>
                  </div>
                  <p className="text-xs text-text-secondary mt-1">
                    Next window: {reminder.next_window} · {reminder.days_until_next} days
                  </p>
                </div>
              )}

              {/* Assessment list */}
              {status.assessments && status.assessments.length > 0 ? (
                <div className="space-y-2">
                  {status.assessments.map((a, i) => (
                    <div key={i} className="flex items-center gap-3 py-2 border-b border-gray-50 last:border-0">
                      <div
                        className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                          a.taken
                            ? (a.score ?? 0) >= 75
                              ? "bg-success/10"
                              : (a.score ?? 0) >= 50
                                ? "bg-warning/10"
                                : "bg-danger/10"
                            : "bg-gray-100"
                        }`}
                      >
                        {a.taken ? (
                          <span className="text-xs font-bold">
                            {a.score !== null ? Math.round(a.score) : "—"}
                          </span>
                        ) : (
                          <Clock size={14} className="text-text-secondary" />
                        )}
                      </div>
                      <div className="flex-1">
                        <p className="text-sm font-medium text-text-primary">{a.quarter}</p>
                        <p className="text-xs text-text-secondary">
                          {a.taken
                            ? `Score: ${a.score} · CE req: ${a.score !== null && a.score >= 75 ? 0 : a.score !== null && a.score >= 50 ? 15 : 30}`
                            : "Not taken yet — 30 CE required"}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-text-secondary text-center py-4">
                  No assessments logged yet. Taking quarterly assessments can reduce your CE
                  requirement to 0.
                </p>
              )}

              {/* Inline assessment form */}
              {showAddAssessment && (
                <div className="mt-3 bg-gray-50 rounded-card p-3 space-y-2">
                  <select
                    value={assessmentQuarter}
                    onChange={(e) => setAssessmentQuarter(e.target.value)}
                    className="w-full h-10 px-3 rounded-button text-sm bg-white border border-gray-200"
                  >
                    <option value="">Select quarter</option>
                    {QUARTERS.map((q) => (
                      <option key={q.value} value={q.value}>{q.label}</option>
                    ))}
                  </select>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    placeholder="Score (0-100, leave blank if skipped)"
                    value={assessmentScore}
                    onChange={(e) => setAssessmentScore(e.target.value)}
                    className="w-full h-10 px-3 rounded-button text-sm bg-white border border-gray-200"
                  />
                  <input
                    type="date"
                    value={assessmentDate}
                    onChange={(e) => setAssessmentDate(e.target.value)}
                    className="w-full h-10 px-3 rounded-button text-sm bg-white border border-gray-200"
                  />
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={() => setShowAddAssessment(false)}
                    >
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      className="flex-1"
                      onClick={handleLogAssessment}
                      disabled={savingAssessment || !assessmentQuarter}
                    >
                      {savingAssessment ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        "Save Assessment"
                      )}
                    </Button>
                  </div>
                </div>
              )}
            </Card>

            {/* Overlap Courses */}
            {status.overlap_courses && status.overlap_courses.length > 0 && (
              <Card className="p-5">
                <h2 className="text-base font-bold text-text-primary mb-3">
                  CEUs Counting for Both State + NBRC
                </h2>
                <div className="space-y-2">
                  {status.overlap_courses.map((course, i) => (
                    <div key={i} className="flex items-center gap-3 py-2 border-b border-gray-50 last:border-0">
                      <div className="w-8 h-8 rounded-full bg-accent/10 flex items-center justify-center flex-shrink-0">
                        <CheckCircle2 size={14} className="text-accent" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-text-primary truncate">{course.title}</p>
                        <p className="text-xs text-text-secondary">
                          {course.provider} · {formatDate(course.date)}
                        </p>
                      </div>
                      <span className="text-xs font-bold text-accent bg-accent/10 px-2 py-1 rounded-full">
                        +{course.credits}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* Add credential button */}
            <Button
              variant="outline"
              className="w-full"
              onClick={() => setShowAddCred(!showAddCred)}
            >
              <Plus size={16} className="mr-2" />
              Add Another NBRC Credential
            </Button>
          </>
        )}

        {/* Add Credential Form */}
        {showAddCred && (
          <Card className="p-5 space-y-3">
            <h2 className="text-base font-bold text-text-primary">Add NBRC Credential</h2>

            <div>
              <label className="text-xs text-text-secondary mb-1 block">Credential Type</label>
              <select
                value={credType}
                onChange={(e) => setCredType(e.target.value)}
                className="w-full h-10 px-3 rounded-button text-sm bg-white border border-gray-200"
              >
                {CREDENTIAL_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs text-text-secondary mb-1 block">Date Earned (approx)</label>
              <input
                type="date"
                value={earnedDate}
                onChange={(e) => setEarnedDate(e.target.value)}
                className="w-full h-10 px-3 rounded-button text-sm bg-white border border-gray-200"
              />
            </div>

            <div>
              <label className="text-xs text-text-secondary mb-1 block">CMP Cycle End Date</label>
              <input
                type="date"
                value={cycleEnd}
                onChange={(e) => setCycleEnd(e.target.value)}
                className="w-full h-10 px-3 rounded-button text-sm bg-white border border-gray-200"
                placeholder="5 years from earned date"
              />
              <p className="text-xs text-text-secondary mt-1">
                This is 5 years from when you passed your most recent NBRC exam.
              </p>
            </div>

            <div>
              <label className="text-xs text-text-secondary mb-1 block">Renewal Method</label>
              <select
                value={renewalMethod}
                onChange={(e) => setRenewalMethod(e.target.value)}
                className="w-full h-10 px-3 rounded-button text-sm bg-white border border-gray-200"
              >
                {RENEWAL_METHODS.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>

            <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
              <input
                type="checkbox"
                checked={isHighest}
                onChange={(e) => setIsHighest(e.target.checked)}
                className="rounded"
              />
              This is my highest credential
            </label>

            <div className="flex gap-2 pt-2">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => setShowAddCred(false)}
              >
                Cancel
              </Button>
              <Button
                className="flex-1"
                onClick={handleAddCredential}
                disabled={saving || !cycleEnd}
              >
                {saving ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  "Save Credential"
                )}
              </Button>
            </div>
          </Card>
        )}
      </div>

      <BottomNav />
    </div>
  );
}