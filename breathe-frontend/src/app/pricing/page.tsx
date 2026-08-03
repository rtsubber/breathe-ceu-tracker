"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Check, Sparkles, Building2, User as UserIcon } from "lucide-react";
import { createCheckoutSession } from "@/lib/api";

export default function PricingPage() {
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [billingCycle, setBillingCycle] = useState<"monthly" | "yearly">("yearly");
  // Billing toggle hidden — intro pricing is $20/yr flat
  void billingCycle; void setBillingCycle;

  const handleSubscribe = async (tier: "pro" | "department") => {
    setLoading(tier);
    setError(null);
    try {
      const { url } = await createCheckoutSession(tier, billingCycle);
      window.location.href = url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start checkout");
    } finally {
      setLoading(null);
    }
  };

  const plans = [
    {
      name: "Free",
      icon: UserIcon,
      price: "$0",
      period: "forever",
      description: "Track everything you need — state license, NBRC, competencies.",
      features: [
        "Manual CEU entry",
        "Certificate photo upload",
        "Progress tracking (state + NBRC)",
        "TMB report generation",
        "Email renewal reminders",
        "Free CEU course alerts",
        "License lookup (TMB auto-fill)",
        "NBRC credential tracking (5-year cycle)",
        "Competency tracking",
      ],
      cta: "Get Started Free",
      ctaAction: null as null | (() => void),
      highlighted: false,
      savings: null as string | null,
    },
    {
      name: "Pro",
      icon: Sparkles,
      price: "$20",
      period: "/year (1st year)",
      description: "Stop typing. Let the app do the work — OCR, auto-import, CE Broker sync.",
      features: [
        "Everything in Free, plus:",
        "Certificate OCR (snap → auto-extract)",
        "Email forwarding (auto-parse CEUs)",
        "AARC auto-import",
        "CE Broker auto-sync ← never type into CE Broker again",
        "SMS reminders",
        "Multi-state license support",
        "Chrome extension (coming soon)",
      ],
      cta: "Upgrade to Pro — $20",
      ctaAction: () => handleSubscribe("pro"),
      highlighted: true,
      savings: "Intro pricing — renews at $39/yr",
    },
    {
      name: "Department",
      icon: Building2,
      price: "$99",
      period: "/month (up to 25 RTs)",
      description: "For RT departments and managers. Flat pricing, no per-seat fees.",
      features: [
        "Everything in Pro for each team member",
        "Manager dashboard",
        "Team competency tracking",
        "Compliance reports",
        "Joint Commission reports",
        "Bulk CEU import",
        "CE Broker auto-sync for all staff",
      ],
      cta: "Contact Sales",
      ctaAction: () => handleSubscribe("department"),
      highlighted: false,
      savings: null,
    },
  ];

  return (
    <div className="page-enter min-h-screen pb-20">
      {/* Header */}
      <div className="bg-gradient-to-br from-primary to-accent px-6 pt-12 pb-8 text-white rounded-b-[32px]">
        <h1 className="text-3xl font-bold text-center">Choose Your Plan</h1>
        <p className="text-center text-white/80 mt-2">
          Free for individual RTs. Pro saves you hours. Department for teams.
        </p>
      </div>

      {error && (
        <div className="px-4 mt-4">
          <div className="bg-danger/10 text-danger rounded-button px-4 py-3 text-sm">
            {error}
          </div>
        </div>
      )}

      {/* Plans */}
      <div className="px-4 mt-6 space-y-4">
        {plans.map((plan) => {
          const Icon = plan.icon;
          return (
            <Card
              key={plan.name}
              className={`p-6 ${plan.highlighted ? "border-2 border-accent shadow-lg" : ""}`}
            >
              <div className="flex items-center gap-3 mb-4">
                <div
                  className={`w-12 h-12 rounded-card flex items-center justify-center ${
                    plan.highlighted ? "bg-accent/10" : "bg-gray-100"
                  }`}
                >
                  <Icon
                    size={24}
                    className={plan.highlighted ? "text-accent" : "text-text-secondary"}
                  />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-text-primary">{plan.name}</h2>
                  {plan.savings && (
                    <span className="text-xs bg-success/10 text-success px-2 py-0.5 rounded-full font-medium">
                      {plan.savings}
                    </span>
                  )}
                </div>
              </div>

              <div className="mb-4">
                <span className="text-3xl font-bold text-text-primary">{plan.price}</span>
                <span className="text-text-secondary">{plan.period}</span>
              </div>

              <p className="text-sm text-text-secondary mb-4">{plan.description}</p>

              <div className="space-y-2 mb-6">
                {plan.features.map((feat) => (
                  <div key={feat} className="flex items-center gap-2">
                    <Check size={16} className="text-success flex-shrink-0" />
                    <span className="text-sm text-text-primary">{feat}</span>
                  </div>
                ))}
              </div>

              {plan.ctaAction ? (
                <Button
                  size="lg"
                  className="w-full"
                  variant={plan.highlighted ? "primary" : "outline"}
                  onClick={plan.ctaAction}
                  disabled={loading === plan.name.toLowerCase()}
                >
                  {loading === plan.name.toLowerCase() ? "Redirecting..." : plan.cta}
                </Button>
              ) : (
                <Button size="lg" className="w-full" variant="outline" disabled>
                  {plan.cta}
                </Button>
              )}
            </Card>
          );
        })}
      </div>

      <div className="px-4 mt-6 text-center">
        <p className="text-xs text-text-secondary">
          Cancel anytime. Pro is $20/yr intro — renews at $39/yr. Cheaper than CE Tracker ($60/yr) and CE Broker ($29-99/yr).
          Department is $99/mo flat for up to 25 RTs.
        </p>
      </div>
    </div>
  );
}