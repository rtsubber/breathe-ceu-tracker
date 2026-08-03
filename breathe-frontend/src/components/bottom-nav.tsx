"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, FileText, Award, Gift, User } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Home", icon: Home },
  { href: "/ceus", label: "CEUs", icon: FileText },
  { href: "/free-courses", label: "Free CEU", icon: Gift },
  { href: "/credentials", label: "Creds", icon: Award },
  { href: "/profile", label: "Profile", icon: User },
];

export function BottomNav() {
  const pathname = usePathname();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-gray-200 bottom-nav-safe">
      <div className="max-w-app mx-auto flex items-center justify-around h-16 px-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex flex-col items-center justify-center gap-1 px-2 py-2 rounded-button transition-all",
                active
                  ? "text-primary"
                  : "text-text-secondary hover:text-text-primary",
              )}
            >
              <Icon size={20} strokeWidth={active ? 2.5 : 2} />
              <span
                className={cn(
                  "text-[10px] font-medium leading-none",
                  active && "font-semibold",
                )}
              >
                {item.label}
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}