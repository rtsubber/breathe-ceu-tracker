"use client";

import { useEffect, useState } from "react";
import { CheckCircle2 } from "lucide-react";

export function Toast({ message, show }: { message: string; show: boolean }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (show) {
      setVisible(true);
      const timer = setTimeout(() => setVisible(false), 3000);
      return () => clearTimeout(timer);
    }
  }, [show]);

  if (!visible) return null;

  return (
    <div className="fixed top-4 left-0 right-0 z-[100] flex justify-center px-4 toast-enter">
      <div className="bg-text-primary text-white px-5 py-3 rounded-button shadow-lg flex items-center gap-2 max-w-app">
        <CheckCircle2 size={20} className="text-success" />
        <span className="text-sm font-medium">{message}</span>
      </div>
    </div>
  );
}