import Link from "next/link";
import { Card } from "@/components/ui/card";

export const metadata = {
  title: "Privacy Policy — Breathe",
  description: "Privacy Policy for Breathe CEU Tracker",
};

const sections = [
  {
    title: "1. Information We Collect",
    body: [
      "We collect the following personal information when you create an account:",
    ],
    list: [
      "Full name",
      "Email address",
      "Respiratory therapy license number(s)",
      "State(s) of practice",
      "CEU records (course title, provider, credits, completion date)",
      "Certificate images (uploaded photos or files)",
      "NBRC credential information (credential type, cycle dates)",
    ],
  },
  {
    title: "2. How We Use Your Information",
    body: [
      "Your information is used solely for the purpose of providing the Breathe service:",
    ],
    list: [
      "Tracking CEU progress toward state license renewal requirements",
      "Generating compliance reports for state boards and employers",
      "Sending license renewal reminders via email and SMS (Pro plan)",
      "Syncing CEU records to CE Broker (Pro plan, when enabled)",
      "Providing NBRC credential cycle tracking and competency management",
    ],
  },
  {
    title: "3. What We Do NOT Do",
    body: [
      "We are committed to your privacy. Specifically, we do NOT:",
    ],
    list: [
      "Sell your personal data to third parties — ever",
      "Share your CEU records or personal information with employers without your explicit consent",
      "Use your data for advertising or marketing purposes beyond service-related communications",
      "Share your data with data brokers or analytics networks",
    ],
  },
  {
    title: "4. CEU Records and HIPAA",
    body: [
      "Your CEU records, certificate images, and license information are professional development records, NOT Protected Health Information (PHI) under HIPAA. They do not contain patient medical data. Breathe is not a HIPAA-covered entity, and your CEU data is not subject to HIPAA regulations.",
    ],
  },
  {
    title: "5. Data Security",
    body: [
      "We take the security of your data seriously and employ industry-standard protections:",
    ],
    list: [
      "Passwords are hashed using bcrypt — we never store plaintext passwords",
      "CE Broker credentials (if provided) are encrypted using AES-256 via Python's Fernet symmetric encryption",
      "Authentication uses JWT (JSON Web Tokens) with signed, time-limited tokens",
      "All API communication uses HTTPS/TLS encryption",
      "Certificate images are stored securely and accessible only to the account owner",
    ],
  },
  {
    title: "6. Data Retention",
    body: [
      "Your personal data and CEU records are retained for as long as your account is active. When you request account deletion, all associated data — including CEU records, certificate images, and personal information — is permanently deleted from our systems within 30 days.",
      "The only data retained after account deletion is anonymized Stripe transaction records required for financial compliance.",
    ],
  },
  {
    title: "7. Your Rights",
    body: [
      "You have the following rights regarding your personal data:",
    ],
    list: [
      "Access — view all personal data stored in your account at any time",
      "Export — download your CEU records and account data in a portable format",
      "Delete — permanently delete your account and all associated data",
      "Correct — update or correct any inaccurate personal information",
    ],
  },
  {
    title: "8. Third-Party Services",
    body: [
      "Breathe integrates with the following third-party services. Each has its own privacy policy that governs how they handle your data:",
    ],
    list: [
      "Stripe — payment processing for Pro plan subscriptions ($25/year). Stripe receives your payment information directly; we do not store credit card numbers.",
      "Resend — transactional email delivery for renewal reminders and account notifications.",
      "Deepgram — used in the OCR pipeline to extract text from uploaded certificate images (Pro plan feature).",
    ],
  },
  {
    title: "9. Cookies",
    body: [
      "Breathe uses minimal session cookies solely for authentication purposes. We do not use tracking cookies, advertising cookies, or third-party analytics cookies. Session cookies are essential for maintaining your login state and are deleted when you close your browser.",
    ],
  },
  {
    title: "10. Children's Privacy",
    body: [
      "Breathe is designed for licensed respiratory therapists and does not knowingly collect information from children under 13. If you believe a child has provided personal information, please contact us and we will promptly delete it.",
    ],
  },
  {
    title: "11. Changes to This Policy",
    body: [
      "We may update this Privacy Policy from time to time. Users will be notified of material changes via email or in-app notification. Continued use of the service after changes take effect constitutes acceptance of the updated policy.",
    ],
  },
  {
    title: "12. Contact",
    body: [
      "For questions about this Privacy Policy or to exercise your data rights, contact: ron.sublett@gmail.com",
    ],
  },
];

export default function PrivacyPage() {
  return (
    <div className="page-enter min-h-screen pb-20">
      {/* Header */}
      <div className="bg-gradient-to-br from-primary to-accent px-6 pt-12 pb-8 text-white rounded-b-[32px]">
        <h1 className="text-2xl font-bold">Privacy Policy</h1>
        <p className="text-white/70 text-sm mt-1">Last updated: August 14, 2026</p>
      </div>

      {/* Intro */}
      <div className="px-4 mt-6">
        <Card className="p-5">
          <p className="text-sm text-text-secondary leading-relaxed">
            Your privacy matters to us. This policy explains what data we collect, how we use it,
            and the rights you have over your personal information.
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
                      <span className="text-primary flex-shrink-0">•</span>
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
          <Link href="/terms" className="text-xs text-text-secondary hover:text-primary transition-colors">
            Terms of Service
          </Link>
          <Link href="/dashboard" className="text-xs text-text-secondary hover:text-primary transition-colors">
            Back to App
          </Link>
        </div>
      </div>
    </div>
  );
}