"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  ArrowLeft,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Sparkles,
} from "lucide-react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  getSubscription,
  cancelSubscription,
  formatDate,
  type Subscription,
  type SubscriptionTier,
} from "@/lib/api";

const tierLabel: Record<SubscriptionTier, string> = {
  free: "Free",
  pro: "Pro",
  department: "Department",
};

export default function SubscriptionPage() {
  const router = useRouter();
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [canceling, setCanceling] = useState(false);
  const [canceled, setCanceled] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const sub = await getSubscription();
        if (!cancelled) setSubscription(sub);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load subscription");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleCancel = async () => {
    if (!confirm("Cancel your subscription? You'll lose Pro features at the end of the billing period.")) {
      return;
    }
    setCanceling(true);
    setError(null);
    try {
      await cancelSubscription();
      setCanceled(true);
      setSubscription((prev) => (prev ? { ...prev, status: "canceled" } : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel subscription");
    } finally {
      setCanceling(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  const tier = subscription?.tier ?? "free";
  const status = subscription?.status ?? "active";
  const isPro = tier === "pro" || tier === "department";

  return (
    <div className="page-enter min-h-screen pb-20">
      {/* Header */}
      <div className="px-4 pt-8 pb-4 flex items-center gap-3">
        <button onClick={() => router.back()} className="p-2 -ml-2">
          <ArrowLeft size={24} className="text-text-primary" />
        </button>
        <h1 className="text-xl font-bold text-text-primary">Subscription</h1>
      </div>

      {error && (
        <div className="px-4 mb-3">
          <div className="flex items-center gap-2 bg-danger/10 text-danger rounded-button px-3 py-2 text-sm">
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
        </div>
      )}

      <div className="px-4 space-y-4">
        {/* Current Plan Card */}
        <Card className="p-6">
          <div className="flex items-center gap-3 mb-4">
            <div
              className={`w-12 h-12 rounded-card flex items-center justify-center ${
                isPro ? "bg-accent/10" : "bg-gray-100"
              }`}
            >
              <Sparkles
                size={24}
                className={isPro ? "text-accent" : "text-text-secondary"}
              />
            </div>
            <div>
              <h2 className="text-xl font-bold text-text-primary">
                {tierLabel[tier]}
              </h2>
              <div className="flex items-center gap-1 mt-0.5">
                {status === "active" ? (
                  <>
                    <CheckCircle2 size={14} className="text-success" />
                    <span className="text-sm text-success font-medium">Active</span>
                  </>
                ) : status === "canceled" ? (
                  <>
                    <XCircle size={14} className="text-danger" />
                    <span className="text-sm text-danger font-medium">Canceled</span>
                  </>
                ) : status === "past_due" ? (
                  <>
                    <AlertTriangle size={14} className="text-warning" />
                    <span className="text-sm text-warning font-medium">Past Due</span>
                  </>
                ) : (
                  <span className="text-sm text-text-secondary">Trialing</span>
                )}
              </div>
            </div>
          </div>

          {subscription?.subscription_expires && isPro && (
            <p className="text-sm text-text-secondary">
              {status === "canceled"
                ? `Access until ${formatDate(subscription.subscription_expires)}`
                : `Renews on ${formatDate(subscription.subscription_expires)}`}
            </p>
          )}

          {tier === "free" && (
            <p className="text-sm text-text-secondary">
              You&apos;re on the Free plan. Upgrade to unlock OCR,
              and more.
            </p>
          )}
        </Card>

        {/* Plan Details */}
        {isPro ? (
          <Card className="p-6">
            <h3 className="text-lg font-bold text-text-primary mb-3">Plan Details</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-text-secondary">Plan</span>
                <span className="text-text-primary font-medium">
                  {tierLabel[tier]}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Status</span>
                <span className="text-text-primary font-medium capitalize">
                  {status}
                </span>
              </div>
              {subscription?.subscription_expires && (
                <div className="flex justify-between">
                  <span className="text-text-secondary">
                    {status === "canceled" ? "Expires" : "Next renewal"}
                  </span>
                  <span className="text-text-primary font-medium">
                    {formatDate(subscription.subscription_expires)}
                  </span>
                </div>
              )}
              {subscription?.stripe_customer_id && (
                <div className="flex justify-between">
                  <span className="text-text-secondary">Billing</span>
                  <span className="text-text-primary font-medium">
                    via Stripe
                  </span>
                </div>
              )}
            </div>
          </Card>
        ) : (
          <Card className="p-6 text-center">
            <h3 className="text-lg font-bold text-text-primary mb-2">
              Ready to upgrade?
            </h3>
            <p className="text-sm text-text-secondary mb-4">
              Pro is $4.99/mo or $39/yr. Cancel anytime.
            </p>
            <Link href="/pricing">
              <Button size="lg" className="w-full">
                View Plans
              </Button>
            </Link>
          </Card>
        )}

        {/* Cancel / Manage */}
        {isPro && status !== "canceled" && (
          <Card className="p-6">
            <h3 className="text-lg font-bold text-text-primary mb-2">
              Manage Subscription
            </h3>
            <p className="text-sm text-text-secondary mb-4">
              Cancel your subscription. You keep Pro access until the end of the
              current billing period.
            </p>
            <Button
              variant="outline"
              className="w-full"
              onClick={handleCancel}
              disabled={canceling}
            >
              {canceling ? (
                <>
                  <Loader2 size={18} className="mr-1 animate-spin" /> Canceling...
                </>
              ) : canceled ? (
                <>
                  <CheckCircle2 size={18} className="mr-1" /> Canceled
                </>
              ) : (
                "Cancel Subscription"
              )}
            </Button>
          </Card>
        )}

        {status === "canceled" && (
          <Card className="p-6 text-center">
            <p className="text-sm text-text-secondary mb-4">
              Your subscription is canceled. Resubscribe anytime.
            </p>
            <Link href="/pricing">
              <Button size="lg" className="w-full">
                Resubscribe
              </Button>
            </Link>
          </Card>
        )}
      </div>
    </div>
  );
}