"use client";

import { useEffect, useState } from "react";
import { BottomNav } from "@/components/bottom-nav";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  User,
  Mail,
  Award,
  MapPin,
  Calendar,
  Bell,
  Shield,
  ChevronRight,
  LogOut,
  Info,
  CreditCard,
  Loader2,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import {
  getUser,
  getPrimaryLicense,
  formatDate,
  type User as UserType,
  type License,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function ProfilePage() {
  const { logout } = useAuth();
  const [user, setUser] = useState<UserType | null>(null);
  const [license, setLicense] = useState<License | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [u, l] = await Promise.all([getUser(), getPrimaryLicense()]);
        if (cancelled) return;
        setUser(u);
        setLicense(l);
      } catch {
        // ignore — show placeholder data
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
      <div className="page-enter min-h-screen pb-20">
        <div className="flex items-center justify-center pt-24">
          <Loader2 className="animate-spin text-primary" size={28} />
        </div>
        <BottomNav />
      </div>
    );
  }

  return (
    <div className="page-enter min-h-screen pb-20">
      {/* Header */}
      <div className="bg-gradient-to-br from-primary to-accent px-6 pt-12 pb-8 text-white rounded-b-[32px]">
        <div className="flex flex-col items-center text-center">
          <div className="w-20 h-20 rounded-full bg-white/20 flex items-center justify-center text-white text-3xl font-bold mb-3">
            {user?.name?.[0] ?? "?"}
          </div>
          <h1 className="text-xl font-bold">{user?.name ?? "—"}</h1>
          <p className="text-white/70 text-sm">{user?.email ?? "—"}</p>
        </div>
      </div>

      {/* License Info */}
      <div className="px-4 -mt-4 mb-6">
        <Card className="p-4">
          <h2 className="text-sm font-bold text-text-secondary uppercase tracking-wide mb-3">
            License Details
          </h2>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center">
                <Award size={18} className="text-primary" />
              </div>
              <div className="flex-1">
                <p className="text-xs text-text-secondary">License Type</p>
                <p className="text-sm font-semibold text-text-primary">
                  {license?.license_type ?? "RRT"} — Registered Respiratory Therapist
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-accent/10 flex items-center justify-center">
                <User size={18} className="text-accent" />
              </div>
              <div className="flex-1">
                <p className="text-xs text-text-secondary">License Number</p>
                <p className="text-sm font-semibold text-text-primary">
                  #{license?.license_number ?? "—"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-success/10 flex items-center justify-center">
                <MapPin size={18} className="text-success" />
              </div>
              <div className="flex-1">
                <p className="text-xs text-text-secondary">State</p>
                <p className="text-sm font-semibold text-text-primary">
                  {license?.state ?? "Texas"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-warning/10 flex items-center justify-center">
                <Calendar size={18} className="text-warning" />
              </div>
              <div className="flex-1">
                <p className="text-xs text-text-secondary">Expires</p>
                <p className="text-sm font-semibold text-text-primary">
                  {license ? formatDate(license.expiry_date) : "—"}
                </p>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Settings */}
      <div className="px-4 mb-6">
        <h2 className="text-sm font-bold text-text-secondary uppercase tracking-wide mb-3">
          Settings
        </h2>
        <Card className="p-0 overflow-hidden">
          <SettingRow
            icon={Bell}
            label="Reminder Preferences"
            value="30 days before expiry"
          />
          <Link href="/settings/subscription" className="block">
            <SettingRow
              icon={CreditCard}
              label="Subscription"
              value={
                user?.subscription_tier === "pro" || user?.subscription_tier === "department"
                  ? `Pro · ${user?.subscription_status ?? "active"}`
                  : "Free plan"
              }
            />
          </Link>
          <Link href="/free-courses" className="block">
            <SettingRow
              icon={Shield}
              label="State Requirements"
              value={`${license?.state ?? "TX"} · ${license?.required_ceus ?? 24} CEUs / ${license?.cycle_years ?? 2} years`}
            />
          </Link>
          <Link href="/pricing" className="block">
            <SettingRow icon={Info} label="About Breathe" value="v1.0.0" />
          </Link>
        </Card>
      </div>

      {/* Texas CEU Requirements */}
      <div className="px-4 mb-6">
        <Card className="bg-gradient-to-br from-accent/5 to-primary/5 border-accent/20">
          <h2 className="text-sm font-bold text-text-primary mb-2">
            Texas CEU Requirements
          </h2>
          <ul className="space-y-1.5 text-sm text-text-secondary">
            <li className="flex items-start gap-2">
              <span className="text-success mt-0.5">✓</span>
              <span>24 CEUs per 2-year renewal cycle</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-success mt-0.5">✓</span>
              <span>≥12 hours must be traditional (live instruction)</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-success mt-0.5">✓</span>
              <span>≥2 hours ethics (incl. 1 hr human trafficking prevention)</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-success mt-0.5">✓</span>
              <span>No carryover — all hours must be in current period</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-success mt-0.5">✓</span>
              <span>License expires May 31 or November 30 (biennial)</span>
            </li>
          </ul>
          <p className="text-xs text-text-secondary mt-3 pt-3 border-t border-gray-100">
            RTs in Texas are licensed through{" "}
            <strong className="text-text-primary">
              TMB — Texas Medical Board
            </strong>
            .
          </p>
        </Card>
      </div>

      {/* Logout */}
      <div className="px-4 mb-6">
        <Button
          variant="outline"
          size="lg"
          className="w-full text-danger border-danger/20 hover:bg-danger/5"
          onClick={() => logout()}
        >
          <LogOut size={20} className="mr-1" /> Sign Out
        </Button>
      </div>

      <BottomNav />
    </div>
  );
}

function SettingRow({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3.5 border-b border-gray-100 last:border-0">
      <div className="w-9 h-9 rounded-full bg-gray-100 flex items-center justify-center">
        <Icon size={18} className="text-text-secondary" />
      </div>
      <div className="flex-1">
        <p className="text-sm font-medium text-text-primary">{label}</p>
        <p className="text-xs text-text-secondary">{value}</p>
      </div>
      <ChevronRight size={18} className="text-text-secondary" />
    </div>
  );
}