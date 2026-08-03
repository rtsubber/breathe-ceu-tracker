"use client";

import { useEffect, useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  ArrowLeft,
  Loader2,
  AlertTriangle,
  RefreshCw,
  ExternalLink,
  Gift,
  Search,
  CheckCircle2,
} from "lucide-react";
import { useRouter } from "next/navigation";
import {
  getUser,
  getFreeCourses,
  triggerFreeCourseScan,
  formatDate,
  type User,
  type FreeCourse,
  type SubscriptionTier,
} from "@/lib/api";
import { Paywall } from "@/components/paywall";

// Source display config
const SOURCE_CONFIG: Record<string, { label: string; color: string }> = {
  aarc_journal: { label: "AARC Journal", color: "bg-blue-500/10 text-blue-600" },
  aarc_webcasts: { label: "AARC Webcasts", color: "bg-blue-500/10 text-blue-600" },
  at_lectures: { label: "A&T Lectures", color: "bg-purple-500/10 text-purple-600" },
  medline: { label: "Medline University", color: "bg-teal-500/10 text-teal-600" },
  rtconnection: { label: "RTConnection", color: "bg-orange-500/10 text-orange-600" },
  passy_muir: { label: "Passy-Muir", color: "bg-green-500/10 text-green-600" },
  vapotherm: { label: "Vapotherm", color: "bg-cyan-500/10 text-cyan-600" },
  aarc: { label: "AARC", color: "bg-blue-500/10 text-blue-600" },
  nbrc: { label: "NBRC", color: "bg-indigo-500/10 text-indigo-600" },
  other: { label: "Other", color: "bg-gray-500/10 text-gray-600" },
};

