import { cn } from "@/lib/utils";
import { HTMLAttributes, forwardRef } from "react";

const Card = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "bg-surface rounded-card shadow-sm border border-gray-100 p-4",
        className
      )}
      {...props}
    />
  )
);
Card.displayName = "Card";

export { Card };