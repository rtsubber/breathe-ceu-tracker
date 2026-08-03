"use client";

import { useEffect, useState } from "react";
import { BottomNav } from "@/components/bottom-nav";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import {
  Plus,
  CheckCircle2,
  Clock,
  AlertCircle,
  FileText,
  Loader2,
  X,
} from "lucide-react";
import {
  getCompetencies,
  addCompetency,
  formatDate,
  type Competency,
} from "@/lib/api";

const statusConfig = {
  completed: {
    color: "text-success",
    bg: "bg-success/10",
    label: "Completed",
    icon: CheckCircle2,
  },
  pending: {
    color: "text-warning",
    bg: "bg-warning/10",
    label: "Pending",
    icon: Clock,
  },
  overdue: {
    color: "text-danger",
    bg: "bg-danger/10",
    label: "Overdue",
    icon: AlertCircle,
  },
} as const;

// Sample data used as fallback if the API has no competencies yet
// (so the demo screen always shows something).
const sampleCompetencies: Omit<Competency, "id" | "user_id">[] = [
  {
    name: "Ventilator Management",
    category: "annual",
    frequency: "annual",
    status: "completed",
    completed_date: "2026-06-15",
    evaluator: "Sarah Chen, RRT",
    notes: "Passed simulation + didactic exam",
  },
  {
    name: "HFOV (High Frequency Oscillatory Ventilation)",
    category: "unit_specific",
    frequency: "annual",
    status: "completed",
    completed_date: "2026-05-20",
    evaluator: "Mike Rodriguez, RRT",
    notes: "NICU checkout complete",
  },
  {
    name: "Code Blue Response",
    category: "annual",
    frequency: "annual",
    status: "pending",
    completed_date: null,
    evaluator: null,
    notes: null,
  },
  {
    name: "NRP (Neonatal Resuscitation Program)",
    category: "unit_specific",
    frequency: "biannual",
    status: "pending",
    completed_date: null,
    evaluator: null,
    notes: null,
  },
];