export default function FreeCoursesPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [courses, setCourses] = useState<FreeCourse[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [u, coursesResp] = await Promise.all([
          getUser().catch(() => null),
          getFreeCourses(),
        ]);
        if (cancelled) return;
        setUser(u);
        setCourses(coursesResp.courses || []);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const tier: SubscriptionTier = user?.subscription_tier ?? "free";
  const isPro = tier === "pro" || tier === "department";

  // Group courses by source
  const groupedCourses = useMemo(() => {
    const groups: Record<string, FreeCourse[]> = {};
    for (const c of courses) {
      if (!groups[c.source]) groups[c.source] = [];
      groups[c.source].push(c);
    }
    return groups;
  }, [courses]);

  const totalCredits = useMemo(
    () => courses.reduce((sum, c) => sum + (c.credits || 0), 0),
    [courses]
  );

  const handleScan = async () => {
    setScanning(true);
    setError(null);
    setScanResult(null);
    try {
      const result = await triggerFreeCourseScan();
      setScanResult(
        result.added > 0
          ? `Found ${result.added} new free course${result.added === 1 ? "" : "s"}!`
          : `Scanned ${result.sources_checked} sources — no new courses since last scan.`
      );
      // Refresh the list
      const fresh = await getFreeCourses();
      setCourses(fresh.courses || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  return (
    <div className="page-enter min-h-screen pb-20">
      {/* Header */}
      <div className="bg-gradient-to-br from-primary to-accent px-6 pt-12 pb-8 text-white rounded-b-[32px]">
        <div className="flex items-center gap-3 mb-2">
          <button onClick={() => router.back()} className="p-2 -ml-2">
            <ArrowLeft size={24} className="text-white" />
          </button>
          <h1 className="text-2xl font-bold">Free CEU Courses</h1>
        </div>
        <p className="text-white/80 text-sm">
          We scan AARC, A&amp;T Lectures, Medline, Passy-Muir, and more for free
          credit opportunities — a feature no competitor offers.
        </p>
        {courses.length > 0 && (
          <div className="mt-4 flex items-center gap-4">
            <div className="bg-white/15 rounded-lg px-3 py-1.5">
              <span className="text-2xl font-bold">{courses.length}</span>
              <span className="text-sm ml-1 text-white/80">courses</span>
            </div>
            <div className="bg-white/15 rounded-lg px-3 py-1.5">
              <span className="text-2xl font-bold">{totalCredits.toFixed(1)}</span>
              <span className="text-sm ml-1 text-white/80">free CEUs</span>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="px-4 mt-4">
          <div className="flex items-center gap-2 bg-danger/10 text-danger rounded-button px-3 py-2 text-sm">
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
        </div>
      )}

      {scanResult && (
        <div className="px-4 mt-4">
          <div className="flex items-center gap-2 bg-success/10 text-success rounded-button px-3 py-2 text-sm">
            <CheckCircle2 size={16} />
            <span>{scanResult}</span>
          </div>
        </div>
      )}

      {/* Scan button — always visible, no paywall for scanning */}
      <div className="px-4 mt-6">
        <Button
          size="lg"
          variant="outline"
          className="w-full"
          onClick={handleScan}
          disabled={scanning}
        >
          {scanning ? (
            <>
              <Loader2 size={18} className="mr-1 animate-spin" /> Scanning 7
              sources…
            </>
          ) : (
            <>
              <Search size={18} className="mr-1" /> Scan for Free Courses
            </>
          )}
        </Button>
        <p className="text-xs text-text-secondary text-center mt-2">
          Scans AARC, A&amp;T Lectures, Medline, Passy-Muir, RTConnection &amp;
          Vapotherm
        </p>
      </div>

      {/* Free course list — public, no paywall */}
      <div className="px-4 mt-6 space-y-4">
        {courses.length === 0 ? (
          <Card className="p-6 text-center">
            <Gift size={32} className="mx-auto text-accent mb-2" />
            <p className="text-sm text-text-secondary">
              No free courses found yet. Tap &quot;Scan&quot; to check now — we
              also scan automatically every week.
            </p>
          </Card>
        ) : (
          <>
            {/* Summary */}
            <div className="flex items-center gap-2 mb-2">
              <Gift size={18} className="text-accent" />
              <h2 className="text-lg font-bold text-text-primary">
                {courses.length} Free Course{courses.length === 1 ? "" : "s"} Available
              </h2>
            </div>

            {/* Grouped by source */}
            {Object.entries(groupedCourses).map(([source, sourceCourses]) => {
              const config = SOURCE_CONFIG[source] || SOURCE_CONFIG.other;
              return (
                <div key={source} className="space-y-2">
                  <div className="flex items-center gap-2 mt-3 mb-1">
                    <span
                      className={`text-xs font-medium px-2 py-0.5 rounded-full ${config.color}`}
                    >
                      {config.label}
                    </span>
                    <span className="text-xs text-text-secondary">
                      {sourceCourses.length} course{sourceCourses.length === 1 ? "" : "s"}
                    </span>
                  </div>
                  {sourceCourses.map((course) => (
                    <Card key={course.id} className="p-4">
                      <div className="flex items-start gap-3">
                        <div className="w-10 h-10 rounded-card bg-accent/10 flex items-center justify-center flex-shrink-0">
                          <Gift size={20} className="text-accent" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <h3 className="text-sm font-bold text-text-primary">
                            {course.title}
                          </h3>
                          <p className="text-xs text-text-secondary mt-0.5">
                            {course.provider}
                            {course.credits > 0 &&
                              ` · ${course.credits} CEU${course.credits === 1 ? "" : "s"}`}
                            {` · ${formatDate(course.alert_date)}`}
                          </p>
                          <div className="flex items-center gap-2 mt-2">
                            <span className="text-xs bg-success/10 text-success px-2 py-0.5 rounded-full font-medium">
                              FREE
                            </span>
                          </div>
                          {course.url && (
                            <a
                              href={course.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 mt-2 text-sm text-primary font-medium hover:underline"
                            >
                              Visit Course <ExternalLink size={12} />
                            </a>
                          )}
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
              );
            })}
          </>
        )}
      </div>

      {/* Upgrade nudge for non-Pro users (non-blocking) */}
      {!isPro && courses.length > 0 && (
        <div className="px-4 mt-8">
          <div className="bg-gradient-to-br from-primary/5 to-accent/5 rounded-card p-4 border border-primary/10">
            <div className="flex items-center gap-2 mb-1">
              <RefreshCw size={16} className="text-primary" />
              <h3 className="text-sm font-bold text-text-primary">
                Want instant alerts?
              </h3>
            </div>
            <p className="text-xs text-text-secondary mb-2">
              Upgrade to Pro to get push notifications the moment free courses
              drop — before they fill up or expire.
            </p>
            <Button
              size="sm"
              className="w-full"
              onClick={() => router.push("/pricing")}
            >
              Upgrade to Pro
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}