import { cn } from "@/lib/utils";
import { ButtonHTMLAttributes, forwardRef } from "react";

const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: "primary" | "secondary" | "outline" | "ghost";
    size?: "sm" | "md" | "lg";
  }
>(({ className, variant = "primary", size = "md", ...props }, ref) => {
  return (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center font-semibold transition-all active:scale-95 disabled:opacity-50 disabled:pointer-events-none",
        {
          "bg-primary text-white hover:bg-blue-700 shadow-sm": variant === "primary",
          "bg-accent text-white hover:bg-violet-700 shadow-sm": variant === "secondary",
          "border-2 border-gray-200 bg-white text-text-primary hover:bg-gray-50": variant === "outline",
          "text-text-secondary hover:bg-gray-100": variant === "ghost",
        },
        {
          "h-9 px-3 text-sm rounded-button": size === "sm",
          "h-11 px-5 text-base rounded-button": size === "md",
          "h-14 px-6 text-lg rounded-button": size === "lg",
        },
        className
      )}
      {...props}
    />
  );
});
Button.displayName = "Button";

export { Button };