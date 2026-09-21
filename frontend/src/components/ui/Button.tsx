import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "violet" | "green" | "amber" | "ghost" | "danger";

const variantClasses: Record<Variant, string> = {
  // Cor lisa (sem gradiente) igual ao azul de destaque da barra lateral
  // (`--color-cyan`) — raio-X 2026-09-21, padronização de botões: antes
  // o degradê criava um segundo tom de azul visualmente diferente do
  // `bg-cyan` usado em outros pontos da UI (ex.: item ativo do menu).
  primary: "bg-cyan text-white",
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
