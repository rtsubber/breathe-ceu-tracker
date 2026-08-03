"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Camera, FileText, ArrowLeft, Check, Loader2, AlertTriangle } from "lucide-react";
import { useRouter } from "next/navigation";
import { ceuCategories, categoryDisplay } from "@/lib/mock-data";
import { Toast } from "@/components/toast";
import {
  addCEU,
  getUser,
  uploadCertificateOCR,
  type CEUCreateInput,
  type User,
  type SubscriptionTier,
} from "@/lib/api";
import { Paywall } from "@/components/paywall";

export default function AddCEUPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"select" | "manual" | "paywall">("select");
  const [showToast, setShowToast] = useState(false);
  const [saving, setSaving] = useState(false);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [form, setForm] = useState<CEUCreateInput>({
    title: "",
    provider: "",
    credits: 0,
    completion_date: "",
    category: "clinical",
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const u = await getUser();
        if (!cancelled) setUser(u);
      } catch {
        /* free tier fallback is fine */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const tier: SubscriptionTier = user?.subscription_tier ?? "free";
  const isPro = tier === "pro" || tier === "department";

  const handleSave = async () => {
    setError(null);
    setSaving(true);
    try {
      await addCEU({
        ...form,
        credits: Number(form.credits) || 0,
        completion_date:
          form.completion_date || new Date().toISOString().slice(0, 10),
      });
      setShowToast(true);
      setTimeout(() => router.push("/dashboard"), 1200);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save CEU");
    } finally {
      setSaving(false);
    }
  };

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    setOcrLoading(true);
    try {
      const result = await uploadCertificateOCR(file);
      setForm({
        title: result.title || "",
        provider: result.provider || "",
        credits: result.credits || 0,
        completion_date: result.completion_date || "",
        category: "clinical",
      });
      setMode("manual");
    } catch (err) {
      setError(err instanceof Error ? err.message : "OCR upload failed");
    } finally {
      setOcrLoading(false);
    }
  };

  return (
    <div className="page-enter min-h-screen pb-20">
      {/* Header */}
      <div className="px-4 pt-8 pb-4 flex items-center gap-3">
        <button
          onClick={() => (mode === "manual" || mode === "paywall" ? setMode("select") : router.back())}
          className="p-2 -ml-2"
        >
          <ArrowLeft size={24} className="text-text-primary" />
        </button>
        <h1 className="text-xl font-bold text-text-primary">Add CEU</h1>
      </div>

      <Toast
        message={`✓ Saved. ${Number(form.credits) || 0} CEUs added.`}
        show={showToast}
      />

      {error && (
        <div className="px-4 mb-3">
          <div className="flex items-center gap-2 bg-danger/10 text-danger rounded-button px-3 py-2 text-sm">
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
        </div>
      )}

      {mode === "select" && (
        <div className="px-4 space-y-4">
          <button
            onClick={() => (isPro ? setMode("manual") : setMode("paywall"))}
            className="w-full text-left"
          >
            <Card className="flex items-center gap-4 p-5 hover:shadow-md transition-shadow">
              <div className="w-14 h-14 rounded-card bg-gradient-to-br from-primary to-accent flex items-center justify-center">
                {ocrLoading ? (
                  <Loader2 size={28} className="text-white animate-spin" />
                ) : (
                  <Camera size={28} className="text-white" />
                )}
              </div>
              <div className="flex-1">
                <h2 className="text-lg font-bold text-text-primary">Snap Certificate</h2>
                <p className="text-sm text-text-secondary">
                  {isPro ? "Take a photo — we'll extract details with AI" : "Take a photo — AI extracts details (Pro)"}
                </p>
              </div>
              {!isPro && (
                <span className="text-xs bg-accent/10 text-accent px-2 py-1 rounded-full font-medium">
                  PRO
                </span>
              )}
            </Card>
          </button>

          {/* Hidden file input for OCR — only functional for Pro */}
          {isPro && (
            <label className="block">
              <Card className="flex items-center gap-4 p-5 hover:shadow-md transition-shadow cursor-pointer">
                <div className="w-14 h-14 rounded-card bg-primary/10 flex items-center justify-center">
                  {ocrLoading ? (
                    <Loader2 size={28} className="text-primary animate-spin" />
                  ) : (
                    <FileText size={28} className="text-primary" />
                  )}
                </div>
                <div className="flex-1">
                  <h2 className="text-lg font-bold text-text-primary">Upload Certificate</h2>
                  <p className="text-sm text-text-secondary">Image file — OCR auto-fills the form</p>
                </div>
              </Card>
              <input
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => handleFile(e.target.files?.[0])}
              />
            </label>
          )}

          <button onClick={() => setMode("manual")} className="w-full text-left">
            <Card className="flex items-center gap-4 p-5 hover:shadow-md transition-shadow">
              <div className="w-14 h-14 rounded-card bg-gray-100 flex items-center justify-center">
                <FileText size={28} className="text-text-secondary" />
              </div>
              <div className="flex-1">
                <h2 className="text-lg font-bold text-text-primary">Enter Manually</h2>
                <p className="text-sm text-text-secondary">Type in the details yourself</p>
              </div>
            </Card>
          </button>

          <div className="mt-8 text-center">
            <p className="text-sm text-text-secondary">
              We&apos;ll auto-extract course info from photos using AI
            </p>
          </div>
        </div>
      )}

      {mode === "paywall" && (
        <div className="px-4 mt-4">
          <Paywall
            feature="Certificate OCR"
            description="Snap a photo of your certificate and we'll auto-extract the course title, provider, credits, and date. Upgrade to Pro to unlock OCR."
          />
          <button
            onClick={() => setMode("select")}
            className="mt-3 text-sm text-primary font-medium mx-auto block">
            ← Back to options
          </button>
        </div>
      )}

      {mode === "manual" && (
        <div className="px-4 space-y-4">
          {/* File input placeholder */}
          <label className="block">
            <Card className="flex flex-col items-center justify-center gap-2 p-8 border-2 border-dashed border-gray-200 hover:border-primary cursor-pointer transition-colors">
              {ocrLoading ? (
                <Loader2 size={32} className="text-primary animate-spin" />
              ) : (
                <Camera size={32} className="text-text-secondary" />
              )}
              <p className="text-sm font-medium text-text-secondary">
                {ocrLoading ? "Processing..." : "Add certificate photo (optional)"}
              </p>
            </Card>
            <input
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0])}
            />
          </label>

          {/* Form */}
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-text-secondary">Course Title</label>
              <input
                type="text"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="e.g. Mechanical Ventilation Essentials"
                className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-text-secondary">Provider</label>
              <input
                type="text"
                value={form.provider}
                onChange={(e) => setForm({ ...form, provider: e.target.value })}
                placeholder="e.g. AARC"
                className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <label className="text-sm font-medium text-text-secondary">Credits</label>
                <input
                  type="number"
                  value={form.credits || ""}
                  onChange={(e) => setForm({ ...form, credits: Number(e.target.value) })}
                  placeholder="4"
                  className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-text-secondary">Completion Date</label>
                <input
                  type="date"
                  value={form.completion_date}
                  onChange={(e) => setForm({ ...form, completion_date: e.target.value })}
                  className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary"
                />
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-text-secondary">Category</label>
              <select
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                className="w-full h-12 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary bg-white"
              >
                {ceuCategories.map((cat) => {
                  // map display back to canonical key
                  const key =
                    Object.keys(categoryDisplay).find(
                      (k) => categoryDisplay[k] === cat,
                    ) ?? cat;
                  return (
                    <option key={cat} value={key}>
                      {cat}
                    </option>
                  );
                })}
              </select>
            </div>
          </div>

          <Button
            size="lg"
            className="w-full"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? (
              <>
                <Loader2 size={20} className="mr-1 animate-spin" /> Saving...
              </>
            ) : (
              <>
                <Check size={20} className="mr-1" /> Save CEU
              </>
            )}
          </Button>
        </div>
      )}
    </div>
  );
}