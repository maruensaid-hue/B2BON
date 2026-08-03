import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "violet" | "green" | "amber" | "ghost" | "danger";

const variantClasses: Record<Variant, string> = {
  primary: "bg-gradient-to-br from-cyan to-[#007AAA] text-bg",
  violet: "bg-gradient-to-br from-violet to-[#5B21B6] text-white",
  green: "bg-gradient-to-br from-green to-[#059669] text-white",
  amber: "bg-gradient-to-br from-amber to-[#B45309] text-bg",
  ghost: "bg-transparent text-muted border border-border hover:text-text",
  danger: "bg-red/15 text-red border border-red/30",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "default" | "sm";
}

export function Button({ variant = "primary", size = "default", className, ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg font-bold tracking-wide transition-transform active:scale-95 disabled:opacity-45 disabled:cursor-not-allowed",
        size === "default" ? "px-4 py-2.5 text-[12.5px]" : "px-3 py-1.5 text-[11px]",
        variantClasses[variant],
        className,
      )}
      {...props}
    />
  );
}
