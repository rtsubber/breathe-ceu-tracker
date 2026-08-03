"use client";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Lock, Sparkles } from "lucide-react";
import Link from "next/link";

type PaywallProps = {
  feature: string;
  description?: string;
};

export function Paywall({ feature, description }: PaywallProps) {
  return (
    <Card className="p-6 text-center border-2 border-accent/20">
      <div className="w-14 h-14 rounded-card bg-accent/10 flex items-center justify-center mx-auto mb-4">
        <Lock size={28} className="text-accent" />
      </div>
      <h3 className="text-lg font-bold text-text-primary mb-1">
        {feature} is a Pro feature
      </h3>
      <p className="text-sm text-text-secondary mb-4">
        {description || `Upgrade to Breathe Pro to unlock ${feature}. Just $4.99/mo or $39/yr.`}
      </p>
      <Link href="/pricing">
        <Button size="lg" className="w-full">
          <Sparkles size={18} className="mr-1" /> Upgrade to Pro
        </Button>
      </Link>
      <p className="text-xs text-text-secondary mt-2">
        Cheaper than CE Tracker. Cancel anytime.
      </p>
    </Card>
  );
}