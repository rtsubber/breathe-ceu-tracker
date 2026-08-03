"use client";

import { useEffect, ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import { AuthProvider, useAuth } from "@/lib/auth";
import { Loader2 } from "lucide-react";

// Routes that don't require authentication
const PUBLIC_ROUTES = new Set([
  "/",
  "/login",
  "/register",
  "/pricing",
]);

// Routes that start with these prefixes are public
const PUBLIC_PREFIXES = ["/api"];

function isPublicRoute(pathname: string): boolean {
  if (PUBLIC_ROUTES.has(pathname)) return true;
  for (const prefix of PUBLIC_PREFIXES) {
    if (pathname.startsWith(prefix)) return true;
  }
  return false;
}

function AuthGuard({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (loading) return;
    if (!user && !isPublicRoute(pathname)) {
      router.replace("/login");
    }
    // If logged in and on login/register, go to dashboard
    // Onboarding only shows on first registration (register page pushes to /onboarding)
    if (user && (pathname === "/login" || pathname === "/register")) {
      router.replace("/dashboard");
    }
  }, [user, loading, pathname, router]);

  // Show loading spinner only for protected routes
  if (loading && !isPublicRoute(pathname)) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  // If not authenticated and on a protected route, show spinner while redirecting
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