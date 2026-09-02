"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────

type CEBrokerSettings = {
  encryption_enabled: boolean;
  cebroker_email: {
    has_email: boolean;
    email_masked: string | null;
  };
  cebroker_password: {
    has_password: boolean;
  };
  licenses: Array<{
    id: number;
    state: string;
    license_type: string;
    license_number: string;
    expiry_date: string | null;
  }>;
  sync_status: {
    total_ceus: number;
    synced: number;
    unsynced: number;
    all_synced: boolean;
  };
};

type SyncLog = {
  id: number;
  ceu_id: number;
  ceu_title: string;
  status: string;
  attempt_count: number;
  error_message: string | null;
  submitted_at: string | null;
  created_at: string | null;
};

// ─── Component ─────────────────────────────────────────────────

export default function IntegrationsSettingsPage() {
  const apiGet = (path: string) => apiFetch<any>(path);
  const apiPut = (path: string, data: any) => apiFetch<any>(path, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  const apiPost = (path: string, data: any) => apiFetch<any>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  const [settings, setSettings] = useState<any>(null);
  const [syncLogs, setSyncLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Form state
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  // OTP connect flow state
  const [otpSent, setOtpSent] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [showOtp, setShowOtp] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  async function loadSettings() {
    setLoading(true);
    try {
      const [settingsRes, logRes] = await Promise.all([
        apiGet("/api/cebroker/settings"),
        apiGet("/api/cebroker/sync-log?limit=10"),
      ]);
      setSettings(settingsRes);
      setSyncLogs((logRes as any)?.logs || []);
      if ((settingsRes as any)?.cebroker_email?.email_masked) {
        setEmail((settingsRes as any).cebroker_email.email_masked);
      }
    } catch (e) {
      setMessage({ type: "error", text: "Failed to load settings" });
    }
    setLoading(false);
  }

  async function saveEmail() {
    if (!email || !email.includes("@")) {
      setMessage({ type: "error", text: "Enter a valid email address" });
      return;
    }
    setSaving(true);
    try {
      await apiPut("/api/cebroker/email", { cebroker_email: email });
      setMessage({ type: "success", text: "CE Broker email saved" });
      loadSettings();
    } catch (e: any) {
      setMessage({ type: "error", text: e?.message || "Failed to save email" });
    }
    setSaving(false);
  }

  async function savePassword() {
    if (!password || password.length < 4) {
      setMessage({ type: "error", text: "Password must be at least 4 characters" });
      return;
    }
    setSaving(true);
    try {
      await apiPut("/api/cebroker/password", { cebroker_password: password });
      setMessage({ type: "success", text: "CE Broker password saved (encrypted)" });
      setPassword("");
      loadSettings();
    } catch (e: any) {
      setMessage({ type: "error", text: e?.message || "Failed to save password" });
    }
    setSaving(false);
  }

  async function sendOtp() {
    setConnecting(true);
    setMessage(null);
    try {
      const res = await apiPost("/api/cebroker/send-otp",
        email && !email.includes("***") ? { cebroker_email: email } : {});
      setOtpSent(true);
      setShowOtp(true);
      setMessage({ type: "success", text: res?.message || `Code sent to ${res?.email_masked || "your email"}` });
    } catch (e: any) {
      setMessage({ type: "error", text: e?.detail || e?.message || "Failed to send code" });
    }
    setConnecting(false);
  }

  async function verifyOtp() {
    if (!otpCode || otpCode.length !== 6) {
      setMessage({ type: "error", text: "Enter the 6-digit code from your email" });
      return;
    }
    setConnecting(true);
    try {
      const res = await apiPost("/api/cebroker/verify-otp", { otp_code: otpCode });
      if (res?.connected) {
        setOtpSent(false);
        setOtpCode("");
        setShowOtp(false);
        setMessage({ type: "success", text: res.message || "CE Broker connected ✅" });
      } else {
        setMessage({ type: "error", text: res?.message || "Verification failed" });
      }
      loadSettings();
    } catch (e: any) {
      setMessage({ type: "error", text: e?.detail || e?.message || "Verification failed" });
    }
    setConnecting(false);
  }

  async function syncNow() {
    setSyncing(true);
    setMessage(null);
    try {
      const result = await apiPost("/api/cebroker/sync", {});
      const needsConnect = result?.message && /not connected|expired/i.test(result.message);
      if (needsConnect) {
        setShowOtp(true);
        setOtpSent(false);
      }
      if (result?.synced > 0) {
        setMessage({ type: "success", text: `Synced ${result.synced} CEU(s) to CE Broker!` });
      } else if (result?.message) {
        setMessage({ type: needsConnect ? "error" : "success", text: result.message });
      } else {
        setMessage({ type: "success", text: "No CEUs to sync — all up to date" });
      }
      loadSettings();
    } catch (e: any) {
      setMessage({ type: "error", text: e?.message || "Sync failed" });
    }
    setSyncing(false);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-gray-500">Loading integrations...</div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Integrations</h1>
        <p className="text-gray-500 mt-1">Connect Breathe to your CE Broker account for automatic CEU submission.</p>
      </div>

      {message && (
        <div className={`p-3 rounded-lg text-sm ${message.type === "success" ? "bg-green-50 text-green-700 border border-green-200" : "bg-red-50 text-red-700 border border-red-200"}`}>
          {message.text}
        </div>
      )}

      {/* ─── CE Broker Card ─── */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 bg-gray-50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center text-xl">🏥</div>
            <div>
              <h2 className="font-semibold text-gray-900">CE Broker</h2>
              <p className="text-sm text-gray-500">Automatic CEU submission to your state board</p>
            </div>
          </div>
        </div>

        <div className="p-6 space-y-4">
          {/* Encryption warning */}
          {!settings?.encryption_enabled && (
            <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-sm text-amber-800">
              ⚠️ Encryption is not configured. Ask your administrator to set BREATHE_ENCRYPTION_KEY.
            </div>
          )}

          {/* Sync status */}
          {settings?.sync_status && (
            <div className="flex items-center gap-4 p-3 rounded-lg bg-gray-50">
              <div className="flex-1">
                <div className="text-sm font-medium text-gray-700">Sync Status</div>
                <div className="text-xs text-gray-500 mt-0.5">
                  {settings.sync_status.synced} of {settings.sync_status.total_ceus} CEUs synced
                </div>
              </div>
              {settings.sync_status.unsynced > 0 ? (
                <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                  {settings.sync_status.unsynced} unsynced
                </span>
              ) : (
                <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700">
                  All synced ✅
                </span>
              )}
            </div>
          )}

          {/* Email input */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              CE Broker Email
            </label>
            <div className="flex gap-2">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="flex-1 px-3 py-2 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button
                onClick={saveEmail}
                disabled={saving}
                className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? "Saving..." : "Save"}
              </button>
            </div>
            {settings?.cebroker_email?.has_email && (
              <p className="text-xs text-gray-400 mt-1">
                Current: {settings.cebroker_email.email_masked}
              </p>
            )}
          </div>

          {/* OTP connect flow — email a code, enter it, done */}
          <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-3 space-y-2">
            <div className="text-sm font-medium text-gray-800">
              {otpSent ? "Step 2 — Enter the 6-digit code" : "Step 1 — Email a login code"}
            </div>
            <p className="text-xs text-gray-500">
              We trigger CE Broker to email you a one-time code. Enter it here to connect
              your account — no password sharing needed. When connected, Breathe submits
              your CEUs to CE Broker automatically on your behalf (you can disconnect anytime).
            </p>
            {!otpSent ? (
              <button
                onClick={sendOtp}
                disabled={connecting}
                className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                {connecting ? "Sending..." : "Send code to my email"}
              </button>
            ) : (
              <div className="flex flex-wrap gap-2">
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ""))}
                  placeholder="000000"
                  className="w-32 px-3 py-2 rounded-lg border border-gray-300 text-sm tracking-widest text-center focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
                <button
                  onClick={verifyOtp}
                  disabled={connecting}
                  className="px-4 py-2 rounded-lg bg-green-600 text-white text-sm font-medium hover:bg-green-700 disabled:opacity-50"
                >
                  {connecting ? "Verifying..." : "Verify & connect"}
                </button>
                <button
                  onClick={sendOtp}
                  disabled={connecting}
                  className="px-3 py-2 rounded-lg border border-gray-300 text-sm text-gray-600 hover:bg-gray-50"
                >
                  Resend
                </button>
              </div>
            )}
            {settings?.cebroker_email?.has_email && (
              <p className="text-xs text-gray-500">
                Code goes to: {settings.cebroker_email.email_masked}
              </p>
            )}
          </div>

          {/* Password input */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              CE Broker Password
            </label>
            <div className="flex gap-2">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={settings?.cebroker_password?.has_password ? "•••••••• (saved)" : "Enter password"}
                className="flex-1 px-3 py-2 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button
                onClick={() => setShowPassword(!showPassword)}
                className="px-3 py-2 rounded-lg border border-gray-300 text-sm text-gray-600 hover:bg-gray-50"
              >
                {showPassword ? "Hide" : "Show"}
              </button>
              <button
                onClick={savePassword}
                disabled={saving || !password}
                className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                Save
              </button>
            </div>
            <p className="text-xs text-gray-400 mt-1">
              {settings?.cebroker_password?.has_password
                ? "Password saved (encrypted). CE Broker uses email OTP — this is stored for reference."
                : "Note: CE Broker uses email OTP login. Password is optional, stored for reference."}
            </p>
          </div>

          {/* Sync button */}
          <button
            onClick={syncNow}
            disabled={syncing || !settings?.cebroker_email?.has_email}
            className="w-full px-4 py-2.5 rounded-lg bg-green-600 text-white text-sm font-medium hover:bg-green-700 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {syncing ? (
              <>
                <span className="animate-spin">⏳</span> Syncing...
              </>
            ) : (
              <>🔄 Sync CEUs Now</>
            )}
          </button>
          {!settings?.cebroker_email?.has_email && (
            <p className="text-xs text-gray-400 text-center">Save your CE Broker email first to enable sync</p>
          )}
        </div>
      </div>

      {/* ─── State License Card ─── */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 bg-gray-50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-purple-50 flex items-center justify-center text-xl">📋</div>
            <div>
              <h2 className="font-semibold text-gray-900">State Licenses</h2>
              <p className="text-sm text-gray-500">Your registered state board licenses</p>
            </div>
          </div>
        </div>
        <div className="p-6">
          {settings?.licenses && settings.licenses.length > 0 ? (
            <div className="space-y-2">
              {settings.licenses.map((lic: any) => (
                <div key={lic.id} className="flex items-center justify-between p-3 rounded-lg bg-gray-50">
                  <div>
                    <div className="text-sm font-medium text-gray-900">{lic.license_type}</div>
                    <div className="text-xs text-gray-500">{lic.state} · {lic.license_number}</div>
                  </div>
                  <div className="text-xs text-gray-500">
                    Expires: {lic.expiry_date ? new Date(lic.expiry_date).toLocaleDateString() : "—"}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400">No licenses added yet.</p>
          )}
        </div>
      </div>

      {/* ─── Sync Log Card ─── */}
      {syncLogs.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 bg-gray-50">
            <h2 className="font-semibold text-gray-900">Recent Sync Activity</h2>
          </div>
          <div className="divide-y divide-gray-100">
            {syncLogs.map((log) => (
              <div key={log.id} className="px-6 py-3 flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium text-gray-900">{log.ceu_title}</div>
                  <div className="text-xs text-gray-500">
                    {log.submitted_at ? new Date(log.submitted_at).toLocaleString() : "Pending"}
                  </div>
                </div>
                <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${
                  log.status === "submitted" || log.status === "confirmed"
                    ? "bg-green-100 text-green-700"
                    : log.status === "failed"
                    ? "bg-red-100 text-red-700"
                    : "bg-amber-100 text-amber-700"
                }`}>
                  {log.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}