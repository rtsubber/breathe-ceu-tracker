"use client";

import { useEffect, useState } from "react";
import { BottomNav } from "@/components/bottom-nav";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Download,
  ExternalLink,
  FileText,
  ArrowLeft,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import { useRouter } from "next/navigation";
import {
  getUser,
  getCEUs,
  getProgress,
  getLicenses,
  getStates,
  formatDate,
  type User,
  type CEU,
  type Progress,
  type License,
  type StateRequirement,
} from "@/lib/api";

async function downloadCEReport() {
  const token = localStorage.getItem("breathe_token");
  const res = await fetch("/api/ce-report", {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Failed to generate report");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "ce_compliance_report.pdf";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export default function CEReportPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [ceus, setCEUs] = useState<CEU[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [licenses, setLicenses] = useState<License[]>([]);
  const [boardName, setBoardName] = useState<string>("State Licensing Board");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [u, c, p, l, s] = await Promise.all([
          getUser(),
          getCEUs(),
          getProgress(),
          getLicenses(),
          getStates(),
        ]);
        if (cancelled) return;
        setUser(u);
        setCEUs(c);
        setProgress(p);
        setLicenses(l);

        // Resolve board name from primary license state
        const primaryLicense = l[0];
        if (primaryLicense) {
          const stateReq = (s as StateRequirement[]).find(
            (sr) => sr.state === primaryLicense.state.toUpperCase()
          );
          if (stateReq?.board_name) {
            setBoardName(stateReq.board_name);
          }
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load report");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const totalCredits = ceus.reduce((a, c) => a + c.credits, 0);
  const primaryLicense = licenses[0] ?? null;
  const hasTxLicense = licenses.some((l) => l.state.toUpperCase() === "TX");

  if (loading) {
    return (
      <div className="page-enter min-h-screen flex items-center justify-center">
        <Loader2 className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-enter min-h-screen pb-20">
        <div className="px-4 pt-8 pb-4 flex items-center gap-3">
          <button onClick={() => router.back()} className="p-2 -ml-2">
            <ArrowLeft size={24} className="text-text-primary" />
          </button>
          <div>
            <h1 className="text-xl font-bold text-text-primary">CE Compliance Report</h1>
          </div>
        </div>
        <div className="px-4 mt-8 text-center">
          <p className="text-danger font-medium">{error}</p>
          <p className="text-sm text-text-secondary mt-2">
            Make sure the API server is running on port 8088.
          </p>
        </div>
        <BottomNav />
      </div>
    );
  }

  return (
    <div className="page-enter min-h-screen pb-20">
      {/* Header */}
      <div className="px-4 pt-8 pb-4 flex items-center gap-3">
        <button onClick={() => router.back()} className="p-2 -ml-2">
          <ArrowLeft size={24} className="text-text-primary" />
        </button>
        <div>
          <h1 className="text-xl font-bold text-text-primary">CE Compliance Report</h1>
          <p className="text-xs text-text-secondary">
            {boardName} CEU report
          </p>
        </div>
      </div>

      {/* TX-specific Sept 1 alert — only show for TX license holders */}
      {hasTxLicense && (
        <div className="px-4 mb-4">
          <div className="bg-warning/10 border border-warning/30 rounded-button p-3 text-sm">
            <p className="text-text-primary font-medium">📅 Available for current renewal cycle</p>
            <p className="text-text-secondary text-xs mt-1">
              TMB accepts self-reported CE until September 1, 2026. After that, CE Broker verification becomes mandatory (SB 912). This report is still useful for your personal records and audit preparation.
            </p>
          </div>
        </div>
      )}

      {/* Summary card */}
      <div className="px-4 mb-4">
        <Card className="bg-gradient-to-br from-primary to-accent text-white p-5">
          <div className="flex justify-between items-center mb-4">
            <div>
              <p className="text-white/70 text-sm">License Holder</p>
              <p className="text-lg font-bold">
                {user?.name ?? "—"}
                {primaryLicense ? `, ${primaryLicense.license_type}` : ""}
              </p>
            </div>
            <div className="text-right">
              <p className="text-white/70 text-sm">License #</p>
              <p className="text-lg font-bold">{primaryLicense?.license_number ?? "—"}</p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="bg-white/10 rounded-button py-2">
              <p className="text-2xl font-bold">{totalCredits}</p>
              <p className="text-xs text-white/70">Total CEUs</p>
            </div>
            <div className="bg-white/10 rounded-button py-2">
              <p className="text-2xl font-bold">{ceus.length}</p>
              <p className="text-xs text-white/70">Courses</p>
            </div>
            <div className="bg-white/10 rounded-button py-2">
              <p className="text-2xl font-bold">{progress?.required ?? "—"}</p>
              <p className="text-xs text-white/70">Required</p>
            </div>
          </div>
        </Card>
      </div>

      {/* CEU Log Table */}
      <div className="px-4 mb-4">
        <h2 className="text-base font-bold text-text-primary mb-2">CEU Log</h2>
        <Card className="p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-text-secondary text-xs">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">Course</th>
                  <th className="text-left px-3 py-2 font-medium">Provider</th>
                  <th className="text-center px-3 py-2 font-medium">Credits</th>
                  <th className="text-left px-3 py-2 font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {ceus.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-3 py-8 text-center text-text-secondary">
                      No CEUs recorded yet
                    </td>
                  </tr>
                ) : (
                  ceus.map((ceu, i) => (
                    <tr key={ceu.id} className={i % 2 === 0 ? "bg-white" : "bg-gray-50/50"}>
                      <td className="px-3 py-2.5 font-medium text-text-primary">{ceu.title}</td>
                      <td className="px-3 py-2.5 text-text-secondary">{ceu.provider}</td>
                      <td className="px-3 py-2.5 text-center font-semibold text-primary">{ceu.credits}</td>
                      <td className="px-3 py-2.5 text-text-secondary text-xs">
                        {formatDate(ceu.completion_date)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
              {ceus.length > 0 && (
                <tfoot className="bg-primary/5 border-t-2 border-primary/20">
                  <tr>
                    <td className="px-3 py-2.5 font-bold text-text-primary" colSpan={2}>Total</td>
                    <td className="px-3 py-2.5 text-center font-bold text-primary">{totalCredits}</td>
                    <td className="px-3 py-2.5"></td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </Card>
      </div>

      {/* Certificate list */}
      {ceus.length > 0 && (
        <div className="px-4 mb-4">
          <h2 className="text-base font-bold text-text-primary mb-2">Certificates Included</h2>
          <Card className="space-y-2">
            {ceus.map((ceu) => (
              <div key={ceu.id} className="flex items-center gap-3 py-1.5">
                <div className="w-8 h-8 rounded-full bg-success/10 flex items-center justify-center flex-shrink-0">
                  <CheckCircle2 size={16} className="text-success" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-text-primary truncate">{ceu.title}</p>
                  <p className="text-xs text-text-secondary">{ceu.provider} · {ceu.credits} CEUs</p>
                </div>
                <FileText size={16} className="text-text-secondary flex-shrink-0" />
              </div>
            ))}
          </Card>
        </div>
      )}

      {/* Action buttons */}
      <div className="px-4 space-y-3 mb-4">
        <Button size="lg" className="w-full" onClick={() => downloadCEReport()}>
          <Download size={20} className="mr-1" /> Download PDF
        </Button>
        {hasTxLicense && (
          <a href="https://www.tmb.state.tx.us/online/" target="_blank" rel="noopener noreferrer">
            <Button variant="outline" size="lg" className="w-full">
              <ExternalLink size={20} className="mr-1" /> Open TMB Portal
            </Button>
          </a>
        )}
      </div>

      <div className="px-4 text-center">
        <p className="text-xs text-text-secondary">
          Report generated {new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
        </p>
      </div>

      <BottomNav />
    </div>
  );
}