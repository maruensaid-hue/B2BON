import { useId, useRef, useState } from "react";

import { cn } from "@/lib/cn";

interface SeletorArquivoProps {
  accept?: string;
  disabled?: boolean;
  onSelecionar: (arquivo: File) => void;
  rotulo?: string;
  className?: string;
}

/**
 * Substitui o `<input type="file">` nativo — o botão embutido do browser
 * ("Escolher arquivo"/"Escolher ficheiro") segue o idioma do sistema
 * operacional, não o da aplicação, e mostra "ficheiro" em navegadores
 * configurados em português de Portugal. Este componente esconde o input
 * nativo e usa um botão com rótulo fixo em pt-BR.
 */
export function SeletorArquivo({ accept, disabled, onSelecionar, rotulo = "Selecionar arquivo", className }: SeletorArquivoProps) {
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [nomeArquivo, setNomeArquivo] = useState<string | null>(null);

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept={accept}
        disabled={disabled}
        className="hidden"
        onChange={(event) => {
          const arquivo = event.target.files?.[0];
          if (arquivo) {
            setNomeArquivo(arquivo.name);
            onSelecionar(arquivo);
          }
          event.target.value = "";
        }}
      />
      <label
        htmlFor={id}
        className={cn(
          "inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-transparent px-3 py-1.5 text-[11px] font-bold tracking-wide text-muted transition-colors hover:text-text",
          disabled && "pointer-events-none opacity-45",
        )}
      >
        {rotulo}
      </label>
      {nomeArquivo && <span className="truncate text-[11px] text-muted">{nomeArquivo}</span>}
    </div>
  );
}
