import { useId, type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

// `label` é opcional e aditivo (Fase 7D, hardening de acessibilidade)
// — quem não passar continua exatamente como antes; quem passar
// ganha um <label htmlFor> associado de verdade, não só texto solto
// acima do campo.
interface ComLabelOpcional {
  label?: string;
}

export function Input({ className, label, id, ...props }: InputHTMLAttributes<HTMLInputElement> & ComLabelOpcional) {
  const idGerado = useId();
  const idFinal = id ?? (label ? idGerado : undefined);
  const campo = (
    <input
      id={idFinal}
      className={cn(
        "w-full rounded-lg border border-border bg-surf2 px-3 py-2 text-[12.5px] text-text outline-none transition-colors focus:border-cyan",
        className,
      )}
      {...props}
    />
  );
  if (!label) return campo;
  return (
    <div>
      <label htmlFor={idFinal} className="mb-1 block text-[10px] tracking-wide text-muted uppercase">
        {label}
      </label>
      {campo}
    </div>
  );
}

export function Textarea({
  className,
  label,
  id,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & ComLabelOpcional) {
  const idGerado = useId();
  const idFinal = id ?? (label ? idGerado : undefined);
  const campo = (
    <textarea
      id={idFinal}
      className={cn(
        "w-full rounded-lg border border-border bg-surf2 px-3 py-2 text-[12.5px] text-text outline-none transition-colors focus:border-cyan",
        className,
      )}
      {...props}
    />
  );
  if (!label) return campo;
  return (
    <div>
      <label htmlFor={idFinal} className="mb-1 block text-[10px] tracking-wide text-muted uppercase">
        {label}
      </label>
      {campo}
    </div>
  );
}

export function Select({
  className,
  children,
  label,
  id,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & ComLabelOpcional) {
  const idGerado = useId();
  const idFinal = id ?? (label ? idGerado : undefined);
  const campo = (
    <select
      id={idFinal}
      className={cn(
        "w-full rounded-lg border border-border bg-surf2 px-3 py-2 text-[12.5px] text-text outline-none transition-colors focus:border-cyan",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
  if (!label) return campo;
  return (
    <div>
      <label htmlFor={idFinal} className="mb-1 block text-[10px] tracking-wide text-muted uppercase">
        {label}
      </label>
      {campo}
    </div>
  );
}
