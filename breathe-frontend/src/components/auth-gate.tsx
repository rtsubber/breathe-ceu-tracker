"use client";

import { useEffect, ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import { AuthProvider, useAuth } from "@/lib/auth";
import { Loader2 } from "lucide-react";

const PUBLIC_ROUTES = new Set(["/", "/login", "/register", "/pricing", "/terms", "/privacy"]);

function isPublicRoute(pathname: string): boolean {
  if (PUBLIC_ROUTES.has(pathname)) return true;
  if (pathname.startsWith("/api")) return true;
  return false;
}

function AuthGuard({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (loading) return;

    // Not logged in, on a protected route → login
    if (!user && !isPublicRoute(pathname)) {
      router.replace("/login");
      return;
    }

    if (user) {
      const needsOnboarding = !user.onboarding_completed;

      // Only redirect from auth pages, not from public landing/pricing pages
      const authPages = ["/login", "/register", "/onboarding"];
      const isAuthPage = authPages.includes(pathname);

      // Logged in but hasn't finished onboarding → force to /onboarding
      // (unless they're already there or on a public non-auth page like landing/pricing)
      if (needsOnboarding && pathname !== "/onboarding" && !PUBLIC_ROUTES.has(pathname)) {
        router.replace("/onboarding");
        return;
      }

      // Logged in AND onboarded, but sitting on auth pages → dashboard
      if (!needsOnboarding && isAuthPage) {
        router.replace("/dashboard");
        return;
      }
    }
  }, [user, loading, pathname, router]);

  // Show loading spinner for protected routes while loading
  if (loading && !isPublicRoute(pathname)) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  // Not authenticated and on a protected route — show spinner while redirecting
  if (!user && !isPublicRoute(pathname)) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  return <>{children}</>;
}

export function AuthGate({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <AuthGuard>{children}</AuthGuard>
    </AuthProvider>
  );
}