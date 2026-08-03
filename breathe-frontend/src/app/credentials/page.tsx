"use client";

import { useEffect, useState } from "react";
import { BottomNav } from "@/components/bottom-nav";
import { Card } from "@/components/ui/card";
import {
  Award,
  ShieldCheck,
  AlertTriangle,
  XCircle,
  Plus,
  Loader2,
  X,
  Pencil,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { getCredentials, formatDate, credStatus, type Credential } from "@/lib/api";

export default function CredentialsPage() {
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [newCred, setNewCred] = useState({
    type: "",
    expiry_date: "",
    cycle_years: 2,
    issuing_org: "NBRC",
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getCredentials();
        if (!cancelled) setCredentials(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load credentials");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const statusConfig = {
    current: {
      color: "text-success",
      bg: "bg-success/10",
      dot: "bg-success",
      label: "Active",
      icon: ShieldCheck,
    },
    expiring: {
      color: "text-warning",
      bg: "bg-warning/10",
      dot: "bg-warning",
      label: "Expiring Soon",
      icon: AlertTriangle,
    },
    expired: {
      color: "text-danger",
      bg: "bg-danger/10",
      dot: "bg-danger",
      label: "Expired",
      icon: XCircle,
    },
  } as const;

  const nbrcCreds = credentials.filter((c) => c.issuing_org === "NBRC");
  const certs = credentials.filter((c) => c.issuing_org !== "NBRC");

  const getToken = () => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("breathe_token");
    }
    return null;
  };

  const handleSaveCredential = async () => {
    if (!newCred.type || !newCred.expiry_date) {
      setError("Please fill in all fields");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const token = getToken();
      const url = editingId ? `/api/credentials/${editingId}` : "/api/credentials";
      const method = editingId ? "PUT" : "POST";
      const res = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(newCred),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to save credential");
      }
      const saved = await res.json();
      if (editingId) {
        setCredentials(credentials.map((c) => (c.id === editingId ? saved : c)));
      } else {
        setCredentials([...credentials, saved]);
      }
      setShowAddForm(false);
      setEditingId(null);
      setNewCred({ type: "", expiry_date: "", cycle_years: 2, issuing_org: "NBRC" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save credential");
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (cred: Credential) => {
    setEditingId(cred.id);
    setNewCred({
      type: cred.type,
      expiry_date: cred.expiry_date,
      cycle_years: cred.cycle_years,
      issuing_org: cred.issuing_org,
    });
    setShowAddForm(true);
  };

  const handleDelete = async (credId: number) => {
    setDeleting(credId);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(`/api/credentials/${credId}`, {
        method: "DELETE",
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to delete credential");
      }
      setCredentials(credentials.filter((c) => c.id !== credId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete credential");
    } finally {
      setDeleting(null);
    }
  };

  const handleCancelForm = () => {
    setShowAddForm(false);
    setEditingId(null);
    setNewCred({ type: "", expiry_date: "", cycle_years: 2, issuing_org: "NBRC" });
  };

  const renderCredentialCard = (cred: Credential) => {
    const status = credStatus(cred.expiry_date);
    const cfg = statusConfig[status];
    const Icon = cfg.icon;
    const isNbrc = cred.issuing_org === "NBRC";
    return (
      <Card key={cred.id} className="flex items-center gap-3 py-3">
        <div
          className={`w-12 h-12 rounded-card ${cfg.bg} flex items-center justify-center flex-shrink-0`}
        >
          {isNbrc ? <Award size={24} className={cfg.color} /> : <ShieldCheck size={24} className={cfg.color} />}
        </div>
        <div className="flex-1">
          <p className="text-base font-bold text-text-primary">{cred.type}</p>
          <p className="text-xs text-text-secondary">
            {cred.issuing_org} · Expires {formatDate(cred.expiry_date)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className={`flex items-center gap-1.5 ${cfg.color}`}>
            <Icon size={16} />
            <span className="text-xs font-medium">{cfg.label}</span>
          </div>
          <button
            onClick={() => handleEdit(cred)}
            className="p-2 rounded-lg text-text-secondary hover:bg-primary/10 hover:text-primary transition-colors"
            title="Edit"
          >
            <Pencil size={14} />
          </button>
          <button
            onClick={() => handleDelete(cred.id)}
            disabled={deleting === cred.id}
            className="p-2 rounded-lg text-text-secondary hover:bg-danger/10 hover:text-danger transition-colors"
            title="Delete"
          >
            {deleting === cred.id ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Trash2 size={14} />
            )}
          </button>
        </div>
      </Card>
    );
  };

  if (loading) {
    return (
      <div className="page-enter min-h-screen pb-20">
        <div className="px-4 pt-8 pb-4">
          <h1 className="text-2xl font-bold text-text-primary">Credentials</h1>
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
      <div className="px-4 pt-8 pb-4">
        <h1 className="text-2xl font-bold text-text-primary">Credentials</h1>
        <p className="text-sm text-text-secondary mt-1">
          Track licenses and certifications
        </p>
      </div>

      {error && (
        <div className="px-4 mb-3">
          <div className="flex items-center gap-2 bg-danger/10 text-danger rounded-button px-3 py-2 text-sm">
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* NBRC Credentials */}
      <div className="px-4 mb-6">
        <div className="flex items-center gap-2 mb-3">
          <Award size={18} className="text-accent" />
          <h2 className="text-base font-bold text-text-primary">NBRC Credentials</h2>
        </div>
        <div className="space-y-2">
          {nbrcCreds.length === 0 ? (
            <Card className="py-4 text-center text-text-secondary text-sm">
              No NBRC credentials yet. Tap "Add Credential" below to add your RRT, NPS, etc.
            </Card>
          ) : (
            nbrcCreds.map(renderCredentialCard)
          )}
        </div>
      </div>

      {/* Certifications */}
      <div className="px-4 mb-6">
        <div className="flex items-center gap-2 mb-3">
          <ShieldCheck size={18} className="text-primary" />
          <h2 className="text-base font-bold text-text-primary">Certifications</h2>
        </div>
        <div className="space-y-2">
          {certs.length === 0 ? (
            <Card className="py-4 text-center text-text-secondary text-sm">
              No certifications yet. Add ACLS, BLS, PALS, NRP, etc.
            </Card>
          ) : (
            certs.map(renderCredentialCard)
          )}
        </div>
      </div>

      {/* Add/Edit credential form */}
      {showAddForm && (
        <div className="px-4 mb-6">
          <Card className="p-4 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-text-primary">
                {editingId ? "Edit Credential" : "Add Credential"}
              </h3>
              <button
                type="button"
                onClick={handleCancelForm}
                className="text-text-secondary hover:text-text-primary"
              >
                <X size={18} />
              </button>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-text-secondary">Category</label>
              <select
                value={newCred.issuing_org}
                onChange={(e) => setNewCred({ ...newCred, issuing_org: e.target.value })}
                className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary bg-white"
              >
                <option value="NBRC">NBRC Credential (RRT, CRT, NPS, ACCS, SDS)</option>
                <option value="AHA">AHA Certification (ACLS, BLS, PALS)</option>
                <option value="AAP">AAP Certification (NRP)</option>
                <option value="Other">Other</option>
              </select>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-text-secondary">Credential Type</label>
              {newCred.issuing_org === "NBRC" ? (
                <select
                  value={newCred.type}
                  onChange={(e) => setNewCred({ ...newCred, type: e.target.value })}
                  className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary bg-white"
                >
                  <option value="" disabled>Select credential</option>
                  <option value="RRT">RRT — Registered Respiratory Therapist</option>
                  <option value="CRT">CRT — Certified Respiratory Therapist</option>
                  <option value="NPS">NPS — Neonatal/Pediatric Specialist</option>
                  <option value="ACCS">ACCS — Adult Critical Care Specialist</option>
                  <option value="SDS">SDS — Sleep Disorders Specialist</option>
                  <option value="RPFT">RPFT — Registered Pulmonary Function Technologist</option>
                  <option value="AE-C">AE-C — Asthma Educator Certified</option>
                </select>
              ) : (
                <input
                  type="text"
                  value={newCred.type}
                  onChange={(e) => setNewCred({ ...newCred, type: e.target.value })}
                  placeholder="e.g. ACLS, BLS, PALS, NRP"
                  className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary"
                />
              )}
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-text-secondary">Expiry Date</label>
              <input
                type="date"
                value={newCred.expiry_date}
                onChange={(e) => setNewCred({ ...newCred, expiry_date: e.target.value })}
                className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary"
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-text-secondary">Renewal Cycle (years)</label>
              <select
                value={newCred.cycle_years}
                onChange={(e) => setNewCred({ ...newCred, cycle_years: Number(e.target.value) })}
                className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary bg-white"
              >
                <option value={2}>2 years</option>
                <option value={3}>3 years</option>
                <option value={5}>5 years</option>
              </select>
            </div>

            <Button
              size="lg"
              className="w-full"
              onClick={handleSaveCredential}
              disabled={saving || !newCred.type || !newCred.expiry_date}
            >
              {saving ? (
                <>
                  <Loader2 size={20} className="mr-1 animate-spin" /> Saving...
                </>
              ) : (
                <>
                  <Plus size={20} className="mr-1" /> {editingId ? "Update Credential" : "Save Credential"}
                </>
              )}
            </Button>
          </Card>
        </div>
      )}

      {/* Add credential button */}
      <div className="px-4 mb-6">
        <Button
          variant="outline"
          size="lg"
          className="w-full"
          onClick={() => {
            if (showAddForm) {
              handleCancelForm();
            } else {
              setShowAddForm(true);
            }
          }}
        >
          <Plus size={20} className="mr-1" /> {showAddForm ? "Cancel" : "Add Credential"}
        </Button>
      </div>

      <BottomNav />
    </div>
  );
}