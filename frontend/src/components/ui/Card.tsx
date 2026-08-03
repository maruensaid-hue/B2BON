import type { HTMLAttributes } from "react";

import { cn } from "@/lib/cn";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  glow?: boolean;
}

export function Card({ glow, className, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-border bg-surf p-4.5",
        glow && "border-border2 shadow-[0_0_20px_rgba(0,194,255,0.06)]",
        className,
      )}
      {...props}
    />
  );
}

export function SectionLabel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("mb-2.5 text-[10px] tracking-wider text-muted uppercase", className)}
      {...props}
    />
  );
}
