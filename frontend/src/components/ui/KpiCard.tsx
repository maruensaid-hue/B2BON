import { cn } from "@/lib/cn";

interface KpiCardProps {
  label: string;
  value: string | number;
  sub?: string;
  colorClassName?: string;
}

export function KpiCard({ label, value, sub, colorClassName = "text-cyan" }: KpiCardProps) {
  return (
    <div className="rounded-xl border border-border bg-surf2 p-3.5">
      <div className="mb-1.5 text-[9.5px] tracking-wider text-muted uppercase">{label}</div>
      <div className={cn("font-head text-[26px] leading-none font-bold", colorClassName)}>{value}</div>
      {sub && <div className="mt-1 text-[10px] text-muted">{sub}</div>}
    </div>
  );
}
