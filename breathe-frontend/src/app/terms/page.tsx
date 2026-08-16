import Link from "next/link";
import { Card } from "@/components/ui/card";

export const metadata = {
  title: "Terms of Service — Breathe",
  description: "Terms of Service for Breathe CEU Tracker",
};

const sections = [
  {
    title: "1. Service Description",
    body: [
      "Breathe is a continuing education unit (CEU) tracking tool designed for respiratory therapists. The service allows users to log CEU records, upload certificate images, track progress toward state license renewal and NBRC credential maintenance, generate compliance reports, and sync records with CE Broker.",
      "Breathe is offered in two tiers: a Free plan with manual entry and basic tracking, and a Pro plan ($25/year) with OCR, auto-import, and CE Broker sync features.",
    ],
  },
  {
    title: "2. User Responsibilities",
    body: [
      "You agree to provide accurate and truthful information when creating your account, including your name, email, license number, and state of practice.",
      "You are responsible for maintaining the confidentiality of your account credentials and for all activity that occurs under your account.",
      "You agree not to share your account with other individuals. Each respiratory therapist must maintain their own separate account.",
    ],
  },
  {
    title: "3. Limitation of Liability",
    body: [
      "Breathe is a tracking and organizational tool. It is NOT a legal compliance guarantee. While we strive for accuracy in state requirement data and progress calculations, we make no warranties that use of Breathe will satisfy your specific state board requirements.",
      "Users must independently verify their CEU requirements and compliance status with their state respiratory therapy board. Breathe should be used as a supplementary tool, not as a substitute for official guidance from licensing authorities.",
      "Breathe shall not be liable for any indirect, incidental, special, or consequential damages, including but not limited to license suspension, loss of employment, or regulatory penalties arising from reliance on the service.",
    ],
  },
  {
    title: "4. CE Broker Sync",
    body: [
      "Breathe may offer integration with CE Broker for syncing CEU records. We do not guarantee the accuracy, timeliness, or completeness of synced data. CE Broker's acceptance of submitted records is subject to their own validation processes.",
      "Users should verify that all synced records appear correctly in their CE Broker account and contact their state board if discrepancies arise.",
    ],
  },
  {
    title: "5. Data Retention",
    body: [
      "We store your account information, CEU records, and certificate images for as long as your account is active. You may request deletion of your account and all associated data at any time.",
      "Upon account deletion, your data is permanently removed within 30 days, with the exception of records retained for legal or financial obligations (e.g., Stripe transaction records).",
    ],
  },
  {
    title: "6. Refund Policy",
    body: [
      "The Pro plan costs $25 per year. We offer a full refund within 14 days of purchase, no questions asked. To request a refund, contact ron.sublett@gmail.com with your account email and transaction ID.",
      "Refunds are processed back to the original payment method via Stripe within 5–10 business days.",
    ],
  },
  {
    title: "7. Account Termination",
    body: [
      "You may delete your account at any time from the app settings or by contacting ron.sublett@gmail.com. Account deletion permanently removes all CEU records, certificate images, and personal information associated with your account.",
      "We reserve the right to suspend or terminate accounts that violate these Terms, particularly in cases of fabricated CEU records or account sharing.",
    ],
  },
  {
    title: "8. Acceptable Use",
    body: [
      "You agree not to:",
    ],
    list: [
      "Fabricate or falsify CEU records, certificate images, or license information",
      "Share your account credentials with other individuals",
      "Use the service for any illegal or unauthorized purpose",
      "Attempt to access, disrupt, or compromise the service's infrastructure or data",
      "Use automated tools to scrape, overload, or interfere with the service",
    ],
  },
  {
    title: "9. Intellectual Property",
    body: [
      "Breathe, including its design, code, and content, is the intellectual property of its operators. You retain ownership of all CEU records and certificate images you upload. We do not claim ownership of your data.",
    ],
  },
  {
    title: "10. Governing Law",
    body: [
      "These Terms shall be governed by and construed in accordance with the laws of the State of Texas, United States of America, without regard to conflict of law principles.",
      "Any disputes arising from these Terms or use of the service shall be resolved in the courts of Texas, USA.",
    ],
  },
  {
    title: "11. Changes to These Terms",
    body: [
      "We may update these Terms from time to time. Users will be notified of material changes via email or in-app notification. Continued use of the service after changes take effect constitutes acceptance of the updated Terms.",
    ],
  },
  {
    title: "12. Contact",
    body: [
      "For questions about these Terms, contact: ron.sublett@gmail.com",
    ],
  },
];

export default function TermsPage() {
  return (
    <div className="page-enter min-h-screen pb-20">
      {/* Header */}
      <div className="bg-gradient-to-br from-primary to-accent px-6 pt-12 pb-8 text-white rounded-b-[32px]">
        <h1 className="text-2xl font-bold">Terms of Service</h1>
        <p className="text-white/70 text-sm mt-1">Last updated: August 14, 2026</p>
      </div>

      {/* Intro */}
      <div className="px-4 mt-6">
        <Card className="p-5">
          <p className="text-sm text-text-secondary leading-relaxed">
            Welcome to Breathe. By creating an account or using the service, you agree to the
            following terms. Please read them carefully.
          </p>
        </Card>
      </div>

      {/* Sections */}
      <div className="px-4 mt-4 space-y-4">
        {sections.map((section) => (
          <Card key={section.title} className="p-5">
            <h2 className="text-base font-bold text-text-primary mb-2">{section.title}</h2>
            <div className="space-y-2">
              {section.body.map((para, i) => (
                <p key={i} className="text-sm text-text-secondary leading-relaxed">
                  {para}
                </p>
              ))}
              {section.list && (
                <ul className="mt-2 space-y-1.5 pl-1">
                  {section.list.map((item, i) => (
                    <li key={i} className="text-sm text-text-secondary leading-relaxed flex gap-2">
                      <span className="text-danger flex-shrink-0">•</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
        ))}
      </div>

      {/* Footer */}
      <div className="px-4 mt-6 text-center">
        <p className="text-xs text-text-secondary">
          Questions? Email{" "}
          <a href="mailto:ron.sublett@gmail.com" className="text-primary font-medium">
            ron.sublett@gmail.com
          </a>
        </p>
        <div className="mt-3 flex justify-center gap-4">
          <Link href="/privacy" className="text-xs text-text-secondary hover:text-primary transition-colors">
            Privacy Policy
          </Link>
          <Link href="/dashboard" className="text-xs text-text-secondary hover:text-primary transition-colors">
            Back to App
          </Link>
        </div>
      </div>
    </div>
  );
}