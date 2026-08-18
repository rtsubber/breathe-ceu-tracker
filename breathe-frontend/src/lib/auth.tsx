"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
  useCallback,
} from "react";
import { useRouter } from "next/navigation";

type User = {
  id: number;
  name: string;
  email: string;
  subscription_tier: string;
  subscription_status: string;
  onboarding_completed: boolean;
};

type AuthContextType = {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  updateUser: (user: User) => void;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    // Check for stored token on mount
    if (typeof window === "undefined") return;
    const stored = localStorage.getItem("breathe_token");
    const storedUser = localStorage.getItem("breathe_user");
    if (stored && storedUser) {
      setToken(stored);
      setUser(JSON.parse(storedUser));
      // Fetch fresh user data to catch onboarding_completed changes
      fetch("/api/me", {
        headers: { Authorization: `Bearer ${stored}` },
      })
        .then((res) => (res.ok ? res.json() : null))
        .then((freshUser) => {
          if (freshUser) {
            setUser(freshUser);
            localStorage.setItem("breathe_user", JSON.stringify(freshUser));
          }
        })
        .catch(() => {});
    }
    setLoading(false);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Login failed");
    }
    const data = await res.json();
    setToken(data.token);
    setUser(data.user);
    localStorage.setItem("breathe_token", data.token);
    localStorage.setItem("breathe_user", JSON.stringify(data.user));
  }, []);

  const register = useCallback(
    async (name: string, email: string, password: string) => {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Registration failed");
      }
      const data = await res.json();
      setToken(data.token);
      setUser(data.user);
      localStorage.setItem("breathe_token", data.token);
      localStorage.setItem("breathe_user", JSON.stringify(data.user));
    },
    [],
  );

  const updateUser = useCallback((freshUser: User) => {
    setUser(freshUser);
    localStorage.setItem("breathe_user", JSON.stringify(freshUser));
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    localStorage.removeItem("breathe_token");
    localStorage.removeItem("breathe_user");
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider
      value={{ user, token, loading, login, register, logout, updateUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}