"use client";

import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { useAuth } from "@/lib/auth";

export default function SplashPage() {
  const { user } = useAuth();

  return (
    <div className="page-enter flex flex-col items-center justify-center min-h-screen px-6 py-12">
      <div className="flex-1 flex flex-col items-center justify-center gap-8">
        <div className="animate-pulse">
          <Logo size={96} />
        </div>
        <div className="text-center space-y-2">
          <h1 className="text-4xl font-bold bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
            Breathe
          </h1>
          <p className="text-lg text-text-secondary font-medium">
            Your career, organized.
          </p>
        </div>
        <div className="flex gap-2">
          <span className="w-2 h-2 rounded-full bg-primary" />
          <span className="w-2 h-2 rounded-full bg-accent" />
          <span className="w-2 h-2 rounded-full bg-success" />
        </div>
      </div>
      <div className="w-full space-y-3 pb-8">
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
                Get Started
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
    </div>
  );
}