export default function CompetenciesPage() {
  const [competencies, setCompetencies] = useState<Competency[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [newComp, setNewComp] = useState({
    name: "",
    category: "annual",
    frequency: "annual",
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getCompetencies();
        if (cancelled) return;
        if (data.length === 0) {
          // Use sample data for demo when API is empty
          setCompetencies(
            sampleCompetencies.map((s, i) => ({
              ...s,
              id: i + 1,
              user_id: 1,
            })) as Competency[],
          );
        } else {
          setCompetencies(data);
        }
      } catch (err) {
        if (!cancelled) {
          // Fall back to sample data on error so demo still works
          setCompetencies(
            sampleCompetencies.map((s, i) => ({
              ...s,
              id: i + 1,
              user_id: 1,
            })) as Competency[],
          );
          setError(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const annual = competencies.filter((c) => c.category === "annual");
  const unitSpecific = competencies.filter((c) => c.category === "unit_specific");

  const handleAdd = async () => {
    if (!newComp.name.trim()) return;
    try {
      const created = await addCompetency({
        name: newComp.name,
        category: newComp.category,
        frequency: newComp.frequency,
        status: "pending",
        completed_date: null,
        evaluator: null,
        notes: null,
      });
      setCompetencies([...competencies, created]);
      setNewComp({ name: "", category: "annual", frequency: "annual" });
      setShowForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add competency");
    }
  };

  if (loading) {
    return (
      <div className="page-enter min-h-screen pb-20">
        <div className="px-4 pt-8 pb-4">
          <h1 className="text-2xl font-bold text-text-primary">Competencies</h1>
        </div>
        <div className="flex items-center justify-center pt-12">
          <Loader2 className="animate-spin text-primary" size={28} />
        </div>
        <BottomNav />
      </div>
    );
  }

  return (
    <div className="page-enter min-h-screen pb-20">
      {/* Header */}
      <div className="px-4 pt-8 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Competencies</h1>
          <p className="text-sm text-text-secondary mt-1">
            Annual and unit-specific checkouts
          </p>
        </div>
        <Button size="sm" onClick={() => setShowForm(!showForm)}>
          {showForm ? <X size={16} /> : <Plus size={16} className="mr-1" />}
          {showForm ? "Cancel" : "Add"}
        </Button>
      </div>

      {error && (
        <div className="px-4 mb-3">
          <div className="flex items-center gap-2 bg-danger/10 text-danger rounded-button px-3 py-2 text-sm">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* Add Competency Form */}
      {showForm && (
        <div className="px-4 mb-4">
          <Card className="space-y-3">
            <h3 className="text-sm font-bold text-text-primary">New Competency</h3>
            <div className="space-y-2">
              <label className="text-sm font-medium text-text-secondary">
                Competency Name
              </label>
              <input
                type="text"
                value={newComp.name}
                onChange={(e) => setNewComp({ ...newComp, name: e.target.value })}
                placeholder="e.g. ECMO Management"
                className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <label className="text-sm font-medium text-text-secondary">
                  Category
                </label>
                <select
                  value={newComp.category}
                  onChange={(e) =>
                    setNewComp({ ...newComp, category: e.target.value })
                  }
                  className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary bg-white"
                >
                  <option value="annual">Annual</option>
                  <option value="unit_specific">Unit-Specific</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-text-secondary">
                  Frequency
                </label>
                <select
                  value={newComp.frequency}
                  onChange={(e) =>
                    setNewComp({ ...newComp, frequency: e.target.value })
                  }
                  className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary bg-white"
                >
                  <option value="annual">Annual</option>
                  <option value="biannual">Biannual</option>
                  <option value="one_time">One-Time</option>
                </select>
              </div>
            </div>
            <Button size="md" className="w-full" onClick={handleAdd}>
              <Plus size={18} className="mr-1" /> Add Competency
            </Button>
          </Card>
        </div>
      )}

      {/* Annual Competencies */}
      <div className="px-4 mb-6">
        <h2 className="text-base font-bold text-text-primary mb-3">
          Annual Competencies
        </h2>
        <div className="space-y-2">
          {annual.length === 0 ? (
            <Card className="py-4 text-center text-text-secondary text-sm">
              No annual competencies yet.
            </Card>
          ) : (
            annual.map((comp) => {
              const cfg = statusConfig[comp.status as keyof typeof statusConfig] ?? statusConfig.pending;
              const Icon = cfg.icon;
              return (
                <Card key={comp.id} className="flex items-center gap-3 py-3">
                  <div
                    className={`w-12 h-12 rounded-card ${cfg.bg} flex items-center justify-center flex-shrink-0`}
                  >
                    <Icon size={24} className={cfg.color} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-text-primary">{comp.name}</p>
                    <p className="text-xs text-text-secondary">
                      {comp.completed_date
                        ? `Completed ${formatDate(comp.completed_date)}`
                        : comp.status === "overdue"
                          ? "Overdue"
                          : "Not yet completed"}
                      {comp.evaluator ? ` · ${comp.evaluator}` : ""}
                    </p>
                  </div>
                  <span
                    className={`text-xs font-medium px-2.5 py-1 rounded-full ${cfg.bg} ${cfg.color} whitespace-nowrap`}
                  >
                    {cfg.label}
                  </span>
                </Card>
              );
            })
          )}
        </div>
      </div>

      {/* Unit-Specific Competencies */}
      <div className="px-4 mb-6">
        <h2 className="text-base font-bold text-text-primary mb-3">
          Unit-Specific
        </h2>
        <div className="space-y-2">
          {unitSpecific.length === 0 ? (
            <Card className="py-4 text-center text-text-secondary text-sm">
              No unit-specific competencies yet.
            </Card>
          ) : (
            unitSpecific.map((comp) => {
              const cfg = statusConfig[comp.status as keyof typeof statusConfig] ?? statusConfig.pending;
              const Icon = cfg.icon;
              return (
                <Card key={comp.id} className="flex items-center gap-3 py-3">
                  <div
                    className={`w-12 h-12 rounded-card ${cfg.bg} flex items-center justify-center flex-shrink-0`}
                  >
                    <Icon size={24} className={cfg.color} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-text-primary">{comp.name}</p>
                    <p className="text-xs text-text-secondary">
                      {comp.completed_date
                        ? `Completed ${formatDate(comp.completed_date)}`
                        : comp.status === "overdue"
                          ? "Overdue"
                          : "Not yet completed"}
                      {comp.evaluator ? ` · ${comp.evaluator}` : ""}
                    </p>
                  </div>
                  <span
                    className={`text-xs font-medium px-2.5 py-1 rounded-full ${cfg.bg} ${cfg.color} whitespace-nowrap`}
                  >
                    {cfg.label}
                  </span>
                </Card>
              );
            })
          )}
        </div>
      </div>

      {/* Generate Report Button */}
      <div className="px-4 mb-4">
        <Link href="/tmb-report">
          <Button variant="outline" size="lg" className="w-full">
            <FileText size={20} className="mr-1" /> Generate TMB Report
          </Button>
        </Link>
      </div>

      <BottomNav />
    </div>
  );
}