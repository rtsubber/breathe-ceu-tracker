import type { Metadata } from "next";
import "./globals.css";
import { AuthGate } from "@/components/auth-gate";

export const metadata: Metadata = {
  title: "Breathe — RT CEU & Competency Tracker",
  description: "CEU tracking that actually works. Free forever. $25/year to stop doing it manually.",
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
        </div>
      </body>
    </html>
  );
}