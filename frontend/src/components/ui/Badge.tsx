import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Tone = "cyan" | "violet" | "green" | "amber" | "red" | "muted";

const toneClasses: Record<Tone, string> = {
  cyan: "text-cyan bg-cyan/15 border-cyan/25",
  violet: "text-violet bg-violet/15 border-violet/25",
  green: "text-green bg-green/15 border-green/25",
  amber: "text-amber bg-amber/15 border-amber/25",
  red: "text-red bg-red/15 border-red/25",
  muted: "text-muted bg-muted/10 border-border",
};

export function Badge({ tone = "muted", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold tracking-wide uppercase",
        toneClasses[tone],
      )}
    >
      {children}
    </span>
  );
}
