import type { Metadata } from "next";
import "./globals.css";
import { AuthGate } from "@/components/auth-gate";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Breathe — RT CEU & Competency Tracker",
  description: "CEU tracking that actually works. Free forever. $22/year to stop doing it manually.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="app-container">
          <AuthGate>{children}</AuthGate>
          <footer className="border-t border-gray-100 bg-surface px-4 py-4 text-center">
            <div className="flex justify-center gap-4 text-xs text-text-secondary">
              <Link href="/terms" className="hover:text-primary transition-colors">
                Terms of Service
              </Link>
              <span className="text-gray-300">·</span>
              <Link href="/privacy" className="hover:text-primary transition-colors">
                Privacy Policy
              </Link>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}