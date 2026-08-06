"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import {
  Award,
  Calendar,
  Clock,
  AlertCircle,
  CheckCircle2,
  TrendingUp,
  ChevronRight,
  Loader2,
  Target,
} from "lucide-react";
import {
  getNBRCStatus,
  getAssessmentReminder,
  formatDate,
  daysUntil,
  type NBRCStatus,
  type AssessmentReminder,
} from "@/lib/api";

export function NBRCStatusCard() {
  const [status, setStatus] = useState<NBRCStatus | null>(null);
  const [reminder, setReminder] = useState<AssessmentReminder | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [s, r] = await Promise.all([
          getNBRCStatus(),
          getAssessmentReminder(),
        ]);
        if (cancelled) return;
        setStatus(s);
        setReminder(r);
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Failed to load NBRC status");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <Card className="flex items-center justify-center py-8">
        <Loader2 className="animate-spin text-primary" size={24} />
      </Card>
    );
  }

  if (error || !status) {
    return (
      <Card className="py-4 text-center">
        <AlertCircle className="mx-auto text-danger mb-2" size={20} />
        <p className="text-sm text-text-secondary">
          {error ?? "Unable to load NBRC status"}
        </p>
      </Card>
    );
  }

  // No NBRC credentials yet
  if (!status.has_nbrc) {
    return (
      <Link href="/nbrc" className="block">
        <Card className="flex items-center gap-3 p-4 hover:shadow-md transition-shadow cursor-pointer border-2 border-dashed border-accent/30">
          <div className="w-10 h-10 rounded-full bg-accent/10 flex items-center justify-center">
            <Award size={20} className="text-accent" />
          </div>
          <div className="flex-1">
            <p className="text-sm font-semibold text-text-primary">NBRC Credential Tracking</p>
            <p className="text-xs text-text-secondary">
              Add your RRT/NPS to track your 5-year CMP cycle
            </p>
          </div>
          <ChevronRight size={18} className="text-text-secondary" />
        </Card>
      </Link>
    );
  }

  const daysLeft = status.days_remaining ?? 0;
  const progressPct = status.progress_pct ?? 0;
  const ceRequired = status.ce_required ?? 30;
  const ceEarned = status.ce_from_state_license ?? 0;
  const additionalCe = status.additional_ce_needed ?? 0;
  const onTrack = status.on_track ?? false;

  // Progress ring for NBRC cycle (5-year)
  const ringSize = 120;
  const ringStroke = 10;
  const radius = (ringSize - ringStroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const ringOffset = circumference * (1 - progressPct / 100);

  return (
    <div className="space-y-3">
      {/* NBRC Credentials + Cycle Progress */}
      <Card className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Award size={16} className="text-accent" />
              <h3 className="text-sm font-bold text-text-primary">NBRC CMP</h3>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {status.credentials
                .filter((cred, _i, arr) => {
                  // Don't show CRT if user has RRT or higher
                  const hasRRTOrHigher = arr.some(c => ["RRT", "RRT-NPS", "ACCS", "SDS", "RPFT", "AE-C"].includes(c.type));
                  return !(hasRRTOrHigher && cred.type === "CRT");
                })
                .map((cred, i) => (
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
          </div>
          {/* Mini progress ring */}
          <div className="relative" style={{ width: ringSize, height: ringSize }}>
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
                stroke="url(#nbrcGradient)"
                strokeWidth={ringStroke}
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={ringOffset}
              />
              <defs>
                <linearGradient id="nbrcGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#7C3AED" />
                  <stop offset="100%" stopColor="#2563EB" />
                </linearGradient>
              </defs>
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-lg font-bold text-text-primary">
                {Math.round(progressPct)}%
              </span>
              <span className="text-[10px] text-text-secondary">5yr cycle</span>
            </div>
          </div>
        </div>

        {/* Cycle dates */}
        <div className="flex items-center gap-2 text-xs text-text-secondary mb-3">
          <Calendar size={12} />
          <span>
            {formatDate(status.cycle_start)} → {formatDate(status.cycle_end)}
          </span>
          <span className="ml-auto font-medium text-text-primary">
            {daysLeft > 0 ? `${daysLeft} days left` : "Expired"}
          </span>
        </div>

        {/* ⭐ CE Overlap Insight — the killer feature */}
        <div
          className={`rounded-card p-3 mb-3 ${
            additionalCe === 0
              ? "bg-success/10 border border-success/20"
              : "bg-accent/10 border border-accent/20"
          }`}
        >
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp size={14} className="text-accent" />
            <p className="text-xs font-bold text-text-primary">CE Overlap Savings</p>
          </div>
          {ceRequired > 0 ? (
            <p className="text-sm text-text-primary">
              Your <span className="font-bold text-accent">{ceEarned.toFixed(1)} state CEUs</span>{" "}
              count toward your NBRC{" "}
              <span className="font-bold">{ceRequired} CE</span> requirement.
              {additionalCe > 0 ? (
                <>
                  {" "}You only need{" "}
                  <span className="font-bold text-warning">{additionalCe} more CE</span> beyond
                  your state license.
                </>
              ) : (
                <span className="font-bold text-success"> You\u2019re fully covered! ✓</span>
              )}
            </p>
          ) : (
            <p className="text-sm text-text-primary">
              High assessment scores — no additional CE needed this cycle!
            </p>
          )}
        </div>

        {/* Status indicator */}
        <div className="flex items-center gap-2">
          {onTrack ? (
            <div className="inline-flex items-center gap-1.5 bg-success/10 text-success px-3 py-1.5 rounded-full text-xs font-medium">
              <CheckCircle2 size={12} />
              On track for renewal
            </div>
          ) : (
            <div className="inline-flex items-center gap-1.5 bg-warning/10 text-warning px-3 py-1.5 rounded-full text-xs font-medium">
              <Clock size={12} />
              Attention needed
            </div>
          )}
          <Link href="/nbrc" className="ml-auto">
            <Button variant="outline" size="sm">
              Details
              <ChevronRight size={14} className="ml-1" />
            </Button>
          </Link>
        </div>
      </Card>

      {/* Assessment Reminder */}
      {reminder && (
        <Card className="p-3">
          <div className="flex items-center gap-3">
            <div
              className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 ${
                reminder.status === "completed"
                  ? "bg-success/10"
                  : "bg-warning/10"
              }`}
            >
              {reminder.status === "completed" ? (
                <CheckCircle2 size={16} className="text-success" />
              ) : (
                <Target size={16} className="text-warning" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-text-primary truncate">
                {reminder.message}
              </p>
              <p className="text-xs text-text-secondary">
                Next: {reminder.next_window} · {reminder.days_until_next} days
              </p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}