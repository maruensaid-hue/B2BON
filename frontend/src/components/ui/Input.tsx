import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full rounded-lg border border-border bg-surf2 px-3 py-2 text-[12.5px] text-text outline-none transition-colors focus:border-cyan",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "w-full rounded-lg border border-border bg-surf2 px-3 py-2 text-[12.5px] text-text outline-none transition-colors focus:border-cyan",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "w-full rounded-lg border border-border bg-surf2 px-3 py-2 text-[12.5px] text-text outline-none transition-colors focus:border-cyan",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}
