"use client";

import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { Smartphone, Camera, RefreshCw, Award, Bell, Shield, Loader2 } from "lucide-react";

export default function SplashPage() {
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-gradient-to-b from-surface to-gray-50">
      {/* Hero */}
      <div className="flex flex-col items-center justify-center px-6 pt-16 pb-12">
        <div className="animate-pulse mb-6">
          <Logo size={80} />
        </div>
        <h1 className="text-5xl font-bold bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent mb-3">
          Breathe
        </h1>
        <p className="text-xl text-text-primary font-semibold text-center max-w-md mb-2">
          CEU tracking that actually works.
        </p>
        <p className="text-base text-text-secondary text-center max-w-md mb-8">
          Free forever. $20/year to stop doing it manually.
        </p>
        <div className="w-full max-w-sm space-y-3">
          {user ? (
            <Link href="/dashboard" className="block">
              <Button size="lg" className="w-full">
                Go to Dashboard
              </Button>
            </Link>
          ) : (
            <>
              <Link href="/register" className="block">
                <Button size="lg" className="w-full">
                  Get Started Free
                </Button>
              </Link>
              <Link href="/login" className="block">
                <Button variant="ghost" size="md" className="w-full">
                  Log In
                </Button>
              </Link>
            </>
          )}
        </div>
        <p className="text-xs text-text-secondary mt-4">
          Built by an RRT, for RTs.
        </p>
      </div>

      {/* Problem */}
      <div className="bg-white px-6 py-12">
        <div className="max-w-2xl mx-auto text-center">
          <p className="text-lg text-text-primary font-medium mb-2">
            CE Broker took 3 days to verify my license.
          </p>
          <p className="text-lg text-text-primary font-medium mb-2">
            SB 912 mandates digital CE verification for every Texas RT by September 2026.
          </p>
          <p className="text-lg text-text-primary font-medium">
            September 1, we all get to experience this. Uuggghhh.
          </p>
        </div>
      </div>

      {/* CE Broker sync status banner */}
      <div className="bg-accent/5 border-y border-accent/20 px-6 py-3">
        <div className="max-w-2xl mx-auto flex items-center justify-center gap-2">
          <Loader2 size={16} className="text-accent animate-spin" />
          <p className="text-sm text-text-secondary">
            <span className="font-semibold text-accent">CE Broker auto-sync</span> is in active development — landing soon for Texas RTs.
          </p>
        </div>
      </div>

      {/* Features */}
      <div className="px-6 py-16">
        <div className="max-w-2xl mx-auto">
          <h2 className="text-2xl font-bold text-text-primary text-center mb-10">
            How it works
          </h2>
          <div className="space-y-8">
            {/* Onboarding */}
            <div className="flex gap-4">
              <div className="flex-shrink-0 w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
                <Smartphone size={24} className="text-primary" />
              </div>
              <div>
                <h3 className="font-semibold text-text-primary mb-1">Onboard in 2 minutes</h3>
                <p className="text-text-secondary text-sm">
                  Enter your email. Type your name. Breathe finds your license automatically.
                  Add your NBRC login and both sides are tracked — state and national.
                </p>
              </div>
            </div>

            {/* OCR */}
            <div className="flex gap-4">
              <div className="flex-shrink-0 w-12 h-12 rounded-full bg-accent/10 flex items-center justify-center">
                <Camera size={24} className="text-accent" />
              </div>
              <div>
                <h3 className="font-semibold text-text-primary mb-1">Snap a photo. Done.</h3>
                <p className="text-text-secondary text-sm">
                  Point your phone at a CEU certificate. Breathe&apos;s OCR reads the course title,
                  provider, credits, and date — all extracted automatically. No typing.
                </p>
              </div>
            </div>

            {/* CE Broker Sync */}
            <div className="flex gap-4">
              <div className="flex-shrink-0 w-12 h-12 rounded-full bg-success/10 flex items-center justify-center">
                <RefreshCw size={24} className="text-success" />
              </div>
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-semibold text-text-primary">Auto-sync to CE Broker</h3>
                  <span className="text-xs bg-accent/10 text-accent px-2 py-0.5 rounded-full font-medium">In Progress</span>
                </div>
                <p className="text-text-secondary text-sm">
                  Every CEU you track in Breathe gets pushed to CE Broker automatically.
                  You don&apos;t enter anything twice. Ever.
                </p>
              </div>
            </div>

            {/* NBRC */}
            <div className="flex gap-4">
              <div className="flex-shrink-0 w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
                <Award size={24} className="text-primary" />
              </div>
              <div>
                <h3 className="font-semibold text-text-primary mb-1">NBRC CMP tracking</h3>
                <p className="text-text-secondary text-sm">
                  Your 5-year CMP cycle, assessment status, and credential renewals —
                  all tracked in one dashboard alongside your state license.
                </p>
              </div>
            </div>

            {/* Reminders */}
            <div className="flex gap-4">
              <div className="flex-shrink-0 w-12 h-12 rounded-full bg-accent/10 flex items-center justify-center">
                <Bell size={24} className="text-accent" />
              </div>
              <div>
                <h3 className="font-semibold text-text-primary mb-1">Never miss a deadline</h3>
                <p className="text-text-secondary text-sm">
                  Email and SMS reminders before your license expires. Free CEU course alerts
                  so you always have credits when you need them.
                </p>
              </div>
            </div>

            {/* Free CEU Alerts */}
            <div className="flex gap-4">
              <div className="flex-shrink-0 w-12 h-12 rounded-full bg-success/10 flex items-center justify-center">
                <Shield size={24} className="text-success" />
              </div>
              <div>
                <h3 className="font-semibold text-text-primary mb-1">Competency tracking</h3>
                <p className="text-text-secondary text-sm">
                  Annual competencies, unit-specific checkoffs, and skills tracking —
                  everything your hospital needs to see, in one place.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Pricing */}
      <div className="bg-white px-6 py-16">
        <div className="max-w-md mx-auto text-center">
          <h2 className="text-2xl font-bold text-text-primary mb-6">Pricing</h2>
          <div className="grid grid-cols-1 gap-4">
            <div className="border-2 border-gray-200 rounded-xl p-6 text-left">
              <p className="font-semibold text-text-primary mb-1">Free</p>
              <p className="text-3xl font-bold text-text-primary mb-3">$0</p>
              <ul className="text-sm text-text-secondary space-y-2">
                <li>✓ Manual CEU entry</li>
                <li>✓ Certificate photo upload</li>
                <li>✓ Progress tracking (state + NBRC)</li>
                <li>✓ CE compliance report generation</li>
                <li>✓ Email renewal reminders</li>
                <li>✓ Free CEU course alerts</li>
                <li>✓ License lookup (auto-fill)</li>
                <li>✓ NBRC credential tracking</li>
                <li>✓ Competency tracking</li>
              </ul>
            </div>
            <div className="border-2 border-primary rounded-xl p-6 text-left relative">
              <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary text-white text-xs font-medium px-3 py-1 rounded-full">
                Most Popular
              </span>
              <p className="font-semibold text-text-primary mb-1">Pro</p>
              <p className="text-3xl font-bold text-text-primary mb-1">$20<span className="text-base font-normal text-text-secondary">/year</span></p>
              <p className="text-xs text-text-secondary mb-3">Intro pricing — renews at $39/year</p>
              <ul className="text-sm text-text-secondary space-y-2">
                <li>✓ Everything in Free, plus:</li>
                <li>✓ Certificate OCR (snap → auto-extract)</li>
                <li>✓ Email forwarding (auto-parse CEU emails)</li>
                <li>✓ AARC auto-import</li>
                <li>✓ CE Broker auto-sync</li>
                <li>✓ SMS reminders</li>
                <li>✓ Multi-state license support</li>
              </ul>
            </div>
          </div>
          <p className="text-xs text-text-secondary mt-6">
            CE Broker charges $29-99/year. We do more for less.
          </p>
        </div>
      </div>

      {/* CTA */}
      <div className="px-6 py-16 text-center">
        <h2 className="text-2xl font-bold text-text-primary mb-4">
          Ready to stop doing it manually?
        </h2>
        <p className="text-text-secondary mb-8">Free forever. No credit card required.</p>
        <div className="max-w-xs mx-auto">
          {user ? (
            <Link href="/dashboard" className="block">
              <Button size="lg" className="w-full">
                Go to Dashboard
              </Button>
            </Link>
          ) : (
            <Link href="/register" className="block">
              <Button size="lg" className="w-full">
                Get Started Free
              </Button>
            </Link>
          )}
        </div>
        <p className="text-xs text-text-secondary mt-4">
          breathe.sublettlabs.com
        </p>
      </div>

      {/* Footer */}
      <div className="border-t border-gray-200 px-6 py-8 text-center">
        <p className="text-xs text-text-secondary">
          Built by an RRT, for RTs. Because this is what it should have been.
        </p>
        <p className="text-xs text-text-secondary mt-2">
          © 2026 Sublett Labs. breathe.sublettlabs.com
        </p>
      </div>
    </div>
  );
}