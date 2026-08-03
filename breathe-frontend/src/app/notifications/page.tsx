"use client";

import { useState } from "react";
import { BottomNav } from "@/components/bottom-nav";
import { Card } from "@/components/ui/card";
import {
  Bell,
  Calendar,
  BookOpen,
  AlertTriangle,
  Sparkles,
  ArrowLeft,
  Mail,
  Smartphone,
  MessageSquare,
  ChevronRight,
} from "lucide-react";
import { useRouter } from "next/navigation";

type NotificationType = "warning" | "info" | "violet" | "success";

interface NotificationItem {
  id: string;
  title: string;
  message: string;
  type: NotificationType;
  icon: typeof Bell;
  time: string;
}

const mockNotifications: NotificationItem[] = [
  {
    id: "1",
    title: "RRT Renewal Approaching",
    message: "Your RRT renewal is 89 days away. Make sure your CEUs are on track.",
    type: "warning",
    icon: Calendar,
    time: "2h ago",
  },
  {
    id: "2",
    title: "CEU Progress Update",
    message: "You need 14 more CEUs to meet Texas requirement (30 total).",
    type: "info",
    icon: BookOpen,
    time: "5h ago",
  },
  {
    id: "3",
    title: "ACLS Expiring Soon",
    message: "ACLS expires in 42 days. Schedule your renewal course.",
    type: "warning",
    icon: AlertTriangle,
    time: "1d ago",
  },
  {
    id: "4",
    title: "New Course Available",
    message: "Mechanical Ventilation Advanced is now available on AARC.",
    type: "violet",
    icon: Sparkles,
    time: "2d ago",
  },
];

const typeStyles: Record<
  NotificationType,
  { bg: string; text: string; ring: string }
> = {
  warning: {
    bg: "bg-warning/10",
    text: "text-warning",
    ring: "bg-warning",
  },
  info: {
    bg: "bg-primary/10",
    text: "text-primary",
    ring: "bg-primary",
  },
  violet: {
    bg: "bg-accent/10",
    text: "text-accent",
    ring: "bg-accent",
  },
  success: {
    bg: "bg-success/10",
    text: "text-success",
    ring: "bg-success",
  },
};

export default function NotificationsPage() {
  const router = useRouter();
  const [settings, setSettings] = useState({
    email: true,
    push: true,
    sms: false,
  });

  const toggleSetting = (key: keyof typeof settings) => {
    setSettings({ ...settings, [key]: !settings[key] });
  };

  return (
    <div className="page-enter min-h-screen pb-20">
      {/* Header */}
      <div className="px-4 pt-8 pb-4 flex items-center gap-3">
        <button onClick={() => router.back()} className="p-2 -ml-2">
          <ArrowLeft size={24} className="text-text-primary" />
        </button>
        <div>
          <h1 className="text-xl font-bold text-text-primary">Notifications</h1>
          <p className="text-xs text-text-secondary">
            {mockNotifications.length} updates
          </p>
        </div>
      </div>

      {/* Notifications List */}
      <div className="px-4 mb-6 space-y-2">
        {mockNotifications.map((n) => {
          const style = typeStyles[n.type];
          const Icon = n.icon;
          return (
            <Card key={n.id} className="flex items-start gap-3 py-3">
              <div
                className={`w-10 h-10 rounded-card ${style.bg} flex items-center justify-center flex-shrink-0`}
              >
                <Icon size={20} className={style.text} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-bold text-text-primary">{n.title}</p>
                  <span className="text-xs text-text-secondary whitespace-nowrap flex-shrink-0">
                    {n.time}
                  </span>
                </div>
                <p className="text-sm text-text-secondary mt-0.5">{n.message}</p>
              </div>
              <span className={`w-2 h-2 rounded-full ${style.ring} mt-2 flex-shrink-0`} />
            </Card>
          );
        })}
      </div>

      {/* Notification Settings */}
      <div className="px-4 mb-6">
        <h2 className="text-sm font-bold text-text-secondary uppercase tracking-wide mb-3">
          Notification Settings
        </h2>
        <Card className="p-0 overflow-hidden">
          <SettingToggle
            icon={Mail}
            label="Email Notifications"
            description="Receive updates via email"
            enabled={settings.email}
            onToggle={() => toggleSetting("email")}
          />
          <SettingToggle
            icon={Smartphone}
            label="Push Notifications"
            description="Receive updates on your device"
            enabled={settings.push}
            onToggle={() => toggleSetting("push")}
          />
          <SettingToggle
            icon={MessageSquare}
            label="SMS Notifications"
            description="Receive text message alerts"
            enabled={settings.sms}
            onToggle={() => toggleSetting("sms")}
            last
          />
        </Card>
      </div>

      <BottomNav />
    </div>
  );
}

function SettingToggle({
  icon: Icon,
  label,
  description,
  enabled,
  onToggle,
  last,
}: {
  icon: typeof Bell;
  label: string;
  description: string;
  enabled: boolean;
  onToggle: () => void;
  last?: boolean;
}) {
  return (
    <div
      className={`flex items-center gap-3 px-4 py-3.5 ${
        last ? "" : "border-b border-gray-100"
      }`}
    >
      <div className="w-9 h-9 rounded-full bg-gray-100 flex items-center justify-center">
        <Icon size={18} className="text-text-secondary" />
      </div>
      <div className="flex-1">
        <p className="text-sm font-medium text-text-primary">{label}</p>
        <p className="text-xs text-text-secondary">{description}</p>
      </div>
      <button
        onClick={onToggle}
        className={`relative w-12 h-7 rounded-full transition-colors ${
          enabled ? "bg-primary" : "bg-gray-200"
        }`}
        aria-pressed={enabled}
        aria-label={`Toggle ${label}`}
      >
        <span
          className={`absolute top-0.5 left-0.5 w-6 h-6 bg-white rounded-full shadow-sm transition-transform ${
            enabled ? "translate-x-5" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );
}